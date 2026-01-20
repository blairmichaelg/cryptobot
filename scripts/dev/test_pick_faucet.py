import asyncio
import logging
from core.config import BotSettings
from browser.instance import BrowserManager
from faucets.litepick import LitePickBot

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("TestPick")

async def test_litepick():
    settings = BotSettings()
    browser_manager = BrowserManager(headless=False) # Visible for verification
    await browser_manager.launch()
    
    try:
        # Create context with profile for cookie persistence test
        litepick_account = settings.get_account("litepick") or {}
        context = await browser_manager.create_context(
            proxy=litepick_account.get("proxy"),
            profile_name="blazefoley97"
        )
        page = await browser_manager.new_page(context=context)
        
        bot = LitePickBot(settings, page)
        
        logger.info("Starting LitePick login/claim test...")
        # Test login (should use cookies if available)
        logged_in = await bot.login_wrapper()
        if logged_in:
            logger.info("✅ Login successful!")
            # Test claim
            result = await bot.claim()
            logger.info(f"Claim result: {result.status}, Balance: {result.balance}")
            
            # Save cookies
            await browser_manager.save_cookies(context, "blazefoley97")
        else:
            logger.error("❌ Login failed!")
            
    finally:
        await browser_manager.close()

if __name__ == "__main__":
    asyncio.run(test_litepick())
