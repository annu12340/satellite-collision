"""
Multi-Object Risk Optimization Engine
======================================

The core AI problem: Given thousands of interacting spacecraft with uncertain
trajectories and limited fuel, what sequence of interventions minimizes
long-term orbital risk?

Implements:
- Conjunction risk graph (spacecraft as nodes, conjunctions as edges)
- Graph-based risk propagation (cascade modeling)
- Greedy and optimal intervention scheduling
- Markov Decision Process (MDP) formulation
- Monte Carlo Tree Search for intervention planning
- Dynamic fuel allocation across constellation
- Long-term risk evolution modeling (Kessler syndrome awareness)
"""

import numpy as np
import networkx as nx
from dataclasses import dataclass, field
from typing import List, Dict, Tuple, Optional, Set
from copy import deepcopy

from .utils import (
    MU_EARTH, R_EARTH,
    StateVector, Spacecraft, Conjunction, Maneuver,
    state_to_coe, orbital_period
)
from .conjunction import (
    run_conjunction_screening, compute_risk_score,
    estimate_debris_count, debris_lifetime
)
from .avoidance import (
    ManeuverDecision, design_avoidance_maneuver, apply_maneuver,
    evaluate_maneuver, plan_avoidance_campaign
)


# ============================================================================
# DATA STRUCTURES
# ============================================================================


@dataclass
class RiskState:
    """Global risk state of the orbital environment."""
    total_collision_probability: float = 0.0
    total_expected_debris: float = 0.0
    total_cascade_risk: float = 0.0
    fuel_consumed_total_ms: float = 0.0
    conjunctions_resolved: int = 0
    conjunctions_remaining: int = 0
    kessler_risk_index: float = 0.0  # 0-1, how close to instability


@dataclass
class InterventionPlan:
    """A complete intervention plan with expected outcomes."""
    maneuvers: List[Maneuver] = field(default_factory=list)
    expected_risk_reduction: float = 0.0
    total_fuel_cost_ms: float = 0.0
    conjunctions_resolved: List[str] = field(default_factory=list)
    risk_state_before: Optional[RiskState] = None
    risk_state_after: Optional[RiskState] = None


@dataclass
class OrbitalShell:
    """An altitude band with aggregated risk metrics."""
    alt_min_km: float
    alt_max_km: float
    object_count: int = 0
    total_mass_kg: float = 0.0
    conjunction_rate: float = 0.0  # Conjunctions per day
    collision_rate: float = 0.0  # Expected collisions per year
    debris_generation_rate: float = 0.0  # Fragments per year
    debris_removal_rate: float = 0.0  # Fragments removed per year (drag)
    is_unstable: bool = False  # True if generation > removal (Kessler)


# ============================================================================
# RISK GRAPH
# ============================================================================


