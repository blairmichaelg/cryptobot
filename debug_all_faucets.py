#!/usr/bin/env python
"""
Comprehensive Faucet Debugging Script

Tests each faucet individually and reports detailed status including:
- Browser launch success
- Navigation success
- Login success
- Claim attempt result
- Timer extraction
- Balance extraction

Usage:
    python debug_all_faucets.py                 # Test all faucets
    python debug_all_faucets.py --faucet fire   # Test specific faucet
    python debug_all_faucets.py --visible       # Run with visible browser
"""

import asyncio
import logging
import os
import sys
import time
import traceback
from datetime import datetime
from dataclasses import dataclass
from typing import Optional, Dict, List

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(name)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler('debug_all_faucets.log', mode='w', encoding='utf-8')
    ]
)
logger = logging.getLogger(__name__)

# Suppress noisy loggers
logging.getLogger("asyncio").setLevel(logging.WARNING)
logging.getLogger("playwright").setLevel(logging.WARNING)

@dataclass
class FaucetTestResult:
    """Result of testing a single faucet"""
    faucet_name: str
    has_account: bool = False
    browser_launched: bool = False
    navigation_success: bool = False
    cloudflare_passed: bool = False
    login_success: bool = False
    claim_attempted: bool = False
    claim_success: bool = False
    timer_extracted: Optional[float] = None
    balance_extracted: Optional[str] = None
    error_message: Optional[str] = None
    duration_seconds: float = 0.0


# Faucet registry with test order (easiest to hardest)
FAUCET_TEST_ORDER = [
    # Non-CF faucets (should work easily)
    ("firefaucet", "fire_faucet", "FireFaucet"),
    ("cointiply", "cointiply", "Cointiply"),
    ("dutchy", "dutchy", "DutchyCorp"),
    ("coinpayu", "coinpayu", "CoinPayU"),
    ("faucetcrypto", "faucetcrypto", "FaucetCrypto"),
    ("adbtc", "adbtc", "AdBTC"),
    ("freebitcoin", "freebitcoin", "FreeBitcoin"),
    # Pick.io family (have Turnstile)
    ("tronpick", "tronpick", "TronPick"),
    ("litepick", "litepick", "LitePick"),
    ("dogepick", "dogepick", "DogePick"),
    ("solpick", "solpick", "SolPick"),
    ("binpick", "binpick", "BinPick"),
    ("bchpick", "bchpick", "BCHPick"),
    ("tonpick", "tonpick", "TonPick"),
    ("polygonpick", "polygonpick", "PolygonPick"),
    ("dashpick", "dashpick", "DashPick"),
    ("ethpick", "ethpick", "EthPick"),
    ("usdpick", "usdpick", "USDPick"),
]


