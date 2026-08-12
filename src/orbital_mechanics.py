"""
Orbital Mechanics Core Module
=============================

Implements:
- Two-body orbit propagation (Keplerian + numerical with perturbations)
- J2 oblateness perturbation
- Atmospheric drag model
- Solar radiation pressure
- State Transition Matrix (STM) propagation for covariance evolution
- Kepler's equation solver for analytical propagation
"""

import numpy as np
from scipy.integrate import solve_ivp
from typing import Optional, Tuple

from .utils import (
    MU_EARTH, R_EARTH, J2, OMEGA_EARTH, P_SOLAR,
    StateVector, OrbitalElements, Spacecraft,
    coe_to_state, state_to_coe, orbital_period
)


# ============================================================================
# KEPLER'S EQUATION (Analytical Propagation)
# ============================================================================


def solve_kepler(M: float, e: float, tol: float = 1e-12, max_iter: int = 50) -> float:
    """
    Solve Kepler's equation: M = E - e·sin(E)

    Uses Newton-Raphson iteration.

    Parameters
    ----------
    M : float
        Mean anomaly [rad]
    e : float
        Eccentricity
    tol : float
        Convergence tolerance
    max_iter : int
        Maximum iterations

    Returns
    -------
    E : float
        Eccentric anomaly [rad]
    """
    # Initial guess
    E = M + e * np.sin(M) if e < 0.8 else np.pi

    for _ in range(max_iter):
        f = E - e * np.sin(E) - M
        fp = 1 - e * np.cos(E)
        dE = -f / fp
        E += dE
        if abs(dE) < tol:
            break

    return E


def eccentric_to_true_anomaly(E: float, e: float) -> float:
    """Convert eccentric anomaly to true anomaly."""
    nu = 2 * np.arctan2(
        np.sqrt(1 + e) * np.sin(E / 2),
        np.sqrt(1 - e) * np.cos(E / 2)
    )
    return nu % (2 * np.pi)


def true_to_eccentric_anomaly(nu: float, e: float) -> float:
    """Convert true anomaly to eccentric anomaly."""
    E = 2 * np.arctan2(
        np.sqrt(1 - e) * np.sin(nu / 2),
        np.sqrt(1 + e) * np.cos(nu / 2)
    )
    return E % (2 * np.pi)


def propagate_kepler(elements: OrbitalElements, dt: float) -> OrbitalElements:
    """
    Propagate orbit analytically using Kepler's equation (two-body only).

    Parameters
    ----------
    elements : OrbitalElements
        Initial orbital elements
    dt : float
        Time step [seconds]

    Returns
    -------
    OrbitalElements
        Propagated elements (only true anomaly changes)
    """
    a, e = elements.a, elements.e

    # Mean motion
    n = np.sqrt(MU_EARTH / a**3)

    # Current eccentric anomaly → mean anomaly
    E0 = true_to_eccentric_anomaly(elements.nu, e)
    M0 = E0 - e * np.sin(E0)

    # Propagate mean anomaly
    M = (M0 + n * dt) % (2 * np.pi)

    # Solve Kepler's equation for new eccentric anomaly
    E = solve_kepler(M, e)

    # New true anomaly
    nu_new = eccentric_to_true_anomaly(E, e)

    return OrbitalElements(
        a=elements.a, e=elements.e, i=elements.i,
        raan=elements.raan, omega=elements.omega, nu=nu_new
    )


# ============================================================================
# PERTURBATION MODELS
# ============================================================================


def acceleration_j2(r: np.ndarray) -> np.ndarray:
    """
    J2 oblateness perturbation acceleration.

    a_J2 = -(3/2)·J2·μ·R_E²/r⁵ · [x(1-5z²/r²), y(1-5z²/r²), z(3-5z²/r²)]

    Parameters
    ----------
    r : ndarray (3,)
        Position vector in ECI [km]

    Returns
    -------
    ndarray (3,)
        Acceleration due to J2 [km/s²]
    """
    x, y, z = r
    r_mag = np.linalg.norm(r)
    r2 = r_mag**2
    r5 = r_mag**5

    factor = -1.5 * J2 * MU_EARTH * R_EARTH**2 / r5
    z2_r2 = z**2 / r2

    ax = factor * x * (1 - 5 * z2_r2)
    ay = factor * y * (1 - 5 * z2_r2)
    az = factor * z * (3 - 5 * z2_r2)

    return np.array([ax, ay, az])


