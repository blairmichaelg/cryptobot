"""
Debug test - Just navigate to FireFaucet login and dump page structure
"""
import asyncio
import logging
import sys
from pathlib import Path

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

sys.path.insert(0, str(Path(__file__).parent))

from core.config import BotSettings
from browser.instance import BrowserManager


async def main():
    logger.info("🔍 FIREFAUCET PAGE STRUCTURE TEST")
    
    browser_mgr = None
    try:
        settings = BotSettings()
        browser_mgr = BrowserManager(headless=False, timeout=60000)
        
        await browser_mgr.launch()
        logger.info("✅ Browser launched")
        
        context = await browser_mgr.create_context(proxy=None)
        page = await browser_mgr.new_page(context=context)
        logger.info("✅ Page created")
        
        # Navigate to login
        logger.info("🌐 Navigating to https://firefaucet.win/login")
        await page.goto("https://firefaucet.win/login", wait_until="domcontentloaded")
        
        await asyncio.sleep(5)  # Let it load
        
        url = page.url
        logger.info(f"📍 Current URL: {url}")
        
        # Check for selectors
        logger.info("🔍 Checking for #username selector...")
        username_count = await page.locator('#username').count()
        logger.info(f"   Found: {username_count}")
        
        logger.info("🔍 Checking for input[type='text'] selectors...")
        text_inputs = await page.locator('input[type="text"]').count()
        logger.info(f"   Found: {text_inputs}")
        
        logger.info("🔍 Checking for input[type='email'] selectors...")
        email_inputs = await page.locator('input[type="email"]').count()
        logger.info(f"   Found: {email_inputs}")
        
        logger.info("🔍 Checking for any input selectors...")
        all_inputs = await page.locator('input').count()
        logger.info(f"   Found: {all_inputs}")
        
        # Get page title
        title = await page.title()
        logger.info(f"📄 Page title: {title}")
        
        # Check for Cloudflare
        logger.info("🔍 Checking for Cloudflare...")
        cf_text = await page.content()
        is_cloudflare = 'cloudflare' in cf_text.lower() or 'checking your browser' in cf_text.lower()
        logger.info(f"   Cloudflare detected: {is_cloudflare}")
        
        # Dump all input names and IDs
        logger.info("🔍 Dumping all input element details...")
        inputs_js = await page.evaluate("""
            () => {
                const inputs = Array.from(document.querySelectorAll('input'));
                return inputs.map(inp => ({
                    id: inp.id,
                    name: inp.name,
                    type: inp.type,
                    placeholder: inp.placeholder
                }));
            }
        """)
        for i, inp in enumerate(inputs_js):
            logger.info(f"   Input {i+1}: {inp}")
        
        logger.info("\n⏸️ Pausing for manual inspection (30s)...")
        await asyncio.sleep(30)
        
    except Exception as e:
        logger.error(f"Error: {e}", exc_info=True)
    finally:
        if browser_mgr:
            await browser_mgr.cleanup()


if __name__ == "__main__":
    asyncio.run(main())
