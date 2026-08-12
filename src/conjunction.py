"""
Conjunction Assessment Module
=============================

Implements:
- All-vs-all conjunction screening (with smart filters to reduce O(N²))
- Time of Closest Approach (TCA) finding
- Miss distance calculation
- Probability of Collision (Pc) computation via covariance projection
- Encounter plane geometry
- Risk scoring with cascade awareness
"""

import numpy as np
from scipy.optimize import brentq, minimize_scalar
from scipy.special import factorial
from typing import List, Tuple, Optional

from .utils import (
    MU_EARTH, R_EARTH,
    StateVector, Spacecraft, Conjunction, OrbitalElements,
    state_to_coe, eci_to_rtn
)
from .orbital_mechanics import (
    propagate_state, generate_ephemeris, propagate_with_stm
)


# ============================================================================
# CONJUNCTION SCREENING (Reducing O(N²))
# ============================================================================


def apogee_perigee_filter(sc1: Spacecraft, sc2: Spacecraft,
                          threshold_km: float = 50.0) -> bool:
    """
    Quick geometric filter: objects can only meet if their orbital shells overlap.

    If perigee of one > apogee of other + threshold, no conjunction possible.

    Parameters
    ----------
    sc1, sc2 : Spacecraft
        Two spacecraft to check
    threshold_km : float
        Additional margin [km]

    Returns
    -------
    bool
        True if conjunction is geometrically possible
    """
    coe1 = state_to_coe(sc1.state)
    coe2 = state_to_coe(sc2.state)

    # Apogee and perigee radii
    apo1 = coe1.a * (1 + coe1.e)
    per1 = coe1.a * (1 - coe1.e)
    apo2 = coe2.a * (1 + coe2.e)
    per2 = coe2.a * (1 - coe2.e)

    # Check if shells overlap
    if per1 > apo2 + threshold_km:
        return False
    if per2 > apo1 + threshold_km:
        return False

    return True


def coplanar_filter(sc1: Spacecraft, sc2: Spacecraft,
                    max_relative_inclination_deg: float = 5.0) -> bool:
    """
    Filter based on relative orbital plane geometry.

    Objects in very different planes with non-intersecting altitude bands
    are unlikely to have close approaches.

    Parameters
    ----------
    sc1, sc2 : Spacecraft
        Two spacecraft
    max_relative_inclination_deg : float
        Maximum relative inclination for filtering

    Returns
    -------
    bool
        True if conjunction possible (not filtered out)
    """
    coe1 = state_to_coe(sc1.state)
    coe2 = state_to_coe(sc2.state)

    # Relative inclination (approximate)
    # cos(i_rel) = cos(i1)cos(i2) + sin(i1)sin(i2)cos(ΔΩ)
    delta_raan = coe2.raan - coe1.raan
    cos_i_rel = (np.cos(coe1.i) * np.cos(coe2.i) +
                 np.sin(coe1.i) * np.sin(coe2.i) * np.cos(delta_raan))
    cos_i_rel = np.clip(cos_i_rel, -1, 1)
    i_rel = np.arccos(cos_i_rel)

    # If relative inclination is very small AND orbits don't overlap radially,
    # conjunction is unlikely (parallel orbits at different altitudes)
    if np.degrees(i_rel) < 0.1:
        coe1_alt = coe1.a - R_EARTH
        coe2_alt = coe2.a - R_EARTH
        if abs(coe1_alt - coe2_alt) > 50:  # More than 50 km apart
            return False

    return True


