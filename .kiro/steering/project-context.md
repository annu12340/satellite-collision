# Satellite Collision Prevention System - Project Context

## Project Overview

This is an AI-powered physics simulation and optimization system for preventing orbital collisions among thousands of spacecraft. The system balances collision risk mitigation with damage minimization when collisions are unavoidable.

**Core Problem:** Given thousands of interacting spacecraft with uncertain trajectories and limited delta-v budgets, find the optimal sequence of interventions that minimizes long-term orbital risk (collision probability × debris generation potential) across the entire constellation.

## Mission Statement

Enable autonomous decision-making in orbital collision prevention by combining:
- **Physics accuracy** in orbit propagation and conjunction assessment
- **Real-time optimization** to find fuel-efficient intervention sequences
- **Risk awareness** of cascading debris effects (Kessler syndrome)
- **AI guidance** for operators on maneuver recommendations and contingency planning

## Architecture & Module Map

### System Architecture Layers

```
┌─────────────────────────────────────────────────────────────┐
│  PRESENTATION LAYER (Dashboard)                             │
│  ├─ index.html (Main UI)  ├─ viz.html (3D orbits)          │
│  ├─ app.js (Frontend logic) └─ docs.html (Reference)        │
└────────────────────┬────────────────────────────────────────┘
                     │ HTTP/WebSocket
┌─────────────────────────────────────────────────────────────┐
│  API LAYER (Flask)                                          │
│  ├─ /api/risk          (Risk scores & metrics)              │
│  ├─ /api/conjunctions  (Conjunction predictions)            │
│  ├─ /api/shells        (Orbital shell analysis)             │
│  ├─ /api/maneuvers     (Planned interventions)              │
│  └─ /api/debris        (Debris projections)                 │
└────────────────────┬────────────────────────────────────────┘
                     │ Python function calls
┌─────────────────────────────────────────────────────────────┐
│  ORCHESTRATION LAYER                                        │
│  ├─ simulation.py      (Main event loop & sequencing)       │
│  ├─ risk_optimizer.py  (Multi-conjunction optimization)     │
│  ├─ ai_analysis.py     (LLM-powered insights)               │
│  └─ cuopt_client.py    (Optimization solver interface)      │
└────────────────────┬────────────────────────────────────────┘
                     │ Physics models & optimization
┌─────────────────────────────────────────────────────────────┐
│  DECISION LAYER (Strategy)                                  │
│  ├─ conjunction.py            (Probability assessment)      │
│  ├─ avoidance.py              (Maneuver planning)          │
│  └─ damage_minimization.py    (Mitigation strategies)       │
└────────────────────┬────────────────────────────────────────┘
                     │ Orbital propagation & state
┌─────────────────────────────────────────────────────────────┐
│  PHYSICS LAYER (Core Simulation)                            │
│  ├─ orbital_mechanics.py   (State propagation, STM)         │
│  └─ utils.py               (Constants, transforms)          │
└─────────────────────────────────────────────────────────────┘
```

### Module Breakdown

```
src/
├── __main__.py                  # Entry point, bootstraps simulation
├── api.py                       # Flask API server (5 core endpoints)
├── ai_analysis.py               # LLM-driven analysis & recommendations
├── orbital_mechanics.py          # Core propagation, STM, perturbations
├── conjunction.py               # Conjunction screening & Pc calculation
├── avoidance.py                 # Maneuver planning & delta-v optimization
├── damage_minimization.py        # Debris impact & cascade modeling
├── risk_optimizer.py            # Global optimization (greedy, network-flow, MCTS)
├── simulation.py                # Main simulation loop & event handler
├── cuopt_client.py              # NVIDIA CuOpt solver interface
└── utils.py                     # Constants, rotations, coordinate transforms

dashboard/
├── index.html                   # Main dashboard (risk overview, actions)
├── viz.html                     # 3D WebGL orbital visualization
├── docs.html                    # Interactive physics reference viewer
├── app.js                       # Frontend logic (fetch, rendering)
├── style.css                    # Responsive styling
└── landing.html / landing copy.html  # (Promotional pages)

docs/
├── physics.md                   # Complete orbital mechanics reference
└── strategy.md                  # Decision framework & algorithms
```

### Data Flow Diagram

