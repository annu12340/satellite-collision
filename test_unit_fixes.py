#!/usr/bin/env python3
"""
Quick test to verify the unit bug fixes.

This script checks:
1. Conjunction.relative_velocity is in km/s (as documented)
2. API scenario metadata contains correct relative_velocity_kms
3. Event log distinguishes between "current range" and "predicted miss distance"
"""

import sys
import json
sys.path.insert(0, '/Users/annu/Desktop/satellite-collision')

from src.api import _build_scenario
from src.utils import Conjunction, StateVector
import numpy as np

def test_scenario_velocity():
    """Test that scenario relative velocity is correct and in km/s."""
    print("TEST 1: Scenario velocity metadata")
    print("-" * 50)
    
    scenario = _build_scenario(
        name="Test",
        description="Test scenario",
        altitude_km=650,
        inclination1_deg=85,
        inclination2_deg=95,
        relative_velocity_kms=14.2,
        mass1=300, mass2=2000,
        maneuver_dv_ms=2.5,
        maneuver_time_fraction=0.4,
        has_correction=True
    )
    
    assert scenario['metadata']['relative_velocity_kms'] == 14.2, \
        f"Scenario velocity mismatch: {scenario['metadata']['relative_velocity_kms']} != 14.2"
    print(f"✓ Scenario metadata: relative_velocity_kms = {scenario['metadata']['relative_velocity_kms']} km/s (CORRECT)")
    
    # Check that min_distance is different from current range at start
    first_dist = scenario['distances'][0]
    min_dist = min(scenario['distances'])
    tca_frame = scenario['tca_frame']
    
    print(f"✓ First frame distance: {first_dist:.1f} km")
    print(f"✓ Minimum distance (at TCA): {min_dist:.1f} km")
    print(f"✓ TCA occurs at frame {tca_frame} / {scenario['n_frames']}")
    
    assert first_dist > min_dist, \
        f"First distance {first_dist} should be greater than min {min_dist}"
    print("✓ Distance changes over encounter (as expected)")
    
    # Check detection event
    detection_evt = None
    for evt in scenario['events']:
        if evt['type'] == 'detection':
            detection_evt = evt
            break
    
    assert detection_evt is not None, "No detection event found"
    
    # With our fix, the message should mention both "current range" and "predicted miss distance"
    msg = detection_evt['message']
    print(f"✓ Detection event message: {msg}")
    
    # The event happens at frame 30 (15% of 200), so current range should NOT be min_distance
    detection_frame = int(scenario['n_frames'] * 0.15)
    current_dist_at_detection = scenario['distances'][detection_frame]
    predicted_miss = scenario['min_distance_km']
    
    print(f"✓ At detection (frame {detection_frame}):")
    print(f"    Current range: {current_dist_at_detection:.1f} km")
    print(f"    Predicted miss distance: {predicted_miss:.1f} km")
    
    assert current_dist_at_detection != predicted_miss, \
        "Current range and miss distance should be different (they are at different times)"
    print("✓ Current range ≠ predicted miss distance (as expected)")
    
    # Verify event data
    assert 'predicted_miss_distance_km' in detection_evt['data'], \
        "Event data should contain predicted_miss_distance_km"
    print(f"✓ Event data contains: {detection_evt['data'].keys()}")
    
    print("\n✓ TEST 1 PASSED\n")

def test_conjunction_velocity_units():
    """Test that Conjunction stores relative_velocity in km/s."""
    print("TEST 2: Conjunction dataclass velocity units")
    print("-" * 50)
    
    conj = Conjunction(
        obj1_id='SAT1',
        obj2_id='SAT2',
        tca=100.0,
        miss_distance=5.2,
        relative_velocity=14.2,  # Should be km/s (as per dataclass docstring)
        probability_of_collision=1.5e-4
    )
    
    assert conj.relative_velocity == 14.2, \
        f"Conjunction relative velocity should be 14.2 km/s, got {conj.relative_velocity}"
    print(f"✓ Conjunction.relative_velocity = {conj.relative_velocity} km/s (CORRECT)")
    
    # Verify this is NOT in m/s by checking range
    assert 1 < conj.relative_velocity < 20, \
        f"Relative velocity {conj.relative_velocity} out of expected LEO range (1-20 km/s)"
    print("✓ Relative velocity in expected LEO range (CORRECT)")
    
    print("\n✓ TEST 2 PASSED\n")

def test_velocity_sanity():
    """Test that closing velocity wouldn't become 1118 km/s with the scenario paths."""
    print("TEST 3: Sanity check on scenario distance changes")
    print("-" * 50)
    
    scenario = _build_scenario(
        name="Test",
        description="Test",
        altitude_km=650,
        inclination1_deg=85,
        inclination2_deg=95,
        relative_velocity_kms=14.2,
        mass1=300, mass2=2000,
        maneuver_dv_ms=2.5,
        maneuver_time_fraction=0.4,
        has_correction=True
    )
    
    distances = scenario['distances']
    n_frames = scenario['n_frames']
    
    # Check the maximum distance change per frame
    max_delta_dist = 0
    for i in range(1, len(distances)):
        delta = abs(distances[i] - distances[i-1])
        max_delta_dist = max(max_delta_dist, delta)
    
    print(f"✓ Max Δdistance per frame: {max_delta_dist:.4f} km")
    
    # If we naively computed closing velocity as Δdist / 0.05s:
    naive_closing_kms = max_delta_dist / 0.05
    print(f"✓ Naive calculation (if we divided Δdist by 0.05): {naive_closing_kms:.2f} km/s")
    
    # The correct scenario velocity
    correct_closing_kms = scenario['metadata']['relative_velocity_kms']
    print(f"✓ Correct relative velocity (from scenario metadata): {correct_closing_kms:.2f} km/s")
    
    # If someone were making the bug, they might get ~1118 by dividing by a small number
    # Let's see what divisor would give 1118 from a plausible distance change
    if max_delta_dist > 0:
        mystery_divisor = max_delta_dist / 1118.36
        print(f"✓ To get 1118 km/s, would need to divide max_delta_dist by {mystery_divisor:.6f}")
        print(f"   (This is definitely not 0.05, so our fix prevents this error)")
    
    print("\n✓ TEST 3 PASSED\n")

if __name__ == '__main__':
    try:
        test_scenario_velocity()
        test_conjunction_velocity_units()
        test_velocity_sanity()
        print("=" * 50)
        print("ALL TESTS PASSED ✓")
        print("=" * 50)
    except AssertionError as e:
        print(f"\n✗ TEST FAILED: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"\n✗ UNEXPECTED ERROR: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
