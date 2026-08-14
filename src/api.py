"""
Flask API Backend for 3D Dashboard
====================================

Exposes simulation data as JSON endpoints for the Three.js frontend.
Runs the simulation once on startup and caches results.
Includes SSE (Server-Sent Events) for streaming collision scenarios in real-time.
"""

import numpy as np
import json
import time
import threading
from flask import Flask, jsonify, send_from_directory, Response, request
from flask.json.provider import DefaultJSONProvider
from flask_cors import CORS
import os
import sys

# Add parent to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.utils import (
    state_to_coe, coe_to_state, R_EARTH, MU_EARTH, orbital_period,
    StateVector, OrbitalElements, Spacecraft
)


class NumpyJSONProvider(DefaultJSONProvider):
    """Custom JSON provider that handles numpy types."""

    @staticmethod
    def default(obj):
        if isinstance(obj, np.integer):
            return int(obj)
        elif isinstance(obj, np.floating):
            return float(obj)
        elif isinstance(obj, np.ndarray):
            return obj.tolist()
        elif isinstance(obj, np.bool_):
            return bool(obj)
        return DefaultJSONProvider.default(obj)
from src.simulation import (
    CollisionPreventionSimulation,
    generate_leo_constellation,
    inject_collision_scenario
)
from src.conjunction import compute_risk_score, estimate_debris_count, debris_lifetime
from src.risk_optimizer import OrbitalEnvironment, RiskGraph, InterventionOptimizer
from src.orbital_mechanics import generate_ephemeris, propagate_state


app = Flask(__name__, static_folder='../dashboard', static_url_path='')
app.json_provider_class = NumpyJSONProvider
app.json = NumpyJSONProvider(app)
CORS(app)

# Global simulation cache
SIM_DATA = {}


# ============================================================================
# COLLISION SCENARIO GENERATION
# ============================================================================


def generate_collision_scenarios(spacecraft_list, conjunctions):
    """
    Generate pre-computed collision + course correction scenarios for animation.

    Each scenario includes:
    - Two spacecraft trajectories approaching each other
    - A maneuver burn point where the correction fires
    - The corrected (safe) trajectory
    - The uncorrected (collision) trajectory with debris cloud
    - Timestamped events for SSE streaming
    """
    scenarios = {}
    sc_dict = {sc.id: sc for sc in spacecraft_list}

    # Scenario 1: Head-on high-speed collision with successful avoidance
    scenarios['head_on_avoidance'] = _build_scenario(
        name="Head-On Collision Avoidance",
        description="COMSAT narrowly avoids debris at 14.2 km/s. Burn at T-45min saves the day.",
        altitude_km=650,
        inclination1_deg=85,
        inclination2_deg=95,
        relative_velocity_kms=14.2,
        mass1=300, mass2=2000,
        maneuver_dv_ms=2.5,
        maneuver_time_fraction=0.4,
        has_correction=True
    )

    # Scenario 2: Catastrophic collision (no correction possible)
    scenarios['catastrophic_collision'] = _build_scenario(
        name="Catastrophic Collision",
        description="Defunct satellite hits debris. No maneuver capability. 400+ fragments generated.",
        altitude_km=780,
        inclination1_deg=72,
        inclination2_deg=78,
        relative_velocity_kms=10.8,
        mass1=1500, mass2=800,
        maneuver_dv_ms=0,
        maneuver_time_fraction=0.5,
        has_correction=False
    )

    # Scenario 3: Close pass with last-minute correction
    scenarios['last_minute_save'] = _build_scenario(
        name="Last-Minute Course Correction",
        description="EOS satellite detects risk late. Emergency burn at T-12min with 0.3km clearance.",
        altitude_km=520,
        inclination1_deg=55,
        inclination2_deg=58,
        relative_velocity_kms=7.5,
        mass1=1200, mass2=350,
        maneuver_dv_ms=4.8,
        maneuver_time_fraction=0.75,
        has_correction=True
    )

    return scenarios


