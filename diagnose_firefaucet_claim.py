#!/usr/bin/env python3
"""
Diagnostic script for FireFaucet claim page button detection.
Issue #86: Investigate and fix "0 buttons" problem.

This script:
1. Logs in to FireFaucet
2. Navigates to /faucet page
3. Monitors button state during countdown timer
4. Identifies correct selectors and timing
"""

import asyncio
import sys
import logging
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent))

from browser.instance import BrowserManager
from core.config import BotSettings

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


async def diagnose_firefaucet_claim():
    """Diagnose FireFaucet claim page button detection issue."""
    
    logger.info("=" * 80)
    logger.info("🔥 FIREFAUCET CLAIM PAGE DIAGNOSTIC")
    logger.info("=" * 80)
    
    settings = BotSettings()
    browser_manager = BrowserManager(settings)
    
    try:
        # Launch browser
        await browser_manager.launch()
        logger.info("✅ Browser launched")
        
        # Get credentials
        creds = settings.get_account("fire_faucet")
        if not creds:
            logger.error("❌ No FireFaucet credentials found in .env")
            return
        
        logger.info(f"📧 Using account: {creds.get('username', 'unknown')}")
        
        # Create context and page
        context = await browser_manager.create_context(profile_name=creds["username"])
        page = await context.new_page()
        
        # Step 1: Login
        logger.info("\n" + "=" * 80)
        logger.info("STEP 1: Login to FireFaucet")
        logger.info("=" * 80)
        
        await page.goto("https://firefaucet.win/login", wait_until='domcontentloaded')
        await asyncio.sleep(2)
        
        # Fill login form
        await page.fill('input[name="email"]', creds["username"])
        await page.fill('input[name="password"]', creds["password"])
        await page.click('button[type="submit"]')
        await asyncio.sleep(5)
        
        current_url = page.url
        logger.info(f"Current URL after login: {current_url}")
        
        if "dashboard" in current_url or "faucet" in current_url:
            logger.info("✅ Login successful")
        else:
            logger.warning("⚠️  Login may have failed - unexpected URL")
        
        # Step 2: Navigate to faucet page
        logger.info("\n" + "=" * 80)
        logger.info("STEP 2: Navigate to /faucet page")
        logger.info("=" * 80)
        
        await page.goto("https://firefaucet.win/faucet", wait_until='domcontentloaded')
        logger.info(f"✅ Navigated to: {page.url}")
        
        # Wait for initial page load
        await asyncio.sleep(3)
        
        # Step 3: Analyze button state
        logger.info("\n" + "=" * 80)
        logger.info("STEP 3: Analyze button state and countdown timer")
        logger.info("=" * 80)
        
        # Check for #get_reward_button
        button_exists = await page.locator("#get_reward_button").count()
        logger.info(f"Button #get_reward_button exists: {button_exists > 0}")
        
        if button_exists > 0:
            # Get initial button state
            button_text = await page.locator("#get_reward_button").text_content()
            is_disabled = await page.locator("#get_reward_button").get_attribute("disabled")
            button_class = await page.locator("#get_reward_button").get_attribute("class")
            
            logger.info(f"Initial button text: '{button_text}'")
            logger.info(f"Initial disabled attribute: {is_disabled}")
            logger.info(f"Button classes: {button_class}")
            
            # Monitor button state changes during countdown
            logger.info("\n📊 Monitoring button state every second...")
            for i in range(15):
                await asyncio.sleep(1)
                
                try:
                    text = await page.locator("#get_reward_button").text_content()
                    is_disabled = await page.locator("#get_reward_button").get_attribute("disabled")
                    is_enabled = await page.locator("#get_reward_button").is_enabled()
                    
                    logger.info(f"  [{i+1}s] text='{text}' | disabled_attr={is_disabled} | is_enabled={is_enabled}")
                    
                    # Check if timer completed
                    if "Get Reward" in text and is_disabled is None:
                        logger.info(f"✅ Button enabled after {i+1} seconds!")
                        break
                except Exception as e:
                    logger.error(f"  [{i+1}s] Error checking button: {e}")
        
        # Step 4: Count all interactive elements
        logger.info("\n" + "=" * 80)
        logger.info("STEP 4: Count all interactive elements on page")
        logger.info("=" * 80)
        
        all_buttons = await page.locator('button').count()
        all_submit_inputs = await page.locator('input[type="submit"]').count()
        all_button_inputs = await page.locator('input[type="button"]').count()
        all_forms = await page.locator('form').count()
        
        logger.info(f"Total <button> elements: {all_buttons}")
        logger.info(f"Total <input type='submit'>: {all_submit_inputs}")
        logger.info(f"Total <input type='button'>: {all_button_inputs}")
        logger.info(f"Total <form> elements: {all_forms}")
        
        # List all buttons with details
        if all_buttons > 0:
            logger.info(f"\n📋 Details of all {all_buttons} button elements:")
            for i in range(min(all_buttons, 20)):
                try:
                    btn = page.locator('button').nth(i)
                    text = await btn.text_content()
                    id_attr = await btn.get_attribute('id')
                    type_attr = await btn.get_attribute('type')
                    visible = await btn.is_visible()
                    enabled = await btn.is_enabled()
                    
                    logger.info(f"  [{i}] id='{id_attr}' type='{type_attr}' text='{text[:30]}...' visible={visible} enabled={enabled}")
                except Exception as e:
                    logger.debug(f"  [{i}] Error: {e}")
        
        # Step 5: Check for iframes
        logger.info("\n" + "=" * 80)
        logger.info("STEP 5: Check for iframes (captcha, etc.)")
        logger.info("=" * 80)
        
        iframes = await page.query_selector_all('iframe')
        logger.info(f"Total iframes on page: {len(iframes)}")
        
        for i, iframe in enumerate(iframes[:10]):
            try:
                src = await iframe.get_attribute('src')
                title = await iframe.get_attribute('title')
                logger.info(f"  [{i}] title='{title}' src='{src[:80]}...'")
            except Exception as e:
                logger.debug(f"  [{i}] Error: {e}")
        
        # Step 6: Save artifacts
        logger.info("\n" + "=" * 80)
        logger.info("STEP 6: Save diagnostic artifacts")
        logger.info("=" * 80)
        
        # Save screenshot
        screenshot_path = "/tmp/firefaucet_claim_diagnostic.png"
        await page.screenshot(path=screenshot_path, full_page=True)
        logger.info(f"📸 Screenshot saved: {screenshot_path}")
        
        # Save HTML
        html = await page.content()
        html_path = "/tmp/firefaucet_claim_diagnostic.html"
        Path(html_path).write_text(html, encoding='utf-8')
        logger.info(f"💾 HTML saved: {html_path}")
        
        # Extract JavaScript countdown logic
        logger.info("\n" + "=" * 80)
        logger.info("STEP 7: Extract countdown timer logic")
        logger.info("=" * 80)
        
        timer_info = await page.evaluate("""
            () => {
                const btn = document.getElementById('get_reward_button');
                if (!btn) return { exists: false };
                
                return {
                    exists: true,
                    text: btn.innerText,
                    disabled: btn.disabled,
                    classList: Array.from(btn.classList),
                    formAction: btn.form ? btn.form.action : null
                };
            }
        """)
        
        logger.info(f"JavaScript timer info: {timer_info}")
        
        # Step 8: Test button selectors
        logger.info("\n" + "=" * 80)
        logger.info("STEP 8: Test various button selectors")
        logger.info("=" * 80)
        
        selectors = [
            "#get_reward_button",
            "button[type='submit']",
            "button.btn.waves-effect",
            "button:has-text('Get Reward')",
            "button:has-text('Please Wait')",
            "form#faucetform button",
            ".earn-btns",
            ".captcha-submit-btn"
        ]
        
        for selector in selectors:
            try:
                count = await page.locator(selector).count()
                if count > 0:
                    text = await page.locator(selector).first.text_content()
                    visible = await page.locator(selector).first.is_visible()
                    logger.info(f"✅ '{selector}' → {count} found, text='{text[:30]}', visible={visible}")
                else:
                    logger.info(f"❌ '{selector}' → 0 found")
            except Exception as e:
                logger.error(f"⚠️  '{selector}' → Error: {e}")
        
        logger.info("\n" + "=" * 80)
        logger.info("✅ DIAGNOSTIC COMPLETE")
        logger.info("=" * 80)
        
    except Exception as e:
        logger.error(f"❌ Fatal error: {e}")
        import traceback
        traceback.print_exc()
    
    finally:
        await browser_manager.close()
        logger.info("Browser closed")


if __name__ == "__main__":
    asyncio.run(diagnose_firefaucet_claim())