def atmospheric_density(altitude_km: float) -> float:
    """
    Exponential atmospheric density model.

    Uses scale heights for different altitude bands.
    Valid for 100-1000 km altitude.

    Parameters
    ----------
    altitude_km : float
        Altitude above Earth surface [km]

    Returns
    -------
    float
        Atmospheric density [kg/m³]
    """
    # Reference densities and scale heights by altitude band
    # (base_alt, base_density, scale_height)
    bands = [
        (100, 5.297e-7, 5.877),
        (150, 2.070e-9, 22.52),
        (200, 2.789e-10, 37.10),
        (250, 7.248e-11, 45.55),
        (300, 2.418e-11, 53.63),
        (350, 9.158e-12, 53.30),
        (400, 3.725e-12, 58.52),
        (450, 1.585e-12, 60.83),
        (500, 6.967e-13, 63.82),
        (600, 1.454e-13, 71.84),
        (700, 3.614e-14, 88.67),
        (800, 1.170e-14, 124.6),
        (900, 5.245e-15, 181.1),
        (1000, 3.019e-15, 268.0),
    ]

    if altitude_km < 100:
        return 1.225  # Sea level approximation
    if altitude_km > 1000:
        return 0.0  # Negligible above 1000 km

    # Find appropriate band
    for idx in range(len(bands) - 1):
        if bands[idx][0] <= altitude_km < bands[idx + 1][0]:
            h0, rho0, H = bands[idx]
            return rho0 * np.exp(-(altitude_km - h0) / H)

    # Last band
    h0, rho0, H = bands[-1]
    return rho0 * np.exp(-(altitude_km - h0) / H)


def acceleration_drag(r: np.ndarray, v: np.ndarray,
                      cd: float, area_mass_ratio: float) -> np.ndarray:
    """
    Atmospheric drag acceleration.

    a_drag = -(1/2) · ρ · Cd · (A/m) · |v_rel| · v_rel

    Parameters
    ----------
    r : ndarray (3,)
        Position in ECI [km]
    v : ndarray (3,)
        Velocity in ECI [km/s]
    cd : float
        Drag coefficient (typically 2.2)
    area_mass_ratio : float
        Area-to-mass ratio [m²/kg]

    Returns
    -------
    ndarray (3,)
        Drag acceleration [km/s²]
    """
    altitude = np.linalg.norm(r) - R_EARTH

    if altitude > 1000 or altitude < 100:
        return np.zeros(3)

    # Velocity relative to atmosphere (co-rotating with Earth)
    omega_vec = np.array([0, 0, OMEGA_EARTH])
    v_atm = np.cross(omega_vec, r)  # Atmosphere velocity at satellite position
    v_rel = v - v_atm  # Relative velocity [km/s]
    v_rel_mag = np.linalg.norm(v_rel)

    # Density [kg/m³] → need to convert acceleration to km/s²
    rho = atmospheric_density(altitude)

    # Factor: (1/2)·ρ·Cd·(A/m) in [kg/m³ · m²/kg] = [1/m]
    # v_rel in km/s, so |v_rel|·v_rel in km²/s²
    # Multiply by 1000 m/km to get consistent units: result in km/s²
    factor = -0.5 * rho * cd * area_mass_ratio * 1000.0  # 1/m · km → 1/km correction

    return factor * v_rel_mag * v_rel