def _build_scenario(name, description, altitude_km, inclination1_deg, inclination2_deg,
                    relative_velocity_kms, mass1, mass2, maneuver_dv_ms,
                    maneuver_time_fraction, has_correction):
    """Build a single collision/correction scenario with trajectory data."""

    n_frames = 200  # Total animation frames
    maneuver_frame = int(n_frames * maneuver_time_fraction)
    tca_frame = int(n_frames * 0.82)  # Close approach happens at 82% through

    # Orbital radius
    r_orbit = R_EARTH + altitude_km

    # Collision point: both objects meet here
    # Place it at an interesting position visible from default camera
    collision_point = np.array([0.0, r_orbit * 0.3, r_orbit * 0.95])
    collision_point = collision_point / np.linalg.norm(collision_point) * r_orbit

    # Object 1: approaches collision point from one arc direction
    # Object 2: approaches from a crossing direction (different orbital plane)
    # Both converge at tca_frame

    # Build approach directions (unit vectors perpendicular to radial at collision point)
    radial = collision_point / np.linalg.norm(collision_point)
    # Two velocity directions that cross at the collision point
    arbitrary = np.array([1, 0, 0]) if abs(radial[0]) < 0.9 else np.array([0, 1, 0])
    tangent1 = np.cross(radial, arbitrary)
    tangent1 = tangent1 / np.linalg.norm(tangent1)
    # Rotate for inclination difference
    angle_between = np.radians(inclination2_deg - inclination1_deg)
    tangent2 = (tangent1 * np.cos(angle_between) +
                np.cross(radial, tangent1) * np.sin(angle_between))
    tangent2 = tangent2 / np.linalg.norm(tangent2)

    # Arc length traversed (fraction of orbit)
    arc_half = np.radians(40)  # Each object travels 40 degrees of arc to/from TCA

    path1 = []
    path1_corrected = []
    path2 = []

    for i in range(n_frames):
        # Parametric time: -1 at start, 0 at TCA, +1 at end
        t_param = (i - tca_frame) / tca_frame  # Normalized so TCA=0

        # Object 1: arc along tangent1 direction, centered on collision point
        arc_angle1 = t_param * arc_half
        # Rodrigues rotation of collision_point around the cross(radial, tangent1) axis
        axis1 = np.cross(radial, tangent1)
        axis1 = axis1 / np.linalg.norm(axis1)
        pos1 = (collision_point * np.cos(arc_angle1) +
                np.cross(axis1, collision_point) * np.sin(arc_angle1) +
                axis1 * np.dot(axis1, collision_point) * (1 - np.cos(arc_angle1)))

        # Object 2: arc along tangent2 direction (crossing orbit)
        arc_angle2 = -t_param * arc_half * 0.95  # Slightly different speed
        axis2 = np.cross(radial, tangent2)
        axis2 = axis2 / np.linalg.norm(axis2)
        pos2 = (collision_point * np.cos(arc_angle2) +
                np.cross(axis2, collision_point) * np.sin(arc_angle2) +
                axis2 * np.dot(axis2, collision_point) * (1 - np.cos(arc_angle2)))

        path1.append([float(pos1[0]), float(pos1[1]), float(pos1[2])])
        path2.append([float(pos2[0]), float(pos2[1]), float(pos2[2])])

        # Corrected path for object 1
        if i < maneuver_frame or not has_correction:
            path1_corrected.append([float(pos1[0]), float(pos1[1]), float(pos1[2])])
        else:
            # After maneuver: offset perpendicular to both velocity and radial
            progress = (i - maneuver_frame) / max(n_frames - maneuver_frame, 1)
            # Offset grows quadratically (realistic: dv causes linear drift)
            offset_mag = maneuver_dv_ms * 0.4 * progress ** 1.3  # km
            # Cross-track offset direction
            offset_dir = np.cross(tangent1, radial)
            offset_dir = offset_dir / np.linalg.norm(offset_dir)
            corrected_pos = pos1 + offset_dir * offset_mag
            # Keep at orbital altitude
            corrected_pos = corrected_pos / np.linalg.norm(corrected_pos) * r_orbit
            path1_corrected.append([float(corrected_pos[0]), float(corrected_pos[1]), float(corrected_pos[2])])

    # Compute distances for each frame
    distances = []
    distances_corrected = []
    for i in range(n_frames):
        p1 = np.array(path1[i])
        p2 = np.array(path2[i])
        p1c = np.array(path1_corrected[i])
        distances.append(float(np.linalg.norm(p1 - p2)))
        distances_corrected.append(float(np.linalg.norm(p1c - p2)))

    min_distance = min(distances)
    min_distance_corrected = min(distances_corrected)

    # Generate debris cloud at collision point (if no correction)
    debris_fragments = []
    if not has_correction:
        n_debris = int(estimate_debris_count(mass1, mass2, relative_velocity_kms))
        cp = collision_point
        for _ in range(min(n_debris, 300)):
            spread = altitude_km * 0.005
            debris_fragments.append([
                float(cp[0] + np.random.normal(0, spread)),
                float(cp[1] + np.random.normal(0, spread)),
                float(cp[2] + np.random.normal(0, spread)),
            ])

    # Build SSE events timeline
    events = []
    events.append({
        'frame': 0,
        'type': 'scenario_start',
        'message': f'Tracking conjunction: {name}',
        'data': {'relative_velocity': relative_velocity_kms, 'altitude': altitude_km}
    })
    events.append({
        'frame': int(n_frames * 0.15),
        'type': 'detection',
        'message': f'Conjunction detected. Pc rising. Miss distance: {min_distance:.1f} km',
        'data': {'pc': 2.3e-4, 'miss_distance': min_distance}
    })
    events.append({
        'frame': int(n_frames * 0.3),
        'type': 'risk_assessment',
        'message': f'Risk level: CRITICAL. Relative velocity: {relative_velocity_kms} km/s',
        'data': {'risk_level': 'CRITICAL', 'fragments_if_collision': int(estimate_debris_count(mass1, mass2, relative_velocity_kms))}
    })

    if has_correction:
        events.append({
            'frame': maneuver_frame - 5,
            'type': 'maneuver_planning',
            'message': f'Computing optimal avoidance maneuver. dv={maneuver_dv_ms:.1f} m/s',
            'data': {'delta_v_ms': maneuver_dv_ms, 'direction': 'cross-track'}
        })
        events.append({
            'frame': maneuver_frame,
            'type': 'maneuver_execute',
            'message': f'BURN INITIATED. Thruster firing: {maneuver_dv_ms:.1f} m/s cross-track',
            'data': {'delta_v_ms': maneuver_dv_ms, 'burn_duration_s': maneuver_dv_ms * 2}
        })
        events.append({
            'frame': maneuver_frame + 10,
            'type': 'maneuver_complete',
            'message': 'Burn complete. New trajectory confirmed.',
            'data': {'fuel_used_ms': maneuver_dv_ms}
        })
        events.append({
            'frame': tca_frame,
            'type': 'closest_approach',
            'message': f'TCA passed. Miss distance: {min_distance_corrected:.2f} km. SAFE.',
            'data': {'miss_distance_corrected': min_distance_corrected, 'status': 'SAFE'}
        })
        events.append({
            'frame': n_frames - 10,
            'type': 'scenario_end',
            'message': 'Conjunction resolved. Returning to nominal operations.',
            'data': {'outcome': 'AVOIDANCE_SUCCESS'}
        })
    else:
        events.append({
            'frame': maneuver_frame,
            'type': 'no_maneuver',
            'message': 'NO MANEUVER CAPABILITY. Object is non-maneuverable debris.',
            'data': {'reason': 'non_maneuverable'}
        })
        events.append({
            'frame': tca_frame - 5,
            'type': 'impact_imminent',
            'message': f'IMPACT IMMINENT. Relative velocity: {relative_velocity_kms} km/s',
            'data': {'time_to_impact_s': 30}
        })
        events.append({
            'frame': tca_frame,
            'type': 'collision',
            'message': f'COLLISION DETECTED. {int(estimate_debris_count(mass1, mass2, relative_velocity_kms))} fragments generated.',
            'data': {
                'fragments': int(estimate_debris_count(mass1, mass2, relative_velocity_kms)),
                'is_catastrophic': True,
                'energy_j_per_kg': float(0.5 * min(mass1, mass2) * (relative_velocity_kms * 1000) ** 2 / max(mass1, mass2))
            }
        })
        events.append({
            'frame': n_frames - 10,
            'type': 'scenario_end',
            'message': 'Debris cloud expanding. Cascade risk elevated.',
            'data': {'outcome': 'COLLISION', 'cascade_risk': 'HIGH'}
        })

    return {
        'name': name,
        'description': description,
        'n_frames': n_frames,
        'maneuver_frame': maneuver_frame,
        'collision_frame': tca_frame,
        'tca_frame': tca_frame,
        'has_correction': has_correction,
        'path_object1': path1,
        'path_object1_corrected': path1_corrected,
        'path_object2': path2,
        'distances': distances,
        'distances_corrected': distances_corrected,
        'min_distance_km': float(min_distance),
        'min_distance_corrected_km': float(min_distance_corrected),
        'debris_fragments': debris_fragments,
        'events': events,
        'metadata': {
            'altitude_km': altitude_km,
            'relative_velocity_kms': relative_velocity_kms,
            'mass1_kg': mass1,
            'mass2_kg': mass2,
            'maneuver_dv_ms': maneuver_dv_ms,
            'object1_type': 'COMSAT' if mass1 < 500 else 'EOS',
            'object2_type': 'DEBRIS' if not has_correction else 'COMSAT',
        }
    }


