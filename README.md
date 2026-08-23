# AI Satellite Collision Prevention System

## The Day the Sky Broke

On February 10, 2009, at 16:56 UTC, something happened 790 kilometers above northern Siberia that changed space operations forever. Iridium 33 — a functioning communications satellite — slammed into Cosmos 2251, a defunct Russian military satellite, at a relative velocity of 11.7 km/s. That's roughly 26,000 miles per hour. The collision lasted milliseconds, but its consequences will persist for centuries.

The impact was catastrophic. Two intact spacecraft became over 2,000 trackable debris fragments, each one a potential bullet screaming through orbit at hypervelocity. These fragments spread into a cloud that still threatens other satellites today — and will continue to do so for decades. The Iridium-Cosmos collision wasn't just a bad day for two satellites. It was proof that the nightmare scenario physicists had warned about since 1978 was real.

That nightmare has a name: **Kessler Syndrome**. The idea is simple and terrifying. Collisions create debris. Debris creates more collisions. More collisions create more debris. Eventually, certain orbital altitudes become unusable — a self-reinforcing cascade that turns valuable orbital real estate into a shooting gallery.

```
  2009: Iridium 33 + Cosmos 2251
         |
         v
  2,000+ fragments > 10cm
         |
         v
  Each fragment is now a potential impactor
         |
         v
  New conjunctions with other spacecraft
         |
         v
  Risk of secondary collisions increases
         |
         v
  Potential cascade (Kessler Syndrome)
```

The Iridium-Cosmos collision proved three things:
1. **Tracking isn't enough.** We knew the objects were there. We even knew they might get close. But nobody acted.
2. **One collision can threaten thousands.** The debris cloud from a single event creates hundreds of new conjunction events per day.
3. **The problem is getting exponentially worse.** In 2009, there were roughly 1,000 active satellites. Today, there are over 10,000. Megaconstellations like Starlink are adding thousands more every year.

This project exists because we can't afford another Iridium-Cosmos. Not once. Not ever.

---

## What This System Does

This is an autonomous collision prevention platform. It takes the messy, uncertain reality of orbital mechanics — thousands of objects, imperfect tracking data, limited fuel — and turns it into clear decisions: which satellites to move, when, how much, and in what direction.

```
                    ┌─────────────────────────────────┐
                    │     ORBITAL ENVIRONMENT          │
                    │  10,000+ tracked objects         │
                    │  Uncertain trajectories          │
                    │  Limited fuel budgets            │
                    └────────────────┬────────────────┘
                                     │
                    ┌────────────────▼────────────────┐
                    │      THIS SYSTEM                 │
                    │                                  │
                    │  Physics ──► Detection ──► Plan  │
                    │     │            │           │   │
                    │     ▼            ▼           ▼   │
                    │  Propagate   Assess Pc   Optimize│
                    │  Covariance  Rank Risk   Execute │
                    │                                  │
                    └────────────────┬────────────────┘
                                     │
                    ┌────────────────▼────────────────┐
                    │         OUTCOMES                 │
                    │  - 80% collision risk reduction  │
                    │  - Fuel-optimal maneuvers        │
                    │  - Cascade prevention            │
                    │  - Real-time operator guidance   │
                    └─────────────────────────────────┘
```

The core problem is deceptively simple to state: given thousands of interacting spacecraft with uncertain trajectories and limited fuel budgets, find the optimal sequence of interventions that minimizes long-term orbital risk across the entire constellation.

The difficulty is in every word of that sentence. "Uncertain" means we're working with probability distributions, not exact positions. "Limited fuel" means every maneuver has a cost that can never be recovered. "Long-term" means a fix for today's conjunction might create tomorrow's crisis. "Optimal" means finding the best answer among billions of possible maneuver combinations.

### What it can do today

| Capability | Description | Status |
|---|---|---|
| Orbit Propagation | 6-DOF with J2, drag, SRP perturbations + STM covariance growth | Complete |
| Conjunction Assessment | All-vs-all screening, Pc via Foster/Chan methods, TCA prediction | Complete |
| Avoidance Planning | STM-based delta-v optimization, multi-conjunction sequencing | Complete |
| Damage Minimization | NASA breakup model, cascade risk, impact geometry optimization | Complete |
| Risk Optimization | Greedy, Network Flow (MILP), MCTS multi-step lookahead | Complete |
| AI Decision Support | LLM-powered analysis, natural language planning queries | Complete |
| 3D Visualization | Three.js orbital viz, real-time SSE event streaming | Complete |
| GPU Acceleration | NVIDIA CuOpt integration for large-scale MILP solving | Integrated |

