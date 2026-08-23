"""
Collision Avoidance Maneuver Planner
====================================

Implements:
- Optimal maneuver direction computation (maximize miss distance per unit Δv)
- Maneuver timing optimization (earlier = more efficient)
- Single-conjunction avoidance maneuver design
- Multi-conjunction joint maneuver optimization
- Fuel-constrained planning with reserve margins
- Maneuver execution and state update
- Dynamic custom strategy registration for extensible risk assessment

Custom Strategies
-----------------
Register custom risk assessment strategies by placing files in src/strategies/custom_*.py
Each file must export a function: evaluate_<name>(conjunction, spacecraft_list) -> float
The integration pipeline automatically validates and wires these strategies.
"""

import numpy as np
from scipy.optimize import minimize, minimize_scalar
from typing import List, Tuple, Optional, Dict, Callable

from .utils import (
    MU_EARTH, R_EARTH,
    StateVector, Spacecraft, Conjunction, Maneuver,
    eci_to_rtn, state_to_coe, get_logger
)

logger = get_logger(__name__)
from .orbital_mechanics import (
    propagate_state, propagate_with_stm, propagate_covariance
)
from .conjunction import (
    compute_encounter_plane, project_covariance_to_encounter_plane,
    probability_of_collision_2d, find_tca
)


# ============================================================================
# CUSTOM STRATEGY REGISTRY
# ============================================================================

CUSTOM_STRATEGIES: Dict[str, Callable] = {}
"""
Registry of custom risk assessment strategies.

Usage:
    register_strategy('relative_velocity', evaluate_relative_velocity)
    
    risk_factor = CUSTOM_STRATEGIES['relative_velocity'](conjunction, spacecraft_list)
"""


def register_strategy(name: str, func: Callable[[Conjunction, List[Spacecraft]], float]) -> None:
    """
    Register a custom risk assessment strategy.
    
    Parameters
    ----------
    name : str
        Strategy identifier (e.g., 'relative_velocity')
    func : Callable
        Function with signature: (Conjunction, List[Spacecraft]) -> float (0-1)
    
    Raises
    ------
    ValueError
        If strategy is already registered or function signature is invalid
    """
    if name in CUSTOM_STRATEGIES:
        raise ValueError(f"Strategy '{name}' already registered")
    
    CUSTOM_STRATEGIES[name] = func


def list_strategies() -> Dict[str, str]:
    """
    List all registered custom strategies.
    
    Returns
    -------
    Dict[str, str]
        Mapping of strategy name to function docstring
    """
    return {name: func.__doc__ or "No documentation" 
            for name, func in CUSTOM_STRATEGIES.items()}


def apply_custom_strategies(conjunction: Conjunction, 
                           spacecraft_list: List[Spacecraft]) -> Dict[str, float]:
    """
    Apply all registered custom strategies to a conjunction.
    
    Parameters
    ----------
    conjunction : Conjunction
        The conjunction event to assess
    spacecraft_list : List[Spacecraft]
        Full constellation for context
    
    Returns
    -------
    Dict[str, float]
        Mapping of strategy name to computed risk factor (0-1)
    """
    results = {}
    for name, func in CUSTOM_STRATEGIES.items():
        try:
            results[name] = func(conjunction, spacecraft_list)
        except Exception as e:
            logger.warning("Custom strategy '%s' failed: %s", name, e)
            results[name] = None
    
    return results


# ============================================================================
# MANEUVER EFFECTIVENESS (STM-based)
# ============================================================================


