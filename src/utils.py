"""
Constants, coordinate transforms, and helper utilities for orbital mechanics.
"""

import numpy as np
from dataclasses import dataclass, field
from typing import Optional

# ============================================================================
# PHYSICAL CONSTANTS
# ============================================================================

MU_EARTH = 398600.4418  # km³/s² — Earth gravitational parameter
R_EARTH = 6378.137  # km — Earth equatorial radius
J2 = 1.08263e-3  # Earth oblateness coefficient
OMEGA_EARTH = 7.2921159e-5  # rad/s — Earth rotation rate
P_SOLAR = 4.56e-6  # N/m² — Solar radiation pressure at 1 AU
CATASTROPHIC_ENERGY = 40000.0  # J/kg — NASA breakup model threshold


# ============================================================================
# DATA STRUCTURES
# ============================================================================


@dataclass
class OrbitalElements:
    """Classical Keplerian orbital elements."""
    a: float  # Semi-major axis [km]
    e: float  # Eccentricity [dimensionless]
    i: float  # Inclination [rad]
    raan: float  # Right Ascension of Ascending Node [rad]
    omega: float  # Argument of perigee [rad]
    nu: float  # True anomaly [rad]


@dataclass
class StateVector:
    """Cartesian state vector in ECI frame."""
    r: np.ndarray  # Position [km] (3,)
    v: np.ndarray  # Velocity [km/s] (3,)

    def __post_init__(self):
        self.r = np.asarray(self.r, dtype=float)
        self.v = np.asarray(self.v, dtype=float)


@dataclass
class Spacecraft:
    """A spacecraft with physical and operational properties."""
    id: str
    state: StateVector
    covariance: np.ndarray  # 6x6 state covariance matrix
    mass: float  # kg
    area: float  # Cross-sectional area [m²]
    cd: float = 2.2  # Drag coefficient
    cr: float = 1.5  # Reflectivity coefficient
    delta_v_budget: float = 25.0  # Remaining Δv [m/s]
    delta_v_used: float = 0.0  # Δv already expended [m/s]
    maneuverable: bool = True
    name: str = ""


@dataclass
class Conjunction:
    """A predicted close approach between two objects."""
    obj1_id: str
    obj2_id: str
    tca: float  # Time of closest approach [seconds from epoch]
    miss_distance: float  # Minimum distance [km]
    relative_velocity: float  # Relative speed at TCA [km/s]
    probability_of_collision: float  # Pc
    combined_covariance_2d: Optional[np.ndarray] = None  # 2x2 in encounter plane
    risk_score: float = 0.0


@dataclass
class Maneuver:
    """A collision avoidance maneuver."""
    spacecraft_id: str
    time: float  # Execution time [seconds from epoch]
    delta_v: np.ndarray  # Δv vector in RTN frame [km/s]
    target_conjunction_id: Optional[str] = None
    fuel_cost: float = 0.0  # |Δv| in m/s

    def __post_init__(self):
        self.delta_v = np.asarray(self.delta_v, dtype=float)
        self.fuel_cost = np.linalg.norm(self.delta_v) * 1000.0  # km/s → m/s


# ============================================================================
# COORDINATE TRANSFORMS
# ============================================================================


def rotation_matrix_x(angle: float) -> np.ndarray:
    """Rotation matrix about X-axis."""
    c, s = np.cos(angle), np.sin(angle)
    return np.array([[1, 0, 0],
                     [0, c, -s],
                     [0, s, c]])


def rotation_matrix_z(angle: float) -> np.ndarray:
    """Rotation matrix about Z-axis."""
    c, s = np.cos(angle), np.sin(angle)
    return np.array([[c, -s, 0],
                     [s, c, 0],
                     [0, 0, 1]])


def perifocal_to_eci(raan: float, i: float, omega: float) -> np.ndarray:
    """
    Rotation matrix from perifocal (PQW) frame to ECI frame.

    R = R3(-Ω) · R1(-i) · R3(-ω)
    """
    return rotation_matrix_z(-raan) @ rotation_matrix_x(-i) @ rotation_matrix_z(-omega)


