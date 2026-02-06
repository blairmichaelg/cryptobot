#!/usr/bin/env python3
"""
Diagnostic script to find correct FreeBitcoin balance and timer selectors.
Run on Linux VM with HEADLESS=true.
"""

import asyncio
import os
import sys
from pathlib import Path
from playwright.async_api import async_playwright
import logging

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

async def inspect_freebitcoin():
    """Inspect FreeBitcoin page to find balance and timer selectors."""
    
    # Load environment variables
    from dotenv import load_dotenv
    load_dotenv()
    
    username = os.getenv("FREEBITCOIN_USERNAME")
    password = os.getenv("FREEBITCOIN_PASSWORD")
    
    if not username or not password:
        logger.error("❌ FREEBITCOIN_USERNAME and FREEBITCOIN_PASSWORD must be set in .env")
        return
    
    async with async_playwright() as p:
        # Launch browser
        headless = os.getenv("HEADLESS", "false").lower() == "true"
        browser = await p.firefox.launch(headless=headless)
        context = await browser.new_context()
        page = await context.new_page()
        
        try:
            logger.info("🌐 Navigating to FreeBitcoin...")
            await page.goto("https://freebitco.in", wait_until="domcontentloaded", timeout=30000)
            await asyncio.sleep(3)
            
            # Click LOGIN trigger
            logger.info("🔍 Looking for LOGIN trigger...")
            login_triggers = [
                "a:has-text('LOGIN')",
                "a:has-text('Log In')",
                "button:has-text('LOGIN')",
                "a[href*='login']"
            ]
            
            for selector in login_triggers:
                try:
                    if await page.locator(selector).is_visible(timeout=2000):
                        logger.info(f"✅ Clicking login trigger: {selector}")
                        await page.locator(selector).first.click()
                        await asyncio.sleep(3)
                        break
                except:
                    continue
            
            # Fill login form
            logger.info("📝 Filling login form...")
            email_field = page.locator("#login_form_btc_address").first
            if await email_field.is_visible(timeout=5000):
                await email_field.fill(username)
                logger.info("✅ Filled username/email")
            
            password_field = page.locator("#login_form_password").first
            if await password_field.is_visible(timeout=5000):
                await password_field.fill(password)
                logger.info("✅ Filled password")
            
            # Click login button
            login_button = page.locator("#login_button").first
            if await login_button.is_visible(timeout=5000):
                await login_button.click()
                logger.info("✅ Clicked login button")
                await asyncio.sleep(5)
            
            # Check if logged in
            current_url = page.url
            logger.info(f"📍 Current URL: {current_url}")
            
            # Inspect balance elements
            logger.info("\n" + "="*60)
            logger.info("💰 SEARCHING FOR BALANCE ELEMENTS")
            logger.info("="*60)
            
            balance_candidates = await page.evaluate("""
                () => {
                    const results = [];
                    // Check all elements with text that looks like crypto amounts
                    const allElements = document.querySelectorAll('*');
                    const cryptoPattern = /\\d+[,.]\\d+|BTC|bitcoin|satoshi/i;
                    
                    for (const el of allElements) {
                        const text = el.textContent?.trim();
                        const hasText = text && text.length < 50;
                        if (hasText && cryptoPattern.test(text)) {
                            const selector = el.id ? `#${el.id}` : 
                                           el.className ? `.${el.className.split(' ')[0]}` : 
                                           el.tagName.toLowerCase();
                            results.push({
                                selector: selector,
                                text: text,
                                id: el.id || '',
                                class: el.className || '',
                                tag: el.tagName
                            });
                        }
                    }
                    return results.slice(0, 20);  // Limit to first 20 matches
                }
            """)
            
            logger.info(f"\n🔍 Found {len(balance_candidates)} potential balance elements:")
            for i, elem in enumerate(balance_candidates, 1):
                logger.info(f"{i}. Selector: {elem['selector']}")
                logger.info(f"   ID: {elem['id']}, Class: {elem['class']}, Tag: {elem['tag']}")
                logger.info(f"   Text: {elem['text'][:100]}")
                logger.info("")
            
            # Inspect timer elements
            logger.info("\n" + "="*60)
            logger.info("⏰ SEARCHING FOR TIMER ELEMENTS")
            logger.info("="*60)
            
            timer_candidates = await page.evaluate("""
                () => {
                    const results = [];
                    const allElements = document.querySelectorAll('*');
                    const timePattern = /\\d+:\\d+|\\d+\\s*(min|sec|hour)|timer|countdown|wait|next|claim/i;
                    
                    for (const el of allElements) {
                        const text = el.textContent?.trim();
                        const hasText = text && text.length < 100;
                        if (hasText && timePattern.test(text)) {
                            const selector = el.id ? `#${el.id}` : 
                                           el.className ? `.${el.className.split(' ')[0]}` : 
                                           el.tagName.toLowerCase();
                            results.push({
                                selector: selector,
                                text: text,
                                id: el.id || '',
                                class: el.className || '',
                                tag: el.tagName
                            });
                        }
                    }
                    return results.slice(0, 20);  // Limit to first 20 matches
                }
            """)
            
            logger.info(f"\n🔍 Found {len(timer_candidates)} potential timer elements:")
            for i, elem in enumerate(timer_candidates, 1):
                logger.info(f"{i}. Selector: {elem['selector']}")
                logger.info(f"   ID: {elem['id']}, Class: {elem['class']}, Tag: {elem['tag']}")
                logger.info(f"   Text: {elem['text'][:100]}")
                logger.info("")
            
            # Check specific selectors
            logger.info("\n" + "="*60)
            logger.info("🔎 TESTING SPECIFIC SELECTORS")
            logger.info("="*60)
            
            test_selectors = {
                "Balance": [
                    "#balance",
                    "#balance_small",
                    ".balance",
                    "span.balance",
                    ".user-balance",
                    "[data-balance]",
                    "#balance_small span"
                ],
                "Timer": [
                    "#time_remaining",
                    "span#timer",
                    ".countdown",
                    "[data-next-claim]",
                    ".time-remaining",
                    "#timer"
                ]
            }
            
            for category, selectors in test_selectors.items():
                logger.info(f"\n{category} selectors:")
                for selector in selectors:
                    try:
                        elem = page.locator(selector).first
                        if await elem.count() > 0:
                            is_visible = await elem.is_visible(timeout=1000)
                            text = await elem.text_content(timeout=1000) if is_visible else "N/A"
                            logger.info(f"  ✅ {selector}: FOUND (visible: {is_visible}, text: {text[:50]})")
                        else:
                            logger.info(f"  ❌ {selector}: NOT FOUND")
                    except Exception as e:
                        logger.info(f"  ❌ {selector}: ERROR ({str(e)[:50]})")
            
            # Save screenshot
            screenshot_path = Path("logs") / "freebitcoin_dashboard.png"
            screenshot_path.parent.mkdir(exist_ok=True)
            await page.screenshot(path=str(screenshot_path))
            logger.info(f"\n📸 Screenshot saved: {screenshot_path}")
            
            logger.info("\n" + "="*60)
            logger.info("✅ DIAGNOSTIC COMPLETE")
            logger.info("="*60)
            
        except Exception as e:
            logger.error(f"❌ Error during inspection: {e}", exc_info=True)
        finally:
            await browser.close()

if __name__ == "__main__":
    asyncio.run(inspect_freebitcoin())
