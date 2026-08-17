# Requirements: NVIDIA cuOpt-Backed Collision-Avoidance Intervention Planning

## Functional Requirements

### 1. Constrained-Assignment MILP Formulation

**Requirement 1.1**: The system shall formulate the intervention-scheduling problem as a mixed-integer linear program with the following structure:
- **Decision variables**: Binary x_k ∈ {0,1} for each candidate (conjunction, spacecraft) pair, where x_k=1 means "spacecraft k maneuvers to resolve conjunction k"
- **Objective**: Minimize (fuel_cost_normalized − risk_score_normalized) across all selected maneuvers, balancing fuel efficiency against risk reduction
- **Constraints**:
  - Assignment constraint: At most one spacecraft per conjunction (Σ x_k ≤ 1 per conjunction)
  - Capacity constraint: Each spacecraft's total fuel cost ≤ remaining budget (Σ fuel_cost_k × x_k ≤ budget_sc per spacecraft)
- **Output**: Binary solution vector indicating which candidates are selected, with objective value and solver status

**Acceptance Criteria**:
- MILP formulation correctly encodes the constrained-assignment problem
- Objective balances fuel and risk (normalized coefficients scale comparably)
- All candidates satisfy preconditions (non-negative fuel cost, valid spacecraft/conjunction references)
- Solution respects all constraints (no double-assignment, no budget overspend)

---

### 1.2: Solver Transport Layer (CuOptClient)

**Requirement 1.2**: The system shall provide a solver abstraction layer that transparently routes LP/MILP problems to one of two backends:

1. **Remote GPU cuOpt server** (if CUOPT_SERVER_IP environment variable is set):
   - Use the `cuopt_sh_client` library to communicate with a self-hosted NVIDIA cuOpt GPU server
   - Implement async invoke/poll loop for remote solve (cuOpt server is not blocking; it returns a request ID and client polls for completion)
   - Respect CUOPT_POLL_TIMEOUT when waiting for solution
   - Timeout or connection error → gracefully degrade to local fallback (no exception to caller)

2. **Local CPU fallback** (scipy.optimize.milp with HiGHS backend):
   - Use scipy.optimize.milp + HiGHS solver for local MILP solving
   - Convert cuOpt's problem_data schema (CSR constraint matrix, bounds, objective) to scipy format (sparse matrix, LinearConstraint, Bounds)
   - Solve with configurable time_limit (default 10 seconds)
   - Return normalized solution dict {vars, objective, status, backend}

**Acceptance Criteria**:
- solve_milp() method accepts problem_data dict and returns solution dict
- Remote solve works when server available; transparent fallback to local when not
- CSR matrix reconstruction matches original constraint matrix
- Solution dict has consistent schema regardless of backend
- Graceful degradation: server error → local solver, never raises to caller (except if both fail)
- Time limit respected (solver terminates within time_limit + small overhead)

---

### 1.3: Candidate Generation

**Requirement 1.3**: The system shall generate all feasible (conjunction, spacecraft) maneuver candidates that feed the MILP formulation.

For each conjunction and each potentially-maneuvering spacecraft:
- Check if spacecraft is maneuverable and has remaining fuel (Δv > 1e-6 m/s)
- Call `design_avoidance_maneuver(maneuverer, target, conjunction)` to compute fuel cost
- Include candidate only if maneuver is valid (fuel_cost > 0)
- Store candidate metadata: conjunction index, IDs, maneuver object

**Acceptance Criteria**:
- All candidates have valid references (conjunction and spacecraft exist)
- All candidates have non-negative fuel cost
- No duplicate (conj, sc) pairs
- Candidates filtered by maneuverability and fuel availability
- Empty candidate list → gracefully fall back to greedy (do not raise exception)

---

### 1.4: Adaptive Method Selection

**Requirement 1.4**: The system shall select the optimization method (greedy, MILP network-flow, or MCTS) based on problem complexity (number of active conjunctions).

- **≤ 5 conjunctions**: Use greedy (simple, deterministic)
- **6–50 conjunctions**: Use network_flow_optimize (MILP via cuOpt, aim for optimal)
- **> 50 conjunctions**: Use MCTS (branch-and-bound MILP may timeout; search is more robust)

**Acceptance Criteria**:
- `optimize(method='adaptive')` dispatcher selects appropriate method
- Method selection is deterministic (same input → same method)
- Each method returns valid InterventionPlan
- Selection thresholds (5, 50) are configurable via constants

