# Development Practices & Guidelines

## Project Structure & Organization

This satellite collision prevention system is organized by **problem domain** rather than by layer. Each module handles a specific aspect of the overall solution:

- **Physics layer:** `orbital_mechanics.py`, `conjunction.py` — Core simulation
- **Decision layer:** `avoidance.py`, `damage_minimization.py`, `risk_optimizer.py` — Strategy selection
- **Integration layer:** `api.py`, `simulation.py`, `ai_analysis.py` — Orchestration and exposure
- **Utilities:** `utils.py` — Constants, transforms, helpers

### Dependency Graph

```
orbital_mechanics.py (no deps on other src modules)
    ↓
conjunction.py (uses orbital_mechanics)
    ↓
avoidance.py (uses orbital_mechanics, conjunction)
    ↓
damage_minimization.py (uses orbital_mechanics)
    ↓
risk_optimizer.py (uses all above, plus NetworkX, cuopt_client)
    ↓
ai_analysis.py (uses conjunction, risk_optimizer, OpenAI)
    ↓
simulation.py (orchestrates everything)
    ↓
api.py (exposes simulation state)
```

**Rule:** Only import downstream (lower in the graph). Never create circular dependencies.

### Module Responsibilities

| Module | Responsibility | Key Functions | External Deps |
|--------|-----------------|----------------|---------------|
| `orbital_mechanics.py` | Orbit propagation & STM | `propagate_state()`, `propagate_covariance()`, `state_to_elements()`, `elements_to_state()` | NumPy, SciPy |
| `conjunction.py` | Risk detection & assessment | `screen_conjunctions()`, `compute_tca()`, `compute_probability_of_collision()` | NumPy, orbital_mechanics |
| `avoidance.py` | Maneuver planning | `plan_avoidance_maneuver()`, `compute_optimal_delta_v()`, `evaluate_maneuver_sequence()` | NumPy, SciPy, orbital_mechanics |
| `damage_minimization.py` | Debris & cascade modeling | `estimate_debris()`, `compute_cascade_risk()`, `evaluate_damage_scenarios()` | NumPy, orbital_mechanics |
| `risk_optimizer.py` | Global optimization | `optimize_greedy()`, `optimize_network_flow()`, `optimize_mcts()` | NetworkX, cuopt_client, all above |
| `ai_analysis.py` | LLM-powered insights | `analyze_conjunction()`, `recommend_maneuver()`, `assess_orbital_environment()` | OpenAI, all above |
| `simulation.py` | Main event loop | `run_simulation()`, `step()`, `get_state()` | All above |
| `api.py` | REST endpoints | Flask routes: `/risk`, `/conjunctions`, `/maneuvers` | Flask, simulation |
| `cuopt_client.py` | Optimization solver interface | `solve_vehicle_routing()`, `solve_allocation()` | Requests, External CuOpt API |
| `utils.py` | Shared utilities | Constants, transforms, helpers | NumPy |



## Making Code Changes

### Before You Start

1. **Understand the context:** Read the relevant section in #[[file:docs/physics.md]] if touching orbital mechanics
2. **Identify dependencies:** Check what other modules import your target file (see Dependency Graph above)
3. **Check for tests:** Look for validation code in the simulation; understand how it's being tested today
4. **Trace the data flow:** Follow input → output through relevant modules

### Physics-Heavy Changes (orbital_mechanics, conjunction)

For modifications to orbit propagation, conjunction assessment, or risk calculations:

1. **Document the math:** Add comments referencing equations or publications
2. **Validate assumptions:** Check against known test cases (two-line elements, published conjunction data)
3. **Test edge cases:** High eccentricity orbits, near-polar trajectories, resonant formations
4. **Cross-reference:** Ensure your changes don't break cascade effects downstream (e.g., conjunction changes affect risk_optimizer)
5. **Verify conservation:** Energy/momentum conservation in relevant calculations

