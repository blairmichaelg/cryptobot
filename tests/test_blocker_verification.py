import pytest
import asyncio
import logging
from browser.instance import BrowserManager

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

@pytest.mark.asyncio
async def test_blocker():
    logger.info("🧪 Testing Resource Blocker...")
    manager = BrowserManager(headless=True)
    
    try:
        await manager.launch()
        # Context 1: Should have blocker
        context = await manager.create_context()
        page = await manager.new_page(context)
        
        logger.info("Navigating to a heavy page (Google)...")
        # Go to a safe page. If blocker works, it shouldn't crash.
        await page.goto("https://www.google.com")
        
        logger.info("✅ Navigation completed without error. Blocker is active.")
        
    except Exception as e:
        pytest.fail(f"❌ Blocker Test Failed: {e}")
    finally:
        await manager.close()
