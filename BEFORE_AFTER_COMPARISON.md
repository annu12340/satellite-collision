# Before/After Comparison: Unit Bug Fixes

## Live Telemetry Display

### BEFORE (Broken)
```
Live Telemetry Panel:
├─ Range: 3788.0 km
├─ Closing Vel: 1118.36 km/s ← WRONG (physically impossible)
└─ Proximity: CRITICAL

Event Log:
V_rel: 14.2 km/s ← CORRECT (but disagrees with Live Telemetry!)
```

**Problem:** Judge immediately sees 1118 km/s and distrusts entire simulation.

---

### AFTER (Fixed)
```
Live Telemetry Panel:
├─ Range: 3788.0 km (current distance snapshot)
├─ Closing Vel: 14.2 km/s ← CORRECT
└─ Proximity: CRITICAL

Event Log:
V_rel: 14.2 km/s ← CORRECT (matches Live Telemetry)

Telemetry Hint:
Predicted miss distance (at TCA): 0.0 km
```

**Result:** All velocity values agree and are physically realistic for LEO.

---

## Event Log Message

### BEFORE (Ambiguous)
```
FRAME 30 (15% of encounter):
"Conjunction detected. Pc rising. Miss distance: 0.0 km"
     ↑ User reads "Miss distance: 0 km" but current range is 3788 km
     ↑ Confuses what "miss distance" means
```

**Problem:** "Miss distance" ambiguously refers to current range at this early time, not the minimum separation at TCA.

---

### AFTER (Clear)
```
FRAME 30 (15% of encounter):
"Conjunction detected. Pc rising. Current range: 7392.5 km, predicted miss distance: 0.0 km"
     ↑ Explicitly shows current range        ↑ Explicitly shows predicted minimum
```

**Result:** Operator understands exactly what values mean and when they apply.

---

## Code Changes

### dashboard/app.js

**BEFORE (Line 2063-2064):**
```javascript
const closingKms = teleState.prevDist !== undefined
    ? (teleState.prevDist - dist) / 0.05 : 0;
    // ↑ Divides synthetic animation deltas by frame interval
    // ↑ 58 km / 0.05 s = 1160 km/s (WRONG)
```

**AFTER (Line 2107):**
```javascript
const closingKms = scenario.metadata?.relative_velocity_kms || 0;
// ↑ Uses physical property from scenario metadata
// ↑ Value is 14.2 km/s (CORRECT)
```

---

### src/api.py

**BEFORE (Line 265-267):**
```python
events.append({
    'frame': int(n_frames * 0.15),
    'type': 'detection',
    'message': f'Conjunction detected. Pc rising. Miss distance: {min_distance:.1f} km',
    'data': {'pc': 2.3e-4, 'miss_distance': min_distance}
})
# ↑ Ambiguous: "miss_distance" at frame 30 is actually current range
```

**AFTER (Line 265-268):**
```python
events.append({
    'frame': int(n_frames * 0.15),
    'type': 'detection',
    'message': f'Conjunction detected. Pc rising. Current range: {distances[int(n_frames * 0.15)]:.1f} km, predicted miss distance: {min_distance:.1f} km',
    'data': {'pc': 2.3e-4, 'current_range_km': distances[int(n_frames * 0.15)], 'predicted_miss_distance_km': min_distance}
})
# ↑ Clear: Shows both current and predicted, with explicit labels
```

---

### src/strategies/custom_relative_velocity.py

**BEFORE (Line 51, 56-57):**
```python
# Extract velocity components
v1 = state1[3:6]  # [vx, vy, vz] in m/s
v2 = state2[3:6]

# Normalize to 0-1 scale (assuming max typical LEO relative velocity ~20 km/s)
max_relative_velocity = 20_000  # m/s (20 km/s)  ← INCONSISTENT: comment says 20 km/s, code uses 20,000 m/s
risk_factor = min(v_rel_magnitude / max_relative_velocity, 1.0)
```

**AFTER (Line 42-57):**
```python
# NOTE: Conjunction objects do NOT have state_1/state_2 attributes.
# Use relative_velocity field from the Conjunction dataclass instead.
# This function is retained for documentation only and should not be called.
#
# Correct usage would be:
#   v_rel_kms = conjunction.relative_velocity  # Already in km/s
#   risk_factor = min(v_rel_kms / 20.0, 1.0)  # Normalize to 0-1 range

# Fallback: use relative_velocity directly from conjunction
if not hasattr(conjunction, 'state_1'):
    v_rel_kms = conjunction.relative_velocity
    max_relative_velocity = 20.0  # km/s (typical max for LEO)  ← CONSISTENT: Both comment and code use km/s
    risk_factor = min(v_rel_kms / max_relative_velocity, 1.0)
    return float(risk_factor)
```

---

## Test Results

```bash
$ python3 test_unit_fixes.py

TEST 1: Scenario velocity metadata
✓ Scenario metadata: relative_velocity_kms = 14.2 km/s (CORRECT)
✓ Max Δdistance per frame: 58.1182 km
✓ Naive calculation (if we divided Δdist by 0.05): 1162.36 km/s
✓ Correct relative velocity (from scenario metadata): 14.20 km/s
✓ To get 1118 km/s, would need to divide max_delta_dist by 0.051967
✓ TEST 1 PASSED

TEST 2: Conjunction dataclass velocity units
✓ Conjunction.relative_velocity = 14.2 km/s (CORRECT)
✓ Relative velocity in expected LEO range (CORRECT)
✓ TEST 2 PASSED

TEST 3: Sanity check on scenario distance changes
✓ Synthetic paths change by ~58 km/frame
✓ Real relative velocity is 14.2 km/s (from physics)
✓ Scenario metadata is the source of truth
✓ TEST 3 PASSED

ALL TESTS PASSED ✓
```

---

## Impact Summary

| Aspect | Before | After | Improvement |
|--------|--------|-------|-------------|
| **Closing Velocity Display** | 1118.36 km/s | 14.2 km/s | ✓ 79× more accurate |
| **Velocity-Log Agreement** | Disagreed | Agree | ✓ No confusion |
| **Physical Realism** | Impossible | Correct | ✓ LEO-valid range |
| **Distance Labeling** | Ambiguous | Clear | ✓ Operationally safer |
| **Code Documentation** | Inconsistent | Consistent | ✓ Future-proof |
| **Judge First Impression** | 😞 Distrustful | 😊 Confident | ✓ Professional |

---

## Root Cause Analysis

The 1118 km/s bug originated from a fundamental mismatch:

1. **Scenario paths** are synthetic animation data (200 frames over ~10 seconds of visual playback)
2. **Distance changes** per frame are ~58 km (for smooth visualization)
3. **Dashboard code** naively computed velocity as Δdist/Δt using animation frame intervals
4. **Result:** 58 km / 0.05s ≈ 1160 km/s (spurious)

**Why nobody caught this immediately:**
- The event log showed the correct value (from metadata), so testing against the event log would pass
- Visual smoothness doesn't require time-accurate paths
- The bug only manifested when someone specifically checked if Live Telemetry and Event Log agreed

**The fix:**
- Use scenario metadata's `relative_velocity_kms` (the authoritative source)
- Never recompute velocities from synthetic animation paths
- Explicitly label what "miss distance" means (minimum vs. current)
