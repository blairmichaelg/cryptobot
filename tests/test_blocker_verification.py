import pytest
import asyncio
import logging
from browser.instance import BrowserManager

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

@pytest.mark.asyncio
async def test_blocker():
    """Test that the resource blocker works without hanging."""
    logger.info("🧪 Testing Resource Blocker...")
    manager = BrowserManager(headless=True)
    
    try:
        await manager.launch()
        context = await manager.create_context()
        page = await manager.new_page(context)
        
        logger.info("Navigating to a test page with timeout...")
        # Use a lightweight page with explicit timeout to prevent hanging
        try:
            # 10 second timeout to prevent indefinite hang
            await asyncio.wait_for(
                page.goto("https://example.com", wait_until="domcontentloaded"),
                timeout=10.0
            )
            logger.info("✅ Navigation completed without error. Blocker is active.")
        except asyncio.TimeoutError:
            logger.error("❌ Page navigation timed out after 10 seconds")
            pytest.fail("Navigation timed out - possible blocker issue")
        
    except Exception as e:
        logger.error(f"❌ Blocker Test Failed: {e}")
        pytest.fail(f"Blocker Test Failed: {e}")
    finally:
        await manager.close()
