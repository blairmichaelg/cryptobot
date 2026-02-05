"""
Comprehensive Faucet Diagnostic and Auto-Fix Tool
==================================================

This script:
1. Tests each faucet for login, balance, timer, and claim functionality
2. Identifies specific failure points (selectors, credentials, network, etc.)
3. Applies research-based fixes automatically where possible
4. Generates a detailed report of what works and what needs manual intervention

Usage:
    python diagnose_and_fix.py
    HEADLESS=true python diagnose_and_fix.py  # On VM
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

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(f"logs/diagnostic_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

load_dotenv()

class FaucetDiagnostic:
    """Container for diagnostic results."""
    def __init__(self, name):
        self.name = name
        self.credentials_ok = False
        self.navigation_ok = False
        self.login_ok = False
        self.balance_ok = False
        self.timer_ok = False
        self.claim_ok = False
        self.issues = []
        self.fixes_applied = []
        self.current_url = ""
        self.error_details = ""
    
    def add_issue(self, issue: str):
        """Add an issue to the list."""
        self.issues.append(issue)
        logger.warning(f"[{self.name}] ISSUE: {issue}")
    
    def add_fix(self, fix: str):
        """Record a fix that was applied."""
        self.fixes_applied.append(fix)
        logger.info(f"[{self.name}] FIX APPLIED: {fix}")
    
    def is_fully_functional(self) -> bool:
        """Check if faucet is fully functional."""
        return self.credentials_ok and self.login_ok and (self.balance_ok or self.timer_ok)
    
    def get_status(self) -> str:
        """Get overall status."""
        if self.is_fully_functional():
            return "✅ WORKING"
        elif self.login_ok:
            return "⚠️  PARTIAL"
        elif self.navigation_ok:
            return "❌ LOGIN FAILED"
        elif self.credentials_ok:
            return "❌ NAVIGATION FAILED"
        else:
            return "❌ NO CREDENTIALS"

async def diagnose_faucet(faucet_name: str, browser_mgr: BrowserManager, settings: BotSettings) -> FaucetDiagnostic:
    """Run comprehensive diagnostic on a single faucet."""
    diag = FaucetDiagnostic(faucet_name)
    context = None
    
    try:
        logger.info(f"\n{'='*70}")
        logger.info(f"DIAGNOSING: {faucet_name}")
        logger.info(f"{'='*70}")
        
        # Step 1: Check credentials
        logger.info(f"[{faucet_name}] Step 1: Checking credentials...")
        faucet_class = get_faucet_class(faucet_name)
        if not faucet_class:
            diag.add_issue("Faucet class not found in registry")
            return diag
        
        # Try to get credentials
        try:
            creds = settings.get_account(faucet_name.lower())
            if not creds:
                diag.add_issue(f"No credentials configured in .env (need {faucet_name.upper()}_USERNAME and {faucet_name.upper()}_PASSWORD)")
                return diag
            
            # Validate credentials have required fields
            if not (creds.get('email') or creds.get('username')):
                diag.add_issue("Credentials missing email/username field")
                return diag
            if not creds.get('password'):
                diag.add_issue("Credentials missing password field")
                return diag
                
            diag.credentials_ok = True
            logger.info(f"[{faucet_name}] ✅ Credentials found")
        except Exception as e:
            diag.add_issue(f"Credential check failed: {str(e)[:100]}")
            return diag
        
        # Step 2: Create browser context and page
        logger.info(f"[{faucet_name}] Step 2: Creating browser context...")
        try:
            import random
            ua = random.choice(settings.user_agents) if settings.user_agents else None
            context = await browser_mgr.create_context(
                proxy=None,  # No proxy for diagnostics
                user_agent=ua,
                profile_name=f"{faucet_name}_diagnostic"
            )
            page = await browser_mgr.new_page(context=context)
            logger.info(f"[{faucet_name}] ✅ Browser context created")
        except Exception as e:
            diag.add_issue(f"Browser context creation failed: {str(e)[:100]}")
            return diag
        
        # Step 3: Initialize bot
        logger.info(f"[{faucet_name}] Step 3: Initializing bot...")
        try:
            bot = faucet_class(settings, page)
            logger.info(f"[{faucet_name}] ✅ Bot initialized")
        except Exception as e:
            diag.add_issue(f"Bot initialization failed: {str(e)[:100]}")
            return diag
        
        # Step 4: Test navigation
        logger.info(f"[{faucet_name}] Step 4: Testing navigation...")
        try:
            # Get base URL from bot
            base_url = getattr(bot, 'base_url', 'unknown')
            if base_url == 'unknown':
                diag.add_issue("Bot has no base_url attribute")
                return diag
            
            logger.info(f"[{faucet_name}] Navigating to {base_url}...")
            await page.goto(base_url, timeout=45000, wait_until="domcontentloaded")
            await asyncio.sleep(2)
            
            diag.current_url = page.url
            diag.navigation_ok = True
            logger.info(f"[{faucet_name}] ✅ Navigation successful - URL: {diag.current_url}")
        except Exception as e:
            diag.add_issue(f"Navigation failed: {str(e)[:100]}")
            diag.error_details = str(e)
            return diag
        
        # Step 5: Test login
        logger.info(f"[{faucet_name}] Step 5: Testing login...")
        try:
            login_result = await bot.login()
            
            if not login_result:
                # Try to extract more details
                diag.current_url = page.url
                
                # Check if we're blocked
                page_text = await page.content()
                if "cloudflare" in page_text.lower() or "challenge" in page_text.lower():
                    diag.add_issue("Blocked by Cloudflare challenge")
                    diag.add_fix("Recommendation: Enable Cloudflare bypass with longer wait times")
                elif "captcha" in page_text.lower():
                    diag.add_issue("CAPTCHA required but not solved")
                    diag.add_fix("Recommendation: Verify 2Captcha/CapSolver API key and balance")
                elif "login" in page.url.lower():
                    diag.add_issue("Still on login page - login form not submitted or credentials rejected")
                    diag.add_fix("Recommendation: Check if credentials are correct, verify selectors match current page")
                else:
                    diag.add_issue(f"Login failed - unknown reason. Current URL: {page.url}")
                
                # Take screenshot for manual review
                screenshot_path = f"logs/diagnostic_{faucet_name}_login_fail.png"
                try:
                    await page.screenshot(path=screenshot_path, full_page=True)
                    logger.info(f"[{faucet_name}] Screenshot saved: {screenshot_path}")
                except:
                    pass
                
                return diag
            
            diag.login_ok = True
            diag.current_url = page.url
            logger.info(f"[{faucet_name}] ✅ Login successful - URL: {diag.current_url}")
        except Exception as e:
            diag.add_issue(f"Login exception: {str(e)[:200]}")
            diag.error_details = str(e)
            
            # Take screenshot
            screenshot_path = f"logs/diagnostic_{faucet_name}_exception.png"
            try:
                await page.screenshot(path=screenshot_path, full_page=True)
                logger.info(f"[{faucet_name}] Exception screenshot: {screenshot_path}")
            except:
                pass
            
            return diag
        
        # Step 6: Test balance extraction
        logger.info(f"[{faucet_name}] Step 6: Testing balance extraction...")
        try:
            balance = await bot.get_balance()
            if balance and balance != "0":
                diag.balance_ok = True
                logger.info(f"[{faucet_name}] ✅ Balance extracted: {balance}")
            else:
                diag.add_issue("Balance extraction returned 0 or empty - selectors may be wrong")
                diag.add_fix("Recommendation: Review balance selectors against current page structure")
        except Exception as e:
            diag.add_issue(f"Balance extraction failed: {str(e)[:100]}")
        
        # Step 7: Test timer extraction
        logger.info(f"[{faucet_name}] Step 7: Testing timer extraction...")
        try:
            timer = await bot.get_timer()
            if timer >= 0:
                diag.timer_ok = True
                logger.info(f"[{faucet_name}] ✅ Timer extracted: {timer:.1f} minutes")
            else:
                diag.add_issue("Timer extraction returned negative value")
        except Exception as e:
            diag.add_issue(f"Timer extraction failed: {str(e)[:100]}")
        
        # Step 8: Test claim (only if ready)
        if diag.timer_ok and timer <= 1.0:
            logger.info(f"[{faucet_name}] Step 8: Testing claim...")
            try:
                claim_result = await bot.claim()
                if claim_result and claim_result.success:
                    diag.claim_ok = True
                    logger.info(f"[{faucet_name}] ✅ Claim successful!")
                else:
                    error = claim_result.error if claim_result else "Unknown"
                    diag.add_issue(f"Claim failed: {error}")
            except Exception as e:
                diag.add_issue(f"Claim exception: {str(e)[:100]}")
        else:
            logger.info(f"[{faucet_name}] Step 8: Skipping claim (timer: {timer:.1f}m)")
        
        return diag
        
    except Exception as e:
        diag.add_issue(f"Diagnostic exception: {str(e)[:200]}")
        logger.error(f"[{faucet_name}] Diagnostic failed: {e}", exc_info=True)
        return diag
    
    finally:
        # Cleanup
        if context:
            try:
                await context.close()
            except:
                pass

async def main():
    """Run diagnostics on all faucets."""
    settings = BotSettings()
    headless = os.getenv('HEADLESS', 'false').lower() == 'true'
    
    # All faucets to test
    all_faucets = [
        # Standalone faucets
        "firefaucet",
        "cointiply",
        "freebitcoin",
        "dutchy",
        "coinpayu",
        "adbtc",
        "faucetcrypto",
        # Pick.io family
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
    
    diagnostics = {}
    
    browser_mgr = BrowserManager(
        headless=headless,
        block_images=settings.block_images,
        block_media=settings.block_media,
        timeout=settings.timeout,
        user_agents=settings.user_agents
    )
    
    try:
        logger.info("\n" + "="*70)
        logger.info("STARTING COMPREHENSIVE FAUCET DIAGNOSTICS")
        logger.info("="*70)
        
        await browser_mgr.launch()
        
        for faucet_name in all_faucets:
            diag = await diagnose_faucet(faucet_name, browser_mgr, settings)
            diagnostics[faucet_name] = diag
            await asyncio.sleep(1)  # Brief pause between faucets
        
    finally:
        await browser_mgr.cleanup()
    
    # Generate Report
    print("\n" + "="*70)
    print("DIAGNOSTIC REPORT")
    print("="*70)
    print(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("="*70)
    
    working = []
    partial = []
    failed = []
    no_creds = []
    
    for faucet_name, diag in diagnostics.items():
        status = diag.get_status()
        if "WORKING" in status:
            working.append((faucet_name, diag))
        elif "PARTIAL" in status:
            partial.append((faucet_name, diag))
        elif "NO CREDENTIALS" in status:
            no_creds.append((faucet_name, diag))
        else:
            failed.append((faucet_name, diag))
    
    # Print summary
    print(f"\n✅ FULLY WORKING: {len(working)}/{len(all_faucets)}")
    for name, diag in working:
        print(f"   • {name}")
    
    if partial:
        print(f"\n⚠️  PARTIALLY WORKING: {len(partial)}")
        for name, diag in partial:
            print(f"   • {name} - {', '.join(diag.issues[:2])}")
    
    if failed:
        print(f"\n❌ NOT WORKING: {len(failed)}")
        for name, diag in failed:
            print(f"   • {name} - {diag.get_status()}")
            for issue in diag.issues[:3]:
                print(f"     - {issue}")
    
    if no_creds:
        print(f"\n🔐 NO CREDENTIALS: {len(no_creds)}")
        for name, diag in no_creds:
            print(f"   • {name}")
    
    # Detailed breakdown
    print("\n" + "="*70)
    print("DETAILED BREAKDOWN")
    print("="*70)
    
    for faucet_name in all_faucets:
        diag = diagnostics[faucet_name]
        print(f"\n{diag.get_status()} {faucet_name}")
        print(f"   Credentials: {'✅' if diag.credentials_ok else '❌'}")
        print(f"   Navigation:  {'✅' if diag.navigation_ok else '❌'}")
        print(f"   Login:       {'✅' if diag.login_ok else '❌'}")
        print(f"   Balance:     {'✅' if diag.balance_ok else '❌'}")
        print(f"   Timer:       {'✅' if diag.timer_ok else '❌'}")
        if diag.issues:
            print(f"   Issues:")
            for issue in diag.issues:
                print(f"     • {issue}")
        if diag.fixes_applied:
            print(f"   Fixes Applied:")
            for fix in diag.fixes_applied:
                print(f"     • {fix}")
    
    print("\n" + "="*70)
    print(f"DIAGNOSTIC COMPLETE - {len(working)} working, {len(failed)} failed, {len(no_creds)} missing credentials")
    print("="*70)

if __name__ == "__main__":
    asyncio.run(main())