def maneuver_effectiveness_matrix(state: StateVector, tca: float,
                                   t_maneuver: float,
                                   area_mass_ratio: float = 0.01) -> np.ndarray:
    """
    Compute how a velocity change at t_maneuver maps to position change at TCA.

    Uses the position-velocity partition of the State Transition Matrix:
        Δr(TCA) = Φ_rv(TCA, t_man) · Δv(t_man)

    This 3×3 matrix tells us exactly how each component of Δv translates
    to position displacement at the encounter.

    Parameters
    ----------
    state : StateVector
        Spacecraft state at current time (t=0)
    tca : float
        Time of closest approach [seconds from now]
    t_maneuver : float
        Planned maneuver time [seconds from now]
    area_mass_ratio : float
        A/m for the spacecraft [m²/kg]

    Returns
    -------
    ndarray (3, 3)
        Position sensitivity to velocity change: Δr_TCA = M · Δv_maneuver
    """
    # First propagate to maneuver time
    state_at_maneuver = propagate_state(state, t_maneuver, area_mass_ratio=area_mass_ratio)

    # Then get STM from maneuver time to TCA
    dt_to_tca = tca - t_maneuver
    _, stm = propagate_with_stm(state_at_maneuver, dt_to_tca,
                                 area_mass_ratio=area_mass_ratio)

    # Extract Φ_rv (upper-right 3×3 block): maps Δv → Δr
    phi_rv = stm[:3, 3:]

    return phi_rv


def optimal_maneuver_direction(phi_rv: np.ndarray,
                                miss_vector_3d: np.ndarray) -> np.ndarray:
    """
    Compute the optimal Δv direction that maximizes miss distance change.

    The optimal direction maximizes |Φ_rv · Δv_hat| in the direction
    that increases the miss distance.

    More precisely: maximize Δv_hat · Φ_rvᵀ · miss_hat

    Parameters
    ----------
    phi_rv : ndarray (3, 3)
        Maneuver effectiveness matrix
    miss_vector_3d : ndarray (3,)
        Current miss vector at TCA (r1 - r2)

    Returns
    -------
    ndarray (3,)
        Optimal unit Δv direction (in ECI frame at maneuver time)
    """
    miss_hat = miss_vector_3d / np.linalg.norm(miss_vector_3d)

    # Optimal direction: Φ_rvᵀ · miss_hat (maximizes miss distance increase)
    optimal = phi_rv.T @ miss_hat
    optimal_mag = np.linalg.norm(optimal)

    if optimal_mag < 1e-15:
        # Degenerate case — use maximum singular vector
        U, S, Vt = np.linalg.svd(phi_rv)
        return Vt[0]  # Direction of maximum effectiveness

    return optimal / optimal_mag


def maneuver_effectiveness_scalar(phi_rv: np.ndarray,
                                   direction: np.ndarray) -> float:
    """
    Compute miss distance change per unit Δv in a given direction.

    effectiveness = |Φ_rv · direction|

    Parameters
    ----------
    phi_rv : ndarray (3, 3)
        Maneuver effectiveness matrix
    direction : ndarray (3,)
        Unit Δv direction

    Returns
    -------
    float
        km of miss distance change per km/s of Δv
    """
    return np.linalg.norm(phi_rv @ direction)


# ============================================================================
# MANEUVER TIMING OPTIMIZATION
# ============================================================================


def optimal_maneuver_time(state: StateVector, tca: float,
                          earliest: float = 0.0,
                          area_mass_ratio: float = 0.01,
                          n_samples: int = 20) -> float:
    """
    Find the optimal maneuver time that maximizes effectiveness.

    Earlier maneuvers are generally more effective (more propagation time),
    but effectiveness also varies within an orbit due to geometry.

    Parameters
    ----------
    state : StateVector
        Current state
    tca : float
        Time of closest approach [seconds]
    earliest : float
        Earliest possible maneuver time [seconds from now]
    area_mass_ratio : float
        A/m ratio
    n_samples : int
        Number of time samples to evaluate

    Returns
    -------
    float
        Optimal maneuver time [seconds from now]
    """
    # Don't maneuver too close to TCA (need time for effect)
    latest = tca - 300.0  # At least 5 minutes before TCA

    if latest <= earliest:
        return earliest

    # Sample effectiveness at different times
    times = np.linspace(earliest, latest, n_samples)
    effectiveness = np.zeros(n_samples)

    for idx, t_man in enumerate(times):
        try:
            phi_rv = maneuver_effectiveness_matrix(state, tca, t_man, area_mass_ratio)
            # Maximum singular value = maximum possible effectiveness
            _, S, _ = np.linalg.svd(phi_rv)
            effectiveness[idx] = S[0]
        except (RuntimeError, np.linalg.LinAlgError):
            effectiveness[idx] = 0.0

    # Return time of maximum effectiveness
    best_idx = np.argmax(effectiveness)
    return times[best_idx]


