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
    StateVector, OrbitalElements, Spacecraft, CATASTROPHIC_ENERGY
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
from src.conjunction import (
    compute_risk_score, estimate_debris_count, debris_lifetime,
    build_bplane_projection, project_relative_position_series,
    covariance_ellipse_params, probability_of_collision_foster
)
from src.utils import StateVector as _StateVector
from src.risk_optimizer import (
    OrbitalEnvironment, RiskGraph, InterventionOptimizer, project_risk_evolution
)
from src.orbital_mechanics import generate_ephemeris, propagate_state
from src.damage_minimization import predict_collision_outcome, collision_specific_energy
from src.simulation import plot_orbits_3d
from src.ai_analysis import plan_intervention_from_query

# Absolute path to the repo root (where the matplotlib PNGs are saved)
ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


app = Flask(__name__, static_folder='../dashboard', static_url_path='')
app.json_provider_class = NumpyJSONProvider
app.json = NumpyJSONProvider(app)
CORS(app)

# Global simulation cache
SIM_DATA = {}
SIM_LOCK = threading.Lock()

# Holds the live CollisionPreventionSimulation object (spacecraft/conjunction
# objects, not just their serialized JSON form) so cuOpt-backed endpoints
# like /api/plan can run a fresh MILP solve against the current scenario.
_CURRENT_SIM = {'sim': None}


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


def _estimate_hard_body_radius_m(mass_kg):
    """
    Rough bus-size scaling for a spacecraft's effective hard-body radius,
    used only for the demo scenario's B-plane hard-body-radius circle
    (real conjunction assessment in conjunction.py derives this from actual
    cross-sectional area: r = sqrt(area / pi), see compute_collision_probability).

    Scales with the cube root of mass, clamped to a plausible bus-only
    range (without solar panels) of roughly 0.3-3 m.
    """
    r_m = 0.3 + 0.08 * mass_kg ** (1.0 / 3.0)
    return float(np.clip(r_m, 0.3, 3.0))


def _build_covariance_ellipse(sigma_major_km, sigma_minor_km, angle_rad, n_sigma=3.0):
    """
    Construct a 2x2 encounter-plane covariance matrix from desired
    principal sigmas and orientation, then immediately round-trip it
    through conjunction.covariance_ellipse_params() -- the same
    eigendecomposition routine the real conjunction-assessment pipeline
    uses to render B-plane confidence ellipses. This keeps the demo
    scenario's *rendering* path identical to the production path, even
    though the covariance *inputs* here are procedurally generated instead
    of coming from real tracking data.

    Returns
    -------
    covariance_2d : ndarray (2, 2)
    (semi_major_km, semi_minor_km, ellipse_angle_rad) : tuple of float
    """
    c, s = np.cos(angle_rad), np.sin(angle_rad)
    R = np.array([[c, -s], [s, c]])
    sigma_sq = np.diag([
        (sigma_major_km / n_sigma) ** 2,
        (sigma_minor_km / n_sigma) ** 2
    ])
    covariance_2d = R @ sigma_sq @ R.T
    ellipse = covariance_ellipse_params(covariance_2d, n_sigma=n_sigma)
    return covariance_2d, ellipse


