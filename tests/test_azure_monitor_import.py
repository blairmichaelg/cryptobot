"""
Test module to verify azure_monitor handles import failures gracefully.
This module tests the import-time exception handling (lines 23-24).
"""
import pytest
import sys
import importlib.util


def test_azure_monitor_import_failure_coverage():
    """Test import failure path with coverage tracking."""
    # Remove azure_monitor from sys.modules to force fresh import
    modules_to_remove = [k for k in sys.modules.keys() if 'azure_monitor' in k]
    saved_modules = {k: sys.modules.pop(k) for k in modules_to_remove}
    
    # Get the correct reference to __import__
    import builtins
    original_import = builtins.__import__
    
    def mock_import(name, *args, **kwargs):
        if 'azure.monitor.opentelemetry' in name or name.startswith('opentelemetry'):
            raise ImportError(f"Mocked: No module named '{name}'")
        return original_import(name, *args, **kwargs)
    
    try:
        # Temporarily replace __import__
        builtins.__import__ = mock_import
        
        # Now import the module - this should trigger the except block on lines 23-24
        spec = importlib.util.find_spec('core.azure_monitor')
        module = importlib.util.module_from_spec(spec)
        sys.modules['core.azure_monitor'] = module
        spec.loader.exec_module(module)
        
        # Verify the except block executed correctly
        assert module._azure_monitor_available == False
        assert module._tracer is None
        
        # Verify initialize works with SDK unavailable
        result = module.initialize_azure_monitor("test_conn")
        assert result == False
        
    finally:
        # Restore original import and modules
        builtins.__import__ = original_import
        
        # Remove the mocked module
        if 'core.azure_monitor' in sys.modules:
            del sys.modules['core.azure_monitor']
        
        # Restore saved modules
        sys.modules.update(saved_modules)


def test_azure_monitor_import_failure_subprocess():
    """Test that azure_monitor handles ImportError gracefully when Azure SDK is missing."""
    # This is a backup test using subprocess to verify behavior
    import subprocess
    test_script = """
import sys

# Create a custom import hook that blocks azure imports
class BlockAzureImporter:
    def find_spec(self, fullname, path, target=None):
        if 'azure.monitor' in fullname or fullname == 'opentelemetry' or fullname.startswith('opentelemetry.'):
            raise ImportError(f"Blocked import of {fullname}")
        return None

# Install the hook BEFORE importing
sys.meta_path.insert(0, BlockAzureImporter())

# Now import core.azure_monitor - it should handle the ImportError
import core.azure_monitor

# Verify the module loaded successfully with _azure_monitor_available = False
assert hasattr(core.azure_monitor, '_azure_monitor_available'), "Module should have _azure_monitor_available attribute"
assert core.azure_monitor._azure_monitor_available == False, f"Expected False, got {core.azure_monitor._azure_monitor_available}"

# Verify that initialize returns False when SDK is unavailable
result = core.azure_monitor.initialize_azure_monitor("test_connection_string")
assert result == False, "initialize_azure_monitor should return False when SDK unavailable"

print("SUCCESS: Import failure handled correctly")
"""
    
    result = subprocess.run(
        [sys.executable, '-c', test_script],
        capture_output=True,
        text=True,
        cwd='/home/runner/work/cryptobot/cryptobot'
    )
    
    assert result.returncode == 0, f"Test failed:\nstdout: {result.stdout}\nstderr: {result.stderr}"
    assert "SUCCESS" in result.stdout, f"Expected success message in output:\n{result.stdout}"
