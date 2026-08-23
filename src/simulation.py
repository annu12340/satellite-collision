"""
Simulation & Visualization Entry Point
=======================================

Ties together all modules into a runnable demonstration:
1. Generates a synthetic LEO constellation with realistic parameters
2. Runs conjunction screening
3. Plans collision avoidance maneuvers
4. Handles unavoidable collisions with damage minimization
5. Runs the multi-object optimizer
6. Visualizes results (orbits, conjunctions, maneuvers, debris, risk evolution)
"""

import matplotlib
matplotlib.use('Agg')  # Headless backend - safe to call from Flask/background threads

import numpy as np
import matplotlib.pyplot as plt
from mpl_toolkits.mplot3d import Axes3D  # noqa: F401 — registers 3D projection
from typing import List, Optional
import time
import warnings

warnings.filterwarnings('ignore', category=RuntimeWarning)

from .utils import (
    MU_EARTH, R_EARTH, CATASTROPHIC_ENERGY,
    StateVector, Spacecraft, Conjunction, Maneuver, OrbitalElements,
    coe_to_state, state_to_coe, orbital_period,
    get_logger
)

logger = get_logger(__name__)
from .orbital_mechanics import (
    propagate_state, generate_ephemeris, propagate_kepler
)
from .conjunction import (
    run_conjunction_screening, assess_conjunction,
    estimate_debris_count, debris_lifetime, compute_risk_score
)
from .avoidance import (
    ManeuverDecision, design_avoidance_maneuver, apply_maneuver,
    evaluate_maneuver, plan_avoidance_campaign
)
from .damage_minimization import (
    predict_collision_outcome, evaluate_all_strategies,
    execute_mitigation_plan, is_catastrophic
)
from .risk_optimizer import (
    RiskGraph, OrbitalEnvironment, InterventionOptimizer,
    allocate_fuel_budget, project_risk_evolution
)


# ============================================================================
# CONSTELLATION GENERATION
# ============================================================================


def generate_leo_constellation(n_spacecraft: int = 50,
                                alt_range: tuple = (400, 900),
                                inc_range: tuple = (50, 98),
                                seed: int = 42) -> List[Spacecraft]:
    """
    Generate a synthetic LEO constellation for simulation.

    Creates spacecraft with realistic orbital parameters, masses, and
    covariance uncertainties mimicking a mix of:
    - Large communication satellites (Starlink-like)
    - Earth observation spacecraft
    - Small CubeSats
    - Defunct satellites (non-maneuverable debris)

    Parameters
    ----------
    n_spacecraft : int
        Number of spacecraft to generate
    alt_range : tuple
        (min_altitude_km, max_altitude_km)
    inc_range : tuple
        (min_inclination_deg, max_inclination_deg)
    seed : int
        Random seed for reproducibility

    Returns
    -------
    list of Spacecraft
        Generated constellation
    """
    rng = np.random.default_rng(seed)
    spacecraft_list = []

    # Spacecraft types with realistic parameters
    types = [
        {  # Large comsat (Starlink-like)
            'mass_range': (250, 350),
            'area_range': (15, 30),
            'dv_budget': (30, 60),
            'probability': 0.4,
            'maneuverable': True,
            'prefix': 'COMSAT'
        },
        {  # Earth observation
            'mass_range': (500, 2000),
            'area_range': (5, 20),
            'dv_budget': (20, 40),
            'probability': 0.2,
            'maneuverable': True,
            'prefix': 'EOS'
        },
        {  # CubeSat
            'mass_range': (1, 10),
            'area_range': (0.01, 0.1),
            'dv_budget': (0, 5),
            'probability': 0.2,
            'maneuverable': False,  # Most CubeSats can't maneuver
            'prefix': 'CUBE'
        },
        {  # Defunct/debris
            'mass_range': (100, 5000),
            'area_range': (1, 50),
            'dv_budget': (0, 0),
            'probability': 0.2,
            'maneuverable': False,
            'prefix': 'DEBRIS'
        }
    ]

    type_probs = [t['probability'] for t in types]

    for i in range(n_spacecraft):
        # Select type
        sc_type = rng.choice(types, p=type_probs)

        # Generate orbital elements
        altitude = rng.uniform(*alt_range)
        a = R_EARTH + altitude
        e = rng.uniform(0.0001, 0.01)  # Near-circular
        inc = np.radians(rng.uniform(*inc_range))
        raan = rng.uniform(0, 2 * np.pi)
        omega = rng.uniform(0, 2 * np.pi)
        nu = rng.uniform(0, 2 * np.pi)

        elements = OrbitalElements(a=a, e=e, i=inc, raan=raan, omega=omega, nu=nu)
        state = coe_to_state(elements)

        # Physical properties
        mass = rng.uniform(*sc_type['mass_range'])
        area = rng.uniform(*sc_type['area_range'])
        dv_budget = rng.uniform(*sc_type['dv_budget'])

        # Position covariance (typical tracking uncertainty)
        # LEO: ~50-500m position, ~1-10 mm/s velocity (1-sigma)
        pos_sigma = rng.uniform(0.05, 0.5)  # km
        vel_sigma = rng.uniform(1e-6, 1e-5)  # km/s
        covariance = np.diag([
            pos_sigma**2, pos_sigma**2, pos_sigma**2,
            vel_sigma**2, vel_sigma**2, vel_sigma**2
        ])

        # Add cross-correlations (position-velocity coupling)
        for j in range(3):
            covariance[j, j + 3] = pos_sigma * vel_sigma * 0.3
            covariance[j + 3, j] = pos_sigma * vel_sigma * 0.3

        sc = Spacecraft(
            id=f"{sc_type['prefix']}_{i:04d}",
            state=state,
            covariance=covariance,
            mass=mass,
            area=area,
            delta_v_budget=dv_budget,
            maneuverable=sc_type['maneuverable'],
            name=f"{sc_type['prefix']}-{i:04d} ({altitude:.0f}km)"
        )

        spacecraft_list.append(sc)

    return spacecraft_list


