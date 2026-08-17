# Requirements Document: Orbital Mechanics Core

## Overview

This requirements document derives from the design.md specification for the orbital mechanics core module. It formalizes acceptance criteria that establish what the implementation must accomplish: fast and accurate orbit propagation with perturbations, STM computation for uncertainty evolution, and reliable covariance propagation for collision probability estimation.

---

## Requirement 1: Kepler's Equation Solver

### 1.1 Convergence and Accuracy

**Requirement**: The Kepler's equation solver must compute eccentric anomaly E satisfying M = E - e·sin(E) to within machine precision for all valid orbits.

**Acceptance Criteria**:
- For any valid mean anomaly M (any real value) and eccentricity 0 ≤ e < 1:
  - Solver converges in ≤ 50 Newton-Raphson iterations
  - Residual |E - e·sin(E) - M| < 1e-12 (or machine epsilon)
  - Returned E is in [0, 2π)
- For e = 0 (circular orbit): E = M (analytically trivial case works correctly)
- For e → 1 (near-parabolic): Solver still converges (may need more iterations)

**Verification Method**: Unit test with known solutions (e.g., M=0 → E=0, M=π → E=π)

---

### 1.2 Efficiency

**Requirement**: Kepler solver must execute in real-time for trajectory prediction in the collision avoidance pipeline.

**Acceptance Criteria**:
- Solve time ≤ 100 µs per call (typical: 10-50 µs)
- Newton-Raphson iterations typically ≤ 8 for LEO orbits
- No dynamic memory allocation per call

**Verification Method**: Benchmark on target hardware; profile typical LEO scenarios

---

### 1.3 Numerical Stability

**Requirement**: Solver must handle edge cases without divergence or numerical instability.

**Acceptance Criteria**:
- Works correctly for e = 0 (division by 1 - e·cos(E) is safe)
- Works correctly for e ≈ 1 (initial guess adapts to avoid parabolic singularities)
- No overflow/underflow of intermediate values
- Returns finite E (no NaN/Inf)

**Verification Method**: Property-based testing with random (M, e) pairs

---

## Requirement 2: Perturbation Acceleration Models

### 2.1 J2 Oblateness Perturbation

**Requirement**: J2 perturbation must model Earth's equatorial bulge effect on orbit dynamics.

