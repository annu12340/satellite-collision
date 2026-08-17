# Requirements: Avoidance Maneuver Planning

## Overview

The Avoidance Maneuver Planning module plans optimal collision avoidance maneuvers for satellite constellations. Given detected conjunctions (predicted close approaches), it designs and sequences maneuvers that maximize miss distance while minimizing fuel consumption. The system uses State Transition Matrix (STM) analysis for precise effectiveness calculations and handles single and multi-conjunction scenarios with fuel-constrained planning.

---

## Functional Requirements

### 1. Maneuver Effectiveness Analysis (STM-Based)

**Requirement 1.1**: Compute position-velocity STM partition

The system shall compute the 3×3 State Transition Matrix (Φ_rv) that maps velocity impulses at a specified maneuver time to position changes at the time of closest approach (TCA).

**Criteria**:
- Input: spacecraft state (r, v), TCA [seconds], maneuver time [seconds], area-to-mass ratio
- Output: 3×3 matrix Φ_rv
- The matrix shall account for Earth's gravitational parameters (μ, R_earth) and perturbations (J2 oblateness, atmospheric drag, solar radiation pressure)
- Numerical integration shall be performed using RK4 or equivalent with step size control
- Computation shall complete within 100 ms for a single call

**Rationale**: STM computation is the foundation of all maneuver effectiveness calculations. Accurate propagation with perturbations ensures realistic miss-distance predictions.

---

**Requirement 1.2**: Ensure STM matrix invertibility and condition number

The system shall validate the computed Φ_rv matrix for numerical stability.

**Criteria**:
- If condition number > 1e10, flag as ill-conditioned and return error
- If matrix is singular (determinant ≈ 0), return error and indicate no maneuver is effective at this time
- All error conditions shall be caught gracefully; design function shall return None (not raise exception)

**Rationale**: Ill-conditioned matrices lead to incorrect optimum directions and unreliable maneuver designs.

---

### 2. Optimal Maneuver Direction Computation

**Requirement 2.1**: Compute the direction that maximizes miss distance gain

The system shall compute the unit velocity vector (Δv_hat) that, when applied at the maneuver time, produces the maximum increase in miss distance at TCA.

**Criteria**:
- Input: Φ_rv matrix [3×3], current miss vector [3×1]
- Output: unit direction vector [3×1]
- The direction shall maximize |Φ_rv · direction| in the miss-distance-increasing sense
- Mathematically: direction = argmax_hat{Φ_rv^T · miss_hat} / |Φ_rv^T · miss_hat|
- Computation shall complete within 10 ms
- Direction shall always be a unit vector (norm = 1.0 ± 1e-8)

**Rationale**: Optimal direction ensures fuel efficiency; any other direction requires more Δv to achieve the same miss distance.

---

**Requirement 2.2**: Handle degenerate cases

If the optimal direction computation is degenerate (e.g., Φ_rv^T · miss_hat ≈ 0), use the maximum singular vector of Φ_rv.

**Criteria**:
- If |Φ_rv^T · miss_hat| < 1e-15, fall back to principal singular vector
- Direction shall still be a unit vector
- Computation shall not raise exception

**Rationale**: Degenerate cases occur when the miss vector is orthogonal to Φ_rv; falling back to the most effective direction ensures best-effort maneuver design.

---

### 3. Maneuver Timing Optimization

**Requirement 3.1**: Find the optimal maneuver execution time

The system shall determine the time (within a feasible window) at which executing a velocity impulse yields maximum effectiveness.

**Criteria**:
- Input: spacecraft state, TCA, feasible time window (earliest, latest)
- Output: optimal maneuver time [seconds]
- Feasible window: earliest time ≥ 60 seconds, latest time ≤ TCA - 300 seconds
- Sample effectiveness (max singular value of Φ_rv) at n_samples = 20 points
- Return the time corresponding to maximum effectiveness
- If effectiveness is zero everywhere, return the midpoint of the window
- Computation shall complete within 500 ms

