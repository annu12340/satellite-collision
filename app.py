"""
Production entry point for Render deployment.

KEY DESIGN: Gunicorn must bind the port within ~60s or Render kills the deploy.
The simulation + heavy scipy/numpy imports take 2-3 minutes on free-tier hardware.

Solution: Create a minimal Flask app HERE that binds immediately, then load
the real app and run the simulation in a background thread. Once ready,
all requests are forwarded to the real API.

Usage:
    gunicorn app:app --bind 0.0.0.0:$PORT --timeout 300 --workers 1
"""
import os
import sys
import threading

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from flask import Flask, jsonify, send_from_directory, request, Response
from flask_cors import CORS

# --------------------------------------------------------------------------
# Lightweight Flask app that binds the port IMMEDIATELY
# --------------------------------------------------------------------------
app = Flask(__name__, static_folder='dashboard', static_url_path='')
CORS(app)

_sim_ready = threading.Event()
_sim_error = None
_real_app = None  # Will hold the fully-loaded src.api.app once ready


def _run_sim_background():
    """Import the heavy modules and run simulation in background."""
    global _sim_error, _real_app
    try:
        # These imports pull in numpy, scipy, etc. — the slow part
        from src.api import app as real_app, run_simulation
        seed = int(os.environ.get("SIM_SEED", "42"))
        run_simulation(seed=seed)
        _real_app = real_app
        _sim_ready.set()
        print("\n  Simulation ready. Dashboard is live.\n", flush=True)
    except Exception as e:
        import traceback
        _sim_error = str(e)
        traceback.print_exc()
        _sim_ready.set()


# Start background loading immediately
_sim_thread = threading.Thread(target=_run_sim_background, daemon=True)
_sim_thread.start()


_LOADING_HTML = '''<!DOCTYPE html>
<html><head><title>Loading...</title>
<meta http-equiv="refresh" content="10">
</head><body>
Simulation is starting, please check back shortly.
</body></html>'''


@app.route('/healthz')
def healthz():
    """Health check - returns 200 immediately so Render knows the port is alive."""
    if _sim_error:
        return jsonify({'status': 'error', 'message': _sim_error}), 500
    if _sim_ready.is_set():
        return jsonify({'status': 'ok', 'simulation': 'ready'}), 200
    return jsonify({'status': 'ok', 'simulation': 'loading'}), 200


@app.route('/')
def index():
    # landing.html is a static, client-rendered page that doesn't need the
    # simulation to be loaded (it only links to index.html for the actual
    # dashboard), so serve it unconditionally instead of gating it behind
    # _sim_ready. Gating it here was the bug: /landing.html worked because
    # Flask's built-in static route serves it directly, but / used this
    # readiness check and got stuck showing the loading placeholder forever
    # if the background simulation thread hung.
    return send_from_directory('dashboard', 'landing.html')


@app.route('/api/<path:path>', methods=['GET', 'POST'])
def api_proxy(path):
    """Proxy API requests to the real app once ready, or return 503."""
    if not _sim_ready.is_set():
        return jsonify({
            'status': 'loading',
            'message': 'Simulation is initializing (~2 min). Please retry shortly.'
        }), 503
    if _sim_error:
        return jsonify({'status': 'error', 'message': _sim_error}), 500
    # Forward to real app
    with _real_app.test_client() as client:
        if request.method == 'POST':
            resp = client.post(
                f'/api/{path}',
                json=request.get_json(silent=True),
                headers={k: v for k, v in request.headers if k.lower() != 'host'}
            )
        else:
            resp = client.get(
                f'/api/{path}?{request.query_string.decode()}',
                headers={k: v for k, v in request.headers if k.lower() != 'host'}
            )
        return Response(resp.data, status=resp.status_code, headers=dict(resp.headers))


@app.route('/<path:path>')
def static_proxy(path):
    """Serve static dashboard files or proxy to real app."""
    if _sim_ready.is_set() and _real_app:
        # Try serving from dashboard folder
        try:
            return send_from_directory('dashboard', path)
        except Exception:
            pass
        # Try the real app (for routes like /orbits_3d.png)
        with _real_app.test_client() as client:
            resp = client.get(f'/{path}')
            return Response(resp.data, status=resp.status_code, headers=dict(resp.headers))
    return _LOADING_HTML, 200


# --------------------------------------------------------------------------
# Direct execution (local dev)
# --------------------------------------------------------------------------
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8050))
    print(f"\n  Server starting on port {port} (simulation loading in background)...\n")
    app.run(host="0.0.0.0", port=port, debug=False, threaded=True)
