import asyncio
import logging
from core.config import BotSettings
from browser.instance import BrowserManager
from faucets.firefaucet import FireFaucetBot

# Setup concise logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger("Test")

async def test_firefaucet_login():
    settings = BotSettings()
    # Use visible mode for debugging, or headless if preferred
    browser_mgr = BrowserManager(headless=False) 
    
    try:
        await browser_mgr.launch()
        context = await browser_mgr.create_context(profile_name="test_firefaucet")
        page = await browser_mgr.new_page(context=context)
        
        bot = FireFaucetBot(settings, page)
        
        logger.info("Attempting login...")
        success = await bot.login()
        
        if success:
            logger.info("✅ Login PASSED")
        else:
            logger.error("❌ Login FAILED")
            
        await asyncio.sleep(5) # Let us see the result
        
    except Exception as e:
        logger.error(f"Test Exception: {e}")
    finally:
        await browser_mgr.close()

if __name__ == "__main__":
    asyncio.run(test_firefaucet_login())
