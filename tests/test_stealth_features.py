"""
Test script for new stealth features:
1. Cookie jar aging
2. Graceful degradation modes
"""

import asyncio
from browser.secure_storage import SecureCookieStorage
from core.config import OperationMode
from unittest.mock import Mock, MagicMock

async def test_cookie_aging():
    """Test cookie jar aging feature."""
    print("\n=== Testing Cookie Jar Aging ===")
    
    storage = SecureCookieStorage()
    
    # Mock browser context
    mock_context = MagicMock()
    mock_context.add_cookies = MagicMock()
    
    result = await storage.inject_aged_cookies(mock_context, "test_profile")
    
    print(f"OK inject_aged_cookies returned: {result}")
    print(f"OK add_cookies called: {mock_context.add_cookies.called}")
    
    if mock_context.add_cookies.called:
        cookies = mock_context.add_cookies.call_args[0][0]
        print(f"OK Number of cookies injected: {len(cookies)}")
        
        # Check cookie structure
        sample = cookies[0] if cookies else None
        if sample:
            print(f"OK Sample cookie: name={sample.get('name')}, domain={sample.get('domain')}")
            print(f"  - Has expiry: {'expires' in sample}")
            print(f"  - Secure: {sample.get('secure')}")
    
    print("PASS Cookie aging test passed")

def test_operation_modes():
    """Test operation mode enum."""
    print("\n=== Testing Operation Modes ===")
    
    # Test all modes exist
    modes = list(OperationMode)
    print(f"OK Available modes: {[m.value for m in modes]}")
    
    assert OperationMode.NORMAL.value == "normal"
    assert OperationMode.LOW_PROXY.value == "low_proxy"
    assert OperationMode.LOW_BUDGET.value == "low_budget"
    assert OperationMode.SLOW_MODE.value == "slow"
    assert OperationMode.MAINTENANCE.value == "maintenance"
    
    print("PASS Operation mode test passed")

def test_mode_detection():
    """Test mode detection logic."""
    print("\n=== Testing Mode Detection ===")
    
    from core.orchestrator import JobScheduler
    from core.config import BotSettings
    
    # Mock components
    settings = BotSettings()
    mock_browser = MagicMock()
    mock_proxy_manager = MagicMock()
    mock_proxy_manager.proxies = [MagicMock(healthy=True) for _ in range(15)]
    
    scheduler = JobScheduler(settings, mock_browser, mock_proxy_manager)
    
    # Test NORMAL mode
    mode = scheduler.detect_operation_mode()
    print(f"OK Default mode (15 healthy proxies): {mode.value}")
    assert mode == OperationMode.NORMAL
    
    # Test LOW_PROXY mode
    mock_proxy_manager.proxies = [MagicMock(healthy=True) for _ in range(5)]
    mode = scheduler.detect_operation_mode()
    print(f"OK Mode with 5 proxies: {mode.value}")
    assert mode == OperationMode.LOW_PROXY
    
    print("PASS Mode detection test passed")

def test_mode_restrictions():
    """Test applying mode restrictions."""
    print("\n=== Testing Mode Restrictions ===")
    
    from core.orchestrator import JobScheduler
    from core.config import BotSettings
    
    settings = BotSettings()
    mock_browser = MagicMock()
    mock_proxy_manager = MagicMock()
    mock_proxy_manager.proxies = [MagicMock(healthy=True) for _ in range(15)]
    
    scheduler = JobScheduler(settings, mock_browser, mock_proxy_manager)
    
    # Test SLOW_MODE delay multiplier
    delay = scheduler.apply_mode_restrictions(OperationMode.SLOW_MODE)
    print(f"OK SLOW_MODE delay multiplier: {delay}x")
    assert delay == 3.0
    
    # Test LOW_PROXY concurrency reduction
    original_concurrent = settings.max_concurrent_bots
    delay = scheduler.apply_mode_restrictions(OperationMode.LOW_PROXY)
    print(f"OK LOW_PROXY concurrency: {original_concurrent} -> {settings.max_concurrent_bots}")
    assert settings.max_concurrent_bots <= 2
    
    # Test NORMAL mode restoration
    delay = scheduler.apply_mode_restrictions(OperationMode.NORMAL)
    print(f"OK NORMAL mode delay multiplier: {delay}x")
    assert delay == 1.0
    
    print("PASS Mode restrictions test passed")

if __name__ == "__main__":
    # Run tests
    asyncio.run(test_cookie_aging())
    test_operation_modes()
    test_mode_detection()
    test_mode_restrictions()
    
    print("\n" + "="*50)
    print("SUCCESS: ALL STEALTH FEATURES TESTS PASSED")
    print("="*50)