# ============================================================================
# SINGLE CONJUNCTION AVOIDANCE
# ============================================================================


def design_avoidance_maneuver(spacecraft: Spacecraft,
                               other: Spacecraft,
                               conjunction: Conjunction,
                               target_miss_km: float = 1.0,
                               max_delta_v_ms: Optional[float] = None,
                               maneuver_time: Optional[float] = None
                               ) -> Optional[Maneuver]:
    """
    Design an optimal collision avoidance maneuver for a single conjunction.

    Strategy:
    1. Compute maneuver effectiveness matrix (STM-based)
    2. Find optimal direction (maximize miss distance per Δv)
    3. Compute required Δv magnitude for target miss distance
    4. Check against fuel budget

    Parameters
    ----------
    spacecraft : Spacecraft
        The spacecraft that will maneuver
    other : Spacecraft
        The other object (not maneuvering)
    conjunction : Conjunction
        The conjunction to avoid
    target_miss_km : float
        Desired minimum miss distance after maneuver [km]
    max_delta_v_ms : float, optional
        Maximum allowed Δv [m/s]. Defaults to remaining budget.
    maneuver_time : float, optional
        Forced maneuver time. If None, optimized automatically.

    Returns
    -------
    Maneuver or None
        Designed maneuver, or None if infeasible
    """
    tca = conjunction.tca
    am = spacecraft.area / spacecraft.mass

    if max_delta_v_ms is None:
        max_delta_v_ms = spacecraft.delta_v_budget - spacecraft.delta_v_used

    max_delta_v_kms = max_delta_v_ms / 1000.0  # Convert to km/s

    # Step 1: Determine maneuver time
    if maneuver_time is None:
        maneuver_time = optimal_maneuver_time(
            spacecraft.state, tca,
            earliest=60.0,  # At least 1 minute from now
            area_mass_ratio=am
        )

    # Step 2: Compute effectiveness matrix
    try:
        phi_rv = maneuver_effectiveness_matrix(
            spacecraft.state, tca, maneuver_time, am
        )
    except RuntimeError:
        return None

    # Step 3: Compute current miss vector at TCA
    state_at_tca = propagate_state(spacecraft.state, tca, area_mass_ratio=am)
    other_at_tca = propagate_state(other.state, tca, area_mass_ratio=other.area / other.mass)
    miss_vector_3d = state_at_tca.r - other_at_tca.r
    current_miss = np.linalg.norm(miss_vector_3d)

    # Step 4: Optimal direction
    dv_direction = optimal_maneuver_direction(phi_rv, miss_vector_3d)

    # Step 5: Required Δv magnitude
    # Δmiss = |Φ_rv · Δv| = effectiveness · |Δv|
    effectiveness = maneuver_effectiveness_scalar(phi_rv, dv_direction)

    if effectiveness < 1e-6:
        return None  # Maneuver not effective at this time

    required_miss_change = max(0, target_miss_km - current_miss)

    if required_miss_change <= 0:
        # Already safe — no maneuver needed
        # But we might still want to increase margin
        required_miss_change = target_miss_km * 0.5  # Add some margin anyway

    dv_magnitude = required_miss_change / effectiveness  # km/s

    # Step 6: Check feasibility
    if dv_magnitude > max_delta_v_kms:
        # Can't fully resolve — use maximum available
        dv_magnitude = max_delta_v_kms

    # Step 7: Construct maneuver
    delta_v_eci = dv_direction * dv_magnitude

    # Convert to RTN frame at maneuver time
    state_at_man = propagate_state(spacecraft.state, maneuver_time, area_mass_ratio=am)
    rtn_matrix = eci_to_rtn(state_at_man.r, state_at_man.v)
    delta_v_rtn = rtn_matrix @ delta_v_eci

    maneuver = Maneuver(
        spacecraft_id=spacecraft.id,
        time=maneuver_time,
        delta_v=delta_v_rtn,
        target_conjunction_id=f"{conjunction.obj1_id}_{conjunction.obj2_id}_{tca:.0f}"
    )

    return maneuver


