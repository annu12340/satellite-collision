#!/bin/bash
# ============================================================================
# Orbital Sentinel - 3D Dashboard Launcher
# ============================================================================

set -e

echo "=============================================="
echo "  ORBITAL SENTINEL - 3D Dashboard"
echo "=============================================="
echo ""

# Check Python
if ! command -v python3 &> /dev/null; then
    echo "ERROR: python3 not found. Please install Python 3.8+."
    exit 1
fi

# Install dependencies if needed
echo "[1/3] Checking dependencies..."
pip3 install -q flask flask-cors numpy scipy matplotlib networkx 2>/dev/null || \
pip install -q flask flask-cors numpy scipy matplotlib networkx 2>/dev/null || {
    echo "Installing from requirements.txt..."
    pip3 install -r requirements.txt
}

echo "[2/3] Starting simulation & server..."
echo "      (This takes ~30s to run orbital propagation)"
echo ""

# Run the API server
cd "$(dirname "$0")"
python3 src/api.py