def screen_conjunctions(spacecraft_list: List[Spacecraft],
                        time_window: float = 86400.0,
                        distance_threshold: float = 5.0,
                        time_steps: int = 100) -> List[Tuple[int, int, float, float]]:
    """
    Screen all spacecraft pairs for potential conjunctions.

    Uses progressive filtering:
    1. Apogee-perigee filter (geometric)
    2. Coarse ephemeris screening
    3. Refined TCA determination for flagged pairs

    Parameters
    ----------
    spacecraft_list : list of Spacecraft
        All tracked objects
    time_window : float
        Screening window [seconds] (default: 1 day)
    distance_threshold : float
        Flagging threshold [km]
    time_steps : int
        Number of ephemeris points for coarse screening

    Returns
    -------
    list of tuples
        (idx1, idx2, tca, min_distance) for each flagged pair
    """
    N = len(spacecraft_list)
    flagged = []

    # Generate coarse ephemerides for all objects
    times = np.linspace(0, time_window, time_steps)
    ephemerides = []

    for sc in spacecraft_list:
        try:
            eph = generate_ephemeris(
                sc.state, times,
                cd=sc.cd, cr=sc.cr,
                area_mass_ratio=sc.area / sc.mass
            )
            ephemerides.append(eph)
        except RuntimeError:
            # Propagation failed — skip this object
            ephemerides.append(None)

    # All-vs-all screening with filters
    for i in range(N):
        if ephemerides[i] is None:
            continue

        for j in range(i + 1, N):
            if ephemerides[j] is None:
                continue

            # Filter 1: Apogee-perigee
            if not apogee_perigee_filter(spacecraft_list[i], spacecraft_list[j]):
                continue

            # Filter 2: Coplanar check
            if not coplanar_filter(spacecraft_list[i], spacecraft_list[j]):
                continue

            # Filter 3: Coarse distance check along ephemeris
            positions_i = ephemerides[i][:, :3]
            positions_j = ephemerides[j][:, :3]
            distances = np.linalg.norm(positions_i - positions_j, axis=1)

            min_dist_idx = np.argmin(distances)
            min_dist = distances[min_dist_idx]

            if min_dist < distance_threshold:
                # Refine TCA
                tca_approx = times[min_dist_idx]
                flagged.append((i, j, tca_approx, min_dist))

    return flagged


# ============================================================================
# TIME OF CLOSEST APPROACH (TCA) REFINEMENT
# ============================================================================


def find_tca(state1: StateVector, state2: StateVector,
             t_guess: float, search_window: float = 600.0,
             cd1: float = 2.2, cd2: float = 2.2,
             am1: float = 0.01, am2: float = 0.01) -> Tuple[float, float]:
    """
    Refine the Time of Closest Approach between two objects.

    Minimizes |r1(t) - r2(t)| around an initial guess.

    Parameters
    ----------
    state1, state2 : StateVector
        Initial states of both objects (at t=0)
    t_guess : float
        Approximate TCA from coarse screening [seconds]
    search_window : float
        Window around guess to search [seconds]

    Returns
    -------
    tca : float
        Refined time of closest approach [seconds]
    miss_distance : float
        Minimum distance [km]
    """
    def distance_at_time(t):
        """Compute distance between objects at time t."""
        s1 = propagate_state(state1, t, cd=cd1, area_mass_ratio=am1, max_step=30.0)
        s2 = propagate_state(state2, t, cd=cd2, area_mass_ratio=am2, max_step=30.0)
        return np.linalg.norm(s1.r - s2.r)

    # Search around the guess
    t_min = max(0, t_guess - search_window)
    t_max = t_guess + search_window

    result = minimize_scalar(
        distance_at_time,
        bounds=(t_min, t_max),
        method='bounded',
        options={'xatol': 0.1}  # 0.1 second precision
    )

    return result.x, result.fun


def find_all_close_approaches(state1: StateVector, state2: StateVector,
                               time_window: float = 86400.0,
                               threshold_km: float = 10.0,
                               n_samples: int = 500) -> List[Tuple[float, float]]:
    """
    Find all close approaches between two objects within a time window.

    Objects in LEO can have multiple close approaches per day (every orbit crossing).

    Parameters
    ----------
    state1, state2 : StateVector
        Initial states
    time_window : float
        Search window [seconds]
    threshold_km : float
        Distance threshold for flagging [km]
    n_samples : int
        Number of sample points for initial scan

    Returns
    -------
    list of (tca, miss_distance)
        All close approaches found
    """
    times = np.linspace(0, time_window, n_samples)

    # Generate ephemerides
    eph1 = generate_ephemeris(state1, times)
    eph2 = generate_ephemeris(state2, times)

    distances = np.linalg.norm(eph1[:, :3] - eph2[:, :3], axis=1)

    # Find local minima below threshold
    approaches = []
    for idx in range(1, len(distances) - 1):
        if (distances[idx] < distances[idx - 1] and
            distances[idx] < distances[idx + 1] and
            distances[idx] < threshold_km):
            # Refine this close approach
            tca, miss = find_tca(state1, state2, times[idx],
                                 search_window=times[1] - times[0])
            approaches.append((tca, miss))

    return approaches


