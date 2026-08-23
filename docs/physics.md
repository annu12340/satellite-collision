# Orbital Mechanics Physics & Mathematics Reference

## 1. The Two-Body Problem

The motion of a satellite around Earth (ignoring all other forces) is governed by:

```
r̈ = -μ/|r|³ · r
```

Where:
- **r** = position vector from Earth's center to satellite [km]
- **μ** = GM_Earth = 398,600.4418 km³/s² (gravitational parameter)
- **r̈** = acceleration vector

This yields **conic section** orbits (ellipses for bound orbits).

### State Vector Representation

A satellite's state at any time is fully described by 6 parameters:

```
X = [x, y, z, vx, vy, vz]ᵀ
```

Position **r** = (x, y, z) and velocity **v** = (vx, vy, vz) in Earth-Centered Inertial (ECI) frame.

### Classical Orbital Elements (COE)

Equivalent representation using 6 Keplerian elements:

| Element | Symbol | Description |
|---------|--------|-------------|
| Semi-major axis | a | Size of orbit [km] |
| Eccentricity | e | Shape (0=circle, <1=ellipse) |
| Inclination | i | Tilt from equatorial plane [rad] |
| RAAN | Ω | Right ascension of ascending node [rad] |
| Argument of perigee | ω | Orientation within orbital plane [rad] |
| True anomaly | ν | Position along orbit [rad] |

### Conversion: COE → State Vector

```
r_PQW = [a(1-e²)/(1+e·cos(ν)) · cos(ν),
          a(1-e²)/(1+e·cos(ν)) · sin(ν),
          0]

v_PQW = √(μ/(a(1-e²))) · [-sin(ν),
                             e + cos(ν),
                             0]
```

Then rotate from perifocal (PQW) to ECI using rotation matrix R:

```
R = R₃(-Ω) · R₁(-i) · R₃(-ω)

r_ECI = R · r_PQW
v_ECI = R · v_PQW
```

### Orbital Period

```
T = 2π √(a³/μ)
```

For LEO (a ≈ 6,778 km): T ≈ 92 minutes.

---

## 2. Orbit Propagation

### Numerical Integration (Full Fidelity)

Integrate the equation of motion with perturbations:

```
r̈ = -μ/|r|³ · r + a_J2 + a_drag + a_SRP + a_3body + ...
```

Use RK4/RK78 or specialized integrators (Gauss-Jackson, Adams-Bashforth).

### Key Perturbations

**J2 Oblateness** (dominant for LEO):
```
a_J2x = -(3/2)·J2·μ·R_E²/r⁵ · x · (1 - 5z²/r²)
a_J2y = -(3/2)·J2·μ·R_E²/r⁵ · y · (1 - 5z²/r²)
a_J2z = -(3/2)·J2·μ·R_E²/r⁵ · z · (3 - 5z²/r²)
```

Where J2 = 1.08263 × 10⁻³, R_E = 6,378.137 km.

**Atmospheric Drag** (LEO < 1000 km):
```
a_drag = -(1/2) · ρ · Cd · A/m · |v_rel| · v_rel
```

- ρ = atmospheric density (exponential model or NRLMSISE-00)
- Cd ≈ 2.2 (drag coefficient)
- A/m = area-to-mass ratio [m²/kg]
- v_rel = velocity relative to rotating atmosphere

**Solar Radiation Pressure**:
```
a_SRP = -P_SR · Cr · A/m · r̂_sun
```

Where P_SR = 4.56 × 10⁻⁶ N/m², Cr = reflectivity coefficient.

---

## 3. Conjunction Assessment

### Time of Closest Approach (TCA)

Given two satellites with states X₁(t) and X₂(t), find t* that minimizes:

```
d(t) = |r₁(t) - r₂(t)|
```

Solve: d/dt |Δr(t)|² = 0 → 2·Δr·Δv = 0

### Miss Distance

At TCA:
```
miss_distance = |r₁(t*) - r₂(t*)|
```

Typical screening threshold: < 5 km (triggers detailed analysis).

### Coarse Screening Propagation

The initial all-vs-all geometric filter (`screen_conjunctions()` /
`generate_ephemeris_kepler()`) only needs to rule out pairs that are
obviously never close, not a precise Pc. It therefore propagates the
unperturbed two-body solution analytically via Kepler's equation
(Section 1) instead of numerically integrating J2/drag/SRP:

```
r(t), v(t) = Kepler_propagate(COE(t=0), t)   [no perturbations]
```

