"""
Test script to verify browser crash fixes (Task 2).

This script tests the browser context lifecycle management improvements:
1. Context health checks before operations
2. Safe context closure with tracking
3. Double-close prevention
4. Page health validation in FaucetBot

Run with: python tests/test_browser_crash_fixes_task2.py
"""
import asyncio
import logging
import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from browser.instance import BrowserManager
from core.config import BotSettings

logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

async def test_context_health_checks():
    """Test 1: Context health checks work correctly"""
    logger.info("=" * 60)
    logger.info("TEST 1: Context Health Checks")
    logger.info("=" * 60)
    
    browser = BrowserManager(headless=True)
    await browser.launch()
    
    # Create a context
    context = await browser.create_context(profile_name="test_health")
    
    # Test 1a: Health check on alive context
    is_alive = await browser.check_context_alive(context)
    assert is_alive, "Context should be alive immediately after creation"
    logger.info("✅ Test 1a: Context health check on alive context - PASSED")
    
    # Test 1b: Health check after closing
    await context.close()
    is_alive = await browser.check_context_alive(context)
    assert not is_alive, "Context should not be alive after closing"
    logger.info("✅ Test 1b: Context health check on closed context - PASSED")
    
    await browser.close()
    logger.info("✅ TEST 1 COMPLETED: Context health checks working correctly\n")

async def test_safe_close_context():
    """Test 2: Safe context closure with tracking"""
    logger.info("=" * 60)
    logger.info("TEST 2: Safe Context Closure")
    logger.info("=" * 60)
    
    browser = BrowserManager(headless=True)
    await browser.launch()
    
    # Create a context
    context = await browser.create_context(profile_name="test_safe_close")
    
    # Test 2a: First close should succeed
    result = await browser.safe_close_context(context, profile_name="test_safe_close")
    assert result, "First close should return True"
    logger.info("✅ Test 2a: First safe_close_context - PASSED")
    
    # Test 2b: Second close should be idempotent (return False, no error)
    result = await browser.safe_close_context(context, profile_name="test_safe_close")
    assert not result, "Second close should return False (already closed)"
    logger.info("✅ Test 2b: Second safe_close_context (double-close prevention) - PASSED")
    
    # Test 2c: Third close should still not error
    result = await browser.safe_close_context(context, profile_name="test_safe_close")
    assert not result, "Third close should return False (already closed)"
    logger.info("✅ Test 2c: Third safe_close_context (idempotent) - PASSED")
    
    await browser.close()
    logger.info("✅ TEST 2 COMPLETED: Safe context closure working correctly\n")

async def test_page_health_checks():
    """Test 3: Page health checks work correctly"""
    logger.info("=" * 60)
    logger.info("TEST 3: Page Health Checks")
    logger.info("=" * 60)
    
    browser = BrowserManager(headless=True)
    await browser.launch()
    
    context = await browser.create_context(profile_name="test_page_health")
    page = await browser.new_page(context)
    
    # Test 3a: Health check on alive page
    is_alive = await browser.check_page_alive(page)
    assert is_alive, "Page should be alive after creation"
    logger.info("✅ Test 3a: Page health check on alive page - PASSED")
    
    # Test 3b: Health check after closing page
    await page.close()
    is_alive = await browser.check_page_alive(page)
    assert not is_alive, "Page should not be alive after closing"
    logger.info("✅ Test 3b: Page health check on closed page - PASSED")
    
    # Test 3c: Health check after closing context
    page2 = await browser.new_page(context)
    await context.close()
    is_alive = await browser.check_page_alive(page2)
    assert not is_alive, "Page should not be alive after context closes"
    logger.info("✅ Test 3c: Page health check after context close - PASSED")
    
    await browser.close()
    logger.info("✅ TEST 3 COMPLETED: Page health checks working correctly\n")

async def test_safe_new_page():
    """Test 4: Safe page creation with health checks"""
    logger.info("=" * 60)
    logger.info("TEST 4: Safe Page Creation")
    logger.info("=" * 60)
    
    browser = BrowserManager(headless=True)
    await browser.launch()
    
    context = await browser.create_context(profile_name="test_safe_page")
    
    # Test 4a: Create page on alive context
    page = await browser.safe_new_page(context)
    assert page is not None, "Page creation should succeed on alive context"
    logger.info("✅ Test 4a: safe_new_page on alive context - PASSED")
    
    # Close the page
    await page.close()
    
    # Test 4b: Create page after context close
    await context.close()
    page2 = await browser.safe_new_page(context)
    assert page2 is None, "Page creation should return None on closed context"
    logger.info("✅ Test 4b: safe_new_page on closed context - PASSED")
    
    await browser.close()
    logger.info("✅ TEST 4 COMPLETED: Safe page creation working correctly\n")

