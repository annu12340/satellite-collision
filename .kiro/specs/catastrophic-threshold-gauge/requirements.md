
# Requirements Document: Catastrophic Threshold Gauge

## Introduction

The Catastrophic Threshold Gauge is a live physics indicator in the dashboard's Live Telemetry panel that compares the current encounter's specific mass-normalized kinetic energy against the NASA Standard Breakup Model's catastrophic-fragmentation line (40 J/g = 40,000 J/kg). Rather than only reporting whether a collision was avoided in distance terms, this gauge reframes a successful avoidance maneuver as having kept the encounter energy under the catastrophic-breakup threshold — a more specific, physics-grounded claim.

The gauge is a horizontal bar with a fixed marker at the 40 J/g line, and it updates live as the relative velocity (and therefore specific energy) changes during a scenario playback, including during an avoidance burn.

## Glossary

- **System**: The Flask API backend (`src/api.py`) together with the Orbital Sentinel dashboard frontend (`dashboard/index.html`, `dashboard/app.js`, `dashboard/style.css`)
- **E_MR (Specific Energy)**: The mass-normalized kinetic energy of a collision, computed as `E_MR = (m_p * v_rel^2) / (2 * m_t)`, where `m_p` is the smaller ("projectile") mass, `m_t` the larger ("target") mass, and `v_rel` the relative velocity [kg, m/s → J/kg]
- **Catastrophic Threshold**: The NASA Standard Breakup Model's classification boundary at 40 J/g (40,000 J/kg); above this, a collision produces complete fragmentation of both bodies rather than cratering/partial damage
- **Scenario**: One of the pre-computed collision/avoidance animations served by `/api/scenario/<id>` and its SSE counterpart `/api/scenario/<id>/stream`
- **Maneuver Frame**: The animation frame index at which an avoidance burn begins, if the scenario has a correction (`has_correction: true`)
- **TCA (Time of Closest Approach)**: The frame index of minimum separation between the two objects in a scenario
- **Specific Energy Series**: The per-frame array of E_MR values (J/kg) for a scenario, reflecting how v_rel (and therefore energy) changes as an avoidance burn takes effect

## Requirements

### Requirement 1: Backend Computation of Specific Energy Timeline

**User Story:** As a developer, I want each collision scenario to carry a physically consistent, per-frame specific-energy timeline so that the frontend gauge reflects real physics rather than an approximation.

#### Acceptance Criteria

1. WHEN a scenario is built (`_build_scenario()` in `src/api.py`), THE System SHALL compute a specific energy value for every animation frame using the existing `collision_specific_energy()` function from `src/damage_minimization.py`.

2. THE specific energy calculation SHALL use `m_proj = min(mass1, mass2)` and `m_targ = max(mass1, mass2)`, consistent with the definition used elsewhere in the codebase (`is_catastrophic()`, `predict_collision_outcome()`).

3. WHERE a scenario has no avoidance correction (`has_correction: false`), THE relative velocity used for every frame's energy calculation SHALL equal the scenario's fixed `relative_velocity_kms` metadata value.

4. WHERE a scenario has an avoidance correction (`has_correction: true`) and `maneuver_dv_ms > 0`, THE System SHALL reduce the relative velocity used for frames at or after the maneuver frame, capped at 50% of the original relative velocity — consistent with the cap already used in `strategy_reduce_relative_velocity()` in `src/damage_minimization.py`.

5. THE transition in relative velocity between the maneuver frame and the TCA frame SHALL be interpolated using a smoothstep easing function, so the burn's effect on specific energy appears progressive rather than instantaneous.

6. THE computed per-frame specific energy array SHALL be exposed as `specific_energy_j_per_kg` in the scenario JSON payload returned by `/api/scenario/<id>`.

7. THE NASA breakup model catastrophic threshold constant (`CATASTROPHIC_ENERGY` from `src/utils.py`, 40,000 J/kg) SHALL be exposed as `catastrophic_energy_threshold_j_per_kg` in the scenario JSON payload.

8. THE scenario `metadata` object SHALL include: `v_rel_final_kms`, `specific_energy_initial_j_per_kg`, `specific_energy_final_j_per_kg`, `is_catastrophic_initial`, and `is_catastrophic_final`.

---

### Requirement 2: Real-Time Streaming of Specific Energy

