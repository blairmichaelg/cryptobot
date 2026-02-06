#!/usr/bin/env python3
"""
Inspect faucet pages to find correct selectors for balance, timer, and claim buttons
"""
import asyncio
import logging
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from browser.instance import BrowserManager
from core.config import BotSettings
from core.registry import get_faucet_class

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


async def inspect_faucet(faucet_name: str, browser_mgr, settings):
    """Inspect a faucet's claim page to find selectors."""
    
    logger.info(f"\n{'='*60}\nINSPECTING: {faucet_name}\n{'='*60}")
    
    context = None
    try:
        # Get credentials
        creds = settings.get_account(faucet_name)
        if not creds:
            logger.warning(f"No credentials for {faucet_name}")
            return
        
        # Create context and bot
        context = await browser_mgr.create_context(profile_name=f"{faucet_name}_inspect")
        page = await context.new_page()
        
        bot_class = get_faucet_class(faucet_name)
        if not bot_class:
            logger.error(f"Bot class not found for {faucet_name}")
            return
        
        bot = bot_class(settings, page)
        bot.settings_account_override = {'username': creds['username'], 'password': creds['password']}
        
        # Login
        logger.info(f"[{faucet_name}] Logging in...")
        login_success = await bot.login()
        
        if not login_success:
            logger.error(f"[{faucet_name}] Login failed")
            return
        
        logger.info(f"[{faucet_name}] Login successful! Current URL: {page.url}")
        
        # Try to navigate to faucet/claim page if not already there
        current_url = page.url.lower()
        # If we're not already on a page with 'faucet' or 'claim' in the URL, navigate there
        if 'faucet' not in current_url and 'claim' not in current_url:
            # Try common faucet page URLs
            base_url = bot.base_url if hasattr(bot, 'base_url') else page.url.split('/')[0] + '//' + page.url.split('/')[2]
            faucet_urls = [f"{base_url}/faucet/", f"{base_url}/faucet", f"{base_url}/claim", f"{base_url}/claim/"]
            
            for url in faucet_urls:
                try:
                    logger.info(f"[{faucet_name}] Trying to navigate to: {url}")
                    await page.goto(url, wait_until='domcontentloaded', timeout=30000)
                    await asyncio.sleep(3)  # Increased wait for page to fully load
                    logger.info(f"[{faucet_name}] Navigated to: {page.url}")
                    if 'faucet' in page.url.lower() or 'claim' in page.url.lower():
                        logger.info(f"[{faucet_name}] ✓ Successfully navigated to claim page!")
                        break
                except Exception as e:
                    logger.debug(f"[{faucet_name}] URL {url} failed: {e}")
        else:
            logger.info(f"[{faucet_name}] Already on faucet/claim page")
        
        # Inspect page for common selectors
        logger.info(f"\n[{faucet_name}] INSPECTING PAGE ELEMENTS:\n")
        
        # Check for balance elements
        balance_selectors = [".user-balance", ".balance", "#user-balance", "#balance", 
                            "[class*='balance']", ".wallet-balance", ".account-balance"]
        logger.info("Balance element candidates:")
        for sel in balance_selectors:
            try:
                count = await page.locator(sel).count()
                if count > 0:
                    text = await page.locator(sel).first.text_content(timeout=2000)
                    logger.info(f"  ✓ {sel:30} - Found {count}, text: '{text[:50]}'")
            except:
                pass
        
        # Check for timer elements
        timer_selectors = ["#claim_timer", "#time", ".timer", ".countdown", "[class*='timer']",
                          "[class*='countdown']", "[id*='timer']", ".time-remaining"]
        logger.info("\nTimer element candidates:")
        for sel in timer_selectors:
            try:
                count = await page.locator(sel).count()
                if count > 0:
                    text = await page.locator(sel).first.text_content(timeout=2000)
                    logger.info(f"  ✓ {sel:30} - Found {count}, text: '{text[:50]}'")
            except:
                pass
        
        # Check for buttons/inputs
        button_selectors = ["button", "input[type='button']", "input[type='submit']", 
                           "[class*='claim']", "[class*='faucet']", "[id*='claim']", "[id*='submit']"]
        logger.info("\nButton/Input candidates:")
        for sel in button_selectors:
            try:
                count = await page.locator(sel).count()
                if count > 0 and count < 20:  # Avoid listing too many
                    logger.info(f"  ✓ {sel:30} - Found {count}")
                    # Get details of first few
                    for i in range(min(3, count)):
                        try:
                            elem = page.locator(sel).nth(i)
                            text = await elem.text_content(timeout=1000)
                            id_attr = await elem.get_attribute('id')
                            class_attr = await elem.get_attribute('class')
                            logger.info(f"      [{i}] text='{text}', id='{id_attr}', class='{class_attr}'")
                        except:
                            pass
            except:
                pass
        
        # Save page HTML for manual inspection
        html = await page.content()
        html_file = f"inspect_{faucet_name}.html"
        with open(html_file, 'w', encoding='utf-8') as f:
            f.write(html)
        logger.info(f"\n[{faucet_name}] Full HTML saved to: {html_file}")
        
        # Save screenshot
        screenshot_file = f"inspect_{faucet_name}.png"
        await page.screenshot(path=screenshot_file, full_page=True)
        logger.info(f"[{faucet_name}] Screenshot saved to: {screenshot_file}")
        
    except Exception as e:
        logger.error(f"[{faucet_name}] Error during inspection: {e}", exc_info=True)
    
    finally:
        if context:
            try:
                await context.close()
            except:
                pass


async def main():
    """Inspect specific faucets that are failing."""
    settings = BotSettings()
    headless = os.getenv('HEADLESS', 'false').lower() == 'true'
    
    # Focus on faucets with known issues
    faucets_to_inspect = [
        "firefaucet",      # Claim button not found
        "coinpayu",        # Login button not found
        # "freebitcoin",   # Login works, just confirmation issue
    ]
    
    logger.info("="*60)
    logger.info("FAUCET SELECTOR INSPECTION")
    logger.info(f"Inspecting {len(faucets_to_inspect)} faucets")
    logger.info("="*60)
    
    browser_mgr = BrowserManager(headless=headless)
    await browser_mgr.launch()
    
    try:
        for faucet_name in faucets_to_inspect:
            await inspect_faucet(faucet_name, browser_mgr, settings)
            await asyncio.sleep(2)
    finally:
        await browser_mgr.close()
    
    logger.info("\n" + "="*60)
    logger.info("Inspection complete! Check inspect_*.html and inspect_*.png files")
    logger.info("="*60)


if __name__ == "__main__":
    asyncio.run(main())
