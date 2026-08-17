# Requirements: Conjunction Assessment

## Feature Overview

The Conjunction Assessment module processes satellite tracking data to identify and quantify collision risks between pairs of objects. It sits at level 2 of the decision hierarchy (after DETECT, before DECIDE) and transforms raw conjunction candidates into statistically rigorous risk information.

**Key Objective**: Efficiently screen O(N²) spacecraft pairs down to actionable conjunction events with Probability of Collision (Pc) values accurate to 4+ significant figures.

---

## Acceptance Criteria

### 1. All-vs-All Screening with Geometric Filters

**Title**: Conjunctions identified for all pairs within threshold distance

**User Story**: As a space operations analyst, I want the system to screen all spacecraft pairs automatically so I don't have to manually check thousands of possible collisions.

**Acceptance Criteria**:

1. **A1.1** System shall screen all unique pairs (N choose 2) from input spacecraft list
   - Example: 100 spacecraft → 4,950 pairs screened
   - No duplicates (always i < j)
   - Verification: Output pair list size = N(N-1)/2

2. **A1.2** System shall apply apogee-perigee filter: eliminate pairs with non-overlapping orbital shells
   - If perigee₁ > apogee₂ + threshold_km, filter out immediately
   - Default threshold: 50 km
   - Verification: Synthetic test with non-overlapping orbits (0 output pairs)

3. **A1.3** System shall apply coplanar filter: eliminate pairs with non-intersecting orbital planes
   - Compute relative inclination using spherical geometry
   - If relative inclination > threshold (5°), and altitude bands don't overlap, filter out
   - Verification: Equatorial vs. 45° inclined orbit should be filtered

4. **A1.4** System shall flag conjunctions where minimum 3D distance < distance_threshold (5 km default)
   - Coarse ephemeris scan (100 time steps)
   - Find global minimum distance along trajectory
   - Verification: Two objects 4 km apart at closest → flagged; 6 km apart → not flagged

5. **A1.5** System shall return flagged pairs with (idx1, idx2, tca_approx, min_distance)
   - TCA is approximate (coarse estimate for refinement)
   - Miss distance is minimum found during coarse scan
   - Verification: End-to-end test with synthetic constellation

6. **A1.6** System shall handle propagation failures gracefully (skip failed objects)
   - If ephemeris generation fails, skip that object in pairing
   - Log warning with object ID and reason
   - Continue with remaining objects
   - Verification: Inject failure for one object, verify others screened normally

7. **A1.7** Filtering shall have no false negatives
   - Every real conjunction below threshold must pass through filters
   - Geometric filters only eliminate geometrically impossible approaches
   - Verification: Test with all filters disabled (reference), confirm enabled version returns superset

---

### 2. Time of Closest Approach Refinement

**Title**: TCA and miss distance refined to high precision

**User Story**: As an autonomous mission planning system, I want precise TCA and miss distance so I can compute accurate collision probabilities and maneuver timing.

**Acceptance Criteria**:

1. **A2.1** System shall refine TCA from coarse estimate using bounded optimization
   - Input: state vectors, approximate TCA (from coarse scan)
   - Output: refined TCA and minimum distance
   - Verification: Analytical two-body trajectory vs. computed TCA (within 0.1 s)

2. **A2.2** System shall achieve TCA precision of ±0.1 seconds
   - Optimizer tolerance: 0.1 second
   - Verification: Perturbation test (±0.1 s around returned TCA should not improve distance)

3. **A2.3** System shall bracket search around approximate TCA (±10 minutes default)
   - Search window prevents divergence to distant future approaches
   - Default window: 600 seconds
   - Verification: Returned TCA within search bounds

4. **A2.4** System shall find local minimum (refinement ≤ coarse estimate)
   - Distance at refined TCA ≤ distance at coarse estimate
   - Verification: Comparision test for 100 random conjunctions

