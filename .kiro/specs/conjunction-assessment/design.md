# Design Document: Conjunction Assessment

## Overview

The Conjunction Assessment module is the critical second level of the space situational awareness decision hierarchy. It screens thousands of spacecraft pairs for potential collisions using O(N²) all-vs-all analysis with progressive geometric filters, then applies rigorous statistical methods to quantify collision risk. For flagged pairs, the system determines the Time of Closest Approach (TCA), computes 3D miss distance, projects uncertainties into the encounter plane (perpendicular to relative velocity), and calculates Probability of Collision (Pc) via 2D Gaussian integration. The result is a ranked list of conjunction events with statistical confidence, enabling downstream maneuver planning to focus on real threats.

**Key Design Principle**: Transform raw screening data (all pairs under 5 km) into actionable risk information (Pc values with validated uncertainty) by layering geometric elimination, sophisticated propagation, and rigorous statistical analysis.

---

## Architecture

The conjunction assessment pipeline flows from detection through statistical quantification:

```mermaid
graph TD
    A["Screening<br/>All-vs-All Pairs"] --> B["Geometric Filters<br/>Apogee/Perigee, Planes"]
    B --> C["Coarse Distance<br/>Ephemeris Scan"]
    C --> D["Refine TCA<br/>Bracketed Search"]
    D --> E["Encounter Plane<br/>Geometry"]
    E --> F["Covariance<br/>Projection"]
    F --> G["Probability of<br/>Collision Calc"]
    G --> H["Risk Scoring<br/>& Output"]
    
    A -.->|O(N²)/2| I["~50M pairs<br/>for N=10k"]
    C -.->|filters reduce| J["~1000 flagged<br/>conjunctions"]
    H --> K["Ranked<br/>Conjunction<br/>List"]
    
    style A fill:#e1f5ff
    style B fill:#fff3e0
    style C fill:#fff3e0
    style D fill:#e8f5e9
    style E fill:#f3e5f5
    style F fill:#f3e5f5
    style G fill:#fce4ec
    style H fill:#e0f2f1
```

### Detailed Workflow

1. **Screening Phase** (O(N²) reduction):
   - All-vs-all pair enumeration
   - Apogee/Perigee orbital shell overlap test → eliminate parallel orbits
   - Coplanar filter (relative inclination check) → eliminate non-intersecting planes
   - Coarse distance threshold (5 km) along coarse ephemeris → flag candidates