def _build_bplane_track(path1, path2, path1_corrected, maneuver_frame, tca_frame,
                         n_frames, has_correction, mass1, mass2,
                         cov_update_frame, sigma_before_m=500.0, sigma_after_m=120.0):
    """
    Compute a live B-plane (encounter plane) time series for a collision
    scenario: the miss-distance vector, hard-body-radius circle, and
    covariance confidence ellipse at every animation frame.

    This is the real mathematical object conjunction assessment is built
    on (Alfriend/Akella / CARA encounter-plane formulation, see
    conjunction.py and docs/physics.md), projected from the scenario's
    already-computed 3D trajectories using the same
    compute_encounter_plane() / probability_of_collision_foster() routines
    used by the production conjunction pipeline. The encounter-plane basis
    is built once from the TCA geometry (it changes slowly relative to the
    few-minute encounter timescale) and reused to project every frame, so
    the burn's effect on the miss vector reads as continuous 2D motion
    rather than a jump.

    Parameters
    ----------
    path1, path2 : list of [x, y, z] (n_frames)
        Uncorrected trajectories [km] (object1, object2)
    path1_corrected : list of [x, y, z] (n_frames)
        Object1 trajectory after the avoidance burn (identical to path1
        before the burn)
    maneuver_frame, tca_frame, n_frames : int
    has_correction : bool
    mass1, mass2 : float
        Object masses [kg], used only to size the hard-body-radius circle
    cov_update_frame : int
        Frame at which tracking refinement reduces covariance (ties to the
        scenario's 'covariance_update' event)
    sigma_before_m, sigma_after_m : float
        Cross-track 1-sigma position uncertainty before/after refinement [m]

    Returns
    -------
    dict
        Per-frame arrays (miss_xi_km, miss_zeta_km, cov_semi_major_km,
        cov_semi_minor_km, pc_estimate) plus scenario-constant fields
        (cov_angle_rad, combined_radius_km, cov_update_frame)
    """
    positions1 = np.array(path1, dtype=float)
    positions2 = np.array(path2, dtype=float)

    # Build the encounter-plane basis from TCA geometry. Velocity is
    # estimated via central finite difference on the (kinematic, not
    # time-scaled) frame path -- only the *direction* of relative
    # velocity matters for orienting the plane, and that direction is
    # preserved regardless of the arbitrary per-frame time step.
    idx_lo = max(tca_frame - 1, 0)
    idx_hi = min(tca_frame + 1, n_frames - 1)
    v1_tca = positions1[idx_hi] - positions1[idx_lo]
    v2_tca = positions2[idx_hi] - positions2[idx_lo]

    state1_tca = _StateVector(r=positions1[tca_frame], v=v1_tca)
    state2_tca = _StateVector(r=positions2[tca_frame], v=v2_tca)

    _, projection_matrix = build_bplane_projection(state1_tca, state2_tca)

    # Project the uncorrected trajectory, and the corrected one if present
    miss_2d = project_relative_position_series(positions1, positions2, projection_matrix)
    if has_correction:
        positions1_corrected = np.array(path1_corrected, dtype=float)
        miss_2d_corrected = project_relative_position_series(
            positions1_corrected, positions2, projection_matrix
        )
    else:
        miss_2d_corrected = miss_2d

    # Hard-body-radius circle (constant size -- physical geometry doesn't change)
    r1_m = _estimate_hard_body_radius_m(mass1)
    r2_m = _estimate_hard_body_radius_m(mass2)
    combined_radius_km = (r1_m + r2_m) / 1000.0

    # Elongated "cigar-shaped" covariance ellipse (along-track uncertainty
    # dominates cross-track for real conjunction assessments), oriented at
    # a fixed angle for this encounter. Steps to a smaller ellipse once
    # additional tracking passes refine the orbit (cov_update_frame).
    angle_rad = np.radians(25.0)
    cov_before, ellipse_before = _build_covariance_ellipse(
        sigma_before_m * 3 / 1000.0, sigma_before_m / 1000.0, angle_rad
    )
    cov_after, ellipse_after = _build_covariance_ellipse(
        sigma_after_m * 3 / 1000.0, sigma_after_m / 1000.0, angle_rad
    )

    miss_xi_km, miss_zeta_km = [], []
    cov_semi_major_km, cov_semi_minor_km = [], []
    pc_estimate = []

    for i in range(n_frames):
        use_corrected = has_correction and i >= maneuver_frame
        xi, zeta = (miss_2d_corrected[i] if use_corrected else miss_2d[i])
        miss_xi_km.append(float(xi))
        miss_zeta_km.append(float(zeta))

        if i < cov_update_frame:
            semi_major, semi_minor = ellipse_before[0], ellipse_before[1]
            cov_2d = cov_before
        else:
            semi_major, semi_minor = ellipse_after[0], ellipse_after[1]
            cov_2d = cov_after
        cov_semi_major_km.append(float(semi_major))
        cov_semi_minor_km.append(float(semi_minor))

        pc = probability_of_collision_foster(
            np.array([xi, zeta]), cov_2d, combined_radius_km
        )
        pc_estimate.append(float(pc))

    return {
        'miss_xi_km': miss_xi_km,
        'miss_zeta_km': miss_zeta_km,
        'cov_semi_major_km': cov_semi_major_km,
        'cov_semi_minor_km': cov_semi_minor_km,
        'cov_angle_rad': float(angle_rad),
        'combined_radius_km': float(combined_radius_km),
        'pc_estimate': pc_estimate,
        'cov_update_frame': int(cov_update_frame),
        'n_sigma': 3.0,
    }


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

    # ------------------------------------------------------------------
    # CATASTROPHIC-THRESHOLD ENERGY TIMELINE
    # ------------------------------------------------------------------
    # E_MR = (m_p * v_rel^2) / (2 * m_t)  [J/kg], compared against the NASA
    # breakup model's 40 J/g = 40,000 J/kg catastrophic-fragmentation line
    # (see docs/physics.md and src/damage_minimization.collision_specific_energy).
    #
    # v_rel is treated as a physical property of the encounter that only
    # changes if/when the avoidance burn reduces the closing speed —
    # consistent with strategy_reduce_relative_velocity() in
    # damage_minimization.py, which converts available delta-v directly
    # into a relative-velocity reduction (capped at 50% of v_rel, since a
    # single-sided burn can only cancel so much of the closing vector).
    m_proj = min(mass1, mass2)
    m_targ = max(mass1, mass2)

    v_rel_reduction_kms = 0.0
    if has_correction and maneuver_dv_ms > 0:
        v_rel_reduction_kms = min(maneuver_dv_ms / 1000.0, relative_velocity_kms * 0.5)
    v_rel_final_kms = max(0.05, relative_velocity_kms - v_rel_reduction_kms)

    v_rel_series = []
    for i in range(n_frames):
        if not has_correction or i < maneuver_frame:
            v_rel_series.append(relative_velocity_kms)
        elif i >= tca_frame:
            v_rel_series.append(v_rel_final_kms)
        else:
            # Smoothstep the burn's effect on closing velocity between
            # maneuver ignition and TCA (the delta-v takes effect
            # progressively, not instantaneously).
            span = max(tca_frame - maneuver_frame, 1)
            t = (i - maneuver_frame) / span
            t = t * t * (3 - 2 * t)  # smoothstep easing
            v_rel_series.append(relative_velocity_kms + (v_rel_final_kms - relative_velocity_kms) * t)

    specific_energy_series = [
        float(collision_specific_energy(m_proj, m_targ, v)) for v in v_rel_series
    ]
    specific_energy_initial = specific_energy_series[0]
    specific_energy_final = specific_energy_series[-1]

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

    # Build SSE events timeline (mission-control style telemetry feed)
    n_debris_estimate = int(estimate_debris_count(mass1, mass2, relative_velocity_kms))
    fuel_available_ms = maneuver_dv_ms * 3.2 + 4.0  # plausible remaining budget

    events = []
    events.append({
        'frame': 0,
        'type': 'scenario_start',
        'message': f'Tracking conjunction: {name}',
        'data': {'relative_velocity': relative_velocity_kms, 'altitude': altitude_km}
    })
    events.append({
        'frame': int(n_frames * 0.08),
        'type': 'radar_contact',
        'message': f'Ground radar contact acquired at {altitude_km:.0f} km altitude. Tracking initiated.',
        'data': {'sensor': 'GROUND_RADAR', 'altitude_km': altitude_km}
    })
    events.append({
        'frame': int(n_frames * 0.15),
        'type': 'detection',
        'message': f'Conjunction detected. Pc rising. Current range: {distances[int(n_frames * 0.15)]:.1f} km, predicted miss distance: {min_distance:.1f} km',
        'data': {'pc': 2.3e-4, 'current_range_km': distances[int(n_frames * 0.15)], 'predicted_miss_distance_km': min_distance}
    })
    events.append({
        'frame': int(n_frames * 0.20),
        'type': 'orbit_refinement',
        'message': 'Orbit determination refined using 3 additional tracking passes.',
        'data': {'tracking_passes': 3}
    })
    events.append({
        'frame': int(n_frames * 0.25),
        'type': 'covariance_update',
        'message': 'Position uncertainty reduced to \u00b1120 m (1\u03c3) in encounter plane.',
        'data': {'sigma_m': 120}
    })
    events.append({
        'frame': int(n_frames * 0.3),
        'type': 'risk_assessment',
        'message': f'Risk level: CRITICAL. Relative velocity: {relative_velocity_kms} km/s',
        'data': {'risk_level': 'CRITICAL', 'fragments_if_collision': n_debris_estimate}
    })
    events.append({
        'frame': int(n_frames * 0.34),
        'type': 'ground_alert',
        'message': 'Conjunction Assessment Report (CAR) transmitted to satellite operator.',
        'data': {'report': 'CAR', 'recipient': 'OPERATOR'}
    })

    if has_correction:
        events.append({
            'frame': max(maneuver_frame - 18, int(n_frames * 0.34) + 1),
            'type': 'fuel_check',
            'message': f'Fuel budget check: {fuel_available_ms:.1f} m/s available, '
                        f'{maneuver_dv_ms:.1f} m/s required. GO for maneuver.',
            'data': {'fuel_available_ms': fuel_available_ms, 'fuel_required_ms': maneuver_dv_ms}
        })
        events.append({
            'frame': maneuver_frame - 5,
            'type': 'maneuver_planning',
            'message': f'Computing optimal avoidance maneuver. dv={maneuver_dv_ms:.1f} m/s',
            'data': {'delta_v_ms': maneuver_dv_ms, 'direction': 'cross-track'}
        })
        events.append({
            'frame': maneuver_frame - 2,
            'type': 'attitude_control',
            'message': 'Reorienting spacecraft to burn attitude. Reaction wheels engaged.',
            'data': {'subsystem': 'ADCS'}
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
            'frame': min(maneuver_frame + 22, tca_frame - 6),
            'type': 'post_burn_tracking',
            'message': 'Post-burn tracking confirms new orbit within predicted envelope.',
            'data': {'fuel_remaining_ms': fuel_available_ms - maneuver_dv_ms}
        })
        events.append({
            'frame': max(tca_frame - 8, maneuver_frame + 1),
            'type': 'final_approach',
            'message': f'Final approach: {(tca_frame - (tca_frame - 8)) * 0.05:.1f}s to closest approach.',
            'data': {'seconds_to_tca': (tca_frame - (tca_frame - 8)) * 0.05}
        })
        events.append({
            'frame': tca_frame,
            'type': 'closest_approach',
            'message': f'TCA passed. Miss distance: {min_distance_corrected:.2f} km. SAFE.',
            'data': {'miss_distance_corrected': min_distance_corrected, 'status': 'SAFE'}
        })
        events.append({
            'frame': min(tca_frame + 15, n_frames - 12),
            'type': 'secondary_screening',
            'message': 'Screening for secondary conjunctions... none found within 24h window.',
            'data': {'secondary_conjunctions': 0}
        })
        events.append({
            'frame': n_frames - 10,
            'type': 'scenario_end',
            'message': 'Conjunction resolved. Returning to nominal operations.',
            'data': {'outcome': 'AVOIDANCE_SUCCESS'}
        })
        events.append({
            'frame': n_frames - 4,
            'type': 'archival',
            'message': 'Conjunction case archived. Event log committed to mission database.',
            'data': {'status': 'CLOSED'}
        })
    else:
        events.append({
            'frame': maneuver_frame,
            'type': 'no_maneuver',
            'message': 'NO MANEUVER CAPABILITY. Object is non-maneuverable debris.',
            'data': {'reason': 'non_maneuverable'}
        })
        events.append({
            'frame': maneuver_frame + 10,
            'type': 'operator_response',
            'message': 'Operators confirm: no avoidance options available for this object.',
            'data': {'status': 'NO_ACTION_POSSIBLE'}
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
            'message': f'COLLISION DETECTED. {n_debris_estimate} fragments generated.',
            'data': {
                'fragments': n_debris_estimate,
                'is_catastrophic': True,
                'energy_j_per_kg': float(0.5 * min(mass1, mass2) * (relative_velocity_kms * 1000) ** 2 / max(mass1, mass2))
            }
        })
        events.append({
            'frame': min(tca_frame + 8, n_frames - 14),
            'type': 'debris_field_analysis',
            'message': f'Debris field analysis: {n_debris_estimate} fragments >10cm tracked. '
                        f'Cascade risk elevated.',
            'data': {'fragments_tracked': n_debris_estimate, 'cascade_risk': 'HIGH'}
        })
        events.append({
            'frame': min(tca_frame + 16, n_frames - 8),
            'type': 'secondary_screening',
            'message': 'Screening for secondary conjunctions from new debris field...',
            'data': {'secondary_conjunctions': 'PENDING'}
        })
        events.append({
            'frame': n_frames - 10,
            'type': 'scenario_end',
            'message': 'Debris cloud expanding. Cascade risk elevated.',
            'data': {'outcome': 'COLLISION', 'cascade_risk': 'HIGH'}
        })
        events.append({
            'frame': n_frames - 4,
            'type': 'archival',
            'message': 'Collision case archived. Event log committed to mission database.',
            'data': {'status': 'CLOSED'}
        })

    # Keep the timeline strictly ordered by frame (defensive: several
    # frame offsets above are computed dynamically and could otherwise
    # land out of order for unusual maneuver_time_fraction values)
    events.sort(key=lambda e: e['frame'])

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
        'specific_energy_j_per_kg': specific_energy_series,
        'catastrophic_energy_threshold_j_per_kg': CATASTROPHIC_ENERGY,
        'metadata': {
            'altitude_km': altitude_km,
            'relative_velocity_kms': relative_velocity_kms,
            'mass1_kg': mass1,
            'mass2_kg': mass2,
            'maneuver_dv_ms': maneuver_dv_ms,
            'object1_type': 'COMSAT' if mass1 < 500 else 'EOS',
            'object2_type': 'DEBRIS' if not has_correction else 'COMSAT',
            'v_rel_final_kms': v_rel_final_kms,
            'specific_energy_initial_j_per_kg': specific_energy_initial,
            'specific_energy_final_j_per_kg': specific_energy_final,
            'is_catastrophic_initial': bool(specific_energy_initial >= CATASTROPHIC_ENERGY),
            'is_catastrophic_final': bool(specific_energy_final >= CATASTROPHIC_ENERGY),
        }
    }


