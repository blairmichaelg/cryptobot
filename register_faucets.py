#!/usr/bin/env python3
"""
Automated Registration Script for Pick.io Faucet Family

This script automates the registration process for all 11 Pick.io faucet sites:
- LitePick.io
- TronPick.io
- DogePick.io
- SolPick.io
- BinPick.io
- BchPick.io
- TonPick.io
- PolygonPick.io
- DashPick.io
- EthPick.io
- UsdPick.io

Usage:
    python register_faucets.py --email your@email.com --password yourpassword

All sites share the same backend, so the registration process is consistent.
"""

import asyncio
import argparse
import logging
from typing import List, Dict
from dataclasses import dataclass

from core.config import BotSettings
from core.logging_setup import setup_logging
from browser.instance import BrowserManager
from faucets.pick import PickFaucetBot

logger = logging.getLogger(__name__)

@dataclass
class RegistrationConfig:
    """Configuration for faucet registration."""
    coin_symbol: str
    faucet_name: str
    base_url: str

# Registry of all Pick.io faucets
PICK_FAUCETS = [
    RegistrationConfig("LTC", "LitePick", "https://litepick.io"),
    RegistrationConfig("TRX", "TronPick", "https://tronpick.io"),
    RegistrationConfig("DOGE", "DogePick", "https://dogepick.io"),
    RegistrationConfig("SOL", "SolPick", "https://solpick.io"),
    RegistrationConfig("BNB", "BinPick", "https://binpick.io"),
    RegistrationConfig("BCH", "BchPick", "https://bchpick.io"),
    RegistrationConfig("TON", "TonPick", "https://tonpick.io"),
    RegistrationConfig("MATIC", "PolygonPick", "https://polygonpick.io"),
    RegistrationConfig("DASH", "DashPick", "https://dashpick.io"),
    RegistrationConfig("ETH", "EthPick", "https://ethpick.io"),
    RegistrationConfig("USDT", "UsdPick", "https://usdpick.io"),
]


async def register_single_faucet(
    browser_manager: BrowserManager,
    settings: BotSettings,
    config: RegistrationConfig,
    email: str,
    password: str
) -> bool:
    """
    Register a single faucet site.
    
    Args:
        browser_manager: Browser instance manager
        settings: Bot configuration settings
        config: Registration configuration for the faucet
        email: Email for registration
        password: Password for registration
        
    Returns:
        bool: True if registration successful
    """
    logger.info(f"\n{'='*60}")
    logger.info(f"Registering: {config.faucet_name}")
    logger.info(f"{'='*60}")
    
    context = None
    page = None
    try:
        # Create isolated context with sticky session support
        proxy = getattr(settings, "registration_proxy", None)
        profile_name = f"register_{config.faucet_name}"
        
        context = await browser_manager.create_context(
            proxy=proxy,
            profile_name=profile_name
        )
        page = await browser_manager.new_page(context=context)
        
        # Initialize bot using consolidated PickFaucetBot
        bot = PickFaucetBot(settings, page, config.faucet_name, config.base_url)
        
        # Get wallet address for this coin if available
        wallet_address = None
        if hasattr(settings, 'wallet_addresses') and settings.wallet_addresses:
            # wallet_addresses is Dict[str, str] mapping coin symbol to address
            wallet_info = settings.wallet_addresses.get(config.coin_symbol)
            if isinstance(wallet_info, dict):
                wallet_address = wallet_info.get('address')
            elif isinstance(wallet_info, str):
                wallet_address = wallet_info
        
        # Perform registration
        success = await bot.register(email, password, wallet_address)
        
        if success:
            logger.info(f"✅ {config.faucet_name} registration successful!")
            # Save cookies/session is handled by sticky session logic in create_context/save_cookies
            await browser_manager.save_cookies(context, profile_name)
        else:
            logger.error(f"❌ {config.faucet_name} registration failed")
            
        # Small delay before next registration
        await asyncio.sleep(2)
        
        return success
        
    except Exception as e:
        logger.error(f"❌ Error registering {config.faucet_name}: {e}")
        return False
    finally:
        if page:
            await page.close()
        if context:
            await context.close()