5. **A2.5** System shall handle multiple close approaches per day
   - LEO objects can have 2+ approaches per day (orbital crossings)
   - Algorithm finds local minima, not just global minimum
   - Verification: Two LEO satellites with 2 orbital crossings → 2 conjunctions identified

6. **A2.6** Miss distance shall be ≥ 0 always
   - Geometric distance cannot be negative
   - Verification: Boundary test (objects at same position → 0; separated → > 0)

7. **A2.7** System shall handle edge cases: objects approaching vs. separating
   - Correctly identifies TCA even if initial guess is before/after actual TCA
   - Verification: Test with t_guess before and after true TCA (same refined TCA returned)

---

### 3. Encounter Plane Geometry

**Title**: Encounter plane established for collision probability calculation

**User Story**: As a statistician building risk models, I need the collision geometry frame so I can project uncertainties and integrate collision probability in 2D.

**Acceptance Criteria**:

1. **A3.1** System shall compute encounter plane as 2D subspace perpendicular to relative velocity
   - z-axis: relative velocity direction (unit vector)
   - x, y-axes: orthonormal basis spanning plane perpendicular to z
   - Verification: Dot product(z, x) = 0, dot product(z, y) = 0

2. **A3.2** System shall project 3D miss vector into 2D encounter plane
   - Miss vector = r₁(TCA) - r₂(TCA)
   - Project into x-y plane of encounter frame
   - Verification: miss_2d has 2 components, |miss_2d| ≤ |miss_3d|

3. **A3.3** System shall robustly handle colinear relative motion
   - If relative velocity nearly aligns with miss vector, choose arbitrary perpendicular basis
   - Verification: Test with objects in nearly identical orbits (same velocity)

4. **A3.4** Basis matrix shall be orthonormal (machine precision)
   - basis @ basis.T ≈ I (identity matrix)
   - All column vectors have unit norm
   - Verification: Check basis matrix properties via linear algebra (det=1, eigenvalues=1)

5. **A3.5** System shall transform 6×6 state covariance to 2×2 encounter plane covariance
   - Extract position covariances (3×3 blocks)
   - Combine: C_combined = C₁_pos + C₂_pos (independent error assumption)
   - Project: C_2d = P @ C_combined @ P.T (where P is 2×3 projection matrix)
   - Verification: eigenvalues(C_2d) ≥ 0 (positive semi-definite)

6. **A3.6** Projected covariance shall be positive semi-definite
   - All eigenvalues ≥ 0 (within numerical precision)
   - Determinant ≥ 0
   - Verification: Eigenvalue check on 100 random conjunctions

7. **A3.7** System shall handle singular covariances gracefully
   - If eigenvalue < 1e-10, regularize to 1e-10 km²
   - Emit warning to log
   - Proceed with regularized covariance
   - Verification: Input near-singular covariance, verify no crash and warning logged

---

### 4. Probability of Collision Calculation

**Title**: Pc calculated via 2D Gaussian hard-body integral (Alfriend/Akella method)

**User Story**: As a collision risk assessor, I need accurate Pc values so I can determine if maneuvers are needed and prioritize among multiple conjunctions.

**Acceptance Criteria**:

1. **A4.1** System shall compute Pc using 2D Gaussian hard-body model
   - Standard formulation: integral of 2D Gaussian PDF over collision disk
   - Disk radius = combined effective radius (both objects)
   - Verification: Compare to published benchmark cases (e.g., NASA conjunctions)

2. **A4.2** Pc shall be bounded in [0, 1]
   - Physically impossible to have probability < 0 or > 1
   - Verification: Property test over random inputs (Hypothesis/fast-check)

3. **A4.3** Pc shall increase monotonically with collision disk radius
   - Larger combined_radius → larger collision disk → higher Pc
   - Verification: Test with increasing radii (r=1mm, 1cm, 10cm, 1m)

4. **A4.4** Pc shall decrease monotonically with miss distance
   - Moving farther from collision center → lower probability
   - Verification: Scale miss_vector by [0.5, 1.0, 2.0, 5.0], verify Pc decreases