def acceleration_srp(r: np.ndarray, cr: float, area_mass_ratio: float,
                     r_sun: Optional[np.ndarray] = None) -> np.ndarray:
    """
    Solar radiation pressure acceleration.

    a_SRP = -P_SR · Cr · (A/m) · r̂_sun

    Parameters
    ----------
    r : ndarray (3,)
        Satellite position in ECI [km]
    cr : float
        Reflectivity coefficient (1=absorber, 2=perfect reflector)
    area_mass_ratio : float
        Area-to-mass ratio [m²/kg]
    r_sun : ndarray (3,), optional
        Sun position in ECI [km]. If None, assumes sun along +X.

    Returns
    -------
    ndarray (3,)
        SRP acceleration [km/s²]
    """
    if r_sun is None:
        # Default: Sun along +X at 1 AU
        r_sun = np.array([1.496e8, 0, 0])  # km

    # Direction from sun to satellite
    r_sat_sun = r - r_sun
    r_hat = r_sat_sun / np.linalg.norm(r_sat_sun)

    # Check for Earth shadow (simple cylindrical model)
    # Project satellite position onto sun direction
    sun_dir = -r_sun / np.linalg.norm(r_sun)
    proj = np.dot(r, sun_dir)
    if proj < 0:  # Satellite is on the sun-side
        perp_dist = np.linalg.norm(r - proj * sun_dir)
        if perp_dist < R_EARTH:
            return np.zeros(3)  # In shadow

    # P_SR in N/m² = kg/(m·s²)
    # Want acceleration in km/s²
    # a = P_SR · Cr · (A/m) → [kg/(m·s²)] · [m²/kg] = [m/s²] → /1000 = [km/s²]
    factor = -P_SOLAR * cr * area_mass_ratio / 1000.0

    return factor * r_hat


# ============================================================================
# EQUATIONS OF MOTION
# ============================================================================


def equations_of_motion(t: float, state: np.ndarray,
                        cd: float = 2.2,
                        cr: float = 1.5,
                        area_mass_ratio: float = 0.01,
                        include_j2: bool = True,
                        include_drag: bool = True,
                        include_srp: bool = False) -> np.ndarray:
    """
    Full equations of motion for numerical propagation.

    ṙ = v
    v̇ = -μ/r³ · r + perturbations

    Parameters
    ----------
    t : float
        Time (not used directly, needed for integrator interface)
    state : ndarray (6,)
        [x, y, z, vx, vy, vz] in ECI
    cd, cr, area_mass_ratio : float
        Spacecraft physical properties
    include_j2, include_drag, include_srp : bool
        Toggle perturbations

    Returns
    -------
    ndarray (6,)
        State derivative [vx, vy, vz, ax, ay, az]
    """
    r = state[:3]
    v = state[3:]
    r_mag = np.linalg.norm(r)

    # Two-body acceleration
    a_twobody = -MU_EARTH / r_mag**3 * r

    # Perturbations
    a_total = a_twobody

    if include_j2:
        a_total = a_total + acceleration_j2(r)

    if include_drag:
        a_total = a_total + acceleration_drag(r, v, cd, area_mass_ratio)

    if include_srp:
        a_total = a_total + acceleration_srp(r, cr, area_mass_ratio)

    return np.concatenate([v, a_total])


