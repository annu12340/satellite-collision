"""
Damage Minimization Module (Unavoidable Collisions)
====================================================

When a collision cannot be prevented (insufficient Δv, too little time, or
non-maneuverable debris), the objective shifts from avoidance to damage control.

Implements:
- NASA Standard Breakup Model for debris prediction
- Impact geometry analysis (head-on vs glancing)
- Relative velocity reduction strategies
- Optimal attitude orientation for minimum cross-section
- Debris orbit distribution prediction
- Altitude selection for fast debris removal
- Collision consequence scoring and strategy ranking
"""

import numpy as np
from dataclasses import dataclass, field
from typing import List, Tuple, Optional

from .utils import (
    MU_EARTH, R_EARTH, CATASTROPHIC_ENERGY,
    StateVector, Spacecraft, Conjunction, Maneuver,
    state_to_coe, eci_to_rtn, orbital_period
)
from .orbital_mechanics import propagate_state


# ============================================================================
# DATA STRUCTURES
# ============================================================================


@dataclass
class DebrisFragment:
    """A single debris fragment from a collision."""
    size: float  # Characteristic length [m]
    mass: float  # Mass [kg]
    area: float  # Cross-sectional area [m²]
    delta_v: np.ndarray  # Velocity change from parent [km/s]
    orbit_lifetime_years: float  # Estimated orbital lifetime
    perigee_km: float  # Perigee altitude [km]
    apogee_km: float  # Apogee altitude [km]


@dataclass
class CollisionOutcome:
    """Predicted outcome of a collision event."""
    is_catastrophic: bool
    specific_energy_j_per_kg: float
    total_fragments_gt_10cm: int
    total_fragments_gt_1cm: int
    debris_mass_kg: float
    mean_debris_lifetime_years: float
    max_debris_altitude_km: float
    min_debris_altitude_km: float
    fragments: List[DebrisFragment] = field(default_factory=list)
    risk_to_other_spacecraft: float = 0.0  # Cascade risk metric


@dataclass
class MitigationStrategy:
    """A damage mitigation strategy with its expected outcome."""
    name: str
    description: str
    required_delta_v_ms: float  # Δv needed to execute [m/s]
    time_required_s: float  # Time needed before impact
    outcome: Optional[CollisionOutcome] = None
    effectiveness_score: float = 0.0  # 0-1, higher = less damage
    feasibility_score: float = 0.0  # 0-1, higher = more achievable


# ============================================================================
# NASA STANDARD BREAKUP MODEL
# ============================================================================


def collision_specific_energy(mass_projectile: float, mass_target: float,
                               relative_velocity_kms: float) -> float:
    """
    Compute specific energy of a collision.

    E_specific = ½ · m_projectile · v_rel² / m_target

    Parameters
    ----------
    mass_projectile : float
        Mass of smaller object [kg]
    mass_target : float
        Mass of larger object [kg]
    relative_velocity_kms : float
        Relative velocity [km/s]

    Returns
    -------
    float
        Specific energy [J/kg]
    """
    v_ms = relative_velocity_kms * 1000.0  # km/s → m/s
    return 0.5 * mass_projectile * v_ms**2 / mass_target


def is_catastrophic(mass1: float, mass2: float,
                     relative_velocity_kms: float) -> bool:
    """
    Determine if collision would be catastrophic (complete fragmentation).

    Threshold: 40 J/g = 40,000 J/kg

    Parameters
    ----------
    mass1, mass2 : float
        Object masses [kg]
    relative_velocity_kms : float
        Relative velocity [km/s]

    Returns
    -------
    bool
        True if collision exceeds catastrophic threshold
    """
    m_proj = min(mass1, mass2)
    m_targ = max(mass1, mass2)
    E = collision_specific_energy(m_proj, m_targ, relative_velocity_kms)
    return E >= CATASTROPHIC_ENERGY