**Testing approach for physics changes:**
```python
# Before making changes, run baseline
baseline_conjunction = simulation.screen_conjunctions(test_epoch)
baseline_risk = simulation.compute_total_risk()

# After making changes, compare
new_conjunction = simulation.screen_conjunctions(test_epoch)
new_risk = simulation.compute_total_risk()

# Check: differences should be explainable by your change
assert abs(new_risk - baseline_risk) < expected_delta, "Unexpected risk change"
```

### Optimization Changes (risk_optimizer, cuopt_client)

When modifying the global optimizer or adding new optimization strategies:

1. **Understand the problem formulation:** How does your strategy minimize the objective?
2. **Test on small problems:** 20-50 objects with known optimal solutions
3. **Benchmark against baseline:** Compare solution quality and solve time against greedy/network-flow
4. **Check scaling:** Test with 1000, 5000, 10000 objects to verify O(n) complexity claims
5. **Validate constraints:** Ensure fuel budgets, TCA deadlines, and other constraints are respected

### API & Dashboard Changes

1. **Maintain backward compatibility** where possible (or version endpoints)
2. **Document new endpoints** with example requests/responses in code comments
3. **Test CORS configuration** if adding new routes
4. **Validate data contracts** between backend and frontend (especially coordinate systems — always ECI)
5. **Add error handling** with meaningful HTTP status codes and error messages

**API endpoint template:**
```python
@app.route('/api/<resource>', methods=['GET', 'POST'])
def get_resource():
    """
    GET /api/<resource> — Retrieve <resource> data
    
    Response (200 OK):
    {
        'status': 'success',
        'data': [...]  # coordinate system: ECI
    }
    
    Response (400 Bad Request):
    {
        'status': 'error',
        'message': 'Invalid parameter: X'
    }
    """
    try:
        # Validation
        # Logic
        # Return
    except ValueError as e:
        return {'status': 'error', 'message': str(e)}, 400
```

### Adding New Features

