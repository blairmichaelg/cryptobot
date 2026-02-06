#!/usr/bin/env python3
"""
Selector verification tool - checks if selectors still work on live faucet pages.
Navigates to each site and validates key selectors without logging in.

Usage:
    HEADLESS=false python scripts/verify_selectors.py  # Visual verification
    HEADLESS=true python scripts/verify_selectors.py --faucet firefaucet
"""

import asyncio
import logging
import sys
import os
import argparse
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from browser.instance import BrowserManager
from playwright.async_api import Page

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class SelectorVerifier:
    """Verify selectors on live pages."""
    
    # Define key selectors for each faucet
    FAUCET_SELECTORS = {
        "firefaucet": {
            "url": "https://firefaucet.win",
            "login_page_selectors": {
                "email_field": ["#email", "input[name='email']", "input[type='email']"],
                "password_field": ["#password", "input[name='password']", "input[type='password']"],
                "login_button": ["button:has-text('Login')", "button[type='submit']"],
            },
            "faucet_page_selectors": {
                "claim_button": ["#get_reward_button", "button:has-text('Get reward')"],
                "balance": [".user-balance", ".balance", "#balance"],
                "timer": ["#claim_timer", ".timer", "#time"],
            }
        },
        "freebitcoin": {
            "url": "https://freebitco.in",
            "login_page_selectors": {
                "login_trigger": ["a:has-text('LOGIN')", "a:has-text('Log In')"],
                "email_field": ["#login_form_btc_address", "input[name='btc_address']"],
                "password_field": ["#login_form_password", "input[name='password']"],
                "login_button": ["#login_button", "button:has-text('Login')"],
            }
        },
        "cointiply": {
            "url": "https://cointiply.com",
            "login_page_selectors": {
                "email_field": ["#email", "input[type='email']"],
                "password_field": ["#password", "input[type='password']"],
                "login_button": ["button:has-text('Login')", "button[type='submit']"],
            }
        },
        # Add more faucets as needed
    }
    
    async def verify_page(self, page: Page, url: str, selectors: dict, page_name: str) -> dict:
        """Verify selectors on a specific page."""
        results = {"url": url, "accessible": False, "selectors": {}}
        
        try:
            logger.info(f"Navigating to {url}...")
            response = await page.goto(url, wait_until="domcontentloaded", timeout=30000)
            
            if response and response.ok:
                results["accessible"] = True
                logger.info(f"✅ Page loaded: {url}")
            else:
                logger.warning(f"⚠️  Page load issue: {url} (status: {response.status if response else 'no response'})")
                results["accessible"] = False
                return results
                
            # Wait a bit for dynamic content
            await asyncio.sleep(3)
            
            # Check each selector group
            for selector_name, selector_list in selectors.items():
                found = False
                working_selector = None
                
                for selector in selector_list:
                    try:
                        count = await page.locator(selector).count()
                        if count > 0:
                            # Check if visible
                            is_visible = await page.locator(selector).first.is_visible(timeout=2000)
                            if is_visible:
                                found = True
                                working_selector = selector
                                logger.info(f"  ✅ {selector_name}: '{selector}' (found {count}, visible)")
                                break
                            else:
                                logger.debug(f"  ⚠️  {selector_name}: '{selector}' (found {count}, not visible)")
                    except Exception as e:
                        logger.debug(f"  ❌ {selector_name}: '{selector}' failed - {e}")
                        continue
                        
                results["selectors"][selector_name] = {
                    "found": found,
                    "working_selector": working_selector,
                    "attempted": selector_list
                }
                
                if not found:
                    logger.error(f"  ❌ {selector_name}: No working selector found!")
                    
        except Exception as e:
            logger.error(f"❌ Error verifying {url}: {e}")
            results["error"] = str(e)
            
        return results
        
    async def verify_faucet(self, faucet_name: str, browser: BrowserManager) -> dict:
        """Verify all pages for a faucet."""
        logger.info(f"\n{'='*80}")
        logger.info(f"Verifying selectors for {faucet_name.upper()}")
        logger.info(f"{'='*80}\n")
        
        if faucet_name.lower() not in self.FAUCET_SELECTORS:
            logger.error(f"No selector definitions for {faucet_name}")
            return {"error": "No selector definitions"}
            
        config = self.FAUCET_SELECTORS[faucet_name.lower()]
        results = {"faucet": faucet_name, "pages": {}}
        
        page = None
        try:
            page = await browser.new_page(profile_name=f"verify_{faucet_name.lower()}")
            
            # Verify login page
            if "login_page_selectors" in config:
                login_results = await self.verify_page(
                    page,
                    config["url"],
                    config["login_page_selectors"],
                    "login_page"
                )
                results["pages"]["login"] = login_results
                
            # Verify faucet/claim page (if different URL)
            if "faucet_page_selectors" in config:
                faucet_url = config.get("faucet_url", config["url"] + "/faucet")
                faucet_results = await self.verify_page(
                    page,
                    faucet_url,
                    config["faucet_page_selectors"],
                    "faucet_page"
                )
                results["pages"]["faucet"] = faucet_results
                
        finally:
            if page:
                try:
                    await page.close()
                except:
                    pass
                    
        return results
        
    async def verify_all(self, faucet_filter: str = None):
        """Verify all faucets or a specific one."""
        headless = os.getenv("HEADLESS", "false").lower() == "true"
        browser = BrowserManager(headless=headless, timeout=60000)
        
        try:
            logger.info("Starting browser...")
            await browser.start()
            
            # Get faucets to verify
            if faucet_filter:
                faucets = [f for f in self.FAUCET_SELECTORS.keys() if f.lower() == faucet_filter.lower()]
                if not faucets:
                    logger.error(f"Unknown faucet: {faucet_filter}")
                    return
            else:
                faucets = list(self.FAUCET_SELECTORS.keys())
                
            # Verify each
            all_results = {}
            for faucet in faucets:
                results = await self.verify_faucet(faucet, browser)
                all_results[faucet] = results
                
            # Print summary
            self.print_summary(all_results)
            
        finally:
            await browser.close()
            
    def print_summary(self, all_results: dict):
        """Print verification summary."""
        logger.info(f"\n{'='*80}")
        logger.info("SELECTOR VERIFICATION SUMMARY")
        logger.info(f"{'='*80}\n")
        
        for faucet, results in all_results.items():
            logger.info(f"\n{faucet.upper()}:")
            
            if "error" in results:
                logger.info(f"  ❌ {results['error']}")
                continue
                
            for page_name, page_results in results.get("pages", {}).items():
                logger.info(f"\n  {page_name.upper()}:")
                logger.info(f"    URL: {page_results['url']}")
                logger.info(f"    Accessible: {'✅' if page_results['accessible'] else '❌'}")
                
                if page_results["accessible"]:
                    for selector_name, selector_results in page_results["selectors"].items():
                        if selector_results["found"]:
                            logger.info(f"    ✅ {selector_name}: {selector_results['working_selector']}")
                        else:
                            logger.info(f"    ❌ {selector_name}: NOT FOUND")
                            logger.info(f"       Tried: {', '.join(selector_results['attempted'])}")


async def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(description="Verify faucet selectors on live pages")
    parser.add_argument("--faucet", "-f", help="Verify specific faucet only")
    args = parser.parse_args()
    
    verifier = SelectorVerifier()
    await verifier.verify_all(faucet_filter=args.faucet)


if __name__ == "__main__":
    asyncio.run(main())
