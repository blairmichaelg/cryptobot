import asyncio
import argparse
import logging
import sys
import random
import time
from typing import List, Dict
from dataclasses import dataclass

from core.config import BotSettings, AccountProfile
from core.logging_setup import setup_logging
from core.wallet_manager import WalletDaemon
from browser.instance import BrowserManager
from faucets.base import ClaimResult
from faucets.firefaucet import FireFaucetBot
from faucets.cointiply import CointiplyBot
from faucets.freebitcoin import FreeBitcoinBot
from faucets.dutchy import DutchyBot
from faucets.coinpayu import CoinPayUBot
from faucets.adbtc import AdBTCBot
from faucets.faucetcrypto import FaucetCryptoBot

from core.orchestrator import JobScheduler, Job

logger = logging.getLogger(__name__)

# Factory registry for faucet bot instantiation
FAUCET_REGISTRY = {
    "fire_faucet": FireFaucetBot,
    "firefaucet": FireFaucetBot,
    "fire": FireFaucetBot,
    "cointiply": CointiplyBot,
    "freebitcoin": FreeBitcoinBot,
    "free": FreeBitcoinBot,
    "dutchy": DutchyBot,
    "dutchycorp": DutchyBot,
    "coinpayu": CoinPayUBot,
    "adbtc": AdBTCBot,
    "faucetcrypto": FaucetCryptoBot,
    # Pick Family (.io)
    "litepick": "faucets.litepick.LitePickBot",
    "tronpick": "faucets.tronpick.TronPickBot",
    "dogepick": "faucets.dogepick.DogePickBot",
    "bchpick": "faucets.bchpick.BCHPickBot",
    "solpick": "faucets.solpick.SolPickBot",
    "tonpick": "faucets.tonpick.TonPickBot",
    "polygonpick": "faucets.polygonpick.PolygonPickBot",
    "binpick": "faucets.binpick.BinPickBot",
}

async def main():
    parser = argparse.ArgumentParser(description="Gen 3.0 Smart Crypto Farm - Job Scheduler")
    parser.add_argument("--visible", action="store_true", help="Show browser")
    parser.add_argument("--wallet-check", action="store_true", help="Check Electrum")
    args = parser.parse_args()

    settings = BotSettings()
    if args.visible:
        settings.headless = False

    setup_logging(settings.log_level)

    # Wallet Check
    if args.wallet_check:
        wallet = WalletDaemon(settings.wallet_rpc_urls, settings.electrum_rpc_user, settings.electrum_rpc_pass)
        for coin in settings.wallet_rpc_urls.keys():
             bal = await wallet.get_balance(coin)
             if bal:
                logger.info(f"💰 {coin} Balance: {bal}")

    browser_manager = BrowserManager(
        headless=settings.headless,
        block_images=settings.block_images,
        block_media=settings.block_media
    )
    
    scheduler = JobScheduler(settings, browser_manager)

    import signal
    
    stop_signal = asyncio.Event()

    def handle_sigterm():
        logger.info("🛑 Received SIGTERM. Initiating graceful shutdown...")
        stop_signal.set()
        scheduler.stop()

    loop = asyncio.get_running_loop()
    loop.add_signal_handler(signal.SIGTERM, handle_sigterm)

    try:
        await browser_manager.launch()
        
        # ... (Profile loading code remains here, assume unchanged for this patch context) ... 
        # CAUTION: The replacement tool requires me to match the existing content EXACTLY.
        # Since I am replacing a huge block, I will just wrap the scheduler loop in a task that waits for the signal.

        # Let's adjust the Main Loop part instead.
        
        # Load Profiles... (omitted for brevity in thought, but must be in tool call if I replace it)
        # Actually, let's just insert the signal handler setup BEFORE the try block, and change the loop wait.
        
        # ... skipping to the try/except block ...
    try:
        await browser_manager.launch()
        
        # Load Profiles and Populate Jobs
        profiles = []
        if settings.accounts:
            profiles = [acc for acc in settings.accounts if acc.enabled]
        else:
            # Legacy Fallback
            if settings.firefaucet_username:
                profiles.append(AccountProfile(faucet="fire_faucet", username=settings.firefaucet_username, password=settings.firefaucet_password))
            if settings.cointiply_username:
                profiles.append(AccountProfile(faucet="cointiply", username=settings.cointiply_username, password=settings.cointiply_password))
            # ... add others as needed for legacy ...

        # 2Captcha Proxy Integration (Sticky Sessions)
        if settings.use_2captcha_proxies:
            from core.proxy_manager import ProxyManager
            logger.info("🔒 2Captcha Proxies Enabled. Initializing Manager...")
            proxy_manager = ProxyManager(settings)
            
            # Attempt fetch
            success = await proxy_manager.fetch_proxies()
            if success:
                proxy_manager.assign_proxies(profiles)
            else:
                logger.warning("⚠️ Failed to fetch 2Captcha proxies. Creating fallback assignments or using direct connection.")

        for profile in profiles:
            # Initialize bot instance to get its jobs using factory pattern
            f_type = profile.faucet.lower()
            bot_class = FAUCET_REGISTRY.get(f_type)
            
            if bot_class:
                # Handle string-based lazy imports for pick family or others
                if isinstance(bot_class, str):
                    import importlib
                    module_path, class_name = bot_class.rsplit('.', 1)
                    module = importlib.import_module(module_path)
                    bot_class = getattr(module, class_name)
                    
                bot = bot_class(settings, None)
                # Inject credentials
                bot.settings_account_override = {
                    "username": profile.username,
                    "password": profile.password
                }
                
                # Sticky Proxy Injection
                if profile.proxy:
                    # Helper check:
                    p_str = profile.proxy
                    if "://" in p_str:
                        p_str = p_str.split("://")[1]
                    bot.set_proxy(p_str)
                
                # Get jobs and add to scheduler
                jobs = bot.get_jobs()
                for job in jobs:
                    job.profile = profile
                    scheduler.add_job(job)
            else:
                logger.warning(f"Unknown faucet type for profile {profile.username}: {profile.faucet}")

        # Start Scheduler with signal support
        scheduler_task = asyncio.create_task(scheduler.scheduler_loop())
        
        # Wait for either completion or stop signal
        await stop_signal.wait()
        
        if not scheduler_task.done():
            scheduler_task.cancel()
            try:
                await scheduler_task
            except asyncio.CancelledError:
                pass

    except KeyboardInterrupt:
        logger.info("👋 Stopping Farm (KeyboardInterrupt)...")
    finally:
        logger.info("🧹 Cleaning up resources...")
        scheduler.stop()
        # Wait briefly for running jobs to acknowledge stop
        await asyncio.sleep(2)
        await browser_manager.close()

if __name__ == "__main__":
    asyncio.run(main())