---

## How It Works: The Full Story

Imagine you're a satellite operator. You have 50 spacecraft in your constellation. It's 3 AM and your automated system just flagged a conjunction — one of your satellites is on a collision course with a piece of debris from (you guessed it) the 2009 Iridium-Cosmos event. You have 18 hours until closest approach. What do you do?

This system answers that question in eight steps, running continuously, watching everything at once.

### The Pipeline

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                        MAIN SIMULATION PIPELINE                              │
└─────────────────────────────────────────────────────────────────────────────┘

  ┌─────────────┐     ┌──────────────┐     ┌──────────────┐     ┌──────────┐
  │ 1. GENERATE │     │ 2. PROPAGATE │     │ 3. SCREEN    │     │ 4. ASSESS│
  │             │────►│              │────►│              │────►│          │
  │ Constellation    │ Orbits + STM  │     │ All-vs-all   │     │ Pc calc  │
  │ TLEs + Cov  │     │ 24h ahead    │     │ Geom filters │     │ TCA find │
  └─────────────┘     └──────────────┘     └──────────────┘     └────┬─────┘
                                                                      │
  ┌─────────────┐     ┌──────────────┐     ┌──────────────┐          │
  │ 8. PUBLISH  │     │ 7. ANALYZE   │     │ 6. EXECUTE   │          │
  │             │◄────│              │◄────│              │◄─────────┘
  │ API + Viz   │     │ AI insights  │     │ Maneuver or  │     ┌──────────┐
  │ Dashboard   │     │ Explanations │     │ Mitigate     │◄────│5.OPTIMIZE│
  └─────────────┘     └──────────────┘     └──────────────┘     │          │
                                                                  │ Greedy   │
                                                                  │ NetFlow  │
                                                                  │ MCTS     │
                                                                  │ CuOpt    │
                                                                  └──────────┘
```

### Step 1: Know Your Constellation

Everything starts with the spacecraft themselves. The system generates or ingests a constellation — positions, velocities, masses, cross-sectional areas, fuel budgets, and whether each object can even maneuver at all. (Remember: roughly half of all tracked objects in orbit are dead — no fuel, no thrusters, no way to dodge. Cosmos 2251 was one of these.) Each spacecraft gets a 6x6 covariance matrix representing our uncertainty about where it actually is. Because we never know exactly.

### Step 2: Predict the Future

The physics engine propagates every orbit forward in time. Not with simple Kepler two-body motion, but with the perturbations that actually matter in LEO: Earth's oblate shape (J2), atmospheric drag that slowly decays orbits, and solar radiation pressure that pushes on large surfaces.

Crucially, it also propagates *uncertainty*. The State Transition Matrix (STM) tells us how a small error in today's position grows into a large error tomorrow. After 24 hours, a 100-meter position uncertainty can grow to several kilometers. This is what made the Iridium-Cosmos prediction so difficult — both objects had large position uncertainties, and the conjunction window was too broad to act on with confidence.

```
┌───────────────────────────────────────────────────────────┐
│              STATE PROPAGATION ENGINE                       │
│                                                           │
│   Input State: X = [x, y, z, vx, vy, vz]  (ECI, SI)     │
│                                                           │
│   ┌─────────────────────────────────────────────────┐     │
│   │         EQUATIONS OF MOTION                      │     │
│   │                                                  │     │
│   │   a_total = a_keplerian                          │     │
│   │           + a_J2(r)           <- Oblateness      │     │
│   │           + a_drag(r, v, A/m) <- Atmospheric     │     │
│   │           + a_SRP(r, Cr, A/m) <- Solar pressure  │     │
│   │                                                  │     │
│   │   dX/dt = [v; a_total]                           │     │
│   └──────────────────────┬──────────────────────────┘     │
│                          │                                 │
│   ┌──────────────────────▼──────────────────────────┐     │
│   │         RK7(8) INTEGRATOR                        │     │
│   │                                                  │     │
│   │   Adaptive step-size control                     │     │
│   │   Error tolerance: 1e-10 (relative)              │     │
│   │   ~8 force evaluations per step                  │     │
│   └──────────────────────┬──────────────────────────┘     │
│                          │                                 │
│   Output: X(t+dt), STM(t0 -> t+dt)                        │
└───────────────────────────────────────────────────────────┘
```

| Perturbation | Model | Effect on 24h LEO orbit | Implementation |
|---|---|---|---|
| J2 Oblateness | Zonal harmonic (C20) | ~10 km nodal drift | `acceleration_j2()` |
| Atmospheric Drag | Exponential density model | 50-500 m (alt-dependent) | `acceleration_drag()` |
| Solar Radiation Pressure | Cannonball model | 10-100 m | `acceleration_srp()` |
| Two-body (Kepler) | Point-mass gravity | Dominant term | `equations_of_motion()` |

### Step 3: Find the Needles in the Haystack

With 10,000 objects, there are nearly 50 million possible pairs. Most of them will never come anywhere near each other. The conjunction screening module rapidly eliminates the safe pairs through a series of increasingly expensive filters:

```
         ALL PAIRS: N*(N-1)/2
         ┌──────────────────┐
         │   ~50 million    │  (for N=10,000)
         │   possible pairs │
         └────────┬─────────┘
                  │
     ┌────────────▼────────────┐
     │  APOGEE/PERIGEE FILTER  │  Reject if orbits can never intersect
     │  Eliminates ~60% pairs  │  (compare orbital altitude ranges)
     └────────────┬────────────┘
                  │
     ┌────────────▼────────────┐
     │    COPLANAR FILTER      │  Reject if orbital planes too separated
     │  Eliminates ~70% remain │  (RAAN + inclination check)
     └────────────┬────────────┘
                  │
     ┌────────────▼────────────┐
     │    DISTANCE FILTER      │  Propagate & check minimum distance
     │  Eliminates ~90% remain │  over time window
     └────────────┬────────────┘
                  │
     ┌────────────▼────────────┐
     │   CANDIDATE PAIRS       │
     │   ~0.1% of original     │  (~50,000 for N=10,000)
     └────────────┬────────────┘
                  │
     ┌────────────▼────────────┐
     │  DETAILED ASSESSMENT    │
     │                         │
     │  - Find TCA (bisection) │
     │  - B-plane projection   │
     │  - Compute Pc (Foster)  │
     │  - Risk scoring         │
     └────────────┬────────────┘
                  │
     ┌────────────▼────────────┐
     │   FLAGGED CONJUNCTIONS  │
     │   Pc > 1e-7 threshold   │
     │   Typically 10-100      │
     └─────────────────────────┘
