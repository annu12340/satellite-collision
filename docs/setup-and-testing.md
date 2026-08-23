# Setup and Testing Notes

## Prerequisites

- Python 3.8+
- pip (or pip3)
- A terminal with access to the project root

## Installation

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

## Environment Variables

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `OPENAI_API_KEY` | For AI analysis | — | OpenAI API key for LLM insights |
| `CUOPT_API_KEY` | For GPU optimization | — | NVIDIA CuOpt solver credentials |
| `SIM_SEED` | No | `42` | Random seed for reproducible simulation |
| `PORT` | No | `8050` | Server port (production entry point) |

## Running Tests

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

## Troubleshooting

| Symptom | Likely Cause | Fix |
|---------|-------------|-----|
| `ModuleNotFoundError: No module named 'src'` | Running from wrong directory | Run from project root: `cd satellite-collision` |
| `ImportError: numpy` | Missing dependencies | `pip install -r requirements.txt` |
| Dashboard shows no data | API not running or CORS issue | Check Flask is running; inspect browser console |
| `OPENAI_API_KEY` error | AI analysis called without key | Set env var or skip AI features |
| Port already in use | Another process on 5000/8050 | Kill it: `lsof -ti:5000 | xargs kill` |

## Adding a Custom Strategy (Quick Test)

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
