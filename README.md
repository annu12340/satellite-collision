# AI Satellite Collision Prevention System

## Index

- [Demo](#demo)
- [The Elevator Pitch](#the-elevator-pitch)
- [How is Kiro Used](#how-is-kiro-used)
- [The Day the Sky Broke](#the-day-the-sky-broke)
- [What This System Does](#what-this-system-does)
- [How It Works: The Full Story](#how-it-works-the-full-story)
- [The Architecture](#the-architecture)
- [The Uncertainty Problem](#the-uncertainty-problem)
- [The Dashboard](#the-dashboard)
- [API Reference](#api-reference)
- [Quick Start](#quick-start)
- [Setup](#setup)
- [Running the System](#running-the-system)
- [Testing](#testing)
- [Troubleshooting](#troubleshooting)
- [Project Structure](#project-structure)
- [Performance](#performance)
- [Technology Stack](#technology-stack)
- [Why This Matters](#why-this-matters)
- [Why We Need AI](#why-we-need-ai)
- [Innovation & Roadmap](#innovation--roadmap)
- [Contributing](#contributing)
- [License](#license)

---

## Demo

| | |
|---|---|
| **Video walkthrough** | *https://www.youtube.com/watch?v=03x7psL5sz8* |
| **Live dashboard** | *https://satellite-collision-1.onrender.com/* |
| **More detailed docs** | *https://satellite-collision-1.onrender.com/docs* |
| **Screenshots** | See [The Dashboard](#the-dashboard) section below for annotated screenshots and visualization output |

The demo walkthrough should cover: launching the simulation, the 3D orbital view detecting a conjunction, the decision engine comparing optimization strategies, an AI-generated maneuver recommendation, and a look at how Kiro's specs/steering/hooks were used to build the feature end-to-end (see [How is Kiro Used](#how-is-kiro-used)).

## The Elevator Pitch

### The Problem

Three numbers explain why this project exists.

- **$2.2 trillion** — roughly the size of the global economy that sits on top of satellite infrastructure. GPS alone is estimated at $1.4 trillion of value to the U.S. economy. Ridesharing, payment networks, precision agriculture, and military logistics all depend on satellites staying where they're supposed to be.
- **~50 million** — the number of possible collision pairs among just 10,000 tracked objects in orbit (N·(N-1)/2 scaling). Every additional satellite makes the problem quadratically worse, not linearly.
- **~25 m/s** — a typical total delta-v fuel budget for a satellite's entire 15-year operational life. Not per year — total. Every avoidance maneuver permanently spends down that budget; there's no refueling in orbit.

Today, conjunction response is largely manual: an analyst gets a warning, opens a spreadsheet, calls the operator, the operator calls engineering, and a team spends hours deciding whether a 1-in-10,000 collision probability justifies burning fuel — for one conjunction, out of hundreds flagged per week. That process doesn't scale as constellations grow into the tens of thousands of objects.

### Our Solution

This system automates that decision loop end-to-end, turning a process that takes human teams hours into one that runs in seconds. It's built from five cooperating layers (each detailed further in [How It Works: The Full Story](#how-it-works-the-full-story)):

1. **Physics engine** — 6-DOF orbit propagation (J2 oblateness, atmospheric drag, solar radiation pressure) plus full 6x6 covariance propagation via the State Transition Matrix, so the system tracks not just where objects are but how uncertain that estimate is.
2. **Conjunction screening** — a cascade of cheap geometric filters (altitude, plane, distance) cuts ~50 million raw pairs down to the tens that actually warrant a full probability-of-collision calculation.
3. **Multi-objective optimizer** — Greedy, Network Flow (MILP), Monte Carlo Tree Search, and GPU-accelerated CuOpt all run and get compared, with an adaptive selector picking the best fit for the situation. MCTS-style multi-step lookahead can find solutions that use significantly less fuel than a pure greedy approach by avoiding maneuvers that create worse conjunctions days later.
4. **Damage minimization** — when a maneuver isn't possible (dead satellite, insufficient fuel, insufficient warning time), the system falls back to the NASA Standard Breakup Model to find the least-bad outcome: minimizing cross-section, biasing impact geometry, and steering debris toward orbits that decay faster.
5. **AI explainability** — every recommendation comes with a plain-language rationale (which conjunctions it resolves, fuel cost versus alternatives, remaining budget for known upcoming threats) instead of a bare "this strategy was selected" output. See [Why We Need AI](#why-we-need-ai) for why this is a deliberate layer on top of the physics, not baked into it.

### Why This Is Hard

This isn't CRUD-app-with-a-space-theme difficulty. It combines several genuinely hard problems at once:

- An **NP-hard, multi-resource, multi-constraint, multi-horizon** optimization problem — not a single collision, but the entire constellation's fuel budget over a multi-day planning window.
- **Real 6-DOF orbital dynamics**, not simplified circular-orbit approximations.
- **Uncertainty quantification** via covariance propagation — the system never treats a position estimate as exact.
- **Irreversible resource constraints** — fuel spent avoiding today's conjunction is fuel that doesn't exist for tomorrow's.
- **Cascade effects** — resolving one conjunction can change the risk landscape for every other object, so every action has to be re-evaluated against the whole constellation.
- **Real-time 3D rendering** of the result, because operators need to see and trust a recommendation before committing irreplaceable fuel.

### The Market

- **SpaceX** operates 6,000+ Starlink satellites and performs on the order of 10,000+ collision-avoidance maneuvers per year.
- **Amazon Kuiper**, **OneWeb** (648 satellites), **Telesat** (298), and **Planet Labs** (200+) are all adding to the same crowded orbital shells.
- The space traffic management market is projected to reach roughly **$1.6 billion by 2030**.
- Conjunction screening for the entire tracked catalog is currently performed largely manually by the U.S. Space Force, at no cost to operators worldwide — a process that does not scale as the tracked object count moves toward 100,000+.

### Tech Stack

- **Python + NumPy/SciPy** for orbital mechanics and numerical integration.
- **NetworkX** for conjunction risk graphs and min-cost flow optimization.
- **NVIDIA CuOpt** for GPU-accelerated MILP solving at scale (with a local CPU fallback — see [Step 5](#step-5-the-hardest-part--deciding-what-to-do)).
- **OpenAI / NVIDIA NIM (LLM)** to translate optimizer output into operator-readable recommendations.
- **Flask** for the REST API serving real-time risk metrics.
- **Three.js** for in-browser 3D orbital visualization.

Full dependency details, versions, and rationale are in [Technology Stack](#technology-stack) and [Setup](#setup).

---

## How is Kiro Used

This project was built inside [Kiro](https://kiro.dev), and it leans on Kiro's spec, steering, and hook systems rather than just using it as a chat-based code generator. Here's how each piece is actually wired up in `.kiro/`.

| Kiro feature | Where it lives | What it does here |
|---|---|---|
| Specs | `.kiro/specs/` (9 features) | Requirements → design → tasks for every physics module and most dashboard features |
| Steering | `.kiro/steering/` (6 docs) | Always-on architecture/context injected into every session |
| Hooks | `.kiro/hooks/` (9 hooks) | Lint/format on save, physics safety gate, post-task validation, custom strategy auto-wiring, git commit workflow |

### Specs — structured feature development

Every non-trivial feature in this codebase went through Kiro's spec workflow (`.kiro/specs/`) instead of an ad-hoc prompt-and-hope loop, using the `requirements.md` → `design.md` → `tasks.md` progression. Not every spec carries all three files — the foundational physics specs stopped at `design.md` (implemented directly against a documented design), while later UI-focused specs were scoped with `requirements.md` and `tasks.md` and skipped a separate design doc since the change was small and visual:

```
.kiro/specs/
├── orbital-mechanics/              # requirements + design   — core propagation, STM, perturbations
├── conjunction-assessment/         # requirements + design   — screening, Pc calculation, TCA
├── avoidance-maneuver-planning/    # requirements + design   — delta-v optimization
├── simulation-engine/              # requirements + design   — main event loop orchestration
├── cuopt-intervention-planning/    # requirements + design + tasks — GPU MILP maneuver sequencing
├── live-bplane-encounter-geometry/ # requirements + tasks    — real-time B-plane visualization
├── catastrophic-threshold-gauge/   # requirements + tasks    — risk threshold UI component
├── mark-tca-zone-3d-visualization/ # requirements only       — 3D TCA marker rendering
└── cuopt-fuel-allocation/          # initialized, not yet written — GPU fuel budget optimization
```

This matters a lot for a physics-heavy codebase: the `design.md` for `cuopt-intervention-planning` documents the MILP formulation and constraint set *before* a line of `cuopt_client.py` gets touched, and its `tasks.md` breaks that design into checkable implementation steps that Kiro executes and tracks one at a time. `cuopt-fuel-allocation` is an example of a spec that was scaffolded for a follow-on feature (per-satellite fuel budget allocation via MILP) but not carried further yet — left as-is here rather than backfilled, since overstating its status wouldn't reflect what was actually built.

### Steering — always-on project context

Six steering docs in `.kiro/steering/` are injected into every session automatically, so Kiro never has to rediscover the architecture from scratch:

| File | What it encodes |
|---|---|
| `project-context.md` | Module map, data structures (spacecraft state, conjunction event, maneuver plan), API contract |
| `project-roadmap.md` | Phase plan, success metrics, risk register |
| `architecture-deep-dive.md` | Layered design principles, data flow diagrams, decision algorithm hierarchy |
| `technical-stack.md` | Dependency rationale, performance characteristics, complexity tables |
| `development-practices.md` | Module dependency graph, code review checklist for physics vs. API changes |
| `physics-change-guard.md` | Hard constraints for anything touching orbital mechanics |

Because these are steering files (not one-off chat context), they stay consistent across every session and every contributor using Kiro on this repo, instead of each person re-explaining the architecture in their own words.

### Hooks — the automation layer

This is the part worth calling out in detail. `.kiro/hooks/` has 9 hook definitions, each a JSON file Kiro reads and executes directly with no manual triggering required. They cover several different concerns:

**1. Session context injection (`SessionStart`)**
- `project-context-injection.json` and `development-practices-injection.json` fire the moment a new Kiro session opens and inject the architecture map and coding conventions straight into context via an `agent` action. This is what makes the steering docs above actually *active* rather than just reference material sitting in a folder — every session starts already knowing the module dependency graph, coordinate conventions, and debugging playbooks.

**2. Code quality automation (`PostFileSave` / `PostFileCreate`)**
- `lint-on-save.json` — matches `\.py$`, runs `ruff check --fix` on every Python file the moment it's saved.
- `format-on-create.json` — matches `\.py$`, runs `ruff format` on brand new Python files right after creation, so nothing lands unformatted.
- `dependency-check.json` — matches `requirements\.txt$`, runs `pip check` whenever the requirements file changes, catching dependency conflicts (e.g. NumPy/SciPy version clashes) immediately instead of at install time.

**3. Physics safety gate (`PreToolUse`)** — the most interesting one
- `physics-safety-gate.json` matches on the tool name (`fs_write|str_replace`) and fires *before* any write tool runs. Its `agent` action instructs Kiro to check whether the target is a physics-critical file (`orbital_mechanics.py`, `conjunction.py`, `damage_minimization.py`) and, if so, enforce five rules before the write is allowed through:
  1. **Coordinate convention** — position vectors must stay in ECI; any other frame (RTN, LVLH, perifocal) requires an explicit conversion back at the function boundary.
  2. **Unit consistency** — no mixing SI and km-based units within a function; new constants must cite units and source.
  3. **Covariance integrity** — any covariance matrix construction/modification must preserve symmetry and positive semi-definiteness, with eigenvalues clamped to ≥1e-10.
  4. **Formula provenance** — new or modified physics formulas need a comment citing `docs/physics.md`, a publication, or a named standard (e.g. NASA Standard Breakup Model).
  5. **Conservation laws** — propagation changes can't silently break energy conservation in the unperturbed two-body case.
  
  If a proposed edit to one of those files would violate a rule, the hook returns a `permissionDecision: "ask"`, which pauses the write and surfaces the concern to the user for explicit approval rather than silently applying a physics-breaking change. Edits to unrelated files (docs, dashboard, README) pass through untouched.

**4. Post-task validation (`PostTaskExec`)**
- `post-task-validation.json` fires after any spec task is marked complete. It imports the five core modules (`orbital_mechanics`, `conjunction`, `avoidance`, `damage_minimization`, `risk_optimizer`) in sequence and prints a pass/fail per module. This catches broken imports, circular dependencies, or syntax errors from an implementation task before moving to the next one — a cheap regression check that runs automatically instead of relying on someone remembering to do it.

**5. Custom strategy integration (`PostFileCreate`)**
- `strategy-auto-integrator.json` matches `src/strategies/custom_.*\.py$` — the moment a new file matching that pattern is created (see `custom_fuel_efficiency.py`, `custom_relative_velocity.py`), it runs `src/strategy_integrator.py` against the new file to validate and register the strategy automatically, instead of requiring a manual wiring step.

**6. Git workflow (`Stop`)**
- `smart-git-commit.json` fires when a session ends. Instead of auto-committing, its `agent` action reviews `git status`/`git diff`, drafts a single-line conventional-commit message, and explicitly asks the user for approval before staging and committing anything. Nothing gets committed without a human sign-off.

Together, these hooks mean the physics-safety review, linting, dependency checks, and post-implementation validation happen automatically as a side effect of normal editing — not as separate manual steps someone has to remember to run.

---

## The Day the Sky Broke

On February 10, 2009, at 16:56 UTC, something happened 790 kilometers above northern Siberia that changed space operations forever. Iridium 33 — a functioning communications satellite — slammed into Cosmos 2251, a defunct Russian military satellite, at a relative velocity of 11.7 km/s. That's roughly 26,000 miles per hour. The collision lasted milliseconds, but its consequences will persist for centuries.

The impact was catastrophic. Two intact spacecraft became over 2,000 trackable debris fragments, each one a potential bullet screaming through orbit at hypervelocity. These fragments spread into a cloud that still threatens other satellites today — and will continue to do so for decades. The Iridium-Cosmos collision wasn't just a bad day for two satellites. It was proof that the nightmare scenario physicists had warned about since 1978 was real.

### The Kessler Syndrome

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

### What the Collision Proved

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

### The Core Problem

The core problem is deceptively simple to state: given thousands of interacting spacecraft with uncertain trajectories and limited fuel budgets, find the optimal sequence of interventions that minimizes long-term orbital risk across the entire constellation.

The difficulty is in every word of that sentence. "Uncertain" means we're working with probability distributions, not exact positions. "Limited fuel" means every maneuver has a cost that can never be recovered. "Long-term" means a fix for today's conjunction might create tomorrow's crisis. "Optimal" means finding the best answer among billions of possible maneuver combinations.

### What It Can Do Today

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
| CuOpt (GPU) | <1s | Optimal (exact MILP) | Large constellations (10k+), production* |

\* `cuopt_client.py` speaks NVIDIA cuOpt's documented MILP wire format (`csr_constraint_matrix` / `objective_data` / `variable_bounds`, etc.) and will call a self-hosted cuOpt GPU server when `CUOPT_SERVER_IP` is set. Without GPU hardware, it solves the identical `problem_data` structure locally via `scipy.optimize.milp` (HiGHS backend) — same formulation, CPU-bound instead of sub-second. This keeps the repo runnable standalone (no GPU/credentials required to reproduce results) while remaining a drop-in swap to real hardware.

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

### Screenshots

| | |
|---|---|
| ![Dashboard overview](docs/images/Screenshot.png) | ![Dashboard detail](docs/images/Screenshot2.png) |
| ![3D orbital visualization](orbits_3d.png) | ![Risk timeline](risk_timeline.png) |
| ![Risk evolution projection](risk_evolution.png) | ![Debris breakup analysis](debris_analysis.png) |

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

# Optional: for AI features (see "Getting an NVIDIA API Key" in Setup below)
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

## Setup

### Prerequisites

- Python 3.8+
- pip (or pip3)
- A terminal with access to the project root

### Installation

```bash
# Clone or navigate to the project directory
cd satellite-collision

# Create a virtual environment (recommended)
python3 -m venv venv
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt
```

### Dependency Summary

| Package | Version | Purpose |
|---------|---------|---------|
| numpy | >=1.24.0 | Orbital state vectors, matrix operations |
| scipy | >=1.10.0 | ODE integration, optimization |
| matplotlib | >=3.7.0 | Trajectory and risk plots |
| networkx | >=3.0 | Risk network graph analysis |
| flask | >=3.0.0 | REST API server |
| flask-cors | >=4.0.0 | Cross-origin requests for dashboard |
| openai | >=1.0.0 | LLM-powered analysis |
| requests | >=2.31.0 | HTTP client for CuOpt API |
| gunicorn | >=21.2.0 | Production WSGI server |

### Environment Variables

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `OPENAI_API_KEY` | For OpenAI-based AI analysis | — | OpenAI API key for LLM insights |
| `NVIDIA_API_KEY` | For NVIDIA NIM-based AI analysis | — | Powers `src/ai_analysis.py` (natural language risk narration, maneuver explanations, `/api/plan`). See [Getting an NVIDIA API Key](#getting-an-nvidia-api-key-free) below |
| `CUOPT_SERVER_IP` | For GPU-accelerated optimization | — | Hostname/IP of a self-hosted NVIDIA cuOpt server. If unset, `risk_optimizer.py` transparently falls back to a local CPU MILP solver (scipy/HiGHS) — no key needed for this path |
| `CUOPT_SERVER_PORT` | No | `5000` | Port of the self-hosted cuOpt server |
| `CUOPT_POLL_TIMEOUT` | No | `25` | Seconds to wait per poll when solving against a remote cuOpt server |
| `SIM_SEED` | No | `42` | Random seed for reproducible simulation |
| `PORT` | No | `8050` | Server port (production entry point) |

### Getting an NVIDIA API Key (Free)

The AI analysis module (`src/ai_analysis.py`) talks to NVIDIA's hosted NIM endpoint (`integrate.api.nvidia.com/v1`, model `nvidia/llama-3.3-nemotron-super-49b-v1`) using an OpenAI-compatible client. This is separate from CuOpt — CuOpt's GPU solver is a different, optional self-hosted service and doesn't require an API key at all.

1. Go to **[build.nvidia.com](https://build.nvidia.com)** and sign in (or create a free account).
2. Search for or open any hosted model card — e.g. **Llama 3.3 Nemotron Super 49B** (the model this project uses) — under the "Models" catalog.
3. On the model page, open the **"Get API Key"** / **"Build with this NIM"** panel and click **Generate API Key**. NVIDIA provides a free tier of API credits for evaluation, no credit card required to get started.
4. Copy the generated key (it looks like `nvapi-...`).
5. Export it before running the simulation:
   ```bash
   export NVIDIA_API_KEY="nvapi-your-key-here"
   ```
   Or add it to a `.env` file in the project root if you're using something like `python-dotenv`.
6. Run the simulation as usual (`python -m src.simulation`). AI-narrated risk insights and the `/api/plan` natural-language endpoint will now work.

If `NVIDIA_API_KEY` is not set, the rest of the system (physics, optimization, dashboard) still runs normally — `ai_analysis.py` simply raises `EnvironmentError` only when an AI-analysis endpoint is actually called, and `/api/plan` will report the missing key rather than crashing the simulation.

---

## Running the System

### Development (local)

```bash
# Option 1: Run the simulation + API server directly
python -m src.simulation

# Option 2: Use the convenience script
chmod +x run_dashboard.sh
./run_dashboard.sh

# Option 3: Run just the API (with simulation on startup)
python app.py
```

The dashboard is accessible at **http://localhost:5000** (or port 8050 for `app.py`).

### Production (Render / Gunicorn)

```bash
gunicorn app:app --bind 0.0.0.0:$PORT --timeout 120 --workers 1
```

The `app.py` entry point runs the simulation once on import, then serves API requests. Worker count is kept at 1 because the simulation state is in-memory.

---

## Testing

### Strategy Integration Tests

The test suite validates the custom strategy auto-wiring pipeline (parsing, validation, registration, execution):

```bash
python3 tests/test_strategy_integration.py
```

This runs 9 tests covering:
- Valid strategy file parsing
- Invalid filename rejection
- Missing function detection
- Wrong parameter count rejection
- Missing return type rejection
- Strategy execution with real conjunction data
- Duplicate registration prevention
- Runtime error graceful handling
- Real `custom_relative_velocity` strategy execution

Expected output:
```
======================================================================
STRATEGY INTEGRATION TEST SUITE
======================================================================

✓ PASS: Parse valid strategy file
✓ PASS: Reject invalid filename
✓ PASS: Reject missing function
✓ PASS: Reject wrong parameter count
✓ PASS: Reject missing return type
✓ PASS: Strategy execution with real data
✓ PASS: Duplicate strategy rejection
✓ PASS: Runtime error handling
✓ PASS: Real relative_velocity strategy

======================================================================
Results: 9/9 tests passed
======================================================================
```

### Manual Verification Checklist

After making changes, verify the following:

1. **Simulation runs without error:**
   ```bash
   python -m src.simulation
   ```

2. **API endpoints respond:**
   ```bash
   curl http://localhost:5000/api/risk
   curl http://localhost:5000/api/conjunctions
   curl http://localhost:5000/api/maneuvers
   curl http://localhost:5000/api/shells
   ```

3. **Dashboard loads:** Open http://localhost:5000 in a browser and confirm data renders.

4. **Physics sanity checks:**
   - Risk scores are in a reasonable range (0 to ~0.1 for typical scenarios)
   - Conjunctions have Pc values between 0 and 1
   - Maneuver delta-v values are physically plausible (< 10 m/s for routine avoidance)

### Adding a Custom Strategy (Quick Test)

To verify the strategy integration pipeline works end-to-end:

1. Create `src/strategies/custom_test_metric.py`:
   ```python
   from typing import List
   from src.conjunction import Conjunction
   from src.orbital_mechanics import Spacecraft
   import numpy as np

   def evaluate_test_metric(
       conjunction: Conjunction,
       spacecraft_list: List[Spacecraft]
   ) -> float:
       """Simple test: return normalized miss distance."""
       return min(conjunction.miss_distance / 10.0, 1.0)
   ```

2. Run the integration tests to confirm it's picked up:
   ```bash
   python3 tests/test_strategy_integration.py
   ```

3. Clean up when done:
   ```bash
   rm src/strategies/custom_test_metric.py
   ```

---

## Troubleshooting

| Symptom | Likely Cause | Fix |
|---------|-------------|-----|
| `ModuleNotFoundError: No module named 'src'` | Running from wrong directory | Run from project root: `cd satellite-collision` |
| `ImportError: numpy` | Missing dependencies | `pip install -r requirements.txt` |
| Dashboard shows no data | API not running or CORS issue | Check Flask is running; inspect browser console |
| `OPENAI_API_KEY` error | AI analysis called without key | Set env var or skip AI features |
| Port already in use | Another process on 5000/8050 | Kill it: `lsof -ti:5000 | xargs kill` |

For more detail, see `docs/setup-and-testing.md`.

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
│   ├── content.md                    # Intuitive explanations
│   └── setup-and-testing.md          # Extended setup/troubleshooting notes
├── tests/
├── app.py                            # Production entry point (Render/Gunicorn)
└── requirements.txt
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

### Why Each Technology Was Chosen

| Layer | Technology | Why this and not something else |
|---|---|---|
| Numerics | **NumPy / SciPy** | Vectorized state-vector math (6 x 10,000+ state variables) needs BLAS/LAPACK-backed operations, not Python loops. `scipy.integrate` gives an adaptive RK45/RK78-style ODE solver for propagation; `scipy.optimize` (via `milp`/HiGHS) provides the CPU fallback for the network-flow/MILP path without requiring a GPU. |
| Graph analysis | **NetworkX** | Conjunctions are naturally a graph (satellites = nodes, risky pairs = edges). `min_cost_flow` gives a provably optimal fuel allocation for free instead of hand-rolling a flow solver. |
| GPU optimization | **NVIDIA CuOpt** | At 10k+ objects, MILP solve time on CPU (NetworkX/HiGHS) grows into minutes. CuOpt's GPU MILP/VRP solver targets sub-second solves at that scale. `cuopt_client.py` talks its documented wire format and transparently degrades to the local CPU solver when no GPU server is configured, so the repo runs standalone. |
| AI layer | **OpenAI API / NVIDIA NIM** | Both expose an OpenAI-compatible chat-completions interface, so `ai_analysis.py` can target either without a different client library. Function-calling support is what makes the natural-language `/api/plan` endpoint possible without a bespoke parser. |
| Web API | **Flask + Flask-CORS** | Lightweight enough to prototype REST endpoints and SSE streaming without an ASGI framework's overhead; CORS middleware is a one-line requirement for a browser dashboard hitting the API from a different origin/port during development. |
| Production serving | **Gunicorn** | Standard sync WSGI server for a Flask app; worker count is deliberately kept at 1 in this deployment because simulation state lives in-memory (see [Running the System](#running-the-system)). |
| Visualization | **Three.js** | WebGL-based 3D rendering in-browser with no plugin install, and it comfortably handles the 10k+ object constellation the dashboard needs to render at interactive frame rates. |
| Language runtime | **Python 3.8+** | Matches the minimum version needed for the typing features and NumPy/SciPy releases the project depends on; also the path of least friction for integrating with C/Fortran-backed scientific libraries if performance-critical sections ever need it. |

### Pinned Dependency Versions & Rationale

| Package | Version constraint | Why this floor |
|---|---|---|
| `numpy` | `>=1.24.0` | Performance improvements and better error handling in array operations used throughout state propagation. |
| `scipy` | `>=1.10.0` | Newer `scipy.integrate` IVP solver interface and improved `scipy.optimize` used for orbit propagation and the MILP fallback. |
| `matplotlib` | `>=3.7.0` | Better rendering/animation support for the generated trajectory and risk-timeline plots (not required for API-only deployments). |
| `networkx` | `>=3.0` | Performance and API cleanups in `min_cost_flow` and graph construction used by `risk_optimizer.py`. |
| `flask` | `>=3.0.0` | Current stable line with performance improvements; async-readiness for future SSE/streaming work. |
| `flask-cors` | `>=4.0.0` | CORS handling for browser requests from the dashboard during local development. |
| `openai` | `>=1.0.0` | Stable client API surface, including function-calling, used by `ai_analysis.py`. |
| `requests` | `>=2.31.0` | HTTP client for the CuOpt REST integration in `cuopt_client.py`. |
| `gunicorn` | `>=21.2.0` | Production WSGI server for the Render/Gunicorn deployment path. |

### Integration Points

**OpenAI / NVIDIA NIM (LLM analysis)**

```python
# ai_analysis.py talks to either backend through the same
# OpenAI-compatible client, selected by which API key is set.
import openai

openai.api_key = os.getenv("OPENAI_API_KEY") or os.getenv("NVIDIA_API_KEY")

response = openai.ChatCompletion.create(
    model="gpt-4",  # or nvidia/llama-3.3-nemotron-super-49b-v1 for NIM
    messages=[
        {"role": "system", "content": "You are an orbital mechanics expert..."},
        {"role": "user", "content": f"Analyze this conjunction: {conjunction_data}"}
    ]
)
```

**NVIDIA CuOpt (GPU MILP solver)**

```python
# cuopt_client.py — same problem_data structure whether it's sent to a
# self-hosted CuOpt GPU server or solved locally via scipy.optimize.milp
from src.cuopt_client import CuOptClient

client = CuOptClient(server_ip=os.getenv("CUOPT_SERVER_IP"))
solution = client.solve_vehicle_routing(
    conjunctions=flagged_pairs,
    fuel_budgets=satellite_fuel,
    time_windows=tca_times
)
```

### Optional / Future Dependencies

These aren't installed by default (not in `requirements.txt`) but are the next additions on the [roadmap](#innovation--roadmap):

| Package | Purpose |
|---|---|
| `nvidia-nim-client` | Vision-language model access for automatic analysis of generated plots (`orbits_3d.png`, `risk_timeline.png`) |
| `nvidia-nv-embed` | Embedding model for RAG retrieval over `docs/physics.md` / `docs/strategy.md` |
| `nemo-guardrails` | Safety/consistency validation layer for LLM output before it reaches an operator |
| `memory-profiler`, `py-spy` | Profiling tools for memory and CPU hotspots at 10k+ object scale |
| `mypy`, `types-requests` | Static type checking as the codebase's type-hint coverage grows |

### Deployment Profiles

| Profile | Scale | Command | Resources |
|---|---|---|---|
| Single-process (prototype) | <1,000 objects, 7-day horizon | `python -m src.simulation` | 1 CPU core, ~500 MB RAM |
| Multi-process (scaling) | 1,000-10,000 objects | `gunicorn -w 4 -b 0.0.0.0:8050 src.api:app` | 4 CPU cores, 2-4 GB RAM |
| GPU-accelerated (large scale) | 10,000+ objects, real-time | CuOpt server + Flask API | 1 NVIDIA GPU (T4/A100+), 8-16 GB VRAM, 1 CPU |

---

## Why This Matters

In 2009, there were about 1,000 active satellites. Today there are over 10,000. By 2030, there may be 100,000. SpaceX alone plans 42,000 Starlink satellites. Amazon's Kuiper will add thousands more.

Every one of these objects shares the same orbital highways. Every one of them creates conjunction events with every other. The N-squared scaling of the conjunction problem means that doubling the number of satellites quadruples the number of potential collisions.

The Iridium-Cosmos collision happened when there were fewer than 1,000 active satellites. Imagine that scenario playing out in a world with 100,000. A single catastrophic collision at 780 km could trigger a cascade that renders entire orbital shells unusable for decades.

We built this system because the alternative — waiting for the next Iridium-Cosmos and hoping it doesn't start a cascade — is not a strategy. It's a gamble with infrastructure that modern civilization depends on: GPS navigation, weather forecasting, communications, climate monitoring, disaster response.

Space is getting crowded. This system is designed to keep it usable.

---

## Why We Need AI

Physics alone tells you *what* is happening. It doesn't tell you *what to do about it*, and it definitely doesn't tell an operator, in the middle of the night, why a particular burn is the right call. That gap is where AI fits into this system — not as a replacement for the physics engine, but as a layer on top of it.

### The numbers alone don't scale to human decision-making

The optimizer can produce four candidate plans, each with a residual risk, a fuel cost, and a list of resolved conjunctions. That's a lot to absorb in real time when someone has 18 hours to act on a critical conjunction. The AI analysis layer (`ai_analysis.py`) translates the optimizer's raw output into something an operator can act on immediately: *"Satellite COMSAT-7 should execute a 2.3 m/s cross-track burn at T-45 minutes. This resolves 3 conjunctions simultaneously and uses 4% of remaining fuel budget."* That's the difference between staring at a JSON blob of four candidates and understanding, in one sentence, what to do and why.

### Why AI is layered on top, not baked into the physics

This is a deliberate architectural choice, not a limitation:

- **The LLM never computes physics or probability.** All Pc calculations, STM propagation, and MILP/greedy/MCTS optimization happen in deterministic, auditable Python before the AI layer ever sees the results. The AI explains and queries; it doesn't decide the numbers.
- **Auditability matters when fuel is irreplaceable.** A hallucinated delta-v recommendation could cost a satellite its remaining maneuvering life. Keeping the LLM downstream of the physics engine means every recommendation it explains traces back to a verifiable calculation, not a guess.
- **This keeps the door open for autonomy later.** The roadmap's Tier 4 (autonomous execution) depends on this separation: a policy can eventually act on the optimizer's output directly, with the AI layer serving as the explanation and audit trail rather than the decision-maker itself.

### Where AI genuinely earns its place

| Problem | Why physics/optimization alone isn't enough | What AI adds |
|---|---|---|
| Comparing 4 optimization strategies | Numbers don't explain *why* one is better for this situation | Plain-language justification tied to the actual tradeoffs (fuel, risk reduction, conjunctions resolved) |
| 3 AM operator decisions | Reading covariance ellipsoids and Pc thresholds takes training most on-call staff don't have | Translates thresholds and STM output into a recommended action in one or two sentences |
| Ad-hoc "what if" questions | Would otherwise require writing custom queries against the API for every scenario | Natural language planning via `/api/plan`, grounded in the same optimizer used everywhere else |
| Cascade risk communication | A single number (risk score) hides *why* a conjunction is dangerous (mass, relative velocity, debris potential) | Surfaces the reasoning behind the score, not just the score itself |

In short: the orbital mechanics and optimization code answer "is there a threat, and what's the best fuel-efficient response." The AI layer answers "how do I get a human to understand and trust that answer fast enough to act on it." Both are necessary — this system exists because the Iridium-Cosmos collision proved that having the data isn't the same as acting on it in time, and clear, fast communication of a correct decision is as important as the decision itself.

---

## Innovation & Roadmap

### What's Novel Here

- **Four optimization strategies compared side-by-side, not just one.** Most collision-avoidance tooling picks a single heuristic. This system runs Greedy, Network Flow (MILP), MCTS, and GPU-accelerated CuOpt in parallel and lets an adaptive selector pick the best fit for the situation (see [Step 5](#step-5-the-hardest-part--deciding-what-to-do)).
- **Cascade-aware risk scoring.** Risk isn't just Pc — it factors in expected debris generation and secondary conjunction probability, directly modeling the Kessler Syndrome mechanism rather than treating each conjunction in isolation.
- **AI decision support grounded in the physics engine, not replacing it.** The LLM layer explains and queries the optimizer's output in natural language; it never computes physics or probability itself, keeping numerical results auditable.
- **Pluggable custom risk strategies.** Dropping a file into `src/strategies/` following the naming convention gets it auto-validated and registered (see `strategy_integrator.py`) — no core code changes required to experiment with new heuristics.

### Roadmap (Near-Term to Long-Term)

| Tier | Focus | Status |
|---|---|---|
| GPU-scale optimization | NVIDIA CuOpt MILP solver for 10k+ object constellations | Integrated |
| LLM-powered analysis | Natural language planning queries, operator-friendly insights | Integrated |
| Safety & validation | NeMo Guardrails for LLM output validation, audit trail | Proposed |
| Scaling to 100k objects | Parallel screening, Cython/Numba JIT, memory optimization | Proposed |
| RAG over documentation | Semantic search grounding LLM answers in `docs/physics.md` / `docs/strategy.md` | Proposed |
| Vision-language plot analysis | Automatic insight generation from generated risk/orbit plots | Proposed |
| Real-time TLE / Space Force feed | Replace simulated constellation with live tracking data | Proposed |
| Autonomous execution | RL-trained policy with confidence-gated auto-maneuvering, human override always available | Long-term |

### Known Limitations (Honest Accounting)

- J2/J3 oblateness only — no 3rd-body (Sun/Moon) perturbations, so accuracy degrades outside LEO.
- Atmospheric drag uses a simplified exponential density model, not NRLMSISE-00.
- Planning horizon is practically capped at ~7 days; uncertainty dominates beyond that.
- Debris cascade modeling is probabilistic and model-averaged, not per-fragment tracked.

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
