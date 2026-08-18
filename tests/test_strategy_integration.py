"""
Integration tests for custom strategy auto-wiring system.

Tests the full pipeline:
1. Strategy file creation → 2. Validation → 3. Registration → 4. Usage

Run with: python3 tests/test_strategy_integration.py
"""

import sys
import tempfile
from pathlib import Path
from typing import List

import numpy as np

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.strategy_integrator import (
    parse_strategy_file,
    validate_strategy_callable,
    integrate_strategy,
    StrategyIntegrationError
)
from src.avoidance import register_strategy, CUSTOM_STRATEGIES, apply_custom_strategies
from src.conjunction import Conjunction
from src.orbital_mechanics import Spacecraft


# ============================================================================
# Test Fixtures
# ============================================================================

def create_mock_conjunction():
    """Create a mock conjunction for testing."""
    conjunction = Conjunction(
        obj1_id="Sat-1",
        obj2_id="Sat-2",
        tca=3600,  # 1 hour from epoch
        miss_distance=0.5,  # 500 meters
        relative_velocity=10.0,  # 10 km/s
        probability_of_collision=0.001,  # 0.1%
        risk_score=0.05
    )
    # Add state vectors for strategies that need them
    conjunction.state_1 = np.array([6.778e6, 0, 0, 0, 7.5e3, 0])  # LEO circular
    conjunction.state_2 = np.array([6.778e6, 100e3, 0, 0, 7.5e3, 100])  # Slightly offset
    return conjunction


def create_mock_spacecraft_list():
    """Create a mock constellation."""
    spacecraft = []
    for i in range(5):
        state = np.array([
            6.778e6 + i*100e3,  # Staggered altitudes
            0,
            0,
            0,
            7.5e3 - i*100,
            0
        ])
        sc = Spacecraft(
            id=f"Sat-{i}",
            state=state,
            covariance=np.eye(6) * 100,
            mass=1000,  # kg
            area=10,  # m²
            cd=2.2,
            cr=1.5,
            delta_v_budget=100,  # m/s
            name=f"Satellite-{i}"
        )
        spacecraft.append(sc)
    return spacecraft


# ============================================================================
# Test Utilities
# ============================================================================

class TestResult:
    def __init__(self, name: str):
        self.name = name
        self.passed = False
        self.error = None
    
    def __repr__(self):
        status = "✓ PASS" if self.passed else "✗ FAIL"
        msg = f"{status}: {self.name}"
        if self.error:
            msg += f"\n  Error: {self.error}"
        return msg


def run_test(name: str, test_func):
    """Run a single test and return result."""
    result = TestResult(name)
    try:
        test_func()
        result.passed = True
    except Exception as e:
        result.error = str(e)
    return result


# ============================================================================
# Tests
# ============================================================================

def test_parse_valid_strategy_file():
    """Test parsing a valid custom strategy file."""
    # Use the actual src/strategies directory for testing
    from pathlib import Path
    strategy_file = Path(__file__).parent.parent / "src" / "strategies" / "custom_relative_velocity.py"
    
    if strategy_file.exists():
        # Parse the existing file
        metadata = parse_strategy_file(str(strategy_file))
        
        assert metadata["name"] == "relative_velocity"
        assert metadata["func_name"] == "evaluate_relative_velocity"
        assert "custom_relative_velocity" in metadata["module_name"]
    else:
        print("⊘ SKIP: custom_relative_velocity.py not found")


def test_parse_invalid_filename():
    """Test that non-custom_*.py files are rejected."""
    try:
        # Try to parse a file with invalid name pattern
        from pathlib import Path
        src_dir = Path(__file__).parent.parent / "src" / "strategies"
        src_dir.mkdir(parents=True, exist_ok=True)
        
        bad_file = src_dir / "invalid_strategy.py"
        bad_file.write_text("# Some code")
        
        try:
            parse_strategy_file(str(bad_file))
            raise AssertionError("Should have raised StrategyIntegrationError")
        except StrategyIntegrationError:
            pass  # Expected
        finally:
            if bad_file.exists():
                bad_file.unlink()
    except Exception as e:
        raise AssertionError(f"Test failed: {e}")


def test_parse_missing_function():
    """Test that files without the expected function are rejected."""
    with tempfile.TemporaryDirectory() as tmpdir:
        strategy_code = '''
def some_other_function() -> float:
    return 0.5
'''
        
        strategy_file = Path(tmpdir) / "custom_bad_func.py"
        strategy_file.write_text(strategy_code)
        
        try:
            parse_strategy_file(str(strategy_file))
            raise AssertionError("Should have raised StrategyIntegrationError")
        except StrategyIntegrationError as e:
            assert "must contain function" in str(e)


def test_parse_wrong_parameter_count():
    """Test that functions with wrong parameter count are rejected."""
    with tempfile.TemporaryDirectory() as tmpdir:
        strategy_code = '''
from typing import List
from src.conjunction import Conjunction

def evaluate_bad_params(conjunction: Conjunction) -> float:
    """Missing spacecraft_list parameter."""
    return 0.5
'''
        
        strategy_file = Path(tmpdir) / "custom_bad_params.py"
        strategy_file.write_text(strategy_code)
        
        try:
            parse_strategy_file(str(strategy_file))
            raise AssertionError("Should have raised StrategyIntegrationError")
        except StrategyIntegrationError as e:
            assert "exactly 2 parameters" in str(e)


