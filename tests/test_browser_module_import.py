"""
Test to verify browser module imports work correctly.
This test specifically addresses the Azure VM service crash issue.
"""

import sys
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))


def test_browser_manager_direct_import():
    """Test importing BrowserManager directly from browser.instance."""
    try:
        from browser.instance import BrowserManager
        assert BrowserManager is not None
        print("✅ Direct import: from browser.instance import BrowserManager")
        return True
    except ImportError as e:
        raise AssertionError(f"Failed to import BrowserManager from browser.instance: {e}")


def test_browser_manager_module_import():
    """Test importing BrowserManager from browser module."""
    try:
        from browser import BrowserManager
        assert BrowserManager is not None
        print("✅ Module import: from browser import BrowserManager")
        return True
    except ImportError as e:
        raise AssertionError(f"Failed to import BrowserManager from browser: {e}")


def test_browser_module_attributes():
    """Test that browser module exposes correct attributes."""
    import browser
    
    assert hasattr(browser, 'BrowserManager'), "browser module should expose BrowserManager"
    assert 'BrowserManager' in browser.__all__, "__all__ should include BrowserManager"
    print("✅ Browser module attributes verified")
    return True


def test_typing_imports_in_instance():
    """Test that typing imports work in browser.instance without errors."""
    from typing import Dict, Optional, List, Any
    
    # Import BrowserManager to trigger all its imports
    from browser.instance import BrowserManager
    
    # If we get here without NameError, Dict is properly imported
    print("✅ All typing imports (Dict, Optional, List, Any) work correctly")
    return True


def test_no_circular_imports():
    """Test that importing the browser module doesn't cause circular import errors."""
    try:
        # Clear any cached imports
        modules_to_clear = [m for m in sys.modules if m.startswith('browser')]
        for m in modules_to_clear:
            del sys.modules[m]
        
        # Fresh import
        import browser
        from browser import BrowserManager
        from browser.instance import BrowserManager as BM2
        
        assert BrowserManager is BM2, "Should be the same class"
        print("✅ No circular import issues detected")
        return True
    except Exception as e:
        raise AssertionError(f"Circular import detected: {e}")


if __name__ == "__main__":
    # Run tests standalone
    print("Testing browser module imports...\n")
    test_browser_manager_direct_import()
    test_browser_manager_module_import()
    test_browser_module_attributes()
    test_typing_imports_in_instance()
    test_no_circular_imports()
    print("\n" + "="*60)
    print("✅ ALL BROWSER MODULE IMPORT TESTS PASSED!")
    print("="*60)
    print("\nThis confirms the Azure VM import fix is working correctly.")
