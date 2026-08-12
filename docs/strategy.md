# Intervention Strategy & Decision Framework

## The Central Question

> Given thousands of interacting spacecraft, uncertainty in their trajectories,
> limited maneuvering capability, and future collision risks, what sequence of
> interventions minimizes long-term orbital risk?

## Decision Hierarchy

```
Level 1: DETECT     → Conjunction screening (all-vs-all)
Level 2: ASSESS     → Probability of collision for flagged pairs
Level 3: DECIDE     → Maneuver/accept/monitor decision
Level 4: PLAN       → Optimal maneuver design
Level 5: MITIGATE   → If unavoidable, minimize damage
Level 6: ADAPT      → Update risk model with new information
```

## Screening: Reducing O(N²) to Manageable

With N = 10,000 objects, N²/2 ≈ 50 million pairs per epoch.

### Smart Filters (progressive elimination):
1. **Apogee-perigee filter**: Objects can't meet if perigee₁ > apogee₂
2. **Orbital plane filter**: Non-intersecting planes → no conjunction
3. **Time filter**: Propagate and check only during orbital crossings
4. **Distance threshold**: Flag only if min distance < 5 km

Result: ~50M pairs → ~1000 flagged conjunctions per day (typical for LEO constellation).

## Risk Scoring

Each conjunction gets a composite risk score:

```
Risk_j = Pc_j × Consequence_j × Cascade_factor_j
```

Where:
- **Pc_j**: Probability of collision (from covariance analysis)
- **Consequence_j**: Expected debris count if collision occurs
  ```
  Consequence = f(m₁, m₂, v_rel, altitude)
  ```
- **Cascade_factor_j**: Multiplier for downstream collision potential
  ```
  Cascade = 1 + density(altitude) × debris_lifetime(altitude)
  ```

## Maneuver Decision Logic

```python
if Pc < 1e-7:
    action = MONITOR
elif Pc < 1e-5:
    action = ASSESS_FURTHER  # refine orbit, get more tracking data
elif Pc < 1e-4:
    action = CONSIDER_MANEUVER  # cost-benefit analysis
else:
    action = MANEUVER  # unless fuel-critical
```

### Cost-Benefit for Maneuver Decision:

```
Benefit = ΔRisk = Risk_before - Risk_after
Cost = Δv_used / Δv_remaining × future_risk_coverage_lost
```

Maneuver if Benefit/Cost > threshold.

## Multi-Conjunction Planning

When one satellite faces multiple conjunctions in sequence:

### Greedy Approach (baseline):
- Handle highest-risk conjunction first
- Re-assess remaining conjunctions after maneuver
- Repeat

### Optimal Approach (what we implement):
- Joint optimization over all conjunctions in planning window
- Single maneuver may resolve multiple conjunctions
- Consider fuel for future (unknown) conjunctions via reserve margin

### Graph-Based Risk Network:
```
Nodes = spacecraft
Edges = conjunctions (weighted by risk)
```

Maneuver planning becomes a network flow optimization:
- Minimize total edge weights (risk) 
- Subject to node constraints (fuel budgets)
- With temporal ordering constraints

## Unavoidable Collision Protocol

When Δv_required > Δv_available, or TCA is too imminent:

### Priority Actions:
1. **Alert**: Notify all operators of objects in debris risk zone
2. **Attitude**: Orient for minimum cross-section to impact
3. **Relative velocity reduction**: Use remaining Δv to slow approach
4. **Altitude selection**: If possible, bias collision to lower altitude
5. **Safe mode**: Protect critical spacecraft systems

### Post-Collision Response:
1. Track new debris (expected fragment cloud)
2. Re-screen all objects against new debris
3. Emergency maneuver planning for newly-threatened spacecraft
4. Update long-term risk models

## Reinforcement Learning Formulation

### State Space:
- Orbital elements of all N spacecraft (6N continuous)
- Covariance matrices (uncertainty)
- Fuel levels (N continuous)
- Upcoming conjunction list

### Action Space:
- For each maneuverable spacecraft: Δv vector (3 continuous per object)
- Timing of maneuver (1 continuous per object)

### Reward Function:
```
R = -α·Σ Pc_j  (minimize collision probability)
    -β·Σ |Δv|  (minimize fuel usage)
    -γ·E[debris_generated]  (minimize cascade risk)
    +δ·Σ clearance_margins  (reward safe separations)
```

### Episode Structure:
- Planning horizon: 7 days (short-term tactical)
- Strategic horizon: 1 year (fuel budget allocation)
- Each step: 1 conjunction decision point

## Performance Metrics

| Metric | Target |
|--------|--------|
| Conjunctions resolved without maneuver | >90% (via better tracking) |
| Maneuver success rate | >99.9% |
| Fuel efficiency (risk reduction per m/s) | Maximize |
| False alarm rate | <20% |
| Cascade risk increase | 0% (never make things worse) |
| Response time (detection to decision) | <2 hours |