5. **A4.5** System shall handle edge cases: zero uncertainty (deterministic collision)
   - If covariance is exactly zero and miss_distance < combined_radius, return Pc = 1
   - If covariance is exactly zero and miss_distance ≥ combined_radius, return Pc = 0
   - Verification: Set covariance to machine epsilon, check limiting behavior

6. **A4.6** System shall regularize near-singular covariances
   - If any eigenvalue < 1e-10 km², clamp to 1e-10
   - Proceed with regularized matrix
   - Verification: Input singular matrix, verify no NaN/Inf output

7. **A4.7** Numerical integration shall achieve ≥4 significant figure accuracy
   - Grid: 50 radial × 100 azimuthal points
   - Compare to higher-resolution (200×400) for validation subset
   - Verification: Difference < 0.1% for test cases

8. **A4.8** System shall handle large miss distances (Pc → 0)
   - As miss_distance → ∞, Pc → 0 (at least exponentially fast)
   - No premature underflow to exactly zero
   - Verification: Test with miss_distance = 10 × σ (should be ~1e-20, not 0)

9. **A4.9** System shall handle very small uncertainties gracefully
   - Prevent division by zero or numerical instability
   - Use eigenvalue threshold for numerical robustness
   - Verification: Input covariance with σ = 0.1 mm (extreme), verify no crash

10. **A4.10** Combined effective radius shall sum individual radii plus margin
    - combined_radius = radius₁ + radius₂ + safety_margin (default: 10 cm)
    - Verification: Known collision case with specified radii → Pc computed correctly

---

### 5. Conjunction Record Output

**Title**: Conjunction structure populated with all required fields

**User Story**: As a downstream maneuver planning system, I need complete conjunction records with TCA, probability, covariance, and other metadata so I can make informed decisions.

**Acceptance Criteria**:

1. **A5.1** System shall output Conjunction records with required fields:
   - obj1_id, obj2_id: Spacecraft identifiers
   - tca: Time of closest approach (seconds from epoch)
   - miss_distance: Minimum separation (km)
   - relative_velocity: Speed at TCA (km/s)
   - probability_of_collision: Pc ∈ [0, 1]
   - combined_covariance_2d: 2×2 encounter plane covariance
   - risk_score: Composite rank (0 to ∞)
   - Verification: Check all fields populated for each conjunction

2. **A5.2** System shall validate Conjunction records
   - 0 ≤ probability_of_collision ≤ 1
   - miss_distance ≥ 0
   - relative_velocity ≥ 0
   - tca > 0 (future event)
   - combined_covariance_2d is 2×2 symmetric PSD
   - Verification: Reject any invalid records, log error

3. **A5.3** System shall compute risk_score as: Pc × Consequence × Cascade_factor
   - Consequence ∝ object mass and relative velocity
   - Cascade_factor = 1 + density(altitude) × debris_lifetime(altitude)
   - Verification: Known debris case with high cascade factor → high risk score

4. **A5.4** System shall rank conjunctions by risk score (highest first)
   - Sort output list by risk_score descending
   - Ties broken by TCA (sooner first)
   - Verification: Output list is strictly ordered by score

5. **A5.5** System shall handle zero Pc appropriately
   - Objects too far away (miss_distance >> σ) may return Pc ≈ 0
   - Should still be included in output (for completeness)
   - Verification: Output contains low-Pc items

6. **A5.6** System shall include encounter plane covariance in conjunction record
   - Downstream algorithms need this for uncertainty analysis
   - Stored in 2×2 numpy array
   - Verification: Covariance retrievable from each record

---

### 6. End-to-End Integration

**Title**: Full pipeline processes constellation to ranked conjunction list

**User Story**: As an operations center, I want the full conjunction assessment pipeline to run automatically, producing a daily briefing of all collision risks ranked by severity.

**Acceptance Criteria**:

