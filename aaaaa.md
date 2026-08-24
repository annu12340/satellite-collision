# 🛰️ AI Satellite Collision Prevention System

### Autonomous collision avoidance for an increasingly crowded orbit.

**What happens when thousands of satellites share the same orbital highways, every trajectory is uncertain, and every maneuver consumes irreplaceable fuel?**

You don't solve that problem with a single collision warning.

You solve it with a system that can **predict, assess, optimize, explain, and continuously re-evaluate risk** across an entire constellation.

This project is an end-to-end satellite collision prevention platform combining **orbital mechanics, probabilistic conjunction assessment, multi-strategy optimization, debris cascade modeling, GPU acceleration, and AI decision support** into one real-time system.

> **Physics determines what is happening. Optimization determines what to do. AI explains why.**

---

## 🚀 See It In Action

| | |
|---|---|
| 🎥 **Video walkthrough** | https://www.youtube.com/watch?v=03x7psL5sz8 |
| 🌐 **Live dashboard** | https://satellite-collision-1.onrender.com/ |
| 📚 **Interactive documentation** | https://satellite-collision-1.onrender.com/docs |

The dashboard provides:

- Real-time 3D orbital visualization
- Conjunction and collision-risk monitoring
- B-plane encounter geometry
- Risk evolution over time
- Maneuver recommendations
- Debris breakup analysis
- Optimization strategy comparison
- Live simulation streaming through SSE

---

# 🌍 Why This Problem Matters

On **February 10, 2009**, Iridium 33 collided with the defunct Cosmos 2251 at approximately **11.7 km/s** above Siberia.

Two spacecraft became more than **2,000 trackable debris fragments**.

That event demonstrated something the space industry had feared for decades:

## The Kessler Syndrome

```text
        Collision
            │
            ▼
      New debris
            │
            ▼
   More conjunctions
            │
            ▼
   More collisions
            │
            ▼
    More debris
            │
            ▼
   Orbital cascade
```

As orbital populations grow, the problem gets harder—not linearly, but **quadratically**.

For 10,000 tracked objects:

**N × (N − 1) / 2 ≈ 50 million potential pairs**

And a satellite cannot simply maneuver every time something looks dangerous.

A typical spacecraft may have only around **25 m/s of total delta-v available across its operational lifetime**.

Every avoidance maneuver spends part of that finite budget.

So the real question isn't:

> *"Is there a collision?"*

It's:

> **"Given uncertainty, limited fuel, multiple simultaneous threats, and future consequences, what is the best intervention?"**

That's the problem this system attacks.

---

# 🧠 What the System Does

The platform turns a large, uncertain orbital environment into an actionable decision loop:

```text
 ┌───────────────────────────────────────┐
 │         ORBITAL ENVIRONMENT           │
 │                                       │
 │  Thousands of objects                 │
 │  Uncertain trajectories                │
 │  Multiple conjunctions                 │
 │  Limited maneuvering fuel             │
 └───────────────────┬───────────────────┘
                     │
                     ▼
 ┌───────────────────────────────────────┐
 │          COLLISION ENGINE             │
 │                                       │
 │  Propagate → Screen → Assess          │
 │       → Optimize → Mitigate           │
 └───────────────────┬───────────────────┘
                     │
                     ▼
 ┌───────────────────────────────────────┐
 │             DECISION                  │
 │                                       │
 │  Which satellite?                     │
 │  What maneuver?                       │
 │  When?                                │
 │  How much delta-v?                    │
 │  What happens next?                   │
 └───────────────────┬───────────────────┘
                     │
                     ▼
 ┌───────────────────────────────────────┐
 │             OPERATOR                  │
 │                                       │
 │  Risk reduction                       │
 │  Fuel cost                            │
 │  Resolved conjunctions                │
 │  Human-readable explanation           │
 └───────────────────────────────────────┘
```

## Current Capabilities

| Capability | Implementation | Status |
|---|---|---|
| Orbit propagation | 6-DOF + J2 + drag + SRP | ✅ Complete |
| Uncertainty propagation | 6×6 covariance + STM | ✅ Complete |
| Conjunction screening | Multi-stage geometric filtering | ✅ Complete |
| Collision probability | Foster / Chan / 2D Gaussian | ✅ Complete |
| TCA prediction | Time-of-closest-approach calculation | ✅ Complete |
| Avoidance planning | STM-based delta-v optimization | ✅ Complete |
| Multi-conjunction planning | Global maneuver sequencing | ✅ Complete |
| Risk optimization | Greedy + MILP + MCTS | ✅ Complete |
| GPU optimization | NVIDIA CuOpt integration | ✅ Integrated |
| Damage minimization | NASA Standard Breakup Model | ✅ Complete |
| Cascade analysis | Secondary conjunction risk | ✅ Complete |
| AI decision support | LLM-powered analysis and planning | ✅ Complete |
| Visualization | Three.js + real-time SSE | ✅ Complete |