def inject_collision_scenario(spacecraft_list: List[Spacecraft],
                               seed: int = 123) -> List[Spacecraft]:
    """
    Modify some orbits to create guaranteed close approaches for demonstration.

    Creates crossing orbits (different inclinations, same altitude) which
    produce real conjunctions within a single screening window.
    """
    rng = np.random.default_rng(seed)

    if len(spacecraft_list) < 10:
        return spacecraft_list

    # Strategy: put two objects on the SAME orbit but with a crossing geometry.
    # Objects at same altitude, different inclinations, timed so they cross.
    scenarios = [
        {'inc_offset_deg': 1.0, 'nu_offset_deg': 2.0, 'label': 'HIGH_RISK'},
        {'inc_offset_deg': 2.0, 'nu_offset_deg': 5.0, 'label': 'MEDIUM_RISK'},
        {'inc_offset_deg': 3.0, 'nu_offset_deg': 8.0, 'label': 'LOW_RISK'},
    ]

    for idx, scenario in enumerate(scenarios):
        i = idx * 2
        j = idx * 2 + 1

        if i >= len(spacecraft_list) or j >= len(spacecraft_list):
            break

        # Object i: keep its orbit
        coe_i = state_to_coe(spacecraft_list[i].state)

        # Object j: same altitude and RAAN, but cross inclination → orbits intersect
        coe_j = OrbitalElements(
            a=coe_i.a,  # Same altitude
            e=coe_i.e,
            i=coe_i.i + np.radians(scenario['inc_offset_deg']),  # Different plane
            raan=coe_i.raan,  # Same node line → guaranteed intersection
            omega=coe_i.omega,
            nu=coe_i.nu + np.radians(scenario['nu_offset_deg'])  # Slightly ahead
        )

        spacecraft_list[j].state = coe_to_state(coe_j)
        spacecraft_list[j].name = f"{scenario['label']}_{j}"
        # Make one non-maneuverable for interesting decisions
        if idx == 0:
            spacecraft_list[j].maneuverable = False
            spacecraft_list[j].delta_v_budget = 0.0

    return spacecraft_list


# ============================================================================
# SIMULATION ENGINE
# ============================================================================