class RiskGraph:
    """
    Graph representation of orbital collision risk.

    Nodes = spacecraft
    Edges = conjunctions (weighted by risk)

    Enables:
    - Identification of high-risk clusters
    - Cascade propagation modeling
    - Network-flow optimization for maneuver assignment
    """

    def __init__(self):
        self.graph = nx.Graph()
        self._spacecraft: Dict[str, Spacecraft] = {}
        self._conjunctions: List[Conjunction] = []

    def build_from_screening(self, spacecraft_list: List[Spacecraft],
                              conjunctions: List[Conjunction]):
        """
        Build the risk graph from screening results.

        Parameters
        ----------
        spacecraft_list : list of Spacecraft
            All tracked objects
        conjunctions : list of Conjunction
            All active conjunctions
        """
        self._spacecraft = {sc.id: sc for sc in spacecraft_list}
        self._conjunctions = conjunctions

        # Add nodes (spacecraft)
        for sc in spacecraft_list:
            coe = state_to_coe(sc.state)
            altitude = coe.a - R_EARTH

            self.graph.add_node(sc.id, **{
                'mass': sc.mass,
                'altitude_km': altitude,
                'maneuverable': sc.maneuverable,
                'fuel_remaining': sc.delta_v_budget - sc.delta_v_used,
                'area': sc.area
            })

        # Add edges (conjunctions)
        for conj in conjunctions:
            if conj.obj1_id in self._spacecraft and conj.obj2_id in self._spacecraft:
                self.graph.add_edge(conj.obj1_id, conj.obj2_id, **{
                    'risk_score': conj.risk_score,
                    'pc': conj.probability_of_collision,
                    'tca': conj.tca,
                    'miss_distance': conj.miss_distance,
                    'relative_velocity': conj.relative_velocity,
                    'conjunction': conj
                })

    def get_risk_clusters(self, min_cluster_risk: float = 1e-4) -> List[Set[str]]:
        """
        Identify clusters of spacecraft with interconnected collision risks.

        A cluster is a connected component where all edges exceed minimum risk.

        Parameters
        ----------
        min_cluster_risk : float
            Minimum edge risk to include in clustering

        Returns
        -------
        list of sets
            Each set contains spacecraft IDs in a risk cluster
        """
        # Create subgraph with only high-risk edges
        high_risk_edges = [
            (u, v) for u, v, d in self.graph.edges(data=True)
            if d.get('risk_score', 0) >= min_cluster_risk
        ]

        subgraph = self.graph.edge_subgraph(high_risk_edges)
        clusters = list(nx.connected_components(subgraph))

        # Sort by total cluster risk
        def cluster_risk(cluster):
            risk = 0
            for node in cluster:
                for _, _, data in self.graph.edges(node, data=True):
                    risk += data.get('risk_score', 0)
            return risk

        clusters.sort(key=cluster_risk, reverse=True)
        return clusters

    def cascade_risk(self, conjunction: Conjunction,
                     propagation_depth: int = 3) -> float:
        """
        Estimate cascade risk: if this conjunction results in collision,
        how much additional risk does the debris create?

        Uses breadth-first propagation through the risk graph.

        Parameters
        ----------
        conjunction : Conjunction
            The conjunction to evaluate
        propagation_depth : int
            How many "hops" of cascade to consider

        Returns
        -------
        float
            Total cascade risk (sum of downstream collision probabilities)
        """
        # Start from both objects involved
        seeds = {conjunction.obj1_id, conjunction.obj2_id}

        # Estimate debris from this collision
        sc1 = self._spacecraft.get(conjunction.obj1_id)
        sc2 = self._spacecraft.get(conjunction.obj2_id)
        if not sc1 or not sc2:
            return 0.0

        n_debris = estimate_debris_count(sc1.mass, sc2.mass, conjunction.relative_velocity)

        # Each debris fragment has some probability of hitting neighbors
        # Simplified: debris threatens all objects in similar orbits
        cascade_risk = 0.0
        visited = set(seeds)

        frontier = seeds
        for depth in range(propagation_depth):
            next_frontier = set()
            for node in frontier:
                for neighbor in self.graph.neighbors(node):
                    if neighbor not in visited:
                        edge_data = self.graph[node][neighbor]
                        # Cascade probability: original risk × debris multiplier
                        # Debris in the path increases collision probability
                        p_cascade = edge_data.get('pc', 0) * n_debris * 0.01
                        cascade_risk += p_cascade
                        next_frontier.add(neighbor)
                        visited.add(neighbor)

            frontier = next_frontier
            n_debris *= 0.3  # Debris cascade diminishes with depth

        return cascade_risk

    def total_risk(self) -> float:
        """Total risk across all edges in the graph."""
        return sum(d.get('risk_score', 0) for _, _, d in self.graph.edges(data=True))

    def highest_risk_conjunctions(self, n: int = 10) -> List[Conjunction]:
        """Get the N highest-risk conjunctions."""
        edges = sorted(
            self.graph.edges(data=True),
            key=lambda e: e[2].get('risk_score', 0),
            reverse=True
        )
        return [e[2]['conjunction'] for e in edges[:n] if 'conjunction' in e[2]]

    def most_threatened_spacecraft(self, n: int = 5) -> List[str]:
        """Find spacecraft involved in the most/highest-risk conjunctions."""
        risk_per_node = {}
        for node in self.graph.nodes:
            total = sum(
                d.get('risk_score', 0)
                for _, _, d in self.graph.edges(node, data=True)
            )
            risk_per_node[node] = total

        sorted_nodes = sorted(risk_per_node.items(), key=lambda x: x[1], reverse=True)
        return [node for node, _ in sorted_nodes[:n]]


