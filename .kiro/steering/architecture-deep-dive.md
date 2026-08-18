# Architecture Deep Dive

## System Design Principles

### 1. Physics-First Accuracy
- Core orbital mechanics trusted first
- All higher-level decisions grounded in validated propagation
- Perturbation models matched to problem domain (LEO/MEO/GEO)

### 2. Separation of Concerns
- Physics (orbital_mechanics) independent of decision logic
- Decision logic (risk_optimizer) pluggable with different strategies
- API layer independent of backend algorithms
- Dashboard UI independent of data source

### 3. Progressive Risk Assessment
```
Quick screening (O(N²)) → Detailed Pc (O(1)) → Optimization (O(N³)) → API
```
Fail-fast approach: eliminate low-risk pairs early, focus compute on truly dangerous scenarios.

### 4. Uncertainty Propagation
- Every trajectory has covariance (uncertainty)
- Covariance grows with time (via State Transition Matrix)
- Risk = Pc × Consequence (accounts for uncertainty quantitatively)

### 5. Scalable Decision Making
- Greedy (fast, good enough for 10k objects)
- Network flow (optimal for small-medium constellations)
- MCTS (parallelizable, asymptotically optimal)
- CuOpt (GPU, production-scale)

---

## Data Flow Architecture

### Flow 1: Real-Time Conjunction Detection

```
Raw TLE Data
    ↓
Parse & Convert to State Vectors (ECI)
    ↓
Propagate 24 hours ahead (with covariance growth)
    ↓
Geometric screening (apogee/perigee, plane, distance)
    ↓
Flagged pairs (~1000 for 10k objects)
    ↓
Compute TCA (exact closest approach time)
    ↓
Compute Pc (probability of collision at TCA)
    ↓
Build risk network (conjunction graph)
    ↓
Store in API cache (for dashboard consumption)
```

**Latency:** ~30-60 seconds for full 10k object constellation (assuming parallel screening).

### Flow 2: Maneuver Planning & Optimization

```
High-risk conjunctions from Flow 1
    ↓
Assess feasibility (can each be dodged?)
    ↓
Plan individual avoidance maneuvers
    ├─ Compute STM at maneuver time
    ├─ Find optimal Δv direction
    └─ Estimate miss distance improvement
    ↓
Global optimization across all maneuvers
    ├─ Greedy: highest risk first
    ├─ Network flow: fuel-optimal allocation
    └─ MCTS: multi-step lookahead
    ↓
Compute cascade effects (new debris conjunctions)
    ↓
Verify solution (all Pc below threshold? Fuel budgets met?)
    ↓
Recommend to operators / publish to dashboard
```

**Latency:** ~1-5 minutes (depends on N and optimization strategy).

### Flow 3: Damage Minimization (Unavoidable Collision)

```
Conjunction with Pc still high after all maneuvers
    ↓
Accept that collision is unavoidable
    ↓
Evaluate damage mitigation strategies
    ├─ Attitude adjustment (minimize cross-section)
    ├─ Relative velocity reduction (if fuel available)
    ├─ Impact geometry optimization
    └─ Debris altitude selection
    ↓
Estimate post-collision debris field
    ├─ Fragment count (NASA model)
    ├─ Fragment velocities (Gaussian spread)
    └─ Debris orbit distribution
    ↓
Screen all objects against debris
    ├─ New high-risk conjunctions?
    └─ Cascade risk calculation
    ↓
Alert operators with contingency plan
```

**Latency:** ~5-10 minutes (includes debris propagation).

---

## Module Interaction Patterns

### Pattern 1: Conjunction Assessment