def fragment_count(mass1: float, mass2: float,
                   relative_velocity_kms: float,
                   min_size_m: float = 0.1) -> int:
    """
    Estimate number of fragments above a given size using NASA breakup model.

    Catastrophic: N(L > Lc) = 0.1 · M_total^0.75 · Lc^(-1.71)
    Non-catastrophic: N(L > Lc) = 0.1 · m_p^0.75 · v_rel^0.5 · Lc^(-1.71)

    Parameters
    ----------
    mass1, mass2 : float
        Object masses [kg]
    relative_velocity_kms : float
        Relative velocity [km/s]
    min_size_m : float
        Minimum fragment size to count [m]

    Returns
    -------
    int
        Expected number of fragments larger than min_size_m
    """
    m_proj = min(mass1, mass2)
    m_targ = max(mass1, mass2)

    if is_catastrophic(mass1, mass2, relative_velocity_kms):
        M_total = mass1 + mass2
        N = 0.1 * M_total**0.75 * min_size_m**(-1.71)
    else:
        v_rel_kms = relative_velocity_kms
        N = 0.1 * m_proj**0.75 * v_rel_kms**0.5 * min_size_m**(-1.71)

    return max(1, int(round(N)))


def fragment_size_distribution(N_total: int, n_samples: int = 100) -> np.ndarray:
    """
    Generate fragment size distribution following power law.

    The cumulative distribution is: N(>L) ∝ L^(-1.71)
    So the PDF is: p(L) ∝ L^(-2.71)

    Parameters
    ----------
    N_total : int
        Total expected fragments (> 0.1m)
    n_samples : int
        Number of samples to generate

    Returns
    -------
    ndarray
        Array of fragment characteristic lengths [m]
    """
    # Power-law sampling: L = L_min * u^(-1/1.71) where u ~ Uniform(0,1)
    # Truncated at L_min = 0.01m (1cm)
    L_min = 0.01  # meters
    L_max = 5.0   # meters (largest reasonable fragment)

    # Inverse CDF sampling for power law with exponent α = 1.71
    alpha = 1.71
    u = np.random.uniform(0, 1, n_samples)

    # CDF: F(L) = 1 - (L/L_min)^(-alpha) for L >= L_min
    # Inverse: L = L_min * (1-u)^(-1/alpha)
    sizes = L_min * (1 - u * (1 - (L_min / L_max)**alpha))**(-1.0 / alpha)

    return np.clip(sizes, L_min, L_max)


def fragment_mass_from_size(size_m: float) -> float:
    """
    Estimate fragment mass from characteristic length.

    Uses area-to-mass ratio correlations from breakup model.

    Parameters
    ----------
    size_m : float
        Characteristic length [m]

    Returns
    -------
    float
        Estimated mass [kg]
    """
    # A/m correlation (simplified from NASA model)
    # For spacecraft fragments: log10(A/m) ~ N(-0.95, 0.55) for L > 11cm
    # Use mean relationship: A/m ≈ 0.112 m²/kg for typical fragments
    # A ≈ size² (characteristic area)
    # m = A / (A/m) = size² / 0.112

    area = size_m**2 * 0.5  # Approximate cross-section
    am_ratio = 10**(-0.95)  # Mean A/m from model ≈ 0.112 m²/kg

    mass = area / am_ratio
    return max(0.001, mass)  # Minimum 1 gram


def fragment_velocity_distribution(specific_energy: float,
                                    n_fragments: int) -> np.ndarray:
    """
    Generate velocity perturbations for debris fragments.

    Fragment ejection velocities depend on specific energy and follow
    a distribution derived from empirical hypervelocity impact data.

    Parameters
    ----------
    specific_energy : float
        Collision specific energy [J/kg]
    n_fragments : int
        Number of fragments

    Returns
    -------
    ndarray (n, 3)
        Velocity perturbations in random directions [km/s]
    """
    # Characteristic ejection velocity
    # v_ej ~ sqrt(2 * E_specific / mass_ratio_factor)
    # Empirically: σ_v ≈ 0.1-1.0 km/s for catastrophic, less for non-catastrophic
    if specific_energy >= CATASTROPHIC_ENERGY:
        sigma_v = min(1.0, np.sqrt(specific_energy / CATASTROPHIC_ENERGY) * 0.3)
    else:
        sigma_v = 0.05 * np.sqrt(specific_energy / 1000.0)

    sigma_v = max(0.01, sigma_v)  # Minimum 10 m/s

    # Random directions (isotropic)
    directions = np.random.randn(n_fragments, 3)
    directions /= np.linalg.norm(directions, axis=1, keepdims=True)

    # Log-normal magnitude distribution
    magnitudes = np.random.lognormal(
        mean=np.log(sigma_v * 0.5),
        sigma=0.8,
        size=n_fragments
    )

    return directions * magnitudes[:, np.newaxis]


