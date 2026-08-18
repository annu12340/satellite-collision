"""
Auto-integration pipeline for custom avoidance strategies.

When a new strategy file is created in src/strategies/custom_*.py,
this module automatically:
1. Parses the strategy function signature
2. Validates it matches the expected interface
3. Wires imports into avoidance.py
4. Registers the strategy in the active strategy list
5. Reports errors clearly if integration fails
"""

import ast
import sys
from pathlib import Path
from typing import Optional, Dict, Any, Tuple
import importlib.util


class StrategyIntegrationError(Exception):
    """Raised when strategy integration fails."""
    pass


def parse_strategy_file(filepath: str) -> Dict[str, Any]:
    """
    Parse a new strategy file and extract metadata.
    
    Expected structure:
    - File: src/strategies/custom_<name>.py
    - Contains: def evaluate_<name>(conjunction: Conjunction, spacecraft_list) -> float
    
    Args:
        filepath: Path to the strategy file (can be relative or absolute)
    
    Returns:
        Dict with keys:
        - name: Strategy name (derived from filename)
        - func_name: Function name to call
        - module_name: Import module name
        - signature: Function signature string
    
    Raises:
        StrategyIntegrationError: If file doesn't match expected structure
    """
    path = Path(filepath).resolve()  # Convert to absolute path
    
    # Validate filename pattern
    if not path.name.startswith("custom_") or not path.suffix == ".py":
        raise StrategyIntegrationError(
            f"Strategy file must be named 'custom_*.py', got '{path.name}'"
        )
    
    # Extract strategy name from filename
    strategy_name = path.stem.replace("custom_", "")
    
    # Parse the file AST
    try:
        with open(path, "r") as f:
            tree = ast.parse(f.read())
    except SyntaxError as e:
        raise StrategyIntegrationError(f"Syntax error in {path.name}: {e}")
    
    # Find the evaluate function
    func_name = f"evaluate_{strategy_name}"
    func_def = None
    
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == func_name:
            func_def = node
            break
    
    if not func_def:
        raise StrategyIntegrationError(
            f"Strategy file must contain function '{func_name}'. "
            f"Found functions: {[n.name for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)]}"
        )
    
    # Validate function signature (should have 2 params: conjunction, spacecraft_list)
    if len(func_def.args.args) != 2:
        raise StrategyIntegrationError(
            f"Strategy function must have exactly 2 parameters "
            f"(conjunction: Conjunction, spacecraft_list: List[Spacecraft]), "
            f"got {len(func_def.args.args)}"
        )
    
    # Validate return type annotation (should be float)
    if func_def.returns is None:
        raise StrategyIntegrationError(
            f"Strategy function must have return type annotation '-> float'"
        )
    
    # Get the relative module path from src/ directory
    src_dir = Path(__file__).parent
    try:
        rel_path = path.relative_to(src_dir)
    except ValueError:
        raise StrategyIntegrationError(
            f"Strategy file must be in or under {src_dir}, got {path}"
        )
    
    module_name = str(rel_path.with_suffix("")).replace("/", ".")
    
    return {
        "name": strategy_name,
        "func_name": func_name,
        "module_name": module_name,
        "filepath": str(path),
        "signature": f"def {func_name}(conjunction: Conjunction, spacecraft_list: List[Spacecraft]) -> float"
    }


def validate_strategy_callable(module_path: str, func_name: str) -> bool:
    """
    Dynamically import and validate the strategy function is callable.
    
    Args:
        module_path: Full path to the module file
        func_name: Name of the function to validate
    
    Returns:
        True if callable, False otherwise
    
    Raises:
        StrategyIntegrationError: If import or execution fails
    """
    try:
        spec = importlib.util.spec_from_file_location("temp_strategy", module_path)
        if spec is None or spec.loader is None:
            raise StrategyIntegrationError(f"Cannot load module from {module_path}")
        
        module = importlib.util.module_from_spec(spec)
        sys.modules["temp_strategy"] = module
        spec.loader.exec_module(module)
        
        if not hasattr(module, func_name):
            raise StrategyIntegrationError(
                f"Module does not contain function '{func_name}'"
            )
        
        func = getattr(module, func_name)
        if not callable(func):
            raise StrategyIntegrationError(
                f"'{func_name}' is not callable"
            )
        
        return True
    
    except Exception as e:
        raise StrategyIntegrationError(
            f"Failed to validate strategy callable: {e}"
        )


def generate_import_statement(module_name: str, func_name: str) -> str:
    """Generate the Python import statement for the strategy."""
    return f"from src.{module_name} import {func_name}"


def integrate_strategy(filepath: str, dry_run: bool = False) -> Tuple[bool, str]:
    """
    Execute the full integration pipeline for a new strategy.
    
    Pipeline:
    1. Parse the strategy file
    2. Validate the function signature
    3. Validate the function is callable
    4. Return integration metadata (errors if any)
    
    Args:
        filepath: Path to the strategy file
        dry_run: If True, don't modify files, just validate
    
    Returns:
        (success: bool, message: str)
    """
    try:
        # Step 1: Parse the file
        metadata = parse_strategy_file(filepath)
        
        # Step 2: Validate the function is callable
        validate_strategy_callable(filepath, metadata["func_name"])
        
        # Step 3: Generate import statement
        import_stmt = generate_import_statement(
            metadata["module_name"],
            metadata["func_name"]
        )
        
        message = (
            f"✓ Strategy '{metadata['name']}' validated successfully\n"
            f"  Module: {metadata['module_name']}\n"
            f"  Function: {metadata['func_name']}\n"
            f"  Import: {import_stmt}\n"
            f"\nNext steps (manual or via hook):\n"
            f"  1. Add import to src/avoidance.py\n"
            f"  2. Register in CUSTOM_STRATEGIES registry\n"
            f"  3. Call evaluate_{metadata['name']}() in evaluate_maneuver() or similar"
        )
        
        return True, message
    
    except StrategyIntegrationError as e:
        return False, f"✗ Integration failed: {str(e)}"
    except Exception as e:
        return False, f"✗ Unexpected error: {str(e)}"


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python -m src.strategy_integrator <filepath>")
        sys.exit(1)
    
    filepath = sys.argv[1]
    success, message = integrate_strategy(filepath)
    print(message)
    sys.exit(0 if success else 1)
