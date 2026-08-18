# Technical Stack & Technology Guide

## Core Technology Selection

### Why These Technologies?

**Python 3.8+**
- Choice for scientific computing (NumPy/SciPy ecosystem unmatched)
- Rapid prototyping for orbital mechanics algorithms
- Easy integration with C/Fortran for performance-critical sections
- Excellent debugging and iterative development

**NumPy & SciPy**
- NumPy: Vectorized operations on orbital states (6×10,000 = 60k state variables)
- SciPy: Numerical integrators (RK78), optimization algorithms, linear algebra
- Both are battle-tested in aerospace/scientific computing
- BLAS/LAPACK backends provide performance

**Flask**
- Lightweight REST framework (minimal overhead)
- Easy to prototype API endpoints
- WebSocket support for real-time dashboard updates (future enhancement)
- Debugging and development server built-in

**NetworkX**
- Graph representation of conjunction dependencies
- Built-in algorithms for min-cost flow (optimal maneuver allocation)
- Intuitive API for risk network analysis

**OpenAI API**
- GPT-4/3.5-turbo for natural language analysis
- Function calling for agentic workflows (future)
- No need to host LLM locally (cost-effective for prototype)

**Three.js**
- WebGL rendering in browser (no plugin installation)
- Standard library for 3D visualization in web
- Good performance for 10k+ object visualization

## Dependency Specifications

### Production Dependencies

```
numpy>=1.24.0
  ├─ Why >=1.24: Performance improvements, better error handling
  ├─ Constraint: Python 3.8+
  └─ Usage: All orbital state vectors, matrix operations

scipy>=1.10.0
  ├─ Why >=1.10: New ODE solver IVP interface, improved optimization
  ├─ Key modules: scipy.integrate, scipy.optimize, scipy.linalg
  └─ Usage: Orbit propagation, encounter geometry

matplotlib>=3.7.0
  ├─ Why >=3.7: Better rendering, improved animation
  ├─ Usage: Trajectory plots, risk timeline visualizations
  └─ Note: Not required for API-only deployment

networkx>=3.0
  ├─ Why >=3.0: Better performance, cleaner API
  ├─ Key functions: min_cost_flow(), connected_components()
  └─ Usage: Risk network analysis, maneuver sequencing

flask>=3.0.0
  ├─ Why >=3.0: Performance, async support readiness
  ├─ Required extensions: flask-cors
  └─ Usage: REST API, static file serving

flask-cors>=4.0.0
  ├─ Purpose: Handle Cross-Origin requests from dashboard
  └─ Config: Allow localhost:5000 → browser requests

openai>=1.0.0
  ├─ Why >=1.0: Stable API, function calling support
  ├─ Requires: OPENAI_API_KEY environment variable
  └─ Usage: LLM analysis, conjunction insights

requests>=2.31.0
  ├─ Usage: HTTP client for CuOpt API calls
  ├─ Note: Could be replaced with httpx for async
  └─ Current: Used in cuopt_client.py
```

### Optional / Future Dependencies

```
# GPU-accelerated optimization
nvidia-cuopt>=0.3.0
  └─ Requires: NVIDIA GPU, CuOpt solver credentials

# Vision-Language Models for chart analysis
# (from NVIDIA build.nvidia.com)
nvidia-nim-client>=0.1.0

# Embedding model for RAG
nvidia-nv-embed>=0.1.0

# Safety guardrails for LLM
nemo-guardrails>=0.3.0

# Advanced profiling
memory-profiler>=0.61.0
py-spy>=0.3.14

# Type checking
mypy>=1.0
types-requests>=2.31.0
```

## Performance Characteristics

### Computational Complexity

| Operation | Complexity | Notes |
|-----------|-----------|-------|
| Orbit propagation (1 object, 1 step) | O(1) | RK78: ~8 force evaluations |
| Propagate N objects, M steps | O(N·M) | Linear scaling, parallelizable |
| Conjunction screening (all-pairs) | O(N²) | Reduced by geometric filters to ~0.1N² |
| Compute Pc (single pair) | O(1) | Covariance ellipsoid method, ~1ms |
| Network flow optimization | O(N³) | NetworkX worst-case; CuOpt: O(N log N) |
| MCTS exploration | O(2^d) | d = decision tree depth; pruning helps |

### Memory Requirements

| Data | Memory per Object | N=1000 | N=10k |
|------|------------------|--------|--------|
| State vector (6×8 bytes) | 48 bytes | 48 KB | 480 KB |
| Covariance matrix (6×6×8 bytes) | 288 bytes | 288 KB | 2.88 MB |
| STM matrix (6×6×8 bytes) | 288 bytes | 288 KB | 2.88 MB |
| Conjunction events (avg 10 per object) | Variable | ~1 MB | ~10 MB |
| **Total per epoch** | ~600 bytes | 0.6 MB | 6 MB |

**Rule of thumb:** 10k object constellation ≈ 60-100 MB RAM per epoch (including Python overhead).

### Execution Time (Typical LEO Constellation, 24-hour window)

| Step | N=100 | N=1000 | N=10k |
|------|-------|--------|--------|
| Propagation (1 day, hourly steps) | 100ms | 1s | 10s |
| Conjunction screening | 50ms | 5s | 500s† |
| Pc calculation (100 conjunctions) | 100ms | 100ms | 100ms |
| Greedy optimization | 200ms | 2s | 20s |
| Network flow optimization | 500ms | 30s | 300s† |
| MCTS (10k iterations) | 5s | 50s | 500s† |
| API update + render | 50ms | 50ms | 50ms |
| **Total (greedy, serial)** | ~500ms | ~8s | ~530s |

