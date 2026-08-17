# Tasks: NVIDIA cuOpt-Backed Collision-Avoidance Intervention Planning

This is a **backfill spec** for an already-implemented system. These tasks document verification and testing of the existing implementation against the design and requirements.

## Phase 1: Verification of Core Components

### 1.1: Verify CuOptClient Solver Transport Layer

**Task**: Validate that CuOptClient correctly routes to remote GPU server or local fallback, with proper CSR matrix handling and schema consistency.

**Steps**:
1. Unit test: Create a small MILP problem (3 variables, 2 constraints)
2. Solve with CuOptClient (assume local fallback, CUOPT_SERVER_IP not set)
3. Verify solution dict structure: `{vars: {}, objective: float, status: str, backend: str}`
4. Verify CSR conversion round-trip: dense → CSR → dense matches original
5. Test constraint bounds handling ('inf', 'ninf', numeric values)
6. Test error case: both server and local unavailable → CuOptUnavailableError
7. Audit: Verify all cuopt_client.py methods are reachable (no dead code)

**Definition of Done**:
- [ ] CuOptClient test suite passes (solve_milp, _solve_remote, _solve_local, CSR conversion)
- [ ] Remote server fallback behavior verified (with mock/mock server)
- [ ] Solution schema validated (all backends return consistent dict)
- [ ] Error handling verified (CuOptUnavailableError raised correctly)
- [ ] Code coverage ≥ 90% for cuopt_client.py

**Owner**: Implementation verified from `src/cuopt_client.py`

---

### 1.2: Verify RiskGraph Risk Network Construction

**Task**: Validate that RiskGraph correctly builds and analyzes orbital risk networks.

**Steps**:
1. Build RiskGraph from synthetic constellation (10 spacecraft, 5 conjunctions)
2. Verify nodes have correct attributes (mass, altitude, fuel_remaining, maneuverable)
3. Verify edges have correct attributes (risk_score, pc, tca, miss_distance)
4. Test get_risk_clusters() → verify connected components identified
5. Test cascade_risk() calculation (BFS propagation, debris decay)
6. Test total_risk() aggregation
7. Test highest_risk_conjunctions() returns sorted list
8. Test most_threatened_spacecraft() ranking

**Definition of Done**:
- [ ] RiskGraph test suite passes (build, cluster detection, cascade risk, aggregations)
- [ ] Cascade risk BFS traversal verified (correct depth, decay rate)
- [ ] All node/edge attributes correctly populated
- [ ] Sorting/ranking methods return expected order
- [ ] Code coverage ≥ 85% for RiskGraph class

**Owner**: Implementation verified from `src/risk_optimizer.py` (RiskGraph class)

---

### 1.3: Verify OrbitalEnvironment Kessler Syndrome Assessment

**Task**: Validate that OrbitalEnvironment correctly models orbital shells and computes Kessler syndrome risk.

**Steps**:
1. Create OrbitalEnvironment (50 km shell width, 200–2000 km altitude range)
2. Populate from constellation (100 spacecraft, altitude distribution)
3. Verify shell assignments (each spacecraft in correct altitude band)
4. Call compute_stability() → verify collision/debris rates computed
5. Verify is_unstable flag set correctly (generation > removal)
6. Compute kessler_risk_index() → verify [0, 1] range
7. Test edge cases: empty shell, all spacecraft at same altitude
8. Validate formulas against physics (kinetic theory, atmospheric drag lifetime)

**Definition of Done**:
- [ ] OrbitalEnvironment test suite passes (build, populate, stability, risk index)
- [ ] Collision rate formula correct (kinetic theory: N²×v_rel×σ / V)
- [ ] Debris generation/removal rates reasonable (generation > removal → unstable)
- [ ] kessler_risk_index() in valid range [0, 1]
- [ ] Edge cases handled (empty shells, extreme altitudes)
- [ ] Code coverage ≥ 80% for OrbitalEnvironment class

**Owner**: Implementation verified from `src/risk_optimizer.py` (OrbitalEnvironment class)

---

## Phase 2: Verification of MILP Formulation & Solver

### 2.1: Verify Candidate Generation (`_build_intervention_candidates`)

