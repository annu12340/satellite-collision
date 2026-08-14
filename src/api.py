"""
Flask API Backend for 3D Dashboard
====================================

Exposes simulation data as JSON endpoints for the Three.js frontend.
Runs the simulation once on startup and caches results.
"""

import numpy as np
from flask import Flask, jsonify, send_from_directory
from flask.json.provider import DefaultJSONProvider
from flask_cors import CORS
import os
import sys

# Add parent to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.utils import state_to_coe, R_EARTH, MU_EARTH, orbital_period


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
from src.orbital_mechanics import generate_ephemeris


app = Flask(__name__, static_folder='../dashboard', static_url_path='')
app.json_provider_class = NumpyJSONProvider
app.json = NumpyJSONProvider(app)
CORS(app)

# Global simulation cache
SIM_DATA = {}


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


# ============================================================================
# ENTRY POINT
# ============================================================================


if __name__ == '__main__':
    run_simulation()
    print("\n" + "=" * 60)
    print("  DASHBOARD RUNNING: http://localhost:8050")
    print("=" * 60 + "\n")
    app.run(host='0.0.0.0', port=8050, debug=False)