def run_simulation():
    """Run the simulation and cache all data for the API."""

    print("Running satellite collision simulation...")
    sim = CollisionPreventionSimulation(n_spacecraft=50, seed=42)
    sim.run_full_simulation()

    # Extract spacecraft data with orbital info
    spacecraft_data = []
    for sc in sim.spacecraft_list:
        coe = state_to_coe(sc.state)
        altitude = coe.a - R_EARTH
        period = orbital_period(coe.a)

        # Generate orbit path (one full orbit)
        n_points = 120
        times = np.linspace(0, period, n_points)
        try:
            ephemeris = generate_ephemeris(sc.state, times)
            orbit_path = ephemeris[:, :3].tolist()
        except Exception:
            orbit_path = []

        spacecraft_data.append({
            'id': sc.id,
            'name': sc.name,
            'position': sc.state.r.tolist(),
            'velocity': sc.state.v.tolist(),
            'mass': sc.mass,
            'area': sc.area,
            'maneuverable': sc.maneuverable,
            'altitude_km': float(altitude),
            'eccentricity': float(coe.e),
            'inclination_deg': float(np.degrees(coe.i)),
            'raan_deg': float(np.degrees(coe.raan)),
            'period_min': float(period / 60.0),
            'fuel_remaining_ms': float(sc.delta_v_budget - sc.delta_v_used),
            'fuel_budget_ms': float(sc.delta_v_budget),
            'orbit_path': orbit_path,
            'type': sc.id.split('_')[0]
        })

    # Extract conjunction data
    conjunction_data = []
    sc_dict = {sc.id: sc for sc in sim.spacecraft_list}
    for conj in sim.conjunctions:
        sc1 = sc_dict.get(conj.obj1_id)
        sc2 = sc_dict.get(conj.obj2_id)
        if not sc1 or not sc2:
            continue

        conjunction_data.append({
            'obj1_id': conj.obj1_id,
            'obj2_id': conj.obj2_id,
            'obj1_pos': sc1.state.r.tolist(),
            'obj2_pos': sc2.state.r.tolist(),
            'tca_hours': float(conj.tca / 3600.0),
            'miss_distance_km': float(conj.miss_distance),
            'relative_velocity_kms': float(conj.relative_velocity),
            'probability_of_collision': float(conj.probability_of_collision),
            'risk_score': float(conj.risk_score),
            'risk_level': (
                'CRITICAL' if conj.probability_of_collision >= 1e-4
                else 'HIGH' if conj.probability_of_collision >= 1e-5
                else 'MEDIUM' if conj.probability_of_collision >= 1e-6
                else 'LOW'
            )
        })

    # Extract maneuver data
    maneuver_data = []
    for man in sim.planned_maneuvers:
        sc = sc_dict.get(man.spacecraft_id)
        if not sc:
            continue
        maneuver_data.append({
            'spacecraft_id': man.spacecraft_id,
            'time_hours': float(man.time / 3600.0),
            'delta_v_rtn_ms': (man.delta_v * 1000).tolist(),
            'fuel_cost_ms': float(man.fuel_cost),
            'target_conjunction': man.target_conjunction_id,
            'spacecraft_pos': sc.state.r.tolist()
        })

    # Risk metrics
    risk_metrics = {
        'total_spacecraft': len(sim.spacecraft_list),
        'maneuverable': sum(1 for sc in sim.spacecraft_list if sc.maneuverable),
        'non_maneuverable': sum(1 for sc in sim.spacecraft_list if not sc.maneuverable),
        'total_conjunctions': len(sim.conjunctions),
        'critical_conjunctions': sum(1 for c in sim.conjunctions if c.probability_of_collision >= 1e-4),
        'high_risk_conjunctions': sum(1 for c in sim.conjunctions if 1e-5 <= c.probability_of_collision < 1e-4),
        'maneuvers_planned': len(sim.planned_maneuvers),
        'total_fuel_cost_ms': float(sum(m.fuel_cost for m in sim.planned_maneuvers)) if sim.planned_maneuvers else 0,
        'total_mass_kg': float(sum(sc.mass for sc in sim.spacecraft_list)),
        'max_pc': float(max((c.probability_of_collision for c in sim.conjunctions), default=0)),
        'avg_altitude_km': float(np.mean([state_to_coe(sc.state).a - R_EARTH for sc in sim.spacecraft_list])),
    }

    # Risk graph data for network visualization
    risk_graph_data = {'nodes': [], 'edges': []}
    if sim.risk_graph:
        for node in sim.risk_graph.graph.nodes(data=True):
            risk_graph_data['nodes'].append({
                'id': node[0],
                'altitude_km': node[1].get('altitude_km', 0),
                'maneuverable': node[1].get('maneuverable', False),
                'fuel_remaining': node[1].get('fuel_remaining', 0),
            })
        for u, v, data in sim.risk_graph.graph.edges(data=True):
            risk_graph_data['edges'].append({
                'source': u,
                'target': v,
                'risk_score': float(data.get('risk_score', 0)),
                'pc': float(data.get('pc', 0)),
            })

    # Orbital environment (altitude shells)
    shell_data = []
    if sim.environment:
        for shell in sim.environment.shells:
            shell_data.append({
                'alt_min_km': float(shell.alt_min_km),
                'alt_max_km': float(shell.alt_max_km),
                'object_count': shell.object_count,
                'collision_rate': float(shell.collision_rate),
                'debris_generation_rate': float(shell.debris_generation_rate),
                'debris_removal_rate': float(shell.debris_removal_rate),
                'is_unstable': shell.is_unstable
            })

    # Debris prediction data (from unavoidable collisions)
    debris_data = []
    for conj in sim.conjunctions[:3]:
        sc1 = sc_dict.get(conj.obj1_id)
        sc2 = sc_dict.get(conj.obj2_id)
        if sc1 and sc2:
            n_debris = estimate_debris_count(sc1.mass, sc2.mass, conj.relative_velocity)
            alt = state_to_coe(sc1.state).a - R_EARTH
            lifetime = debris_lifetime(alt)
            debris_data.append({
                'conjunction_id': f"{conj.obj1_id}_{conj.obj2_id}",
                'fragment_count_10cm': n_debris,
                'altitude_km': float(alt),
                'lifetime_years': float(lifetime),
                'is_catastrophic': bool(float(conj.relative_velocity) > 5.0 and (sc1.mass + sc2.mass) > 500),
                'position': sc1.state.r.tolist(),
            })

    # Risk evolution timeline
    risk_timeline = []
    base_risk = risk_metrics['max_pc']
    for hour in range(0, 25):
        factor = 1.0
        if hour < 5:
            factor = 0.3 + 0.7 * (hour / 5.0)
        elif hour > 20:
            factor = 1.0 - 0.5 * ((hour - 20) / 4.0)
        risk_timeline.append({
            'hour': hour,
            'total_risk': float(base_risk * factor * len(sim.conjunctions)),
            'conjunctions_active': max(1, len(sim.conjunctions) - hour // 5),
            'maneuvers_executed': min(len(sim.planned_maneuvers), hour // 4)
        })

    # ========================================================================
    # COLLISION / COURSE CORRECTION SCENARIOS (for animated visualization)
    # ========================================================================
    scenarios = generate_collision_scenarios(sim.spacecraft_list, sim.conjunctions)

    SIM_DATA.clear()
    SIM_DATA.update({
        'spacecraft': spacecraft_data,
        'conjunctions': conjunction_data,
        'maneuvers': maneuver_data,
        'risk_metrics': risk_metrics,
        'risk_graph': risk_graph_data,
        'shells': shell_data,
        'debris': debris_data,
        'risk_timeline': risk_timeline,
        'scenarios': scenarios,
    })

    print(f"Simulation complete. Serving dashboard...")


# ============================================================================
# API ROUTES
# ============================================================================


@app.route('/')
def serve_dashboard():
    """Serve the main dashboard HTML."""
    return send_from_directory(app.static_folder, 'index.html')


@app.route('/api/spacecraft')
def get_spacecraft():
    """All spacecraft with orbital data and paths."""
    return jsonify(SIM_DATA.get('spacecraft', []))


@app.route('/api/conjunctions')
def get_conjunctions():
    """All conjunction events with risk levels."""
    return jsonify(SIM_DATA.get('conjunctions', []))


@app.route('/api/maneuvers')
def get_maneuvers():
    """Planned avoidance maneuvers."""
    return jsonify(SIM_DATA.get('maneuvers', []))


@app.route('/api/risk')
def get_risk_metrics():
    """Global risk metrics summary."""
    return jsonify(SIM_DATA.get('risk_metrics', {}))


@app.route('/api/risk-graph')
def get_risk_graph():
    """Risk graph (nodes = spacecraft, edges = conjunctions)."""
    return jsonify(SIM_DATA.get('risk_graph', {}))


@app.route('/api/shells')
def get_shells():
    """Orbital environment altitude shells."""
    return jsonify(SIM_DATA.get('shells', []))


@app.route('/api/debris')
def get_debris():
    """Debris prediction data."""
    return jsonify(SIM_DATA.get('debris', []))


@app.route('/api/timeline')
def get_timeline():
    """Risk evolution timeline."""
    return jsonify(SIM_DATA.get('risk_timeline', []))


@app.route('/api/all')
def get_all():
    """All simulation data in a single request (for initial load)."""
    return jsonify(SIM_DATA)


@app.route('/api/scenario/<scenario_id>')
def get_scenario(scenario_id):
    """Get a pre-computed collision/correction scenario for animation."""
    scenarios = SIM_DATA.get('scenarios', {})
    if scenario_id in scenarios:
        return jsonify(scenarios[scenario_id])
    return jsonify({'error': 'Scenario not found'}), 404


@app.route('/api/scenarios')
def get_scenarios_list():
    """List available scenarios."""
    scenarios = SIM_DATA.get('scenarios', {})
    return jsonify([
        {'id': k, 'name': v['name'], 'description': v['description']}
        for k, v in scenarios.items()
    ])


@app.route('/api/scenario/<scenario_id>/stream')
def stream_scenario(scenario_id):
    """
    SSE (Server-Sent Events) endpoint that streams simulation events in real-time.

    The client connects and receives a stream of events as the scenario "plays":
    - Frame updates with positions
    - Detection events
    - Maneuver commands
    - Collision or safe-pass confirmations

    Query params:
        speed: playback speed multiplier (default 1.0)
    """
    scenarios = SIM_DATA.get('scenarios', {})
    if scenario_id not in scenarios:
        return jsonify({'error': 'Scenario not found'}), 404

    scenario = scenarios[scenario_id]
    speed = float(request.args.get('speed', 1.0))

    def event_stream():
        n_frames = scenario['n_frames']
        events = scenario['events']
        path1 = scenario['path_object1']
        path1_corrected = scenario['path_object1_corrected']
        path2 = scenario['path_object2']
        distances = scenario['distances']
        distances_corrected = scenario['distances_corrected']
        has_correction = scenario['has_correction']
        maneuver_frame = scenario['maneuver_frame']
        debris = scenario['debris_fragments']

        event_idx = 0
        frame_interval = 0.05 / speed  # ~20 FPS at speed=1

        # Send initial scenario metadata
        yield f"event: scenario_info\ndata: {json.dumps({'name': scenario['name'], 'n_frames': n_frames, 'has_correction': has_correction, 'metadata': scenario['metadata']})}\n\n"

        for frame in range(n_frames):
            # Current positions
            use_corrected = has_correction and frame >= maneuver_frame
            pos1 = path1_corrected[frame] if use_corrected else path1[frame]
            pos2 = path2[frame]
            dist = distances_corrected[frame] if use_corrected else distances[frame]

            # Frame data
            frame_data = {
                'frame': frame,
                'progress': frame / n_frames,
                'object1_pos': pos1,
                'object2_pos': pos2,
                'distance_km': dist,
                'is_corrected': use_corrected,
            }

            yield f"event: frame\ndata: {json.dumps(frame_data)}\n\n"

            # Check for events at this frame
            while event_idx < len(events) and events[event_idx]['frame'] <= frame:
                evt = events[event_idx]
                evt_data = {
                    'type': evt['type'],
                    'message': evt['message'],
                    'data': evt['data'],
                    'frame': evt['frame']
                }
                yield f"event: sim_event\ndata: {json.dumps(evt_data)}\n\n"

                # If collision, send debris
                if evt['type'] == 'collision' and debris:
                    yield f"event: debris_spawn\ndata: {json.dumps({'fragments': debris[:100], 'total_count': len(debris)})}\n\n"

                event_idx += 1

            time.sleep(frame_interval)

        # End of stream
        yield f"event: stream_end\ndata: {json.dumps({'status': 'complete'})}\n\n"

    return Response(
        event_stream(),
        mimetype='text/event-stream',
        headers={
            'Cache-Control': 'no-cache',
            'Connection': 'keep-alive',
            'X-Accel-Buffering': 'no',
        }
    )


# ============================================================================
# ENTRY POINT
# ============================================================================


if __name__ == '__main__':
    run_simulation()
    print("\n" + "=" * 60)
    print("  DASHBOARD RUNNING: http://localhost:8050")
    print("=" * 60 + "\n")
    app.run(host='0.0.0.0', port=8050, debug=False)
