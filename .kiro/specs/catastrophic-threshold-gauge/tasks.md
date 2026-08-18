# Implementation Tasks: Catastrophic Threshold Gauge

Status: Implemented (fast-task workflow — implemented directly, spec recorded after the fact).

- [x] 1. Backend: compute per-frame specific energy series in `_build_scenario()` (`src/api.py`)
  - Import `collision_specific_energy` from `src/damage_minimization.py` and `CATASTROPHIC_ENERGY` from `src/utils.py`
  - Derive `m_proj`/`m_targ` from scenario mass1/mass2
  - For corrected scenarios, reduce v_rel from the maneuver frame to TCA using a smoothstep ease, capped at 50% reduction
  - Build `specific_energy_series` for all frames
  - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5_

- [x] 2. Backend: expose new fields in scenario payload
  - Add `specific_energy_j_per_kg` (array) and `catastrophic_energy_threshold_j_per_kg` to the returned scenario dict
  - Add `v_rel_final_kms`, `specific_energy_initial_j_per_kg`, `specific_energy_final_j_per_kg`, `is_catastrophic_initial`, `is_catastrophic_final` to `metadata`
  - _Requirements: 1.6, 1.7, 1.8_

- [x] 3. Backend: stream specific energy over SSE
  - Include `specific_energy_j_per_kg` in each `frame` event emitted by `/api/scenario/<id>/stream`
  - _Requirements: 2.1_

- [x] 4. Frontend: read per-frame energy value during playback
  - In `playScenarioFrames()`, read `scenario.specific_energy_j_per_kg[frame]` (guarded against out-of-bounds) and attach to `frameData`
  - _Requirements: 2.2, 2.3_

- [x] 5. Frontend: gauge markup
  - Add "Catastrophic Threshold" panel section to `dashboard/index.html` (track, fill, threshold marker, status badge, value readout)
  - Add fourth physics-equation row (`E_MR = m_p·v_rel² / 2m_t`) to the existing physics readout block
  - _Requirements: 3.1, 3.2, 3.5, 5.1_

- [x] 6. Frontend: gauge styling
  - Add `.catastrophic-section`, `.catastrophic-track`, `.catastrophic-fill` (with `.over-threshold` variant), `.catastrophic-threshold-line`, `.catastrophic-status-badge` (with success/warning/critical variants + pulse animation) to `dashboard/style.css`
  - _Requirements: 3.3, 3.4, 3.6, 3.7_

- [x] 7. Frontend: gauge update/reset logic
  - Implement `updateCatastrophicGauge(specificEnergyJPerKg, scenario)` — scales fill so the 40 J/g line aligns with the fixed 60% marker position, sets status badge text/class, updates value + physics-eq readout
  - Implement `resetCatastrophicGauge()` and call it from `resetTelemetryPanel()`
  - Call `updateCatastrophicGauge()` from the per-frame playback loop alongside the existing telemetry chart update
  - _Requirements: 3.3, 4.1, 4.2, 4.3, 5.2_

- [x] 8. Verification
  - Confirmed via direct Python invocation that `collision_specific_energy()` produces expected values for all three built-in scenarios
  - Confirmed via `curl` against a running dev server that `/api/scenario/<id>` and `/api/scenario/<id>/stream` both carry the new fields correctly per frame
  - Checked `dashboard/app.js`, `dashboard/index.html`, `dashboard/style.css`, `src/api.py` with diagnostics (no errors)
  - _Requirements: 6.1, 6.2_
