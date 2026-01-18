import pytest
from core.registry import get_faucet_class, FAUCET_REGISTRY
from faucets.firefaucet import FireFaucetBot

def test_get_faucet_class_direct():
    """Test resolving a direct class reference."""
    cls = get_faucet_class("firefaucet")
    assert cls == FireFaucetBot
    
    cls = get_faucet_class("fire")
    assert cls == FireFaucetBot

def test_get_faucet_class_case_insensitive():
    """Test that key lookup is case-insensitive."""
    cls = get_faucet_class("FIREFAUCET")
    assert cls == FireFaucetBot

def test_get_faucet_class_invalid():
    """Test resolving an unknown faucet type."""
    cls = get_faucet_class("unknown_faucet")
    assert cls is None

def test_get_faucet_class_lazy_load():
    """Test resolving a lazy-loaded bot via string path."""
    # We'll use litepick as an example since it's in the registry as a string
    # We mock importlib to avoid actual module loading if it's heavy, 
    # but let's see if it works directly first.
    cls = get_faucet_class("litepick")
    assert cls is not None
    assert cls.__name__ == "LitePickBot"

def test_get_faucet_class_all_registry_keys():
    """Verify all keys in registry can be resolved without error."""
    for key in FAUCET_REGISTRY.keys():
        cls = get_faucet_class(key)
        assert cls is not None