def build_risk_evolution(sim, years=10.0, time_steps=60):
    """
    Project long-term risk evolution (collision probability, debris
    accumulation, Kessler index, fuel depletion) so the dashboard can
    render a dynamic equivalent of risk_evolution.png.
    """
    states = project_risk_evolution(
        sim.spacecraft_list, sim.conjunctions, years=years, time_steps=time_steps
    )
    n = max(len(states) - 1, 1)
    timeline = []
    for i, s in enumerate(states):
        timeline.append({
            'year': float(i / n * years),
            'total_collision_probability': float(s.total_collision_probability),
            'total_expected_debris': float(s.total_expected_debris),
            'kessler_risk_index': float(s.kessler_risk_index),
            'fuel_consumed_total_ms': float(s.fuel_consumed_total_ms),
        })
    return timeline


def build_debris_analysis(sim, n_monte_carlo=300):
    """
    Run the full NASA-breakup-model collision outcome prediction for the
    highest-risk conjunction, so the dashboard can render a dynamic
    equivalent of debris_analysis.png.
    """
    if not sim.conjunctions:
        return None

    sc_dict = {sc.id: sc for sc in sim.spacecraft_list}
    conj = max(sim.conjunctions, key=lambda c: c.probability_of_collision)
    sc1 = sc_dict.get(conj.obj1_id)
    sc2 = sc_dict.get(conj.obj2_id)
    if not sc1 or not sc2:
        return None

    try:
        outcome = predict_collision_outcome(sc1, sc2, conj, n_monte_carlo=n_monte_carlo)
    except Exception as e:
        print(f"  Warning: debris analysis failed: {e}")
        return None

    sizes = [float(f.size) for f in outcome.fragments]
    perigees = [float(f.perigee_km) for f in outcome.fragments if 0 < f.perigee_km < 2000]
    apogees = [float(f.apogee_km) for f in outcome.fragments if 0 < f.apogee_km < 2000]
    lifetimes = [float(f.orbit_lifetime_years) for f in outcome.fragments
                 if 0 < f.orbit_lifetime_years < 1000]

    return {
        'conjunction_id': f"{conj.obj1_id}_{conj.obj2_id}",
        'object1': conj.obj1_id,
        'object2': conj.obj2_id,
        'relative_velocity_kms': float(conj.relative_velocity),
        'is_catastrophic': bool(outcome.is_catastrophic),
        'specific_energy_j_per_kg': float(outcome.specific_energy_j_per_kg),
        'total_fragments_gt_10cm': int(outcome.total_fragments_gt_10cm),
        'total_fragments_gt_1cm': int(outcome.total_fragments_gt_1cm),
        'debris_mass_kg': float(outcome.debris_mass_kg),
        'mean_debris_lifetime_years': float(outcome.mean_debris_lifetime_years),
        'max_debris_altitude_km': float(outcome.max_debris_altitude_km),
        'min_debris_altitude_km': float(outcome.min_debris_altitude_km),
        'risk_to_other_spacecraft': float(outcome.risk_to_other_spacecraft),
        'fragment_sizes': sizes,
        'perigees_km': perigees,
        'apogees_km': apogees,
        'lifetimes_years': lifetimes,
    }


