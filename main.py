"""
Gen 3.0 Crypto Faucet Farm - Main Entry Point

This script serves as the central orchestrator for the crypto faucet automation system.
It initializes the browser environment, loads account profiles, and starts the
JobScheduler to manage concurrent claiming tasks.

Usage:
    python main.py              # Run in standard continuous mode
    python main.py --visible    # Run with visible browser
    python main.py --single fire_faucet  # Run specific faucet only
"""
from dotenv import load_dotenv

# Load environment variables from .env file into os.environ
load_dotenv()

import asyncio
import argparse
import logging
import sys

from core.config import BotSettings, AccountProfile
from core.logging_setup import setup_logging
from core.wallet_manager import WalletDaemon
from browser.instance import BrowserManager
from core.orchestrator import JobScheduler

logger = logging.getLogger(__name__)

# Factory registry for faucet bot instantiation
from core.registry import get_faucet_class

async def main():
    """
    Main execution loop.

    1. Parses command line arguments.
    2. detailed logging setup.
    3. Initializes BrowserManager (Stealth Context).
    4. Initializes ProxyManager (if 2Captcha proxies enabled).
    5. Loads Faucet Jobs from the Factory Registry.
    6. Starts the JobScheduler and waits for SIGTERM or interruption.
    """
    parser = argparse.ArgumentParser(description="Gen 3.0 Smart Crypto Farm - Job Scheduler")
    parser.add_argument("--visible", action="store_true", help="Show browser")
    parser.add_argument("--wallet-check", action="store_true", help="Check Electrum")
    parser.add_argument("--single", type=str, help="Run only a specific faucet (e.g. 'firefaucet')")
    args = parser.parse_args()

    settings = BotSettings()
    if args.visible:
        settings.headless = False

    if settings.headless and not (settings.twocaptcha_api_key or settings.capsolver_api_key):
        logger.warning("⚠️ Headless mode with no CAPTCHA API key will block claims. Switching to visible mode.")
        settings.headless = False

    setup_logging(settings.log_level)

    # Wallet Check
    if args.wallet_check:
        wallet = WalletDaemon(settings.wallet_rpc_urls, settings.electrum_rpc_user, settings.electrum_rpc_pass)
        for coin in settings.wallet_rpc_urls.keys():
            bal = await wallet.get_balance(coin)
            if bal:
                logger.info(f"💰 {coin} Balance: {bal}")

    # Initialize Managers
    browser_manager = BrowserManager(
        headless=settings.headless,
        block_images=settings.block_images,
        block_media=settings.block_media,
        timeout=settings.timeout,
        user_agents=settings.user_agents
    )
    
    proxy_manager = None
    if settings.use_2captcha_proxies:
        from core.proxy_manager import ProxyManager
        logger.info("🔒 2Captcha Proxies Enabled. Initializing Manager...")
        proxy_manager = ProxyManager(settings)
    
    scheduler = JobScheduler(settings, browser_manager, proxy_manager)

    import signal
    
    stop_signal = asyncio.Event()

    def handle_sigterm():
        logger.info("🛑 Received SIGTERM. Initiating graceful shutdown...")
        stop_signal.set()
        scheduler.stop()

    loop = asyncio.get_running_loop()
    if sys.platform != "win32":
        loop.add_signal_handler(signal.SIGTERM, handle_sigterm)

    
    # Main Execution Block
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
            if settings.freebitcoin_username:
                profiles.append(AccountProfile(faucet="freebitcoin", username=settings.freebitcoin_username, password=settings.freebitcoin_password))
            if settings.dutchy_username:
                profiles.append(AccountProfile(faucet="dutchy", username=settings.dutchy_username, password=settings.dutchy_password))
            
            # Pick.io Family
            if settings.litepick_username:
                profiles.append(AccountProfile(faucet="litepick", username=settings.litepick_username, password=settings.litepick_password))
            if settings.tronpick_username:
                profiles.append(AccountProfile(faucet="tronpick", username=settings.tronpick_username, password=settings.tronpick_password))
            if settings.dogepick_username:
                profiles.append(AccountProfile(faucet="dogepick", username=settings.dogepick_username, password=settings.dogepick_password))
            if settings.bchpick_username:
                profiles.append(AccountProfile(faucet="bchpick", username=settings.bchpick_username, password=settings.bchpick_password))
            if settings.solpick_username:
                profiles.append(AccountProfile(faucet="solpick", username=settings.solpick_username, password=settings.solpick_password))
            if settings.tonpick_username:
                profiles.append(AccountProfile(faucet="tonpick", username=settings.tonpick_username, password=settings.tonpick_password))
            if settings.polygonpick_username:
                profiles.append(AccountProfile(faucet="polygonpick", username=settings.polygonpick_username, password=settings.polygonpick_password))
            if settings.binpick_username:
                profiles.append(AccountProfile(faucet="binpick", username=settings.binpick_username, password=settings.binpick_password))
            if settings.dashpick_username:
                profiles.append(AccountProfile(faucet="dashpick", username=settings.dashpick_username, password=settings.dashpick_password))
            if settings.ethpick_username:
                profiles.append(AccountProfile(faucet="ethpick", username=settings.ethpick_username, password=settings.ethpick_password))
            if settings.usdpick_username:
                profiles.append(AccountProfile(faucet="usdpick", username=settings.usdpick_username, password=settings.usdpick_password))
        
        # Filter if --single provided
        if args.single:
            target = args.single.lower().replace("_", "")
            profiles = [p for p in profiles if target in p.faucet.lower().replace("_", "")]
            if not profiles:
                logger.warning(f"No profiles found matching '{args.single}'")
                return

        # If we have real profiles, purge legacy test jobs restored from session_state.json
        if profiles and any(p.faucet.lower() != "test" for p in profiles):
            if scheduler.has_only_test_jobs():
                removed = scheduler.purge_jobs(lambda j: j.faucet_type.lower() == "test")
                if removed:
                    logger.info(f"Purged {removed} legacy test jobs from restored session.")
                    scheduler.persist_session()

        # Canary filter (optional)
        if settings.canary_only and settings.canary_profile:
            filtered_profiles = settings.filter_profiles(profiles)
            if not filtered_profiles:
                logger.warning(
                    "No profiles matched CANARY_PROFILE '%s'",
                    settings.canary_profile
                )
                return
            profiles = filtered_profiles

        # 2Captcha Proxy Integration (Sticky Sessions)
        if proxy_manager:
            # Attempt fetch (redirects to file loader in modern versions)
            success = await proxy_manager.fetch_proxies()
            if success:
                proxy_manager.assign_proxies(profiles)
            else:
                logger.warning("⚠️ No 2Captcha proxies found in proxies.txt. Using fallback or direct connection.")

        for profile in profiles:
            # Initialize bot instance to get its jobs using factory pattern
            f_type = profile.faucet.lower()
            bot_class = get_faucet_class(f_type)
            
            if bot_class:
                    
                bot = bot_class(settings, None)
                # Inject credentials
                override = {
                    "username": profile.username,
                    "password": profile.password
                }
                if "pick" in f_type:
                    override["email"] = profile.username
                bot.settings_account_override = override
                
                # Sticky Proxy Injection
                if profile.proxy:
                    bot.set_proxy(profile.proxy)
                
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