† Candidates for parallelization or GPU acceleration (CuOpt).

## Integration Points

### External Services

**OpenAI API**
```python
# Usage pattern
import openai

openai.api_key = os.getenv("OPENAI_API_KEY")

response = openai.ChatCompletion.create(
    model="gpt-4",
    messages=[
        {"role": "system", "content": "You are an orbital mechanics expert..."},
        {"role": "user", "content": f"Analyze this conjunction: {conjunction_data}"}
    ]
)
```

**NVIDIA CuOpt** (via cuopt_client.py)
```python
# Usage pattern
from src.cuopt_client import CuOptClient

client = CuOptClient(api_key=os.getenv("CUOPT_API_KEY"))
solution = client.solve_vehicle_routing(
    conjunctions=flagged_pairs,
    fuel_budgets=satellite_fuel,
    time_windows=tca_times
)
```

### Dashboard Integration

**API Contract**
```
GET /api/risk
├─ Returns: total_risk_score, trending (up/down/stable)
└─ Update rate: 1/second

GET /api/conjunctions
├─ Returns: list of {sat1, sat2, tca, pc, risk_score}
└─ Update rate: 1/minute (expensive calculation)

GET /api/shells
├─ Returns: debris density by altitude band
└─ Update rate: 1/hour

GET /api/maneuvers
├─ Returns: planned maneuvers with status
└─ Update rate: 1/second

POST /api/simulate
├─ Params: scenario_id, time_step
└─ Returns: updated state
```

## Optimization Paths

### CPU-Bound Optimization

**Current state:**
- Sequential screening of N² pairs
- NetworkX min-cost flow (good for N<10k)

**Quick wins (1-2 hour work):**
1. Parallelize pair screening with `multiprocessing.Pool`
2. Use `scipy.spatial.cKDTree` for nearest-neighbor screening
3. Vectorize inner loops in conjunction.py

**Medium-term (1-2 day work):**
1. Cython compilation for hot loops (orbital_mechanics.py)
2. Numba JIT compilation for force evaluation
3. GPU screening via PyTorch or CuPy

### GPU Acceleration

**CuOpt integration:** Already scaffolded in `cuopt_client.py`
- Solves maneuver sequencing 100-1000× faster than NetworkX
- Requires NVIDIA GPU + credentials
- Cost: ~$0.10 per solve for prototype pricing

**GPU screening:** Potential future enhancement
- All-pairs distance computation on GPU
- Would handle 100k objects easily
- Library: PyTorch or RAPIDS

### Algorithm Optimization

**Greedy heuristics:**
- Currently: sort by risk, resolve highest-risk first
- Alternative: sort by fuel-efficiency (ΔRisk / Δv)
- Alternative: cluster analysis (resolve clusters vs. individuals)

**MCTS improvements:**
- Current: random playout
- Enhancement: learned policy network (AlphaGo-style)
- Benefit: converge to better solutions faster

## Testing Strategy

### Unit Tests

For physics-critical functions:
```python
def test_two_body_circular_orbit():
    """Circular orbit should have constant radius."""
    state = np.array([6778e3, 0, 0, 0, 7.5e3, 0])  # LEO, 400 km altitude
    for _ in range(100):
        state = propagate_state(state, dt=60, perturbations=False)
        r = np.linalg.norm(state[:3])
        assert abs(r - 6778e3) < 1  # Should stay constant (no J2)

def test_pc_bounds():
    """Probability of collision should be in [0, 1]."""
    for _ in range(100):
        pc = compute_probability_of_collision(...)
        assert 0 <= pc <= 1
```

### Integration Tests

```python
def test_full_pipeline():
    """Full simulation should complete without error."""
    config = {'n_spacecraft': 100, 'duration_days': 1}
    sim = Simulation(config)
    sim.run()
    assert sim.n_maneuvers_planned >= 0
    assert sim.total_risk >= 0
```

### Regression Tests

Before deploying major changes:
```bash
# Baseline run
python -m src.simulation --config baseline.json > baseline.log

# After changes
python -m src.simulation --config baseline.json > new.log

# Compare metrics
python scripts/compare_metrics.py baseline.log new.log
# Should show: Risk scores within 5%, maneuver counts ±10%
```

## Deployment Considerations

### Single-Process (Prototype)
- Suitable for: <1000 objects, 7-day planning horizon
- Execution: `python -m src.simulation`
- Resource: 1 CPU core, ~500MB RAM

### Multi-Process (Scaling)
- Suitable for: 1000-10k objects, 1-7 day horizon
- Execution: `gunicorn -w 4 -b 0.0.0.0:5000 src.api:app`
- Resource: 4 CPU cores, 2-4GB RAM

### GPU-Accelerated (Large Scale)
- Suitable for: 10k+ objects, real-time updates
- Execution: CuOpt solver + Flask API
- Resource: 1 NVIDIA GPU (T4/A100), 8-16GB VRAM, 1 CPU

## Documentation References

- **Physics Deep Dive:** #[[file:docs/physics.md]]
- **Decision Framework:** #[[file:docs/strategy.md]]
- **Intuitive Guide:** #[[file:content.md]]
- **AI Opportunities:** #[[file:ai.md]]