**Task**: Validate that candidate generation produces correct (conjunction, spacecraft) pairs with valid fuel costs.

**Steps**:
1. Create small problem: 5 spacecraft (3 maneuverable), 3 conjunctions
2. Call `_build_intervention_candidates()` → verify candidate count
3. For each candidate: verify (conj_idx, spacecraft_id, maneuver, fuel_cost)
4. Verify all candidates satisfy preconditions (fuel > 0, maneuverable=true, valid refs)
5. Verify no duplicate (conj, sc) pairs
6. Verify candidates with zero or negative fuel excluded
7. Verify non-maneuverable spacecraft excluded
8. Edge case: No maneuverable spacecraft → empty candidates (fallback to greedy)

**Definition of Done**:
- [ ] Candidate generation test passes (correct count, no duplicates, valid attributes)
- [ ] Preconditions verified (fuel > 0, maneuverability, valid refs)
- [ ] Filtering correct (no invalid candidates in output)
- [ ] Empty candidate list handled gracefully
- [ ] Code coverage ≥ 85% for _build_intervention_candidates

**Owner**: Implementation verified from `src/risk_optimizer.py` (InterventionOptimizer._build_intervention_candidates)

---

### 2.2: Verify MILP Problem Formulation

**Task**: Validate that network_flow_optimize() correctly formulates the constrained-assignment MILP.

**Steps**:
1. Create problem: 5 spacecraft, 4 conjunctions, 10 candidates
2. Call network_flow_optimize() (will use local scipy fallback)
3. Verify MILP structure:
   - Objective coefficients: (fuel_norm − risk_norm) for each candidate
   - Assignment constraints: at most 1 per conjunction (CSR row)
   - Capacity constraints: fuel per spacecraft (CSR row)
4. Verify CSR matrix structure (offsets monotonic, indices valid)
5. Verify bounds (variable bounds [0,1], constraint bounds correct)
6. Verify variable types: all 'I' (integer)
7. Verify maximize: False (minimization problem)

**Definition of Done**:
- [ ] MILP formulation test passes (objective, constraints, bounds, types, CSR structure)
- [ ] Objective coefficients normalized correctly (fuel/max_fuel − risk/max_risk)
- [ ] Assignment constraint count = # conjunctions (with candidates)
- [ ] Capacity constraint count = # maneuverable spacecraft (with fuel)
- [ ] CSR matrix valid (no index out of bounds, offsets consistent)
- [ ] Code coverage ≥ 90% for MILP formulation

**Owner**: Implementation verified from `src/risk_optimizer.py` (InterventionOptimizer.network_flow_optimize, formulation section)

---

### 2.3: Verify Adaptive Method Selection

**Task**: Validate that optimize(method='adaptive') selects correct method based on problem size.

**Steps**:
1. Create problems of varying sizes:
   - 3 conjunctions → expect greedy
   - 20 conjunctions → expect network_flow
   - 100 conjunctions → expect MCTS
2. Call optimize(method='adaptive') for each
3. Verify method selection matches expectations
4. Verify each method returns valid InterventionPlan
5. Verify fallback chain works (if MILP fails → greedy)

**Definition of Done**:
- [ ] Adaptive selection test passes (correct method for each size)
- [ ] Method selection deterministic (same input → same method)
- [ ] Each method returns valid plan
- [ ] Fallback chain verified (MILP fail → greedy)
- [ ] Code coverage ≥ 90% for optimize() dispatcher

**Owner**: Implementation verified from `src/risk_optimizer.py` (InterventionOptimizer.optimize)

---

## Phase 3: Verification of Greedy & MCTS Fallbacks

### 3.1: Verify Greedy Optimization

**Task**: Validate that greedy_optimize() produces valid plans and handles edge cases.

**Steps**:
1. Create problem: 5 spacecraft (2 maneuverable), 8 conjunctions
2. Call greedy_optimize() → verify plan structure
3. Verify maneuvers assigned in order of decreasing conjunction risk
4. Verify fuel budget constraint: no spacecraft exceeds budget
5. Verify assignment constraint: no conjunction double-assigned
6. Verify max_maneuvers limit respected
7. Verify fuel depletion causes early stop (partial plan OK)
8. Edge cases:
   - No maneuverable spacecraft → empty plan
   - All spacecraft out of fuel → empty plan
   - Single conjunction → single maneuver plan