def run_simulation(seed=42, n_spacecraft=50):
    """Run the simulation and cache all data for the API."""

    print(f"Running satellite collision simulation (seed={seed})...")
    sim = CollisionPreventionSimulation(n_spacecraft=n_spacecraft, seed=seed)
    sim.run_full_simulation()
    _CURRENT_SIM['sim'] = sim

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

    # Long-term risk evolution projection (dynamic equivalent of risk_evolution.png)
    risk_evolution = build_risk_evolution(sim)

    # Full debris breakup analysis for the riskiest conjunction
    # (dynamic equivalent of debris_analysis.png)
    debris_analysis = build_debris_analysis(sim)

    # Regenerate the 3D orbits plot (orbits_3d.png) from this run's data so
    # the "View Orbits 3D" button always reflects the latest simulation.
    # plot_orbits_3d() saves relative to the process cwd, so temporarily
    # switch to the repo root (where the dashboard expects to find the file).
    try:
        prev_cwd = os.getcwd()
        os.chdir(ROOT_DIR)
        try:
            plot_orbits_3d(
                sim.spacecraft_list, sim.conjunctions, sim.planned_maneuvers,
                title=f"Orbital Configuration (seed={seed})"
            )
        finally:
            os.chdir(prev_cwd)
    except Exception as e:
        print(f"  Warning: could not regenerate orbits_3d.png: {e}")

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
        'risk_evolution': risk_evolution,
        'debris_analysis': debris_analysis,
        'scenarios': scenarios,
        'run_id': int(time.time() * 1000),
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
    """Risk evolution timeline (24h, short-term)."""
    return jsonify(SIM_DATA.get('risk_timeline', []))