**Feature workflow:**
1. Define the physics/algorithm clearly with reference to docs or publications
2. Identify which module(s) need changes
3. Implement with minimal scope (don't refactor unrelated code)
4. Test with realistic scenarios (use existing simulation data)
5. Document in code and steering docs
6. Update relevant docstrings and comments

**Example: Adding a new avoidance strategy**
- Implement function in `avoidance.py`
- Add to strategy selection logic in `conjunction.py` or `risk_optimizer.py`
- Create test case with known high-risk conjunction
- Document delta-v requirements and effectiveness assumptions
- Update #[[file:docs/strategy.md]] if decision logic changes



## Code Quality Standards

### Type Hints
Use type hints for function signatures where practical:
```python
def calculate_conjunction_probability(
    r1: np.ndarray,
    v1: np.ndarray,
    cov1: np.ndarray,
    r2: np.ndarray,
    v2: np.ndarray,
    cov2: np.ndarray,
    hard_body_radius: float = 10.0
) -> float:
    """Calculate probability of collision between two objects."""
```

### Constants & Configuration
- All physical constants in `utils.py` with clear documentation
- Orbital parameters (earth radius, gravitational constant, etc.)
- Threshold values (Pc thresholds, maneuver limits, risk levels)

### Coordinate Systems
- **Backend:** Always ECI (Earth-Centered Inertial) unless explicitly noted
- **API responses:** Include coordinate system in documentation
- **Conversions:** Keep at boundaries (input validation, API responses)

### Error Handling
- Validate input ranges (orbital elements, covariance matrices)
- Return meaningful error messages with context
- Log warnings for unusual but valid scenarios (high eccentricity, unexpected timing)

## Testing & Validation

### Validation Approach
Since this is a physics simulation, validation differs from typical unit tests:

1. **Known scenarios:** Run against published conjunction data; verify Pc estimates
2. **Physical consistency:** Check that energy/momentum are conserved in relevant calculations
3. **Numerical stability:** Test with extreme orbital elements (very high/low altitude, high eccentricity)
4. **Regression testing:** Periodically validate against baseline results

### Running Verification
```bash
# Start the simulation (includes basic validation checks)
python -m src.simulation

# Check simulation output and dashboard for anomalies
# Verify conjunctions are detected correctly
# Confirm risk calculations are reasonable
```

## Common Patterns

### Accessing Orbital Constants
```python
from src.utils import EARTH_RADIUS, MU_EARTH, DEG_TO_RAD

# Use constants for calculations
semi_major_axis = (MU_EARTH / (mean_motion ** 2)) ** (1/3)
```

### Working with State Vectors
```python
# State vectors are [x, y, z, vx, vy, vz] in ECI coordinates (meters, m/s)
position = state[:3]
velocity = state[3:6]

# Covariance is 6x6 matrix in same coordinate system
cov_r = cov[:3, :3]  # Position covariance
cov_v = cov[3:6, 3:6]  # Velocity covariance
```

### Propagating Orbits
```python
from src.orbital_mechanics import propagate_state

# Propagate from current epoch for 24 hours
dt_seconds = 24 * 3600
new_state = propagate_state(current_state, dt_seconds, perturbations=True)
```

## Documentation Standards

### Inline Documentation
- **Functions:** Docstring with inputs, outputs, units, coordinate system
- **Complex logic:** Comments explaining the "why" with formula references
- **Constants:** Document units and source (reference paper, physics constant, empirical)

### Example
```python
def calculate_probability_of_collision(
    r1: np.ndarray,
    v1: np.ndarray,
    cov1: np.ndarray,
    r2: np.ndarray,
    v2: np.ndarray,
    cov2: np.ndarray,
    hard_body_radius: float = 10.0
) -> float:
    """
    Calculate probability of collision between two spacecraft.
    
    Uses covariance ellipsoid approach from [Reference: NASA Breakup Model].
    
    Args:
        r1, r2: Position vectors in ECI (meters)
        v1, v2: Velocity vectors in ECI (m/s)
        cov1, cov2: 6x6 covariance matrices in ECI
        hard_body_radius: Combined hard-body radius (meters)
    
    Returns:
        Probability of collision (0-1)
    
    Notes:
        - Assumes Gaussian error distribution
        - Valid for short encounter timescales (< 1 hour)
        - Reference: Conjunction Assessment Risk Analysis (CARA)
    """
```

## Debugging Tips

### Enable Verbose Output
Add logging to trace execution:
```python
import logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

logger.debug(f"Conjunction detected at t={encounter_time}, Pc={probability}")
logger.info(f"Maneuver planned: Δv={delta_v}m/s at t={burn_time}")
logger.warning(f"Covariance trace exceeds threshold: {np.trace(cov)}")
logger.error(f"Invalid state vector: NaN detected at index {np.where(np.isnan(state))}")
```

### Inspection Points

**Orbit Propagation Issues:**
```python
# Check position after propagation
state_before = spacecraft.state.copy()
state_after = propagate_state(state_before, dt, perturbations=True)

# Sanity checks:
assert np.all(np.isfinite(state_after)), "Non-finite state detected"
r = np.linalg.norm(state_after[:3])
assert r > EARTH_RADIUS, f"Crashed: r={r} < R_earth={EARTH_RADIUS}"
v = np.linalg.norm(state_after[3:6])
assert v_circular - 2 < v < v_escape, f"Unphysical velocity: v={v}"
```

**Conjunction Detection:**
```python
# Verify TCA is actually closest approach
t_before = tca - 10  # 10 seconds before
t_after = tca + 10

r_before = np.linalg.norm(state1(t_before)[:3] - state2(t_before)[:3])
r_at_tca = np.linalg.norm(state1(tca)[:3] - state2(tca)[:3])
r_after = np.linalg.norm(state1(t_after)[:3] - state2(t_after)[:3])

assert r_at_tca <= min(r_before, r_after), "TCA is not minimum distance"
```

**Covariance Matrix:**
```python
# Check positive-definiteness
eigenvalues = np.linalg.eigvals(covariance)
assert np.all(eigenvalues > 0), f"Non-PD covariance: eigs={eigenvalues}"

# Check trace grows but stays reasonable
trace_before = np.trace(cov_t0)
trace_after = np.trace(cov_t1)
assert trace_after > trace_before, "Uncertainty should increase over time"
assert trace_after < 1e10, "Uncertainty grew unreasonably large"
```

### Common Issues & Solutions

**Problem:** Conjunctions not being detected
- **Check 1:** Conjunction time window size in `conjunction.py` — may be too small
- **Check 2:** Minimum Pc threshold value in `risk_optimizer.py` — may be too high
- **Check 3:** Verify both objects' covariance matrices are positive-definite
- **Check 4:** Run screen_conjunctions() with debug output enabled

**Problem:** Risk scores seem unrealistic (too high or too low)
- **Verify:** Debris model assumptions in `damage_minimization.py` (mass, velocity)
- **Check:** Cascade effects in `risk_optimizer.py` — are future conjunctions being propagated?
- **Confirm:** State propagation accuracy — perturbations enabled? STM calculation correct?
- **Inspect:** Probability of collision calculation — covariance conditioning issue?

**Problem:** Maneuvers not reducing risk as expected
- **Check:** STM calculation correctness at maneuver time
- **Verify:** Delta-v direction optimization (should be along miss gradient)
- **Inspect:** Timing — is maneuver far enough before TCA?
- **Test:** With synthetic case: known initial miss, known Δv, verify final miss change

**Problem:** Dashboard not updating
- **Check 1:** Flask API is running and accessible (curl http://localhost:5000/api/risk)
- **Check 2:** CORS headers in `api.py` response (should include Access-Control-Allow-Origin)
- **Check 3:** Browser console for fetch errors
- **Ensure:** Simulation is writing to API endpoints (add logging to /api/<endpoint>)
- **Verify:** JSON response format matches frontend expectations

**Problem:** Out-of-memory with large constellation
- **Profile:** Use `memory_profiler` to identify hotspots
- **Reduce:** Constellation size or propagation window for testing
- **Consider:** GPU acceleration (CuOpt) for screening step
- **Optimize:** Covariance storage (symmetric matrices can be compressed)

### Profiling Performance

```bash
# Time a particular function
import time
t0 = time.time()
result = conjunction.screen_conjunctions(epoch, all_pairs)
elapsed = time.time() - t0
print(f"Screening took {elapsed:.2f}s for {len(all_pairs)} pairs")

# Profile memory usage
from memory_profiler import profile

@profile
def expensive_function():
    # ... code here
    pass

# Run with: python -m memory_profiler script.py
```

### Debug Mode for Simulation

Add debug flags to `simulation.py`:

```python
DEBUG = True
VERBOSE = True
SAVE_INTERMEDIATES = True

if DEBUG:
    logger.setLevel(logging.DEBUG)
    
if VERBOSE:
    print(f"Epoch: {epoch}, N_conjunctions: {len(conjunctions)}")
    print(f"Risk score: {total_risk:.6f}")
    
if SAVE_INTERMEDIATES:
    np.save(f"state_epoch_{epoch}.npy", all_states)
    np.save(f"cov_epoch_{epoch}.npy", all_covariances)
```



## Deployment & Operations

### Running in Production
```bash
# Run with output logging
python -m src.simulation > simulation.log 2>&1 &

# Monitor the simulation
tail -f simulation.log

# Access dashboard at http://localhost:5000
```

### Key Metrics to Monitor
- Conjunction detection rate (should match historical patterns)
- Average risk scores (should decrease after interventions)
- API response times (should stay < 500ms for typical queries)
- Memory usage (simulation with 10k+ objects can be memory-intensive)

## Resources & References

- **Physics Reference:** #[[file:docs/physics.md]]
- **Strategy Reference:** #[[file:docs/strategy.md]]
- **README:** #[[file:README.md]]
- **Requirements:** #[[file:requirements.txt]]
