# Implementation Tasks: Live B-Plane Encounter Geometry

Status: Implemented (fast-task workflow — implemented directly, spec recorded after the fact).

- [x] 1. Physics: reusable B-plane projection helpers (`src/conjunction.py`)
  - Add `build_bplane_projection(state1_ref, state2_ref)` — wraps `compute_encounter_plane()` to return the encounter-frame basis and 3D→2D projection matrix
  - Add `project_relative_position_series(positions1, positions2, projection_matrix)` — projects an (N, 3) relative-position time series into (N, 2) B-plane coordinates using one fixed basis
  - Add `covariance_ellipse_params(covariance_2d, n_sigma=3.0)` — eigendecomposes a 2x2 covariance into semi-major/semi-minor axes and rotation angle
  - Add `probability_of_collision_foster(miss_vector, covariance_2d, combined_radius)` — closed-form Pc approximation (Foster's method) for cheap per-frame evaluation, distinct from the numerical-integration `probability_of_collision_2d` used by the real decision pipeline
  - _Requirements: 1.1, 1.2, 1.3, 1.4_

- [x] 2. Backend: per-scenario B-plane time series (`src/api.py`)
  - Add `_estimate_hard_body_radius_m(mass_kg)` — bus-size scaling for the demo scenario's HBR circle
  - Add `_build_covariance_ellipse(sigma_major_km, sigma_minor_km, angle_rad, n_sigma)` — constructs a 2x2 covariance matrix from desired principal sigmas/orientation and round-trips it through `covariance_ellipse_params()`
  - Add `_build_bplane_track(...)` — builds the encounter-plane basis from TCA geometry (via finite-difference velocity estimate), projects the full uncorrected and corrected trajectories, steps the covariance ellipse size down at `cov_update_frame`, and evaluates `probability_of_collision_foster()` at every frame
  - Wire `_build_bplane_track()` into `_build_scenario()`, keyed to the existing `covariance_update` event's frame, and add the resulting `bplane` dict to the returned scenario payload
  - _Requirements: 2.1, 2.2, 2.3, 2.4, 2.5_

- [x] 3. Frontend: B-plane panel markup (`dashboard/index.html`)
  - Add "B-Plane Encounter Geometry" panel section to the left sidebar, with a canvas (`#bplane-chart`), status badge (`#bplane-badge`), and readouts for miss vector, 3-sigma ellipse, combined HBR, and Pc estimate
  - _Requirements: 3.1_

- [x] 4. Frontend: B-plane panel styling (`dashboard/style.css`)
  - Add `.bplane-section`, `#bplane-chart`, `.bplane-readout`, `.bplane-stat`, `.bplane-label`, `.bplane-value` (with `.critical-text` variant), `.bplane-hint`
  - _Requirements: 3.1_

- [x] 5. Frontend: live rendering and state wiring (`dashboard/app.js`)
  - Add `bplaneState` tracking object alongside the existing `teleState`
  - Add `setBplaneBadge()`, `resetBplanePanel()`, `updateBplaneFrame()`, `drawBplaneChart()`
  - `drawBplaneChart()` auto-scales the plot to fit the larger of (miss distance + ellipse extent) or a reasonable minimum, and renders: range-ring grid, covariance ellipse (rotated per `cov_angle_rad`), miss vector, HBR disk, and origin/primary object markers
  - Call `updateBplaneFrame()` from the per-frame scenario playback loop (`playScenarioFrames`) alongside the existing telemetry and catastrophic-gauge updates
  - Call `resetBplanePanel()` from `resetTelemetryPanel()` and on simulation stop; set the badge to LIVE on scenario start
  - Call `drawBplaneChart()` once at dashboard init for the idle empty-state grid
  - _Requirements: 3.2, 3.3, 3.4, 3.5_

- [x] 6. Verification
  - Confirmed via direct Python invocation that `_build_scenario()` produces a valid `bplane` dict (correct key set, 200-frame arrays, physically plausible miss distances and Pc values) for all three built-in scenarios
  - Confirmed via `node --check` that `dashboard/app.js` has no syntax errors after the additions
  - Confirmed via `curl` against a running dev server that `/api/scenario/<id>` returns the `bplane` field, and that the served `index.html`/`app.js`/`style.css` reflect the new panel markup, rendering functions, and styles
  - Checked `src/api.py` and `src/conjunction.py` with diagnostics (no errors)
  - _Requirements: (verification of all above)_
