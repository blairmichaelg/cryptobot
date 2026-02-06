#!/usr/bin/env python3
"""
Comprehensive faucet testing script.
Tests each faucet systematically: login → claim → verify.

Usage:
    HEADLESS=true python scripts/test_all_faucets.py
    HEADLESS=true python scripts/test_all_faucets.py --faucet firefaucet
    HEADLESS=true python scripts/test_all_faucets.py --quick  # Skip claim, just test login
"""

import asyncio
import logging
import sys
import os
import argparse
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from core.config import BotSettings
from core.registry import FaucetRegistry
from browser.instance import BrowserManager
from faucets.base import ClaimResult

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class FaucetTester:
    """Systematic faucet testing."""
    
    def __init__(self, settings: BotSettings, quick_mode: bool = False):
        self.settings = settings
        self.quick_mode = quick_mode
        self.results = {}
        
    async def test_faucet(self, faucet_name: str) -> dict:
        """Test a single faucet end-to-end."""
        logger.info(f"{'='*80}")
        logger.info(f"Testing {faucet_name}")
        logger.info(f"{'='*80}")
        
        result = {
            "faucet": faucet_name,
            "import": False,
            "credentials": False,
            "login": False,
            "balance": None,
            "timer": None,
            "claim": False,
            "errors": []
        }
        
        # Test 1: Import
        try:
            factory = FaucetRegistry()
            bot_class = factory.get_faucet_class(faucet_name)
            result["import"] = True
            logger.info(f"✅ {faucet_name}: Import successful")
        except Exception as e:
            result["errors"].append(f"Import failed: {e}")
            logger.error(f"❌ {faucet_name}: Import failed - {e}")
            return result
            
        # Test 2: Credentials
        try:
            creds = self.settings.get_account(faucet_name.lower())
            if creds and creds.get("username") and creds.get("password"):
                result["credentials"] = True
                logger.info(f"✅ {faucet_name}: Credentials found")
            else:
                result["errors"].append("Credentials missing or incomplete")
                logger.error(f"❌ {faucet_name}: Credentials missing")
                return result
        except Exception as e:
            result["errors"].append(f"Credential check failed: {e}")
            logger.error(f"❌ {faucet_name}: Credential check failed - {e}")
            return result
            
        # Test 3: Browser test (login, claim)
        browser = None
        page = None
        bot = None
        
        try:
            # Initialize browser
            headless = os.getenv("HEADLESS", "true").lower() == "true"
            browser = BrowserManager(headless=headless, timeout=180000)
            
            logger.info(f"🌐 {faucet_name}: Starting browser...")
            await browser.start()
            
            # Create page
            page = await browser.new_page(profile_name=f"test_{faucet_name.lower()}")
            
            # Initialize bot
            bot = factory.create_faucet(faucet_name, self.settings, page)
            
            # Test login
            logger.info(f"🔐 {faucet_name}: Testing login...")
            login_success = await bot.login()
            
            if login_success:
                result["login"] = True
                logger.info(f"✅ {faucet_name}: Login successful")
                
                if self.quick_mode:
                    logger.info(f"⏭️  {faucet_name}: Quick mode - skipping claim test")
                else:
                    # Test claim
                    logger.info(f"💰 {faucet_name}: Testing claim...")
                    try:
                        claim_result = await bot.claim()
                        
                        result["balance"] = getattr(claim_result, "balance", None)
                        result["timer"] = getattr(claim_result, "next_claim_minutes", None)
                        
                        if claim_result.success:
                            result["claim"] = True
                            logger.info(f"✅ {faucet_name}: Claim successful - {claim_result.status}")
                        else:
                            result["errors"].append(f"Claim failed: {claim_result.status}")
                            logger.warning(f"⚠️  {faucet_name}: Claim failed - {claim_result.status}")
                            
                    except Exception as e:
                        result["errors"].append(f"Claim exception: {e}")
                        logger.error(f"❌ {faucet_name}: Claim exception - {e}")
            else:
                result["errors"].append("Login returned False")
                logger.error(f"❌ {faucet_name}: Login failed")
                
        except Exception as e:
            result["errors"].append(f"Browser test exception: {e}")
            logger.error(f"❌ {faucet_name}: Browser test exception - {e}")
            
        finally:
            # Cleanup
            try:
                if page:
                    await page.close()
                if browser:
                    await browser.close()
            except Exception as e:
                logger.warning(f"Cleanup error for {faucet_name}: {e}")
                
        return result
        
    async def test_all(self, faucet_filter: str = None):
        """Test all faucets or a specific one."""
        
        # Get list of faucets
        all_faucets = [
            "FireFaucet",
            "Cointiply",
            "FreeBitcoin",
            "DutchyCorp",
            "CoinPayU",
            "AdBTC",
            "FaucetCrypto",
            "LitePick",
            "TronPick",
            "DogePick",
            "SolPick",
            "BinPick",
            "BchPick",
            "TonPick",
            "PolygonPick",
            "DashPick",
            "EthPick",
            "UsdPick",
        ]
        
        # Filter if requested
        if faucet_filter:
            faucets_to_test = [f for f in all_faucets if f.lower() == faucet_filter.lower()]
            if not faucets_to_test:
                logger.error(f"Faucet '{faucet_filter}' not found")
                return
        else:
            faucets_to_test = all_faucets
            
        logger.info(f"Testing {len(faucets_to_test)} faucet(s)")
        
        # Test each faucet
        for faucet in faucets_to_test:
            result = await self.test_faucet(faucet)
            self.results[faucet] = result
            
        # Print summary
        self.print_summary()
        
    def print_summary(self):
        """Print test results summary."""
        logger.info(f"\n{'='*80}")
        logger.info("TEST SUMMARY")
        logger.info(f"{'='*80}\n")
        
        total = len(self.results)
        imports_ok = sum(1 for r in self.results.values() if r["import"])
        creds_ok = sum(1 for r in self.results.values() if r["credentials"])
        logins_ok = sum(1 for r in self.results.values() if r["login"])
        claims_ok = sum(1 for r in self.results.values() if r["claim"])
        
        logger.info(f"Total Faucets:   {total}")
        logger.info(f"Imports OK:      {imports_ok}/{total}")
        logger.info(f"Credentials OK:  {creds_ok}/{total}")
        logger.info(f"Logins OK:       {logins_ok}/{total}")
        logger.info(f"Claims OK:       {claims_ok}/{total}")
        logger.info("")
        
        # Detailed results
        for faucet, result in self.results.items():
            status_icons = []
            status_icons.append("✅" if result["import"] else "❌")
            status_icons.append("✅" if result["credentials"] else "❌")
            status_icons.append("✅" if result["login"] else "❌")
            
            if not self.quick_mode:
                status_icons.append("✅" if result["claim"] else "❌")
            
            status = " ".join(status_icons)
            
            logger.info(f"{faucet:15} {status}")
            
            if result["errors"]:
                for error in result["errors"]:
                    logger.info(f"  └─ {error}")
                    
        logger.info(f"\n{'='*80}")
        
        # Return exit code
        if self.quick_mode:
            return 0 if logins_ok == total else 1
        else:
            return 0 if claims_ok == total else 1


async def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(description="Test all faucets systematically")
    parser.add_argument("--faucet", "-f", help="Test specific faucet only")
    parser.add_argument("--quick", "-q", action="store_true", help="Quick mode: test login only")
    args = parser.parse_args()
    
    # Load settings
    settings = BotSettings()
    
    # Create tester
    tester = FaucetTester(settings, quick_mode=args.quick)
    
    # Run tests
    await tester.test_all(faucet_filter=args.faucet)
    
    # Return exit code
    return tester.print_summary()


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