```python
# conjunction.py exposes high-level interface
conjunctions = conjunction.screen_conjunctions(
    all_states,           # List of state vectors
    all_covariances,      # List of covariance matrices
    propagation_horizon   # seconds (e.g., 86400 = 1 day)
)

# Internally calls orbital_mechanics for propagation
for dt in time_steps:
    state1_future = orbital_mechanics.propagate_state(state1, dt)
    state2_future = orbital_mechanics.propagate_state(state2, dt)
    # ... screening logic ...

# Returns structured conjunctions with Pc already computed
for conj in conjunctions:
    print(f"Satellites {conj.sat1_id} and {conj.sat2_id}: "
          f"Pc={conj.probability_of_collision}, risk={conj.risk_score}")
```

### Pattern 2: Maneuver Planning

```python
# avoidance.py exposes high-level planning
maneuver = avoidance.plan_avoidance_maneuver(
    satellite_state,
    satellite_covariance,
    conjunction_event,
    margin_required=1000  # meters
)

# Internally uses orbital_mechanics STM
stm = orbital_mechanics.compute_state_transition_matrix(
    satellite_state,
    from_epoch=current_time,
    to_epoch=conjunction_event.tca
)

# Optimizes delta-v direction
# Returns: delta_v_magnitude, delta_v_direction, execution_time
```

### Pattern 3: Risk Optimization

```python
# risk_optimizer.py orchestrates all previous modules
plan = risk_optimizer.optimize_greedy(
    satellites,           # List of spacecraft with state, cov, fuel
    conjunctions,         # Output from conjunction.screen_conjunctions()
    fuel_allocation='risk_weighted'
)

# Internally:
# 1. Sorts conjunctions by risk_score (descending)
# 2. For each conjunction:
#    - Calls avoidance.plan_avoidance_maneuver()
#    - Checks fuel availability
#    - Executes maneuver (updates satellite fuel budget)
#    - Re-screens remaining conjunctions (cascade effects)
# 3. Returns: list of {satellite_id, maneuver}

# Alternatively, uses network-flow or MCTS for larger problems
plan = risk_optimizer.optimize_network_flow(...)
plan = risk_optimizer.optimize_mcts(...)
```

### Pattern 4: API Access

```python
# api.py exposes state through REST endpoints
# Internally maintains simulation handle

@app.route('/api/conjunctions', methods=['GET'])
def get_conjunctions():
    conjunctions = simulation.get_current_conjunctions()
    return jsonify([
        {
            'sat1_id': c.sat1_id,
            'sat2_id': c.sat2_id,
            'tca': c.tca,
            'pc': c.probability_of_collision,
            'risk_score': c.risk_score,
            'coordinates': 'ECI'  # Document coordinate system
        }
        for c in conjunctions
    ])

# Called by dashboard (JavaScript fetch)
# fetch('/api/conjunctions').then(data => render(data))
```

---

## Decision Algorithm Hierarchy

### Level 0: Feasibility Check
```
IF Pc < 1e-7:
    IGNORE (risk is essentially zero)
ELSE:
    PROCEED to Level 1
```

### Level 1: Early Assessment
```
IF Pc < 1e-5:
    MONITOR (collect more data)
ELSEIF Pc < 1e-4:
    FLAG (needs detailed analysis)
ELSE:
    CRITICAL (immediate action)
```

### Level 2: Maneuver Feasibility
```
can_dodge = can_we_achieve_safe_miss_with_available_fuel(conjunction)

IF can_dodge:
    PLAN maneuver (go to Level 3)
ELSE:
    DAMAGE_MITIGATION (go to Level 4)
```

### Level 3: Maneuver Planning
```
FOR each spacecraft in pair:
    compute_optimal_maneuver(spacecraft, conjunction)
    IF maneuver cost > available fuel:
        MARK as "expensive" (prefer other solutions)

global_optimize(all_conjunctions, all_spacecraft)
    # Choose greedy, network-flow, or MCTS
    # Returns: {sat_id → maneuver}

EXECUTE maneuvers (or recommend to operator)
RE_ASSESS all conjunctions (cascade effects)
```

