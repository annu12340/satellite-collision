"""
Custom avoidance strategy: Relative velocity magnitude assessment.

This strategy evaluates collision risk based on the relative velocity
between two spacecraft at closest approach. Higher relative velocity
means more kinetic energy and more severe debris generation if a
collision occurs.

Entry point: evaluate_relative_velocity()

Reference:
    NASA Standard Breakup Model — fragment count scales with v_rel^0.5
    for non-catastrophic collisions. Catastrophic threshold (40 kJ/kg)
    is also velocity-dependent.
"""

from typing import List

from src.utils import Spacecraft, Conjunction


# Maximum typical relative velocity for LEO encounters [km/s].
# Head-on retrograde crossings at ~400 km altitude produce ~15 km/s;
# 20 km/s is a conservative upper bound.
_MAX_RELATIVE_VELOCITY_KMS = 20.0


def evaluate_relative_velocity(
    conjunction: Conjunction,
    spacecraft_list: List[Spacecraft],
) -> float:
    """
    Assess risk factor based on relative velocity at TCA.

    Higher relative velocities indicate more energetic encounters and
    more severe damage if a collision occurs (fragment count scales
    with v_rel^0.5 per NASA breakup model).

    Parameters
    ----------
    conjunction : Conjunction
        The conjunction event to assess. Uses the `relative_velocity`
        field (km/s) computed during conjunction screening.
    spacecraft_list : List[Spacecraft]
        Full constellation context (unused by this strategy, but
        required by the strategy interface for consistency).

    Returns
    -------
    float
        Risk factor in [0.0, 1.0]:
        - 0.0 = very low relative velocity (minimal debris potential)
        - 1.0 = maximum expected relative velocity (severe debris risk)
    """
    v_rel_kms = conjunction.relative_velocity
    risk_factor = min(v_rel_kms / _MAX_RELATIVE_VELOCITY_KMS, 1.0)
    return float(risk_factor)