**Criteria**:
- The returned time shall satisfy: earliest ≤ returned_time ≤ latest
- Effectiveness at returned time shall be within 1% of the true maximum (within sampling precision)

**Rationale**: Earlier maneuvers are generally more effective, but geometry varies. Sampling captures this variation and ensures near-optimal timing.

---

### 4. Single-Conjunction Avoidance Maneuver Design

**Requirement 4.1**: Design an avoidance maneuver for one conjunction

The system shall design a single velocity impulse that reduces the collision risk for a specified conjunction.

**Criteria**:
- Input: maneuvering spacecraft, target spacecraft, conjunction, target miss distance [km], max Δv [m/s], optional forced maneuver time
- Output: Maneuver object or None if infeasible
- The designed maneuver shall have Δv expressed in RTN (Radial-Transverse-Normal) frame
- Execution time shall be within feasible window [60 s, TCA - 300 s]
- Fuel cost shall not exceed the smaller of: (a) remaining budget, (b) provided max_delta_v_ms
- After maneuver, miss distance shall increase toward target (or maintain margin if already safe)
- If target miss distance is unachievable within fuel budget, use maximum available fuel in optimal direction

**Criteria**:
- Required Δv magnitude: |Δv| = required_miss_change / effectiveness
- If effectiveness < 1e-6, return None (maneuver too weak)
- If required |Δv| > max_available, apply max_available and return partial success

**Rationale**: Single-conjunction design is the basic unit of maneuver planning. It must be robust to fuel constraints and time constraints.

---

**Requirement 4.2**: Validate maneuver feasibility

Before returning a maneuver, the system shall verify it is executable.

**Criteria**:
- Spacecraft must be maneuverable (maneuverable flag = True)
- Maneuver time must be positive and before TCA
- Δv magnitude must be positive and ≤ remaining fuel budget (minus reserve)
- Execution shall not raise exceptions; return None if any check fails

**Rationale**: Invalid maneuvers corrupt the planning process; fail-safe validation prevents downstream errors.

---

### 5. Maneuver Evaluation (Post-Execution Assessment)

**Requirement 5.1**: Evaluate maneuver effectiveness post-hoc

The system shall assess the actual miss distance and Pc after a planned maneuver is applied.

**Criteria**:
- Input: pre-maneuver spacecraft, target spacecraft, maneuver, original TCA
- Output: new miss distance [km], new Pc
- Process: apply Δv at maneuver time, propagate to TCA, compute miss distance
- Pc calculation shall use the original covariance matrices (approximation; full re-propagation of covariance not required)
- Return values shall match forward propagation to within 0.1% (numerical precision)

**Rationale**: Evaluation predicts the outcome of a planned maneuver, enabling decision logic and optimization feedback.

---

### 6. Multi-Conjunction Joint Optimization

**Requirement 6.1**: Jointly optimize maneuvers for multiple sequential conjunctions

When one spacecraft faces multiple conjunctions, the system shall find a single (or small sequence of) maneuver(s) that resolves all of them with minimal fuel.

**Criteria**:
- Input: maneuvering spacecraft, list of target spacecraft (one per conjunction), list of conjunctions, fuel reserve fraction
- Output: list of Maneuver objects (typically 1, occasionally 2-3)
- Approach: numerical optimization (Nelder-Mead) to find Δv minimizing total risk across all conjunctions
- Objective function: minimize Σ_j exp(-miss_j / 0.5) + fuel_penalty
- Fuel penalty: (|Δv| / available_budget)² with 0.1 coefficient to balance risk vs fuel
- Maneuver time: selected as min(earliest_tca / 2, earliest_tca - 3600 s) to affect all conjunctions
- Fuel budget: available_budget × (1 - reserve_fraction) (reserve fraction default 0.3)
- Optimization shall use at most 500 iterations
- Convergence criterion: fatol ≤ 1e-10, xatol ≤ 1e-8

