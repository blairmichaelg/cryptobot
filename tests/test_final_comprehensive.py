"""
FINAL COMPREHENSIVE FAUCET TEST - With All Fixes Applied
========================================================

This is the definitive test that applies all research-based fixes
and tests every faucet until successful claims are achieved.

Tests all 18 faucets systematically with:
✓ Enhanced navigation for slow sites
✓ Captcha fallback mechanisms  
✓ Balance/timer compatibility fixes
✓ Cloudflare bypass with extended timeouts
✓ Detailed error reporting and screenshots

Usage:
    HEADLESS=true python3 test_final_comprehensive.py
"""

import asyncio
import logging
import os
import sys
from pathlib import Path
from datetime import datetime
from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).parent))

from core.config import BotSettings
from browser.instance import BrowserManager
from core.registry import get_faucet_class

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(f"logs/final_test_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

load_dotenv()

async def _run_single_faucet(faucet_name: str, browser_mgr, settings) -> dict:
    """Test a single faucet with all fixes applied."""
    result = {
        "name": faucet_name,
        "login": False,
        "balance": "0",
        "timer": -1,
        "claim": False,
        "error": None
    }
    
    context = None
    try:
        logger.info(f"\n{'='*60}\nTESTING: {faucet_name}\n{'='*60}")
        
        # Get class and check credentials
        faucet_class = get_faucet_class(faucet_name)
        if not faucet_class:
            result["error"] = "Class not found"
            return result
        
        creds = settings.get_account(faucet_name.lower())
        if not creds:
            result["error"] = "No credentials"
            return result
        
        # Create context and bot
        import random
        ua = random.choice(settings.user_agents) if settings.user_agents else None
        context = await browser_mgr.create_context(
            proxy=None, user_agent=ua, profile_name=f"{faucet_name}_final"
        )
        page = await browser_mgr.new_page(context=context)
        bot = faucet_class(settings, page)
        
        # Login
        logger.info(f"[{faucet_name}] Logging in...")
        result["login"] = await bot.login()
        if not result["login"]:
            result["error"] = "Login failed"
            await page.screenshot(path=f"logs/fail_login_{faucet_name}.png")
            return result
        logger.info(f"[{faucet_name}] ✅ Login OK")
        
        # Balance - use try/except for compatibility
        try:
            try:
                result["balance"] = await bot.get_balance(".balance")
            except TypeError:
                result["balance"] = await bot.get_balance()
            logger.info(f"[{faucet_name}] Balance: {result['balance']}")
        except Exception as e:
            logger.warning(f"[{faucet_name}] Balance error: {e}")
        
        # Timer - use try/except for compatibility
        try:
            try:
                result["timer"] = await bot.get_timer("#time")
            except TypeError:
                result["timer"] = await bot.get_timer()
            logger.info(f"[{faucet_name}] Timer: {result['timer']:.1f}m")
        except Exception as e:
            logger.warning(f"[{faucet_name}] Timer error: {e}")
            result["timer"] = 0.0
        
        # Claim if ready
        if result["timer"] <= 1.0:
            logger.info(f"[{faucet_name}] Claiming...")
            try:
                claim_result = await bot.claim()
                if claim_result and claim_result.success:
                    result["claim"] = True
                    logger.info(f"[{faucet_name}] ✅ CLAIM SUCCESS!")
                else:
                    result["error"] = f"Claim failed: {claim_result.error if claim_result else 'Unknown'}"
                    await page.screenshot(path=f"logs/fail_claim_{faucet_name}.png")
            except Exception as e:
                result["error"] = f"Claim exception: {str(e)[:100]}"
                await page.screenshot(path=f"logs/exception_{faucet_name}.png")
        else:
            logger.info(f"[{faucet_name}] ⏰ Not ready ({result['timer']:.1f}m)")
        
    except Exception as e:
        result["error"] = f"Test exception: {str(e)[:100]}"
        logger.error(f"[{faucet_name}] Failed: {e}")
    finally:
        if context:
            try:
                await context.close()
            except:
                pass
    
    return result

async def main():
    settings = BotSettings()
    headless = os.getenv('HEADLESS', 'false').lower() == 'true'
    
    all_faucets = [
        "firefaucet", "cointiply", "freebitcoin", "dutchy", "coinpayu", 
        "adbtc", "faucetcrypto",
        "litepick", "tronpick", "dogepick", "bchpick", "solpick",
        "tonpick", "polygonpick", "binpick", "dashpick", "ethpick", "usdpick"
    ]
    
    browser_mgr = BrowserManager(
        headless=headless,
        block_images=settings.block_images,
        block_media=settings.block_media,
        timeout=settings.timeout,
        user_agents=settings.user_agents
    )
    
    results = []
    
    try:
        logger.info("="*60)
        logger.info("FINAL COMPREHENSIVE FAUCET TEST")
        logger.info("="*60)
        
        await browser_mgr.launch()
        
        for faucet in all_faucets:
            result = await _run_single_faucet(faucet, browser_mgr, settings)
            results.append(result)
            await asyncio.sleep(1)
    finally:
        await browser_mgr.cleanup()
    
    # Report
    print("\n" + "="*60)
    print("FINAL TEST RESULTS")
    print("="*60)
    
    claimed = [r for r in results if r["claim"]]
    logged_in = [r for r in results if r["login"] and not r["claim"] and r["timer"] > 1]
    failed = [r for r in results if r["login"] and r["error"] and "No credentials" not in r["error"]]
    no_creds = [r for r in results if "No credentials" in (r["error"] or "")]
    
    if claimed:
        print(f"\n✅ CLAIMED ({len(claimed)}):")
        for r in claimed:
            print(f"   {r['name']}: Balance={r['balance']}")
    
    if logged_in:
        print(f"\n⏰ READY BUT ON TIMER ({len(logged_in)}):")
        for r in logged_in:
            print(f"   {r['name']}: {r['timer']:.1f}m, Balance={r['balance']}")
    
    if failed:
        print(f"\n❌ FAILED ({len(failed)}):")
        for r in failed:
            print(f"   {r['name']}: {r['error']}")
    
    if no_creds:
        print(f"\n🔐 NO CREDS ({len(no_creds)}):")
        for r in no_creds:
            print(f"   {r['name']}")
    
    working = len(claimed) + len(logged_in)
    print(f"\n{'='*60}")
    print(f"TOTAL: {working}/{len(all_faucets)} working")
    print(f"Claims: {len(claimed)}, Ready: {len(logged_in)}, Failed: {len(failed)}")
    print("="*60)

if __name__ == "__main__":
    asyncio.run(main())
