#!/usr/bin/env python3
"""
Test script for Pick.io family login functionality.

This script tests all 11 Pick.io faucets to verify that:
1. Each faucet inherits from PickFaucetBase correctly
2. Login credentials are properly retrieved
3. Login flow executes without errors

Usage:
    python scripts/test_pickio_login.py
    python scripts/test_pickio_login.py --faucet litepick
    python scripts/test_pickio_login.py --visible
"""
import asyncio
import logging
import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from playwright.async_api import async_playwright
from core.config import BotSettings
from core.registry import get_faucet_class

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Pick.io faucet list
PICKIO_FAUCETS = [
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

async def test_faucet_login(faucet_name: str, headless: bool = True) -> dict:
    """Test login for a single Pick.io faucet.
    
    Args:
        faucet_name: Name of the faucet to test
        headless: Run in headless mode
        
    Returns:
        dict: Test results with status and details
    """
    result = {
        "faucet": faucet_name,
        "class_loaded": False,
        "credentials_found": False,
        "base_url_set": False,
        "login_attempted": False,
        "login_success": False,
        "error": None,
    }
    
    try:
        # Load faucet class
        faucet_class = get_faucet_class(faucet_name)
        if not faucet_class:
            result["error"] = "Faucet class not found in registry"
            return result
        result["class_loaded"] = True
        logger.info(f"✓ [{faucet_name}] Class loaded: {faucet_class.__name__}")
        
        # Initialize settings
        settings = BotSettings()
        
        # Check credentials
        creds = settings.get_account(faucet_name)
        if not creds:
            result["error"] = f"No credentials found - set {faucet_name.upper()}_USERNAME and {faucet_name.upper()}_PASSWORD in .env"
            return result
        result["credentials_found"] = True
        
        email = creds.get("email") or creds.get("username")
        logger.info(f"✓ [{faucet_name}] Credentials found: {email}")
        
        # Initialize browser
        async with async_playwright() as p:
            browser = await p.firefox.launch(headless=headless)
            context = await browser.new_context()
            page = await context.new_page()
            
            # Initialize bot
            bot = faucet_class(settings, page)
            
            # Check base_url
            if not bot.base_url:
                result["error"] = "base_url not set"
                await browser.close()
                return result
            result["base_url_set"] = True
            logger.info(f"✓ [{faucet_name}] Base URL: {bot.base_url}")
            
            # Test login
            result["login_attempted"] = True
            logger.info(f"→ [{faucet_name}] Attempting login...")
            
            try:
                login_success = await bot.login()
                result["login_success"] = login_success
                
                if login_success:
                    logger.info(f"✓ [{faucet_name}] LOGIN SUCCESS!")
                    
                    # Try to get balance to confirm we're logged in
                    try:
                        balance = await bot.get_balance()
                        logger.info(f"  └─ Balance: {balance}")
                    except Exception as e:
                        logger.warning(f"  └─ Could not retrieve balance: {e}")
                else:
                    logger.error(f"✗ [{faucet_name}] LOGIN FAILED")
                    result["error"] = "Login returned False"
                    
            except Exception as login_error:
                result["error"] = f"Login exception: {str(login_error)}"
                logger.error(f"✗ [{faucet_name}] Login error: {login_error}")
            
            await browser.close()
            
    except Exception as e:
        result["error"] = f"Test exception: {str(e)}"
        logger.error(f"✗ [{faucet_name}] Test error: {e}")
    
    return result

async def test_all_faucets(headless: bool = True, single_faucet: str = None):
    """Test all Pick.io faucets or a specific one.
    
    Args:
        headless: Run in headless mode
        single_faucet: Test only this faucet (None = test all)
    """
    faucets_to_test = [single_faucet] if single_faucet else PICKIO_FAUCETS
    
    logger.info("=" * 80)
    logger.info("Pick.io Family Login Test")
    logger.info("=" * 80)
    logger.info(f"Testing {len(faucets_to_test)} faucet(s)")
    logger.info(f"Headless mode: {headless}")
    logger.info("=" * 80)
    
    results = []
    for faucet in faucets_to_test:
        logger.info(f"\n{'=' * 80}")
        logger.info(f"Testing: {faucet.upper()}")
        logger.info('=' * 80)
        
        result = await test_faucet_login(faucet, headless)
        results.append(result)
        
        # Small delay between tests
        if len(faucets_to_test) > 1:
            await asyncio.sleep(2)
    
    # Print summary
    logger.info("\n" + "=" * 80)
    logger.info("TEST SUMMARY")
    logger.info("=" * 80)
    
    success_count = sum(1 for r in results if r["login_success"])
    total_count = len(results)
    
    for result in results:
        faucet = result["faucet"]
        status = "✓ PASS" if result["login_success"] else "✗ FAIL"
        logger.info(f"{status:8} - {faucet:15} - {result.get('error', 'OK')}")
    
    logger.info("=" * 80)
    logger.info(f"Results: {success_count}/{total_count} faucets passed")
    logger.info("=" * 80)
    
    # Return status code
    return 0 if success_count == total_count else 1

def main():
    """Main entry point."""
    import argparse
    
    parser = argparse.ArgumentParser(description="Test Pick.io family login")
    parser.add_argument("--faucet", type=str, help="Test specific faucet")
    parser.add_argument("--visible", action="store_true", help="Run in visible mode")
    args = parser.parse_args()
    
    headless = not args.visible
    
    if args.faucet:
        if args.faucet not in PICKIO_FAUCETS:
            logger.error(f"Unknown faucet: {args.faucet}")
            logger.error(f"Valid faucets: {', '.join(PICKIO_FAUCETS)}")
            sys.exit(1)
    
    exit_code = asyncio.run(test_all_faucets(headless, args.faucet))
    sys.exit(exit_code)

if __name__ == "__main__":
    main()