This is exact for the two-body problem (specific orbital energy
ε = v²/2 - μ/r is conserved identically, not just to integration
tolerance) and ~2 orders of magnitude faster than full perturbed
integration, since it has no adaptive-step ODE solver overhead.
Perturbation-induced position error over a single day at LEO altitudes
(~10 km from J2, ~500 m from drag — see Section 2 error budget) is
negligible next to the 5-25 km screening threshold used here.

Once a pair is flagged, `find_tca()` and `assess_conjunction()` still use
the fully perturbed `propagate_state()` for TCA refinement and the actual
Pc calculation — this fast path affects only which pairs get a detailed
look, never the accuracy of the detailed look itself.

### Probability of Collision (Pc)

The core metric. Uses the **combined covariance** of both objects.

**Setup:**
- Relative position: Δr = r₁ - r₂
- Combined covariance: C = C₁ + C₂ (assuming independent errors)
- Project into the **encounter plane** (perpendicular to relative velocity)

**2D Probability Integral (Alfriend/Akella method):**

```
Pc = (1/2π|C_2D|^½) ∫∫_A exp(-½ · xᵀ · C_2D⁻¹ · x) dx dy
```

Where:
- C_2D = 2×2 covariance projected onto encounter plane
- A = combined hard-body circle of radius R = R₁ + R₂
- x = (ξ, ζ) coordinates in encounter plane centered on miss vector