---

# ⚙️ How It Works

The system operates as a continuous decision pipeline:

```text
1. GENERATE
      │
      ▼
2. PROPAGATE
      │
      ▼
3. SCREEN
      │
      ▼
4. ASSESS
      │
      ▼
5. OPTIMIZE
      │
      ▼
6. EXECUTE / MITIGATE
      │
      ▼
7. ANALYZE
      │
      ▼
8. PUBLISH
      │
      └──────────────► Repeat
```

## 1. Generate the Orbital Environment

Each spacecraft is represented with:

- Position and velocity
- Mass
- Cross-sectional area
- Fuel budget
- Maneuverability
- Orbital state
- 6×6 covariance matrix

The covariance matrix matters because the system never assumes that an object's position is known exactly.

---

## 2. Propagate the Future

The physics engine propagates spacecraft states forward using:

- Keplerian gravity
- Earth's J2 oblateness
- Atmospheric drag
- Solar radiation pressure

The system also propagates uncertainty using the **State Transition Matrix (STM)**.

```text
X(t₀), P(t₀)
      │
      ▼
   RK7(8)
      │
      ▼
X(t), P(t)
```

The covariance evolves approximately as:

```text
P(t) = Φ(t,t₀) P(t₀) Φ(t,t₀)ᵀ + Q(t)
```

The result is that the system tracks not only:

> **Where is the satellite?**

but also:

> **How confident are we that it is there?**

---

## 3. Screen Millions of Potential Pairs

With 10,000 objects, approximately 50 million pairs are possible.

Running an expensive probability-of-collision calculation on every pair would be wasteful.

Instead, the system uses progressively more expensive filters:

```text
50,000,000 possible pairs
          │
          ▼
Altitude / Apogee / Perigee filter
          │
          ▼
Orbital-plane filter
          │
          ▼
Minimum-distance filter
          │
          ▼
Candidate conjunctions
          │
          ▼
Detailed assessment
```

This reduces the search space before expensive probability calculations are performed.

---

# 🎯 4. Calculate Collision Probability

For each surviving conjunction, the system evaluates:

- Miss distance
- Relative velocity
- Combined covariance
- Hard-body radius
- Time of closest approach
- Encounter-plane geometry

Multiple probability-of-collision approaches are implemented.

### Foster

Numerical integration using the projected covariance ellipse.

### Chan

A fast series-based approximation.

### 2D Gaussian

An analytic encounter-plane reference implementation.

The resulting probability is combined with consequence and cascade information:

```text
Risk =
    Probability of Collision
    × Consequence
    × Cascade Multiplier
```

This matters because two conjunctions with identical `Pc` values can have dramatically different consequences.

---

# 🧮 5. Find the Best Maneuver

This is where the problem becomes an optimization problem.

Imagine:

- 12 active conjunctions
- 35 maneuverable satellites
- Limited fuel
- Multiple possible burns
- Maneuvers that can create new future conjunctions

A locally optimal maneuver may make the global situation worse.

The system therefore evaluates multiple strategies.

## Greedy

Fast and simple:

```text
Rank threats
    ↓
Resolve highest-risk threat
    ↓
Re-screen
    ↓
Resolve next threat
    ↓
Repeat
```

Useful when decisions must be made extremely quickly.

## Network Flow / MILP

Models satellites, conjunctions, and fuel constraints as an optimization problem.

Useful when fuel allocation matters and the problem is small enough for an exact or high-quality solve.

## Monte Carlo Tree Search

Looks beyond the immediate maneuver:

```text
Current state
      │
 ┌────┼────┐
 ▼    ▼    ▼
Burn A Burn B Burn C
 │      │      │
 ▼      ▼      ▼
Future Future Future
state   state   state
```

This allows the system to evaluate whether today's maneuver creates tomorrow's problem.

## NVIDIA CuOpt

For larger optimization problems, the same optimization formulation can be sent to a self-hosted NVIDIA CuOpt server.

Without a GPU server configured, the project falls back to the local CPU optimization path.

