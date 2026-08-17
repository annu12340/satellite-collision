"""
NVIDIA cuOpt Client
====================

Thin transport layer for solving LP/MILP problems with NVIDIA cuOpt
(https://github.com/NVIDIA/cuOpt), NVIDIA's GPU-accelerated solver for
VRP-style routing and general LP/MILP problems.

`risk_optimizer.py` formulates the intervention-scheduling problem (which
maneuverable spacecraft resolves which conjunction, subject to fuel-budget
capacity constraints and TCA-driven mandatory coverage constraints) as a
Mixed-Integer Linear Program using cuOpt's documented wire format:

    https://docs.nvidia.com/cuopt/user-guide/latest/cuopt-server/examples/milp-examples.html
    (csr_constraint_matrix / constraint_bounds / objective_data /
     variable_bounds / variable_types / maximize / solver_config)

This module solves that exact problem_data dict against one of two
backends:

1. A self-hosted cuOpt GPU server, via NVIDIA's official `cuopt_sh_client`
   thin client — configure with the CUOPT_SERVER_IP / CUOPT_SERVER_PORT
   environment variables.
2. A local CPU fallback (scipy.optimize.milp, HiGHS backend) that consumes
   the *same* problem_data structure, so this repository runs standalone
   without GPU hardware or a running cuOpt service, and can be pointed at
   a real cuOpt deployment later with zero formulation changes.

Only the LP/MILP subset of the cuOpt API is used here (not the VRP/routing
endpoints, which are a better fit for delivery/dispatch style problems).
"""

import os
import time
from typing import Any, Dict, List, Optional

import numpy as np
from scipy import sparse
from scipy.optimize import milp, LinearConstraint, Bounds


class CuOptUnavailableError(RuntimeError):
    """Raised when neither a cuOpt server nor the local fallback can solve the problem."""


def _env_float(name: str, default: float) -> float:
    val = os.environ.get(name)
    if val is None:
        return default
    try:
        return float(val)
    except ValueError:
        return default


def _to_bound(value: Any) -> float:
    """Convert a cuOpt bound value ('inf' / 'ninf' / number) to a float."""
    if value == 'inf':
        return np.inf
    if value == 'ninf':
        return -np.inf
    return float(value)