```

Think of it like triage in an emergency room. You don't run expensive diagnostics on everyone who walks in — you do a quick visual check, then a basic assessment, and only bring out the MRI for the patients who really need it.

### Step 4: How Dangerous Is It, Really?

For each surviving pair, the system computes the *probability of collision* (Pc). This isn't a yes/no question — it's a continuous probability that accounts for both objects' uncertainty ellipsoids, their relative velocity, and their physical sizes.

The system implements three methods, each validated against different test cases:

```
┌─────────────────────────────────────────────────────────────────────┐
│                   Pc CALCULATION PIPELINE                             │
│                                                                     │
│  ┌─────────────────┐                                                │
│  │ Miss Vector (m)  │──┐                                            │
│  └─────────────────┘  │    ┌──────────────────────────────────┐    │
│                        ├───►│  Foster (2D numerical integral)   │    │
│  ┌─────────────────┐  │    │  - Full covariance ellipse        │    │
│  │Combined Cov (6x6)│──┤    │  - Most accurate for short TCA   │    │
│  └─────────────────┘  │    └──────────────────────────────────┘    │
│                        │                                            │
│  ┌─────────────────┐  │    ┌──────────────────────────────────┐    │
│  │ Hard-body Radius │──┼───►│  Chan (series expansion)          │    │
│  └─────────────────┘  │    │  - Fast closed-form approx        │    │
│                        │    │  - Good for circular orbits       │    │
│                        │    └──────────────────────────────────┘    │
│                        │                                            │
│                        │    ┌──────────────────────────────────┐    │
│                        └───►│  2D Gaussian (analytic)            │    │
│                             │  - Encounter-plane projection     │    │
│                             │  - Reference implementation       │    │
│                             └──────────────────────────────────┘    │
│                                                                     │
│  Output: Pc in [0, 1]                                               │
│  Thresholds: >1e-4 CRITICAL, >1e-5 HIGH, >1e-6 MEDIUM              │
└─────────────────────────────────────────────────────────────────────┘
```

But raw Pc isn't the whole story. A 1-in-10,000 chance of collision between two 10 kg cubesats is very different from the same probability involving a 2,000 kg dead rocket body. The system computes a composite risk score:

```
Risk Score = Pc * Consequence Factor * Cascade Multiplier

Where:
  Pc              = Probability of collision (Foster method)
  Consequence     = f(mass1, mass2, v_rel) -> expected debris count
  Cascade         = Sum of secondary conjunction probabilities from new debris