# ============================================================================
# ENCOUNTER PLANE GEOMETRY
# ============================================================================


def compute_encounter_plane(state1_tca: StateVector,
                            state2_tca: StateVector) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
    """
    Compute the encounter plane basis vectors and miss vector.

    The encounter plane is perpendicular to the relative velocity at TCA.
    All Pc calculations happen in this 2D plane.

    Parameters
    ----------
    state1_tca, state2_tca : StateVector
        States of both objects at TCA

    Returns
    -------
    miss_vector_2d : ndarray (2,)
        Miss vector projected into encounter plane [km]
    basis : ndarray (3, 3)
        Encounter frame basis vectors [along_track, cross_track, relative_vel]
    projection_matrix : ndarray (2, 3)
        Matrix to project 3D vectors into encounter plane
    """
    # Relative state
    delta_r = state1_tca.r - state2_tca.r  # Miss vector (3D)
    delta_v = state1_tca.v - state2_tca.v  # Relative velocity

    v_rel_mag = np.linalg.norm(delta_v)

    # Encounter plane normal = relative velocity direction
    z_hat = delta_v / v_rel_mag

    # Choose basis vectors in the encounter plane
    # x_hat: component of miss vector in the plane
    delta_r_proj = delta_r - np.dot(delta_r, z_hat) * z_hat
    proj_mag = np.linalg.norm(delta_r_proj)

    if proj_mag > 1e-10:
        x_hat = delta_r_proj / proj_mag
    else:
        # Miss vector is along relative velocity — choose arbitrary perpendicular
        arbitrary = np.array([1, 0, 0]) if abs(z_hat[0]) < 0.9 else np.array([0, 1, 0])
        x_hat = np.cross(z_hat, arbitrary)
        x_hat /= np.linalg.norm(x_hat)

    y_hat = np.cross(z_hat, x_hat)

    # Basis matrix (rows are basis vectors)
    basis = np.array([x_hat, y_hat, z_hat])

    # Projection matrix (3D → 2D encounter plane)
    projection_matrix = np.array([x_hat, y_hat])  # (2, 3)

    # Miss vector in 2D encounter plane
    miss_vector_2d = projection_matrix @ delta_r

    return miss_vector_2d, basis, projection_matrix


def project_covariance_to_encounter_plane(
        cov1: np.ndarray, cov2: np.ndarray,
        projection_matrix: np.ndarray) -> np.ndarray:
    """
    Project combined position covariance into the 2D encounter plane.

    C_2D = P · (C1_pos + C2_pos) · Pᵀ

    Parameters
    ----------
    cov1, cov2 : ndarray (6, 6)
        Full state covariances of both objects
    projection_matrix : ndarray (2, 3)
        Projection from 3D to encounter plane

    Returns
    -------
    ndarray (2, 2)
        Combined covariance in the encounter plane
    """
    # Extract position covariances (upper-left 3x3 blocks)
    pos_cov1 = cov1[:3, :3]
    pos_cov2 = cov2[:3, :3]

    # Combined (assuming independent errors)
    combined_pos_cov = pos_cov1 + pos_cov2

    # Project to 2D
    cov_2d = projection_matrix @ combined_pos_cov @ projection_matrix.T

    return cov_2d


# ============================================================================
# PROBABILITY OF COLLISION (Pc)
# ============================================================================


