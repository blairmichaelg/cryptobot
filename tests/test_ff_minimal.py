"""
Minimal FireFaucet login test - fast, focused debugging
"""
import asyncio
import logging
import sys
from pathlib import Path

# Setup logging FIRST
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent))

from core.config import BotSettings
from faucets.firefaucet import FireFaucetBot
from browser.instance import BrowserManager


async def main():
    logger.info("="*80)
    logger.info("🔥 FIREFAUCET MINIMAL LOGIN TEST")
    logger.info("="*80)
    
    # Load config
    try:
        settings = BotSettings()
        account = settings.get_account('firefaucet')
        
        if not account:
            logger.error("❌ No FireFaucet account found in config")
            return
        
        logger.info(f"📧 Account loaded: {account['username']}")
    except Exception as e:
        logger.error(f"Config load failed: {e}", exc_info=True)
        return
    
    # Initialize browser
    browser_mgr = None
    context = None
    try:
        logger.info("🌐 Initializing browser...")
        browser_mgr = BrowserManager(
            headless=False,  # Visible for debugging
            block_images=False,  # Don't block images for initial testing
            block_media=False,
            timeout=60000  # 60s timeout
        )
        
        logger.info("🚀 Launching browser...")
        await browser_mgr.launch()
        logger.info("✅ Browser launched")
        
        # Create context and page
        logger.info("📄 Creating page context...")
        context = await browser_mgr.create_context(
            proxy=None,
            profile_name=account['username']
        )
        page = await browser_mgr.new_page(context=context)
        logger.info("✅ Page created")
        
        # Create bot instance
        logger.info("🤖 Creating bot instance...")
        bot = FireFaucetBot(settings, page)
        
        # Set credentials
        bot.settings_account_override = {
            "username": account['username'],
            "password": account['password']
        }
        logger.info("✅ Bot configured")
        
        #Test login
        logger.info("🔐 Starting login test...")
        try:
            login_result = await asyncio.wait_for(bot.login(), timeout=120)
            
            if login_result:
                logger.info("✅ LOGIN SUCCESSFUL!")
                logger.info(f"Current URL: {page.url}")
                
                # Try to get balance
                try:
                    balance = await bot.get_balance()
                    logger.info(f"💰 Balance: {balance}")
                except Exception as bal_err:
                    logger.warning(f"Balance check failed: {bal_err}")
                    
            else:
                logger.error("❌ LOGIN FAILED - returned False")
                logger.info(f"Current URL: {page.url}")
                
        except asyncio.TimeoutError:
            logger.error("❌ LOGIN TIMEOUT after 120s")
            logger.info(f"Current URL: {page.url}")
        except Exception as login_err:
            logger.error(f"❌ LOGIN ERROR: {login_err}", exc_info=True)
            logger.info(f"Current URL: {page.url}")
            
    except Exception as e:
        logger.error(f"Test failed: {e}", exc_info=True)
    finally:
        logger.info("🧹 Cleaning up...")
        try:
            if context:
                await browser_mgr.safe_close_context(context, profile_name=account.get('username', 'unknown'))
            if browser_mgr:
                await browser_mgr.cleanup()
            logger.info("✅ Cleanup complete")
        except Exception as cleanup_err:
            logger.error(f"Cleanup error: {cleanup_err}")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Test interrupted by user")
    except Exception as e:
        logger.error(f"Fatal error: {e}", exc_info=True)