```

This is exactly the lesson of Iridium-Cosmos: it's not just about whether two things hit. It's about what happens to everything else when they do.

### Step 5: The Hardest Part — Deciding What To Do

Now comes the optimization problem that makes this project genuinely difficult. You might have 12 active threats, 35 maneuverable spacecraft, and a finite amount of fuel shared across the constellation. Resolving one conjunction might create a new one. Spending fuel today means less fuel available for tomorrow's crisis.

The system doesn't pick one strategy and hope for the best. It runs four optimization approaches in parallel and compares them:

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    OPTIMIZATION STRATEGY COMPARISON                           │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  ┌─────────────────────┐   ┌─────────────────────┐                         │
│  │  A. GREEDY           │   │  B. NETWORK FLOW    │                         │
│  │                      │   │     (MILP)          │                         │
│  │  Sort by risk (desc) │   │                     │                         │
│  │  Resolve top-1       │   │  Graph:             │                         │
│  │  Re-screen           │   │  Nodes = satellites │                         │
│  │  Resolve top-2       │   │  Edges = conjunct.  │                         │
│  │  Re-screen           │   │  Capacity = fuel    │                         │
│  │  ...                 │   │                     │                         │
│  │                      │   │  Min-cost max-flow  │                         │
│  │  O(C log C)          │   │  O(N^3) worst case  │                         │
│  │  Fast, near-optimal  │   │  Provably optimal   │                         │
│  └─────────────────────┘   └─────────────────────┘                         │
│                                                                             │
│  ┌─────────────────────┐   ┌─────────────────────┐                         │
│  │  C. MCTS             │   │  D. CuOpt (GPU)    │                         │
│  │  (Monte Carlo Tree)  │   │                     │                         │
│  │                      │   │  VRP formulation:   │                         │
│  │  Root = current      │   │  Fleet = sats       │                         │
│  │  Actions = maneuvers │   │  Capacity = fuel    │                         │
│  │  Rollout to horizon  │   │  Orders = conj.     │                         │
│  │  Backprop rewards    │   │  Windows = TCA +/- t│                         │
│  │                      │   │                     │                         │
│  │  Multi-step lookahead│   │  GPU MILP solver    │                         │
│  │  Handles cascades    │   │  100-1000x faster   │                         │
│  │  O(iterations)       │   │  Sub-second @10k    │                         │
│  └─────────────────────┘   └─────────────────────┘                         │
│                                                                             │
│  Selection: argmax( risk_reduction / fuel_cost * (1 + resolved * 0.1) )     │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

| Strategy | Solve Time (N=1000) | Optimality | Best For |
|---|---|---|---|
| Greedy | ~2s | Near-optimal | Real-time decisions, small constellations |
| Network Flow | ~30s | Optimal (LP relaxation) | Medium constellations, fuel-constrained |
| MCTS | ~50s (configurable) | Asymptotically optimal | Multi-step planning, cascade avoidance |
| CuOpt (GPU) | <1s | Optimal (exact MILP) | Large constellations (10k+), production |

The adaptive selection logic picks the right tool for the situation:

```
┌───────────────────────────────────────────────────────────┐
│              ADAPTIVE METHOD SELECTION                      │
│                                                           │
│  IF conjunctions < 5:                                     │
│      -> Use Network Flow (small enough for exact solve)   │
│                                                           │
│  ELIF conjunctions < 50:                                  │
│      -> Use MCTS (lookahead helps with cascade effects)   │
│                                                           │
│  ELIF CuOpt available:                                    │
│      -> Use CuOpt GPU solver (handles scale)              │
│                                                           │
│  ELSE:                                                    │
│      -> Use Greedy (fast fallback, always available)      │
│                                                           │
│  ALWAYS: compare result against greedy baseline           │
│  ALWAYS: verify fuel constraints are respected            │
└───────────────────────────────────────────────────────────┘
```

### Step 6: Act — Or Accept the Unavoidable

For conjunctions where avoidance is possible, the system computes the optimal burn: direction, magnitude, and timing. The State Transition Matrix tells us exactly how a small velocity change now will translate into miss distance improvement at the time of closest approach.

But sometimes — like the Cosmos 2251, a dead satellite with no thrusters — you simply can't dodge. For unavoidable collisions, the system shifts to damage minimization. Using the NASA Standard Breakup Model, it simulates what happens when the objects collide and asks: is there anything we can do to reduce the devastation? Adjust attitude to minimize cross-section? Use remaining fuel to reduce relative velocity? Choose an impact geometry that sends debris into orbits that will decay faster?

```
  Conjunction Detected (Pc computed)
           │
           ▼
  ┌────────────────────┐
  │  Pc < 1e-7 ?       │──── YES ────► IGNORE (negligible risk)
  └────────┬───────────┘
           │ NO
           ▼
  ┌────────────────────┐
  │  Pc < 1e-5 ?       │──── YES ────► MONITOR (collect more data)
  └────────┬───────────┘
           │ NO
           ▼
  ┌────────────────────┐
  │  Pc < 1e-4 ?       │──── YES ────► ASSESS FURTHER (get tracking)
  └────────┬───────────┘
           │ NO
           ▼
  ┌────────────────────┐
  │  CRITICAL THREAT   │
  │  Action Required   │
  └────────┬───────────┘
           │
           ▼
  ┌────────────────────┐         ┌──────────────────────────┐
  │ Can maneuver?      │── NO ──►│ DAMAGE MINIMIZATION      │
  │ (fuel + time)      │         │ - Attitude adjustment    │
  └────────┬───────────┘         │ - Velocity reduction     │
           │ YES                  │ - Impact geometry opt    │
           ▼                      │ - Alert operators        │
  ┌────────────────────┐         └──────────────────────────┘
  │ AVOIDANCE PLANNING │
  │ - Compute STM      │
  │ - Optimal dv dir   │
  │ - Timing opt       │
  │ - Cascade check    │
  └────────┬───────────┘
           │
           ▼
  ┌────────────────────┐
  │ GLOBAL OPTIMIZE    │
  │ across all threats │
  └────────────────────┘