**Acceptance Criteria**:
- Acceleration formula: a_J2 = -(3/2)·J2·μ·R_E²/r⁵ · [x(1-5z²/r²), y(1-5z²/r²), z(3-5z²/r²)]
- J2 = 1.08263 × 10⁻³ (Earth's actual oblateness coefficient)
- For LEO (400 km altitude): magnitude ~ 1e-4 km/s²
- Dominant effect: causes apsidal precession and node regression
- Algorithm must compute all three components (x, y, z)

**Verification Method**: 
- Analytical solution: Compare against published ephemerides (e.g., SGP4)
- Known effect: ~10°/day node precession for sun-synchronous orbits

---

### 2.2 Atmospheric Density Model

**Requirement**: Drag acceleration must use realistic atmospheric density that varies with altitude.

**Acceptance Criteria**:
- Density modeled as exponential in altitude bands (100-1000 km)
- At 100 km: ρ ≈ 5.297 × 10⁻⁷ kg/m³
- At 400 km: ρ ≈ 3.725 × 10⁻¹² kg/m³
- Below 100 km or above 1000 km: drag = 0 (negligible)
- No density for satellite position below Earth surface

**Verification Method**: Compare against NRLMSISE-00 reference model at reference points

---

### 2.3 Atmospheric Drag Calculation

**Requirement**: Drag acceleration must account for satellite velocity relative to Earth's rotating atmosphere.

**Acceptance Criteria**:
- Formula: a_drag = -(1/2)·ρ·Cd·(A/m)·|v_rel|·v_rel
- v_rel = v_eci - (ω_earth × r) (inertial velocity - atmospheric velocity)
- ω_earth = 7.2921159 × 10⁻⁵ rad/s (Earth's rotation rate)
- For LEO cubesat (m=3kg, A=0.1m², Cd=2.2): ~1e-5 km/s² at 400 km
- Drag always opposes motion (negative dot product with velocity)

**Verification Method**: 
- Orbital decay rate for ISS: ~1-2 km/year at 400 km; algorithm should predict similar decay
- Direction check: a_drag · v < 0 always

---

### 2.4 Solar Radiation Pressure (Optional High-Fidelity)

**Requirement**: SRP acceleration must model photon momentum transfer (optional for code paths).

**Acceptance Criteria**:
- Formula: a_SRP = -P_SR · Cr · (A/m) · r̂_sun
- P_SR = 4.56 × 10⁻⁶ N/m² (solar pressure at 1 AU)
- Cr = reflectivity coefficient (1 = absorber, 2 = perfect reflector, typically 1.5)
- Sun direction computed from current state (or provided externally)
- Earth shadow check: return 0 if satellite in Earth shadow (simple cylindrical model)
- For GEO: ~1e-7 km/s²; for LEO: negligible

**Verification Method**: GEO orbit analysis; SRP-induced libration

---

### 2.5 Perturbation Selectivity

**Requirement**: Each perturbation must be independently toggleable for flexibility in propagation fidelity.

**Acceptance Criteria**:
- Function parameters: `include_j2`, `include_drag`, `include_srp` (all boolean)
- When False, that perturbation contributes 0 to acceleration
- Two-body gravity always included (cannot disable)
- Default: J2=True, drag=True, SRP=False (typical LEO setup)

**Verification Method**: Test with each perturbation toggled on/off; verify acceleration magnitude

---

## Requirement 3: Numerical Integration

### 3.1 Accuracy and Convergence

**Requirement**: Numerical integration must provide high-fidelity trajectory prediction.

**Acceptance Criteria**:
- Integrator method: RK78 (Runge-Kutta 7th/8th order, embedded error control)
- Relative tolerance: rtol ≤ 1e-10 (user-specified, typically 1e-10)
- Absolute tolerance: atol ≤ 1e-12 [km, km/s] (user-specified)
- Energy conservation (two-body): |ΔE|/E₀ < 1e-8 over one propagation
- Local truncation error controlled adaptively; solver adjusts step size

**Verification Method**: Energy conservation test; compare vs. analytical solutions (Kepler)

---

### 3.2 Robustness

**Requirement**: Integration must handle diverse orbit regimes and propagation times.

**Acceptance Criteria**:
- Works for LEO (circular, a ≈ 6,800 km)
- Works for GEO (highly elliptical on propagation near periapsis)
- Works for hyperbolic escape trajectories (should detect and handle gracefully)
- Maximum step size configurable: default max_step = 60 seconds
- Forward and backward (negative dt) propagation both supported

**Verification Method**: Test suite covering LEO, GEO, elliptical transfer orbits

---

### 3.3 Event Detection and Stopping

**Requirement**: Integration must support optional event detection (apogee, perigee, etc.).

**Acceptance Criteria**:
- No hard requirement for event detection in Phase 1
- Architecture must allow adding event functions without redesign
- Currently: propagate for specified dt and return final state

**Verification Method**: Integration framework supports event parameter (even if unused)

---

## Requirement 4: State Transition Matrix (STM)

### 4.1 STM Computation

**Requirement**: STM must accurately encode sensitivity of final state to initial state perturbations.

**Acceptance Criteria**:
- STM Φ(t, t₀) satisfies: Φ̇ = F·Φ where F = ∂f/∂X (Jacobian of dynamics)
- Integrated alongside state using same ODE solver (RK78)
- Initial condition: Φ(t₀, t₀) = I₆ (6×6 identity)
- For two-body Kepler: STM is symplectic (det(Φ) ≈ 1)
- Numerical error bounded: |Φ_computed - Φ_analytical| < 1e-8 (for circular orbits)

**Verification Method**: Compare vs. analytical STM for Kepler orbit; finite-difference validation

---

### 4.2 STM-State Consistency

**Requirement**: STM must correctly map initial perturbations to final state perturbations.

**Acceptance Criteria**:
- For small δX₀: δX_final ≈ Φ · δX₀ (linearization property)
- Quadratic convergence: error ∝ |δX₀|²
- Residual |δX_final - Φ · δX₀| < 1e-9 · |δX₀| for |δX₀| < 0.1 km

**Verification Method**: Finite-difference STM; compare analytical vs. numerical

---

### 4.3 Jacobian Accuracy

**Requirement**: Jacobian F must be computed accurately for STM integration.

**Acceptance Criteria**:
- Two-body gravity gradient: G = -μ/r³ · I + 3μ/r⁵ · (r⊗r)
- J2 gravity gradient: Approximate form with diagonal dominance
- Derivatives are continuous and smooth (no discontinuities)
- Numerical Jacobian matches symbolic within 1e-8 (finite-difference check)

**Verification Method**: Finite-difference Jacobian validation

---

## Requirement 5: Covariance Propagation

### 5.1 Covariance Evolution Formula

**Requirement**: Covariance must evolve via the standard formula using STM.

**Acceptance Criteria**:
- Formula: P(t) = Φ(t, t₀) · P(t₀) · Φ(t, t₀)ᵀ + Q(t, t₀)
- P(t₀) is 6×6 symmetric positive semi-definite (initial uncertainty)
- Q (process noise) is 6×6 symmetric positive semi-definite (optional)
- Result P(t) is symmetric and positive semi-definite
- Trace(P(t)) ≥ Trace(P(t₀)) (monotonic uncertainty growth)

**Verification Method**: Test with known covariance; verify PSD property via eigenvalues

---

### 5.2 Numerical Stability

**Requirement**: Covariance computation must remain stable despite matrix operations.

**Acceptance Criteria**:
- Result symmetrized: (P + Pᵀ)/2 to correct floating-point errors
- No eigenvalue can be negative (even by numerical error < 1e-14)
- Condition number remains bounded (not ill-conditioned)
- Double precision (float64) used throughout

**Verification Method**: Test with high-eccentricity orbits; monitor condition number

---

### 5.3 Process Noise Integration

**Requirement**: Process noise Q can model unmodeled accelerations over propagation interval.

**Acceptance Criteria**:
- Q is time-integrated unmodeled force covariance
- For atmospheric drag: σ_acc ~ 1e-9 km/s² (typical value)
- Q is optional (default None → no process noise added)
- Q can be user-provided (e.g., from uncertainty budget model)

**Verification Method**: Compare covariance growth with/without Q; validate against EKF theory

---

## Requirement 6: Coordinate Transformations

### 6.1 Classical Orbital Elements ↔ Cartesian State

**Requirement**: Must convert between COE and ECI Cartesian coordinates.

**Acceptance Criteria**:
- Forward (COE → State): Uses perifocal frame as intermediate
  - Compute radius: r = a(1-e²)/(1+e·cos(ν))
  - Compute velocity in PQW frame
  - Rotate via R3(-Ω)·R1(-i)·R3(-ω) transformation
- Reverse (State → COE): Solve for orbital elements from r, v
  - a from orbital energy: a = -μ/(2E_orbit)
  - e from specific angular momentum: h = r × v
  - i from h: i = arccos(h_z/|h|)
  - RAAN, ω, ν from angle calculations
- Round-trip accuracy: |COE_recovered - COE_original| < 1e-10

**Verification Method**: Round-trip test; compare against known COE↔State conversions

---

### 6.2 RTN (Relative) Frame Transformation

**Requirement**: Must transform to RTN frame for maneuver planning and conjunction analysis.

**Acceptance Criteria**:
- RTN frame definition:
  - R̂ = r/|r| (radial outward)
  - N̂ = (r×v)/|r×v| (normal, along angular momentum)
  - T̂ = N̂ × R̂ (transverse)
- Transformation matrix M_rtn: 3×3, orthonormal (M·Mᵀ = I)
- Converts ECI state: r_rtn = M·r_eci, v_rtn = M·v_eci
- For circular orbits: T̂ ≈ v/|v| (transverse = velocity direction)

**Verification Method**: Orthonormality test; comparison with published transformations

---

### 6.3 Rotation Matrices

**Requirement**: Must provide elementary rotation matrices for coordinate transforms.

**Acceptance Criteria**:
- Rotation about X-axis (pitch): R_x(θ) is 3×3 orthogonal
- Rotation about Z-axis (yaw): R_z(θ) is 3×3 orthogonal
- Composition: R_final = R_z(ω)·R_x(i)·R_z(raan) for COE rotation
- Inverse: R⁻¹ = Rᵀ (orthogonal matrix property)
- det(R) = 1 (proper rotation, no reflection)

**Verification Method**: Determinant check; inverse equals transpose

---

## Requirement 7: Propagation Interfaces

### 7.1 Single-Step Propagation

**Requirement**: Must propagate a single state vector forward by specified time.

**Acceptance Criteria**:
- Function: `propagate_state(state, dt, **kwargs) → StateVector`
- Input: valid StateVector at epoch t₀
- Output: StateVector at t₀ + dt
- dt can be positive (forward) or negative (backward)
- dt can be any real value (no artificial limits)
- Supports perturbation selection: include_j2, include_drag, include_srp
- Returns error if propagation fails (invalid state, NaN, solver error)

**Verification Method**: Test with various dt values; check round-trip accuracy

---

### 7.2 STM-Enabled Propagation

**Requirement**: Must propagate state AND STM simultaneously for efficiency.

**Acceptance Criteria**:
- Function: `propagate_with_stm(state, dt) → (StateVector, ndarray)`
- Returns both final state and 6×6 STM matrix
- STM accuracy matches STM-only computation
- More efficient than computing STM via finite differences
- Reduces computational load vs. separate propagations

**Verification Method**: Compare (state, STM) to separate propagate_state + finite-difference

---

### 7.3 Ephemeris Generation

**Requirement**: Must generate state trajectory at specified time points.

**Acceptance Criteria**:
- Function: `generate_ephemeris(state, times) → ndarray (N, 6)`
- Input: initial state, array of N time points
- Output: Nx6 array of [r, v] at each time
- Efficient: reuses ODE solution trajectory (t_eval parameter)
- No need to call propagate_state N times

**Verification Method**: Compare vs. repeated propagate_state calls; verify efficiency

---

### 7.4 Spacecraft Object Propagation

**Requirement**: Must propagate full spacecraft object including state and covariance.

**Acceptance Criteria**:
- Function: `propagate_spacecraft(spacecraft, dt) → (Spacecraft, STM)`
- Input: Spacecraft object (state + covariance + properties)
- Output: Updated Spacecraft with propagated state/covariance, plus STM
- Covariance updated: P_new = Φ·P·Φᵀ + Q
- Process noise Q automatically computed from propagation duration and spacecraft properties
- Supports all perturbation toggles

**Verification Method**: Integration test; verify state + covariance evolution consistency

---

## Requirement 8: Spacecraft Data Structure

### 8.1 State and Uncertainty

**Requirement**: Spacecraft object must encapsulate orbital state and uncertainty.

**Acceptance Criteria**:
- Fields: `state` (StateVector), `covariance` (6×6 matrix)
- state: position [km] and velocity [km/s] in ECI frame
- covariance: symmetric PSD matrix (uncertainties in state space)
- Both must be initialized and propagated together

**Verification Method**: Type checking; covariance symmetry tests

---

### 8.2 Physical Properties

**Requirement**: Spacecraft must store properties needed for propagation.

**Acceptance Criteria**:
- mass [kg]: Required for drag/SRP (area-to-mass ratio)
- area [m²]: Cross-sectional area (drag/SRP calculations)
- cd [dimensionless]: Drag coefficient (default 2.2)
- cr [dimensionless]: Reflectivity coefficient (default 1.5)
- Constraints: mass > 0, area > 0, cd > 0, cr > 0

**Verification Method**: Validation in constructor; reject invalid values

---

### 8.3 Operational Properties

**Requirement**: Spacecraft must track maneuver capability and identity.

**Acceptance Criteria**:
- id: Unique string identifier (e.g., "SAT001")
- name: Human-readable name (e.g., "CubeSat-A")
- delta_v_budget [m/s]: Total Δv available (e.g., 25.0)
- delta_v_used [m/s]: Δv already expended (e.g., 0.0)
- maneuverable: Boolean (can execute maneuvers or passive)
- Constraint: delta_v_used ≤ delta_v_budget always

**Verification Method**: Validation; maneuver planning checks budget constraint

---

## Requirement 9: Data Validation

### 9.1 StateVector Validation

**Requirement**: State vectors must represent physically valid orbital states.

**Acceptance Criteria**:
- r: Must be non-zero (not at Earth center)
- r: Must not be below Earth surface (|r| ≥ R_Earth)
- v: Must be finite (not NaN/Inf)
- r: Must be finite (not NaN/Inf)
- No orbital energy ≈ 0 (hyperbolic escape paths allowed but flagged)

**Verification Method**: Input validation in StateVector constructor

---

### 9.2 OrbitalElements Validation

**Requirement**: Classical orbital elements must satisfy physical constraints.

**Acceptance Criteria**:
- a > R_Earth: Semi-major axis must exceed Earth radius
- 0 ≤ e < 1: Eccentricity defines elliptical (bound) orbit
- 0 ≤ i ≤ π: Inclination non-negative by convention
- Angles (raan, omega, nu) normalized to [0, 2π)

**Verification Method**: Validation in OrbitalElements; unit tests for boundary cases

---

### 9.3 Covariance Validation

**Requirement**: Covariance matrices must be valid uncertainty representations.

**Acceptance Criteria**:
- Shape: 6×6 matrix
- Symmetry: P = Pᵀ (to numerical precision)
- Positive semi-definite: All eigenvalues ≥ 0
- Diagonal ≥ 0: Diagonal elements non-negative

**Verification Method**: Eigenvalue decomposition; PSD check

---

## Requirement 10: Performance and Resource Constraints

### 10.1 Propagation Speed

**Requirement**: Propagation must execute quickly for real-time collision avoidance.

**Acceptance Criteria**:
- Kepler propagation (analytical): ≤ 100 µs per call
- State propagation (numerical, ~10 min orbit): ≤ 10 ms
- STM propagation (same + 6×6 matrix math): ≤ 15 ms
- Ephemeris generation (1000 points): ≤ 500 ms
- Covariance propagation: ≤ 1 ms (just matrix math)

**Verification Method**: Benchmark suite; profile on target hardware

---

### 10.2 Memory Footprint

**Requirement**: Module must not require excessive memory.

**Acceptance Criteria**:
- StateVector: ~50 bytes
- Spacecraft: ~500 bytes (includes 6×6 covariance)
- Propagation workspace: ≤ 1 MB for a single integration
- No memory leaks over repeated propagations

**Verification Method**: Memory profiler; integration stress test

---

### 10.3 Numerical Precision

**Requirement**: Use standard double precision throughout.

**Acceptance Criteria**:
- All floating-point: float64 (64-bit IEEE)
- No single precision (float32) in core computation
- No loss of accuracy from mixed-precision operations

**Verification Method**: Type checking; precision validation tests

---

## Requirement 11: Error Handling and Robustness

### 11.1 Invalid Input Handling

**Requirement**: Module must reject or warn on invalid inputs.

**Acceptance Criteria**:
- Raise ValueError for invalid StateVector (r below Earth surface)
- Raise ValueError for invalid OrbitalElements (e ≥ 1)
- Raise ValueError for negative mass/area
- Graceful degradation: continue with 2-body if perturbation model fails

**Verification Method**: Unit test for each error condition

---

### 11.2 Numerical Failure Handling

**Requirement**: Propagation must report failures clearly.

**Acceptance Criteria**:
- Raise RuntimeError if ODE solver fails (non-convergence, NaN)
- Includes solver diagnostic message
- No silent failures or undefined behavior

**Verification Method**: Stress test with pathological cases

---

### 11.3 Logging and Diagnostics

**Requirement**: Optional logging for debugging and monitoring.

**Acceptance Criteria**:
- Debug mode: Optional logging of propagation steps, solver info
- Performance metrics: Optional timing information
- No logging in production performance-critical paths by default

**Verification Method**: Integration with logging framework; optional flags

---

## Requirement 12: Integration with Collision Avoidance Pipeline

### 12.1 Maneuver Sensitivity

**Requirement**: STM must enable maneuver effectiveness computation.

**Acceptance Criteria**:
- For a planned conjunction at time TCA:
  - Maneuver time: t_man (before TCA)
  - STM from t_man to TCA: Φ(TCA, t_man)
  - Position change from Δv: Δr ≈ Φ[0:3, 3:6](TCA, t_man) · Δv
  - This is used for collision avoidance planning

**Verification Method**: Integration test with conjunction analysis module

---

### 12.2 Covariance for Probability Computation

**Requirement**: Propagated covariance feeds into collision probability estimation.

**Acceptance Criteria**:
- Covariance P(TCA) at time of conjunction
- Relative position covariance (2D projected onto encounter plane)
- Used by conjunction module to compute Pc (probability of collision)

**Verification Method**: Integration test with conjunction probability module

---

### 12.3 Ephemeris for Trajectory Search

**Requirement**: Ephemerides must support trajectory optimization searches.

**Acceptance Criteria**:
- generate_ephemeris must produce smooth trajectories
- High time resolution: ≥ 100 points per orbit
- Used for visualization and trajectory searching

**Verification Method**: Integration test with optimization module

---

## Requirement 13: Testing and Validation

### 13.1 Unit Test Coverage

**Requirement**: Core functions must have comprehensive unit tests.

**Acceptance Criteria**:
- Kepler solver: ≥ 10 test cases (circular, elliptical, high-e)
- Each perturbation model: ≥ 5 test cases
- Coordinate transforms: ≥ 10 test cases
- Data structures: ≥ 5 validation tests
- Target: ≥ 80% code coverage

**Verification Method**: pytest suite; coverage report

---

### 13.2 Property-Based Testing

**Requirement**: Use generative testing to find edge cases.

**Acceptance Criteria**:
- Kepler equation satisfaction: 1000 random (M, e) pairs
- Energy conservation: 100 random orbit propagations
- STM invertibility: 100 random STM generations
- Covariance PSD: 100 random propagations

**Verification Method**: Hypothesis/fast-check property tests

---

### 13.3 Integration Testing

**Requirement**: Multi-component scenarios must work correctly.

**Acceptance Criteria**:
- Multi-step propagation: Verify temporal continuity
- Spacecraft + perturbations: LEO decay scenario
- Maneuver + STM: Collision avoidance case study
- Round-trip: Forward-backward propagation consistency

**Verification Method**: Integration test suite

---

## Requirement 14: Documentation and API

### 14.1 API Documentation

**Requirement**: All public functions must be documented.

**Acceptance Criteria**:
- Docstrings for all functions (purpose, parameters, returns)
- Type hints for all function signatures
- Example usage for key functions
- Preconditions and postconditions documented

**Verification Method**: Documentation review; docstring validation

---

### 14.2 Algorithm Documentation

**Requirement**: Core algorithms must be documented with references.

**Acceptance Criteria**:
- Kepler solver: Algorithm + Newton-Raphson details
- Perturbation models: Physics and formulas
- STM propagation: Jacobian computation details
- Covariance propagation: Linear estimation theory

**Verification Method**: Design document completeness

---

## Acceptance Criteria Summary Table

| Req | Feature | Acceptance Criterion | Priority |
|-----|---------|----------------------|----------|
| 1.1 | Kepler Solver Convergence | Residual < 1e-12, ≤ 50 iterations | CRITICAL |
| 1.2 | Kepler Solver Speed | ≤ 100 µs per call | HIGH |
| 2.1 | J2 Perturbation | Formula accurate, ≈ 1e-4 km/s² for LEO | CRITICAL |
| 2.2 | Atmospheric Density | Exponential model, validated vs. NRLMSISE | CRITICAL |
| 2.3 | Atmospheric Drag | Earth rotation correction, decay verification | CRITICAL |
| 2.4 | Solar Radiation Pressure | Optional, correct for GEO | MEDIUM |
| 2.5 | Perturbation Selectivity | Toggleable: J2, drag, SRP | HIGH |
| 3.1 | Numerical Integration Accuracy | rtol=1e-10, atol=1e-12, energy error < 1e-8 | CRITICAL |
| 3.2 | Numerical Integration Robustness | Works LEO/GEO/elliptical, forward/backward | HIGH |
| 4.1 | STM Computation | det(Φ) ≈ 1, accuracy < 1e-8 | CRITICAL |
| 4.2 | STM-State Consistency | δX_final ≈ Φ·δX_initial, quadratic error | HIGH |
| 5.1 | Covariance Evolution | P(t) = Φ·P(t₀)·Φᵀ + Q, monotonic growth | CRITICAL |
| 5.2 | Covariance Stability | Symmetric PSD, no negative eigenvalues | HIGH |
| 6.1 | COE ↔ Cartesian Conversion | Round-trip error < 1e-10 | HIGH |
| 6.2 | RTN Frame Transformation | Orthonormal, correct orientation | HIGH |
| 7.1 | Single-Step Propagation | propagate_state(state, dt) works | CRITICAL |
| 7.2 | STM-Enabled Propagation | propagate_with_stm(state, dt) efficient | HIGH |
| 7.3 | Ephemeris Generation | Smooth trajectories, reuses ODE solution | MEDIUM |
| 7.4 | Spacecraft Propagation | State + covariance together | HIGH |
| 8.1-8.3 | Spacecraft Data Structure | All fields required, validation enforced | HIGH |
| 9.1-9.3 | Data Validation | Type checks, physical constraints | MEDIUM |
| 10.1 | Propagation Speed | ≤ 15 ms for STM, ≤ 10 ms for state | HIGH |
| 10.2 | Memory Footprint | ≤ 500 bytes per Spacecraft, ≤ 1 MB workspace | MEDIUM |
| 11.1 | Invalid Input Handling | Raise ValueError with clear message | MEDIUM |
| 11.2 | Numerical Failure Handling | Raise RuntimeError with diagnostic | MEDIUM |
| 12.1 | Maneuver Sensitivity | STM computes Δr from Δv | CRITICAL |
| 12.2 | Covariance for Probability | P propagates to encounter epoch | CRITICAL |
| 13.1 | Unit Test Coverage | ≥ 80% code coverage | HIGH |
| 13.2 | Property-Based Testing | 1000+ random test cases per property | HIGH |
| 14.1 | API Documentation | Docstrings + examples | MEDIUM |
| 14.2 | Algorithm Documentation | Formulas + references | MEDIUM |