# ============================================================================
# DEBRIS ORBIT PREDICTION
# ============================================================================


def predict_debris_orbits(collision_state: StateVector,
                          fragment_velocities: np.ndarray,
                          collision_altitude_km: float) -> List[Tuple[float, float, float]]:
    """
    Predict orbital parameters of debris fragments.

    Each fragment gets the parent velocity + ejection velocity,
    resulting in a spread of orbital elements.

    Parameters
    ----------
    collision_state : StateVector
        State of the collision center-of-mass
    fragment_velocities : ndarray (n, 3)
        Fragment ejection velocities [km/s]
    collision_altitude_km : float
        Altitude of collision [km]

    Returns
    -------
    list of (perigee_km, apogee_km, lifetime_years)
        Orbital parameters and lifetime for each fragment
    """
    from .conjunction import debris_lifetime

    results = []

    for dv in fragment_velocities:
        # Fragment state
        frag_state = StateVector(
            r=collision_state.r.copy(),
            v=collision_state.v + dv
        )

        # Convert to orbital elements
        try:
            coe = state_to_coe(frag_state)

            # Check if orbit is valid (bound, not impacting Earth)
            if coe.e >= 1.0 or coe.a <= 0:
                # Hyperbolic — escapes (good for debris)
                results.append((0, np.inf, 0.0))
                continue

            perigee = coe.a * (1 - coe.e) - R_EARTH
            apogee = coe.a * (1 + coe.e) - R_EARTH

            if perigee < 0:
                # Will reenter quickly
                lifetime = 0.01  # days
            else:
                lifetime = debris_lifetime(perigee)

            results.append((perigee, apogee, lifetime))

        except (ValueError, RuntimeError):
            results.append((collision_altitude_km, collision_altitude_km, 1.0))

    return results