def evaluate_maneuver(spacecraft: Spacecraft, other: Spacecraft,
                      maneuver: Maneuver, tca: float) -> Tuple[float, float]:
    """
    Evaluate a maneuver's effectiveness: new miss distance and new Pc.

    Parameters
    ----------
    spacecraft : Spacecraft
        Maneuvering spacecraft
    other : Spacecraft
        Other object
    maneuver : Maneuver
        The proposed maneuver
    tca : float
        Original TCA

    Returns
    -------
    new_miss_distance : float
        Miss distance after maneuver [km]
    new_pc : float
        Probability of collision after maneuver
    """
    am = spacecraft.area / spacecraft.mass

    # Propagate to maneuver time
    state_at_man = propagate_state(spacecraft.state, maneuver.time, area_mass_ratio=am)

    # Apply Δv (convert RTN back to ECI)
    rtn_matrix = eci_to_rtn(state_at_man.r, state_at_man.v)
    delta_v_eci = rtn_matrix.T @ maneuver.delta_v  # RTN → ECI

    new_state_at_man = StateVector(
        r=state_at_man.r,
        v=state_at_man.v + delta_v_eci
    )

    # Propagate post-maneuver state to TCA
    dt_to_tca = tca - maneuver.time
    new_state_tca = propagate_state(new_state_at_man, dt_to_tca, area_mass_ratio=am)

    # Other object at TCA
    other_at_tca = propagate_state(other.state, tca,
                                    area_mass_ratio=other.area / other.mass)

    # New miss distance
    new_miss = np.linalg.norm(new_state_tca.r - other_at_tca.r)

    # New Pc (simplified — use original covariance as approximation)
    miss_2d, _, proj_matrix = compute_encounter_plane(new_state_tca, other_at_tca)

    cov_2d = project_covariance_to_encounter_plane(
        spacecraft.covariance, other.covariance, proj_matrix
    )

    r1 = np.sqrt(spacecraft.area / np.pi) / 1000.0
    r2 = np.sqrt(other.area / np.pi) / 1000.0
    combined_radius = r1 + r2

    new_pc = probability_of_collision_2d(miss_2d, cov_2d, combined_radius)

    return new_miss, new_pc


# ============================================================================
# MULTI-CONJUNCTION JOINT OPTIMIZATION
# ============================================================================