def equations_of_motion_with_stm(t: float, state_and_stm: np.ndarray,
                                  cd: float = 2.2,
                                  cr: float = 1.5,
                                  area_mass_ratio: float = 0.01,
                                  include_j2: bool = True) -> np.ndarray:
    """
    Equations of motion including State Transition Matrix propagation.

    The STM Φ satisfies: Φ̇ = F · Φ, where F = ∂f/∂X is the Jacobian.

    Parameters
    ----------
    t : float
        Time
    state_and_stm : ndarray (42,)
        First 6: state vector, next 36: flattened 6×6 STM

    Returns
    -------
    ndarray (42,)
        Derivatives of state and STM
    """
    state = state_and_stm[:6]
    stm = state_and_stm[6:].reshape(6, 6)

    r = state[:3]
    v = state[3:]
    r_mag = np.linalg.norm(r)

    # State derivative
    state_dot = equations_of_motion(t, state, cd, cr, area_mass_ratio, include_j2,
                                     include_drag=False, include_srp=False)

    # Jacobian of the dynamics (F matrix)
    # F = [[0₃ₓ₃,  I₃ₓ₃],
    #      [G,      0₃ₓ₃]]
    # where G = ∂a/∂r (gravity gradient tensor)

    # Two-body gravity gradient
    r2 = r_mag**2
    r5 = r_mag**5
    G = -MU_EARTH / r_mag**3 * np.eye(3) + 3 * MU_EARTH / r5 * np.outer(r, r)

    # J2 contribution to gravity gradient
    if include_j2:
        x, y, z = r
        r7 = r_mag**7

        # Partial derivatives of J2 acceleration (simplified)
        factor = -1.5 * J2 * MU_EARTH * R_EARTH**2
        z2 = z**2

        # Diagonal terms (approximate — full expressions are lengthy)
        G_j2 = np.zeros((3, 3))
        G_j2[0, 0] = factor / r5 * (1 - 5 * z2 / r2) + factor * x * (
            -5 * x / r7 * (1 - 5 * z2 / r2) + 10 * z2 * x / r7)
        G_j2[1, 1] = factor / r5 * (1 - 5 * z2 / r2) + factor * y * (
            -5 * y / r7 * (1 - 5 * z2 / r2) + 10 * z2 * y / r7)
        G_j2[2, 2] = factor / r5 * (3 - 5 * z2 / r2) + factor * z * (
            -5 * z / r7 * (3 - 5 * z2 / r2) + 10 * z2 * z / r7 - 10 * z / (r5))

        G = G + G_j2

    # Full Jacobian
    F = np.zeros((6, 6))
    F[:3, 3:] = np.eye(3)
    F[3:, :3] = G

    # STM derivative: Φ̇ = F · Φ
    stm_dot = (F @ stm).flatten()

    return np.concatenate([state_dot, stm_dot])


# ============================================================================
# PROPAGATION INTERFACE
# ============================================================================


def propagate_state(state: StateVector, dt: float,
                    cd: float = 2.2, cr: float = 1.5,
                    area_mass_ratio: float = 0.01,
                    include_j2: bool = True,
                    include_drag: bool = True,
                    include_srp: bool = False,
                    max_step: float = 60.0) -> StateVector:
    """
    Propagate a state vector forward by dt seconds using numerical integration.

    Parameters
    ----------
    state : StateVector
        Initial state
    dt : float
        Propagation time [seconds] (can be negative for backward prop)
    cd, cr, area_mass_ratio : float
        Spacecraft properties
    include_j2, include_drag, include_srp : bool
        Perturbation toggles
    max_step : float
        Maximum integration step [seconds]

    Returns
    -------
    StateVector
        Propagated state
    """
    y0 = np.concatenate([state.r, state.v])

    sol = solve_ivp(
        equations_of_motion,
        [0, dt],
        y0,
        method='DOP853',
        max_step=max_step,
        rtol=1e-10,
        atol=1e-12,
        args=(cd, cr, area_mass_ratio, include_j2, include_drag, include_srp)
    )

    if not sol.success:
        raise RuntimeError(f"Propagation failed: {sol.message}")

    final = sol.y[:, -1]
    return StateVector(r=final[:3], v=final[3:])


def propagate_with_stm(state: StateVector, dt: float,
                       cd: float = 2.2, cr: float = 1.5,
                       area_mass_ratio: float = 0.01,
                       include_j2: bool = True,
                       max_step: float = 60.0) -> Tuple[StateVector, np.ndarray]:
    """
    Propagate state AND State Transition Matrix.

    The STM maps perturbations at t₀ to perturbations at t:
        δX(t) = Φ(t, t₀) · δX(t₀)

    This is essential for:
    - Covariance propagation: P(t) = Φ·P(t₀)·Φᵀ
    - Maneuver effectiveness: Δr(TCA) = Φ_rv · Δv(t_man)

    Parameters
    ----------
    state : StateVector
        Initial state
    dt : float
        Propagation time [seconds]

    Returns
    -------
    StateVector
        Propagated state
    np.ndarray (6, 6)
        State Transition Matrix Φ(t₀+dt, t₀)
    """
    # Initial conditions: state + identity STM
    y0 = np.concatenate([
        state.r, state.v,
        np.eye(6).flatten()
    ])

    sol = solve_ivp(
        equations_of_motion_with_stm,
        [0, dt],
        y0,
        method='DOP853',
        max_step=max_step,
        rtol=1e-10,
        atol=1e-12,
        args=(cd, cr, area_mass_ratio, include_j2)
    )

    if not sol.success:
        raise RuntimeError(f"Propagation with STM failed: {sol.message}")

    final = sol.y[:, -1]
    final_state = StateVector(r=final[:3], v=final[3:])
    stm = final[6:].reshape(6, 6)

    return final_state, stm


