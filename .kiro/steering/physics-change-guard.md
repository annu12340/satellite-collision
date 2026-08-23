---
inclusion: fileMatch
fileMatchPattern: "**/orbital_mechanics.py"
---

# Physics Change Guard — Orbital Mechanics

This steering activates when `src/orbital_mechanics.py` is read into context, providing domain-specific constraints for the most safety-critical module in the system.

## Core Invariants

1. **State vectors are always `[x, y, z, vx, vy, vz]` in ECI frame** (Earth-Centered Inertial). Units: kilometers for position, km/s for velocity (matching the convention in `src/utils.py`). Never store or return state in any other frame without immediate conversion.

2. **Gravitational parameter**: Always use `MU_EARTH` from `src/utils.py` (398600.4418 km³/s²). Never hardcode this value.

3. **Perturbation models** currently implemented:
   - J2 oblateness (dominant for LEO)
   - Atmospheric drag (exponential density model)
   - Solar radiation pressure
   
   Any new perturbation must be added as a toggleable term in the acceleration function and documented in #[[file:docs/physics.md]].

4. **State Transition Matrix (STM)** must remain 6×6 and satisfy Φ(t₀, t₀) = I₆. After long propagation (>24h), check conditioning — if `cond(Φ) > 1e12`, warn and suggest re-initialization.

5. **Energy conservation test**: In the two-body (unperturbed) case, specific orbital energy `ε = v²/2 − μ/r` must remain constant to within 1e-10 km²/s² per orbit. Any change to the integrator or force model should be validated against this invariant.

## Formula Reference

All equations in this module trace to #[[file:docs/physics.md]]. When modifying a formula:
- Cite the equation number or section from physics.md
- If introducing a formula not yet in physics.md, add it there first
- Include units in the docstring for every parameter and return value

## Integration Method

The current integrator is RK7(8) (Dormand-Prince) via `scipy.integrate.solve_ivp`. Acceptable alternatives: RK4(5), Adams-Bashforth-Moulton. Do not switch to a symplectic integrator without discussion — the perturbation terms break symplecticity anyway.

## Common Pitfalls

- **Unit mismatch**: The API layer (`src/api.py`) sometimes uses meters. Conversions happen at the API boundary, never inside this module.
- **Covariance propagation**: Uses `P(t) = Φ·P₀·Φᵀ + Q`. The process noise Q is optional and defaults to zero. If Q is added, document its physical basis.
- **Vectorization**: NumPy broadcasting is preferred over Python loops for multi-object propagation.