```
┌─────────────────────────────────────────────────────────────┐
│  Input: Spacecraft TLEs + Covariance Matrices               │
└──────────────────────────┬──────────────────────────────────┘
                           │
        ┌──────────────────┴──────────────────┐
        │                                     │
┌───────▼─────────────────┐      ┌───────────▼────────┐
│  Orbit Propagation      │      │  Covariance        │
│  (orbital_mechanics)    │      │  Propagation (STM) │
└───────┬─────────────────┘      └───────────┬────────┘
        │                                     │
        └──────────────────┬──────────────────┘
                           │
        ┌──────────────────▼──────────────────┐
        │  Conjunction Screening (all-vs-all) │
        │  Filter by: apogee/perigee, plane   │
        └──────────────────┬──────────────────┘
                           │
        ┌──────────────────▼──────────────────┐
        │  TCA & Probability Calculation      │
        │  (conjunction.py: covariance method)│
        └──────────────────┬──────────────────┘
                           │
        ┌──────────────────▼──────────────────┐
        │  Risk Scoring (Pc × Consequence     │
        │              × Cascade Factor)      │
        └──────────────────┬──────────────────┘
                           │
        ┌──────────────────▼──────────────────┐
        │  Multi-Conjunction Optimization     │
        │  - Greedy                           │
        │  - Network Flow (NetworkX)          │
        │  - MCTS                             │
        │  - CuOpt (GPU LP/MILP)             │
        └──────────────────┬──────────────────┘
                           │
        ┌──────────────────▼──────────────────┐
        │  Maneuver Planning (avoidance.py)   │
        │  STM × Δv direction optimization    │
        └──────────────────┬──────────────────┘
                           │
        ┌──────────────────▼──────────────────┐
        │  Damage Modeling (unavoidable case) │
        │  Debris generation & reentry time   │
        └──────────────────┬──────────────────┘
                           │
        ┌──────────────────▼──────────────────┐
        │  AI Analysis (ai_analysis.py)       │
        │  LLM insights & recommendations     │
        └──────────────────┬──────────────────┘
                           │
        ┌──────────────────▼──────────────────┐
        │  Output: Actions + Visualizations   │
        │  ├─ Maneuver commands (Δv, timing) │
        │  ├─ Risk metrics & projections      │
        │  └─ Debris tracking (future refs)   │
        └─────────────────────────────────────┘
```

### Key Data Structures

**Spacecraft State**
```python
{
    'id': int,
    'name': str,
    'state': np.ndarray([x, y, z, vx, vy, vz]),  # ECI, meters
    'covariance': np.ndarray(6x6),               # ECI uncertainty
    'mass': float,  # kg
    'radius': float,  # meters (hard-body)
    'fuel_budget': float,  # m/s delta-v remaining
    'maneuverable': bool,  # can execute burns
}
```

**Conjunction Event**
```python
{
    'sat1_id': int,
    'sat2_id': int,
    'time_to_closest_approach': float,  # seconds
    'miss_distance': float,  # meters
    'relative_velocity': float,  # m/s
    'probability_of_collision': float,  # 0-1
    'risk_score': float,  # composite metric
    'debris_potential': float,  # expected fragments > 10cm
}
```

**Maneuver Plan**
```python
{
    'satellite_id': int,
    'delta_v': float,  # magnitude (m/s)
    'direction': np.ndarray([x, y, z]),  # unit vector
    'execution_time': float,  # epoch (seconds)
    'expected_miss_improvement': float,  # meters gained
    'fuel_cost': float,  # m/s consumed
    'conjunction_ids_resolved': list[int],
}
```

## Technology Stack

### Core Scientific Computing
- **NumPy** (>=1.24.0) — Vectorized orbital mechanics calculations, matrix operations
- **SciPy** (>=1.10.0) — Numerical integration (orbit propagation), optimization algorithms, linear algebra
- **Matplotlib** (>=3.7.0) — 2D analysis plots, trajectory visualization

### Web & API Layer
- **Flask** (>=3.0.0) — REST API server for dashboard integration
- **Flask-CORS** (>=4.0.0) — Cross-origin resource sharing for browser dashboard
- **Requests** (>=2.31.0) — HTTP client for external APIs (OpenAI, CuOpt)

### Advanced Analytics & Optimization
- **NetworkX** (>=3.0) — Graph-based risk network analysis, conjunction dependency modeling
- **OpenAI API** (>=1.0.0) — AI-powered analysis and recommendation generation

### Frontend Visualization (Dashboard)
- **Three.js** — 3D orbital visualization in browser (WebGL)
- **HTML5/CSS3** — Responsive dashboard UI
- **JavaScript** — Interactive controls and real-time updates

### Optimization Backends (Integrated)
- **NVIDIA CuOpt** — GPU-accelerated vehicle routing problem solver (via cuopt_client.py) for large-scale maneuver sequencing
- **Custom Python** — Monte Carlo Tree Search (MCTS), network flow algorithms for medium-scale problems