def test_parse_missing_return_type():
    """Test that functions without return type are rejected."""
    with tempfile.TemporaryDirectory() as tmpdir:
        strategy_code = '''
from typing import List
from src.conjunction import Conjunction
from src.orbital_mechanics import Spacecraft

def evaluate_no_return(conjunction: Conjunction, spacecraft_list: List[Spacecraft]):
    """Missing return type annotation."""
    return 0.5
'''
        
        strategy_file = Path(tmpdir) / "custom_no_return.py"
        strategy_file.write_text(strategy_code)
        
        try:
            parse_strategy_file(str(strategy_file))
            raise AssertionError("Should have raised StrategyIntegrationError")
        except StrategyIntegrationError as e:
            assert "return type annotation" in str(e)


def test_strategy_execution_with_real_data():
    """Test a strategy that actually uses conjunction data."""
    def evaluate_velocity_test(
        conjunction: Conjunction,
        spacecraft_list: List[Spacecraft]
    ) -> float:
        """Compute risk based on relative velocity magnitude."""
        v1 = conjunction.state_1[3:6]
        v2 = conjunction.state_2[3:6]
        v_rel = np.linalg.norm(v1 - v2)
        # Normalize to 0-1 (max typical LEO relative velocity ~20 km/s)
        risk = min(v_rel / 20_000, 1.0)
        return float(risk)
    
    # Clear registry
    CUSTOM_STRATEGIES.clear()
    
    register_strategy("velocity_test", evaluate_velocity_test)
    
    conjunction = create_mock_conjunction()
    spacecraft_list = create_mock_spacecraft_list()
    results = apply_custom_strategies(conjunction, spacecraft_list)
    
    assert "velocity_test" in results
    assert results["velocity_test"] is not None
    assert 0 <= results["velocity_test"] <= 1.0


def test_duplicate_strategy_registration():
    """Test that duplicate strategy registration is rejected."""
    CUSTOM_STRATEGIES.clear()
    
    def evaluate_dup(conjunction, spacecraft_list) -> float:
        return 0.5
    
    # Register once
    register_strategy("dup_test", evaluate_dup)
    
    # Try to register again
    try:
        register_strategy("dup_test", evaluate_dup)
        raise AssertionError("Should have raised ValueError")
    except ValueError as e:
        assert "already registered" in str(e)


def test_strategy_with_runtime_error():
    """Test that strategies with runtime errors are caught gracefully."""
    CUSTOM_STRATEGIES.clear()
    
    def evaluate_broken(conjunction, spacecraft_list) -> float:
        """Strategy that raises an error."""
        raise RuntimeError("Intentional error for testing")
    
    register_strategy("broken_test", evaluate_broken)
    
    conjunction = create_mock_conjunction()
    spacecraft_list = create_mock_spacecraft_list()
    results = apply_custom_strategies(conjunction, spacecraft_list)
    
    assert "broken_test" in results
    assert results["broken_test"] is None


def test_real_relative_velocity_strategy():
    """Test the example custom_relative_velocity.py strategy."""
    CUSTOM_STRATEGIES.clear()
    
    try:
        from src.strategies.custom_relative_velocity import evaluate_relative_velocity
        
        register_strategy("relative_velocity", evaluate_relative_velocity)
        
        conjunction = create_mock_conjunction()
        spacecraft_list = create_mock_spacecraft_list()
        results = apply_custom_strategies(conjunction, spacecraft_list)
        
        assert "relative_velocity" in results
        assert results["relative_velocity"] is not None
        assert 0 <= results["relative_velocity"] <= 1.0
    except ImportError as e:
        print(f"⊘ SKIP: custom_relative_velocity module not found: {e}")


# ============================================================================
# Main
# ============================================================================

if __name__ == "__main__":
    print("\n" + "="*70)
    print("STRATEGY INTEGRATION TEST SUITE")
    print("="*70 + "\n")
    
    tests = [
        ("Parse valid strategy file", test_parse_valid_strategy_file),
        ("Reject invalid filename", test_parse_invalid_filename),
        ("Reject missing function", test_parse_missing_function),
        ("Reject wrong parameter count", test_parse_wrong_parameter_count),
        ("Reject missing return type", test_parse_missing_return_type),
        ("Strategy execution with real data", test_strategy_execution_with_real_data),
        ("Duplicate strategy rejection", test_duplicate_strategy_registration),
        ("Runtime error handling", test_strategy_with_runtime_error),
        ("Real relative_velocity strategy", test_real_relative_velocity_strategy),
    ]
    
    results = []
    for name, test_func in tests:
        result = run_test(name, test_func)
        results.append(result)
        print(result)
    
    print("\n" + "="*70)
    passed = sum(1 for r in results if r.passed)
    total = len(results)
    print(f"Results: {passed}/{total} tests passed")
    print("="*70 + "\n")
    
    sys.exit(0 if passed == total else 1)