**Criteria**:
- If final objective value < 0.5, maneuver effectively resolves all conjunctions
- If final objective value ≥ 0.5, maneuver is partial; flag for secondary planning
- Execution time (optimization) shall be ≤ 2 seconds

**Rationale**: Joint optimization is fuel-efficient; a single well-placed maneuver often resolves multiple conjunctions, freeing fuel for future unknowns.

---

**Requirement 6.2**: Reserve fuel for future unknowns

The system shall preserve a fraction of the fuel budget for future, unplanned conjunctions.

**Criteria**:
- Default reserve fraction: 0.3 (30%)
- Actual available for current planning: budget × (1 - 0.3) = 70%
- Reserve is not allocated to any maneuver; it remains available
- If a conjunction cannot be resolved with only 70% budget, it may be escalated to use reserve (see decision logic)

**Rationale**: Constellations face continuous discovery of new conjunctions. Preserving margins ensures capability to respond to emergencies.

---

### 7. Maneuver Execution and Fuel Accounting

**Requirement 7.1**: Apply a maneuver and update spacecraft state

The system shall execute a planned maneuver, updating the spacecraft state and fuel budget.

**Criteria**:
- Input: pre-maneuver spacecraft, maneuver
- Output: post-maneuver spacecraft with updated state and fuel
- Process:
  1. Propagate state to maneuver time
  2. Convert Δv from RTN frame to ECI frame
  3. Apply: v_new = v_old + Δv_eci
  4. Update covariance: add execution error (1% of |Δv| as 1-sigma velocity error)
  5. Deduct fuel: fuel_used_total += |Δv| [in m/s]
  6. Return updated spacecraft
- Execution shall complete within 50 ms
- Updated fuel shall satisfy: 0 ≤ fuel_used ≤ fuel_budget

**Rationale**: Accurate fuel tracking and state updates are critical for sequential maneuver planning and risk re-assessment.

---

**Requirement 7.2**: Account for maneuver execution uncertainty

The system shall increase the spacecraft's covariance matrix to reflect uncertainty in maneuver execution.

**Criteria**:
- Execution error: 1% of |Δv| as 1-sigma error in velocity components
- Add to velocity covariance: Δ Cov_v = σ² · I_3×3, where σ = 0.01 × |Δv| [km/s]
- Updated covariance shall remain positive definite
- Covariance increase shall be symmetric

**Rationale**: Thrusters have finite precision; tracking the resulting uncertainty enables realistic risk updates for subsequent conjunctions.

---

### 8. Decision Logic for Maneuver Execution

**Requirement 8.1**: Determine whether a conjunction warrants a maneuver

The system shall apply decision logic based on collision probability, available fuel, and time to TCA.

**Criteria**:
- Decision thresholds:
  | Decision | Pc Threshold | Fuel Requirement | Timing |
  |----------|-------------|------------------|--------|
  | MANEUVER | ≥ 1e-4 | Any | Any |
  | CONSIDER | 1e-5 to 1e-4 | ≥ 10 m/s | > 300 s to TCA |
  | MONITOR | 1e-6 to 1e-5 | N/A | N/A |
  | ACCEPT | < 1e-6 | N/A | N/A |

- Special cases:
  - If fuel_remaining < 5 m/s AND Pc > 1e-3: Decision = MANEUVER (emergency)
  - If time_to_tca < 300 s AND Pc > 1e-3: Decision = MANEUVER (no time for refinement)
  - If spacecraft.maneuverable = False: Decision = ACCEPT (cannot maneuver)

- Function should return one of: {'MANEUVER', 'CONSIDER', 'MONITOR', 'ACCEPT'}

**Rationale**: Decision thresholds balance operational risk (Pc), resource availability (fuel), and timing constraints. They reflect industry best practices.

---

**Requirement 8.2**: Prioritize conjunctions for planning

When multiple conjunctions require decisions, the system shall rank them by risk and urgency.