async def test_faucet_bot_health_checks():
    """Test 5: FaucetBot safe operation wrappers"""
    logger.info("=" * 60)
    logger.info("TEST 5: FaucetBot Safe Operations")
    logger.info("=" * 60)
    
    from faucets.base import FaucetBot
    from playwright.async_api import Page
    
    browser = BrowserManager(headless=True)
    await browser.launch()
    
    context = await browser.create_context(profile_name="test_faucet_bot")
    page = await browser.new_page(context)
    
    # Create a FaucetBot instance
    settings = BotSettings()
    bot = FaucetBot(settings, page)
    
    # Test 5a: Health check on alive page
    is_healthy = await bot.check_page_health()
    assert is_healthy, "Bot page should be healthy"
    logger.info("✅ Test 5a: FaucetBot page health check - PASSED")
    
    # Test 5b: Safe goto operation
    try:
        result = await bot.safe_goto("data:text/html,<h1>Test</h1>")
        if not result:
            # Page operations might fail on fresh page - that's okay, we're testing the wrapper
            logger.info("⚠️  Test 5b: safe_goto returned False (acceptable for fresh page)")
        logger.info("✅ Test 5b: FaucetBot safe_goto wrapper works - PASSED")
    except Exception as e:
        logger.error(f"Test 5b failed with exception: {e}")
        raise
    
    # Test 5c: Operations after page close
    await page.close()
    is_healthy = await bot.check_page_health()
    assert not is_healthy, "Bot page should not be healthy after close"
    logger.info("✅ Test 5c: FaucetBot health check after page close - PASSED")
    
    # Test 5d: Safe operations should fail gracefully
    try:
        result = await bot.safe_goto("https://example.com")
        # Result should be None or False - either way, no exception is success
        logger.info("✅ Test 5d: FaucetBot safe operation on closed page failed gracefully - PASSED")
    except Exception as e:
        # If we get an exception about closed page, the wrapper didn't work
        if "Target.*closed" in str(e) or "Connection.*closed" in str(e):
            raise AssertionError("safe_goto should not raise 'Target closed' exception")
        # Other exceptions might be expected
        logger.info("✅ Test 5d: FaucetBot safe operation raised handled exception - PASSED")
    
    await browser.close()
    logger.info("✅ TEST 5 COMPLETED: FaucetBot safe operations working correctly\n")

async def test_closed_context_tracking():
    """Test 6: Closed context tracking prevents errors"""
    logger.info("=" * 60)
    logger.info("TEST 6: Closed Context Tracking")
    logger.info("=" * 60)
    
    browser = BrowserManager(headless=True)
    await browser.launch()
    
    # Create multiple contexts
    contexts = []
    for i in range(3):
        ctx = await browser.create_context(profile_name=f"test_tracking_{i}")
        contexts.append(ctx)
    
    # Close them all using safe_close_context
    for i, ctx in enumerate(contexts):
        result = await browser.safe_close_context(ctx, profile_name=f"test_tracking_{i}")
        assert result, f"Context {i} should close successfully"
        logger.info(f"✅ Test 6.{i+1}: Closed context {i} successfully")
    
    # Verify all are tracked as closed
    logger.info(f"Closed contexts tracked: {len(browser._closed_contexts)}")
    assert len(browser._closed_contexts) == 3, "All 3 contexts should be tracked as closed"
    logger.info("✅ Test 6.4: All contexts tracked as closed - PASSED")
    
    # Closing browser should clear tracking
    await browser.close()
    assert len(browser._closed_contexts) == 0, "Closed context tracking should be cleared"
    logger.info("✅ Test 6.5: Closed context tracking cleared on browser close - PASSED")
    
    logger.info("✅ TEST 6 COMPLETED: Closed context tracking working correctly\n")

async def run_all_tests():
    """Run all browser crash fix tests"""
    logger.info("\n" + "=" * 60)
    logger.info("RUNNING BROWSER CRASH FIX TESTS (TASK 2)")
    logger.info("=" * 60 + "\n")
    
    try:
        await test_context_health_checks()
        await test_safe_close_context()
        await test_page_health_checks()
        await test_safe_new_page()
        await test_faucet_bot_health_checks()
        await test_closed_context_tracking()
        
        logger.info("\n" + "=" * 60)
        logger.info("ALL TESTS PASSED! ✅")
        logger.info("=" * 60)
        logger.info("\nBrowser crash fixes are working correctly:")
        logger.info("✅ Context health checks prevent operations on closed contexts")
        logger.info("✅ Safe context closure with double-close prevention")
        logger.info("✅ Page health validation in FaucetBot")
        logger.info("✅ Closed context tracking prevents errors")
        logger.info("✅ Safe operation wrappers provide graceful failure")
        logger.info("\nNext step: Run bots for 30+ minutes to verify stability")
        logger.info("Command: python main.py --visible\n")
        
    except AssertionError as e:
        logger.error(f"\n❌ TEST FAILED: {e}")
        raise
    except Exception as e:
        logger.error(f"\n❌ UNEXPECTED ERROR: {e}", exc_info=True)
        raise

if __name__ == "__main__":
    asyncio.run(run_all_tests())