def predict_collision_outcome(sc1: Spacecraft, sc2: Spacecraft,
                               conjunction: Conjunction,
                               n_monte_carlo: int = 200) -> CollisionOutcome:
    """
    Full collision outcome prediction using NASA breakup model.

    Parameters
    ----------
    sc1, sc2 : Spacecraft
        The colliding objects
    conjunction : Conjunction
        Conjunction details (TCA, relative velocity)
    n_monte_carlo : int
        Number of Monte Carlo debris samples

    Returns
    -------
    CollisionOutcome
        Complete prediction of collision consequences
    """
    v_rel = conjunction.relative_velocity
    mass1, mass2 = sc1.mass, sc2.mass

    # Specific energy
    m_proj = min(mass1, mass2)
    m_targ = max(mass1, mass2)
    E_spec = collision_specific_energy(m_proj, m_targ, v_rel)

    # Catastrophic check
    catastrophic = E_spec >= CATASTROPHIC_ENERGY

    # Fragment counts
    N_10cm = fragment_count(mass1, mass2, v_rel, min_size_m=0.1)
    N_1cm = fragment_count(mass1, mass2, v_rel, min_size_m=0.01)

    # Generate debris samples
    sizes = fragment_size_distribution(N_10cm, n_monte_carlo)
    velocities = fragment_velocity_distribution(E_spec, n_monte_carlo)

    # Collision state (center of mass)
    am1 = sc1.area / sc1.mass
    state1_tca = propagate_state(sc1.state, conjunction.tca, area_mass_ratio=am1)
    state2_tca = propagate_state(sc2.state, conjunction.tca,
                                  area_mass_ratio=sc2.area / sc2.mass)

    # Center of mass state
    total_mass = mass1 + mass2
    com_r = (mass1 * state1_tca.r + mass2 * state2_tca.r) / total_mass
    com_v = (mass1 * state1_tca.v + mass2 * state2_tca.v) / total_mass
    com_state = StateVector(r=com_r, v=com_v)

    collision_alt = np.linalg.norm(com_r) - R_EARTH

    # Predict debris orbits
    orbit_data = predict_debris_orbits(com_state, velocities, collision_alt)

    # Build fragment list
    fragments = []
    total_debris_mass = 0.0
    lifetimes = []

    for i, (size, dv, (perigee, apogee, lifetime)) in enumerate(
            zip(sizes, velocities, orbit_data)):
        mass = fragment_mass_from_size(size)
        area = size**2 * 0.5
        total_debris_mass += mass
        lifetimes.append(lifetime)

        fragments.append(DebrisFragment(
            size=size,
            mass=mass,
            area=area,
            delta_v=dv,
            orbit_lifetime_years=lifetime,
            perigee_km=perigee,
            apogee_km=apogee
        ))

    # Summary statistics
    perigees = [f.perigee_km for f in fragments if f.perigee_km > 0]
    apogees = [f.apogee_km for f in fragments if f.apogee_km < 100000]

    outcome = CollisionOutcome(
        is_catastrophic=catastrophic,
        specific_energy_j_per_kg=E_spec,
        total_fragments_gt_10cm=N_10cm,
        total_fragments_gt_1cm=N_1cm,
        debris_mass_kg=min(total_debris_mass, total_mass),
        mean_debris_lifetime_years=np.mean(lifetimes) if lifetimes else 0,
        max_debris_altitude_km=max(apogees) if apogees else collision_alt,
        min_debris_altitude_km=min(perigees) if perigees else 0,
        fragments=fragments
    )

    # Cascade risk: probability that debris hits another object
    # Proportional to fragment count × orbital density × lifetime
    from .conjunction import debris_lifetime as dl_func
    shell_lifetime = dl_func(collision_alt)
    outcome.risk_to_other_spacecraft = N_10cm * shell_lifetime * 1e-6

    return outcome


# ============================================================================
# MITIGATION STRATEGIES
# ============================================================================


def strategy_reduce_relative_velocity(sc1: Spacecraft, sc2: Spacecraft,
                                       conjunction: Conjunction) -> MitigationStrategy:
    """
    Strategy: Use remaining Δv to reduce relative velocity at impact.

    Physics: Fragment count scales as v_rel^0.5 (non-catastrophic) or
    is dominated by mass (catastrophic). Reducing v_rel below the
    catastrophic threshold (40 kJ/kg) dramatically reduces debris.

    The optimal direction is anti-parallel to relative velocity.
    """
    v_rel = conjunction.relative_velocity  # km/s
    mass1, mass2 = sc1.mass, sc2.mass

    # How much Δv needed to go below catastrophic threshold?
    m_proj = min(mass1, mass2)
    m_targ = max(mass1, mass2)

    # E = 0.5 * m_proj * v² / m_targ < 40000
    # v_threshold = sqrt(2 * 40000 * m_targ / m_proj) in m/s
    v_threshold_ms = np.sqrt(2 * CATASTROPHIC_ENERGY * m_targ / m_proj)
    v_threshold_kms = v_threshold_ms / 1000.0

    # Δv needed to reduce to threshold
    dv_to_threshold_kms = max(0, v_rel - v_threshold_kms)
    dv_to_threshold_ms = dv_to_threshold_kms * 1000.0

    # Available Δv
    dv_available = sc1.delta_v_budget - sc1.delta_v_used
    if sc2.maneuverable:
        dv_available += sc2.delta_v_budget - sc2.delta_v_used

    # Effectiveness: what fraction of v_rel can we cancel?
    v_reduction_achievable = min(dv_available / 1000.0, v_rel * 0.5)  # Can't do more than 50%
    new_v_rel = v_rel - v_reduction_achievable

    # Predict outcome with reduced velocity
    # N ∝ v^0.5 for non-catastrophic
    original_N = fragment_count(mass1, mass2, v_rel)
    reduced_N = fragment_count(mass1, mass2, max(0.1, new_v_rel))

    reduction_factor = 1.0 - (reduced_N / max(original_N, 1))

    strategy = MitigationStrategy(
        name="Reduce Relative Velocity",
        description=(
            f"Use Δv to reduce impact speed from {v_rel:.2f} km/s to {new_v_rel:.2f} km/s. "
            f"Reduces fragment count by {reduction_factor*100:.0f}%. "
            f"{'Crosses below catastrophic threshold!' if new_v_rel < v_threshold_kms and v_rel > v_threshold_kms else ''}"
        ),
        required_delta_v_ms=v_reduction_achievable * 1000.0,
        time_required_s=300.0,  # Need at least 5 min for maneuver execution
        effectiveness_score=reduction_factor,
        feasibility_score=min(1.0, dv_available / (dv_to_threshold_ms + 1))
    )

    return strategy