async def register_all_faucets(
    email: str,
    password: str,
    faucet_filter: List[str] = None,
    headless: bool = True
):
    """
    Register all Pick.io faucets with the same credentials.
    
    Args:
        email: Email address for registration
        password: Password for all accounts
        faucet_filter: Optional list of faucet names to register (e.g., ['litepick', 'tronpick'])
        headless: Whether to run browser in headless mode
    """
    settings = BotSettings()
    settings.headless = headless
    
    browser_manager = BrowserManager(
        headless=settings.headless,
        block_images=settings.block_images,
        block_media=settings.block_media
    )
    
    results = {}
    
    try:
        await browser_manager.launch()
        logger.info("🚀 Starting Pick.io Faucet Registration Process")
        logger.info(f"📧 Email: {email}")
        logger.info(f"🔐 Password: {'*' * len(password)}")
        logger.info(f"🌐 Headless Mode: {headless}")
        logger.info("")
        
        # Filter faucets if specified
        faucets_to_register = PICK_FAUCETS
        if faucet_filter:
            faucet_filter_lower = [f.lower() for f in faucet_filter]
            faucets_to_register = [
                f for f in PICK_FAUCETS 
                if f.faucet_name.lower() in faucet_filter_lower
            ]
        
        logger.info(f"📝 Registering {len(faucets_to_register)} faucet(s)")
        
        # Register each faucet
        for config in faucets_to_register:
            success = await register_single_faucet(
                browser_manager,
                settings,
                config,
                email,
                password
            )
            results[config.faucet_name] = success
            
        # Print summary
        logger.info(f"\n{'='*60}")
        logger.info("REGISTRATION SUMMARY")
        logger.info(f"{'='*60}")
        
        successful = [name for name, success in results.items() if success]
        failed = [name for name, success in results.items() if not success]
        
        logger.info(f"✅ Successful: {len(successful)}/{len(results)}")
        for name in successful:
            logger.info(f"   - {name}")
            
        if failed:
            logger.info(f"\n❌ Failed: {len(failed)}/{len(results)}")
            for name in failed:
                logger.info(f"   - {name}")
        
        logger.info(f"\n{'='*60}")
        
    except Exception as e:
        logger.error(f"Fatal error during registration process: {e}")
    finally:
        await browser_manager.close()


def main():
    """Main entry point for the registration script."""
    parser = argparse.ArgumentParser(
        description="Automated registration for Pick.io faucet family",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Register all 11 Pick.io faucets
  python register_faucets.py --email your@email.com --password yourpass123

  # Register specific faucets only
  python register_faucets.py --email your@email.com --password yourpass123 --faucets litepick tronpick

  # Show browser during registration (visible mode)
  python register_faucets.py --email your@email.com --password yourpass123 --visible
        """
    )
    
    parser.add_argument(
        "--email",
        required=True,
        help="Email address for registration"
    )
    
    parser.add_argument(
        "--password",
        required=True,
        help="Password for all accounts"
    )
    
    parser.add_argument(
        "--faucets",
        nargs="+",
        help="Specific faucets to register (e.g., litepick tronpick). If not specified, all faucets will be registered."
    )
    
    parser.add_argument(
        "--visible",
        action="store_true",
        help="Run browser in visible mode (not headless)"
    )
    
    parser.add_argument(
        "--log-level",
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        help="Logging level"
    )
    
    args = parser.parse_args()
    
    # Setup logging
    setup_logging(args.log_level)
    
    # Run registration
    asyncio.run(register_all_faucets(
        email=args.email,
        password=args.password,
        faucet_filter=args.faucets,
        headless=not args.visible
    ))


if __name__ == "__main__":
    main()