def probability_of_collision_2d(miss_vector: np.ndarray,
                                 covariance_2d: np.ndarray,
                                 combined_radius: float) -> float:
    """
    Compute probability of collision using 2D Gaussian integral over hard-body disk.

    This is the standard Alfriend/Akella formulation:

    Pc = (1/2π|C|^½) ∫∫_A exp(-½ xᵀ C⁻¹ x) dx dy

    where A is a circle of radius R centered at the miss vector.

    Uses numerical integration via eigendecomposition for efficiency.

    Parameters
    ----------
    miss_vector : ndarray (2,)
        Miss vector in encounter plane [km]
    covariance_2d : ndarray (2, 2)
        Combined position covariance in encounter plane [km²]
    combined_radius : float
        Sum of effective radii of both objects [km]

    Returns
    -------
    float
        Probability of collision (0 to 1)
    """
    # Eigendecomposition of covariance
    eigenvalues, eigenvectors = np.linalg.eigh(covariance_2d)

    # Ensure positive definite
    if np.any(eigenvalues <= 0):
        eigenvalues = np.maximum(eigenvalues, 1e-10)

    sigma_x = np.sqrt(eigenvalues[0])
    sigma_y = np.sqrt(eigenvalues[1])

    # Transform miss vector to principal axes
    miss_rotated = eigenvectors.T @ miss_vector
    xm = miss_rotated[0]
    ym = miss_rotated[1]

    # Numerical integration using polar coordinates
    # Pc = ∫₀²π ∫₀ᴿ (1/(2π·σx·σy)) exp(-½[(x-xm)²/σx² + (y-ym)²/σy²]) r dr dθ
    n_r = 50
    n_theta = 100

    R = combined_radius
    r_vals = np.linspace(0, R, n_r)
    theta_vals = np.linspace(0, 2 * np.pi, n_theta)

    dr = r_vals[1] - r_vals[0] if n_r > 1 else R
    dtheta = theta_vals[1] - theta_vals[0]

    Pc = 0.0
    for r in r_vals[1:]:  # Skip r=0
        for theta in theta_vals[:-1]:
            x = r * np.cos(theta)
            y = r * np.sin(theta)

            exp_term = -0.5 * ((x - xm)**2 / eigenvalues[0] +
                               (y - ym)**2 / eigenvalues[1])
            if exp_term > -50:  # Avoid underflow
                Pc += r * np.exp(exp_term) * dr * dtheta

    Pc /= (2 * np.pi * sigma_x * sigma_y)

    return np.clip(Pc, 0.0, 1.0)


def probability_of_collision_chan(miss_distance: float,
                                  covariance_2d: np.ndarray,
                                  combined_radius: float,
                                  n_terms: int = 20) -> float:
    """
    Chan's series approximation for Pc (faster than full numerical integration).

    Assumes circular combined hard body cross-section.
    Accurate when miss distance is not too large relative to covariance.

    Parameters
    ----------
    miss_distance : float
        Scalar miss distance in encounter plane [km]
    covariance_2d : ndarray (2, 2)
        Combined covariance [km²]
    combined_radius : float
        Combined object radius [km]
    n_terms : int
        Number of series terms

    Returns
    -------
    float
        Probability of collision
    """
    det_C = np.linalg.det(covariance_2d)

    if det_C <= 0:
        return 0.0

    # Normalized radius squared
    u = combined_radius**2 / (2 * np.sqrt(det_C))

    # Normalized miss distance squared
    eigenvalues = np.linalg.eigvalsh(covariance_2d)
    sigma_max = np.sqrt(max(eigenvalues))
    sigma_min = np.sqrt(min(eigenvalues))

    # Mahalanobis-like distance
    try:
        C_inv = np.linalg.inv(covariance_2d)
    except np.linalg.LinAlgError:
        return 0.0

    miss_vec = np.array([miss_distance, 0])  # Assume along one axis for simplification
    v = 0.5 * miss_vec @ C_inv @ miss_vec

    # Chan's series: Pc = exp(-v) * Σ (v^k / k!) * (1 - exp(-u) * Σ (u^j / j!))
    # Simplified form for computational stability
    Pc = 0.0
    exp_neg_v = np.exp(-v) if v < 500 else 0.0

    for k in range(n_terms):
        poisson_term = exp_neg_v * v**k / factorial(k, exact=False)

        # Incomplete gamma function approximation
        incomplete_sum = 0.0
        exp_neg_u = np.exp(-u) if u < 500 else 0.0
        for j in range(k + 1):
            incomplete_sum += u**j / factorial(j, exact=False)

        cdf_term = 1.0 - exp_neg_u * incomplete_sum
        Pc += poisson_term * cdf_term

    # Alternative: simple upper bound (Foster's method)
    # Pc_upper = R² / (2 * sqrt(det_C)) * exp(-miss_distance² / (2 * trace(C)))
    # Use as sanity check
    trace_C = np.trace(covariance_2d)
    if trace_C > 0:
        Pc_foster = (combined_radius**2 / (2 * np.sqrt(det_C)) *
                     np.exp(-miss_distance**2 / (2 * trace_C)))
    else:
        Pc_foster = 0.0

    # Return the more conservative estimate
    return np.clip(max(Pc, Pc_foster * 0.5), 0.0, 1.0)