def strategy_glancing_impact(sc1: Spacecraft, sc2: Spacecraft,
                              conjunction: Conjunction) -> MitigationStrategy:
    """
    Strategy: Adjust trajectory for glancing rather than head-on impact.

    Physics: Effective collision energy depends on the component of relative
    velocity along the line connecting the centers at impact.
    A glancing blow (large impact parameter) has lower effective v_rel:
        v_effective = v_rel · sin(θ)
    where θ is the angle between relative velocity and miss vector.

    Minimal Δv needed — just enough to shift impact parameter.
    """
    v_rel = conjunction.relative_velocity
    miss = conjunction.miss_distance

    # For a glancing impact, we want the approach to be nearly tangential
    # to the combined collision sphere
    r1 = np.sqrt(sc1.area / np.pi) / 1000.0  # km
    r2 = np.sqrt(sc2.area / np.pi) / 1000.0  # km
    R_combined = r1 + r2

    # Ideal: impact parameter b ≈ R_combined (just barely touching)
    # sin(θ) = b / R_combined for b < R_combined
    # If we can make θ small, effective energy drops significantly
    # Even going from head-on (θ=90°) to glancing (θ=20°) reduces energy by ~88%

    # Δv needed: small cross-track impulse to shift impact parameter
    # Δb ≈ Δv_crosstrack × time_to_impact / v_rel (simplified)
    # We need Δb ≈ R_combined × cos(target_angle)
    target_angle_deg = 15.0  # degrees — very glancing
    target_angle = np.radians(target_angle_deg)

    # Estimate Δv needed (very rough — actual depends on geometry)
    # Typically a few cm/s is sufficient for LEO conjunctions
    dv_needed_ms = 0.5  # Conservative estimate: 0.5 m/s

    # Effectiveness: sin(θ) reduction in effective collision energy
    # E_effective = E * sin²(θ)
    sin_theta = np.sin(target_angle)
    energy_reduction = 1.0 - sin_theta**2  # Fraction of energy avoided

    # Fragment reduction
    original_N = fragment_count(sc1.mass, sc2.mass, v_rel)
    effective_v = v_rel * sin_theta
    reduced_N = fragment_count(sc1.mass, sc2.mass, max(0.1, effective_v))
    debris_reduction = 1.0 - (reduced_N / max(original_N, 1))

    strategy = MitigationStrategy(
        name="Glancing Impact Geometry",
        description=(
            f"Adjust trajectory for {target_angle_deg:.0f}° glancing impact. "
            f"Effective collision velocity reduced to {effective_v:.2f} km/s. "
            f"Energy reduction: {energy_reduction*100:.0f}%. "
            f"Debris reduction: {debris_reduction*100:.0f}%."
        ),
        required_delta_v_ms=dv_needed_ms,
        time_required_s=600.0,  # Need 10+ min for geometry alignment
        effectiveness_score=debris_reduction,
        feasibility_score=0.8  # Generally achievable with small Δv
    )

    return strategy