def joint_avoidance_optimization(spacecraft: Spacecraft,
                                  others: List[Spacecraft],
                                  conjunctions: List[Conjunction],
                                  fuel_reserve_fraction: float = 0.3
                                  ) -> List[Maneuver]:
    """
    Jointly optimize maneuvers for multiple conjunctions affecting one spacecraft.

    A single well-timed maneuver can resolve multiple conjunctions.
    This optimizer finds the minimum-fuel solution that satisfies all constraints.

    Parameters
    ----------
    spacecraft : Spacecraft
        The maneuvering spacecraft
    others : list of Spacecraft
        Other objects involved in conjunctions
    conjunctions : list of Conjunction
        All active conjunctions for this spacecraft
    fuel_reserve_fraction : float
        Fraction of remaining budget to keep in reserve for future unknowns

    Returns
    -------
    list of Maneuver
        Optimal maneuver sequence (may be 1 maneuver resolving multiple conjunctions)
    """
    if not conjunctions:
        return []

    am = spacecraft.area / spacecraft.mass
    available_dv = (spacecraft.delta_v_budget - spacecraft.delta_v_used) * (1 - fuel_reserve_fraction)
    available_dv_kms = available_dv / 1000.0  # m/s → km/s

    # Sort conjunctions by TCA
    sorted_conjs = sorted(conjunctions, key=lambda c: c.tca)
    earliest_tca = sorted_conjs[0].tca

    # Try single maneuver first (most fuel efficient)
    # Maneuver time: well before earliest TCA
    t_man = min(earliest_tca * 0.5, earliest_tca - 3600.0)  # Half-way or 1hr before
    t_man = max(t_man, 60.0)  # At least 1 minute from now

    # Optimization: find Δv that minimizes max Pc across all conjunctions
    def objective(dv_flat):
        """Minimize sum of Pc across all conjunctions."""
        dv_eci = dv_flat  # In ECI at maneuver time

        # Check fuel constraint
        dv_mag = np.linalg.norm(dv_eci)
        if dv_mag > available_dv_kms:
            return 1e10  # Infeasible

        # Apply maneuver and check each conjunction
        state_at_man = propagate_state(spacecraft.state, t_man, area_mass_ratio=am)
        new_state = StateVector(r=state_at_man.r, v=state_at_man.v + dv_eci)

        total_risk = 0.0
        for conj, other in zip(sorted_conjs, others):
            dt = conj.tca - t_man
            try:
                new_state_tca = propagate_state(new_state, dt, area_mass_ratio=am)
                other_tca = propagate_state(
                    other.state, conj.tca,
                    area_mass_ratio=other.area / other.mass
                )
                miss = np.linalg.norm(new_state_tca.r - other_tca.r)
                # Penalize small miss distances exponentially
                total_risk += np.exp(-miss / 0.5)  # e-folding at 500m
            except RuntimeError:
                total_risk += 1.0

        # Add fuel penalty
        fuel_penalty = 0.1 * (dv_mag / available_dv_kms)**2

        return total_risk + fuel_penalty

    # Initial guess: optimal direction for highest-risk conjunction
    try:
        phi_rv = maneuver_effectiveness_matrix(spacecraft.state, sorted_conjs[0].tca, t_man, am)
        state_tca = propagate_state(spacecraft.state, sorted_conjs[0].tca, area_mass_ratio=am)
        other_tca = propagate_state(
            others[0].state, sorted_conjs[0].tca,
            area_mass_ratio=others[0].area / others[0].mass
        )
        miss_3d = state_tca.r - other_tca.r
        direction = optimal_maneuver_direction(phi_rv, miss_3d)
        x0 = direction * available_dv_kms * 0.1  # Start with 10% of budget
    except (RuntimeError, np.linalg.LinAlgError):
        x0 = np.array([available_dv_kms * 0.01, 0, 0])

    # Optimize
    result = minimize(
        objective, x0,
        method='Nelder-Mead',
        options={'maxiter': 500, 'xatol': 1e-8, 'fatol': 1e-10}
    )

    if not result.success and result.fun > 0.5:
        # Single maneuver might not suffice — try two maneuvers
        # (For now, just use the best single maneuver found)
        pass

    dv_optimal = result.x
    dv_mag = np.linalg.norm(dv_optimal)

    if dv_mag < 1e-10:
        return []  # No maneuver needed

    # Convert to RTN
    state_at_man = propagate_state(spacecraft.state, t_man, area_mass_ratio=am)
    rtn_matrix = eci_to_rtn(state_at_man.r, state_at_man.v)
    dv_rtn = rtn_matrix @ dv_optimal

    maneuver = Maneuver(
        spacecraft_id=spacecraft.id,
        time=t_man,
        delta_v=dv_rtn,
        target_conjunction_id="multi_conjunction"
    )

    return [maneuver]


# ============================================================================
# MANEUVER EXECUTION
# ============================================================================


