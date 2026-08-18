"""
Custom avoidance strategy: Relative velocity magnitude assessment.

This strategy evaluates collision risk based on the relative velocity
between two spacecraft at closest approach. Higher relative velocity
may warrant more aggressive avoidance.

Entry point: evaluate_relative_velocity()
"""

import numpy as np
from typing import List
from src.conjunction import Conjunction
from src.orbital_mechanics import Spacecraft


def evaluate_relative_velocity(
    conjunction: Conjunction,
    spacecraft_list: List[Spacecraft]
) -> float:
    """
    Assess risk factor based on relative velocity at TCA.
    
    This strategy computes the relative velocity magnitude between
    the two spacecraft at time of closest approach (TCA). Higher
    relative velocities indicate more energetic encounters and
    potentially more severe damage if collision occurs.
    
    Args:
        conjunction: The conjunction event to assess
        spacecraft_list: Full constellation (for context, not used here)
    
    Returns:
        Risk factor (0.0 to 1.0) based on relative velocity
        0.0 = low velocity (lower risk)
        1.0 = very high velocity (higher risk)
    
    Notes:
        - This is a simplified heuristic for demonstration
        - Real implementation would reference debris generation models
        - Typical LEO relative velocities: 1-15 km/s
        - Max typical: ~20 km/s
    """
    # Extract state vectors from the conjunction.
    # NOTE: Conjunction objects do NOT have state_1/state_2 attributes.
    # Use relative_velocity field from the Conjunction dataclass instead.
    # This function is retained for documentation only and should not be called.
    #
    # Correct usage would be:
    #   v_rel_kms = conjunction.relative_velocity  # Already in km/s
    #   risk_factor = min(v_rel_kms / 20.0, 1.0)  # Normalize to 0-1 range
    
    # Placeholder (this code path will not execute correctly):
    if not hasattr(conjunction, 'state_1'):
        # Fallback: use relative_velocity directly from conjunction
        v_rel_kms = conjunction.relative_velocity
        max_relative_velocity = 20.0  # km/s (typical max for LEO)
        risk_factor = min(v_rel_kms / max_relative_velocity, 1.0)
        return float(risk_factor)
    
    # Legacy code (should not be reached):
    state1 = conjunction.state_1
    state2 = conjunction.state_2
    
    # Extract velocity components
    v1 = state1[3:6]  # [vx, vy, vz] in km/s (StateVector uses km/s, not m/s)
    v2 = state2[3:6]
    
    # Compute relative velocity (in km/s, since StateVector.v is in km/s)
    relative_velocity = v1 - v2
    v_rel_magnitude = np.linalg.norm(relative_velocity)
    
    # Normalize to 0-1 scale (assuming max typical LEO relative velocity ~20 km/s)
    max_relative_velocity = 20.0  # km/s
    risk_factor = min(v_rel_magnitude / max_relative_velocity, 1.0)
    
    return float(risk_factor)