def strategy_lower_altitude(sc1: Spacecraft, sc2: Spacecraft,
                             conjunction: Conjunction) -> MitigationStrategy:
    """
    Strategy: Maneuver so collision occurs at lower altitude.

    Physics: Lower altitude → higher atmospheric density → debris reenters faster.
    Below 400 km, most debris clears within months.
    Below 300 km, debris clears within days-weeks.

    Trade-off: Requires Δv and time, but dramatically reduces long-term impact.
    """
    # Current collision altitude
    am1 = sc1.area / sc1.mass
    state1_tca = propagate_state(sc1.state, conjunction.tca, area_mass_ratio=am1)
    current_alt = np.linalg.norm(state1_tca.r) - R_EARTH

    # Target: bring collision down to 350 km (fast decay zone)
    target_alt = min(current_alt, 350.0)
    alt_reduction = current_alt - target_alt

    if alt_reduction < 10:
        # Already low enough
        strategy = MitigationStrategy(
            name="Lower Collision Altitude",
            description=f"Already at {current_alt:.0f} km — low enough for fast debris decay.",
            required_delta_v_ms=0,
            time_required_s=0,
            effectiveness_score=0.5,  # Moderate: already good altitude
            feasibility_score=1.0
        )
        return strategy

    # Δv to lower perigee (Hohmann-like)
    # Δv ≈ v_circ × (1 - sqrt(r_target / r_current)) (first order)
    r_current = R_EARTH + current_alt
    r_target = R_EARTH + target_alt
    v_circ = np.sqrt(MU_EARTH / r_current)  # km/s
    dv_kms = v_circ * (1.0 - np.sqrt(r_target / r_current))
    dv_ms = abs(dv_kms) * 1000.0

    # Effectiveness: ratio of debris lifetimes
    from .conjunction import debris_lifetime
    lifetime_current = debris_lifetime(current_alt)
    lifetime_target = debris_lifetime(target_alt)
    lifetime_reduction = 1.0 - (lifetime_target / max(lifetime_current, 0.01))

    # Time needed: at least one orbital period to execute and take effect
    period = orbital_period(r_current)

    strategy = MitigationStrategy(
        name="Lower Collision Altitude",
        description=(
            f"Lower collision point from {current_alt:.0f} km to {target_alt:.0f} km. "
            f"Debris lifetime reduced from {lifetime_current:.1f} to {lifetime_target:.1f} years "
            f"({lifetime_reduction*100:.0f}% reduction). "
            f"Requires {dv_ms:.1f} m/s retrograde burn."
        ),
        required_delta_v_ms=dv_ms,
        time_required_s=period,
        effectiveness_score=lifetime_reduction,
        feasibility_score=min(1.0, (sc1.delta_v_budget - sc1.delta_v_used) / max(dv_ms, 0.1))
    )

    return strategy


def strategy_minimum_cross_section(sc1: Spacecraft, sc2: Spacecraft,
                                    conjunction: Conjunction) -> MitigationStrategy:
    """
    Strategy: Orient spacecraft to present minimum cross-section to impact.

    Physics: Reduces both probability of actual hit AND damage if hit occurs.
    Most spacecraft are elongated — presenting the narrow edge reduces
    effective area by 5-10x typically.

    This is a "free" strategy (no Δv needed, just attitude control).
    """
    # Assume spacecraft can reduce cross-section by factor of 5 via attitude
    area_reduction_factor = 5.0
    min_area = sc1.area / area_reduction_factor

    # Effect on collision probability
    # Pc ∝ R² ∝ Area → Pc_new = Pc / area_reduction_factor
    pc_reduction = 1.0 - 1.0 / area_reduction_factor

    # Effect on damage (smaller intercept area → less material involved)
    damage_reduction = 1.0 - 1.0 / np.sqrt(area_reduction_factor)

    strategy = MitigationStrategy(
        name="Minimum Cross-Section Attitude",
        description=(
            f"Orient to present minimum area ({min_area:.2f} m² vs {sc1.area:.2f} m²). "
            f"Collision probability reduced by {pc_reduction*100:.0f}%. "
            f"Damage reduced by {damage_reduction*100:.0f}% if hit occurs. "
            f"No Δv required — attitude control only."
        ),
        required_delta_v_ms=0.0,
        time_required_s=60.0,  # 1 minute for attitude slew
        effectiveness_score=damage_reduction,
        feasibility_score=1.0  # Always feasible if spacecraft has attitude control
    )

    return strategy


