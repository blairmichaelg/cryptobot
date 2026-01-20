import asyncio
import logging
import argparse
from core.config import BotSettings
from browser.instance import BrowserManager
from faucets.coinpayu import CoinPayUBot
from faucets.adbtc import AdBTCBot
from faucets.faucetcrypto import FaucetCryptoBot

# Configure Logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger("Verifier")

async def verify_faucet(name: str):
    logger.info(f"Verifying {name}...")
    
    settings = BotSettings()
    # Force Visible
    settings.headless = False
    
    browser_mgr = BrowserManager(headless=False, block_images=False) # Images useful for debugging
    await browser_mgr.launch()
    
    try:
        context = await browser_mgr.create_context()
        page = await browser_mgr.new_page(context)
        
        bot = None
        if name.lower() == "coinpayu":
            bot = CoinPayUBot(settings, page)
        elif name.lower() == "adbtc":
            bot = AdBTCBot(settings, page)
        elif name.lower() == "faucetcrypto":
            bot = FaucetCryptoBot(settings, page)
        elif name.lower() == "firefaucet":
             from faucets.firefaucet import FireFaucetBot
             bot = FireFaucetBot(settings, page)
        else:
            logger.error(f"Unknown faucet: {name}")
            return

        logger.info(f"Starting {name} Bot Logic...")
        
        # Test Login
        if await bot.login():
            logger.info("Login Verified!")
            
            # Test Claim/PTC
            logger.info("Attempting Claim/PTC (Ctrl+C to stop)...")
            await bot.claim()
            if hasattr(bot, 'view_ptc_ads'):
                await bot.view_ptc_ads()
                
        else:
            logger.error("Login Failed. Check credentials in .env")

    except Exception as e:
        logger.error(f"Runtime Error: {e}")
    finally:
        logger.info("Closing browser in 5 seconds...")
        await asyncio.sleep(5)
        await browser_mgr.close()

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("faucet", help="Name of faucet to verify (coinpayu, adbtc, faucetcrypto)")
    args = parser.parse_args()
    
    asyncio.run(verify_faucet(args.faucet))