class CuOptClient:
    """
    Client for solving LP/MILP problems via NVIDIA cuOpt.

    Configuration (environment variables):
        CUOPT_SERVER_IP    : hostname/IP of a self-hosted cuOpt server.
                              If unset, this client solves everything
                              locally without ever attempting a network
                              call.
        CUOPT_SERVER_PORT  : port of the self-hosted cuOpt server
                              (default: 5000)
        CUOPT_POLL_TIMEOUT : seconds to wait per poll when solving
                              remotely (default: 25)
    """

    def __init__(self, server_ip: Optional[str] = None, server_port: Optional[int] = None):
        self.server_ip = server_ip or os.environ.get('CUOPT_SERVER_IP')
        self.server_port = server_port or int(os.environ.get('CUOPT_SERVER_PORT', '5000'))
        self.poll_timeout = _env_float('CUOPT_POLL_TIMEOUT', 25.0)

    def server_configured(self) -> bool:
        """True if a self-hosted cuOpt GPU server has been configured."""
        return bool(self.server_ip)

    def solve_milp(self, problem_data: Dict[str, Any], time_limit: float = 10.0) -> Dict[str, Any]:
        """
        Solve an LP/MILP problem described in cuOpt's request schema.

        Parameters
        ----------
        problem_data : dict
            cuOpt LPData-schema dictionary: csr_constraint_matrix,
            constraint_bounds, objective_data, variable_bounds,
            variable_types (optional), variable_names (optional),
            maximize, solver_config.
        time_limit : float
            Solver time budget [seconds]

        Returns
        -------
        dict
            {"vars": {name: value}, "objective": float, "status": str,
             "backend": "cuopt-server" | "local-fallback"}
        """
        problem_data = dict(problem_data)
        solver_config = dict(problem_data.get('solver_config', {}))
        solver_config.setdefault('time_limit', time_limit)
        problem_data['solver_config'] = solver_config

        if self.server_configured():
            try:
                return self._solve_remote(problem_data)
            except Exception as e:
                # A cuOpt server outage should degrade gracefully to the
                # local solver, not take down the intervention pipeline.
                print(f"  cuOpt server unavailable ({e}); using local MILP fallback.")

        return self._solve_local(problem_data)

    # ------------------------------------------------------------------
    # Remote (self-hosted GPU cuOpt server)
    # ------------------------------------------------------------------

    def _solve_remote(self, problem_data: Dict[str, Any]) -> Dict[str, Any]:
        from cuopt_sh_client import CuOptServiceSelfHostClient  # optional dependency

        client = CuOptServiceSelfHostClient(
            ip=self.server_ip, port=self.server_port,
            polling_timeout=self.poll_timeout, timeout_exception=False
        )
        solution = client.get_LP_solve(problem_data, response_type='dict')

        # cuOpt's server uses an async invoke/poll interface: a busy
        # solver first replies with just a reqId.
        tries = 0
        while 'reqId' in solution and 'response' not in solution and tries < 60:
            time.sleep(1)
            solution = client.repoll(solution['reqId'], response_type='dict')
            tries += 1

        response = solution.get('response', {}).get('solver_response', {})
        sol = response.get('solution', {}) or {}
        return {
            'vars': sol.get('vars', {}),
            'objective': sol.get('primal_objective'),
            'status': response.get('status', 'unknown'),
            'backend': 'cuopt-server',
        }

    # ------------------------------------------------------------------
    # Local fallback (scipy.optimize.milp / HiGHS)
    # ------------------------------------------------------------------

    def _solve_local(self, problem_data: Dict[str, Any]) -> Dict[str, Any]:
        csr = problem_data['csr_constraint_matrix']
        cb = problem_data['constraint_bounds']
        obj = problem_data['objective_data']
        vb = problem_data['variable_bounds']
        var_names: Optional[List[str]] = problem_data.get('variable_names')
        var_types: Optional[List[str]] = problem_data.get('variable_types')
        maximize: bool = bool(problem_data.get('maximize', False))
        time_limit = problem_data.get('solver_config', {}).get('time_limit', 10.0)

        n_vars = len(vb['upper_bounds'])
        n_rows = len(cb['upper_bounds'])

        result_kwargs = dict(shape=(n_rows, n_vars))
        A = sparse.csr_matrix(
            (csr['values'], csr['indices'], csr['offsets']), **result_kwargs
        )

        row_lb = np.array([_to_bound(v) for v in cb['lower_bounds']])
        row_ub = np.array([_to_bound(v) for v in cb['upper_bounds']])
        constraints = LinearConstraint(A, row_lb, row_ub)

        var_lb = np.array([_to_bound(v) for v in vb['lower_bounds']])
        var_ub = np.array([_to_bound(v) for v in vb['upper_bounds']])
        bounds = Bounds(var_lb, var_ub)

        if var_types:
            integrality = np.array([1 if t == 'I' else 0 for t in var_types])
        else:
            integrality = np.zeros(n_vars)

        c = np.array(obj['coefficients'], dtype=float) * obj.get('scalability_factor', 1.0)
        if maximize:
            c = -c

        result = milp(
            c, constraints=constraints, integrality=integrality, bounds=bounds,
            options={'time_limit': max(float(time_limit), 1.0)}
        )

        if not result.success or result.x is None:
            raise CuOptUnavailableError(f"Local MILP fallback failed: {result.message}")

        x = result.x
        names = var_names or [str(i) for i in range(n_vars)]
        # `result.fun` is c^T x for the (possibly sign-flipped) objective
        # scipy minimized; undo the flip and add back cuOpt's offset term.
        real_obj = -result.fun if maximize else result.fun
        objective = float(real_obj) + float(obj.get('offset', 0.0))

        return {
            'vars': {name: float(val) for name, val in zip(names, x)},
            'objective': objective,
            'status': 'Optimal' if result.success else 'Infeasible',
            'backend': 'local-fallback',
        }