@app.route('/api/risk-evolution')
def get_risk_evolution():
    """Long-term (multi-year) risk evolution projection: collision probability,
    debris accumulation, Kessler index, and fuel depletion over time.
    Dynamic equivalent of risk_evolution.png."""
    return jsonify(SIM_DATA.get('risk_evolution', []))


@app.route('/api/debris-analysis')
def get_debris_analysis():
    """Full NASA-breakup-model debris analysis for the highest-risk
    conjunction: fragment size/altitude/lifetime distributions and
    collision outcome summary. Dynamic equivalent of debris_analysis.png."""
    data = SIM_DATA.get('debris_analysis')
    if data is None:
        return jsonify({'error': 'No conjunction data available'}), 404
    return jsonify(data)


@app.route('/api/all')
def get_all():
    """All simulation data in a single request (for initial load)."""
    return jsonify(SIM_DATA)


@app.route('/orbits_3d.png')
def get_orbits_3d_image():
    """Serve the latest generated 3D orbits plot (matplotlib PNG)."""
    path = os.path.join(ROOT_DIR, 'orbits_3d.png')
    if not os.path.exists(path):
        return jsonify({'error': 'orbits_3d.png not generated yet'}), 404
    response = send_from_directory(ROOT_DIR, 'orbits_3d.png')
    response.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
    return response