def strategy_controlled_deorbit(sc1: Spacecraft, sc2: Spacecraft,
                                 conjunction: Conjunction) -> MitigationStrategy:
    """
    Strategy: Deorbit the spacecraft entirely before collision.

    Last resort: sacrifice the spacecraft to prevent debris generation.
    Only viable if enough Δv and time to deorbit completely.
    """
    # Δv to deorbit (lower perigee to ~80 km for guaranteed reentry)
    am1 = sc1.area / sc1.mass
    state = propagate_state(sc1.state, 0, area_mass_ratio=am1)
    coe = state_to_coe(state)

    r_current = coe.a
    r_target_perigee = R_EARTH + 80.0  # km — guaranteed reentry

    # Deorbit Δv (at apogee, lower perigee)
    # Δv = v_current - v_transfer_at_apogee
    v_current = np.sqrt(MU_EARTH / r_current)  # Circular approximation
    a_transfer = (r_current + r_target_perigee) / 2.0
    v_transfer = np.sqrt(MU_EARTH * (2.0 / r_current - 1.0 / a_transfer))
    dv_kms = abs(v_current - v_transfer)
    dv_ms = dv_kms * 1000.0

    available = sc1.delta_v_budget - sc1.delta_v_used
    feasible = available >= dv_ms

    # Time needed: at least half an orbit to execute
    period = orbital_period(r_current)
    time_needed = period * 0.75  # Need time to reach optimal burn point

    strategy = MitigationStrategy(
        name="Controlled Deorbit",
        description=(
            f"Deorbit spacecraft before collision. "
            f"Requires {dv_ms:.1f} m/s (available: {available:.1f} m/s). "
            f"{'FEASIBLE' if feasible else 'INFEASIBLE — insufficient fuel'}. "
            f"Eliminates collision entirely but sacrifices spacecraft."
        ),
        required_delta_v_ms=dv_ms,
        time_required_s=time_needed,
        effectiveness_score=1.0 if feasible else 0.0,
        feasibility_score=1.0 if feasible else 0.0
    )

    return strategy


# ============================================================================
# STRATEGY EVALUATION AND RANKING
# ============================================================================


def evaluate_all_strategies(sc1: Spacecraft, sc2: Spacecraft,
                             conjunction: Conjunction,
                             time_available: float = 3600.0
                             ) -> List[MitigationStrategy]:
    """
    Evaluate all damage mitigation strategies and rank them.

    Parameters
    ----------
    sc1, sc2 : Spacecraft
        The colliding objects
    conjunction : Conjunction
        Conjunction details
    time_available : float
        Time remaining before collision [seconds]

    Returns
    -------
    list of MitigationStrategy
        All strategies, sorted by combined score (effectiveness × feasibility)
    """
    strategies = []

    # Generate all strategies
    strategies.append(strategy_minimum_cross_section(sc1, sc2, conjunction))
    strategies.append(strategy_glancing_impact(sc1, sc2, conjunction))
    strategies.append(strategy_reduce_relative_velocity(sc1, sc2, conjunction))
    strategies.append(strategy_lower_altitude(sc1, sc2, conjunction))
    strategies.append(strategy_controlled_deorbit(sc1, sc2, conjunction))

    # Filter by time feasibility
    for s in strategies:
        if s.time_required_s > time_available:
            s.feasibility_score *= 0.1  # Heavily penalize if not enough time

    # Filter by fuel feasibility
    available_dv = sc1.delta_v_budget - sc1.delta_v_used
    for s in strategies:
        if s.required_delta_v_ms > available_dv:
            s.feasibility_score *= (available_dv / max(s.required_delta_v_ms, 0.1))

    # Sort by combined score
    strategies.sort(
        key=lambda s: s.effectiveness_score * s.feasibility_score,
        reverse=True
    )

    return strategies