# ============================================================================
# ORBITAL ENVIRONMENT MODEL (Kessler Syndrome)
# ============================================================================


class OrbitalEnvironment:
    """
    Model of the orbital environment for long-term risk assessment.

    Tracks object density by altitude shell and predicts stability
    (Kessler syndrome threshold).
    """

    def __init__(self, shell_width_km: float = 50.0,
                 min_alt_km: float = 200.0, max_alt_km: float = 2000.0):
        self.shell_width = shell_width_km
        self.shells: List[OrbitalShell] = []

        alt = min_alt_km
        while alt < max_alt_km:
            self.shells.append(OrbitalShell(
                alt_min_km=alt,
                alt_max_km=alt + shell_width_km
            ))
            alt += shell_width_km

    def populate_from_spacecraft(self, spacecraft_list: List[Spacecraft]):
        """Fill shells with spacecraft data."""
        for sc in spacecraft_list:
            coe = state_to_coe(sc.state)
            alt = coe.a - R_EARTH

            for shell in self.shells:
                if shell.alt_min_km <= alt < shell.alt_max_km:
                    shell.object_count += 1
                    shell.total_mass_kg += sc.mass
                    break

    def compute_stability(self):
        """
        Assess Kessler syndrome stability for each shell.

        A shell is unstable when debris generation rate exceeds removal rate:
            dN/dt = collision_rate × fragments_per_collision - drag_removal_rate

        If dN/dt > 0, the shell is in runaway growth.
        """
        for shell in self.shells:
            N = shell.object_count
            if N < 2:
                shell.is_unstable = False
                continue

            alt_mid = (shell.alt_min_km + shell.alt_max_km) / 2.0
            r = R_EARTH + alt_mid

            # Spatial density (objects per km³)
            # Shell volume ≈ 4π r² × Δr (thin shell approximation)
            shell_volume = 4 * np.pi * r**2 * self.shell_width  # km³
            spatial_density = N / shell_volume

            # Average relative velocity for crossing orbits
            v_circ = np.sqrt(MU_EARTH / r)  # km/s
            # For random inclinations: <v_rel> ≈ v_circ × sqrt(2) × sin(i_avg)
            v_rel_avg = v_circ * 0.5  # Conservative average

            # Average cross-section (10 m² typical)
            avg_cross_section = 10.0 / 1e6  # km²

            # Collision rate: R = N² × v_rel × σ / V (kinetic theory)
            collision_rate_per_year = (
                N * (N - 1) / 2 * v_rel_avg * avg_cross_section / shell_volume
                * 365.25 * 86400  # per second → per year
            )

            # Debris per collision (average)
            avg_mass = shell.total_mass_kg / max(N, 1)
            fragments_per_collision = estimate_debris_count(
                avg_mass, avg_mass, v_rel_avg
            )

            # Generation rate
            shell.debris_generation_rate = collision_rate_per_year * fragments_per_collision
            shell.collision_rate = collision_rate_per_year

            # Removal rate (atmospheric drag)
            lifetime = debris_lifetime(alt_mid)
            if lifetime > 0:
                shell.debris_removal_rate = N / lifetime  # Objects removed per year
            else:
                shell.debris_removal_rate = N  # Very low altitude, everything decays

            # Stability assessment
            shell.is_unstable = shell.debris_generation_rate > shell.debris_removal_rate
            shell.conjunction_rate = collision_rate_per_year * 1000  # Rough: conj >> collisions

    def kessler_risk_index(self) -> float:
        """
        Compute overall Kessler syndrome risk index (0-1).

        0 = all shells stable
        1 = critical shells in runaway
        """
        critical_shells = [s for s in self.shells
                          if s.alt_min_km >= 700 and s.alt_max_km <= 1100]

        if not critical_shells:
            return 0.0

        unstable_fraction = sum(1 for s in critical_shells if s.is_unstable) / len(critical_shells)
        max_ratio = max(
            s.debris_generation_rate / max(s.debris_removal_rate, 1e-10)
            for s in critical_shells
        )

        return min(1.0, unstable_fraction * 0.5 + min(max_ratio / 10.0, 0.5))