**Criteria**:
- Priority score = risk_score × urgency_multiplier × maneuverability_factor
- urgency_multiplier = 2^((24 - hours_to_tca) / 6): doubles every 6 hours as TCA approaches
- maneuverability_factor = 0.1 if both objects unmaneuverable; 1.0 otherwise
- Return conjunctions sorted in descending priority order

**Criteria**:
- Highest-priority conjunctions are first in the list
- Planning algorithm processes them in order, assigning maneuvers greedily

**Rationale**: Prioritization ensures time-critical and high-risk conjunctions are addressed first, even if fuel limits prevent handling all.

---

### 9. Full Avoidance Campaign Planning

**Requirement 9.1**: Plan a complete sequence of maneuvers for all active conjunctions

The system shall generate an optimal or near-optimal maneuver sequence for an entire constellation over a planning horizon.

**Criteria**:
- Input: spacecraft list, active conjunctions, planning horizon [seconds]
- Output: list of maneuvers sorted by execution time
- Process:
  1. Build lookup dictionary of spacecraft by ID
  2. Prioritize conjunctions
  3. For each conjunction, determine maneuverer (prefer higher remaining fuel)
  4. Apply decision logic
  5. If decision is MANEUVER or CONSIDER, design maneuver and add to plan
  6. Update spacecraft state after each maneuver (for subsequent planning)
  7. Sort final maneuvers by execution time
- Execution time shall be < 5 seconds for 1000 spacecraft and 100 conjunctions

**Criteria**:
- No spacecraft shall execute two maneuvers simultaneously (sorted order ensures sequential)
- Total fuel expended across all maneuvers shall not exceed initial budgets
- Maneuvers shall be executable in the returned order without conflicts

**Rationale**: Campaign planning is the top-level interface; it must handle realistic constellation sizes efficiently.

---

**Requirement 9.2**: Avoid creating new problems

The planning algorithm shall check that maneuvers do not inadvertently create new conjunctions.

**Criteria**:
- After each maneuver assignment, the system may optionally re-screen affected spacecraft against all objects
- If new high-risk conjunctions are created, deprioritize the original maneuver
- (Note: Full re-screening is O(N²); optional optimization for phase 2)

**Rationale**: Poorly planned maneuvers can shift a collision risk from one conjunction to another. This requirement discourages such transfers.

---

## Behavioral Requirements

### 10. Coordinate Frames and Transformations

**Requirement 10.1**: Convert Δv between ECI and RTN frames

The system shall transform velocity impulses between Earth-Centered Inertial (ECI) and Radial-Transverse-Normal (RTN) frames.

**Criteria**:
- RTN frame: R = radial (outward from Earth center), T = transverse (prograde), N = normal (angular momentum)
- Transformation: RTN_from_ECI = [r_hat, t_hat, n_hat] constructed from spacecraft state (r, v)
- Transformation: ECI_from_RTN = transpose of above
- All transformations shall preserve vector magnitude (rotation matrices are orthogonal)
- Both directions shall be invertible

**Rationale**: RTN is the natural frame for maneuver planning (Radial, prograde, out-of-plane); ECI is the natural frame for propagation. Conversion must be exact.

---

### 11. Numerical Stability and Error Handling

**Requirement 11.1**: Gracefully handle propagation failures

If numerical integration diverges, the system shall catch the exception and return a safe default.

**Criteria**:
- Propagation errors (NaN, Inf, divergence): catch and return None or empty list
- Decision logic shall treat None/empty as "unable to design maneuver; accept risk"
- Logging: each failure shall be logged with reason and context
- No exception shall propagate to the caller

**Rationale**: Numerical failures should not crash the planning system; accept-risk fallback is safe.

---

**Requirement 11.2**: Validate input data

All input spacecraft states, conjunctions, and parameters shall be validated before use.

**Criteria**:
- Spacecraft state: r_magnitude > R_Earth (above Earth surface)
- Covariance: positive definite (all eigenvalues > 0)
- Conjunction: TCA > 0, miss_distance ≥ 0, 0 ≤ Pc ≤ 1
- Fuel budget: non-negative
- Area-to-mass ratio: positive
- If validation fails, log warning and return None (not raise exception)

