# Technology Stack

This satellite collision prevention system combines advanced orbital mechanics simulation with AI-powered optimization and real-time visualization.

## Backend & Scientific Computing

### Core Physics & Numerical Methods

| Technology | Version | Purpose | Key Modules |
|-----------|---------|---------|-------------|
| **NumPy** | ≥1.24.0 | Vectorized orbital mechanics calculations, matrix operations | `orbital_mechanics.py`, `conjunction.py` |
| **SciPy** | ≥1.10.0 | Numerical integration (RK78), optimization algorithms, linear algebra | `orbital_mechanics.py`, `risk_optimizer.py` |
| **Matplotlib** | ≥3.7.0 | 2D analysis plots, trajectory visualization | Analysis scripts, dashboards |

### Graph & Network Analysis

| Technology | Version | Purpose | Key Modules |
|-----------|---------|---------|-------------|
| **NetworkX** | ≥3.0 | Conjunction dependency graph modeling, min-cost flow algorithms for optimal maneuver allocation | `risk_optimizer.py` |

### Web API & Communication

| Technology | Version | Purpose | Key Modules |
|-----------|---------|---------|-------------|
| **Flask** | ≥3.0.0 | Lightweight REST API server for dashboard integration | `api.py` |
| **Flask-CORS** | ≥4.0.0 | Cross-origin request handling for browser dashboard | `api.py` |
| **Requests** | ≥2.31.0 | HTTP client for external API calls (CuOpt, OpenAI) | `cuopt_client.py`, `ai_analysis.py` |

### AI & Large Language Models

| Technology | Version | Purpose | Key Modules |
|-----------|---------|---------|-------------|
| **OpenAI API** | ≥1.0.0 | GPT-4/3.5-turbo for natural language analysis and recommendations | `ai_analysis.py` |

### GPU-Accelerated Optimization (Optional)

| Technology | Purpose | Key Modules |
|-----------|---------|-------------|
| **NVIDIA CuOpt** | GPU-accelerated vehicle routing problem solver for large-scale maneuver sequencing | `cuopt_client.py` |
| Requires: NVIDIA GPU, CuOpt API credentials | Sub-second solve times for 100k+ decisions |

## Frontend & Visualization

### 3D Orbital Visualization

| Technology | Purpose | Key Files |
|-----------|---------|-----------| 
| **Three.js** | WebGL-based 3D orbital visualization in browser (handles 10k+ objects) | `dashboard/viz.html` |

### Web Frontend

| Technology | Purpose | Key Files |
|-----------|---------|-----------| 
| **HTML5 / CSS3** | Responsive dashboard UI | `dashboard/index.html`, `dashboard/style.css` |
| **JavaScript (Vanilla)** | Interactive controls, real-time updates via fetch API | `dashboard/app.js` |

## Development & Deployment

### Runtime Requirements

- **Python:** 3.8+ (required)
- **Operating System:** Linux, macOS, or Windows

### Production Deployment

| Technology | Purpose | Configuration |
|-----------|---------|---|
| **Gunicorn** | Production WSGI server for scaling beyond single process | Multi-worker deployment |
| **Render** | Cloud deployment platform | `render.yaml` configuration |

## Architecture Overview

### Module Organization by Domain

```
Physical Simulation Layer
├── orbital_mechanics.py      → NumPy, SciPy (RK78 integration)
├── conjunction.py            → NumPy, SciPy
└── utils.py                  → Constants, coordinate transforms

Decision Layer
├── avoidance.py              → NumPy, SciPy
├── damage_minimization.py    → NumPy
└── risk_optimizer.py         → NetworkX, CuOpt client

Integration & Orchestration Layer
├── simulation.py             → All above modules
├── ai_analysis.py            → OpenAI API
└── cuopt_client.py           → Requests

API & Frontend Layer
├── api.py                    → Flask, Flask-CORS
└── dashboard/                → Three.js, JavaScript, HTML/CSS
```

## Why These Technologies?

### NumPy & SciPy Ecosystem

- **Unmatched for scientific computing** in Python
- **Vectorized operations** handle 60k state variables (6 × 10,000 spacecraft) efficiently
- **BLAS/LAPACK backend** provides high-performance linear algebra
- **Battle-tested** in aerospace and scientific computing
- Enables rapid prototyping while maintaining accuracy

### Flask for Web API

- **Minimal overhead** suitable for prototype and production
- **Easy debugging** with built-in development server
- **WebSocket support** for future real-time dashboard enhancements
- **CORS middleware** for browser integration

### Three.js for Visualization

- **Standard library** for 3D visualization on the web
- **WebGL rendering** requires no plugins
- **Excellent performance** for 10k+ object visualization
- **Battle-tested** in industry applications

### OpenAI API for AI Analysis

- **Cost-effective** (no need to host LLM locally)
- **GPT-4 access** for high-quality natural language analysis
- **Function calling support** for future agentic workflows
- **Easy integration** via REST API