**GPU acceleration is optional. Reproducibility is not.**

---

# 🧩 Adaptive Strategy Selection

The system does not blindly use one optimizer.

It compares available approaches and selects an appropriate strategy based on the problem:

```text
              Conjunctions
                   │
          ┌────────┴────────┐
          │                 │
        Small             Large
          │                 │
          ▼                 ▼
   Network Flow            MCTS
          │                 │
          └────────┬────────┘
                   │
                   ▼
          CuOpt available?
              │       │
             YES      NO
              │       │
              ▼       ▼
            CuOpt   Greedy
```

The selected result is compared against alternative strategies and checked against fuel constraints.

---

# 💥 6. What If You Can't Avoid the Collision?

Not every object can maneuver.

A dead satellite has no thrusters.

A warning may arrive too late.

A spacecraft may not have enough fuel.

When avoidance is impossible, the system switches from **collision avoidance** to **damage minimization**.

Using the NASA Standard Breakup Model, it evaluates potential consequences of an impact and attempts to reduce resulting damage through factors such as:

- Impact geometry
- Cross-sectional area
- Relative velocity
- Debris distribution
- Orbital decay characteristics
- Secondary conjunction risk

The objective changes from:

> **"Prevent the collision."**

to:

> **"If the collision cannot be prevented, minimize what happens next."**

---

# 🤖 7. Why AI?

The AI layer is deliberately **not** responsible for orbital physics.

That's an architectural decision.

The deterministic system computes:

- Orbital states
- Covariances
- Collision probabilities
- Risk scores
- Fuel consumption
- Maneuver candidates
- Optimization results

The AI layer explains those results.

```text
             PHYSICS
                │
                ▼
        CONJUNCTION ASSESSMENT
                │
                ▼
           OPTIMIZATION
                │
                ▼
        ┌───────────────┐
        │   AI LAYER    │
        │               │
        │ Explain       │
        │ Compare       │
        │ Query         │
        │ Summarize     │
        └───────┬───────┘
                │
                ▼
            OPERATOR
```

Instead of forcing an operator to interpret raw optimizer output, the AI layer translates the results into concise, actionable explanations.

For example:

> **Network Flow is recommended because it resolves three critical conjunctions while using less fuel than the alternative strategies.**

The LLM explains the calculation.

**It does not invent the calculation.**

### Why this separation matters

- **The physics remains deterministic and auditable.**
- **Collision probability is never generated by the LLM.**
- **Optimization results can be traced back to numerical calculations.**
- **The AI layer can be replaced without changing the physics engine.**
- **Future autonomous execution can act directly on validated optimizer outputs.**

---

# 🖥️ Real-Time Dashboard

The frontend provides an operational view of the simulation:

- 3D orbital environment
- Spacecraft trajectories
- Conjunction markers
- B-plane encounter geometry
- Risk timelines
- Risk evolution
- Maneuver visualization
- Debris breakup scenarios
- Strategy comparison
- Live simulation events

Real-time simulation events are streamed through **Server-Sent Events (SSE)**.

```text
Simulation
    │
    ▼
Flask API
    │
    │ SSE
    ▼
Browser
    │
    ▼
Three.js visualization
```

---

# 🏗️ Architecture

The project separates physics, decision-making, orchestration, and presentation.

```text
┌──────────────────────────────────────────────┐
│                PRESENTATION                  │
│                                              │
│ Dashboard │ Three.js │ Maneuver Viz │ Docs  │
└──────────────────────┬───────────────────────┘
                       │
                 REST / SSE
                       │
┌──────────────────────▼───────────────────────┐
│                    API                       │
│                   Flask                      │
└──────────────────────┬───────────────────────┘
                       │
┌──────────────────────▼───────────────────────┐
│               ORCHESTRATION                 │
│                                              │
│ simulation │ risk optimizer │ AI │ CuOpt    │
└──────────────────────┬───────────────────────┘
                       │
┌──────────────────────▼───────────────────────┐
│                 DECISION                    │
│                                              │
│ conjunction │ avoidance │ damage minimizer  │
└──────────────────────┬───────────────────────┘
                       │
┌──────────────────────▼───────────────────────┐
│                  PHYSICS                    │
│                                              │
│ Orbit propagation │ STM │ covariance │ J2  │
│ drag │ SRP │ numerical integration          │
└──────────────────────────────────────────────┘
```

---

# 🧰 Technology Stack

