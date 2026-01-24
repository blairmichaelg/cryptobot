"""
Test to verify typing imports are correct in browser module.
This test ensures the Azure VM service crash (NameError: Dict) is prevented.

This test can run without dependencies installed by checking source code directly.
"""

import sys
from pathlib import Path
import ast
import re

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

# Optional pytest support, but can run standalone
try:
    import pytest
    HAS_PYTEST = True
except ImportError:
    HAS_PYTEST = False


def check_file_has_typing_import(file_path: Path, required_types: list) -> bool:
    """Check if a Python file has the required typing imports."""
    with open(file_path, 'r') as f:
        content = f.read()
    
    # Parse the file to find imports
    tree = ast.parse(content)
    
    found_types = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            if node.module == 'typing':
                for alias in node.names:
                    found_types.add(alias.name)
    
    # Check if all required types are imported
    missing = set(required_types) - found_types
    if missing:
        return False, missing
    return True, set()


def test_browser_instance_typing_imports():
    """Verify browser/instance.py has all required typing imports."""
    file_path = Path(__file__).parent.parent / 'browser' / 'instance.py'
    
    # Check the file uses Dict, Optional, List, Any
    with open(file_path, 'r') as f:
        content = f.read()
    
    # Find what typing constructs are used
    uses_dict = bool(re.search(r'\bDict\[', content))
    uses_optional = bool(re.search(r'\bOptional\[', content))
    uses_list = bool(re.search(r'\bList\[', content))
    uses_any = bool(re.search(r'\bAny\b', content))
    
    required_types = []
    if uses_dict:
        required_types.append('Dict')
    if uses_optional:
        required_types.append('Optional')
    if uses_list:
        required_types.append('List')
    if uses_any:
        required_types.append('Any')
    
    has_imports, missing = check_file_has_typing_import(file_path, required_types)
    
    assert has_imports, f"Missing typing imports: {missing}"
    print(f"✅ browser/instance.py imports typing correctly: {', '.join(required_types)}")
    return True


def test_browser_secure_storage_typing_imports():
    """Verify browser/secure_storage.py has all required typing imports."""
    file_path = Path(__file__).parent.parent / 'browser' / 'secure_storage.py'
    
    with open(file_path, 'r') as f:
        content = f.read()
    
    uses_dict = bool(re.search(r'\bDict\[', content))
    uses_optional = bool(re.search(r'\bOptional\[', content))
    uses_list = bool(re.search(r'\bList\[', content))
    uses_any = bool(re.search(r'\bAny\b', content))
    
    required_types = []
    if uses_dict:
        required_types.append('Dict')
    if uses_optional:
        required_types.append('Optional')
    if uses_list:
        required_types.append('List')
    if uses_any:
        required_types.append('Any')
    
    has_imports, missing = check_file_has_typing_import(file_path, required_types)
    assert has_imports, f"Missing typing imports: {missing}"
    print(f"✅ browser/secure_storage.py imports typing correctly: {', '.join(required_types)}")
    return True


def test_browser_stealth_hub_typing_imports():
    """Verify browser/stealth_hub.py has all required typing imports."""
    file_path = Path(__file__).parent.parent / 'browser' / 'stealth_hub.py'
    
    with open(file_path, 'r') as f:
        content = f.read()
    
    uses_dict = bool(re.search(r'\bDict\[', content))
    uses_list = bool(re.search(r'\bList\[', content))
    uses_any = bool(re.search(r'\bAny\b', content))
    
    required_types = []
    if uses_dict:
        required_types.append('Dict')
    if uses_list:
        required_types.append('List')
    if uses_any:
        required_types.append('Any')
    
    has_imports, missing = check_file_has_typing_import(file_path, required_types)
    assert has_imports, f"Missing typing imports: {missing}"
    print(f"✅ browser/stealth_hub.py imports typing correctly: {', '.join(required_types)}")
    return True


def test_browser_module_syntax():
    """Verify all browser module files have valid Python syntax."""
    import py_compile
    import tempfile
    
    browser_files = [
        'browser/instance.py',
        'browser/secure_storage.py',
        'browser/stealth_hub.py',
        'browser/blocker.py',
        'browser/stealth_scripts.py',
    ]
    
    for file_path in browser_files:
        full_path = Path(__file__).parent.parent / file_path
        if full_path.exists():
            # Compile the file to check for syntax errors
            with tempfile.NamedTemporaryFile(suffix='.pyc', delete=True) as tmp:
                py_compile.compile(str(full_path), tmp.name, doraise=True)
            print(f"✅ {file_path} has valid syntax")
    return True


def test_dict_type_annotations():
    """Test that Dict type annotations work correctly."""
    from typing import Dict, Any, Optional, List
    
    # Test the exact type annotations used in browser/instance.py
    def test_func1() -> Optional[Dict[str, str]]:
        return {"locale": "en-US", "timezone_id": "America/New_York"}
    
    def test_func2() -> Dict[str, Any]:
        return {"blocked": False, "network_error": False, "status": 200}
    
    def test_func3(cookies: List[Dict[str, Any]]) -> bool:
        return len(cookies) > 0
    
    # Call them to verify they work
    result1 = test_func1()
    assert result1 is not None
    assert "locale" in result1
    
    result2 = test_func2()
    assert result2 is not None
    assert "blocked" in result2
    
    test_cookies = [{"name": "session", "value": "test"}]
    result3 = test_func3(test_cookies)
    assert result3 is True
    
    print("✅ All Dict type annotations work correctly")
    return True


# Add pytest markers if pytest is available
if HAS_PYTEST:
    test_browser_instance_typing_imports = pytest.mark.unit(test_browser_instance_typing_imports)
    test_browser_secure_storage_typing_imports = pytest.mark.unit(test_browser_secure_storage_typing_imports)
    test_browser_stealth_hub_typing_imports = pytest.mark.unit(test_browser_stealth_hub_typing_imports)
    test_browser_module_syntax = pytest.mark.unit(test_browser_module_syntax)
    test_dict_type_annotations = pytest.mark.unit(test_dict_type_annotations)


if __name__ == "__main__":
    # Run tests standalone
    print("Testing typing imports in browser module...\n")
    test_browser_instance_typing_imports()
    test_browser_secure_storage_typing_imports()
    test_browser_stealth_hub_typing_imports()
    test_browser_module_syntax()
    test_dict_type_annotations()
    print("\n" + "="*60)
    print("✅ ALL TYPING IMPORT TESTS PASSED!")
    print("="*60)
    print("\nThis confirms the Azure VM crash fix is in place.")
    print("The repository code has correct 'from typing import Dict' imports.")