1. **A6.1** System shall process N=10,000 spacecraft in <10 minutes
   - Total pipeline time budget: 10 minutes for full screening + Pc calculation
   - Includes all ~50 million pair checks and ~1000 conjunction refinements
   - Verification: Benchmark with constellation data (measure end-to-end time)

2. **A6.2** System shall produce output list with no duplicates
   - Each pair appears at most once (always i < j)
   - Verification: Check for duplicate (obj1_id, obj2_id) pairs in output

3. **A6.3** System shall handle empty/null inputs gracefully
   - If spacecraft_list is empty, return empty conjunction list (no crash)
   - Verification: Call with empty list, verify graceful return

4. **A6.4** System shall provide diagnostic output for debugging
   - Log number of pairs screened at each filter stage
   - Log number of flagged pairs, refined pairs, final ranked list
   - Verification: Check log output for diagnostic information

5. **A6.5** Conjunction list shall be suitable for maneuver planning input
   - Highest-risk items processable first for rapid decision-making
   - Verification: Feed top-N conjunctions to maneuver planner, verify success

6. **A6.6** System shall produce reproducible results
   - Same input, same random seed → identical output
   - Verification: Run twice on same constellation data, compare outputs (bit-identical)

7. **A6.7** System shall scale linearly with number of conjunctions (not N²)
   - Once pairs are flagged, remaining time ∝ number of flagged pairs
   - Verification: Profile with 100 vs. 1000 flagged conjunctions

---

### 7. Error Handling and Edge Cases

**Title**: System handles errors and boundary conditions gracefully

**User Story**: As a system administrator, I want the conjunction assessment module to fail gracefully so that operations are not disrupted by bad data or numerical issues.

**Acceptance Criteria**:

1. **A7.1** System shall detect and report singular covariances
   - Eigenvalue check before Pc calculation
   - If any eigenvalue ≤ 0 (within tolerance), regularize and warn
   - Verification: Inject singular matrix, verify warning in log

2. **A7.2** System shall skip objects with propagation failures
   - If ephemeris generation fails, log error and continue with remaining objects
   - Verification: Simulate propagation failure, verify graceful skip

3. **A7.3** System shall validate input state vectors
   - Check for NaN, Inf, or unreasonable magnitudes (radii outside 6000–7000 km for LEO)
   - Reject invalid objects, continue with valid ones
   - Verification: Input invalid state, verify rejection and warning

4. **A7.4** System shall handle very small relative velocities
   - If |v_rel| < 1e-10 km/s, raise ValueError with descriptive message
   - Flag pair as non-conjunction (orbiting together)
   - Verification: Test with nearly identical orbits, verify appropriate error

5. **A7.5** System shall prevent numeric underflow/overflow
   - Gaussian PDF: cap exponent to prevent underflow
   - Covariance inverse: use eigendecomposition (more stable than direct inversion)
   - Verification: Input extreme (very large or very small) values, verify no NaN/Inf

6. **A7.6** System shall provide clear error messages
   - All exceptions include spacecraft IDs, parameter values, and suggestions
   - Verification: Trigger each error scenario, check message clarity

---

### 8. Validation and Verification

**Title**: Correctness of conjunction assessment verified via testing

**User Story**: As a mission assurance engineer, I want rigorous testing so I can trust that the collision predictions are accurate.

**Acceptance Criteria**:

1. **A8.1** System shall pass unit tests for all components
   - Geometric filters (no false negatives)
   - TCA refinement (precision ±0.1 s)
   - Encounter plane (orthonormality)
   - Pc calculation (bounds, monotonicity)
   - Verification: Unit test suite with ≥95% code coverage

2. **A8.2** System shall pass property-based tests
   - Pc bounded in [0, 1] for 10,000 random inputs
   - Monotonicity properties hold
   - Numerical stability under extreme inputs
   - Verification: Hypothesis/fast-check suite with ≥1000 test cases per property

3. **A8.3** System shall match analytical results for simple cases
   - Head-on collision in circular orbits → Pc ≈ 1 (for reasonable combined_radius)
   - Miss >> σ → Pc ≈ 0 (exponential decay)
   - Verification: Benchmark against NASA/ESA conjunction data where available