### Key Dependencies & Versions
```
numpy>=1.24.0           # N-dimensional arrays, linear algebra
scipy>=1.10.0           # Scientific computing (ODE solvers, optimizers)
matplotlib>=3.7.0       # Plotting and visualization
networkx>=3.0           # Graph algorithms for risk networks
flask>=3.0.0            # Web framework for API
flask-cors>=4.0.0       # CORS middleware
openai>=1.0.0           # LLM integration for analysis
requests>=2.31.0        # HTTP requests for APIs
```

### Optional/Future Components
- **NVIDIA Nemotron** — Tool-calling LLM for agentic decision support
- **NV-Embed** — Embedding model for RAG over physics docs
- **NeMo Guardrails** — Safety constraints for LLM outputs



## Development Workflow

### System Execution Flow

The simulation runs as a continuous decision loop:

```
EPOCH 0 (Initial State)
├─ Load spacecraft TLEs & covariance
├─ Propagate to planning horizon
└─ Enter main loop

MAIN LOOP (repeats every time step)
├─ Propagate all spacecraft + covariance (orbital_mechanics)
├─ Screen all pairs for close approaches (conjunction)
├─ For flagged pairs: compute Pc (conjunction.py)
├─ Build risk network (NetworkX)
├─ Run global optimizer on current state (risk_optimizer)
│  ├─ Greedy: highest-risk first
│  ├─ Network flow: global fuel-optimal solution
│  └─ MCTS: explore maneuver sequences
├─ For each maneuver decision:
│  ├─ If Pc avoidable: plan maneuver (avoidance.py)
│  └─ If unavoidable: evaluate damage strategies (damage_minimization.py)
├─ Generate AI analysis for operators (ai_analysis.py)
├─ Publish API updates (api.py → dashboard)
├─ Render visualizations (matplotlib + Three.js)
└─ Advance time, repeat
```

### Running the System

```bash
# Install dependencies
pip install -r requirements.txt

# Run the simulation and start dashboard API (port 5000)
python -m src.simulation

# Dashboard opens at http://localhost:5000
```

### Key Entry Points

- **Main Simulation:** `python -m src.simulation` or `src/__main__.py`
- **API Server:** `src/api.py` (automatically started by simulation)
- **Dashboard:** Open `dashboard/index.html` in browser after API is running
- **Visualization Server:** Three.js renders in `dashboard/viz.html`

### Decision Points During Execution

At each time step, the system makes decisions through this hierarchy:

```
1. DETECT RISK
   └─ Any Pc > 1e-7? (essentially zero risk)
   
2. ASSESS SEVERITY
   ├─ Pc > 1e-4? → MANEUVER REQUIRED
   ├─ Pc > 1e-5? → ASSESS_FURTHER (get more tracking data)
   └─ Pc < 1e-5? → MONITOR (accept risk)

3. PLAN INTERVENTION
   ├─ Can we dodge? → AVOIDANCE (compute delta-v)
   ├─ Can't dodge? → DAMAGE_MINIMIZATION (choose impact strategy)
   └─ Can't do either? → ALERT (notify operators)

4. EXECUTE & ADAPT
   ├─ Apply maneuver (or recommend to operator)
   ├─ Re-assess ALL conjunctions (may have unintended consequences)
   └─ Update risk model with new trajectory data
```

### Testing & Verification

When making changes to orbital mechanics or risk calculations:
1. Verify physics accuracy against reference equations in `docs/physics.md`
2. Test with known conjunction scenarios (existing test data in simulation)
3. Validate that debris projections remain physically consistent
4. Run full simulation to 24 hours, check for anomalies

### Performance Considerations

- **N² Problem**: Conjunction screening is O(N²). For 10,000 objects = 50M pairs/epoch. Mitigated by geometric filters (apogee/perigee, plane, distance).
- **Integration Cost**: Propagating 10,000 orbits + covariance is CPU-intensive. RK78 integration is accurate but slower than Mean Motion formulae.
- **Optimization Complexity**: MCTS explores exponential decision trees. Practical horizon: 7 days. Longer horizons require approximation or sampling.
- **GPU Acceleration**: CuOpt solves LP/MILP in seconds (vs minutes for NetworkX on large constellations).



## Physics & Mathematical Context

The system is grounded in:
- **Keplerian orbital mechanics** for state propagation
- **Probability of collision (Pc)** estimation using covariance ellipsoids
- **Encounter dynamics** and relative motion analysis
- **Debris generation models** for post-collision risk assessment
- **Multi-body optimization** for finding optimal intervention sequences

See `docs/physics.md` for detailed mathematical references.

## Code Style & Conventions

- **Python version:** 3.8+ required
- **Module organization:** Functional decomposition by problem domain
- **Constants:** Centralized in `utils.py` (orbital parameters, physical constants)
- **Coordinate systems:** ECI (Earth-Centered Inertial) throughout backend; conversions at API boundaries
- **Type hints:** Use where practical for clarity
- **Comments:** Explain the "why" for complex physics; physics formulas should reference `docs/physics.md`

