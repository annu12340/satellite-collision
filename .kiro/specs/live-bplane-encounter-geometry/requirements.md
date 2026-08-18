# Requirements Document: Live B-Plane Encounter Geometry

## Introduction

The B-plane (encounter plane) is the 2D plane through the secondary object, perpendicular to the relative velocity vector at closest approach. It is the actual mathematical object conjunction assessment is built on: probability-of-collision calculations integrate a Gaussian covariance distribution over a hard-body disk within this plane (see `compute_encounter_plane()` / `probability_of_collision_2d()` in `src/conjunction.py`, and `docs/physics.md`).

This feature adds a live-updating B-plane inset to the dashboard, rendered next to the existing telemetry and catastrophic-threshold panels. As a collision-scenario animation plays back (including an avoidance burn), the inset shows the hard-body-radius disk, the n-sigma covariance confidence ellipse, and the miss-distance vector, all updating frame-by-frame using the same encounter-plane projection math as the production conjunction-assessment pipeline — not a cosmetic approximation.

## Glossary

- **B-plane / encounter plane**: The 2D plane perpendicular to the relative velocity vector at TCA, in which conjunction-assessment Pc calculations are performed.
- **TCA**: Time of Closest Approach.
- **Miss vector**: The relative position vector (r1 - r2) projected into the B-plane, expressed in (ξ, ζ) coordinates.
- **HBR (Hard-Body Radius)**: The combined physical collision radius of both objects (sum of each object's effective radius).
- **Covariance ellipse**: The n-sigma (here 3σ) confidence region of the combined position uncertainty, projected into the B-plane and rendered as an ellipse via eigendecomposition.
- **Pc**: Probability of Collision — the likelihood the miss vector falls within the HBR disk given the uncertainty ellipse.
- **Scenario**: A precomputed collision/avoidance animation served by `/api/scenario/<id>` (e.g. `head_on_avoidance`, `catastrophic_collision`, `last_minute_save`).

## Requirements

### Requirement 1: Encounter-plane projection reuses production math

**User Story:** As a developer, I want the B-plane inset's geometry to come from the same routines the real conjunction-assessment pipeline uses, so the visualization is physically accurate rather than a cosmetic approximation.

#### Acceptance Criteria

1. THE System SHALL provide a reusable function (`build_bplane_projection`) that derives the B-plane basis and 3D→2D projection matrix from a representative pair of states at/near TCA, using the existing `compute_encounter_plane()` routine.
2. THE System SHALL provide a function (`project_relative_position_series`) that projects an entire time series of relative positions into 2D (ξ, ζ) B-plane coordinates using a single fixed projection matrix, so a burn's effect on the miss vector reads as continuous 2D motion rather than a discontinuous jump.
3. THE System SHALL provide a function (`covariance_ellipse_params`) that decomposes a 2×2 encounter-plane covariance matrix into semi-major/semi-minor axis lengths and rotation angle for a given confidence level (n-sigma), via eigendecomposition.
4. THE System SHALL provide a fast closed-form Pc approximation (`probability_of_collision_foster`) suitable for evaluating every animation frame, distinct from the numerical-integration `probability_of_collision_2d` used by the real decision pipeline.

### Requirement 2: Per-scenario B-plane time series

**User Story:** As a developer, I want each collision scenario to expose a precomputed B-plane time series, so the frontend can render live geometry without recomputing physics client-side.

#### Acceptance Criteria

1. WHEN a scenario is built (`_build_scenario` in `src/api.py`), THE System SHALL compute a `bplane` field containing, per animation frame: `miss_xi_km`, `miss_zeta_km`, `cov_semi_major_km`, `cov_semi_minor_km`, and `pc_estimate`.
2. THE `bplane` field SHALL also include scenario-constant values: `cov_angle_rad`, `combined_radius_km`, `cov_update_frame`, and `n_sigma`.
3. THE covariance ellipse SHALL step from a larger "before tracking refinement" size to a smaller "after refinement" size at `cov_update_frame`, aligned with the scenario's existing `covariance_update` event.
4. WHEN a scenario has an avoidance correction (`has_correction: true`), THE projected miss vector SHALL reflect the corrected trajectory from the maneuver frame onward, using the same fixed B-plane basis as the uncorrected portion.
5. THE `bplane` field SHALL be included in the response of `/api/scenario/<id>` and available to `/api/scenario/<id>/stream` consumers via the full scenario payload.

### Requirement 3: Live B-plane inset panel

**User Story:** As an operator, I want a dashboard panel showing the B-plane geometry live, so I can see the actual risk geometry conjunction assessment is built on, updating as an avoidance burn executes.

#### Acceptance Criteria

1. THE dashboard SHALL display a "B-Plane Encounter Geometry" panel in the left sidebar, containing a canvas render and readouts for the current miss vector, 3σ ellipse dimensions, combined HBR, and Pc estimate.
2. WHEN a scenario is running, THE panel SHALL update every animation frame to show: the hard-body-radius disk, the covariance confidence ellipse (correctly rotated and sized), and a vector from the secondary object (origin) to the primary object's projected position.
3. THE canvas rendering SHALL auto-scale so that the larger of (miss distance + ellipse extent) or a reasonable minimum fits within the visible plot area, keeping the geometry readable as the miss vector shrinks or grows.
4. THE panel SHALL show an idle/empty state (faint crosshair grid, placeholder readouts) before any scenario has been run, and reset to that state when a scenario is stopped or a new one starts.
5. THE panel's status badge SHALL reflect IDLE / LIVE state in sync with the existing telemetry and catastrophic-gauge panels.

## Non-Goals

- This feature does not change the production conjunction-assessment decision pipeline (`assess_conjunction`, `run_conjunction_screening`, `compute_collision_probability`), which continues to use the existing numerical-integration Pc calculation.
- Covariance inputs for the demo scenarios are procedurally generated for visualization purposes; they are not derived from real tracking data.
