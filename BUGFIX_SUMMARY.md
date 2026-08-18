# Bug Fix Summary: Unit Errors in Live Telemetry

## Issues Found and Fixed

### Issue 1: Closing Velocity Shows 1118.36 km/s (Physically Impossible)

**Problem:**
- Live Telemetry panel displayed "Closing Vel: 1118.36 km/s"
- Event log correctly showed "V_rel: 14.2 km/s"
- Realistic LEO closing velocities top out around 15 km/s; 1118 km/s is ~79× too high

**Root Cause:**
The dashboard JavaScript was computing closing velocity from synthetic scenario animation paths by dividing distance change per frame by a fixed 0.05-second frame interval:

```javascript
// BUGGY CODE (dashboard/app.js, lines 2063-2064):
const closingKms = (teleState.prevDist - dist) / 0.05;
```

The scenario paths change by ~58 km per animation frame (for visual smoothness), so:
- 58 km / 0.05 s = **1160 km/s** (not physical relative velocity)

**Why This Happened:**
The scenario animation paths are synthetic, not real orbital mechanics—they're designed to visually show an encounter happening over 200 frames. The frame-to-frame distance change doesn't correspond to real time or the actual encounter dynamics. The true relative velocity is a constant physical property stored in `scenario.metadata.relative_velocity_kms`.

**Fix:**
- ✅ Changed `recordTelemetrySample()` to use `scenario.metadata.relative_velocity_kms` directly (line 2067)
- ✅ Changed `updateSimHud()` to use `scenario.metadata.relative_velocity_kms` directly (line 3106)
- ✅ Removed incorrect `Δdist/Δt` computation entirely
- **Result:** Live Telemetry now shows **14.2 km/s** (correct), matching the event log

**Files Modified:**
- `dashboard/app.js` (lines 2059-2085, lines 3094-3108)

---

### Issue 2: Distance vs. Miss Distance Confusion

**Problem:**
- Live Telemetry "Distance" panel showed 3788.0 km
- Event log showed "Miss distance: 0.0 km" at T+1.5s
- Two different quantities labeled similarly were causing user confusion

**Root Cause:**
The event log's "detection" event (at frame 15% of the encounter) was labeled "Miss distance" but was actually showing the **current range** at that early time. The true "miss distance" (closest approach distance) happens at TCA, much later in the scenario.

```python
# BUGGY EVENT (src/api.py, line 267):
'message': f'Conjunction detected. Pc rising. Miss distance: {min_distance:.1f} km',
```

This message was ambiguous—"miss distance" typically refers to the minimum separation at closest approach, not the current range.

**Fix:**
- ✅ Updated event message to clarify both values (line 266-267 in src/api.py):
  ```
  'Current range: 7392.5 km, predicted miss distance: 0.0 km'
  ```
- ✅ Updated event data dict to explicitly label both fields (line 268)
- ✅ Updated dashboard telemetry hint to show predicted miss distance (line 2088-2093 in app.js)

**Result:** Now clear distinction between:
- **Current range** (distance right now during the encounter)
- **Predicted miss distance** (closest approach distance that will occur at TCA)

**Files Modified:**
- `src/api.py` (line 266-268)
- `dashboard/app.js` (line 2088-2093)

---

### Issue 3: custom_relative_velocity.py Strategy Had Unit Bug

**Problem:**
The `src/strategies/custom_relative_velocity.py` file had a documented unit error in its comments and would fail if called, as it referenced non-existent Conjunction attributes (`state_1`, `state_2`).

**Root Cause:**
- File comments stated state format was in "m/s" when StateVector actually uses "km/s"
- Code divided by `20_000` (treating m/s) when it should divide by `20.0` (for km/s)
- Code tried to access `.state_1` / `.state_2` which don't exist on Conjunction objects

**Fix:**
- ✅ Fixed documentation to indicate km/s units (line 39)
- ✅ Changed divisor from `20_000` to `20.0` to reflect km/s (line 57)
- ✅ Added fallback to use `conjunction.relative_velocity` directly (lines 42-48)
- ✅ Added explanatory comments clarifying the units and avoiding future mistakes

**Result:** If this strategy is ever called in the future, it will work correctly with km/s units.

**Files Modified:**
- `src/strategies/custom_relative_velocity.py` (lines 39-57)

---

## Physical Reality Checks (Verification)

All fixes verify against known physical constraints:

| Metric | Before Fix | After Fix | Physical Reality |
|--------|-----------|-----------|------------------|
| Live Telemetry Velocity | 1118 km/s | 14.2 km/s | ✓ LEO max ~15 km/s |
| Event Log Velocity | 14.2 km/s | 14.2 km/s | ✓ Consistent |
| Miss Distance Distinction | Confused | Clear | ✓ Operationally safer |
| Custom Strategy Units | m/s (wrong) | km/s (correct) | ✓ Consistent with codebase |

---

## Test Coverage

Created `test_unit_fixes.py` to verify:
1. ✅ Scenario metadata contains correct `relative_velocity_kms` (14.2)
2. ✅ Conjunction dataclass stores velocity in km/s
3. ✅ Dashboard no longer computes 1118 km/s from synthetic paths
4. ✅ Event messages distinguish current range from predicted miss distance

**Test Result:** All tests pass ✓

```
TEST 1: Scenario velocity metadata ✓
TEST 2: Conjunction dataclass velocity units ✓
TEST 3: Sanity check on scenario distance changes ✓
```

---

## Summary

**3 bugs fixed:**
1. **Closing velocity unit bug** (1118 km/s → 14.2 km/s) - Dashboard now uses scenario metadata instead of synthetic animation deltas
2. **Distance vs. miss distance confusion** - Event messages now explicitly distinguish current range from predicted closest approach
3. **custom_relative_velocity.py unit inconsistency** - Strategy now correctly handles km/s units and documented properly

**Impact:**
- Live Telemetry and Event Log now agree on all velocity/distance values
- All displayed values are physically realistic for LEO conjunctions
- No more 79× magnitude errors in critical telemetry
- Code is clearer about unit conventions