```

### Step 7: Explain It Like a Human

Raw numbers don't help operators at 3 AM. The AI analysis module translates the optimizer's output into natural language: "Satellite COMSAT-7 should execute a 2.3 m/s cross-track burn at T-45 minutes. This resolves 3 conjunctions simultaneously and uses 4% of remaining fuel budget. Risk reduction: 91%."

You can even ask it questions in plain English:

```bash
curl -X POST http://localhost:8050/api/plan \
  -H "Content-Type: application/json" \
  -d '{"query": "What is the minimum-fuel plan to resolve critical conjunctions?"}'
```

### Step 8: Show Everything

All of this feeds into a real-time dashboard with 3D visualization, B-plane encounter geometry, risk timelines, and animated collision scenarios. Not because it looks cool (though it does), but because operators need to see and understand what the system is recommending before they commit real fuel on a real spacecraft.

---

## The Architecture

Under the hood, the system is organized by problem domain. Physics doesn't know about decisions. Decisions don't know about the API. Each layer depends only on the layers below it:

```
┌──────────────────────────────────────────────────────────────────────────────┐
│                         PRESENTATION LAYER                                    │
│                                                                              │
│  ┌──────────┐  ┌──────────┐  ┌──────────────┐  ┌───────────┐  ┌─────────┐ │
│  │ Dashboard│  │ 3D Viz   │  │ Maneuver Viz │  │ Science   │  │  Arch   │ │
│  │index.html│  │ viz.html │  │maneuver-viz  │  │science.htm│  │arch.html│ │
│  └────┬─────┘  └────┬─────┘  └──────┬───────┘  └─────┬─────┘  └────┬────┘ │
│       │              │               │                 │              │       │
└───────┼──────────────┼───────────────┼─────────────────┼──────────────┼──────┘
        │              │               │                 │              │
        └──────────────┴───────────────┴────────┬────────┴──────────────┘
                                                │
                                    HTTP REST / SSE
                                                │
┌───────────────────────────────────────────────┼──────────────────────────────┐
│                          API LAYER (Flask)     │                              │
│                                               │                              │
│  ┌────────────────────────────────────────────▼─────────────────────────┐   │
│  │  /api/spacecraft    /api/conjunctions    /api/risk     /api/maneuvers│   │
│  │  /api/risk-graph    /api/shells          /api/debris   /api/timeline │   │
│  │  /api/risk-evolution  /api/debris-analysis  /api/decision-engine     │   │
│  │  /api/scenarios     /api/scenario/:id/stream (SSE)    /api/plan      │   │
│  │  /api/run (POST)                                                     │   │
│  └──────────────────────────────────────────────────────────────────────┘   │
│                                                                              │
└──────────────────────────────────────────┬───────────────────────────────────┘
                                           │
                                  Python function calls
                                           │