@app.route('/api/run', methods=['POST'])
def run_new_simulation():
    """
    Re-run the full simulation pipeline with a fresh random seed and
    re-cache all derived data (spacecraft, conjunctions, risk evolution,
    debris analysis, etc). Lets the dashboard "Run Simulation" button
    regenerate all charts with new data instead of just replaying a
    canned scenario animation.
    """
    if not SIM_LOCK.acquire(blocking=False):
        return jsonify({'error': 'A simulation run is already in progress'}), 409
    try:
        seed = request.get_json(silent=True) or {}
        new_seed = int(seed.get('seed', int(time.time())))
        run_simulation(seed=new_seed)
        return jsonify({'status': 'ok', 'run_id': SIM_DATA.get('run_id')})
    except Exception as e:
        return jsonify({'error': str(e)}), 500
    finally:
        SIM_LOCK.release()


@app.route('/api/plan', methods=['POST'])
def plan_intervention():
    """
    Natural-language intervention planning, backed by NVIDIA cuOpt.

    Body: {"query": "what's the minimum-fuel plan to resolve today's
    critical conjunctions?"}

    Pipeline: the query is mapped to a conjunction subset (by risk-level
    keyword), NVIDIA cuOpt solves the constrained maneuver-assignment MILP
    for that subset (InterventionOptimizer.network_flow_optimize, see
    risk_optimizer.py / cuopt_client.py), and the LLM narrates the
    already-solved plan — it never invents delta-v numbers itself.

    NOTE: this endpoint calls the NVIDIA NIM chat API (ai_analysis.py) and
    requires NVIDIA_API_KEY to be set; the underlying cuOpt solve itself
    does not require an API key (it runs locally unless CUOPT_SERVER_IP
    is configured).
    """
    sim = _CURRENT_SIM.get('sim')
    if sim is None:
        return jsonify({'error': 'No simulation has been run yet. Call /api/run first.'}), 409

    body = request.get_json(silent=True) or {}
    query = body.get('query', '').strip()
    if not query:
        return jsonify({'error': 'Request body must include a non-empty "query" string.'}), 400

    try:
        result = plan_intervention_from_query(sim.spacecraft_list, sim.conjunctions, query)
        return jsonify(result)
    except Exception as e:
        return jsonify({'error': str(e)}), 500


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
        specific_energy_series = scenario.get('specific_energy_j_per_kg', [])

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
                'specific_energy_j_per_kg': (
                    specific_energy_series[frame] if frame < len(specific_energy_series) else None
                ),
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
    # threaded=True is required: the /api/run endpoint blocks for 30-90s+
    # while re-running the full simulation pipeline. Without threading,
    # Flask's dev server can only handle one request at a time, so a
    # long-running /api/run call would freeze /api/all and every other
    # route (including the initial page load) until it finished.
    app.run(host='0.0.0.0', port=8050, debug=False, threaded=True)