### Level 4: Damage Mitigation (Unavoidable)
```
unavoidable_collisions = [c for c in conjunctions if not can_dodge]

FOR each unavoidable collision:
    strategies = evaluate_mitigation_options(collision)
        # Options: attitude control, altitude selection, etc.
    best_strategy = minimize_debris_generation(strategies)
    
    SIMULATE post-collision debris field
    SCREEN debris against all spacecraft
    CASCADE_RISK += expected_new_conjunctions
    
ALERT operators with contingency plan
```

---

## Optimization Strategy Selection

### Greedy (Fast, Good)
```
1. Sort conjunctions by risk (descending)
2. For each conjunction:
   - Plan avoidance maneuver
   - Check fuel constraint
   - If feasible, execute (update fuel, re-screen)
   - Else, mark for damage mitigation
3. Return plan
```
- **Time:** O(C log C) where C = conjunctions (typically < 10k)
- **Quality:** Often near-optimal for realistic problems
- **Parallelizable:** Yes (parallel maneuver planning)

### Network Flow (Optimal for Resource Allocation)
```
Graph:
  Nodes = spacecraft (each with fuel capacity)
  Edges = conjunctions (each with fuel cost to resolve)
  
Objective:
  Minimize total risk subject to fuel capacity constraints
  
Algorithm:
  Min-cost max-flow on bipartite graph
  via NetworkX.min_cost_flow()
```
- **Time:** O(N³) in worst case; ~O(N log N) average (NetworkX optimized)
- **Quality:** Provably optimal
- **Limit:** Degrades beyond ~5k conjunctions

### Monte Carlo Tree Search (Deep Planning)
```
Tree:
  Root = current state (all spacecraft, all fuel)
  Each action = one maneuver decision
  Each branch = new state after maneuver
  
Simulation:
  1. From root, traverse tree (MCTS policy)
  2. At leaf, simulate random playout to end of horizon
  3. Backup: propagate outcome rewards up tree
  4. Repeat 10k-100k iterations
  
Return:
  Path from root to best leaf
```
- **Time:** O(k) where k = iterations (configurable, typically 1-5 minutes)
- **Quality:** Suboptimal but good; improves with more iterations
- **Parallelizable:** Yes (parallel tree exploration)

### CuOpt (GPU, Production-Scale)
```
VRP Formulation:
  Fleet = maneuverable spacecraft (vehicles)
  Capacity = fuel budget (vehicle capacity)
  Orders = conjunctions (delivery locations)
  Time windows = TCA ± margin
  
Objective:
  Minimize total risk (or fuel consumed)
  
Solver:
  GPU-accelerated exact/heuristic mixed-integer programming
```
- **Time:** Sub-second for 100k+ decisions
- **Quality:** Optimal or near-optimal
- **Requirement:** NVIDIA GPU, CuOpt API credentials

---

## State Propagation & Uncertainty

### State Vector (ECI Coordinates)
```
State = [x, y, z, vx, vy, vz]
         [meters, meters, meters, m/s, m/s, m/s]

Position r = (x, y, z) — Earth-Centered Inertial frame
Velocity v = (vx, vy, vz) — Earth-Centered Inertial frame
```

### Covariance Matrix
```
Cov = 6×6 matrix representing uncertainty in state

Cov = [ Cov_rr   Cov_rv ]   where
      [ Cov_vr   Cov_vv ]

Cov_rr = 3×3 covariance of position (m²)
Cov_vv = 3×3 covariance of velocity ((m/s)²)
Cov_rv = cross-covariance terms
```

### State Transition Matrix (STM)
```
Φ(t, t0) = ∂X(t) / ∂X(t0)

Maps perturbation in initial state to perturbation at later time
dX(t) = Φ(t, t0) · dX(t0)

Also propagates covariance:
P(t) = Φ(t, t0) · P(t0) · Φ(t, t0)ᵀ + Q(t)
       └─ STM         └─ initial cov  └─ process noise
```

### Propagation Accuracy