def compute_collision_probability(sc1: Spacecraft, sc2: Spacecraft,
                                   tca: float) -> Tuple[float, np.ndarray]:
    """
    Full Pc computation pipeline for a conjunction.

    1. Propagate both objects to TCA (with covariance)
    2. Compute encounter plane
    3. Project covariance into encounter plane
    4. Integrate Pc over hard-body disk

    Parameters
    ----------
    sc1, sc2 : Spacecraft
        The two objects in conjunction
    tca : float
        Time of closest approach [seconds from epoch]

    Returns
    -------
    Pc : float
        Probability of collision
    cov_2d : ndarray (2, 2)
        Combined covariance in encounter plane [km²]
    """
    # Propagate both to TCA
    am1 = sc1.area / sc1.mass
    am2 = sc2.area / sc2.mass

    state1_tca, stm1 = propagate_with_stm(sc1.state, tca, area_mass_ratio=am1)
    state2_tca, stm2 = propagate_with_stm(sc2.state, tca, area_mass_ratio=am2)

    # Propagate covariances
    from .orbital_mechanics import propagate_covariance
    cov1_tca = propagate_covariance(sc1.covariance, stm1)
    cov2_tca = propagate_covariance(sc2.covariance, stm2)

    # Encounter plane geometry
    miss_2d, basis, proj_matrix = compute_encounter_plane(state1_tca, state2_tca)

    # Project covariance
    cov_2d = project_covariance_to_encounter_plane(cov1_tca, cov2_tca, proj_matrix)

    # Combined hard-body radius (approximate from cross-sectional area)
    # R = sqrt(A/π)
    r1 = np.sqrt(sc1.area / np.pi) / 1000.0  # m → km
    r2 = np.sqrt(sc2.area / np.pi) / 1000.0  # m → km
    combined_radius = r1 + r2

    # Compute Pc
    Pc = probability_of_collision_2d(miss_2d, cov_2d, combined_radius)

    return Pc, cov_2d


# ============================================================================
# RISK SCORING
# ============================================================================


def estimate_debris_count(mass1: float, mass2: float,
                          relative_velocity: float) -> float:
    """
    Estimate number of trackable debris fragments using NASA breakup model.

    Parameters
    ----------
    mass1, mass2 : float
        Masses of the two objects [kg]
    relative_velocity : float
        Relative velocity at collision [km/s]

    Returns
    -------
    float
        Expected number of fragments > 10 cm
    """
    from .utils import CATASTROPHIC_ENERGY

    v_rel_ms = relative_velocity * 1000.0  # km/s → m/s
    m_target = max(mass1, mass2)
    m_projectile = min(mass1, mass2)

    # Specific energy
    E_specific = 0.5 * m_projectile * v_rel_ms**2 / m_target  # J/kg

    # Fragment count (Lc = 0.1 m = 10 cm)
    Lc = 0.1  # meters

    if E_specific >= CATASTROPHIC_ENERGY:
        # Catastrophic: complete fragmentation
        M_total = mass1 + mass2
        N_fragments = 0.1 * M_total**0.75 * Lc**(-1.71)
    else:
        # Non-catastrophic: cratering
        N_fragments = 0.1 * m_projectile**0.75 * (v_rel_ms / 1000.0)**0.5 * Lc**(-1.71)

    return N_fragments


def debris_lifetime(altitude_km: float) -> float:
    """
    Estimate orbital lifetime of debris at given altitude [years].

    Based on empirical models of atmospheric drag decay.

    Parameters
    ----------
    altitude_km : float
        Altitude [km]

    Returns
    -------
    float
        Estimated orbital lifetime [years]
    """
    if altitude_km < 200:
        return 0.01  # Days
    elif altitude_km < 400:
        return 1.0  # ~1 year
    elif altitude_km < 600:
        return 25.0
    elif altitude_km < 800:
        return 200.0
    elif altitude_km < 1000:
        return 1000.0
    else:
        return 10000.0  # Effectively permanent


