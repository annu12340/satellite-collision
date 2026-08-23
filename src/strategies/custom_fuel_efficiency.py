"""
Custom avoidance strategy: Fuel efficiency risk assessment.

This strategy evaluates the risk-to-fuel-cost ratio for a conjunction,
answering: "How much risk does this conjunction pose per unit of
available delta-v to resolve it?"

A conjunction is more concerning when:
- High probability of collision (Pc)
- Low available fuel on involved spacecraft
- The required delta-v to achieve safe miss distance is large relative to budget

Entry point: evaluate_fuel_efficiency()

Reference:
    STM-based maneuver sizing — see docs/physics.md, "Maneuver Planning"
    section. Delta-v requirement scales inversely with lead time before TCA.
"""

import numpy as np
from typing import List

from src.utils import Spacecraft, Conjunction


# Minimum fuel budget below which a spacecraft is considered critically low [m/s]
_CRITICAL_FUEL_THRESHOLD_MS = 5.0

# Reference delta-v for normalization: typical LEO avoidance maneuver [m/s]
_REFERENCE_DV_MS = 1.0


def evaluate_fuel_efficiency(
    conjunction: Conjunction,
    spacecraft_list: List[Spacecraft],
) -> float:
    """
    Assess risk based on fuel availability relative to conjunction severity.

    Higher values indicate conjunctions where fuel scarcity makes
    resolution expensive or impossible — these need priority attention
    from the global optimizer.

    The metric combines:
    - Conjunction severity (Pc × relative velocity)
    - Fuel scarcity of the maneuverable spacecraft in the pair
    - Time pressure (less lead time = more delta-v required)

    Parameters
    ----------
    conjunction : Conjunction
        The conjunction event to assess. Uses `probability_of_collision`,
        `relative_velocity` (km/s), `tca` (seconds from epoch), and
        object IDs to look up spacecraft.
    spacecraft_list : List[Spacecraft]
        Full constellation list. Used to find fuel budgets for the
        spacecraft involved in this conjunction.

    Returns
    -------
    float
        Risk factor in [0.0, 1.0]:
        - 0.0 = ample fuel, low severity (easy to resolve)
        - 1.0 = critically low fuel with high severity (urgent)
    """
    # Find involved spacecraft fuel budgets
    fuel_budgets = []
    for sc in spacecraft_list:
        if sc.id in (conjunction.obj1_id, conjunction.obj2_id):
            fuel_budgets.append(sc.delta_v_budget)

    if not fuel_budgets:
        # Cannot find spacecraft — return moderate risk as fallback
        return 0.5

    # Use the minimum fuel budget among involved spacecraft
    min_fuel = min(fuel_budgets)

    # Fuel scarcity factor: approaches 1.0 as fuel drops toward critical
    # Uses a smooth sigmoid-like curve
    fuel_scarcity = 1.0 / (1.0 + np.exp(-((_CRITICAL_FUEL_THRESHOLD_MS - min_fuel) / 2.0)))

    # Severity factor: Pc weighted by relative velocity (energy proxy)
    # Normalize relative velocity to [0, 1] range (max ~15 km/s for LEO)
    v_rel_normalized = min(conjunction.relative_velocity / 15.0, 1.0)
    severity = conjunction.probability_of_collision * (0.5 + 0.5 * v_rel_normalized)

    # Time pressure: less time to TCA means more delta-v required
    # Normalize: 1 hour = high pressure, 24 hours = low pressure
    hours_to_tca = max(conjunction.tca / 3600.0, 0.01)
    time_pressure = min(1.0 / hours_to_tca, 1.0)

    # Combined risk: weighted blend of fuel scarcity, severity, and time pressure
    combined = (
        0.4 * fuel_scarcity
        + 0.35 * severity
        + 0.25 * time_pressure
    )

    # Clamp to [0, 1]
    return float(np.clip(combined, 0.0, 1.0))