### NetworkX for Optimization

- **Graph-based risk modeling** of conjunction dependencies
- **Built-in algorithms** for min-cost flow optimization
- **Intuitive API** for conjunction dependency analysis
- Good for medium-scale problems (N < 5,000 conjunctions)

### CuOpt for Large-Scale Optimization

- **GPU acceleration** provides 100-1000× speedup over CPU
- **Vehicle Routing Problem (VRP)** formulation natural for maneuver sequencing
- **Sub-second solve times** for 100k+ decision variables
- Critical for production megaconstellations

## Performance Characteristics

### Computational Complexity

| Operation | Time Complexity | Typical Latency (N=10k) |
|-----------|-----------------|----------------------|
| Orbit propagation (1 day) | O(N·M) | ~10 seconds |
| Conjunction screening | O(N²) → O(0.1N²) with filters | ~500 seconds |
| Probability calculation | O(1) | ~1 ms per pair |
| Greedy optimization | O(C log C) | ~20 seconds |
| Network flow optimization | O(N³) | ~300 seconds |
| MCTS exploration (10k iterations) | O(k) | ~500 seconds |

### Memory Requirements

| Data | Per Object | N=1,000 | N=10,000 |
|------|-----------|---------|----------| 
| State vector | 48 bytes | 48 KB | 480 KB |
| Covariance matrix | 288 bytes | 288 KB | 2.88 MB |
| STM matrix | 288 bytes | 288 KB | 2.88 MB |
| **Total per epoch** | ~600 bytes | 0.6 MB | 6 MB |

**Rule of thumb:** 10k object constellation ≈ 60-100 MB RAM per epoch (including Python overhead)

## Scaling Roadmap

### Phase 1 (Current) — Research & Prototype
- **Stack:** Serial Python (NumPy/SciPy optimized)
- **Suitable for:** N < 5,000 objects
- **Use case:** Algorithm development, validation

### Phase 2 (Medium-term) — Production Hardening
- **Additions:** Parallel screening (multiprocessing.Pool), Numba JIT compilation
- **Suitable for:** N < 10,000 objects
- **Use case:** Small operational deployments

### Phase 3 (Long-term) — Enterprise Scale
- **Additions:** CuOpt GPU solver, RAPIDS for data processing
- **Suitable for:** N > 100,000 objects
- **Use case:** Production megaconstellations (Starlink, Kuiper scale)

## Dependencies Summary

### Production Dependencies

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

### Optional / Future Dependencies

```
nvidia-cuopt>=0.3.0     # GPU-accelerated optimization (requires NVIDIA GPU)
nvidia-nim-client       # Vision-Language Models for chart analysis
nvidia-nv-embed         # Embedding model for RAG over documentation
nemo-guardrails         # Safety guardrails for LLM outputs
memory-profiler         # Advanced profiling
py-spy                  # Performance profiling
mypy                    # Type checking
```

## Integration Points

### External APIs

- **OpenAI API** — Natural language analysis of conjunctions and maneuvers
- **NVIDIA CuOpt API** — GPU-accelerated optimization solver (optional)
- **TLE Data Sources** — Two-line element sets for spacecraft tracking (future)

### Dashboard Communication

- **REST API:** HTTP polling via Flask endpoints (`/api/risk`, `/api/conjunctions`, etc.)
- **Response Format:** JSON with ECI coordinate system (meters, m/s)
- **Update Rate:** 1 Hz for risk metrics, 1/min for conjunctions

## Code Style & Conventions

- **Python version:** 3.8+ required
- **Type hints:** Encouraged for function signatures
- **Coordinate system:** ECI (Earth-Centered Inertial) throughout backend
- **Constants:** Centralized in `utils.py`
- **Documentation:** Physics formulas reference `docs/physics.md`

## Deployment Configurations

### Single-Process (Prototype)
```bash
python -m src.simulation
```
- Suitable for: < 1,000 objects, 7-day planning horizon
- Resource: 1 CPU core, ~500MB RAM
- Execution: Sequential processing

### Multi-Process (Scaling)
```bash
gunicorn -w 4 -b 0.0.0.0:5000 src.api:app
```
- Suitable for: 1,000-10,000 objects
- Resource: 4 CPU cores, 2-4GB RAM
- Execution: Parallel conjunction screening

### GPU-Accelerated (Production)
```bash
python -m src.simulation  # Uses CuOpt for optimization
```
- Suitable for: 10,000+ objects
- Resource: 1 NVIDIA GPU (T4/A100), 8-16GB VRAM, 1 CPU core
- Execution: GPU solver for maneuver optimization

## References & Documentation

- **Physics Reference:** `docs/physics.md` — Orbital mechanics equations and validation
- **Strategy Framework:** `docs/strategy.md` — Intervention strategies and optimization approaches
- **Setup & Testing:** `docs/setup-and-testing.md` — Development and deployment guides
- **Architecture:** `docs/architecture-deep-dive.md` — System design and module interactions