**User Story:** As an operator watching a live scenario playback, I want the specific-energy value to update every frame so the gauge reflects the encounter's current physical state, not just a static summary.

#### Acceptance Criteria

1. WHEN the SSE endpoint (`/api/scenario/<id>/stream`) emits a `frame` event, THE System SHALL include a `specific_energy_j_per_kg` field with that frame's value, sourced from the same series computed in Requirement 1.

2. WHEN the client-side animation loop (`playScenarioFrames()` in `dashboard/app.js`) advances a frame, THE System SHALL read the corresponding value from `scenario.specific_energy_j_per_kg[frame]` and pass it to the gauge update function.

3. IF the frame index exceeds the bounds of the specific energy series, THEN THE System SHALL pass `null` rather than throwing or reading out of bounds.

---

### Requirement 3: Gauge Visual Representation

**User Story:** As an operator, I want a simple horizontal bar gauge showing current specific energy against the 40 J/g catastrophic line so I can assess encounter severity at a glance.

#### Acceptance Criteria

1. THE gauge SHALL be rendered in the dashboard's Live Telemetry panel (`dashboard/index.html`), immediately below the existing physics-equation readout block.

2. THE gauge SHALL consist of a horizontal track, a fill bar representing the current E_MR value, and a fixed vertical marker line representing the 40 J/g catastrophic threshold.

3. THE threshold marker SHALL be rendered at a fixed 60% position along the track width; the fill bar's percentage SHALL be scaled so that a value equal to the threshold (40 J/g) also lands at 60%, keeping the two visually aligned.

4. THE fill bar SHALL use a color gradient from green (safe) through yellow (approaching) to red (over threshold), and SHALL apply a glow effect when the current value meets or exceeds the threshold.

5. THE gauge SHALL display the current numeric value in J/g (converted from the underlying J/kg unit) alongside a text label identifying it as the encounter specific energy (E_MR).

6. THE gauge SHALL display a status badge with one of three states: "BELOW THRESHOLD" (value below 75% of threshold), "APPROACHING" (value between 75% and 100% of threshold), or "CATASTROPHIC" (value at or above threshold).

7. WHEN the status is "CATASTROPHIC", THE status badge SHALL visually pulse to draw operator attention.

---

### Requirement 4: Gauge Lifecycle and Reset Behavior

**User Story:** As an operator, I want the gauge to reset to a neutral state when starting a new scenario so stale data from a previous run is not displayed.

#### Acceptance Criteria

1. WHEN a new scenario begins playback (`resetTelemetryPanel()` in `dashboard/app.js`), THE gauge fill, threshold marker, value text, and status badge SHALL be reset to their initial/empty state ("STANDBY" status, 0% fill, "-- J/g" value).

2. WHILE a scenario is playing, THE gauge SHALL update on every animation frame via `updateCatastrophicGauge()`, driven by the same frame loop that updates the range/velocity telemetry chart.

3. IF the scenario is stopped by the user before completion, THEN THE gauge SHALL retain its last displayed value (consistent with the existing behavior of the live telemetry range chart, which is not cleared on stop).

---

### Requirement 5: Physics Equation Transparency

**User Story:** As an operator or reviewer, I want to see the governing equation alongside its live-evaluated result so the gauge's basis is transparent and auditable.

#### Acceptance Criteria

1. THE Live Telemetry panel's physics-equation readout SHALL include a row displaying the equation `E_MR = m_p·v_rel² / 2m_t` alongside its live-evaluated result in J/g for the current frame.

2. THE live-evaluated result SHALL update in sync with the gauge's fill and value display, using the same per-frame specific energy value.

---

### Requirement 6: Consistency with Existing Physics Model

**User Story:** As a developer, I want the gauge's underlying physics to reuse existing, already-validated code paths so the dashboard does not introduce a second, potentially divergent definition of specific energy or the catastrophic threshold.

#### Acceptance Criteria

1. THE System SHALL NOT redefine or duplicate the specific-energy formula or the 40,000 J/kg threshold constant; it SHALL import and reuse `collision_specific_energy()` and `CATASTROPHIC_ENERGY` from `src/damage_minimization.py` and `src/utils.py` respectively.

2. THE gauge's catastrophic classification (per frame or in `metadata`) SHALL be consistent with the boolean result of `is_catastrophic()` given the same masses and relative velocity, within floating-point tolerance.