class CollisionPreventionSimulation:
    """
    Main simulation engine that demonstrates the full collision prevention pipeline.
    """

    def __init__(self, n_spacecraft: int = 50, seed: int = 42,
                 max_conjunctions_to_process: int = 25):
        """
        Initialize simulation with synthetic constellation.

        Parameters
        ----------
        n_spacecraft : int
            Number of spacecraft to simulate
        seed : int
            Random seed
        max_conjunctions_to_process : int
            Upper bound on how many screened conjunctions (already sorted by
            risk, descending) are carried into Phase 2/3/4. This bounds the
            worst-case cost of downstream maneuver design regardless of how
            many pairs get flagged during screening.
        """
        logger.info("=" * 70)
        logger.info("   AI SATELLITE COLLISION PREVENTION SYSTEM")
        logger.info("=" * 70)
        logger.info("Initializing simulation with %d spacecraft...", n_spacecraft)

        self.spacecraft_list = generate_leo_constellation(n_spacecraft, seed=seed)
        self.spacecraft_list = inject_collision_scenario(self.spacecraft_list, seed=seed + 1)

        self.max_conjunctions_to_process = max_conjunctions_to_process

        self.conjunctions: List[Conjunction] = []
        self.planned_maneuvers: List[Maneuver] = []
        self.risk_graph: Optional[RiskGraph] = None
        self.environment: Optional[OrbitalEnvironment] = None

        # Statistics
        self.stats = {
            'spacecraft_total': n_spacecraft,
            'maneuverable': sum(1 for sc in self.spacecraft_list if sc.maneuverable),
            'non_maneuverable': sum(1 for sc in self.spacecraft_list if not sc.maneuverable),
            'total_mass_kg': sum(sc.mass for sc in self.spacecraft_list),
        }

        self._print_constellation_summary()

    def _print_constellation_summary(self):
        """Print summary of generated constellation."""
        logger.info("--- Constellation Summary ---")
        logger.info("  Total objects: %d", self.stats['spacecraft_total'])
        logger.info("  Maneuverable: %d", self.stats['maneuverable'])
        logger.info("  Non-maneuverable (debris/CubeSats): %d", self.stats['non_maneuverable'])
        logger.info("  Total mass: %.0f kg", self.stats['total_mass_kg'])

        # Altitude distribution
        altitudes = []
        for sc in self.spacecraft_list:
            coe = state_to_coe(sc.state)
            altitudes.append(coe.a - R_EARTH)

        logger.info("  Altitude range: %.0f - %.0f km", min(altitudes), max(altitudes))
        logger.info("  Mean altitude: %.0f km", np.mean(altitudes))

    def run_screening(self, time_window_hours: float = 24.0,
                       distance_threshold_km: float = 25.0):
        """
        Phase 1: Conjunction screening.

        Screens all pairs for potential close approaches.
        """
        logger.info("=" * 70)
        logger.info("  PHASE 1: CONJUNCTION SCREENING")
        logger.info("=" * 70)
        logger.info("  Screening window: %.0f hours", time_window_hours)
        logger.info("  Distance threshold: %.0f km", distance_threshold_km)
        n_pairs = len(self.spacecraft_list) * (len(self.spacecraft_list) - 1) // 2
        logger.info("  Pairs to check: %d", n_pairs)

        t_start = time.time()

        self.conjunctions = run_conjunction_screening(
            self.spacecraft_list,
            time_window=time_window_hours * 3600,
            pc_threshold=1e-7,  # Standard negligible-risk cutoff (Level 0: Pc < 1e-7 is essentially zero risk, ignore)
        )

        elapsed = time.time() - t_start
        logger.info("  Screening completed in %.2fs", elapsed)
        logger.info("  Conjunctions found: %d", len(self.conjunctions))

        # Conjunctions are already sorted by risk (descending) by
        # run_conjunction_screening(). Cap the working list so Phase 2/3/4
        # (maneuver design, damage assessment, optimization) have a bounded
        # worst-case cost regardless of how many pairs get flagged.
        if len(self.conjunctions) > self.max_conjunctions_to_process:
            n_dropped = len(self.conjunctions) - self.max_conjunctions_to_process
            logger.info("  Truncating to top %d conjunctions by risk (dropping %d lower-risk events)",
                        self.max_conjunctions_to_process, n_dropped)
            self.conjunctions = self.conjunctions[:self.max_conjunctions_to_process]

        if self.conjunctions:
            pcs = [c.probability_of_collision for c in self.conjunctions]
            logger.info("    Highest Pc: %.2e", max(pcs))
            logger.info("    Mean Pc: %.2e", np.mean(pcs))

            # Categorize by risk level
            high = sum(1 for p in pcs if p >= 1e-4)
            medium = sum(1 for p in pcs if 1e-5 <= p < 1e-4)
            low = sum(1 for p in pcs if p < 1e-5)
            logger.info("    High risk (Pc >= 1e-4): %d", high)
            logger.info("    Medium risk (1e-5 <= Pc < 1e-4): %d", medium)
            logger.info("    Low risk (Pc < 1e-5): %d", low)

            # Print top conjunctions
            logger.info("  Top 5 conjunctions:")
            for i, conj in enumerate(self.conjunctions[:5]):
                logger.info("    %d. %s <-> %s | Pc=%.2e, miss=%.3f km, "
                            "v_rel=%.2f km/s, TCA=%.1fh",
                            i + 1, conj.obj1_id, conj.obj2_id,
                            conj.probability_of_collision,
                            conj.miss_distance, conj.relative_velocity,
                            conj.tca / 3600)

    def plan_avoidance(self):
        """
        Phase 2: Collision avoidance planning.

        Plans maneuvers for all actionable conjunctions.
        """
        logger.info("=" * 70)
        logger.info("  PHASE 2: COLLISION AVOIDANCE PLANNING")
        logger.info("=" * 70)

        if not self.conjunctions:
            logger.info("  No conjunctions to address.")
            return

        self.planned_maneuvers = plan_avoidance_campaign(
            self.spacecraft_list, self.conjunctions
        )

        logger.info("  Maneuvers planned: %d", len(self.planned_maneuvers))

        if self.planned_maneuvers:
            total_dv = sum(m.fuel_cost for m in self.planned_maneuvers)
            logger.info("  Total dv cost: %.2f m/s", total_dv)
            logger.info("  Average dv per maneuver: %.2f m/s",
                        total_dv / len(self.planned_maneuvers))

            for i, man in enumerate(self.planned_maneuvers[:10]):
                dv_rtn = man.delta_v * 1000  # km/s -> m/s
                logger.info("    %d. SC=%s, T+%.1fh, dv=[%.2f, %.2f, %.2f] m/s (|dv|=%.2f)",
                            i + 1, man.spacecraft_id, man.time / 3600,
                            dv_rtn[0], dv_rtn[1], dv_rtn[2], man.fuel_cost)

    def assess_unavoidable(self):
        """
        Phase 3: Damage minimization for unavoidable collisions.

        For conjunctions where avoidance is impossible (no fuel, no time,
        non-maneuverable objects).
        """
        logger.info("=" * 70)
        logger.info("  PHASE 3: UNAVOIDABLE COLLISION ASSESSMENT")
        logger.info("=" * 70)

        # Find conjunctions that couldn't be resolved
        resolved_ids = set()
        for man in self.planned_maneuvers:
            if man.target_conjunction_id:
                resolved_ids.add(man.target_conjunction_id)

        sc_dict = {sc.id: sc for sc in self.spacecraft_list}
        unavoidable = []

        for conj in self.conjunctions:
            conj_id = f"{conj.obj1_id}_{conj.obj2_id}_{conj.tca:.0f}"
            if conj_id not in resolved_ids:
                sc1 = sc_dict.get(conj.obj1_id)
                sc2 = sc_dict.get(conj.obj2_id)
                if sc1 and sc2 and conj.probability_of_collision > 1e-5:
                    unavoidable.append((conj, sc1, sc2))

        logger.info("  Unavoidable high-risk conjunctions: %d", len(unavoidable))

        if not unavoidable:
            logger.info("  All significant risks have been addressed!")
            return

        for i, (conj, sc1, sc2) in enumerate(unavoidable[:3]):
            logger.info("  --- Collision Scenario %d ---", i + 1)
            logger.info("  Objects: %s (%.0fkg) <-> %s (%.0fkg)",
                        sc1.name, sc1.mass, sc2.name, sc2.mass)
            logger.info("  Relative velocity: %.2f km/s", conj.relative_velocity)

            # Predict outcome
            try:
                outcome = predict_collision_outcome(sc1, sc2, conj)
            except (RuntimeError, np.linalg.LinAlgError):
                # Use analytical prediction when propagation fails
                from .damage_minimization import fragment_count, collision_specific_energy
                m_proj = min(sc1.mass, sc2.mass)
                m_targ = max(sc1.mass, sc2.mass)
                E_spec = collision_specific_energy(m_proj, m_targ, conj.relative_velocity)
                N_10 = fragment_count(sc1.mass, sc2.mass, conj.relative_velocity, 0.1)
                N_1 = fragment_count(sc1.mass, sc2.mass, conj.relative_velocity, 0.01)
                catastrophic = E_spec >= CATASTROPHIC_ENERGY

                logger.info("  Type: %s", 'CATASTROPHIC' if catastrophic else 'Non-catastrophic')
                logger.info("  Specific energy: %.0f J/kg (threshold: %.0f J/kg)",
                            E_spec, CATASTROPHIC_ENERGY)
                logger.info("  Fragments >10cm: %d, >1cm: %d", N_10, N_1)

                strategies = evaluate_all_strategies(sc1, sc2, conj, time_available=1800)
                for j, strat in enumerate(strategies):
                    score = strat.effectiveness_score * strat.feasibility_score
                    logger.info("    %d. [%.2f] %s | dv=%.1f m/s",
                                j + 1, score, strat.name, strat.required_delta_v_ms)
                continue

            logger.info("  Type: %s", 'CATASTROPHIC' if outcome.is_catastrophic else 'Non-catastrophic')
            logger.info("  Specific energy: %.0f J/kg (threshold: %.0f J/kg)",
                        outcome.specific_energy_j_per_kg, CATASTROPHIC_ENERGY)
            logger.info("  Fragments >10cm: %d, >1cm: %d",
                        outcome.total_fragments_gt_10cm, outcome.total_fragments_gt_1cm)
            logger.info("  Mean debris lifetime: %.1f years", outcome.mean_debris_lifetime_years)

            # Evaluate mitigation strategies
            strategies = evaluate_all_strategies(sc1, sc2, conj, time_available=1800)
            for j, strat in enumerate(strategies):
                score = strat.effectiveness_score * strat.feasibility_score
                logger.info("    %d. [%.2f] %s | dv=%.1f m/s, eff=%.1f%%, feas=%.1f%%",
                            j + 1, score, strat.name, strat.required_delta_v_ms,
                            strat.effectiveness_score * 100,
                            strat.feasibility_score * 100)

    def run_optimizer(self, method: str = 'adaptive'):
        """
        Phase 4: Multi-object risk optimization.

        Runs the global optimizer to find the best intervention sequence.
        """
        logger.info("=" * 70)
        logger.info("  PHASE 4: MULTI-OBJECT RISK OPTIMIZATION")
        logger.info("=" * 70)

        if not self.conjunctions:
            logger.info("  No conjunctions to optimize.")
            return

        logger.info("  Method: %s", method)
        logger.info("  Optimizing across %d conjunctions...", len(self.conjunctions))

        t_start = time.time()

        optimizer = InterventionOptimizer(
            self.spacecraft_list, self.conjunctions
        )

        # Get initial risk state
        risk_before = optimizer.compute_risk_state()
        logger.info("  Initial risk state:")
        logger.info("    Total Pc: %.2e", risk_before.total_collision_probability)
        logger.info("    Expected debris: %.0f fragments", risk_before.total_expected_debris)
        logger.info("    Kessler index: %.3f", risk_before.kessler_risk_index)

        # Run optimizer
        plan = optimizer.optimize(method=method)

        elapsed = time.time() - t_start
        logger.info("  Optimization completed in %.2fs", elapsed)
        logger.info("  Maneuvers in optimal plan: %d", len(plan.maneuvers))
        logger.info("  Total fuel cost: %.1f m/s", plan.total_fuel_cost_ms)
        logger.info("  Conjunctions resolved: %d", len(plan.conjunctions_resolved))

        # Risk graph analysis
        self.risk_graph = optimizer.risk_graph
        clusters = self.risk_graph.get_risk_clusters()
        logger.info("  Risk graph analysis:")
        logger.info("    Risk clusters: %d", len(clusters))
        if clusters:
            logger.info("    Largest cluster: %d spacecraft", len(clusters[0]))
        logger.info("    Total graph risk: %.2e", self.risk_graph.total_risk())

        # Most threatened
        threatened = self.risk_graph.most_threatened_spacecraft(3)
        if threatened:
            logger.info("    Most threatened: %s", ', '.join(threatened))

        # Environment stability
        self.environment = optimizer.environment
        unstable = [s for s in self.environment.shells if s.is_unstable]
        logger.info("  Orbital environment:")
        logger.info("    Shells analyzed: %d", len(self.environment.shells))
        logger.info("    Unstable shells: %d", len(unstable))
        if unstable:
            for s in unstable[:3]:
                logger.info("      %.0f-%.0f km: gen=%.2f/yr, removal=%.2f/yr",
                            s.alt_min_km, s.alt_max_km,
                            s.debris_generation_rate, s.debris_removal_rate)

    def _create_demo_conjunctions(self):
        """
        Create synthetic conjunctions for demonstration when screening
        doesn't find any (normal for small constellations over short windows).

        In reality, operators screen thousands of objects over 7-day windows.
        With 30 objects over 24h, real conjunctions are statistically rare.
        """
        logger.info("  Real LEO conjunctions are rare events. For a constellation")
        logger.info("  of 30 objects over 24h, finding none is realistic.")
        logger.info("  Creating synthetic demonstration conjunctions...")

        sc_dict = {sc.id: sc for sc in self.spacecraft_list}

        # Create 5 synthetic conjunctions at varying risk levels
        demo_configs = [
            {'pc': 2.3e-4, 'miss': 0.15, 'v_rel': 14.2, 'tca_h': 4.5},
            {'pc': 8.1e-5, 'miss': 0.45, 'v_rel': 10.8, 'tca_h': 8.2},
            {'pc': 3.7e-5, 'miss': 1.2, 'v_rel': 7.5, 'tca_h': 12.7},
            {'pc': 5.0e-6, 'miss': 2.8, 'v_rel': 12.1, 'tca_h': 18.3},
            {'pc': 1.2e-6, 'miss': 4.1, 'v_rel': 9.3, 'tca_h': 22.0},
        ]

        n_pairs = min(len(demo_configs), len(self.spacecraft_list) // 2)

        for idx in range(n_pairs):
            cfg = demo_configs[idx]
            sc1 = self.spacecraft_list[idx * 2]
            sc2 = self.spacecraft_list[idx * 2 + 1]

            altitude = state_to_coe(sc1.state).a - R_EARTH

            conj = Conjunction(
                obj1_id=sc1.id,
                obj2_id=sc2.id,
                tca=cfg['tca_h'] * 3600,
                miss_distance=cfg['miss'],
                relative_velocity=cfg['v_rel'],
                probability_of_collision=cfg['pc'],
                combined_covariance_2d=np.array([[0.04, 0.001], [0.001, 0.02]]),
            )

            # Compute risk score
            conj.risk_score = compute_risk_score(
                conj, sc1.mass, sc2.mass, altitude
            )

            self.conjunctions.append(conj)

        # Sort by risk
        self.conjunctions.sort(key=lambda c: c.risk_score, reverse=True)

    def run_full_simulation(self):
        """Run the complete simulation pipeline."""
        self.run_screening()

        # If no real conjunctions found, create demo scenarios
        if not self.conjunctions:
            self._create_demo_conjunctions()

        self.plan_avoidance()
        self.assess_unavoidable()
        self.run_optimizer()
        self._print_final_summary()

    def _print_final_summary(self):
        """Print final simulation summary."""
        logger.info("=" * 70)
        logger.info("  SIMULATION COMPLETE")
        logger.info("=" * 70)
        logger.info("  Constellation: %d objects", self.stats['spacecraft_total'])
        logger.info("  Conjunctions detected: %d", len(self.conjunctions))
        logger.info("  Maneuvers planned: %d", len(self.planned_maneuvers))
        if self.planned_maneuvers:
            total_dv = sum(m.fuel_cost for m in self.planned_maneuvers)
            logger.info("  Total dv expended: %.2f m/s", total_dv)
        logger.info("  System status: OPERATIONAL")


# ============================================================================
# VISUALIZATION
# ============================================================================


def plot_orbits_3d(spacecraft_list: List[Spacecraft],
                   conjunctions: Optional[List[Conjunction]] = None,
                   maneuvers: Optional[List[Maneuver]] = None,
                   title: str = "Orbital Configuration"):
    """
    3D visualization of spacecraft orbits with conjunctions and maneuvers.

    Parameters
    ----------
    spacecraft_list : list of Spacecraft
        Spacecraft to plot
    conjunctions : list of Conjunction, optional
        Conjunctions to highlight
    maneuvers : list of Maneuver, optional
        Planned maneuvers to show
    title : str
        Plot title
    """
    # Dark theme to match the dashboard's UI (bg-primary #0a0e17)
    bg_color = '#0a0e17'
    panel_color = '#0f1520'
    grid_color = '#1e2a42'
    text_color = '#8b9cc0'

    fig = plt.figure(figsize=(12, 10), facecolor=bg_color)
    ax = fig.add_subplot(111, projection='3d')
    ax.set_facecolor(bg_color)

    for pane in (ax.xaxis.pane, ax.yaxis.pane, ax.zaxis.pane):
        pane.set_facecolor(panel_color)
        pane.set_edgecolor(grid_color)
        pane.set_alpha(1.0)
    for axis in (ax.xaxis, ax.yaxis, ax.zaxis):
        axis.line.set_color(grid_color)
        axis._axinfo['grid']['color'] = grid_color
        axis.label.set_color(text_color)
    ax.tick_params(colors=text_color)

    # Draw Earth (accent-blue tinted sphere, matching the dashboard's 3D globe)
    u = np.linspace(0, 2 * np.pi, 30)
    v_angles = np.linspace(0, np.pi, 20)
    x_earth = R_EARTH * np.outer(np.cos(u), np.sin(v_angles))
    y_earth = R_EARTH * np.outer(np.sin(u), np.sin(v_angles))
    z_earth = R_EARTH * np.outer(np.ones_like(u), np.cos(v_angles))
    ax.plot_surface(x_earth, y_earth, z_earth, alpha=0.35, color='#00d4ff', linewidth=0)

    # Plot orbit arcs for each spacecraft (dashboard accent palette)
    colors = {'COMSAT': '#00d4ff', 'EOS': '#7b2ff7', 'CUBE': '#06ffd0', 'DEBRIS': '#ff6b6b'}

    for sc in spacecraft_list[:30]:  # Limit for clarity
        # Generate one orbit arc
        coe = state_to_coe(sc.state)
        period = orbital_period(coe.a)
        times = np.linspace(0, period, 100)

        try:
            eph = generate_ephemeris(sc.state, times, include_drag=False)
            prefix = sc.id.split('_')[0]
            color = colors.get(prefix, '#e8edf5')
            ax.plot(eph[:, 0], eph[:, 1], eph[:, 2],
                   alpha=0.5, linewidth=0.6, color=color)

            # Mark current position
            ax.scatter(*sc.state.r, s=10, color=color, alpha=0.9)
        except RuntimeError:
            pass

    # Highlight conjunctions
    if conjunctions:
        sc_dict = {sc.id: sc for sc in spacecraft_list}
        for conj in conjunctions[:10]:
            sc1 = sc_dict.get(conj.obj1_id)
            sc2 = sc_dict.get(conj.obj2_id)
            if sc1 and sc2:
                # Draw line between conjunction objects
                points = np.array([sc1.state.r, sc2.state.r])
                ax.plot(points[:, 0], points[:, 1], points[:, 2],
                       color='#ff2d55', linestyle='-', linewidth=2, alpha=0.8)
                # Mark with X
                mid = (sc1.state.r + sc2.state.r) / 2
                ax.scatter(*mid, marker='x', s=100, color='#ff2d55', linewidth=2)

    ax.set_xlabel('X [km]', color=text_color)
    ax.set_ylabel('Y [km]', color=text_color)
    ax.set_zlabel('Z [km]', color=text_color)
    ax.set_title(title, color='#e8edf5')

    # Legend
    from matplotlib.lines import Line2D
    legend_elements = [
        Line2D([0], [0], color='#00d4ff', label='Communication Sats'),
        Line2D([0], [0], color='#7b2ff7', label='Earth Observation'),
        Line2D([0], [0], color='#06ffd0', label='CubeSats'),
        Line2D([0], [0], color='#ff6b6b', label='Debris/Defunct'),
        Line2D([0], [0], color='#ff2d55', marker='x', linestyle='',
               markersize=10, label='Conjunction'),
    ]
    legend = ax.legend(handles=legend_elements, loc='upper left', facecolor=panel_color,
                        edgecolor=grid_color, labelcolor=text_color)

    plt.tight_layout()
    plt.savefig('orbits_3d.png', dpi=150, bbox_inches='tight', facecolor=bg_color)
    logger.info("  Saved: orbits_3d.png")
    plt.close()


def plot_risk_timeline(conjunctions: List[Conjunction],
                       maneuvers: List[Maneuver],
                       title: str = "Conjunction Risk Timeline"):
    """
    Timeline showing conjunctions and planned maneuvers.
    """
    if not conjunctions:
        logger.info("  No conjunctions to plot.")
        return

    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(14, 8), sharex=True)

    # Top: Probability of collision over time
    tcas = [c.tca / 3600 for c in conjunctions]  # Hours
    pcs = [c.probability_of_collision for c in conjunctions]

    # Color by risk level
    colors = []
    for pc in pcs:
        if pc >= 1e-4:
            colors.append('red')
        elif pc >= 1e-5:
            colors.append('orange')
        else:
            colors.append('green')

    ax1.scatter(tcas, pcs, c=colors, s=50, alpha=0.7, edgecolors='black', linewidth=0.5)
    ax1.set_yscale('log')
    ax1.axhline(y=1e-4, color='red', linestyle='--', alpha=0.5, label='Maneuver threshold')
    ax1.axhline(y=1e-5, color='orange', linestyle='--', alpha=0.5, label='Consider threshold')
    ax1.axhline(y=1e-7, color='green', linestyle='--', alpha=0.5, label='Acceptable')
    ax1.set_ylabel('Probability of Collision')
    ax1.set_title(title)
    ax1.legend()
    ax1.grid(True, alpha=0.3)

    # Bottom: Maneuver timeline
    if maneuvers:
        man_times = [m.time / 3600 for m in maneuvers]
        man_dvs = [m.fuel_cost for m in maneuvers]

        ax2.bar(man_times, man_dvs, width=0.3, color='blue', alpha=0.7,
               edgecolor='darkblue', label='Avoidance maneuvers')

        # Cumulative fuel
        ax2_twin = ax2.twinx()
        cumulative_dv = np.cumsum(man_dvs)
        ax2_twin.plot(man_times, cumulative_dv, 'r-o', markersize=4,
                     label='Cumulative Δv')
        ax2_twin.set_ylabel('Cumulative Δv [m/s]', color='red')
        ax2_twin.tick_params(axis='y', labelcolor='red')

    ax2.set_xlabel('Time [hours]')
    ax2.set_ylabel('Maneuver Δv [m/s]')
    ax2.legend(loc='upper left')
    ax2.grid(True, alpha=0.3)

    plt.tight_layout()
    plt.savefig('risk_timeline.png', dpi=150, bbox_inches='tight')
    logger.info("  Saved: risk_timeline.png")
    plt.close()