# ============================================================================
# INTERVENTION OPTIMIZER
# ============================================================================


class InterventionOptimizer:
    """
    Optimizes the sequence of collision avoidance interventions across
    an entire constellation.

    Approaches:
    1. Greedy: handle highest-risk conjunction first, iterate
    2. Graph-based: network flow optimization
    3. MCTS: Monte Carlo Tree Search for multi-step planning
    """

    def __init__(self, spacecraft_list: List[Spacecraft],
                 conjunctions: List[Conjunction],
                 planning_horizon_s: float = 7 * 86400.0):
        """
        Parameters
        ----------
        spacecraft_list : list of Spacecraft
            All spacecraft in constellation
        conjunctions : list of Conjunction
            All active conjunctions
        planning_horizon_s : float
            Planning horizon [seconds] (default: 7 days)
        """
        self.spacecraft = {sc.id: deepcopy(sc) for sc in spacecraft_list}
        self.conjunctions = sorted(conjunctions, key=lambda c: c.risk_score, reverse=True)
        self.horizon = planning_horizon_s
        self.risk_graph = RiskGraph()
        self.risk_graph.build_from_screening(spacecraft_list, conjunctions)
        self.environment = OrbitalEnvironment()
        self.environment.populate_from_spacecraft(spacecraft_list)
        self.environment.compute_stability()

    def compute_risk_state(self) -> RiskState:
        """Compute current global risk state."""
        state = RiskState()

        for conj in self.conjunctions:
            state.total_collision_probability += conj.probability_of_collision

            sc1 = self.spacecraft.get(conj.obj1_id)
            sc2 = self.spacecraft.get(conj.obj2_id)
            if sc1 and sc2:
                state.total_expected_debris += (
                    conj.probability_of_collision *
                    estimate_debris_count(sc1.mass, sc2.mass, conj.relative_velocity)
                )

        state.total_cascade_risk = sum(
            self.risk_graph.cascade_risk(c) for c in self.conjunctions[:10]
        )
        state.conjunctions_remaining = len(self.conjunctions)
        state.kessler_risk_index = self.environment.kessler_risk_index()

        for sc in self.spacecraft.values():
            state.fuel_consumed_total_ms += sc.delta_v_used

        return state

    def greedy_optimize(self, max_maneuvers: int = 50) -> InterventionPlan:
        """
        Greedy optimization: handle highest-risk conjunction first.

        Simple but effective baseline. Handles each conjunction independently,
        in order of decreasing risk.

        Parameters
        ----------
        max_maneuvers : int
            Maximum number of maneuvers to plan

        Returns
        -------
        InterventionPlan
            Planned interventions
        """
        plan = InterventionPlan()
        plan.risk_state_before = self.compute_risk_state()

        # Work with copies so we can track state changes
        working_spacecraft = deepcopy(self.spacecraft)
        resolved = set()

        for conj in self.conjunctions:
            if len(plan.maneuvers) >= max_maneuvers:
                break

            conj_id = f"{conj.obj1_id}_{conj.obj2_id}_{conj.tca:.0f}"
            if conj_id in resolved:
                continue

            # Get spacecraft
            sc1 = working_spacecraft.get(conj.obj1_id)
            sc2 = working_spacecraft.get(conj.obj2_id)
            if not sc1 or not sc2:
                continue

            # Decision check
            decision = ManeuverDecision.should_maneuver(conj, sc1, conj.tca)
            if decision not in ('MANEUVER', 'CONSIDER'):
                continue

            # Choose who maneuvers (more fuel = maneuvers)
            if sc1.maneuverable and sc2.maneuverable:
                fuel1 = sc1.delta_v_budget - sc1.delta_v_used
                fuel2 = sc2.delta_v_budget - sc2.delta_v_used
                maneuverer, target = (sc1, sc2) if fuel1 >= fuel2 else (sc2, sc1)
            elif sc1.maneuverable:
                maneuverer, target = sc1, sc2
            elif sc2.maneuverable:
                maneuverer, target = sc2, sc1
            else:
                continue

            # Design maneuver
            maneuver = design_avoidance_maneuver(maneuverer, target, conj)

            if maneuver is not None:
                plan.maneuvers.append(maneuver)
                plan.total_fuel_cost_ms += maneuver.fuel_cost
                plan.conjunctions_resolved.append(conj_id)
                resolved.add(conj_id)

                # Update working state
                working_spacecraft[maneuverer.id] = apply_maneuver(maneuverer, maneuver)

        plan.conjunctions_resolved = list(resolved)
        plan.expected_risk_reduction = (
            plan.risk_state_before.total_collision_probability *
            len(resolved) / max(len(self.conjunctions), 1)
        )

        return plan

    def network_flow_optimize(self) -> InterventionPlan:
        """
        Graph-based optimization using minimum-cost network flow.

        Formulation:
        - Source: risk (collision probability to be "absorbed")
        - Sink: safety (risk successfully mitigated)
        - Edges: maneuver options with costs (fuel) and capacities (Δv budgets)

        Minimizes total fuel expenditure subject to risk reduction constraints.
        """
        plan = InterventionPlan()
        plan.risk_state_before = self.compute_risk_state()

        # Build flow network
        G = nx.DiGraph()

        # Source and sink
        G.add_node('source')
        G.add_node('sink')

        # For each conjunction: source → conjunction node (capacity = risk to mitigate)
        for i, conj in enumerate(self.conjunctions):
            conj_node = f"conj_{i}"
            G.add_edge('source', conj_node, capacity=conj.risk_score, weight=0)

            # For each maneuverable spacecraft involved:
            # conjunction → spacecraft → sink (capacity = fuel, cost = Δv needed)
            for sc_id in [conj.obj1_id, conj.obj2_id]:
                sc = self.spacecraft.get(sc_id)
                if sc and sc.maneuverable:
                    sc_node = f"sc_{sc_id}"
                    fuel = sc.delta_v_budget - sc.delta_v_used

                    # Edge: conjunction → spacecraft (can this SC resolve this conj?)
                    # Cost proportional to estimated Δv needed
                    estimated_dv = 0.01  # km/s rough estimate
                    G.add_edge(conj_node, sc_node,
                              capacity=conj.risk_score,
                              weight=estimated_dv * 1000)  # Convert to m/s cost

                    # Edge: spacecraft → sink (limited by fuel)
                    if not G.has_edge(sc_node, 'sink'):
                        G.add_edge(sc_node, 'sink', capacity=fuel, weight=0)

        # Solve minimum cost flow (approximate via greedy matching)
        # Full min-cost flow would use nx.min_cost_flow, but we need a feasible flow first
        try:
            # Use maximum flow as upper bound on what we can resolve
            flow_value, flow_dict = nx.maximum_flow(G, 'source', 'sink')

            # Extract maneuver assignments from flow
            for conj_node, targets in flow_dict.items():
                if not conj_node.startswith('conj_'):
                    continue

                conj_idx = int(conj_node.split('_')[1])
                conj = self.conjunctions[conj_idx]

                for sc_node, flow in targets.items():
                    if flow > 0 and sc_node.startswith('sc_'):
                        sc_id = sc_node[3:]  # Remove 'sc_' prefix
                        sc = self.spacecraft.get(sc_id)
                        if sc:
                            other_id = (conj.obj2_id if conj.obj1_id == sc_id
                                       else conj.obj1_id)
                            other = self.spacecraft.get(other_id)
                            if other:
                                maneuver = design_avoidance_maneuver(sc, other, conj)
                                if maneuver:
                                    plan.maneuvers.append(maneuver)
                                    plan.total_fuel_cost_ms += maneuver.fuel_cost
                                    break  # One spacecraft per conjunction

        except (nx.NetworkXError, nx.NetworkXUnfeasible):
            # Fall back to greedy if flow optimization fails
            return self.greedy_optimize()

        return plan

    def mcts_optimize(self, n_simulations: int = 100,
                      max_depth: int = 10,
                      exploration_weight: float = 1.414) -> InterventionPlan:
        """
        Monte Carlo Tree Search for multi-step intervention planning.

        Explores the tree of possible intervention sequences:
        - Each node = current state (which conjunctions resolved, fuel remaining)
        - Each edge = a maneuver decision
        - Leaf evaluation = total risk after all maneuvers

        This handles the sequential nature of the problem:
        maneuver A might make maneuver B unnecessary, or might create
        new conjunctions.

        Parameters
        ----------
        n_simulations : int
            Number of MCTS simulations to run
        max_depth : int
            Maximum planning depth (maneuvers)
        exploration_weight : float
            UCB1 exploration constant (sqrt(2) is theoretical optimal)

        Returns
        -------
        InterventionPlan
            Best intervention plan found
        """
        plan = InterventionPlan()
        plan.risk_state_before = self.compute_risk_state()

        # MCTS Node
        class MCTSNode:
            def __init__(self, state, parent=None, action=None):
                self.state = state  # (resolved_set, fuel_state_dict)
                self.parent = parent
                self.action = action  # Conjunction index that was resolved
                self.children = []
                self.visits = 0
                self.total_reward = 0.0
                self.untried_actions = None

            def ucb1(self, c=exploration_weight):
                if self.visits == 0:
                    return float('inf')
                exploit = self.total_reward / self.visits
                explore = c * np.sqrt(np.log(self.parent.visits) / self.visits)
                return exploit + explore

        # Initial state
        initial_fuel = {
            sc_id: sc.delta_v_budget - sc.delta_v_used
            for sc_id, sc in self.spacecraft.items()
        }
        root = MCTSNode(state=(frozenset(), initial_fuel))

        # Available actions: conjunctions that can be resolved
        all_actions = list(range(len(self.conjunctions)))

        def get_available_actions(node):
            """Get actions not yet taken from this state."""
            resolved = node.state[0]
            fuel_state = node.state[1]

            available = []
            for idx in all_actions:
                if idx in resolved:
                    continue
                conj = self.conjunctions[idx]

                # Check if any involved spacecraft has fuel
                for sc_id in [conj.obj1_id, conj.obj2_id]:
                    if fuel_state.get(sc_id, 0) > 1.0:  # At least 1 m/s
                        available.append(idx)
                        break

            return available

        def simulate_rollout(resolved_set, fuel_state, depth=0):
            """Random rollout from current state to estimate value."""
            current_resolved = set(resolved_set)
            current_fuel = dict(fuel_state)

            for _ in range(max_depth - depth):
                available = [
                    i for i in all_actions
                    if i not in current_resolved
                ]
                if not available:
                    break

                # Random action
                action = np.random.choice(available)
                conj = self.conjunctions[action]

                # Check fuel and "resolve"
                for sc_id in [conj.obj1_id, conj.obj2_id]:
                    if current_fuel.get(sc_id, 0) > 5.0:
                        current_fuel[sc_id] -= 5.0  # Estimated cost
                        current_resolved.add(action)
                        break

            # Evaluate: total risk of unresolved conjunctions
            remaining_risk = sum(
                self.conjunctions[i].risk_score
                for i in all_actions if i not in current_resolved
            )
            total_risk = sum(c.risk_score for c in self.conjunctions)
            reward = 1.0 - (remaining_risk / max(total_risk, 1e-10))

            return reward

        # MCTS main loop
        for _ in range(n_simulations):
            node = root

            # Selection: traverse tree using UCB1
            while node.children and not node.untried_actions:
                node = max(node.children, key=lambda n: n.ucb1())

            # Expansion: add a child node
            if node.untried_actions is None:
                node.untried_actions = get_available_actions(node)

            if node.untried_actions:
                action = node.untried_actions.pop(
                    np.random.randint(len(node.untried_actions))
                )

                # Create new state
                new_resolved = frozenset(node.state[0] | {action})
                new_fuel = dict(node.state[1])

                conj = self.conjunctions[action]
                for sc_id in [conj.obj1_id, conj.obj2_id]:
                    if new_fuel.get(sc_id, 0) > 5.0:
                        new_fuel[sc_id] -= 5.0
                        break

                child = MCTSNode(
                    state=(new_resolved, new_fuel),
                    parent=node,
                    action=action
                )
                node.children.append(child)
                node = child

            # Simulation: random rollout
            reward = simulate_rollout(node.state[0], node.state[1])

            # Backpropagation
            while node is not None:
                node.visits += 1
                node.total_reward += reward
                node = node.parent

        # Extract best plan from tree
        best_sequence = []
        node = root
        while node.children:
            node = max(node.children, key=lambda n: n.visits)
            if node.action is not None:
                best_sequence.append(node.action)

        # Convert to actual maneuvers
        working_spacecraft = deepcopy(self.spacecraft)

        for conj_idx in best_sequence:
            conj = self.conjunctions[conj_idx]
            sc1 = working_spacecraft.get(conj.obj1_id)
            sc2 = working_spacecraft.get(conj.obj2_id)

            if not sc1 or not sc2:
                continue

            # Choose maneuverer
            if sc1.maneuverable and (sc1.delta_v_budget - sc1.delta_v_used) > 1.0:
                maneuverer, target = sc1, sc2
            elif sc2.maneuverable and (sc2.delta_v_budget - sc2.delta_v_used) > 1.0:
                maneuverer, target = sc2, sc1
            else:
                continue

            maneuver = design_avoidance_maneuver(maneuverer, target, conj)
            if maneuver:
                plan.maneuvers.append(maneuver)
                plan.total_fuel_cost_ms += maneuver.fuel_cost
                plan.conjunctions_resolved.append(
                    f"{conj.obj1_id}_{conj.obj2_id}_{conj.tca:.0f}"
                )
                working_spacecraft[maneuverer.id] = apply_maneuver(maneuverer, maneuver)

        plan.expected_risk_reduction = (
            plan.risk_state_before.total_collision_probability *
            len(plan.conjunctions_resolved) / max(len(self.conjunctions), 1)
        )

        return plan

    def optimize(self, method: str = 'adaptive') -> InterventionPlan:
        """
        Run the optimizer with selected method.

        Parameters
        ----------
        method : str
            'greedy', 'network_flow', 'mcts', or 'adaptive'
            Adaptive selects based on problem size.

        Returns
        -------
        InterventionPlan
            Optimal intervention plan
        """
        n_conjunctions = len(self.conjunctions)
        n_spacecraft = len(self.spacecraft)

        if method == 'adaptive':
            # Choose method based on problem complexity
            if n_conjunctions <= 5:
                method = 'greedy'  # Simple enough for greedy
            elif n_conjunctions <= 50:
                method = 'network_flow'  # Medium: use graph optimization
            else:
                method = 'mcts'  # Large: need search

        if method == 'greedy':
            return self.greedy_optimize()
        elif method == 'network_flow':
            return self.network_flow_optimize()
        elif method == 'mcts':
            return self.mcts_optimize()
        else:
            return self.greedy_optimize()


