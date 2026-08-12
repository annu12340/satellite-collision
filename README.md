# AI Satellite Collision Prevention System

A physics-based simulation and optimization system for preventing orbital collisions
among thousands of spacecraft, and minimizing damage when collisions are unavoidable.

## Architecture

```
src/
├── orbital_mechanics.py    # Keplerian orbits, state propagation, perturbations
├── conjunction.py          # Conjunction assessment, probability of collision
├── avoidance.py            # Collision avoidance maneuver planning
├── damage_minimization.py  # Unavoidable collision damage optimization
├── risk_optimizer.py       # Multi-object long-term risk optimization
├── simulation.py           # Main simulation engine
└── utils.py                # Constants, coordinate transforms, helpers
docs/
├── physics.md              # Orbital mechanics physics and math reference
└── strategy.md             # Intervention strategy and decision framework
```

## Quick Start

```bash
pip install -r requirements.txt
python -m src.simulation
```

## Core Problem Statement

Given thousands of interacting spacecraft with:
- Uncertain trajectories (covariance in position/velocity)
- Limited delta-v budgets
- Future conjunction risks propagating forward

Find the sequence of interventions that minimizes long-term orbital risk
(collision probability × debris generation potential) across the entire constellation.