**Definition of Done**:
- [ ] Greedy optimization test passes (valid plan, constraints satisfied)
- [ ] Maneuver assignment order correct (decreasing risk)
- [ ] Fuel budget constraint verified post-solve
- [ ] Assignment constraint verified post-solve
- [ ] max_maneuvers limit respected
- [ ] Edge cases handled (no exception)
- [ ] Code coverage ≥ 85% for greedy_optimize

**Owner**: Implementation verified from `src/risk_optimizer.py` (InterventionOptimizer.greedy_optimize)

---

### 3.2: Verify MCTS Optimization

**Task**: Validate that mcts_optimize() explores the intervention tree and produces valid plans.

**Steps**:
1. Create problem: 5 spacecraft, 10 conjunctions
2. Call mcts_optimize(n_simulations=100) → verify plan structure
3. Verify fuel budget constraint satisfied
4. Verify assignment constraint satisfied
5. Verify plan is valid (can apply maneuvers in sequence)
6. Test parameter sensitivity:
   - Vary n_simulations: more → better quality (if deterministic seed)
   - Vary max_depth: deeper → longer search
   - Vary exploration_weight: affects exploration vs. exploitation
7. Edge cases: Empty candidates, single conjunction

**Definition of Done**:
- [ ] MCTS optimization test passes (valid plan, constraints satisfied)
- [ ] Fuel budget constraint verified
- [ ] Assignment constraint verified
- [ ] MCTS tree search executes without exception
- [ ] Parameter sensitivity tested (quality improves with more simulations)
- [ ] Edge cases handled
- [ ] Code coverage ≥ 80% for mcts_optimize

**Owner**: Implementation verified from `src/risk_optimizer.py` (InterventionOptimizer.mcts_optimize)

---

## Phase 4: Verification of Natural-Language Interface

### 4.1: Verify Query Filtering

**Task**: Validate that _filter_conjunctions_for_query() correctly interprets risk-level keywords.

**Steps**:
1. Create conjunction list: 5 conjunctions with varying Pc (1e-3, 1e-4, 1e-5, 1e-6, 1e-7)
2. Test queries:
   - "critical" → Pc ≥ 1e-4 (expect 2 conjunctions)
   - "high" → Pc ≥ 1e-5 (expect 3 conjunctions)
   - "moderate" → Pc ≥ 1e-6 (expect 4 conjunctions)
   - "low" / "all" → Pc ≥ 0 (expect all 5)
3. Test case-insensitivity:
   - "CRITICAL" → same as "critical"
   - "CrItIcAl" → same as "critical"
4. Test multiple keywords:
   - "critical high" → max(1e-4, 1e-5) = 1e-4
5. Test no keywords:
   - "What's the plan?" → default to all (fail-safe)
6. Verify filtering returns correct subset each time

**Definition of Done**:
- [ ] Query filtering test passes (correct threshold for each keyword)
- [ ] Case-insensitivity verified
- [ ] Multiple keywords handled (max threshold)
- [ ] No-keyword fallback to all conjunctions
- [ ] Code coverage ≥ 95% for _filter_conjunctions_for_query

**Owner**: Implementation verified from `src/ai_analysis.py` (_filter_conjunctions_for_query)

---

### 4.2: Verify LLM Narration Safety (No Fabricated Numbers)

**Task**: Validate that plan_intervention_from_query() narration uses only solver-generated numbers.

**Steps**:
1. Create problem: 4 spacecraft, 3 conjunctions
2. Call plan_intervention_from_query(query="critical")
3. Extract narration text
4. Parse all numeric values from narration (using regex: \\d+\\.?\\d*)
5. For each number, verify source:
   - If delta-v: must appear in [m.fuel_cost for m in plan.maneuvers] or plan.total_fuel_cost_ms
   - If count: must match len(resolved) or len(unresolved) or len(considered)
   - If time: must appear in [m.time for m in plan.maneuvers]
6. Flag any unexplained number as test failure