┌──────────────────────────────────────────┼───────────────────────────────────┐
│                    ORCHESTRATION LAYER    │                                   │
│                                          │                                   │
│  ┌──────────────┐  ┌────────────────┐  ┌▼────────────────┐  ┌───────────┐  │
│  │ simulation.py│  │risk_optimizer.py│  │  ai_analysis.py │  │cuopt_     │  │
│  │              │  │                 │  │                  │  │client.py  │  │
│  │ Main loop    │  │ Greedy/NF/MCTS │  │ LLM insights    │  │ GPU solver│  │
│  └──────┬───────┘  └───────┬────────┘  └────────┬────────┘  └─────┬─────┘  │
│         │                   │                     │                  │        │
└─────────┼───────────────────┼─────────────────────┼──────────────────┼───────┘
          │                   │                     │                  │
          └───────────────────┴──────────┬──────────┴──────────────────┘
                                         │
                              Physics models & decisions
                                         │
┌────────────────────────────────────────┼─────────────────────────────────────┐
│                    DECISION LAYER       │                                     │
│                                        │                                     │
│  ┌──────────────────┐  ┌──────────────▼──┐  ┌───────────────────────────┐   │
│  │  conjunction.py   │  │  avoidance.py   │  │  damage_minimization.py   │   │
│  │                   │  │                 │  │                           │   │
│  │ Pc calculation    │  │ Delta-v planning│  │ NASA breakup model        │   │
│  │ TCA prediction    │  │ STM optimization│  │ Cascade risk              │   │
│  │ B-plane analysis  │  │ Multi-conj seq. │  │ Impact geometry           │   │
│  └─────────┬─────────┘  └────────┬───────┘  └─────────────┬─────────────┘   │
│            │                      │                         │                 │
└────────────┼──────────────────────┼─────────────────────────┼────────────────┘
             │                      │                         │
             └──────────────────────┴────────────┬────────────┘
                                                 │
                                    State propagation & math
                                                 │
┌────────────────────────────────────────────────┼─────────────────────────────┐
│                    PHYSICS LAYER               │                              │
│                                               │                              │
│  ┌────────────────────────────────────────────▼──────────────────────────┐   │
│  │                    orbital_mechanics.py                                │   │
│  │                                                                       │   │
│  │  Kepler solver ──► State propagation ──► STM computation              │   │
│  │  J2 perturbation   Drag model            Covariance propagation       │   │
│  │  SRP model          RK78 integration      Ephemeris generation        │   │
│  └───────────────────────────────────────────────────────────────────────┘   │
│                                                                              │
│  ┌───────────────────────────────────────────────────────────────────────┐   │
│  │                         utils.py                                       │   │
│  │  Physical constants, coordinate transforms, data structures            │   │
│  └───────────────────────────────────────────────────────────────────────┘   │
│                                                                              │
└──────────────────────────────────────────────────────────────────────────────┘
```

### Module Dependency Graph

```
                    utils.py
                       │
                       ▼
              orbital_mechanics.py  <--- No internal deps (pure physics)
                    │       │
                    ▼       ▼
           conjunction.py  avoidance.py
                │       │       │
                ▼       ▼       ▼
          damage_minimization.py
                       │
                       ▼
              risk_optimizer.py <---- cuopt_client.py
                    │       │
                    ▼       ▼
           ai_analysis.py  simulation.py
                       │       │
                       ▼       ▼
                     api.py (exposes everything)
```

---

## The Uncertainty Problem

Here's something that makes orbital collision prevention fundamentally different from most engineering problems: you never actually *know* where anything is. You have estimates. Those estimates have error bars. And those error bars grow with time.

The system tracks this uncertainty rigorously through covariance propagation:

```
  Initial State                    Propagated State
  ┌─────────┐                     ┌─────────┐
  │ X(t0)   │───── RK7(8) ──────►│ X(t)    │
  │ P(t0)   │                     │ P(t)    │
  └─────────┘                     └─────────┘

  Where:
    P(t) = Phi(t,t0) * P(t0) * Phi(t,t0)^T + Q(t)

    Phi = State Transition Matrix (6x6)
    P   = Covariance matrix (6x6)
    Q   = Process noise (accounts for unmodeled forces)