async def test_single_faucet(faucet_module: str, account_key: str, faucet_class_name: str, 
                             settings, visible: bool = True, timeout_seconds: int = 120) -> FaucetTestResult:
    """
    Test a single faucet end-to-end.
    
    Args:
        faucet_module: Module name (e.g., 'firefaucet')
        account_key: Key for settings.get_account() (e.g., 'fire_faucet')
        faucet_class_name: Display name for the faucet
        settings: BotSettings instance
        visible: Whether to run browser visibly
        timeout_seconds: Maximum time for test
        
    Returns:
        FaucetTestResult with detailed status
    """
    result = FaucetTestResult(faucet_name=faucet_class_name)
    start_time = time.time()
    page = None
    browser_manager = None
    
    try:
        # Check for account
        account = settings.get_account(account_key)
        if not account:
            result.error_message = f"No account configured for '{account_key}'"
            result.duration_seconds = time.time() - start_time
            return result
        result.has_account = True
        logger.info(f"[{faucet_class_name}] Account found: {account.get('username', 'unknown')}")
        
        # Import faucet class dynamically
        try:
            if faucet_module == "firefaucet":
                from faucets.firefaucet import FireFaucetBot as FaucetClass
            elif faucet_module == "cointiply":
                from faucets.cointiply import CointiplyBot as FaucetClass
            elif faucet_module == "dutchy":
                from faucets.dutchy import DutchyBot as FaucetClass
            elif faucet_module == "coinpayu":
                from faucets.coinpayu import CoinPayUBot as FaucetClass
            elif faucet_module == "faucetcrypto":
                from faucets.faucetcrypto import FaucetCryptoBot as FaucetClass
            elif faucet_module == "adbtc":
                from faucets.adbtc import AdBTCBot as FaucetClass
            elif faucet_module == "freebitcoin":
                from faucets.freebitcoin import FreeBitcoinBot as FaucetClass
            elif faucet_module == "tronpick":
                from faucets.tronpick import TronPickBot as FaucetClass
            elif faucet_module == "litepick":
                from faucets.litepick import LitePickBot as FaucetClass
            elif faucet_module == "dogepick":
                from faucets.dogepick import DogePickBot as FaucetClass
            elif faucet_module == "solpick":
                from faucets.solpick import SolPickBot as FaucetClass
            elif faucet_module == "binpick":
                from faucets.binpick import BinPickBot as FaucetClass
            elif faucet_module == "bchpick":
                from faucets.bchpick import BCHPickBot as FaucetClass
            elif faucet_module == "tonpick":
                from faucets.tonpick import TonPickBot as FaucetClass
            elif faucet_module == "polygonpick":
                from faucets.polygonpick import PolygonPickBot as FaucetClass
            elif faucet_module == "dashpick":
                from faucets.dashpick import DashPickBot as FaucetClass
            elif faucet_module == "ethpick":
                from faucets.ethpick import EthPickBot as FaucetClass
            elif faucet_module == "usdpick":
                from faucets.usdpick import USDPickBot as FaucetClass
            else:
                result.error_message = f"Unknown faucet module: {faucet_module}"
                return result
        except ImportError as e:
            result.error_message = f"Failed to import {faucet_module}: {e}"
            return result
        
        # Launch browser
        logger.info(f"[{faucet_class_name}] Launching browser (visible={visible})...")
        from browser.instance import BrowserManager
        browser_manager = BrowserManager(headless=not visible)
        await browser_manager.launch()
        
        # Create context and get page
        context_key = f"{faucet_module}_{account.get('username', 'default')}"
        context = await browser_manager.create_context(profile_name=context_key)
        page = await browser_manager.new_page(context)
        result.browser_launched = True
        logger.info(f"[{faucet_class_name}] ✅ Browser launched successfully")
        
        # Create bot instance
        bot = FaucetClass(settings, page)
        bot.settings_account_override = account
        
        # Test 1: Navigate to base URL
        logger.info(f"[{faucet_class_name}] Testing navigation to {bot.base_url}...")
        try:
            await page.goto(bot.base_url, wait_until="domcontentloaded", timeout=30000)
            result.navigation_success = True
            logger.info(f"[{faucet_class_name}] ✅ Navigation successful")
        except Exception as nav_err:
            result.error_message = f"Navigation failed: {str(nav_err)[:100]}"
            logger.error(f"[{faucet_class_name}] ❌ Navigation failed: {nav_err}")
            return result
        
        # Test 2: Handle Cloudflare
        logger.info(f"[{faucet_class_name}] Checking for Cloudflare...")
        try:
            cf_result = await asyncio.wait_for(bot.handle_cloudflare(max_wait_seconds=30), timeout=35)
            result.cloudflare_passed = cf_result
            if cf_result:
                logger.info(f"[{faucet_class_name}] ✅ Cloudflare handled")
            else:
                logger.warning(f"[{faucet_class_name}] ⚠️ Cloudflare may be blocking")
        except asyncio.TimeoutError:
            logger.warning(f"[{faucet_class_name}] ⚠️ Cloudflare check timed out")
            result.cloudflare_passed = False
        except Exception as cf_err:
            logger.warning(f"[{faucet_class_name}] ⚠️ Cloudflare error: {cf_err}")
            result.cloudflare_passed = False
        
        # Test 3: Login
        logger.info(f"[{faucet_class_name}] Attempting login...")
        try:
            login_result = await asyncio.wait_for(bot.login(), timeout=90)
            result.login_success = login_result
            if login_result:
                logger.info(f"[{faucet_class_name}] ✅ LOGIN SUCCESS!")
            else:
                logger.error(f"[{faucet_class_name}] ❌ Login failed")
                result.error_message = "Login returned False"
        except asyncio.TimeoutError:
            logger.error(f"[{faucet_class_name}] ❌ Login timed out after 90s")
            result.error_message = "Login timeout"
        except Exception as login_err:
            logger.error(f"[{faucet_class_name}] ❌ Login exception: {login_err}")
            result.error_message = f"Login error: {str(login_err)[:100]}"
        
        # If login failed, skip claim
        if not result.login_success:
            return result
        
        # Test 4: Attempt claim
        logger.info(f"[{faucet_class_name}] Attempting claim...")
        result.claim_attempted = True
        try:
            claim_result = await asyncio.wait_for(bot.claim(), timeout=120)
            result.claim_success = claim_result.success
            result.timer_extracted = claim_result.next_claim_minutes
            result.balance_extracted = claim_result.balance
            
            if claim_result.success:
                logger.info(f"[{faucet_class_name}] ✅ CLAIM SUCCESS! Balance: {claim_result.balance}, Next: {claim_result.next_claim_minutes}min")
            else:
                logger.warning(f"[{faucet_class_name}] ⚠️ Claim status: {claim_result.status}")
                result.error_message = f"Claim: {claim_result.status}"
                
        except asyncio.TimeoutError:
            logger.error(f"[{faucet_class_name}] ❌ Claim timed out after 120s")
            result.error_message = "Claim timeout"
        except Exception as claim_err:
            logger.error(f"[{faucet_class_name}] ❌ Claim exception: {claim_err}")
            result.error_message = f"Claim error: {str(claim_err)[:100]}"
        
    except Exception as e:
        logger.error(f"[{faucet_class_name}] ❌ Test failed: {e}")
        result.error_message = str(e)[:200]
        traceback.print_exc()
        
    finally:
        result.duration_seconds = time.time() - start_time
        
        # Cleanup
        if browser_manager:
            try:
                await browser_manager.close()
            except Exception:
                pass
    
    return result