def eci_to_rtn(r: np.ndarray, v: np.ndarray) -> np.ndarray:
    """
    Rotation matrix from ECI to RTN (Radial-Transverse-Normal) frame.

    R_hat = r / |r|  (radial outward)
    N_hat = (r × v) / |r × v|  (normal, along angular momentum)
    T_hat = N × R  (transverse, completes right-hand system)
    """
    r_hat = r / np.linalg.norm(r)
    h = np.cross(r, v)
    n_hat = h / np.linalg.norm(h)
    t_hat = np.cross(n_hat, r_hat)
    return np.array([r_hat, t_hat, n_hat])


def coe_to_state(elements: OrbitalElements) -> StateVector:
    """
    Convert classical orbital elements to ECI state vector.

    Uses the perifocal frame as intermediate.
    """
    a, e, i, raan, omega, nu = (
        elements.a, elements.e, elements.i,
        elements.raan, elements.omega, elements.nu
    )

    # Semi-latus rectum
    p = a * (1 - e**2)

    # Radius
    r_mag = p / (1 + e * np.cos(nu))

    # Position and velocity in perifocal frame
    r_pqw = np.array([r_mag * np.cos(nu),
                       r_mag * np.sin(nu),
                       0.0])

    v_factor = np.sqrt(MU_EARTH / p)
    v_pqw = np.array([-v_factor * np.sin(nu),
                       v_factor * (e + np.cos(nu)),
                       0.0])

    # Rotate to ECI
    R = perifocal_to_eci(raan, i, omega)
    r_eci = R @ r_pqw
    v_eci = R @ v_pqw

    return StateVector(r=r_eci, v=v_eci)


def state_to_coe(state: StateVector) -> OrbitalElements:
    """
    Convert ECI state vector to classical orbital elements.
    """
    r = state.r
    v = state.v
    r_mag = np.linalg.norm(r)
    v_mag = np.linalg.norm(v)

    # Angular momentum
    h = np.cross(r, v)
    h_mag = np.linalg.norm(h)

    # Node vector
    k_hat = np.array([0, 0, 1.0])
    n = np.cross(k_hat, h)
    n_mag = np.linalg.norm(n)

    # Eccentricity vector
    e_vec = ((v_mag**2 - MU_EARTH / r_mag) * r - np.dot(r, v) * v) / MU_EARTH
    e = np.linalg.norm(e_vec)

    # Specific energy → semi-major axis
    energy = v_mag**2 / 2 - MU_EARTH / r_mag
    a = -MU_EARTH / (2 * energy)

    # Inclination
    i = np.arccos(np.clip(h[2] / h_mag, -1, 1))

    # RAAN
    if n_mag > 1e-10:
        raan = np.arccos(np.clip(n[0] / n_mag, -1, 1))
        if n[1] < 0:
            raan = 2 * np.pi - raan
    else:
        raan = 0.0

    # Argument of perigee
    if n_mag > 1e-10 and e > 1e-10:
        omega = np.arccos(np.clip(np.dot(n, e_vec) / (n_mag * e), -1, 1))
        if e_vec[2] < 0:
            omega = 2 * np.pi - omega
    else:
        omega = 0.0

    # True anomaly
    if e > 1e-10:
        nu = np.arccos(np.clip(np.dot(e_vec, r) / (e * r_mag), -1, 1))
        if np.dot(r, v) < 0:
            nu = 2 * np.pi - nu
    else:
        nu = 0.0

    return OrbitalElements(a=a, e=e, i=i, raan=raan, omega=omega, nu=nu)


def orbital_period(a: float) -> float:
    """Orbital period in seconds given semi-major axis in km."""
    return 2 * np.pi * np.sqrt(a**3 / MU_EARTH)


def circular_velocity(altitude_km: float) -> float:
    """Circular orbital velocity at given altitude above Earth surface [km/s]."""
    r = R_EARTH + altitude_km
    return np.sqrt(MU_EARTH / r)