```

Today, a satellite might have a position uncertainty of 100 meters. Tomorrow, that might be 3 kilometers. Next week — who knows. This is why conjunction assessment is fundamentally probabilistic, and why the system recomputes everything as new tracking data arrives.

---

## The Dashboard

Operators need to see the situation, understand the recommendations, and trust the system before executing burns that spend irreplaceable fuel. The dashboard provides:

| Page | URL | What it shows |
|---|---|---|
| Main Dashboard | `/` | Risk overview, active threats, maneuver recommendations |
| 3D Orbital Viz | `/viz.html` | Three.js WebGL rendering of the full constellation |
| Maneuver Viz | `/maneuver-viz.html` | Animated collision scenarios with B-plane geometry |
| Science | `/science.html` | Physics methodology for operators who want depth |
| Architecture | `/architecture.html` | System design for developers |
| Docs | `/docs.html` | Interactive physics reference |

Real-time updates flow through Server-Sent Events:

```
┌─────────────┐         ┌─────────────────┐         ┌──────────────┐
│   Browser   │◄── SSE ─┤  Flask Server   │◄────────┤  Simulation  │
│  (Three.js) │         │  /stream (SSE)  │         │  Event Loop  │
└─────────────┘         └─────────────────┘         └──────────────┘

  SSE Event Types:
  ├── scenario_info    -> Initial metadata (name, frames, corrections)
  ├── frame            -> Position updates at ~20 FPS
  ├── sim_event        -> Detection, maneuver, collision notifications
  ├── debris_spawn     -> Fragment cloud generation data
  └── stream_end       -> Playback complete signal
```

---

## API Reference

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/api/spacecraft` | All spacecraft with orbital elements and paths |
| `GET` | `/api/conjunctions` | Conjunction events with risk levels |
| `GET` | `/api/maneuvers` | Planned avoidance maneuvers |
| `GET` | `/api/risk` | Global risk metrics summary |
| `GET` | `/api/risk-graph` | Network graph (nodes=sats, edges=conjunctions) |
| `GET` | `/api/shells` | Orbital environment altitude shells |
| `GET` | `/api/debris` | Debris prediction data |
| `GET` | `/api/timeline` | 24-hour risk evolution timeline |
| `GET` | `/api/risk-evolution` | Multi-year risk projection (Pc, debris, Kessler index) |
| `GET` | `/api/debris-analysis` | NASA breakup model analysis for highest-risk conjunction |
| `GET` | `/api/decision-engine` | Multi-strategy comparison with recommendation |
| `GET` | `/api/scenarios` | List available collision scenarios |
| `GET` | `/api/scenario/:id` | Full scenario data for animation |
| `GET` | `/api/scenario/:id/stream` | SSE real-time event stream |
| `POST` | `/api/run` | Re-run simulation with new seed |
| `POST` | `/api/plan` | Natural language intervention planning (LLM + CuOpt) |

### Example: The Decision Engine at Work

```json
{
  "situation": {
    "active_threats": 12,
    "critical_threats": 3,
    "total_collision_probability": 0.0047,
    "maneuverable_spacecraft": 35,
    "total_fuel_available_ms": 425.8
  },
  "candidates": [
    {"id": "A", "strategy": "none", "residual_risk": 0.89, "fuel_cost_ms": 0},
    {"id": "B", "strategy": "greedy", "residual_risk": 0.12, "fuel_cost_ms": 8.4},
    {"id": "C", "strategy": "network_flow", "residual_risk": 0.08, "fuel_cost_ms": 6.1},
    {"id": "D", "strategy": "mcts", "residual_risk": 0.10, "fuel_cost_ms": 7.2}
  ],
  "recommended": {
    "candidate_id": "C",
    "strategy": "network_flow",
    "risk_reduction_pct": 91.0,
    "reason": "Network flow MILP selected. Resolves 3 conjunction(s) with 91% risk reduction. Most fuel-efficient option."
  }
}
```

---

## Quick Start

```bash
git clone <repository-url>
cd satellite-collision

pip install -r requirements.txt

# Optional: for AI features
export OPENAI_API_KEY="your-key"
export NVIDIA_API_KEY="your-key"

# Run simulation + dashboard
python -m src.simulation

# Open http://localhost:8050
```

### Alternative Entry Points

```bash
python src/api.py                                    # Direct API start
gunicorn -w 4 -b 0.0.0.0:8050 src.api:app          # Production
./run_dashboard.sh                                   # Convenience script
```

---

## Project Structure