## Common Tasks

### Adding a New Avoidance Strategy
1. Implement strategy function in `avoidance.py`
2. Register in the conjunction assessment workflow
3. Add test case with known collision scenario
4. Document assumptions and delta-v requirements

### Updating Conjunction Assessment
1. Modify calculation in `conjunction.py`
2. Verify against reference publications (document source)
3. Update probability validation tests
4. Verify cascade impacts in `risk_optimizer.py`

### Dashboard Integration
1. Add new API endpoint in `api.py`
2. Consume via JavaScript in `app.js` or add new HTML file in `dashboard/`
3. Test with actual simulation data

### AI Analysis Enhancement
1. Extend prompts and logic in `ai_analysis.py`
2. Add new insight categories as needed
3. Validate that insights are physically meaningful (cross-check with simulation results)

## Debugging & Troubleshooting

- **Orbital mechanics errors:** Check units (always SI); validate against published two-line elements (TLEs)
- **Conjunction failures:** Enable debug output in `conjunction.py`; check covariance matrix conditioning
- **Optimization timeout:** Tune iteration limits in `risk_optimizer.py` and `cuopt_client.py`
- **Dashboard not updating:** Verify Flask CORS settings in `api.py`; check browser console for fetch errors

## Important Files to Review Before Major Changes

- `docs/physics.md` — Reference for orbital equations and assumptions
- `src/orbital_mechanics.py` — Core state propagation logic
- `src/conjunction.py` — Collision probability calculation (critical for accuracy)
- `src/risk_optimizer.py` — Multi-object optimization strategy

## Project Status & Roadmap

### Current Capabilities

✅ **Physics Simulation**
- Full 6-DOF orbit propagation with J2, drag, SRP perturbations
- Covariance propagation via State Transition Matrix
- Numerical integration via RK78

✅ **Conjunction Assessment**
- All-vs-all screening with geometric filters
- Probability of collision using covariance ellipsoid method
- TCA prediction

✅ **Maneuver Planning**
- STM-based delta-v optimization
- Multi-conjunction greedy solving
- Network flow formulation

✅ **Damage Mitigation**
- Debris generation model (NASA Breakup)
- Cascade risk calculation
- Impact geometry optimization

✅ **Visualization & API**
- Flask REST API with 5 core endpoints
- 3D orbital visualization (Three.js)
- Dashboard with real-time updates

✅ **AI Integration**
- OpenAI API for LLM-based analysis
- Risk insights and recommendation generation

### Planned Enhancements

🔄 **NVIDIA CuOpt Integration** (In Progress)
- GPU-accelerated LP/MILP solver for large constellations
- Vehicle Routing Problem formulation for maneuver sequencing
- Sub-second solve times for 10k+ object scenarios

🔄 **Agentic Decision Support** (Proposed)
- Nemotron function-calling LLM
- Tool-calling interface to expose API as agent actions
- Natural language query → optimized plan

🔄 **RAG Over Documentation** (Proposed)
- NV-Embed for semantic search
- Grounding LLM insights in physics.md and strategy.md
- "Ask the docs" dashboard chat

🔄 **Vision-Language Analysis** (Proposed)
- VLM analysis of generated plots (orbits_3d.png, risk_timeline.png)
- Automatic insight generation from visualizations

🔄 **Safety Constraints** (Proposed)
- NeMo Guardrails for LLM output validation
- Consistency checks against decision thresholds
- Liability-aware recommendations

### Known Limitations

⚠️ **Physics Model**
- J2/J3 oblateness only (higher-order perturbations neglected)
- Atmospheric density via exponential model (simplified vs. NRLMSISE-00)
- No 3rd-body perturbations (Sun/Moon) — adequate for LEO, not for MEO

⚠️ **Optimization Scope**
- Planning horizon: 7 days (beyond that, uncertainty dominates)
- Constellation size: tested to ~1000 objects, degrades beyond 10k without GPU

⚠️ **Uncertainty Propagation**
- Assumes Gaussian error distribution (real TLE errors are non-Gaussian at tails)
- Covariance matrix positive-definiteness not always guaranteed after long propagation

⚠️ **Debris Tracking**
- Fragment prediction uses averaged models (individual debris not tracked)
- Cascade analysis is probabilistic, not exact

## Related Documentation

- #[[file:docs/physics.md]] — Orbital mechanics equations and references
- #[[file:docs/strategy.md]] — Intervention strategy and decision framework
- #[[file:README.md]] — Project overview and quick start
- #[[file:content.md]] — Intuitive explanations and physical intuition
- #[[file:ai.md]] — AI integration opportunities and roadmap