| Layer | Technology |
|---|---|
| Language | Python 3.8+ |
| Numerical computing | NumPy, SciPy |
| Optimization | SciPy/HiGHS, NetworkX, MCTS |
| GPU optimization | NVIDIA CuOpt |
| AI | OpenAI API / NVIDIA NIM |
| Backend | Flask + Flask-CORS |
| Production | Gunicorn |
| Visualization | Three.js |
| Streaming | Server-Sent Events |

### Why These Technologies?

| Layer | Technology | Why |
|---|---|---|
| Numerics | NumPy / SciPy | Vectorized state-vector math and scientific integration |
| Graph analysis | NetworkX | Natural representation of satellites and conjunctions as graphs |
| GPU optimization | NVIDIA CuOpt | GPU-accelerated optimization for large-scale problems |
| AI | OpenAI API / NVIDIA NIM | OpenAI-compatible interface for analysis and planning |
| Web API | Flask | Lightweight REST API and SSE streaming |
| Production | Gunicorn | Production WSGI serving for Flask |
| Visualization | Three.js | Interactive browser-based 3D rendering |
| Runtime | Python 3.8+ | Scientific ecosystem and numerical computing support |

---

# 🔌 API Reference

| Method | Endpoint | Purpose |
|---|---|---|
| `GET` | `/api/spacecraft` | Spacecraft and orbital data |
| `GET` | `/api/conjunctions` | Active conjunctions |
| `GET` | `/api/maneuvers` | Planned maneuvers |
| `GET` | `/api/risk` | Global risk metrics |
| `GET` | `/api/risk-graph` | Satellite/conjunction graph |
| `GET` | `/api/shells` | Orbital altitude shells |
| `GET` | `/api/debris` | Debris prediction data |
| `GET` | `/api/timeline` | 24-hour risk evolution |
| `GET` | `/api/risk-evolution` | Long-term risk projection |
| `GET` | `/api/debris-analysis` | Breakup analysis |
| `GET` | `/api/decision-engine` | Strategy comparison |
| `GET` | `/api/scenarios` | Available scenarios |
| `GET` | `/api/scenario/:id` | Scenario data |
| `GET` | `/api/scenario/:id/stream` | Live SSE stream |
| `POST` | `/api/run` | Re-run simulation |
| `POST` | `/api/plan` | Natural-language planning |

Example:

```bash
curl -X POST http://localhost:8050/api/plan \
  -H "Content-Type: application/json" \
  -d '{"query":"What is the minimum-fuel plan to resolve critical conjunctions?"}'
```

---

# ⚡ Quick Start

```bash
git clone <repository-url>
cd satellite-collision

python3 -m venv venv
source venv/bin/activate

pip install -r requirements.txt

python -m src.simulation
```

Then open:

```text
http://localhost:8050
```

## Optional AI Features

```bash
export OPENAI_API_KEY="your-key"
export NVIDIA_API_KEY="your-key"
```

## Optional GPU Acceleration

```bash
export CUOPT_SERVER_IP="your-cuopt-server"
export CUOPT_SERVER_PORT="5000"
```

If `CUOPT_SERVER_IP` is not configured, the system uses the local CPU optimization path.

---

# 🧪 Testing

Run the strategy integration suite:

```bash
python3 tests/test_strategy_integration.py
```

The suite validates:

- Strategy file parsing
- Filename validation
- Function validation
- Parameter validation
- Return types
- Strategy execution
- Duplicate registration
- Runtime error handling
- Custom strategy integration

---

# 📁 Project Structure

```text
satellite-collision/
│
├── src/
│   ├── orbital_mechanics.py
│   ├── conjunction.py
│   ├── avoidance.py
│   ├── damage_minimization.py
│   ├── risk_optimizer.py
│   ├── ai_analysis.py
│   ├── simulation.py
│   ├── api.py
│   ├── cuopt_client.py
│   ├── strategy_integrator.py
│   ├── utils.py
│   └── strategies/
│
├── dashboard/
│   ├── index.html
│   ├── viz.html
│   ├── maneuver-viz.html
│   ├── science.html
│   ├── architecture.html
│   ├── docs.html
│   ├── landing.html
│   ├── app.js
│   └── style.css
│
├── docs/
│   ├── physics.md
│   ├── strategy.md
│   ├── content.md
│   └── setup-and-testing.md
│
├── tests/
├── app.py
└── requirements.txt
```

---

# 📈 Scaling

The computational challenge grows rapidly with constellation size.