def compute_risk_score(conjunction: Conjunction,
                       mass1: float, mass2: float,
                       altitude_km: float,
                       orbital_density: float = 1.0) -> float:
    """
    Compute composite risk score for a conjunction.

    Risk = Pc × Consequence × Cascade_factor

    Parameters
    ----------
    conjunction : Conjunction
        The conjunction event
    mass1, mass2 : float
        Object masses [kg]
    altitude_km : float
        Altitude of conjunction [km]
    orbital_density : float
        Relative density of objects in this orbital shell (1.0 = average)

    Returns
    -------
    float
        Risk score (higher = more dangerous)
    """
    Pc = conjunction.probability_of_collision
    v_rel = conjunction.relative_velocity

    # Consequence: expected debris if collision occurs
    debris = estimate_debris_count(mass1, mass2, v_rel)

    # Cascade factor: debris in crowded, long-lived shells is worse
    lifetime = debris_lifetime(altitude_km)
    cascade_factor = 1.0 + orbital_density * np.log10(max(lifetime, 1.0))

    # Composite risk
    risk = Pc * debris * cascade_factor

    return risk


# ============================================================================
# FULL CONJUNCTION ASSESSMENT PIPELINE
# ============================================================================


def assess_conjunction(sc1: Spacecraft, sc2: Spacecraft,
                       tca: float) -> Conjunction:
    """
    Complete conjunction assessment for a pair of objects.

    Parameters
    ----------
    sc1, sc2 : Spacecraft
        The two objects
    tca : float
        Time of closest approach [seconds]

    Returns
    -------
    Conjunction
        Full assessment with Pc, risk score, etc.
    """
    # Propagate to TCA for miss distance and relative velocity
    am1 = sc1.area / sc1.mass
    am2 = sc2.area / sc2.mass

    state1_tca = propagate_state(sc1.state, tca, area_mass_ratio=am1)
    state2_tca = propagate_state(sc2.state, tca, area_mass_ratio=am2)

    miss_distance = np.linalg.norm(state1_tca.r - state2_tca.r)
    relative_velocity = np.linalg.norm(state1_tca.v - state2_tca.v)

    # Compute Pc
    Pc, cov_2d = compute_collision_probability(sc1, sc2, tca)

    # Altitude at conjunction
    altitude = np.linalg.norm(state1_tca.r) - R_EARTH

    # Build conjunction object
    conj = Conjunction(
        obj1_id=sc1.id,
        obj2_id=sc2.id,
        tca=tca,
        miss_distance=miss_distance,
        relative_velocity=relative_velocity,
        probability_of_collision=Pc,
        combined_covariance_2d=cov_2d
    )

    # Compute risk score
    conj.risk_score = compute_risk_score(conj, sc1.mass, sc2.mass, altitude)

    return conj


def run_conjunction_screening(spacecraft_list: List[Spacecraft],
                               time_window: float = 86400.0,
                               pc_threshold: float = 1e-7) -> List[Conjunction]:
    """
    Full screening pipeline: from list of spacecraft to ranked conjunctions.

    Parameters
    ----------
    spacecraft_list : list of Spacecraft
        All objects to screen
    time_window : float
        Screening window [seconds]
    pc_threshold : float
        Minimum Pc to include in results

    Returns
    -------
    list of Conjunction
        Conjunctions exceeding threshold, sorted by risk score (highest first)
    """
    # Phase 1: Coarse screening
    flagged = screen_conjunctions(spacecraft_list, time_window)

    # Phase 2: Detailed assessment of flagged pairs
    conjunctions = []

    for idx1, idx2, tca_approx, min_dist in flagged:
        sc1 = spacecraft_list[idx1]
        sc2 = spacecraft_list[idx2]

        try:
            # Refine TCA
            tca_refined, miss_refined = find_tca(
                sc1.state, sc2.state, tca_approx,
                am1=sc1.area / sc1.mass,
                am2=sc2.area / sc2.mass
            )

            # Full assessment
            conj = assess_conjunction(sc1, sc2, tca_refined)

            if conj.probability_of_collision >= pc_threshold:
                conjunctions.append(conj)

        except (RuntimeError, np.linalg.LinAlgError):
            # Skip failures — log in production system
            continue

    # Sort by risk score (highest risk first)
    conjunctions.sort(key=lambda c: c.risk_score, reverse=True)

    return conjunctions