# ============================================================================
# FUEL ALLOCATION
# ============================================================================


def allocate_fuel_budget(spacecraft_list: List[Spacecraft],
                         conjunctions: List[Conjunction],
                         planning_horizon_days: float = 30.0) -> Dict[str, float]:
    """
    Dynamically allocate fuel reserves across the constellation.

    Spacecraft facing more conjunctions or in higher-risk orbital shells
    should keep more fuel in reserve.

    Parameters
    ----------
    spacecraft_list : list of Spacecraft
        All spacecraft
    conjunctions : list of Conjunction
        Known conjunctions in planning window
    planning_horizon_days : float
        How far ahead to plan

    Returns
    -------
    dict
        spacecraft_id → recommended fuel reserve [m/s]
    """
    # Count conjunctions per spacecraft
    conj_count = {}
    risk_exposure = {}

    for conj in conjunctions:
        for sc_id in [conj.obj1_id, conj.obj2_id]:
            conj_count[sc_id] = conj_count.get(sc_id, 0) + 1
            risk_exposure[sc_id] = risk_exposure.get(sc_id, 0) + conj.risk_score

    reserves = {}
    for sc in spacecraft_list:
        if not sc.maneuverable:
            reserves[sc.id] = 0.0
            continue

        total_fuel = sc.delta_v_budget - sc.delta_v_used

        # Base reserve: 30% for unknown future conjunctions
        base_reserve = total_fuel * 0.3

        # Risk-adjusted: spacecraft in crowded shells need more reserve
        n_conj = conj_count.get(sc.id, 0)
        risk = risk_exposure.get(sc.id, 0)

        # Expected future conjunctions (extrapolate from current rate)
        expected_future = n_conj * (planning_horizon_days / 7.0)  # Scale from 1-week data

        # Reserve enough for expected_future maneuvers at 5 m/s each
        risk_reserve = min(expected_future * 5.0, total_fuel * 0.5)

        reserves[sc.id] = min(base_reserve + risk_reserve, total_fuel * 0.7)

    return reserves


