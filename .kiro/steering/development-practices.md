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
2. **Identify dependencies:** Check what other modules import your target file
3. **Check for tests:** Look for validation code in the simulation; understand how it's being tested today

### Physics-Heavy Changes

For modifications to orbital mechanics, conjunction assessment, or risk calculations:

1. **Document the math:** Add comments referencing equations or publications
2. **Validate assumptions:** Check against known test cases (two-line elements, published conjunction data)
3. **Test edge cases:** High eccentricity orbits, near-polar trajectories, resonant formations
4. **Cross-reference:** Ensure your changes don't break cascade effects downstream (e.g., conjunction changes affect risk_optimizer)

### API & Dashboard Changes

1. **Maintain backward compatibility** where possible
2. **Document new endpoints** with example requests/responses in code comments
3. **Test CORS configuration** if adding new routes
4. **Validate data contracts** between backend and frontend (especially coordinate systems)

### Adding New Features

**Feature workflow:**
1. Define the physics/algorithm clearly with reference to docs or publications
2. Implement in appropriate module (don't create new modules without discussion)
3. Integrate into the main simulation loop or add API endpoint
4. Test with realistic scenarios (use existing simulation data)
5. Document in code and steering docs

**Example: Adding a new avoidance strategy**
- Implement function in `avoidance.py`
- Add to strategy selection logic in `conjunction.py` or `risk_optimizer.py`
- Create test case with known high-risk conjunction
- Document delta-v requirements and effectiveness assumptions

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
```

### Common Issues

**Problem:** Conjunctions not being detected
- Check: Conjunction time window size in `conjunction.py`
- Check: Minimum Pc threshold value in `risk_optimizer.py`
- Verify: Both objects' covariance matrices are positive-definite

**Problem:** Risk scores seem unrealistic
- Verify: Debris model assumptions in `damage_minimization.py`
- Check: Cascade effects in `risk_optimizer.py` (are future conjunctions being propagated?)
- Confirm: State propagation accuracy (perturbations enabled?)

**Problem:** Dashboard not updating
- Check: Flask API is running and accessible
- Verify: CORS headers in `api.py`
- Check: Browser console for fetch errors
- Ensure: Simulation data is being written to API endpoints

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