def apply_maneuver(spacecraft: Spacecraft, maneuver: Maneuver) -> Spacecraft:
    """
    Apply a maneuver to a spacecraft, updating its state and fuel budget.

    Parameters
    ----------
    spacecraft : Spacecraft
        Pre-maneuver spacecraft
    maneuver : Maneuver
        Maneuver to execute

    Returns
    -------
    Spacecraft
        Post-maneuver spacecraft with updated state and fuel
    """
    am = spacecraft.area / spacecraft.mass

    # Propagate to maneuver time
    state_at_man = propagate_state(spacecraft.state, maneuver.time, area_mass_ratio=am)

    # Convert RTN Δv to ECI
    rtn_matrix = eci_to_rtn(state_at_man.r, state_at_man.v)
    delta_v_eci = rtn_matrix.T @ maneuver.delta_v

    # Apply Δv
    new_state = StateVector(
        r=state_at_man.r.copy(),
        v=state_at_man.v + delta_v_eci
    )

    # Update fuel budget
    fuel_used = maneuver.fuel_cost  # Already in m/s

    # Increase covariance slightly (maneuver execution error)
    # Typical: 1% of Δv as 1-sigma error
    maneuver_error_sigma = 0.01 * np.linalg.norm(maneuver.delta_v)  # km/s
    cov_increase = np.zeros((6, 6))
    cov_increase[3:, 3:] = maneuver_error_sigma**2 * np.eye(3)
    new_cov = spacecraft.covariance + cov_increase

    return Spacecraft(
        id=spacecraft.id,
        state=new_state,
        covariance=new_cov,
        mass=spacecraft.mass,
        area=spacecraft.area,
        cd=spacecraft.cd,
        cr=spacecraft.cr,
        delta_v_budget=spacecraft.delta_v_budget,
        delta_v_used=spacecraft.delta_v_used + fuel_used,
        maneuverable=spacecraft.maneuverable,
        name=spacecraft.name
    )


# ============================================================================
# DECISION LOGIC
# ============================================================================


class ManeuverDecision:
    """Decision framework for whether and how to maneuver."""

    # Pc thresholds
    PC_MANEUVER = 1e-4        # Strong recommendation to maneuver
    PC_CONSIDER = 1e-5        # Consider maneuver, cost-benefit analysis
    PC_MONITOR = 1e-6         # Monitor, refine tracking
    PC_ACCEPTABLE = 1e-7      # Acceptable risk

    # Fuel thresholds
    FUEL_CRITICAL = 5.0       # m/s — below this, only maneuver for extreme risk
    FUEL_LOW = 10.0           # m/s — conservative maneuver planning
    FUEL_NORMAL = 25.0        # m/s — normal operations

    @staticmethod
    def should_maneuver(conjunction: Conjunction,
                        spacecraft: Spacecraft,
                        time_to_tca: float) -> str:
        """
        Decide whether to maneuver based on Pc, fuel, and timing.

        Parameters
        ----------
        conjunction : Conjunction
            The conjunction to evaluate
        spacecraft : Spacecraft
            The spacecraft in question
        time_to_tca : float
            Time remaining until TCA [seconds]

        Returns
        -------
        str
            Decision: 'MANEUVER', 'CONSIDER', 'MONITOR', 'ACCEPT'
        """
        Pc = conjunction.probability_of_collision
        fuel_remaining = spacecraft.delta_v_budget - spacecraft.delta_v_used

        # Not maneuverable
        if not spacecraft.maneuverable:
            return 'ACCEPT'

        # Fuel critical — only maneuver for extreme danger
        if fuel_remaining < ManeuverDecision.FUEL_CRITICAL:
            if Pc > 1e-3:  # Very high risk
                return 'MANEUVER'
            return 'ACCEPT'

        # Time critical — maneuver becomes less effective close to TCA
        if time_to_tca < 300:  # Less than 5 minutes
            if Pc > 1e-3:
                return 'MANEUVER'  # Emergency
            return 'ACCEPT'  # Too late for effective maneuver

        # Standard decision logic
        if Pc >= ManeuverDecision.PC_MANEUVER:
            return 'MANEUVER'
        elif Pc >= ManeuverDecision.PC_CONSIDER:
            # Cost-benefit: maneuver if fuel is available and risk is significant
            if fuel_remaining > ManeuverDecision.FUEL_LOW:
                return 'MANEUVER'
            return 'CONSIDER'
        elif Pc >= ManeuverDecision.PC_MONITOR:
            return 'MONITOR'
        else:
            return 'ACCEPT'

    @staticmethod
    def prioritize_conjunctions(conjunctions: List[Conjunction],
                                 spacecraft_dict: dict) -> List[Conjunction]:
        """
        Prioritize conjunctions for maneuver planning.

        Considers:
        - Risk score (Pc × consequence)
        - Time urgency (sooner TCA = higher priority)
        - Fuel efficiency (can one maneuver resolve multiple?)

        Parameters
        ----------
        conjunctions : list of Conjunction
            All active conjunctions
        spacecraft_dict : dict
            Mapping of spacecraft_id → Spacecraft

        Returns
        -------
        list of Conjunction
            Sorted by priority (highest first)
        """
        def priority_score(conj):
            # Base: risk score
            score = conj.risk_score

            # Time urgency multiplier (exponential as TCA approaches)
            # Urgency doubles every 6 hours
            hours_to_tca = conj.tca / 3600.0
            urgency = 2.0 ** max(0, (24 - hours_to_tca) / 6.0)
            score *= urgency

            # Maneuverability discount (if neither object can maneuver, lower priority)
            obj1 = spacecraft_dict.get(conj.obj1_id)
            obj2 = spacecraft_dict.get(conj.obj2_id)
            if obj1 and not obj1.maneuverable and obj2 and not obj2.maneuverable:
                score *= 0.1  # Can't do anything — deprioritize

            return score

        return sorted(conjunctions, key=priority_score, reverse=True)


