"""
Production entry point for Render deployment.

Gunicorn imports this module and looks for the `app` Flask object.
The simulation runs once on first import, then the app serves requests.

Usage:
    gunicorn app:app --bind 0.0.0.0:$PORT --timeout 120 --workers 1
"""
import os
import sys

# Ensure the project root is on the path so `src.*` imports resolve
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from src.api import app, run_simulation

# Run the simulation on startup (populates the in-memory cache).
# Use a fixed seed for reproducibility; override with SIM_SEED env var.
_seed = int(os.environ.get("SIM_SEED", "42"))
run_simulation(seed=_seed)

# Gunicorn picks up `app` from this module.
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8050))
    app.run(host="0.0.0.0", port=port, debug=False, threaded=True)