**Rationale**: Invalid inputs lead to garbage outputs; early validation provides clear failure modes.

---

## Non-Functional Requirements

### 12. Performance

**Requirement 12.1**: Single maneuver design latency

The `design_avoidance_maneuver` function shall complete within 200 ms (typically 50-100 ms).

**Criteria**:
- Measured on a standard laptop (Intel i7, 8GB RAM)
- Includes STM computation, timing optimization, direction computation, and all checks
- 90th percentile latency shall be ≤ 200 ms
- 99th percentile latency shall be ≤ 500 ms (rare outliers)

**Rationale**: Maneuver design may be called hundreds of times in campaign planning; fast turnaround enables real-time operations.

---

**Requirement 12.2**: Joint optimization latency

The `joint_avoidance_optimization` function shall complete within 2 seconds (typically 500-1500 ms).

**Criteria**:
- For 3-5 sequential conjunctions
- Nelder-Mead optimizer with 500 iterations maximum
- Measured on standard laptop
- 90th percentile latency ≤ 2 seconds

**Rationale**: Joint optimization is heavier than single-maneuver design but must still be fast enough for batch planning.

---

**Requirement 12.3**: Campaign planning latency

The `plan_avoidance_campaign` function shall complete within 5 seconds for realistic constellation sizes.

**Criteria**:
- Up to 1000 spacecraft
- Up to 100 active conjunctions
- 90th percentile latency ≤ 5 seconds
- Linear or near-linear scaling with conjunction count

**Rationale**: Campaign planning is the top-level interface; interactive systems need <10 second response times.

---

### 13. Accuracy and Precision

**Requirement 13.1**: STM computation accuracy

The computed Φ_rv matrix shall match the true state transition matrix to within numerical precision.

**Criteria**:
- Relative error ≤ 1e-6 (for double-precision floating point)
- Verified by comparison to analytical solutions (e.g., Keplerian two-body for unperturbed case)
- Impact: miss distance predictions accurate to ~1 meter over 24-hour horizons

**Rationale**: STM errors propagate through all downstream calculations; sub-1e-6 precision is adequate for safety margins (1 km).

---

**Requirement 13.2**: Optimal direction accuracy

The computed direction shall have the correct orientation to within 0.1 degrees.

**Criteria**:
- Angle between computed and true optimal direction ≤ 0.1 degrees
- Verified by numerical differentiation (finite-difference comparison)
- Impact: fuel efficiency within 0.2% (worst case, for small maneuvers)

**Rationale**: Direction errors cause minor fuel penalties; 0.1 degree tolerance is negligible.

---

### 14. Robustness

**Requirement 14.1**: Fuel budget never violated

No sequence of operations shall allow fuel_used to exceed fuel_budget.

**Criteria**:
- This is a hard invariant, enforced at every step
- If a planned maneuver would exceed budget, it shall be rejected
- System design prevents any bypass

**Rationale**: Fuel is a real physical resource; violations represent impossible states.

---

**Requirement 14.2**: Covariance remains positive definite

The spacecraft covariance matrix shall remain positive definite after every operation.

**Criteria**:
- Minimum eigenvalue > 1e-10 (numerical precision)
- If propagation corrupts covariance, reset to diagonal positive definite estimate
- Logging: each reset shall be logged as anomaly

**Rationale**: Negative or zero eigenvalues cause numerical failures in probability calculations.

---

## Data Requirements

### 15. Input Data Specifications

**Requirement 15.1**: Spacecraft state representation

Each spacecraft is described by:
- Unique ID (string)
- Position r [km] and velocity v [km/s] in ECI frame
- 6×6 state covariance matrix P [km², (km/s)²]
- Physical properties: mass [kg], cross-sectional area [m²]
- Maneuver properties: Δv budget [m/s], fuel used [m/s], maneuverable [bool]