4. **A8.4** System shall be reproducible and deterministic
   - Same input → identical output (across platforms, runs)
   - Verification: Run on different machines, verify bit-identical outputs

5. **A8.5** System shall document all assumptions and limitations
   - Two-body problem (no J2 or other perturbations)
   - Independent error model (no correlation between objects)
   - Alfriend/Akella methodology (standard in CAM community)
   - Verification: Design document includes Assumptions section

---

## Non-Functional Requirements

### Performance

- **Screening throughput**: 50 million pairs per day (for N=10k, 1-day window)
- **TCA refinement latency**: <150 ms per conjunction
- **Memory footprint**: <200 MB for N=10k, 1-day ephemerides
- **Scalability**: Linear in number of conjunctions (after screening)

### Reliability

- **Availability**: 99.9% (conjunction screening should not fail in operations)
- **Error detection**: All numerical errors caught and logged
- **Graceful degradation**: Skip failed objects, continue with remainder

### Usability

- **Logging**: Diagnostic info at each pipeline stage
- **Output format**: Structured (Python dataclasses or JSON)
- **Documentation**: All algorithms explained in design doc

### Maintainability

- **Code style**: PEP 8 Python standards
- **Test coverage**: ≥90% code coverage (unit + integration tests)
- **Comments**: Formal specifications (preconditions, postconditions, invariants) for all algorithms

---

## Traceability

| Requirement | Design Section | Test Type | Priority |
|-------------|----------------|-----------|----------|
| A1.1–A1.7  | Screening Component | Unit, Integration | High |
| A2.1–A2.7  | TCA Refinement | Unit, Property-based | High |
| A3.1–A3.7  | Encounter Plane | Unit, Property-based | High |
| A4.1–A4.10 | Probability Calc | Unit, Property-based | Critical |
| A5.1–A5.6  | Risk Scoring | Unit | High |
| A6.1–A6.7  | Integration | End-to-End | High |
| A7.1–A7.6  | Error Handling | Unit | Medium |
| A8.1–A8.5  | Validation | All Test Types | High |

---

## Acceptance Test Scenarios

### Scenario 1: Typical LEO Constellation (24-hour screening)

**Setup**:
- 100 LEO satellites (circular orbits, 500 km altitude, random inclinations)
- 24-hour screening window
- Standard filters and thresholds

**Expected Outcome**:
- 50–100 conjunctions flagged and ranked
- Top conjunction has Pc > 1e-5
- All conjunctions have valid Pc ∈ [0, 1]
- Processing time < 5 minutes

---

### Scenario 2: High-Risk Conjunction

**Setup**:
- Two satellites with miss_distance < 100 m
- Combined uncertainty σ ≈ 50 m
- Combined effective radius ≈ 5 m

**Expected Outcome**:
- Pc > 1e-3 (high risk)
- System flags for immediate maneuver consideration
- Detailed encounter plane geometry provided

---

### Scenario 3: Degenerate Case: Singular Covariance

**Setup**:
- Two satellites with tracking covariance eigenvalues: [1e-15, 1e-15, 1e-15, ...]
- Very small uncertainties (frozen tracking data)

**Expected Outcome**:
- System detects singularity and regularizes
- Pc computed with regularized covariance (conservative estimate)
- Warning logged for operator review

---

## Success Criteria

The conjunction assessment module is **complete** when:

1. ✓ All 8 requirement groups (A1–A8) have passing acceptance tests
2. ✓ Property-based tests cover all main algorithms (>90% coverage)
3. ✓ End-to-end benchmark: N=10,000 processed in <10 minutes
4. ✓ Comparison with reference data (NASA/ESA conjunctions) shows <5% Pc deviation
5. ✓ Design documentation explains all assumptions and limitations
6. ✓ Logging provides operators visibility into screening process
7. ✓ Error handling robust against edge cases and bad data

