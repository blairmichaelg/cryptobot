import asyncio
import logging
import argparse
import os
import sys

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from core.config import BotSettings
from browser.instance import BrowserManager
from core.registry import get_faucet_class

# Configure Logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger("Verifier")

DEFAULT_FAUCETS = [
    "firefaucet",
    "cointiply",
    "freebitcoin",
    "dutchy",
    "coinpayu",
    "adbtc",
    "faucetcrypto",
    "litepick",
    "tronpick",
    "dogepick",
    "bchpick",
    "solpick",
    "tonpick",
    "polygonpick",
    "binpick",
    "dashpick",
    "ethpick",
    "usdpick",
]

async def verify_faucet(name: str, visible: bool = True, login_only: bool = False):
    logger.info(f"Verifying {name}...")
    
    settings = BotSettings()
    settings.headless = not visible
    
    browser_mgr = BrowserManager(headless=not visible, block_images=False)
    await browser_mgr.launch()
    
    try:
        context = await browser_mgr.create_context()
        page = await browser_mgr.new_page(context)

        faucet_cls = get_faucet_class(name)
        if not faucet_cls:
            logger.error(f"Unknown faucet: {name}")
            return

        bot = faucet_cls(settings, page)

        logger.info(f"Starting {name} Bot Logic...")
        
        # Test Login
        if await bot.login():
            logger.info("Login Verified!")
            if login_only:
                return

            # Test Claim/PTC
            logger.info("Attempting Claim/PTC (Ctrl+C to stop)...")
            await bot.claim()
            if hasattr(bot, "view_ptc_ads"):
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
    parser.add_argument("faucet", nargs="?", help="Name of faucet to verify")
    parser.add_argument("--all", action="store_true", help="Verify all supported faucets")
    parser.add_argument("--visible", action="store_true", help="Run with visible browser")
    parser.add_argument("--login-only", action="store_true", help="Only test login flow")
    args = parser.parse_args()

    if args.all:
        for faucet in DEFAULT_FAUCETS:
            asyncio.run(verify_faucet(faucet, visible=args.visible, login_only=args.login_only))
    elif args.faucet:
        asyncio.run(verify_faucet(args.faucet, visible=args.visible, login_only=args.login_only))
    else:
        parser.error("Specify a faucet name or use --all")