# ============================================================================
# LONG-TERM RISK EVOLUTION
# ============================================================================


def project_risk_evolution(spacecraft_list: List[Spacecraft],
                            conjunctions: List[Conjunction],
                            years: float = 5.0,
                            time_steps: int = 60) -> List[RiskState]:
    """
    Project how orbital risk evolves over time (months/years).

    Models:
    - Fuel depletion (more maneuvers = less future capability)
    - Orbital decay (objects deorbit naturally)
    - New launches (population growth)
    - Collision debris (if any collisions occur)

    Parameters
    ----------
    spacecraft_list : list of Spacecraft
        Current constellation
    conjunctions : list of Conjunction
        Current conjunction list (used to estimate rates)
    years : float
        Projection horizon [years]
    time_steps : int
        Number of time steps

    Returns
    -------
    list of RiskState
        Risk state at each time step
    """
    dt_years = years / time_steps
    dt_seconds = dt_years * 365.25 * 86400

    # Current metrics
    N = len(spacecraft_list)
    conj_rate = len(conjunctions) / 7.0  # Conjunctions per day (assuming 1-week data)
    total_mass = sum(sc.mass for sc in spacecraft_list)

    states = []

    current_N = N
    current_fuel_fraction = 1.0  # Average fuel remaining fraction
    accumulated_debris = 0

    for step in range(time_steps):
        state = RiskState()

        # Collision probability scales as N²
        scaling = (current_N / max(N, 1))**2
        state.total_collision_probability = (
            sum(c.probability_of_collision for c in conjunctions) * scaling
        )

        # Expected debris from collisions in this period
        collision_prob_per_step = state.total_collision_probability * dt_years * 365.0
        new_debris = collision_prob_per_step * 500  # Average fragments per collision
        accumulated_debris += new_debris

        # Debris removal (atmospheric drag)
        # Average lifetime ~ 100 years for most shells
        debris_removed = accumulated_debris * dt_years / 100.0
        accumulated_debris = max(0, accumulated_debris - debris_removed)

        state.total_expected_debris = accumulated_debris
        state.conjunctions_remaining = int(conj_rate * 7 * scaling)

        # Fuel depletion (assume average 2 maneuvers/year at 5 m/s each)
        fuel_used_per_year = 10.0 / 25.0  # Fraction of typical budget
        current_fuel_fraction -= fuel_used_per_year * dt_years
        current_fuel_fraction = max(0.0, current_fuel_fraction)

        state.fuel_consumed_total_ms = (1 - current_fuel_fraction) * 25.0 * N

        # Population growth (new launches)
        launch_rate = 0.1 * N  # 10% growth per year
        current_N += int(launch_rate * dt_years)
        current_N += int(accumulated_debris * 0.01)  # Debris adds to tracked objects

        # Kessler index
        env = OrbitalEnvironment()
        # Simplified: just check if growth exceeds removal
        if accumulated_debris > 0:
            generation = new_debris / max(dt_years, 0.01)
            removal = debris_removed / max(dt_years, 0.01)
            state.kessler_risk_index = min(1.0, generation / max(removal, 1.0) / 10.0)
        else:
            state.kessler_risk_index = 0.0

        states.append(state)

    return states