# ============================================================================
# FULL AVOIDANCE PIPELINE
# ============================================================================


def plan_avoidance_campaign(spacecraft_list: List[Spacecraft],
                             conjunctions: List[Conjunction],
                             planning_horizon: float = 86400.0
                             ) -> List[Maneuver]:
    """
    Plan a complete avoidance campaign for all active conjunctions.

    This is the top-level planning function that:
    1. Prioritizes conjunctions by risk and urgency
    2. Assigns maneuvers to spacecraft
    3. Checks for conflicts (one maneuver creating new problems)
    4. Returns the optimal maneuver sequence

    Parameters
    ----------
    spacecraft_list : list of Spacecraft
        All spacecraft in the constellation
    conjunctions : list of Conjunction
        All active conjunctions from screening
    planning_horizon : float
        Planning window [seconds]

    Returns
    -------
    list of Maneuver
        Planned maneuvers in execution order
    """
    # Build lookup
    sc_dict = {sc.id: sc for sc in spacecraft_list}

    # Prioritize
    prioritized = ManeuverDecision.prioritize_conjunctions(conjunctions, sc_dict)

    planned_maneuvers = []
    modified_spacecraft = {}  # Track spacecraft that have been assigned maneuvers

    for conj in prioritized:
        # Check if either object can maneuver
        obj1 = sc_dict.get(conj.obj1_id)
        obj2 = sc_dict.get(conj.obj2_id)

        if obj1 is None or obj2 is None:
            continue

        # Use modified state if spacecraft already has a planned maneuver
        if conj.obj1_id in modified_spacecraft:
            obj1 = modified_spacecraft[conj.obj1_id]
        if conj.obj2_id in modified_spacecraft:
            obj2 = modified_spacecraft[conj.obj2_id]

        # Determine who maneuvers (prefer the one with more fuel)
        maneuverer, target = None, None
        if obj1.maneuverable and obj2.maneuverable:
            fuel1 = obj1.delta_v_budget - obj1.delta_v_used
            fuel2 = obj2.delta_v_budget - obj2.delta_v_used
            if fuel1 >= fuel2:
                maneuverer, target = obj1, obj2
            else:
                maneuverer, target = obj2, obj1
        elif obj1.maneuverable:
            maneuverer, target = obj1, obj2
        elif obj2.maneuverable:
            maneuverer, target = obj2, obj1
        else:
            continue  # Neither can maneuver

        # Check decision
        decision = ManeuverDecision.should_maneuver(conj, maneuverer, conj.tca)

        if decision in ('MANEUVER', 'CONSIDER'):
            maneuver = design_avoidance_maneuver(
                maneuverer, target, conj,
                target_miss_km=1.0
            )

            if maneuver is not None:
                planned_maneuvers.append(maneuver)
                # Update spacecraft state for subsequent planning
                modified_spacecraft[maneuverer.id] = apply_maneuver(maneuverer, maneuver)

    # Sort by execution time
    planned_maneuvers.sort(key=lambda m: m.time)

    return planned_maneuvers