def propagate_covariance(covariance: np.ndarray, stm: np.ndarray,
                         process_noise: Optional[np.ndarray] = None) -> np.ndarray:
    """
    Propagate state covariance using the STM.

    P(t) = Φ · P(t₀) · Φᵀ + Q

    Parameters
    ----------
    covariance : ndarray (6, 6)
        Initial state covariance
    stm : ndarray (6, 6)
        State Transition Matrix
    process_noise : ndarray (6, 6), optional
        Process noise covariance (models unmodeled accelerations)

    Returns
    -------
    ndarray (6, 6)
        Propagated covariance
    """
    P_new = stm @ covariance @ stm.T

    if process_noise is not None:
        P_new += process_noise

    return P_new


# ============================================================================
# TRAJECTORY GENERATION
# ============================================================================


def generate_ephemeris(state: StateVector, times: np.ndarray,
                      cd: float = 2.2, cr: float = 1.5,
                      area_mass_ratio: float = 0.01,
                      include_j2: bool = True,
                      include_drag: bool = True) -> np.ndarray:
    """
    Generate ephemeris (position/velocity history) at specified times.

    Parameters
    ----------
    state : StateVector
        Initial state at t=0
    times : ndarray
        Array of output times [seconds]
    cd, cr, area_mass_ratio : float
        Spacecraft properties

    Returns
    -------
    ndarray (N, 6)
        State vectors at each requested time
    """
    y0 = np.concatenate([state.r, state.v])

    sol = solve_ivp(
        equations_of_motion,
        [times[0], times[-1]],
        y0,
        method='DOP853',
        t_eval=times,
        max_step=60.0,
        rtol=1e-10,
        atol=1e-12,
        args=(cd, cr, area_mass_ratio, include_j2, include_drag, False)
    )

    if not sol.success:
        raise RuntimeError(f"Ephemeris generation failed: {sol.message}")

    return sol.y.T  # Shape: (N_times, 6)


def propagate_spacecraft(spacecraft: Spacecraft, dt: float,
                         include_j2: bool = True,
                         include_drag: bool = True) -> Tuple[Spacecraft, np.ndarray]:
    """
    Propagate a full spacecraft object (state + covariance).

    Parameters
    ----------
    spacecraft : Spacecraft
        Spacecraft to propagate
    dt : float
        Time step [seconds]

    Returns
    -------
    Spacecraft
        Updated spacecraft with propagated state and covariance
    np.ndarray (6, 6)
        State Transition Matrix
    """
    area_mass = spacecraft.area / spacecraft.mass  # m²/kg

    # Propagate state and STM
    new_state, stm = propagate_with_stm(
        spacecraft.state, dt,
        cd=spacecraft.cd, cr=spacecraft.cr,
        area_mass_ratio=area_mass,
        include_j2=include_j2
    )

    # Propagate covariance
    # Process noise: accounts for drag uncertainty, etc.
    # Scale with time — larger uncertainty over longer propagations
    sigma_acc = 1e-9  # km/s² unmodeled acceleration uncertainty
    Q = np.zeros((6, 6))
    Q[3:, 3:] = (sigma_acc * dt)**2 * np.eye(3)

    new_cov = propagate_covariance(spacecraft.covariance, stm, process_noise=Q)

    # Create updated spacecraft
    new_sc = Spacecraft(
        id=spacecraft.id,
        state=new_state,
        covariance=new_cov,
        mass=spacecraft.mass,
        area=spacecraft.area,
        cd=spacecraft.cd,
        cr=spacecraft.cr,
        delta_v_budget=spacecraft.delta_v_budget,
        delta_v_used=spacecraft.delta_v_used,
        maneuverable=spacecraft.maneuverable,
        name=spacecraft.name
    )

    return new_sc, stm