**Simplification for circular cross-section (Chan's formula):**

```
Pc = 1 - exp(-R²/(2·det(C_2D))) · Σ (R²/(2·det(C_2D)))^k / k!
```

Or numerically integrated using the series expansion.

**Risk thresholds (typical):**
- Pc > 10⁻⁴: Maneuver strongly recommended
- Pc > 10⁻⁵: Detailed assessment, maneuver considered
- Pc < 10⁻⁷: Acceptable risk

---

## 4. Covariance Propagation

Uncertainty grows over time. The state covariance P evolves as:

```
Ṗ = F·P + P·Fᵀ + Q
```

Where:
- F = ∂f/∂X (Jacobian of dynamics) — the state transition matrix
- Q = process noise (accounts for unmodeled forces)

### State Transition Matrix (STM)

```
Φ(t, t₀) = ∂X(t)/∂X(t₀)
```

Propagated alongside the state:
```
Φ̇ = F · Φ,   Φ(t₀, t₀) = I₆ₓ₆
```

Covariance at time t:
```
P(t) = Φ(t, t₀) · P(t₀) · Φ(t, t₀)ᵀ + ∫Q dt
```

---

## 5. Collision Avoidance Maneuvers

### Delta-V for Avoidance

A maneuver changes the satellite's velocity:
```
v_new = v_old + Δv
```

The goal: shift the trajectory so miss distance exceeds a safe threshold.

### Optimal Maneuver Direction

The most efficient avoidance maneuver is in the direction that maximizes
miss distance change per unit delta-v. In the encounter plane:

```
∂(miss)/∂(Δv) = ∂r_TCA/∂v_maneuver = Φ_rv(TCA, t_man)
```

Where Φ_rv is the position-velocity partition of the STM from maneuver time
to TCA.

### Maneuver Timing

Earlier maneuvers are more efficient (more time for trajectory to diverge):
```
Δ_miss ≈ |Φ_rv| · |Δv| · (TCA - t_maneuver)
```

Rule of thumb: maneuvering 1 orbit before TCA with 1 cm/s Δv produces ~100m miss change.

### Fuel Budget Constraint

Total available Δv is limited:
```
Σ |Δvᵢ| ≤ Δv_budget
```

For a typical LEO smallsat: Δv_budget ≈ 10-50 m/s total lifetime.

---

## 6. Damage Minimization (Unavoidable Collisions)

When collision cannot be avoided, the goal shifts to minimizing debris.

### NASA Breakup Model (Key Physics)

Debris generation depends primarily on:

1. **Specific energy** of collision:
   ```
   E_specific = ½ · m_projectile · v_rel² / m_target
   ```

2. **Catastrophic vs Non-catastrophic threshold:**
   ```
   E_catastrophic = 40 J/g = 40,000 J/kg
   ```
   
   - Below threshold: cratering, localized damage, fewer fragments
   - Above threshold: complete fragmentation, debris cloud

3. **Number of fragments** (> 10 cm):
   ```
   N(L > Lc) = 0.1 · M_total^0.75 · Lc^(-1.71)    [catastrophic]
   N(L > Lc) = 0.1 · m_p^0.75 · v_rel^0.5 · Lc^(-1.71)  [non-catastrophic]
   ```

### Damage Minimization Strategies

**Strategy 1: Reduce relative velocity**
- Lower v_rel → lower specific energy → fewer fragments
- Ideal: match velocities (but usually impossible with limited Δv)
- Even partial reduction helps: N ∝ v_rel^0.5

**Strategy 2: Minimize cross-section (attitude control)**
- Present minimum area to impact direction
- Reduces probability of hit AND damage if hit occurs

**Strategy 3: Choose impact geometry**
- Prefer **glancing** over head-on collisions
- Effective v_rel for damage = v_rel · sin(θ) where θ = impact angle
- Glancing → fragments stay closer to original orbits → less pollution

**Strategy 4: Orbit selection for debris**
- If collision is inevitable, maneuver so debris forms in orbits that:
  - Decay quickly (lower perigee → more drag → faster reentry)
  - Avoid populated orbital shells
  - Minimize debris spreading via differential precession

**Strategy 5: Controlled breakup altitude**
- Lower altitude → higher atmospheric density → faster debris removal
- Below ~400 km: most debris reenters within months
- Above ~800 km: debris persists for centuries

### Debris Orbit Distribution

After collision, fragments spread in velocity:
```
Δv_fragment ~ N(0, σ²)
σ ≈ f(E_specific, fragment_size)
```

This spreads orbital elements:
```
Δa ≈ 2a²v/μ · Δv_tangential
Δe ≈ 1/(na) · (2(e + cos ν)Δv_T + sin ν · Δv_R)
Δi ≈ r·cos(ω+ν)/(na²√(1-e²)) · Δv_N
```

---

## 7. Long-Term Risk: Kessler Syndrome

The cascading risk from debris:

```
dN/dt = S(t) - D(t) + C(t)
```

Where:
- S(t) = source rate (new launches)
- D(t) = decay rate (atmospheric drag removal)
- C(t) = collision-generated fragments = k · N² · v_rel · σ_cross

When C > D, the debris population grows exponentially even without new launches.
This is the **Kessler Syndrome** instability threshold.

### Critical Density

An orbital shell becomes unstable when:
```
N_crit = D / (k · v_rel · σ_cross · N)
```

Current status: 800-1000 km shell may already be near/above critical density.

---

## 8. Multi-Object Optimization (The Core AI Problem)

### Problem Formulation

Given:
- N spacecraft with states X₁...X_N and covariances P₁...P_N
- M predicted conjunctions over planning horizon T
- Δv budgets for each maneuverable spacecraft
- Probability of collision Pc_j for each conjunction j

**Minimize:**
```
J = Σⱼ w_j · Pc_j(Δv₁...Δv_N) + λ · Σᵢ |Δvᵢ|/Δv_budget_i + γ · Debris_risk
```

Where:
- w_j = risk weight for conjunction j (accounts for debris potential)
- λ = fuel penalty (preserve future maneuver capability)
- γ = long-term debris risk weight

### Sequential Decision Making

This is naturally a **Markov Decision Process (MDP)**:
- State: all orbital states + covariances + fuel levels
- Actions: maneuver commands for each spacecraft
- Transitions: orbital mechanics + stochastic perturbations
- Reward: negative risk (minimize collision probability)

### Cascade Awareness

A collision generates debris that creates NEW conjunctions:
```
Risk_total = Risk_direct + Σ P(collision_j) · E[Risk_cascade_j]
```

This creates a tree of possible futures that grows exponentially.
The AI must evaluate these branching futures efficiently (Monte Carlo tree search,
approximate dynamic programming, or deep reinforcement learning).

---

## 9. Key Constants

| Constant | Value | Description |
|----------|-------|-------------|
| μ_Earth | 398,600.4418 km³/s² | Earth gravitational parameter |
| R_Earth | 6,378.137 km | Earth equatorial radius |
| J2 | 1.08263 × 10⁻³ | Earth oblateness coefficient |
| ω_Earth | 7.2921159 × 10⁻⁵ rad/s | Earth rotation rate |
| P_SR | 4.56 × 10⁻⁶ N/m² | Solar radiation pressure at 1 AU |
| v_circ(LEO) | ~7.5 km/s | Circular velocity at 400 km |

---

## 10. Coordinate Frames

- **ECI (J2000)**: Earth-Centered Inertial — primary propagation frame
- **ECEF**: Earth-Centered Earth-Fixed — for ground tracks
- **RTN**: Radial-Transverse-Normal — for relative motion and maneuvers
  - R: radial (outward from Earth center)
  - T: transverse (in velocity direction for circular orbits)
  - N: normal (completes right-hand system, along angular momentum)
- **Encounter plane**: perpendicular to relative velocity at TCA