---

### 2. Greedy Optimization Fallback

**Requirement 2.1**: The system shall provide a greedy optimization strategy as fallback when MILP solver is unavailable or problem is trivial.

**Algorithm**:
1. Sort conjunctions by risk_score (descending)
2. For each conjunction (up to max_maneuvers limit):
   - Check if already resolved
   - Choose a maneuverable spacecraft with available fuel
   - Design maneuver via `design_avoidance_maneuver()`
   - If maneuver succeeds: add to plan, update working spacecraft state
3. Return plan with list of maneuvers

**Acceptance Criteria**:
- Greedy always terminates (no infinite loops)
- Maneuvers assigned in order of decreasing conjunction risk
- No spacecraft exceeds fuel budget (checked after assignment)
- Returns valid InterventionPlan (may be partial if fuel exhausted)
- Greedy solution often 70–80% of optimal MILP (validated against known problems)

---

### 3. Natural-Language Query Interface

**Requirement 3.1**: The system shall accept operator free-text queries and interpret them into conjunction filters via risk-level keywords.

**Keyword mapping**:
- "critical" → Pc ≥ 1e-4
- "high" → Pc ≥ 1e-5
- "moderate" / "medium" → Pc ≥ 1e-6
- "low" / "all" → Pc ≥ 0.0 (no filter)

**Algorithm**:
1. Convert query to lowercase
2. Check for keywords; set Pc threshold to max(matched keyword thresholds)
3. Filter conjunctions: keep those with Pc ≥ threshold
4. If no keywords matched: default to all conjunctions (fail-safe)

**Acceptance Criteria**:
- Query parsing is case-insensitive
- Multiple keywords in query → use highest-risk threshold
- Filtering returns correct subset of conjunctions
- Empty result gracefully returns empty plan (no exception)

---

### 3.2: LLM-Based Plan Narration

**Requirement 3.2**: The system shall use NVIDIA NIM (LLM) to narrate the already-solved intervention plan in plain English, grounded strictly in solver output.

**System Prompt Constraint**:
- LLM receives solver_output JSON (problem counts, maneuvers with fuel costs, resolved/unresolved conjunction IDs)
- LLM is forbidden from inventing delta-v numbers (must use solver output exactly)
- Narration must state how many conjunctions were resolved, unresolved, and considered
- Narration must indicate reason for unresolved conjunctions (fuel exhausted, no maneuverable spacecraft)
- Output tone: operational and concise (2–3 sentences max)

**Acceptance Criteria**:
- Narration text contains only numbers from solver_output (no fabricated Δv values)
- Every delta-v in narration appears in {maneuver.fuel_cost} ∪ {total_fuel_cost, 0}
- Narration counts match solver output (resolved, unresolved, considered)
- If LLM unavailable (API error): return plan with status='partial' and error message
- Narration accuracy validated post-generation (test suite checks against solver JSON)

---

### 3.3: End-to-End Query → Plan → Narration Pipeline

**Requirement 3.3**: The system shall provide a single entry point `plan_intervention_from_query(spacecraft_list, conjunctions, query)` that orchestrates: (1) query interpretation, (2) MILP solving, (3) LLM narration.

**Acceptance Criteria**:
- Function signature accepts spacecraft list, conjunction list, query string
- Returns dict with keys: status, query, considered_conjunctions, maneuvers, total_fuel_cost_ms, resolved_conjunction_ids, unresolved_conjunction_ids, narration
- status ∈ {'success', 'partial', 'error'}
- All numbers in narration trace back to solver output
- Operator can act directly on returned plan (no additional interpretation needed)

---

## Non-Functional Requirements

### 4. Performance

**Requirement 4.1**: The system shall solve medium-scale problems (10–50 conjunctions) within 10 seconds.

- MILP solve time: ≤ 10 seconds (cuOpt GPU: typically 0.1–5 seconds; local scipy: 1–10 seconds)
- End-to-end query → plan time: ≤ 15 seconds (including candidate generation, MILP, LLM narration)
- Greedy fallback: ≤ 1 second (always instant as backup)

**Acceptance Criteria**:
- Benchmark: 50 conjunctions, 100 spacecraft, diverse fuel budgets
- MILP solves in ≤ 10 seconds
- Greedy solves in ≤ 1 second
- LLM narration latency ≤ 5 seconds (dominated by API round-trip)