**Criteria**:
- All numerical values are IEEE 754 double precision
- State vector r and v are represented as numpy arrays of shape (3,)
- Covariance is 6×6 symmetric positive definite

---

**Requirement 15.2**: Conjunction data representation

Each conjunction is described by:
- IDs of both objects
- Time of closest approach [seconds from epoch]
- Minimum predicted miss distance [km]
- Relative velocity at TCA [km/s]
- Probability of collision [dimensionless, 0 to 1]
- Optional: 2×2 covariance matrix in encounter plane

**Criteria**:
- All data derived from conjunction assessment module
- Accuracy ≥ 10 meters in miss distance for LEO (< 2000 km altitude)

---

## Integration and Interfaces

### 16. API Contracts

**Requirement 16.1**: Export public functions

The avoidance module shall export these public functions:

```python
def design_avoidance_maneuver(
    spacecraft: Spacecraft,
    other: Spacecraft,
    conjunction: Conjunction,
    target_miss_km: float = 1.0,
    max_delta_v_ms: Optional[float] = None,
    maneuver_time: Optional[float] = None
) -> Optional[Maneuver]

def joint_avoidance_optimization(
    spacecraft: Spacecraft,
    others: List[Spacecraft],
    conjunctions: List[Conjunction],
    fuel_reserve_fraction: float = 0.3
) -> List[Maneuver]

def plan_avoidance_campaign(
    spacecraft_list: List[Spacecraft],
    conjunctions: List[Conjunction],
    planning_horizon: float = 86400.0
) -> List[Maneuver]

def apply_maneuver(
    spacecraft: Spacecraft,
    maneuver: Maneuver
) -> Spacecraft

class ManeuverDecision:
    @staticmethod
    def should_maneuver(
        conjunction: Conjunction,
        spacecraft: Spacecraft,
        time_to_tca: float
    ) -> str

    @staticmethod
    def prioritize_conjunctions(
        conjunctions: List[Conjunction],
        spacecraft_dict: dict
    ) -> List[Conjunction]
```

**Criteria**:
- All functions shall be importable from `avoidance` module
- Type hints shall match signatures exactly
- Return types shall be as documented
- No breaking changes to signatures without major version bump

**Rationale**: Clear API contract enables external integration and testing.

---

**Requirement 16.2**: Dependency interfaces

The module shall depend on these external modules:

- `orbital_mechanics.py`: `propagate_state`, `propagate_with_stm`
- `conjunction.py`: `compute_encounter_plane`, `probability_of_collision_2d`
- `utils.py`: `StateVector`, `Spacecraft`, `Conjunction`, `Maneuver`, coordinate transforms

**Criteria**:
- All dependencies shall be imported explicitly
- Version compatibility: compatible with numpy >= 1.19, scipy >= 1.5
- No circular imports

**Rationale**: Clear dependency graph enables modular testing and maintenance.

---

## Verification and Validation

### 17. Testing Requirements

**Requirement 17.1**: Unit test coverage

The avoidance module shall have ≥ 85% line coverage by automated tests.

**Criteria**:
- Tests for all public functions
- Tests for error handling and edge cases
- Measured by coverage.py or equivalent
- Coverage report shall be generated in CI/CD pipeline

---

**Requirement 17.2**: Property-based testing

The module shall use property-based testing (Hypothesis, fast-check, or equivalent) for at least 4 properties.

**Criteria**:
- Properties shall include: monotonicity, fuel conservation, frame consistency, covariance positive definiteness
- Each property shall be tested with 100+ random cases
- Shrinking shall identify minimal failing examples

**Rationale**: Property testing catches edge cases and invariant violations that example-based tests miss.

---

## Summary

This requirements document specifies the complete behavior of the Avoidance Maneuver Planning module. It covers single and multi-conjunction maneuver design, fuel-constrained optimization, decision logic, and full campaign planning. All requirements are testable, measurable, and aligned with the high-level design.