**Definition of Done**:
- [ ] Narration grounding test passes (100% of numbers have source in solver output)
- [ ] No fabricated delta-v values in narration
- [ ] Numeric parsing and verification works correctly
- [ ] Test runs on 10+ random problems (all pass)
- [ ] Code coverage ≥ 90% for plan_intervention_from_query (narration section)

**Owner**: Implementation verified from `src/ai_analysis.py` (plan_intervention_from_query, LLM narration section)

---

### 4.3: Verify End-to-End Query → Plan → Narration

**Task**: Validate complete pipeline from operator query to LLM-narrated plan.

**Steps**:
1. Create realistic problem: 10 spacecraft, 12 conjunctions
2. Call plan_intervention_from_query(query="high-risk conjunctions?")
3. Verify function returns dict with expected keys (status, query, maneuvers, total_fuel_cost_ms, resolved_ids, unresolved_ids, narration)
4. Verify status ∈ {'success', 'partial', 'error'}
5. Verify maneuvers list has correct structure (spacecraft_id, target_conjunction_id, time_hours, fuel_cost_ms)
6. Verify total_fuel_cost_ms matches Σ(m.fuel_cost for m in maneuvers)
7. Verify resolved/unresolved conjunction IDs are disjoint and complete
8. Verify narration is plain English, 2–3 sentences max
9. Verify narration states problem size, resolved count, unresolved count, and reason

**Definition of Done**:
- [ ] End-to-end test passes (complete pipeline works)
- [ ] Response dict has all expected keys and values
- [ ] Fuel cost sum verified (total = Σ individual)
- [ ] Conjunction IDs consistent (resolved ∪ unresolved ⊆ considered)
- [ ] Narration quality checked manually (readable, grounded, actionable)
- [ ] Test runs on 5+ realistic scenarios (all pass)

**Owner**: Implementation verified from `src/ai_analysis.py` (plan_intervention_from_query)

---

## Phase 5: Correctness & Safety Verification

### 5.1: Verify Fuel Budget Constraint (Hard Constraint)

**Task**: Validate that every plan respects per-spacecraft fuel budgets.

**Steps**:
1. Create 20 random problems (varying constellation size, fuel budgets)
2. For each problem:
   - Solve via all three methods (greedy, network_flow, mcts if applicable)
   - For each plan: compute Σ(fuel_cost for maneuvers assigned to each spacecraft)
   - Verify: total_spent ≤ budget_remaining (for each spacecraft)
   - Allow small numerical tolerance (1e-6 m/s)
3. Log any violations (test failure)
4. Audit `_tmp_test_cuopt.py` pattern: explicitly check budget compliance

**Definition of Done**:
- [ ] Fuel budget verification test passes on 20 random problems
- [ ] 100% of plans satisfy constraint (zero violations)
- [ ] Numerical tolerance handled correctly (1e-6)
- [ ] Audit code matches reference `_tmp_test_cuopt.py` logic
- [ ] Code coverage ≥ 90% for constraint verification

**Owner**: Implementation verified via synthetic test harness + `_tmp_test_cuopt.py` reference

---

### 5.2: Verify Assignment Constraint (No Double-Assignment)

**Task**: Validate that no conjunction is assigned to multiple spacecraft.

**Steps**:
1. Create 20 random problems
2. For each problem and each solver method:
   - Solve to get plan
   - For each conjunction: count how many maneuvers target it
   - Verify: count ≤ 1 for all conjunctions
   - Log any double-assignments (test failure)
3. Verify assignment counts sum to len(plan.conjunctions_resolved)

**Definition of Done**:
- [ ] Assignment constraint verification test passes on 20 problems
- [ ] 100% of plans satisfy constraint (zero double-assignments)
- [ ] Count consistency verified (assignments = resolved)
- [ ] Code coverage ≥ 90% for constraint verification

**Owner**: Implementation verified via synthetic test harness

---

### 5.3: Performance Benchmark (Target: 10 seconds for 50 conjunctions)

**Task**: Validate system performance on realistic problem sizes.

**Steps**:
1. Generate benchmark problem: 100 spacecraft, 50 conjunctions, diverse fuel budgets
2. Time network_flow_optimize() solving:
   - Candidate generation time
   - MILP formulation time
   - Solver time (cuOpt or scipy)
   - Total end-to-end time