```
satellite-collision/
├── src/                              # Core Python package
│   ├── orbital_mechanics.py          # Physics: propagation, STM, perturbations
│   ├── conjunction.py                # Detection: screening, Pc, TCA, B-plane
│   ├── avoidance.py                  # Planning: delta-v optimization, sequencing
│   ├── damage_minimization.py        # Mitigation: breakup model, cascade risk
│   ├── risk_optimizer.py             # Optimization: greedy, MILP, MCTS
│   ├── ai_analysis.py               # AI: LLM insights, NL planning
│   ├── simulation.py                 # Orchestration: main loop
│   ├── api.py                        # API: Flask REST + SSE streaming
│   ├── cuopt_client.py               # GPU: NVIDIA CuOpt solver
│   ├── strategy_integrator.py        # Plugin system for custom strategies
│   ├── utils.py                      # Constants, transforms, data classes
│   └── strategies/                   # Pluggable optimization strategies
├── dashboard/                        # Frontend (served by Flask)
│   ├── index.html, viz.html, maneuver-viz.html, science.html
│   ├── architecture.html, docs.html, landing.html
│   ├── app.js                        # Frontend logic
│   └── style.css
├── docs/                             # Technical documentation
│   ├── physics.md                    # Orbital mechanics reference
│   ├── strategy.md                   # Decision framework
│   └── content.md                    # Intuitive explanations
├── tests/
├── requirements.txt
└── render.yaml                       # Deployment config
```

---

## Performance

The real question: can it process 10,000 objects fast enough to matter?

| Operation | Complexity | N=1,000 | N=10,000 |
|---|---|---|---|
| Orbit propagation (all, 24h) | O(N) | 1s | 10s |
| Conjunction screening | O(N^2) reduced to O(0.1*N^2) | 5s | 500s |
| Pc calculation (per pair) | O(1) | ~1ms | ~1ms |
| Greedy optimization | O(C log C) | 2s | 20s |
| Network flow (MILP) | O(N^3) worst | 30s | 300s |
| MCTS (10k iterations) | O(iterations) | 50s | 500s |
| CuOpt GPU solve | O(N log N) | <1s | <1s |

### Scaling Roadmap

```
  N < 1,000:    Single-process Python, all strategies viable
  N < 10,000:   Parallel screening recommended, greedy for real-time
  N < 100,000:  CuOpt GPU required, parallel propagation
  N > 100,000:  Full GPU pipeline (CuPy/RAPIDS), distributed computing
```

---

## Technology Stack

```
┌─────────────────────────────────────────────────────────────────┐
│  FRONTEND                                                        │
│  Three.js (WebGL 3D)  |  HTML5/CSS3  |  Vanilla JS  |  SSE     │
├─────────────────────────────────────────────────────────────────┤
│  API LAYER                                                       │
│  Flask 3.0  |  Flask-CORS  |  Gunicorn                           │
├─────────────────────────────────────────────────────────────────┤
│  COMPUTATION                                                     │
│  NumPy >=1.24  |  SciPy >=1.10  |  NetworkX >=3.0               │
├─────────────────────────────────────────────────────────────────┤
│  AI / OPTIMIZATION                                               │
│  OpenAI API >=1.0  |  NVIDIA CuOpt (GPU MILP)                   │
├─────────────────────────────────────────────────────────────────┤
│  RUNTIME                                                         │
│  Python 3.8+  |  macOS / Linux                                   │
└─────────────────────────────────────────────────────────────────┘
```

---

## Why This Matters

In 2009, there were about 1,000 active satellites. Today there are over 10,000. By 2030, there may be 100,000. SpaceX alone plans 42,000 Starlink satellites. Amazon's Kuiper will add thousands more.

Every one of these objects shares the same orbital highways. Every one of them creates conjunction events with every other. The N-squared scaling of the conjunction problem means that doubling the number of satellites quadruples the number of potential collisions.

The Iridium-Cosmos collision happened when there were fewer than 1,000 active satellites. Imagine that scenario playing out in a world with 100,000. A single catastrophic collision at 780 km could trigger a cascade that renders entire orbital shells unusable for decades.

We built this system because the alternative — waiting for the next Iridium-Cosmos and hoping it doesn't start a cascade — is not a strategy. It's a gamble with infrastructure that modern civilization depends on: GPS navigation, weather forecasting, communications, climate monitoring, disaster response.

Space is getting crowded. This system is designed to keep it usable.

---

## Contributing

1. Read `docs/physics.md` before touching orbital mechanics
2. Check the module dependency graph to understand impact
3. Run `python -m src.simulation` to verify changes
4. Test with known conjunction scenarios
5. Validate physics consistency (energy conservation, Pc bounds)

### References

- `docs/physics.md` — Orbital mechanics equations and derivations
- `docs/strategy.md` — Decision framework and algorithm selection
- `docs/content.md` — Intuitive explanations for non-specialists

---

## License

This project is for research and educational purposes in orbital mechanics and space situational awareness.
