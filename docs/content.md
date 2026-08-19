## The Big Picture

Imagine you have thousands of objects flying around Earth at 28,000 km/h. They can't stop. They can't easily turn. They have very limited fuel. And if two of them smash into each other, they create thousands of new bullet-like fragments that threaten everything else.

Your job: figure out which ones might hit each other, push the ones you can control out of the way, and when you *can't* avoid a crash, make it as gentle as possible.

That's this codebase.

---

## Step 1: Understanding How Satellites Move (`orbital_mechanics.py`)

### The core idea: falling and missing

A satellite isn't floating — it's *falling* toward Earth, but moving sideways so fast that it keeps missing. That's what an orbit is.

Newton gives us:
```
acceleration = -μ / r²   (pointed toward Earth's center)
```

Where μ = 398,600 km³/s² is Earth's "gravitational pull strength" and r is the distance from Earth's center.

This equation produces ellipses. A satellite's orbit is completely described by **6 numbers** — think of them as:
- How big is the ellipse? (`a` — semi-major axis)
- How squished is it? (`e` — eccentricity, 0 = circle)
- How tilted? (`i` — inclination)
- Which way is it tilted? (`Ω` — RAAN)
- Where's the closest point? (`ω` — argument of perigee)
- Where is the satellite right now on the ellipse? (`ν` — true anomaly)

Alternatively, you can just say: "it's at position (x, y, z) moving at velocity (vx, vy, vz)." Same information, different format. The code converts between these constantly.

### Why orbits aren't perfect ellipses

Three things mess up the clean ellipse:

1. **Earth is fat at the equator** (J2): The extra mass near the equator pulls satellites slightly differently depending on latitude. This makes the orbital plane slowly spin like a top.

2. **Air drag**: Even at 400 km altitude, there are a few air molecules. At 28,000 km/h, they add up. Drag slowly lowers the orbit until the satellite burns up.

3. **Sunlight pressure**: Photons from the Sun literally push on the satellite. Tiny force, but it accumulates.

The code integrates all these forces numerically (RK method — tiny time steps, very accurate).

### The uncertainty problem

We don't know EXACTLY where a satellite is. Tracking stations measure it, but there's always error. We represent this uncertainty as a **covariance matrix** — a 6×6 grid of numbers saying "position could be off by X in this direction, Y in that direction, and these errors are correlated."

Crucially: **uncertainty grows over time**. A satellite we tracked yesterday has bigger position uncertainty today. The code propagates this uncertainty forward using the State Transition Matrix (STM).

---

## Step 2: Finding Potential Collisions (`conjunction.py`)

### The problem: too many pairs

With 10,000 objects, there are ~50 million possible collision pairs. You can't thoroughly check all of them. So we filter:

**Quick geometric check**: If satellite A never goes above 500 km and satellite B never goes below 600 km, they can't meet. This eliminates most pairs instantly.

**Coarse scan**: For remaining pairs, propagate both forward in time, check distance every few minutes. Flag any pair that gets within 5 km.

**Refined analysis**: For flagged pairs, find the exact moment of closest approach (TCA) and compute the actual collision probability.

### How collision probability works (the key insight)

At the moment of closest approach, imagine you're riding on satellite A, looking at satellite B approaching. B is coming at you at some relative speed (could be 7-15 km/s in LEO — that's a bullet speed × 20).

Now, the encounter happens so fast (milliseconds of danger) that you can treat it as a 2D problem in the plane perpendicular to B's approach direction. This is the **encounter plane**.

In this plane, you have:
- A **miss vector**: where B's center will pass relative to A's center (e.g., "0.3 km to the left, 0.1 km above")
- A **combined uncertainty blob**: a stretched-out Gaussian (bell curve in 2D) representing where B *might actually be*
- A **collision circle**: if their centers get within R₁ + R₂ (sum of their physical sizes), they hit

The probability of collision = the integral of the Gaussian over the collision circle:

```
Pc = ∫∫(circle) bell_curve(x, y) dx dy
```

If Pc > 10⁻⁴ (1 in 10,000 chance), that's considered dangerous enough to maneuver.

---

## Step 3: Dodging (`avoidance.py`)

### The physics of dodging

You fire a thruster, changing your velocity by a tiny amount (Δv). This doesn't immediately move you — but over time, your path diverges from where it would have been.

The key question: **"If I burn Δv now, how much does my position change at the encounter?"**

The answer is the STM's upper-right block (Φ_rv):
```
position_change_at_encounter = Φ_rv × velocity_change_now
```

This 3×3 matrix tells you exactly how effective each burn direction is.

### Optimal burn direction

You want to push the miss vector *away* from the collision circle as efficiently as possible. The math says:

```
best_direction = Φ_rvᵀ × miss_direction  (then normalize)
```

This finds the Δv direction that moves the encounter point the most for the least fuel.

### Timing matters

Earlier burns are almost always better. Think of it like steering a ship — a small rudder adjustment now creates a big course change by the time you reach the iceberg. A last-second turn barely helps.

Rule of thumb the code uses: 1 cm/s of Δv applied one orbit early → ~100 meters of miss distance change.

### Fuel is precious

A typical small satellite has 25 m/s of Δv total — for its ENTIRE lifetime (years of operations). Each avoidance maneuver might cost 0.5-5 m/s. You can't dodge everything. The code decides:

- **Pc > 10⁻⁴**: Maneuver (dangerous enough to justify fuel cost)
- **Pc 10⁻⁵ to 10⁻⁴**: Maybe maneuver (depends on fuel remaining)
- **Pc < 10⁻⁵**: Accept the risk (save fuel for worse threats)

---

## Step 4: When You Can't Dodge (`damage_minimization.py`)

### Why collisions are so destructive

At 10 km/s relative velocity, kinetic energy is enormous. The energy per kilogram of target:

```
E = ½ × m_projectile × v² / m_target
```

A 10 kg object hitting a 300 kg satellite at 10 km/s:
```
E = 0.5 × 10 × (10,000)² / 300 = 1,670,000 J/kg
```

The catastrophic threshold is only 40,000 J/kg. This collision exceeds it by 40×. Both objects shatter completely.

### The NASA breakup model

From hypervelocity impact experiments, NASA determined that fragment count follows a power law:
```
N(bigger than size L) = 0.1 × M^0.75 × L^(-1.71)
```

For our 310 kg collision: ~360 fragments larger than 10 cm (trackable), ~18,000 fragments larger than 1 cm (lethal but hard to track).

### Five ways to reduce damage

The code evaluates these from "free" to "expensive":

**1. Turn sideways (0 fuel):** Present your thinnest edge to the impact. Reduces both the chance of being hit and the damage if hit. Like turning a book edge-on to a thrown ball instead of showing the flat cover.

**2. Make it a glancing blow (tiny fuel):** Instead of a head-on crash, deflect slightly so objects barely clip each other. A 15° glancing angle reduces effective impact energy by 93%. Think: a car sideswipe vs. a head-on collision.

**3. Slow down the approach (moderate fuel):** Fragment count scales with v^0.5, so reducing relative velocity helps. But in LEO, relative velocities are huge (7-15 km/s) and you typically only have a few m/s of fuel — like trying to slow a bullet with a hand fan.

**4. Push the collision lower (significant fuel):** If collision MUST happen, make it happen at low altitude where atmospheric drag will clean up the debris in months rather than centuries. Below 400 km = debris gone within a year. Above 800 km = debris lasts forever.

**5. Sacrifice the spacecraft (extreme fuel):** Deorbit entirely before the collision. No spacecraft = no collision. But you lose the mission.

---

## Step 5: The Big Brain Decision (`risk_optimizer.py`)

### The real problem is sequential

You don't face ONE conjunction — you face hundreds simultaneously, involving the same spacecraft, sharing fuel budgets. And decisions interact:
- Maneuvering spacecraft A to dodge object B might push A toward object C
- Spending fuel now means less fuel for future (unknown) threats
- A collision creates debris that generates NEW conjunctions

### The graph model

Think of the constellation as a social network:
- Each spacecraft is a person
- Each conjunction is a connection between two people
- Connection strength = collision risk

**Clusters**: Groups of spacecraft with interconnected risks. One well-placed maneuver might resolve an entire cluster.

**Cascade modeling**: If A and B collide, debris threatens C, D, E. If debris hits C, MORE debris threatens F, G... This branching tree is the Kessler syndrome.

### Kessler Syndrome (the nightmare scenario)

For each altitude band, the code checks:
```
Are we generating debris faster than drag removes it?
```

If yes, that altitude becomes a self-sustaining minefield even without new launches. Currently, 800-1000 km is dangerously close to this threshold.

### Three optimization strategies

**Greedy** (simple): Handle the scariest conjunction first. Then re-evaluate. Then the next scariest. Fast, simple, good enough for small problems.

**Network flow** (smart): Model the whole problem as a graph and solve "minimize total risk subject to fuel budgets" as an optimization problem. Better than greedy when maneuvers interact.

**Monte Carlo Tree Search** (AI): Same algorithm that beat humans at Go. Explores thousands of possible "what if I maneuver A first, then B, then..." sequences, evaluating each by random simulation to the end. Finds near-optimal solutions for problems too complex for exact methods.

---

## Step 6: Running It All (`simulation.py`)

Creates a synthetic constellation, then runs the full pipeline:

```
Generate 20 spacecraft (mix of types)
    ↓
Screen all pairs for close approaches (24-hour window)
    ↓
For each flagged pair: compute Pc
    ↓
For high-Pc events: plan avoidance maneuvers
    ↓
For unavoidable events: evaluate damage strategies
    ↓
Run global optimizer across all conjunctions
    ↓
Generate visualizations
```

---

## The Physical Intuition Summary

| Concept | Everyday Analogy |
|---------|-----------------|
| Orbit | Ball on a string — always falling inward, always moving sideways |
| Covariance | "I think the car is in lane 2, but it might be in lane 1 or 3" |
| Conjunction screening | Checking which highway lanes might merge ahead |
| Probability of collision | "Given the uncertainty, what are the odds they're in the same spot?" |
| STM / maneuver planning | "If I turn the wheel 2° now, where will I be in 5 minutes?" |
| Δv budget | Gas tank — very small, has to last years |
| Catastrophic threshold | Difference between a fender-bender and a total wreck |
| Kessler syndrome | One crash causes more crashes causes more crashes (chain reaction) |
| MCTS optimizer | Chess AI exploring "if I do this, then they do that, then..." trees |

The fundamental tension of the whole system: **fuel is finite, threats are infinite, and every decision has consequences for the future.** That's what makes it an AI problem rather than a simple physics calculation.