| Profile | Scale | Deployment |
|---|---:|---|
| Prototype | < 1,000 objects | Single-process Python |
| Scaling | 1,000–10,000 objects | Multi-process / optimized CPU |
| Large-scale | 10,000+ objects | GPU-accelerated CuOpt |
| Future | 100,000+ objects | Parallel screening + GPU/distributed pipeline |

The architecture is designed so expensive optimization can move from local CPU computation to a GPU-backed CuOpt server without changing the surrounding decision pipeline.

---

# 🧠 How Kiro Was Used

The project was developed using **Kiro**, with specifications, steering documents, and hooks integrated into the engineering workflow.

### Specs

The `.kiro/specs/` directory captures requirements, designs, and implementation tasks for major features including:

- Orbital mechanics
- Conjunction assessment
- Avoidance maneuver planning
- Simulation orchestration
- CuOpt intervention planning
- B-plane visualization
- Risk visualization
- 3D TCA visualization

### Steering

Project-wide steering documents provide persistent context for:

- Architecture
- Data structures
- Roadmap
- Physics conventions
- Development practices
- Module dependencies

### Hooks

Automated hooks help enforce engineering consistency around:

- Linting
- Formatting
- Dependency validation
- Physics safety checks
- Post-task validation
- Custom-strategy registration
- Human-approved Git commits

The goal was to use Kiro not simply to generate code, but to maintain coherence across a complex multi-module system.

> **Kiro accelerates implementation without turning the physics engine into an opaque black box.**

---

# 🧪 What Makes This Different?

## 1. Multiple optimization strategies

Rather than relying on a single heuristic, the system compares:

**Greedy → MILP → MCTS → CuOpt**

and selects an appropriate strategy for the current problem.

## 2. Cascade-aware risk

The system doesn't stop at:

> "What's the probability these two objects collide?"

It also considers:

> **"What happens to the orbital environment if they do?"**

## 3. Physics-first AI

The LLM does not calculate orbital mechanics or collision probabilities.

It operates downstream of deterministic calculations and explains their results.

## 4. Future-aware planning

MCTS and global optimization allow the system to consider the consequences of today's maneuver rather than optimizing only for the next conjunction.

## 5. Pluggable strategies

Custom strategies can be added under:

```text
src/strategies/
```

and integrated through the strategy validation and registration pipeline.

---

# 🛣️ Roadmap

| Capability | Status |
|---|---|
| Orbital mechanics engine | ✅ Integrated |
| Conjunction assessment | ✅ Integrated |
| Multi-strategy optimization | ✅ Integrated |
| NASA breakup modeling | ✅ Integrated |
| AI decision support | ✅ Integrated |
| NVIDIA CuOpt integration | ✅ Integrated |
| LLM safety / validation | 🔬 Proposed |
| Scaling toward 100k objects | 🔬 Proposed |
| RAG over physics documentation | 🔬 Proposed |
| Vision-language plot analysis | 🔬 Proposed |
| Live tracking / TLE feeds | 🔬 Proposed |
| Autonomous maneuver execution | 🔭 Long-term |

---

# ⚠️ Known Limitations

This is a research and engineering prototype, not a flight-certified collision avoidance system.

Current limitations include:

- J2/J3 oblateness modeling rather than a complete high-fidelity perturbation model
- Simplified atmospheric drag model
- No full Sun/Moon third-body perturbation model
- Planning horizon is practically limited to roughly seven days
- Debris cascades are probabilistically modeled rather than individually propagated
- GPU acceleration requires a compatible CuOpt deployment
- Live operational tracking feeds are not yet integrated

---

# 🌌 The Bigger Picture

The orbital environment is changing faster than the systems used to manage it.

More satellites means:

**More conjunctions.**

More conjunctions mean:

**More decisions.**

More decisions mean:

**More opportunities for human latency, inconsistent judgment, and wasted fuel.**

The goal of this project is not simply to predict collisions.

It is to build the computational infrastructure required to make **safe, explainable, fuel-efficient decisions at orbital scale**.

Because the next major space-safety problem may not be a lack of data.

It may be the inability to turn that data into the right decision quickly enough.

---

# 🛰️ Built for a Crowded Orbit

**Physics tells us what is happening.**

**Optimization tells us what to do.**

**AI tells us why.**

Together, they turn orbital collision avoidance from a reactive warning system into a **continuous decision engine**.

> **The objective isn't just to avoid the next collision.**
>
> **It's to keep orbit usable.**
