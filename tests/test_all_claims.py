#!/usr/bin/env python3
"""
Comprehensive Faucet Claim Test
Tests each faucet's complete claim cycle: login → claim → report results
"""
import asyncio
import logging
import os
import sys
from pathlib import Path
from datetime import datetime

# Setup path
sys.path.insert(0, str(Path(__file__).parent))

from browser.instance import BrowserManager
from core.config import BotSettings
from core.registry import get_faucet_class

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(f'logs/claim_test_{datetime.now().strftime("%Y%m%d_%H%M%S")}.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

async def test_single_faucet_claim(faucet_name: str, browser_mgr, settings) -> dict:
    """
    Test a single faucet's complete claim cycle.
    
    Returns dict with: name, success, status, error, next_claim_minutes
    """
    result = {
        'name': faucet_name,
        'success': False,
        'status': 'not_started',
        'error': None,
        'next_claim_minutes': None,
        'balance': None
    }
    
    context = None
    page = None
    
    try:
        logger.info(f"\n{'='*60}\nTESTING CLAIM: {faucet_name}\n{'='*60}")
        
        # Get credentials
        creds = settings.get_account(faucet_name)
        if not creds:
            result['status'] = 'no_credentials'
            logger.warning(f"[{faucet_name}] No credentials configured")
            return result
        
        # Create isolated browser context
        # Use empty profile name to avoid loading stale cookies
        context = await browser_mgr.create_context(
            profile_name=None,  # Fresh context without old cookies
            proxy=None  # Use direct connection first, proxies can be enabled later
        )
        page = await context.new_page()
        
        # Initialize bot
        bot_class = get_faucet_class(faucet_name)
        if not bot_class:
            result['status'] = 'no_bot_class'
            result['error'] = 'Bot not registered'
            logger.error(f"[{faucet_name}] Bot class not found in registry")
            return result
        
        bot = bot_class(settings, page)
        
        # Set credentials (the bot's login() method uses settings_account_override)
        bot.settings_account_override = {
            'username': creds['username'],
            'password': creds['password']
        }
        
        # Login
        logger.info(f"[{faucet_name}] Attempting login...")
        login_success = await bot.login()
        
        if not login_success:
            result['status'] = 'login_failed'
            result['error'] = 'Login returned False'
            logger.error(f"[{faucet_name}] ❌ Login failed")
            # Screenshot
            try:
                await page.screenshot(path=f"logs/claim_fail_{faucet_name}_login.png", full_page=True)
            except:
                pass
            return result
        
        logger.info(f"[{faucet_name}] ✅ Login successful")
        
        # Claim
        logger.info(f"[{faucet_name}] Attempting claim...")
        claim_result = await bot.claim()
        
        if not claim_result:
            result['status'] = 'claim_returned_none'
            result['error'] = 'claim() returned None'
            logger.error(f"[{faucet_name}] ❌ Claim returned None")
            return result
        
        # Parse result
        result['success'] = claim_result.success
        result['status'] = claim_result.status
        result['error'] = getattr(claim_result, 'message', getattr(claim_result, 'error', None))
        result['next_claim_minutes'] = claim_result.next_claim_minutes
        result['balance'] = getattr(claim_result, 'balance', None)
        
        if claim_result.success:
            logger.info(f"[{faucet_name}] ✅ CLAIM SUCCESS - Status: {claim_result.status}, Balance: {claim_result.balance}, Next: {claim_result.next_claim_minutes}m")
        else:
            error_msg = result['error'] or claim_result.status
            logger.warning(f"[{faucet_name}] ⚠️ Claim unsuccessful - Status: {claim_result.status}, Error: {error_msg}")
            # Screenshot on failure
            try:
                await page.screenshot(path=f"logs/claim_fail_{faucet_name}.png", full_page=True)
            except:
                pass
        
        return result
        
    except Exception as e:
        result['status'] = 'exception'
        result['error'] = str(e)[:200]
        logger.error(f"[{faucet_name}] ❌ Exception: {e}", exc_info=True)
        
        # Screenshot
        if page:
            try:
                await page.screenshot(path=f"logs/claim_fail_{faucet_name}_exception.png", full_page=True)
            except:
                pass
        
        return result
        
    finally:
        # Cleanup
        if context:
            try:
                await context.close()
            except:
                pass


async def main():
    """Run comprehensive claim tests on all faucets."""
    settings = BotSettings()
    headless = os.getenv('HEADLESS', 'false').lower() == 'true'
    
    # All faucets (18 total: 7 standalone + 11 Pick.io family)
    all_faucets = [
        # Standalone faucets (7)
        "firefaucet",
        "cointiply",
        "freebitcoin",
        "dutchy",
        "coinpayu",
        "adbtc",
        "faucetcrypto",
        
        # Pick.io family (11) - all inherit login from pick_base.py
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
    
    logger.info("="*60)
    logger.info("COMPREHENSIVE FAUCET CLAIM TEST")
    logger.info(f"Testing {len(all_faucets)} faucets")
    logger.info("="*60)
    
    # Launch browser
    logger.info(f"Launching Camoufox (Headless: {headless})...")
    browser_mgr = BrowserManager(headless=headless)
    await browser_mgr.launch()
    
    results = []
    
    try:
        # Test each faucet
        for faucet_name in all_faucets:
            result = await test_single_faucet_claim(faucet_name, browser_mgr, settings)
            results.append(result)
            
            # Brief pause between faucets
            await asyncio.sleep(2)
        
    finally:
        # Cleanup
        await browser_mgr.close()
    
    # Summary
    logger.info("\n" + "="*60)
    logger.info("FINAL CLAIM TEST RESULTS")
    logger.info("="*60)
    
    success_count = sum(1 for r in results if r['success'])
    ready_count = sum(1 for r in results if r['status'] in ['Timer Active', 'Already Claimed'] and not r['success'])
    no_creds = sum(1 for r in results if r['status'] == 'no_credentials')
    failed_count = len(results) - success_count - ready_count - no_creds
    
    logger.info(f"\n✅ Successfully Claimed: {success_count}/{len(results)}")
    logger.info(f"⏰ Ready but not claimed (timer active): {ready_count}/{len(results)}")
    logger.info(f"❌ Failed: {failed_count}/{len(results)}")
    logger.info(f"⚠️ No Credentials: {no_creds}/{len(results)}\n")
    
    # Detailed breakdown
    logger.info("DETAILED BREAKDOWN:")
    logger.info("-" * 60)
    for r in results:
        status_emoji = "✅" if r['success'] else ("⏰" if r['status'] in ['Timer Active', 'Already Claimed'] else "❌")
        logger.info(f"{status_emoji} {r['name']:15} - {r['status']:20} - Next: {r['next_claim_minutes'] or 'N/A'}m")
        if r['error']:
            logger.info(f"    Error: {r['error'][:100]}")
    
    logger.info("\n" + "="*60)
    logger.info(f"Test completed. Check logs/claim_test_*.log for details")
    logger.info("="*60)


if __name__ == "__main__":
    asyncio.run(main())