def plot_debris_analysis(sc1: Spacecraft, sc2: Spacecraft,
                          conjunction: Conjunction,
                          title: str = "Collision Debris Analysis"):
    """
    Visualize predicted debris from a collision.
    """
    outcome = predict_collision_outcome(sc1, sc2, conjunction, n_monte_carlo=500)

    fig, axes = plt.subplots(2, 2, figsize=(14, 10))

    # 1. Fragment size distribution
    ax = axes[0, 0]
    sizes = [f.size for f in outcome.fragments]
    ax.hist(sizes, bins=30, color='steelblue', edgecolor='black', alpha=0.7)
    ax.set_xlabel('Fragment Size [m]')
    ax.set_ylabel('Count')
    ax.set_title('Fragment Size Distribution')
    ax.axvline(x=0.1, color='red', linestyle='--', label='>10cm (trackable)')
    ax.legend()

    # 2. Debris altitude distribution
    ax = axes[0, 1]
    perigees = [f.perigee_km for f in outcome.fragments if 0 < f.perigee_km < 2000]
    apogees = [f.apogee_km for f in outcome.fragments if 0 < f.apogee_km < 2000]
    if perigees and apogees:
        ax.hist(perigees, bins=30, alpha=0.6, label='Perigee', color='blue')
        ax.hist(apogees, bins=30, alpha=0.6, label='Apogee', color='red')
    ax.set_xlabel('Altitude [km]')
    ax.set_ylabel('Count')
    ax.set_title('Debris Altitude Distribution')
    ax.axvline(x=400, color='green', linestyle='--', alpha=0.7, label='Fast decay zone')
    ax.legend()

    # 3. Debris lifetime distribution
    ax = axes[1, 0]
    lifetimes = [f.orbit_lifetime_years for f in outcome.fragments
                 if 0 < f.orbit_lifetime_years < 1000]
    if lifetimes:
        ax.hist(lifetimes, bins=30, color='orange', edgecolor='black', alpha=0.7)
    ax.set_xlabel('Orbital Lifetime [years]')
    ax.set_ylabel('Count')
    ax.set_title('Debris Lifetime Distribution')
    ax.set_xscale('log')

    # 4. Summary text
    ax = axes[1, 1]
    ax.axis('off')
    summary = (
        f"COLLISION OUTCOME SUMMARY\n"
        f"{'='*35}\n\n"
        f"Type: {'CATASTROPHIC' if outcome.is_catastrophic else 'Non-catastrophic'}\n"
        f"Specific Energy: {outcome.specific_energy_j_per_kg:.0f} J/kg\n"
        f"  (threshold: {CATASTROPHIC_ENERGY:.0f} J/kg)\n\n"
        f"Fragments (>10 cm): {outcome.total_fragments_gt_10cm}\n"
        f"Fragments (>1 cm): {outcome.total_fragments_gt_1cm}\n"
        f"Total debris mass: {outcome.debris_mass_kg:.0f} kg\n\n"
        f"Mean lifetime: {outcome.mean_debris_lifetime_years:.1f} years\n"
        f"Altitude range: {outcome.min_debris_altitude_km:.0f} - "
        f"{outcome.max_debris_altitude_km:.0f} km\n\n"
        f"Cascade risk: {outcome.risk_to_other_spacecraft:.2e}"
    )
    ax.text(0.1, 0.9, summary, transform=ax.transAxes,
            fontsize=11, verticalalignment='top', fontfamily='monospace',
            bbox=dict(boxstyle='round', facecolor='lightyellow', alpha=0.8))

    plt.suptitle(title, fontsize=14, fontweight='bold')
    plt.tight_layout()
    plt.savefig('debris_analysis.png', dpi=150, bbox_inches='tight')
    logger.info("  Saved: debris_analysis.png")
    plt.close()