3. Verify total ≤ 10 seconds (target)
4. Repeat greedy benchmark: target ≤ 1 second (should be instant)
5. Repeat for MCTS: target ≤ 30 seconds (slower, acceptable for large problems)
6. Report timings and summary

**Definition of Done**:
- [ ] Performance benchmark runs without exception
- [ ] network_flow solves 50-conjunction problem in ≤ 10 seconds
- [ ] greedy solves in ≤ 1 second
- [ ] MCTS solves in ≤ 30 seconds
- [ ] Timings logged and reported
- [ ] Code coverage ≥ 85% for all solver paths

**Owner**: Benchmarking harness created and executed

---

## Phase 6: Integration & Documentation

### 6.1: Verify API Integration (Flask endpoint)

**Task**: Validate that POST /api/interventions endpoint works end-to-end.

**Steps**:
1. Start Flask API server
2. Send POST request: `{"query": "critical conjunctions"}`
3. Verify response structure: {status, query, maneuvers, total_fuel_cost_ms, resolved_ids, unresolved_ids, narration}
4. Verify HTTP status code: 200 (success) or appropriate error
5. Verify narration present (if LLM available)
6. Verify plan can be displayed on dashboard
7. Test error cases:
   - No query field → 400 Bad Request
   - Invalid JSON → 400 Bad Request
   - LLM unavailable → status='partial' (HTTP 200)

**Definition of Done**:
- [ ] API endpoint test passes (correct response, status codes)
- [ ] Response structure validated
- [ ] Error handling verified (bad requests, missing LLM)
- [ ] API can be called from dashboard without error
- [ ] Documentation updated (endpoint schema, examples)

**Owner**: Implementation verified from `src/api.py` (/api/interventions endpoint)

---

### 6.2: Documentation & Handoff

**Task**: Ensure all components documented and tested for production use.

**Steps**:
1. Review design.md for completeness and accuracy
2. Review requirements.md for coverage (all implemented features documented)
3. Review code comments: all functions have docstrings
4. Verify README includes:
   - Setup instructions (cuOpt server, scipy fallback)
   - Example usage (Python API, Flask endpoint, CLI)
   - Performance expectations
   - Troubleshooting guide
5. Verify LICENSE & attribution for dependencies (cuopt_sh_client, scipy, NVIDIA NIM)
6. Test suite documented (how to run, what each test verifies)

**Definition of Done**:
- [ ] design.md reflects actual implementation (accuracy check)
- [ ] requirements.md complete and consistent with design
- [ ] All functions have docstrings (> 90% coverage)
- [ ] README includes setup, examples, performance, troubleshooting
- [ ] Dependencies attributed
- [ ] Test suite documented (runnable by future maintainers)

**Owner**: Documentation review and updates

---

## Overall Success Criteria

1. **All unit tests pass**: CuOptClient, RiskGraph, OrbitalEnvironment, Optimizer (all methods), Query filtering, LLM narration
2. **All integration tests pass**: End-to-end pipeline, API endpoint, fallback chain
3. **Correctness verified**: 100% constraint satisfaction (fuel budget, assignment, non-negative cost)
4. **Performance met**: Medium problems (50 conjunctions) solve in ≤ 10 seconds
5. **Safety verified**: LLM narration 100% grounded in solver output (no fabricated numbers)
6. **Documentation complete**: design.md, requirements.md, code comments, README, test documentation
7. **Code coverage**: ≥ 85% for all core modules (cuopt_client, risk_optimizer, ai_analysis)

---

## Notes for Future Maintenance

- **Adaptive method thresholds** (5, 50 conjunctions): May need tuning based on deployment experience
- **CSR matrix construction**: Performance bottleneck for very large problems (> 10,000 candidates); consider pre-allocation / vectorization
- **LLM grounding checks**: Build automated pipeline to audit narrations for fabricated numbers (periodic validation)
- **MCTS search depth**: May need tuning based on typical problem structures (currently max_depth=10)
- **cuOpt server monitoring**: Ensure server health checks in production (fast failure / fallback critical)