def recommend_mitigation(sc1: Spacecraft, sc2: Spacecraft,
                          conjunction: Conjunction,
                          time_available: float = 3600.0) -> Tuple[MitigationStrategy, CollisionOutcome]:
    """
    Top-level recommendation: best mitigation strategy + predicted outcome.

    Parameters
    ----------
    sc1, sc2 : Spacecraft
        Colliding objects
    conjunction : Conjunction
        Conjunction details
    time_available : float
        Time remaining [seconds]

    Returns
    -------
    best_strategy : MitigationStrategy
        Recommended strategy
    baseline_outcome : CollisionOutcome
        What happens with NO mitigation (baseline for comparison)
    """
    # Baseline: what happens if we do nothing
    baseline_outcome = predict_collision_outcome(sc1, sc2, conjunction)

    # Evaluate strategies
    strategies = evaluate_all_strategies(sc1, sc2, conjunction, time_available)

    # Best strategy
    best = strategies[0] if strategies else MitigationStrategy(
        name="No Mitigation Available",
        description="No feasible mitigation strategies available.",
        required_delta_v_ms=0, time_required_s=0,
        effectiveness_score=0, feasibility_score=0
    )

    return best, baseline_outcome


# ============================================================================
# COMBINED STRATEGY EXECUTION
# ============================================================================


def execute_mitigation_plan(sc1: Spacecraft, sc2: Spacecraft,
                             conjunction: Conjunction,
                             time_available: float = 3600.0
                             ) -> Tuple[List[MitigationStrategy], CollisionOutcome, CollisionOutcome]:
    """
    Execute a combined mitigation plan using multiple compatible strategies.

    Strategies can be combined (e.g., minimum cross-section + glancing + lower altitude)
    for maximum damage reduction.

    Parameters
    ----------
    sc1, sc2 : Spacecraft
        Colliding objects
    conjunction : Conjunction
        Conjunction event
    time_available : float
        Time budget [seconds]

    Returns
    -------
    selected_strategies : list of MitigationStrategy
        Strategies to execute (in order)
    baseline_outcome : CollisionOutcome
        Unmitigated outcome
    mitigated_outcome : CollisionOutcome
        Estimated outcome with mitigation
    """
    baseline = predict_collision_outcome(sc1, sc2, conjunction)
    strategies = evaluate_all_strategies(sc1, sc2, conjunction, time_available)

    # Select compatible strategies (greedy by score, check fuel/time budget)
    selected = []
    remaining_dv = sc1.delta_v_budget - sc1.delta_v_used
    remaining_time = time_available

    for s in strategies:
        if s.required_delta_v_ms <= remaining_dv and s.time_required_s <= remaining_time:
            if s.effectiveness_score * s.feasibility_score > 0.05:  # Minimum threshold
                selected.append(s)
                remaining_dv -= s.required_delta_v_ms
                remaining_time -= s.time_required_s

    # Estimate combined effectiveness
    # Conservative: multiply individual reduction factors
    combined_reduction = 1.0
    for s in selected:
        combined_reduction *= (1.0 - s.effectiveness_score * s.feasibility_score)

    # Mitigated outcome estimate
    mitigated = CollisionOutcome(
        is_catastrophic=baseline.is_catastrophic and combined_reduction > 0.5,
        specific_energy_j_per_kg=baseline.specific_energy_j_per_kg * combined_reduction,
        total_fragments_gt_10cm=int(baseline.total_fragments_gt_10cm * combined_reduction),
        total_fragments_gt_1cm=int(baseline.total_fragments_gt_1cm * combined_reduction),
        debris_mass_kg=baseline.debris_mass_kg * combined_reduction,
        mean_debris_lifetime_years=baseline.mean_debris_lifetime_years * combined_reduction,
        max_debris_altitude_km=baseline.max_debris_altitude_km,
        min_debris_altitude_km=baseline.min_debris_altitude_km,
        risk_to_other_spacecraft=baseline.risk_to_other_spacecraft * combined_reduction
    )

    return selected, baseline, mitigated