def plot_risk_evolution(spacecraft_list: List[Spacecraft],
                        conjunctions: List[Conjunction],
                        title: str = "Long-Term Risk Evolution"):
    """
    Plot projected risk evolution over years.
    """
    states = project_risk_evolution(spacecraft_list, conjunctions, years=10.0, time_steps=120)

    fig, axes = plt.subplots(2, 2, figsize=(14, 10))

    times = np.linspace(0, 10, len(states))

    # 1. Total collision probability
    ax = axes[0, 0]
    ax.plot(times, [s.total_collision_probability for s in states], 'r-', linewidth=2)
    ax.set_ylabel('Total Collision Probability')
    ax.set_title('Collision Risk vs Time')
    ax.grid(True, alpha=0.3)
    ax.set_yscale('log')

    # 2. Expected debris
    ax = axes[0, 1]
    ax.plot(times, [s.total_expected_debris for s in states], 'b-', linewidth=2)
    ax.set_ylabel('Expected Debris Fragments')
    ax.set_title('Debris Accumulation')
    ax.grid(True, alpha=0.3)

    # 3. Kessler index
    ax = axes[1, 0]
    kessler = [s.kessler_risk_index for s in states]
    ax.plot(times, kessler, 'purple', linewidth=2)
    ax.axhline(y=0.5, color='red', linestyle='--', label='Critical threshold')
    ax.fill_between(times, 0, kessler, alpha=0.2, color='purple')
    ax.set_xlabel('Time [years]')
    ax.set_ylabel('Kessler Syndrome Index')
    ax.set_title('Kessler Syndrome Risk')
    ax.set_ylim(0, 1)
    ax.legend()
    ax.grid(True, alpha=0.3)

    # 4. Fuel depletion
    ax = axes[1, 1]
    fuel = [s.fuel_consumed_total_ms for s in states]
    ax.plot(times, fuel, 'green', linewidth=2)
    ax.set_xlabel('Time [years]')
    ax.set_ylabel('Total Fuel Consumed [m/s equivalent]')
    ax.set_title('Constellation Fuel Depletion')
    ax.grid(True, alpha=0.3)

    plt.suptitle(title, fontsize=14, fontweight='bold')
    plt.tight_layout()
    plt.savefig('risk_evolution.png', dpi=150, bbox_inches='tight')
    logger.info("  Saved: risk_evolution.png")
    plt.close()


# ============================================================================
# MAIN ENTRY POINT
# ============================================================================


def main():
    """Run the full simulation and generate visualizations."""

    # Run simulation (20 spacecraft for faster demo; real systems handle 10,000+)
    sim = CollisionPreventionSimulation(n_spacecraft=20, seed=42)
    sim.run_full_simulation()

    # Generate visualizations
    logger.info("=" * 70)
    logger.info("  GENERATING VISUALIZATIONS")
    logger.info("=" * 70)

    plot_orbits_3d(sim.spacecraft_list, sim.conjunctions, sim.planned_maneuvers)
    plot_risk_timeline(sim.conjunctions, sim.planned_maneuvers)

    # Debris analysis for first high-risk conjunction
    if sim.conjunctions:
        sc_dict = {sc.id: sc for sc in sim.spacecraft_list}
        conj = sim.conjunctions[0]
        sc1 = sc_dict.get(conj.obj1_id)
        sc2 = sc_dict.get(conj.obj2_id)
        if sc1 and sc2:
            plot_debris_analysis(sc1, sc2, conj)

    plot_risk_evolution(sim.spacecraft_list, sim.conjunctions)

    logger.info("  All visualizations saved to current directory.")


if __name__ == '__main__':
    main()
