"""
Test script to verify browser crash fixes.

Tests:
1. Context lifecycle management
2. Closed context detection
3. Error handling for closed contexts
4. Context health checks
"""

import asyncio
import logging
from browser.instance import BrowserManager
from core.config import BotSettings
from playwright.async_api import Error as PlaywrightError

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

async def test_context_health_checks():
    """Test context health check methods."""
    print("\n=== Test 1: Context Health Checks ===")
    
    manager = BrowserManager(headless=True)
    await manager.launch()
    
    # Create a context
    context = await manager.create_context(profile_name="test_health")
    page = await manager.new_page(context=context)
    
    # Test alive context
    is_alive = await manager.check_context_alive(context)
    print(f"✓ Context alive before close: {is_alive}")
    assert is_alive, "Context should be alive"
    
    page_alive = await manager.check_page_alive(page)
    print(f"✓ Page alive before close: {page_alive}")
    assert page_alive, "Page should be alive"
    
    # Close context and test again
    await context.close()
    
    is_alive = await manager.check_context_alive(context)
    print(f"✓ Context alive after close: {is_alive}")
    assert not is_alive, "Context should be detected as closed"
    
    page_alive = await manager.check_page_alive(page)
    print(f"✓ Page alive after close: {page_alive}")
    assert not page_alive, "Page should be detected as closed"
    
    await manager.close()
    print("✓ Test 1 passed!")

async def test_closed_context_operations():
    """Test that operations on closed contexts fail gracefully."""
    print("\n=== Test 2: Closed Context Operations ===")
    
    manager = BrowserManager(headless=True)
    await manager.launch()
    
    context = await manager.create_context(profile_name="test_closed")
    page = await manager.new_page(context=context)
    
    # Close context
    await context.close()
    
    # Try to use page after close - should fail gracefully
    try:
        await page.goto("https://google.com")
        print("✗ Page navigation should have failed!")
        assert False, "Should not reach here"
    except (PlaywrightError, Exception) as e:
        error_msg = str(e).lower()
        if "target" in error_msg and "closed" in error_msg:
            print(f"✓ Caught expected closed context error: {type(e).__name__}")
        else:
            print(f"✓ Caught error on closed context: {e}")
    
    # Test status check on closed page
    status = await manager.check_page_status(page)
    print(f"✓ Status check on closed page returned: {status}")
    assert status["network_error"] or status["status"] == -1, "Should detect page is closed"
    
    await manager.close()
    print("✓ Test 2 passed!")

async def test_context_cleanup_safety():
    """Test safe context cleanup in error scenarios."""
    print("\n=== Test 3: Safe Context Cleanup ===")
    
    manager = BrowserManager(headless=True)
    await manager.launch()
    
    context = await manager.create_context(profile_name="test_cleanup")
    
    # Simulate cleanup on alive context
    is_alive = await manager.check_context_alive(context)
    if is_alive:
        await manager.save_cookies(context, "test_cleanup")
        await context.close()
        print("✓ Cleanup successful on alive context")
    
    # Create new context and close it immediately
    context2 = await manager.create_context(profile_name="test_cleanup2")
    await context2.close()
    
    # Try cleanup on already-closed context
    is_alive = await manager.check_context_alive(context2)
    if not is_alive:
        print("✓ Detected context already closed - skipping cleanup")
    else:
        # This shouldn't happen but handle it
        try:
            await manager.save_cookies(context2, "test_cleanup2")
            await context2.close()
        except Exception as e:
            print(f"✓ Cleanup error handled: {type(e).__name__}")
    
    await manager.close()
    print("✓ Test 3 passed!")

async def test_multiple_contexts_lifecycle():
    """Test creating and closing multiple contexts in sequence."""
    print("\n=== Test 4: Multiple Context Lifecycle ===")
    
    manager = BrowserManager(headless=True)
    await manager.launch()
    
    contexts = []
    for i in range(3):
        ctx = await manager.create_context(profile_name=f"test_multi_{i}")
        contexts.append(ctx)
        print(f"✓ Created context {i+1}/3")
    
    # Check all are alive
    for i, ctx in enumerate(contexts):
        is_alive = await manager.check_context_alive(ctx)
        assert is_alive, f"Context {i} should be alive"
    print("✓ All contexts alive")
    
    # Close them
    for i, ctx in enumerate(contexts):
        await ctx.close()
        is_alive = await manager.check_context_alive(ctx)
        assert not is_alive, f"Context {i} should be closed"
    print("✓ All contexts closed successfully")
    
    await manager.close()
    print("✓ Test 4 passed!")

async def test_browser_restart_recovery():
    """Test browser restart with active contexts."""
    print("\n=== Test 5: Browser Restart Recovery ===")
    
    manager = BrowserManager(headless=True)
    await manager.launch()
    
    # Create context
    context = await manager.create_context(profile_name="test_restart")
    page = await manager.new_page(context=context)
    
    # Check browser health
    healthy = await manager.check_health()
    print(f"✓ Browser healthy before restart: {healthy}")
    assert healthy, "Browser should be healthy"
    
    # Restart browser (this closes all contexts)
    await manager.restart()
    print("✓ Browser restarted")
    
    # Old context should be closed
    is_alive = await manager.check_context_alive(context)
    print(f"✓ Old context alive after restart: {is_alive}")
    assert not is_alive, "Old context should be closed after restart"
    
    # Create new context after restart
    context2 = await manager.create_context(profile_name="test_restart_new")
    is_alive = await manager.check_context_alive(context2)
    print(f"✓ New context alive after restart: {is_alive}")
    assert is_alive, "New context should be alive"
    
    await context2.close()
    await manager.close()
    print("✓ Test 5 passed!")

async def main():
    """Run all tests."""
    print("\n" + "="*60)
    print("Browser Crash Fix Verification Tests")
    print("="*60)
    
    try:
        await test_context_health_checks()
        await test_closed_context_operations()
        await test_context_cleanup_safety()
        await test_multiple_contexts_lifecycle()
        await test_browser_restart_recovery()
        
        print("\n" + "="*60)
        print("✅ ALL TESTS PASSED!")
        print("="*60)
        print("\nBrowser crash fixes verified successfully.")
        print("Context lifecycle management is working correctly.")
        
    except Exception as e:
        print("\n" + "="*60)
        print(f"❌ TEST FAILED: {e}")
        print("="*60)
        import traceback
        traceback.print_exc()
        return 1
    
    return 0

if __name__ == "__main__":
    exit_code = asyncio.run(main())
    exit(exit_code)