2. **TCA Refinement Phase**:
   - For each flagged pair, bracket the minimum distance
   - Use bounded optimization (Brent's method) to refine TCA to ~0.1 second precision
   - Compute 3D miss distance at TCA

3. **Encounter Plane Phase**:
   - Establish orthonormal basis: encounter plane perpendicular to relative velocity
   - Project 3D miss vector into 2D encounter plane
   - Transform combined position uncertainty into encounter plane coordinates

4. **Probability Calculation Phase**:
   - Integrate 2D Gaussian hard-body probability over collision disk (Alfriend/Akella method)
   - Use eigendecomposition and polar coordinate numerical integration
   - Output Pc ∈ [0, 1] with high confidence

5. **Risk Scoring Phase**:
   - Combine Pc with object mass, relative velocity, and debris cascade potential
   - Assign risk scores for maneuver prioritization
   - Return ranked conjunction list

---

## Components and Interfaces

### 1. Geometric Filters

**Purpose**: Eliminate impossible encounters using fast orbital geometry checks. Reduces O(N²) pairing workload by 95%+ in typical LEO constellations.

**Interface**:
```python
def apogee_perigee_filter(sc1: Spacecraft, sc2: Spacecraft, 
                           threshold_km: float = 50.0) -> bool:
    """
    Quick geometric filter: objects can only meet if their orbital shells overlap.
    
    Returns True if conjunction geometrically possible (not filtered out).
    """

def coplanar_filter(sc1: Spacecraft, sc2: Spacecraft,
                     max_relative_inclination_deg: float = 5.0) -> bool:
    """
    Filter based on relative orbital plane geometry.
    
    Objects in very different planes with non-intersecting altitude bands
    are unlikely to have close approaches.
    
    Returns True if conjunction possible (not filtered out).
    """
```

**Responsibilities**:
- Compute orbital elements from state vectors (via state_to_coe)
- Check apogee/perigee overlap with user-specified margin
- Compute relative inclination using spherical geometry
- Return boolean pass/fail for each filter
- No false negatives: never eliminate real conjunctions

**Performance**: ~1 microsecond per pair (negligible compared to propagation)

---

### 2. Coarse Ephemeris Screening

**Purpose**: Generate low-resolution satellite trajectories and find minimum distance candidates for TCA refinement.

**Interface**:
```python
def screen_conjunctions(spacecraft_list: List[Spacecraft],
                        time_window: float = 86400.0,
                        distance_threshold: float = 5.0,
                        time_steps: int = 100) -> List[Tuple[int, int, float, float]]:
    """
    Screen all spacecraft pairs for potential conjunctions.
    
    Applies progressive filters and returns:
      (idx1, idx2, tca_approx, min_distance)
    
    for each flagged pair.
    """
```

**Responsibilities**:
- Generate ephemerides with ~1 km/point accuracy (coarse)
- Apply all geometric filters
- Find global minima below distance threshold
- Return approximate TCA for refinement
- Handle propagation failures gracefully (skip object)

**Performance**: ~1-10 ms per pair (dominated by propagation)

---

### 3. TCA Refinement Solver

**Purpose**: Find the precise time and distance of closest approach using bounded optimization.

**Interface**:
```python
def find_tca(state1: StateVector, state2: StateVector,
             t_guess: float, search_window: float = 600.0,
             cd1: float = 2.2, cd2: float = 2.2,
             am1: float = 0.01, am2: float = 0.01) -> Tuple[float, float]:
    """
    Refine the Time of Closest Approach between two objects.
    
    Minimizes |r1(t) - r2(t)| around initial guess using bounded optimization.
    
    Returns:
      (tca_refined, miss_distance)
    """

def find_all_close_approaches(state1: StateVector, state2: StateVector,
                              time_window: float = 86400.0,
                              threshold_km: float = 10.0,
                              n_samples: int = 500) -> List[Tuple[float, float]]:
    """
    Find all close approaches in a time window.
    
    Objects in LEO can have multiple close approaches per day (orbit crossings).
    
    Returns list of (tca, miss_distance) tuples.
    """
```

**Responsibilities**:
- Use scipy minimize_scalar with bounded method
- Precision: 0.1 second TCA accuracy
- Handle local minima (multiple close approaches per pair)
- Return both TCA and corresponding miss distance
- Efficient: converges in 10-50 function evaluations

**Performance**: ~100 ms per conjunction to refine TCA

---

### 4. Encounter Plane Analyzer

**Purpose**: Establish the collision geometry frame and project uncertainties into it. All Pc calculations operate in this 2D plane.

**Interface**:
```python
def compute_encounter_plane(state1_tca: StateVector, state2_tca: StateVector) \
        -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
    """
    Compute encounter plane basis vectors and miss vector projection.
    
    The encounter plane is perpendicular to the relative velocity at TCA.
    
    Returns:
      (miss_vector_2d, basis_3x3, projection_matrix_2x3)
    """

def project_covariance_to_encounter_plane(cov1: np.ndarray, cov2: np.ndarray,
                                          projection_matrix: np.ndarray) \
        -> np.ndarray:
    """
    Project combined position covariance into 2D encounter plane.
    
    C_2D = P · (C1_pos + C2_pos) · Pᵀ
    
    Assumes independent errors (no correlation between objects).
    
    Returns 2×2 covariance matrix in encounter plane [km²].
    """
```

**Responsibilities**:
- Compute relative position and velocity at TCA
- Establish orthonormal encounter frame (x, y along plane; z = v_rel direction)
- Robustly handle edge cases (colinear states, very small relative velocities)
- Transform 3D covariances to 2D projection
- Return data in standardized form for Pc calculation

**Performance**: ~1 ms per conjunction

---

### 5. Probability of Collision Calculator

**Purpose**: Compute Pc using rigorous statistical integration over the 2D hard-body encounter disk.

**Interface**:
```python
def probability_of_collision_2d(miss_vector: np.ndarray,
                                covariance_2d: np.ndarray,
                                combined_radius: float) -> float:
    """
    Compute probability of collision using 2D Gaussian integral (Alfriend/Akella).
    
    Pc = (1/2π|C|^½) ∫∫_A exp(-½ xᵀ C⁻¹ x) dx dy
    
    where A is a circle of radius R centered at the miss vector.
    
    Returns Pc ∈ [0, 1].
    """

def compute_combined_radius(radius1_km: float, radius2_km: float,
                            margin_km: float = 0.01) -> float:
    """
    Combine effective radii of two objects for collision disk.
    
    Accounts for: physical size + tracking uncertainty margin + RCS model.
    
    Returns combined_radius [km].
    """
```

**Responsibilities**:
- Eigendecompose 2×2 covariance matrix (to principal axes)
- Set up 2D Gaussian distribution in encounter plane
- Numerically integrate probability over collision disk
- Handle near-singular covariances robustly
- Return value in [0, 1] with high numerical precision

**Method**: Polar coordinate integration over collision disk
- 50 radial grid points × 100 azimuthal points
- ~5000 PDF evaluations per Pc (accurate to 4+ significant figures)
- Total time: ~50 ms per conjunction

---

### 6. Risk Scorer

**Purpose**: Rank conjunctions for maneuver planning using composite risk metric.

**Interface**:
```python
def compute_risk_score(conjunction: Conjunction,
                       obj1: Spacecraft, obj2: Spacecraft,
                       altitude_km: float,
                       debris_lifetime_factor: float = 1.0) -> float:
    """
    Compute composite risk score combining probability and consequence.
    
    Risk = Pc × Consequence × Cascade_Factor
    
    where:
      Consequence = f(m1, m2, v_rel, altitude)
      Cascade_Factor = 1 + density(altitude) × debris_lifetime(altitude)
    
    Returns risk_score [0, ∞).
    """

def rank_conjunctions(conjunctions: List[Conjunction]) -> List[Conjunction]:
    """
    Sort conjunctions by risk score (descending).
    
    Returns ordered list for maneuver planning.
    """
```

**Responsibilities**:
- Combine Pc with object mass to estimate debris count
- Weight by relative velocity (higher impact → more debris)
- Apply cascade multiplier based on altitude and debris environment
- Return normalized scores for decision thresholds
- Handle ties by TCA ordering (sooner first)

**Performance**: ~1 μs per conjunction (after Pc computed)

---

## Data Models

### Conjunction

```python
@dataclass
class Conjunction:
    """A predicted close approach between two objects."""
    obj1_id: str
    obj2_id: str
    tca: float                          # Time of closest approach [s from epoch]
    miss_distance: float                # Minimum distance [km]
    relative_velocity: float            # Relative speed at TCA [km/s]
    probability_of_collision: float     # Pc ∈ [0, 1]
    combined_covariance_2d: Optional[np.ndarray]  # 2×2 in encounter plane [km²]
    risk_score: float = 0.0             # Composite rank score
```

**Validation Rules**:
- `0 ≤ probability_of_collision ≤ 1`
- `miss_distance ≥ 0`
- `relative_velocity ≥ 0`
- `tca > 0` (future event)
- `combined_covariance_2d` is positive semi-definite (eigenvalues ≥ 0)

### Spacecraft

```python
@dataclass
class Spacecraft:
    """A spacecraft with physical and operational properties."""
    id: str
    state: StateVector              # ECI position [km] & velocity [km/s]
    covariance: np.ndarray          # 6×6 state covariance matrix
    mass: float                     # [kg]
    area: float                     # Cross-sectional area [m²]
    cd: float = 2.2                 # Drag coefficient
    cr: float = 1.5                 # Reflectivity coefficient
    delta_v_budget: float = 25.0    # Remaining Δv [m/s]
    maneuverable: bool = True       # Can execute maneuvers
    name: str = ""
```

**Validation Rules**:
- `mass > 0`
- `area > 0`
- `cd > 0`, typically 1.5–2.5
- `delta_v_budget ≥ 0`
- `covariance` is 6×6 symmetric positive semi-definite

### StateVector

```python
@dataclass
class StateVector:
    """Cartesian state vector in ECI frame."""
    r: np.ndarray  # Position [km] (3,)
    v: np.ndarray  # Velocity [km/s] (3,)
```

---

## Algorithmic Pseudocode with Formal Specifications

### Algorithm 1: All-vs-All Conjunction Screening

```pascal
ALGORITHM screenConjunctions(spacecraftList, timeWindow, distanceThreshold)
  INPUT: spacecraftList ← list of Spacecraft objects
         timeWindow ← time horizon [seconds]
         distanceThreshold ← flag threshold [km]
  OUTPUT: flaggedPairs ← list of (idx1, idx2, tca, miss_distance)

  PRECONDITION:
    - spacecraftList is not empty
    - Each spacecraft has valid state and covariance
    - timeWindow > 0
    - distanceThreshold > 0

  POSTCONDITION:
    - flaggedPairs contains all pairs with min_dist < distanceThreshold
    - For each pair: tca is within [0, timeWindow]
    - No duplicates (i, j) with i < j
    - All entries sorted by miss_distance ascending

  BEGIN
    N ← length(spacecraftList)
    flaggedPairs ← empty list
    
    // Generate coarse ephemerides for all objects
    LOOP FOR i FROM 0 TO N-1 DO
      ephemerides[i] ← generateEphemeris(
        spacecraftList[i].state, timeWindow, nSteps=100
      )
      ASSERT length(ephemerides[i]) = 100
    END LOOP
    
    // All-vs-all screening with progressive filters
    LOOP FOR i FROM 0 TO N-1 DO
      LOOP FOR j FROM i+1 TO N-1 DO
        // Filter 1: Geometric shell overlap
        IF NOT apogeePerigeeFilter(spacecraftList[i], spacecraftList[j]) THEN
          CONTINUE  // No conjunction possible geometrically
        END IF
        
        // Filter 2: Orbital plane intersection
        IF NOT coplanarFilter(spacecraftList[i], spacecraftList[j]) THEN
          CONTINUE  // Planes don't intersect
        END IF
        
        // Filter 3: Coarse distance check
        distances ← computeDistances(ephemerides[i], ephemerides[j])
        ASSERT length(distances) = 100
        
        minDist ← minimum(distances)
        minDistIdx ← index of minimum
        
        IF minDist < distanceThreshold THEN
          tcaApprox ← timeWindow × (minDistIdx / 100)
          // Refine TCA
          tcaRefined, missRefined ← findTCA(
            spacecraftList[i].state, spacecraftList[j].state, tcaApprox
          )
          ASSERT 0 ≤ missRefined
          APPEND (i, j, tcaRefined, missRefined) TO flaggedPairs
        END IF
      END LOOP
    END LOOP
    
    // Sort by miss distance
    flaggedPairs ← sort(flaggedPairs, key=miss_distance)
    
    RETURN flaggedPairs
  END

  LOOP INVARIANTS:
    - All pairs checked so far satisfy i < j
    - flaggedPairs contains only pairs with min_dist < distanceThreshold
    - Each flagged pair has passed both geometric filters
```

### Algorithm 2: Time of Closest Approach Refinement

```pascal
ALGORITHM findTCA(state1, state2, tGuess, searchWindow)
  INPUT: state1, state2 ← StateVector objects at t=0
         tGuess ← approximate TCA [seconds]
         searchWindow ← search interval around guess [seconds]
  OUTPUT: tca ← refined TCA [seconds]
          missDistance ← minimum distance [km]

  PRECONDITION:
    - state1, state2 are valid StateVectors
    - tGuess ≥ 0
    - searchWindow > 0
    - tGuess - searchWindow ≥ 0 (or handled gracefully)

  POSTCONDITION:
    - tca is within [tGuess - searchWindow, tGuess + searchWindow]
    - missDistance = |r1(tca) - r2(tca)|
    - tca minimizes distance over search interval (within 0.1 second precision)

  BEGIN
    // Bounded optimization bracket
    tMin ← max(0, tGuess - searchWindow)
    tMax ← tGuess + searchWindow
    
    ASSERT tMin ≤ tGuess ≤ tMax
    ASSERT tMax - tMin = 2 × searchWindow
    
    // Minimization loop
    result ← boundedMinimize(
      objectiveFunc = LAMBDA t: distance(state1, state2, t),
      bounds = [tMin, tMax],
      method = "bounded",
      tolerance = 0.1  // seconds
    )
    
    tca ← result.x  // Optimal time
    missDistance ← result.fun  // Minimum distance value
    
    ASSERT tMin ≤ tca ≤ tMax
    ASSERT missDistance ≥ 0
    
    RETURN tca, missDistance
  END
```

### Algorithm 3: Encounter Plane Geometry

```pascal
ALGORITHM computeEncounterPlane(state1_tca, state2_tca)
  INPUT: state1_tca, state2_tca ← states at TCA
  OUTPUT: missVector2d ← projected miss vector [km]
          basis ← orthonormal frame [3×3]
          projectionMatrix ← 3D to 2D projector [2×3]

  PRECONDITION:
    - state1_tca, state2_tca are valid StateVectors
    - relative velocity is non-zero (objects approaching)

  POSTCONDITION:
    - basis is orthonormal (columns are unit vectors)
    - projectionMatrix has rows that form orthonormal basis in encounter plane
    - missVector2d has 2 components (x, y in encounter plane)
    - |v_rel| = 1 in basis[2] direction

  BEGIN
    // Relative motion
    deltaR ← state1_tca.r - state2_tca.r     // Miss vector (3D)
    deltaV ← state1_tca.v - state2_tca.v     // Relative velocity
    
    vRelMag ← magnitude(deltaV)
    ASSERT vRelMag > 0
    
    // Encounter plane normal: along relative velocity
    zHat ← deltaV / vRelMag
    
    // Component of miss vector in encounter plane
    deltaRProj ← deltaR - dot(deltaR, zHat) × zHat
    projMag ← magnitude(deltaRProj)
    
    // First basis vector in plane
    IF projMag > 1e-10 THEN
      xHat ← deltaRProj / projMag
    ELSE
      // Miss vector aligned with v_rel — choose arbitrary perpendicular
      arbitrary ← [1, 0, 0] IF |zHat[0]| < 0.9 ELSE [0, 1, 0]
      xHat ← cross(zHat, arbitrary)
      xHat ← xHat / magnitude(xHat)
    END IF
    
    // Complete orthonormal system
    yHat ← cross(zHat, xHat)
    
    // Basis matrix (rows are orthonormal)
    basis ← [xHat; yHat; zHat]
    ASSERT all(|basis[i]| = 1 for i in 0..2)  // Unit vectors
    ASSERT orthogonal(basis[i], basis[j] for i ≠ j)  // Orthogonal
    
    // Projection to 2D
    projectionMatrix ← [xHat; yHat]  // 2×3 matrix
    
    // Miss vector in encounter plane
    missVector2d ← projectionMatrix × deltaR
    ASSERT length(missVector2d) = 2
    
    RETURN missVector2d, basis, projectionMatrix
  END

  INVARIANTS:
    - zHat always points in direction of relative velocity
    - xHat, yHat span encounter plane (perpendicular to zHat)
    - projectionMatrix × zHat = [0, 0] (zero in encounter plane)
```

### Algorithm 4: Probability of Collision Computation

```pascal
ALGORITHM probabilityOfCollision2d(missVector, covariance2d, combinedRadius)
  INPUT: missVector ← 2D miss vector in encounter plane [km]
         covariance2d ← 2×2 combined position covariance [km²]
         combinedRadius ← collision disk radius [km]
  OUTPUT: Pc ← probability of collision ∈ [0, 1]

  PRECONDITION:
    - missVector is 2D
    - covariance2d is 2×2 symmetric
    - covariance2d is positive semi-definite (all eigenvalues ≥ 0)
    - combinedRadius > 0

  POSTCONDITION:
    - 0 ≤ Pc ≤ 1
    - Pc = 0 if miss vector >> covariance (collision disk far from center)
    - Pc ≈ 1 if combined_radius >> σ (large collision disk, small uncertainty)

  BEGIN
    // Eigendecomposition to principal axes
    eigenvalues, eigenvectors ← eig(covariance2d)
    ASSERT length(eigenvalues) = 2
    
    // Ensure positive definite (numerical robustness)
    eigenvalues ← max(eigenvalues, 1e-10)
    
    sigmaX ← sqrt(eigenvalues[0])
    sigmaY ← sqrt(eigenvalues[1])
    
    ASSERT sigmaX > 0 AND sigmaY > 0
    
    // Transform miss vector to principal axes
    missRotated ← transpose(eigenvectors) × missVector
    xm ← missRotated[0]
    ym ← missRotated[1]
    
    // Numerical integration in polar coordinates
    // Pc = ∫₀²π ∫₀ᴿ (1/(2π·σx·σy)) exp(-½[(x-xm)²/σx² + (y-ym)²/σy²]) r dr dθ
    
    R ← combinedRadius
    nR ← 50  // Radial grid points
    nTheta ← 100  // Azimuthal points
    
    rVals ← linspace(0, R, nR)
    thetaVals ← linspace(0, 2π, nTheta)
    
    dr ← rVals[1] - rVals[0] IF nR > 1 ELSE R
    dTheta ← thetaVals[1] - thetaVals[0]
    
    // Integrate over collision disk
    Pc ← 0
    LOOP FOR r IN rVals[1:] DO  // Skip r=0
      LOOP FOR theta IN thetaVals[:-1] DO
        // Cartesian coordinates in principal axes
        x ← r × cos(theta)
        y ← r × sin(theta)
        
        // Gaussian PDF in principal axes
        exponent ← -0.5 × ((x - xm)² / sigmaX² + (y - ym)² / sigmaY²)
        pdf ← exp(exponent) / (2π × sigmaX × sigmaY)
        
        // Jacobian: r dr dθ
        Pc ← Pc + pdf × r × dr × dTheta
      END LOOP
    END LOOP
    
    ASSERT 0 ≤ Pc ≤ 1
    
    RETURN Pc
  END

  LOOP INVARIANTS:
    - All r, theta values within bounds [0, R] × [0, 2π]
    - pdf values are non-negative
    - Partial Pc always monotonically increasing (only accumulating positive terms)
```

---

## Key Functions with Formal Specifications

### Function: screen_conjunctions()

```python
def screen_conjunctions(spacecraft_list: List[Spacecraft],
                        time_window: float = 86400.0,
                        distance_threshold: float = 5.0,
                        time_steps: int = 100) -> List[Tuple[int, int, float, float]]:
```

**Preconditions**:
- `len(spacecraft_list) ≥ 2`
- All spacecraft have valid state vectors (3D position and velocity)
- All spacecraft have 6×6 covariance matrices
- `time_window > 0`
- `distance_threshold > 0`
- `time_steps ≥ 10`

**Postconditions**:
- Returns list of tuples `(i, j, tca, miss_distance)` with `i < j`
- For each returned pair: `miss_distance < distance_threshold`
- Times are within `[0, time_window]`
- Miss distances are all ≥ 0
- No duplicate pairs

**Side Effects**: None (read-only on spacecraft_list)

---

### Function: find_tca()

```python
def find_tca(state1: StateVector, state2: StateVector,
             t_guess: float, search_window: float = 600.0) -> Tuple[float, float]:
```

**Preconditions**:
- `state1`, `state2` are valid StateVector objects
- `t_guess ≥ 0`
- `search_window > 0`
- `t_guess - search_window ≥ 0` (or will be clamped to 0)

**Postconditions**:
- Returned `tca ≥ max(0, t_guess - search_window)`
- Returned `miss_distance ≥ 0`
- `miss_distance` is the minimum within the search window
- Precision: TCA accurate to ~0.1 seconds

**Side Effects**: None

---

### Function: compute_encounter_plane()

```python
def compute_encounter_plane(state1_tca: StateVector, 
                            state2_tca: StateVector) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
```

**Preconditions**:
- Both states are valid StateVectors
- Relative velocity magnitude > 1e-10 km/s (objects approaching)

**Postconditions**:
- Returned basis is 3×3 orthonormal matrix
- Returned projection_matrix is 2×3 with orthonormal rows
- miss_vector_2d has exactly 2 components
- basis @ basis.T ≈ I (orthogonal to machine precision)

**Side Effects**: None

---

### Function: probability_of_collision_2d()

```python
def probability_of_collision_2d(miss_vector: np.ndarray,
                                covariance_2d: np.ndarray,
                                combined_radius: float) -> float:
```

**Preconditions**:
- `miss_vector` is 1D array of length 2
- `covariance_2d` is 2×2 symmetric positive semi-definite
- `combined_radius > 0`

**Postconditions**:
- Returns float in range `[0.0, 1.0]`
- Pc = 0 if miss >> radius (collision unlikely)
- Pc ≈ 1 if combined_radius >> σ (collision almost certain)
- Accuracy: ≥ 4 significant figures (from 50×100 grid)

**Side Effects**: None

---

## Example Usage

```python
import numpy as np
from conjunction import (
    screen_conjunctions, find_tca, 
    compute_encounter_plane, probability_of_collision_2d
)
from utils import StateVector, Spacecraft, Conjunction

# Create a simple constellation of 3 objects
spacecraft = [
    Spacecraft(
        id="SAT-001",
        state=StateVector(
            r=np.array([6678.0, 0.0, 0.0]),
            v=np.array([0.0, 7.54, 0.0])
        ),
        covariance=np.eye(6) * 1e-4,  # 0.01 km position uncertainty
        mass=500.0,
        area=10.0
    ),
    Spacecraft(
        id="SAT-002",
        state=StateVector(
            r=np.array([6678.5, 0.0, 0.0]),
            v=np.array([0.0, 7.53, 0.0])
        ),
        covariance=np.eye(6) * 1e-4,
        mass=500.0,
        area=10.0
    ),
    Spacecraft(
        id="SAT-003",
        state=StateVector(
            r=np.array([7000.0, 0.0, 0.0]),
            v=np.array([0.0, 7.35, 0.0])
        ),
        covariance=np.eye(6) * 1e-4,
        mass=500.0,
        area=10.0
    ),
]

# Screen for conjunctions over 1 day (86400 seconds)
flagged_pairs = screen_conjunctions(
    spacecraft,
    time_window=86400.0,
    distance_threshold=5.0,
    time_steps=100
)

print(f"Flagged {len(flagged_pairs)} potential conjunctions")

# Process first flagged pair
if flagged_pairs:
    idx1, idx2, tca_approx, miss_coarse = flagged_pairs[0]
    
    print(f"Pair: {spacecraft[idx1].id} vs {spacecraft[idx2].id}")
    print(f"  Approximate TCA: {tca_approx:.1f} s")
    print(f"  Coarse miss distance: {miss_coarse:.3f} km")
    
    # Refine TCA
    tca_refined, miss_refined = find_tca(
        spacecraft[idx1].state,
        spacecraft[idx2].state,
        t_guess=tca_approx,
        search_window=600.0
    )
    print(f"  Refined TCA: {tca_refined:.1f} s")
    print(f"  Refined miss distance: {miss_refined:.3f} km")
    
    # Propagate to TCA
    from orbital_mechanics import propagate_state
    state1_tca = propagate_state(spacecraft[idx1].state, tca_refined)
    state2_tca = propagate_state(spacecraft[idx2].state, tca_refined)
    
    # Compute encounter plane
    miss_2d, basis, proj_matrix = compute_encounter_plane(state1_tca, state2_tca)
    print(f"  Miss vector (2D encounter plane): {miss_2d}")
    
    # Project covariance to encounter plane
    from conjunction import project_covariance_to_encounter_plane
    cov_2d = project_covariance_to_encounter_plane(
        spacecraft[idx1].covariance,
        spacecraft[idx2].covariance,
        proj_matrix
    )
    
    # Combined effective radius (5 cm + 5 cm = 10 cm = 0.001 km)
    combined_radius = 0.001
    
    # Calculate Pc
    Pc = probability_of_collision_2d(miss_2d, cov_2d, combined_radius)
    print(f"  Probability of Collision: {Pc:.2e}")
    
    # Create conjunction record
    conjunction = Conjunction(
        obj1_id=spacecraft[idx1].id,
        obj2_id=spacecraft[idx2].id,
        tca=tca_refined,
        miss_distance=miss_refined,
        relative_velocity=np.linalg.norm(state1_tca.v - state2_tca.v),
        probability_of_collision=Pc,
        combined_covariance_2d=cov_2d
    )
    
    print(f"\nConjunction record: {conjunction}")
```

**Expected Output**:
```
Flagged 2 potential conjunctions
Pair: SAT-001 vs SAT-002
  Approximate TCA: 42000.5 s
  Coarse miss distance: 0.450 km
  Refined TCA: 42000.3 s
  Refined miss distance: 0.428 km
  Miss vector (2D encounter plane): [0.428 0.001]
  Probability of Collision: 3.14e-06
  Relative velocity at TCA: 0.0134 km/s
```

---

## Correctness Properties

### Property 1: Geometric Filters Never Eliminate Real Conjunctions

```python
# For any two spacecraft with overlapping orbital shells and intersecting planes:
# A conjunction at any distance < threshold should never be filtered out

∀ sc1, sc2, threshold:
  IF orbitalShellsOverlap(sc1, sc2) AND planesIntersect(sc1, sc2)
  THEN apogeePerigeeFilter(sc1, sc2) = True AND coplanarFilter(sc1, sc2) = True
```

**Validation**: Pass-through test with synthetic constellation (all filters disabled vs. enabled)

---

### Property 2: TCA Refinement Minimizes Distance

```python
# After refinement, the returned TCA must be a local minimum

∀ state1, state2, t_guess, search_window:
  tca, miss = findTCA(state1, state2, t_guess, search_window)
  
  THEN:
    distance(state1, state2, tca) ≤ distance(state1, state2, t_guess)
    AND distance(state1, state2, tca) ≤ distance(state1, state2, tca ± ε) ∀ε ∈ (-0.1, 0.1)
```

**Validation**: Perturbation tests around returned TCA

---

### Property 3: Encounter Plane Projection is Orthonormal

```python
# Projected covariance must be positive semi-definite (real eigenvalues ≥ 0)

∀ cov1, cov2 ∈ (6×6 PSD matrices):
  proj_matrix = projectToEncounterPlane(cov1, cov2)
  
  THEN:
    eigenvalues(proj_matrix) ≥ 0 (all non-negative)
    AND det(proj_matrix) ≥ 0 (determinant non-negative)
```

**Validation**: Check eigenvalues of returned covariance for 100 random conjunctions

---

### Property 4: Probability Bounds

```python
# Pc must be well-defined and bounded

∀ miss_vec, cov_2d, radius:
  Pc = probabilityOfCollision2d(miss_vec, cov_2d, radius)
  
  THEN:
    0 ≤ Pc ≤ 1
```

**Validation**: Property-based test with random inputs (Hypothesis or fast-check)

---

### Property 5: Pc Increases with Collision Disk Size

```python
# Larger combined radius => higher Pc (monotonicity)

∀ miss_vec, cov_2d, r1 < r2:
  Pc1 = probabilityOfCollision2d(miss_vec, cov_2d, r1)
  Pc2 = probabilityOfCollision2d(miss_vec, cov_2d, r2)
  
  THEN:
    Pc1 ≤ Pc2
```

**Validation**: Test with 10 increasing radii for fixed miss_vec, cov_2d

---

### Property 6: Pc Decreases with Distance from Disk Center

```python
# Larger miss distance => lower Pc (moving away from collision center)

∀ r_scales (∈ [0.5, 2.0]), cov_2d, radius:
  FOR each r_scale:
    miss_vec_scaled = miss_vec × r_scale
    Pc_scaled = probabilityOfCollision2d(miss_vec_scaled, cov_2d, radius)
  
  THEN:
    Pc_scaled is monotonically decreasing with r_scale
```

**Validation**: Scaling test with 5 scaling factors

---

### Property 7: No False Negatives Below Distance Threshold

```python
# If min distance < threshold in coarse screening, TCA refine must find something

∀ pairs flagged in screenConjunctions(threshold=T):
  THEN:
    findTCA(pair) returns miss_distance < T + margin (where margin is refinement tolerance)
```

**Validation**: End-to-end test comparing coarse vs. refined distances

---

## Error Handling

### Error Scenario 1: Singular Covariance (Near-Zero Uncertainty)

**Condition**: One or both covariance matrices have near-zero eigenvalues (numerical singularity)

**Response**: 
- Clamp eigenvalues to minimum threshold `1e-10` km²
- Emit warning to log
- Proceed with regularized covariance

**Recovery**: Pc will be computed using regularized (slightly inflated) uncertainty, producing conservative (higher) Pc estimates

---

### Error Scenario 2: Propagation Failure (e.g., Object Decayed)

**Condition**: Ephemeris generation fails (object no longer in orbit, integration diverged)

**Response**:
- Catch RuntimeError from propagator
- Log warning with spacecraft ID and failure reason
- Skip this object in all-vs-all pairing

**Recovery**: Continue screening remaining pairs. Operator should investigate failed propagation separately

---

### Error Scenario 3: Relative Velocity Nearly Zero

**Condition**: state1_tca.v ≈ state2_tca.v (objects in nearly identical orbit)

**Response**:
- Check relative velocity magnitude < 1e-10 km/s
- If true: raise ValueError("Relative velocity too small for encounter plane")

**Recovery**: Flag pair as "orbiting together" (extremely low Pc) and skip to next pair

---

### Error Scenario 4: Invalid Covariance (Not Positive Semi-Definite)

**Condition**: 2D encounter plane covariance has negative eigenvalue (indicates tracking data error)

**Response**:
- Eigendecomposition flags negative eigenvalue
- Clamp all negative eigenvalues to `1e-10`
- Emit warning

**Recovery**: Proceed with regularized covariance (conservative Pc estimate)

---

### Error Scenario 5: Search Window Too Small for TCA

**Condition**: Bracketed TCA search doesn't contain true minimum (search_window too narrow)

**Response**:
- Optimizer returns edge value (lower or upper bound)
- Check if result is within tolerance of bounds
- If so, double search window and retry

**Recovery**: Retry with expanded window (default handling)

---

## Testing Strategy

### Unit Testing Approach

**Test Coverage**:

1. **Geometric Filters**:
   - Test apogee/perigee filter with overlapping and non-overlapping orbits
   - Test coplanar filter with equatorial and inclined orbits
   - Verify no false negatives (all real conjunctions pass filters)

2. **TCA Refinement**:
   - Synthetic circular orbit pair with known TCA
   - Verify refined TCA within 0.1 seconds of analytical solution
   - Test multiple close approaches per pass

3. **Encounter Plane**:
   - Orthonormality check (basis matrix is orthonormal)
   - Projection invariance (projecting orthogonal directions returns [0,0])
   - Edge cases: colinear states, very small relative velocity

4. **Probability Calculation**:
   - Boundary conditions: Pc → 0 as miss_distance → ∞
   - Boundary conditions: Pc → 1 as combined_radius → ∞
   - Symmetry: shifting miss vector radially changes Pc monotonically

5. **Full Pipeline**:
   - End-to-end test with synthetic constellation
   - Known collision case (should return high Pc)
   - Known miss case (should return low Pc)

---

### Property-Based Testing Approach

**Property Test Library**: `hypothesis` (Python)

**Key Properties**:

| Property | Input Domain | Assertion |
|----------|--------------|-----------|
| Bounds | `Pc ∈ [0, 1]` | All returned probabilities in valid range |
| Monotonicity (radius) | `radius1 < radius2` | `Pc(radius1) ≤ Pc(radius2)` |
| Monotonicity (distance) | `dist1 < dist2` | `Pc(dist1) ≥ Pc(dist2)` |
| No NaN/Inf | Random inputs | No NaN or Inf in outputs |
| Idempotence | Run twice on same data | Identical results |
| Numerical Stability | Near-singular covariances | Graceful degradation (no crashes) |

---

### Integration Testing Approach

**Test Scenarios**:

1. **LEO Constellation Screening**:
   - 100 satellites in similar circular orbits
   - Expect ~50–100 conjunctions in 24 hours
   - Verify no duplicates, reasonable Pc distribution

2. **Multi-Pass Conjunctions**:
   - Two satellites with 2 close approaches per day
   - Verify both found and ranked correctly

3. **Covariance Evolution**:
   - Spacecraft with growing uncertainty (no new tracking)
   - Verify Pc increases over time (widening uncertainty)

4. **Cascade Risk Scenario**:
   - One satellite threatens two others in sequence
   - Verify maneuver planning sees both risks

---

## Performance Considerations

### Complexity Analysis

| Component | Complexity | Typical Time |
|-----------|-----------|--------------|
| All-vs-all enumeration | O(N²) | N=10k → 50M pairs |
| Apogee/perigee filter | O(1) per pair | ~1 μs |
| Coarse ephemeris screening | O(100 propagations) per pair | ~10 ms |
| Filters reduce workload | 95–99% | 50M → 10k–100k flagged |
| TCA refinement (optimizer) | ~10–50 iterations | ~100 ms per pair |
| Encounter plane computation | O(1) | ~1 ms |
| Covariance projection | O(1) | ~1 ms |
| Pc numerical integration | 50×100 grid | ~50 ms |
| **Total per conjunction (after coarse)** | — | ~150–300 ms |
| **Total per 1000 conjunctions** | — | ~2–5 minutes |

### Optimization Opportunities

- **Vectorize distances**: Compute all pairwise distances via NumPy (500× speedup)
- **Parallel screening**: Process object pairs on multiple cores (N_cores speedup)
- **Coarse Pc approximation**: Use faster 1D Gaussian for initial ranking, refine top K
- **Cached ephemerides**: Pre-compute 7-day ephemeris per object, reuse across all pairs

### Memory Requirements

| Structure | Size (N=10k) | Notes |
|-----------|-------------|-------|
| Spacecraft list | ~80 MB | 8 bytes/ID + 6×6 covariance + state |
| Ephemerides (coarse) | ~40 MB | 100 points × (3 pos + 3 vel) × 8 bytes × 10k |
| Flagged pairs buffer | ~1 MB | ~1000 conjunctions × 40 bytes each |
| **Total** | **~120 MB** | Easily fits in modern RAM |

---

## Security Considerations

### Input Validation

- **Covariance matrix**: Verify 6×6, symmetric, positive semi-definite (eigenvalue check)
- **State vectors**: Check finite (no NaN/Inf), magnitude reasonable for LEO (6000–7000 km radii)
- **Time values**: Ensure positive and within physically reasonable bounds (0 to 1 year)
- **Spacecraft count**: Limit to N ≤ 100,000 (prevent quadratic-time DOS)

### Numerical Stability

- **Covariance conditioning**: Regularize ill-conditioned matrices (add `1e-10 × I`)
- **Division by zero**: Guard against `1/sigma` operations with threshold checks
- **Exponential underflow**: Cap exponent arguments in Gaussian PDF to prevent underflow

### Data Integrity

- **Conjunction ordering**: Sort deterministically (miss_distance, then TCA, then IDs)
- **Pc reproducibility**: Set random seeds if using stochastic methods (currently deterministic)
- **Audit trail**: Log all flagged pairs, TCA refinements, and Pc calculations for verification

---

## Dependencies

### External Libraries

- **numpy**: Numerical arrays, linear algebra (eigendecomposition, projections)
- **scipy.optimize**: Bounded optimization (find_tca)
- **scipy.special**: Special functions (if using Gaussian CDF approximation)

### Internal Dependencies

- `orbital_mechanics.propagate_state()`: Propagate individual spacecraft
- `orbital_mechanics.generate_ephemeris()`: Generate coarse trajectories
- `orbital_mechanics.propagate_with_stm()`: Optional (for covariance propagation)
- `utils.StateVector, Spacecraft, Conjunction`: Data structures
- `utils.state_to_coe()`: Convert state to orbital elements
- `utils.eci_to_rtn()`: Convert to RTN frame (optional, for visualization)

### Implicit Assumptions

1. **ECI Frame**: All state vectors and covariances are in Earth-Centered Inertial frame
2. **Keplerian Dynamics**: Two-body problem (no high-fidelity perturbations like J2 in propagation)
3. **Independent Errors**: Position uncertainties of two objects are uncorrelated
4. **Non-relativistic**: Velocities << c (appropriate for LEO)
5. **Continuous Time**: Propagation uses continuous integration (not discrete updates)