async def run_all_tests(faucet_filter: Optional[str] = None, visible: bool = True):
    """Run tests for all or filtered faucets."""
    
    from core.config import BotSettings
    settings = BotSettings()
    
    results: List[FaucetTestResult] = []
    
    # Determine which faucets to test
    if faucet_filter:
        test_faucets = [f for f in FAUCET_TEST_ORDER if faucet_filter.lower() in f[0].lower() or faucet_filter.lower() in f[2].lower()]
        if not test_faucets:
            logger.error(f"No faucet matches filter: {faucet_filter}")
            return results
    else:
        test_faucets = FAUCET_TEST_ORDER
    
    logger.info(f"\n{'='*60}")
    logger.info(f"FAUCET DEBUGGING SESSION - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    logger.info(f"Testing {len(test_faucets)} faucets")
    logger.info(f"{'='*60}\n")
    
    for faucet_module, account_key, faucet_name in test_faucets:
        logger.info(f"\n{'='*50}")
        logger.info(f"TESTING: {faucet_name}")
        logger.info(f"{'='*50}")
        
        result = await test_single_faucet(
            faucet_module=faucet_module,
            account_key=account_key,
            faucet_class_name=faucet_name,
            settings=settings,
            visible=visible,
            timeout_seconds=180
        )
        results.append(result)
        
        # Brief pause between faucets
        await asyncio.sleep(2)
    
    # Print summary
    print_summary(results)
    
    return results


def print_summary(results: List[FaucetTestResult]):
    """Print formatted summary of test results."""
    
    print(f"\n{'='*70}")
    print("FAUCET DEBUG SUMMARY")
    print(f"{'='*70}")
    print(f"{'Faucet':<20} {'Account':<8} {'Nav':<6} {'CF':<6} {'Login':<8} {'Claim':<8} {'Time':<8}")
    print(f"{'-'*70}")
    
    success_count = 0
    login_success_count = 0
    
    for r in results:
        account = "✅" if r.has_account else "❌"
        nav = "✅" if r.navigation_success else "❌"
        cf = "✅" if r.cloudflare_passed else "⚠️"
        login = "✅" if r.login_success else "❌"
        claim = "✅" if r.claim_success else ("⏳" if r.claim_attempted and not r.claim_success else "❌")
        time_str = f"{r.duration_seconds:.1f}s"
        
        print(f"{r.faucet_name:<20} {account:<8} {nav:<6} {cf:<6} {login:<8} {claim:<8} {time_str:<8}")
        
        if r.claim_success:
            success_count += 1
        if r.login_success:
            login_success_count += 1
    
    print(f"{'-'*70}")
    print(f"TOTAL: {len(results)} faucets tested")
    print(f"  ✅ Login Success: {login_success_count}/{len(results)}")
    print(f"  ✅ Claim Success: {success_count}/{len(results)}")
    print(f"{'='*70}")
    
    # Print failures detail
    failures = [r for r in results if r.error_message]
    if failures:
        print(f"\nFAILURE DETAILS:")
        print(f"{'-'*70}")
        for r in failures:
            print(f"  {r.faucet_name}: {r.error_message}")


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Debug all faucets")
    parser.add_argument("--faucet", "-f", help="Filter to specific faucet (partial match)")
    parser.add_argument("--visible", "-v", action="store_true", help="Run with visible browser")
    parser.add_argument("--headless", action="store_true", help="Run headless (no browser window)")
    
    args = parser.parse_args()
    
    # Check HEADLESS environment variable (for VM compatibility)
    env_headless = os.environ.get("HEADLESS", "").lower() in ("true", "1", "yes")
    
    # Priority: --headless flag > HEADLESS env var > --visible flag > default (headless on Linux, visible on Windows)
    if args.headless:
        visible = False
    elif env_headless:
        visible = False
    elif args.visible:
        visible = True
    else:
        # Default: headless on Linux (no DISPLAY), visible on Windows
        visible = sys.platform == "win32" or os.environ.get("DISPLAY") is not None
    
    logger.info(f"Browser mode: {'visible' if visible else 'headless'}")
    
    try:
        results = asyncio.run(run_all_tests(faucet_filter=args.faucet, visible=visible))
    except KeyboardInterrupt:
        print("\n\nTest interrupted by user")
    except Exception as e:
        print(f"\n\nTest failed with error: {e}")
        traceback.print_exc()