---

### 5. Reliability & Error Handling

**Requirement 5.1**: The system shall gracefully degrade when any component fails (cuOpt server, local MILP, LLM API).

**Fallback Chain**:
1. cuOpt server unavailable → local MILP
2. Local MILP infeasible → greedy
3. Greedy fails → return empty plan with status
4. LLM unreachable → return plan without narration (status='partial')

**Acceptance Criteria**:
- No unhandled exceptions bubble up to caller
- Every code path returns a valid response dict (even if partial)
- Error messages are logged and returned to caller for debugging
- Timeouts configured for all remote calls (cuOpt server, LLM API)

---

### 6. Correctness & Safety

**Requirement 6.1**: The system shall guarantee that every returned intervention plan satisfies all fuel-budget and assignment constraints.

**Hard Constraints**:
- No spacecraft exceeds its Δv budget: Σ(fuel_cost for maneuvers assigned to sc) ≤ budget_sc
- No double-assignment: Each conjunction resolved by at most one spacecraft
- All maneuvers have non-negative cost (no manufacturing fuel)

**Verification**:
- Post-solve audit: check all constraints for all returned plans
- Test suite validates constraints on synthetic problems
- Fuel budget sanity check runs on every plan (per `_tmp_test_cuopt.py` pattern)

**Acceptance Criteria**:
- 100% of plans pass constraint audit (fuel budget, assignment, non-negative cost)
- Any plan violating constraints triggers test failure
- Audit results logged for debugging

---

### 6.2: LLM Output Grounding

**Requirement 6.2**: Every number in LLM narration must trace back to solver output; fabricated delta-v values are forbidden.

**Verification**:
- Test suite extracts all numeric values from narration text
- For each value: verify it appears in solver_output (maneuver costs, total cost, or counts)
- Any unexplained number triggers test failure

**Acceptance Criteria**:
- 100% of narrations pass numeric grounding check
- No fabricated fuel costs in narration
- Every cost mentioned in narration has source in solver output

---

### 7. Scalability

**Requirement 7.1**: The system shall scale to typical LEO constellation sizes.

- Constellation: up to 1000 tracked spacecraft
- Active conjunctions: up to 1000 per week
- Candidate pool: up to 5000 (before MILP solving)

**Acceptance Criteria**:
- Can generate 5000 candidates in < 1 second
- MILP with 5000 variables and 10,000 constraints solves in < 60 seconds (with cuOpt)
- No memory overflow (feasible on commodity GPU with 8–16 GB)
- Adaptive method selection ensures reasonable solve time

---

### 8. Maintainability

**Requirement 8.1**: The system shall use the cuOpt problem_data schema consistently across all solvers (remote, local, future alternatives).

- All problem formulations use cuOpt's LPData schema (CSR, bounds, objective, etc.)
- Schema is language/solver-agnostic (JSON representation)
- Future solvers can consume same problem_data without reformulation

**Acceptance Criteria**:
- problem_data structure is well-documented and validated
- All solvers accept same problem_data dict
- Adding a new solver requires only implementing convert_to_solver_format() + solve()

---

## Constraints & Assumptions

### Constraints

- **Fuel Budget Immutability**: Fuel budgets are frozen at optimization time; operator cannot edit mid-solve
- **Maneuver Feasibility**: All designed maneuvers are feasible (via STM-based design; assumes healthy spacecraft)
- **Conjunction Data Quality**: Conjunction risk scores and TCA values are accurate (from screening module)
- **LLM Determinism**: LLM output may vary; narration is best-effort (not security-critical)

### Assumptions

- Maneuvering spacecraft are cooperative (can execute maneuvers as planned)
- Fuel consumption is deterministic (no margin for execution error)
- Conjunctions are independent (no cascade or secondary conjunctions modeled during planning)
- cuOpt server (if configured) is available and healthy (caller ensures maintenance)
- NVIDIA_API_KEY environment variable is set for LLM access (caller ensures)

---

## Success Metrics

1. **Correctness**: 100% of plans satisfy fuel budget and assignment constraints
2. **Performance**: Medium problems (50 conjunctions) solve in ≤ 10 seconds
3. **Robustness**: All error scenarios (server down, MILP fail, LLM timeout) handled gracefully
4. **Grounding**: 100% of narration passes numeric grounding check (no fabricated costs)
5. **Usability**: Operator can understand narration and act on plan within 30 seconds of query