| Perturbation | Effect on 24h Orbit | Model Used |
|--------------|-------------------|------------|
| J2 oblateness | ~10 km | Included (dominant for LEO) |
| J3+ terms | <100 m | Neglected |
| Atmospheric drag | ~50-500 m (altitude-dependent) | Exponential model |
| Solar radiation | ~10-100 m | Included |
| 3rd-body (Moon/Sun) | <10 m (LEO) | Neglected |
| **Total error budget** | ~500-1000 m | Typical for LEO |

---

## Error Handling & Robustness

### Invalid Input Detection
```python
def _validate_state(state):
    assert state.shape == (6,), "State must be 6-vector"
    assert np.all(np.isfinite(state)), "Non-finite state"
    r = np.linalg.norm(state[:3])
    assert r > EARTH_RADIUS, f"Crashed: r={r} < {EARTH_RADIUS}"
    v = np.linalg.norm(state[3:6])
    assert v < v_escape, f"Escape velocity exceeded: v={v}"
    return True

def _validate_covariance(cov):
    assert cov.shape == (6, 6), "Covariance must be 6×6"
    assert np.allclose(cov, cov.T), "Covariance not symmetric"
    eigs = np.linalg.eigvals(cov)
    assert np.all(eigs > 0), f"Non-PD covariance: eigs={eigs}"
    trace = np.trace(cov)
    assert trace < 1e12, f"Covariance trace too large: {trace}"
    return True
```

### Cascade Failure Prevention
```python
# If one conjunction resolution fails, don't cascade failure
try:
    maneuver = avoidance.plan_maneuver(conj)
    execute_maneuver(maneuver)
except PlanningError as e:
    logger.error(f"Failed to plan maneuver for {conj}: {e}")
    # Fallback: mark for damage mitigation
    FLAG_FOR_DAMAGE_MITIGATION(conj)
    # Continue processing other conjunctions
    continue
```

### Numerical Stability Checks
```python
# After long propagation, re-normalize covariance
P = propagate_covariance(P0, t_long)
if condition_number(P) > 1e10:
    logger.warning("Covariance conditioning poor after long propagation")
    # Either: reduce propagation interval, or use filter (Kalman update)
    P = apply_kalman_update(P, new_measurement)
```

---

## Performance Optimization Roadmap

### Phase 1 (Current)
- Serial Python (NumPy/SciPy optimized)
- Suitable for: N < 5000, research/prototyping

### Phase 2 (Medium-term)
- Parallel screening (multiprocessing.Pool)
- Numba JIT for hot loops
- Suitable for: N < 10000, small operational deployments

### Phase 3 (Long-term)
- CuOpt GPU solver integration
- RAPIDS for data processing
- Suitable for: N > 100000, production megaconstellations

---

## API Contract Reference

### Response Format (All Endpoints)
```json
{
  "status": "success|error",
  "data": { ... },
  "timestamp": "ISO-8601",
  "version": "1.0"
}
```

### Key Endpoints

**GET /api/risk**
```json
{
  "status": "success",
  "data": {
    "total_risk_score": 0.045,
    "critical_conjunctions": 3,
    "monitored_conjunctions": 47,
    "trend": "increasing|stable|decreasing",
    "forecast_24h": 0.063
  }
}
```

**GET /api/conjunctions?filter=critical**
```json
{
  "status": "success",
  "data": [
    {
      "id": "conj-12345",
      "sat1": {"id": 101, "name": "Sat-A"},
      "sat2": {"id": 102, "name": "Sat-B"},
      "tca": "2026-08-20T14:23:45Z",
      "pc": 0.0012,
      "risk_score": 0.089,
      "status": "critical|monitored|acceptable",
      "maneuver_recommended": true
    }
  ]
}
```

---

## Documentation References

- **Physics Foundation:** #[[file:docs/physics.md]]
- **Strategy Framework:** #[[file:docs/strategy.md]]
- **Technical Stack:** technical-stack.md
- **Development Guide:** development-practices.md
