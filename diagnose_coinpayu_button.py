#!/usr/bin/env python3
"""
Diagnostic script to find correct CoinPayU login button selector after CAPTCHA solve.
Run on Linux VM with HEADLESS=true.

This script:
1. Navigates to CoinPayU login page
2. Fills in credentials
3. Waits for/solves CAPTCHA if present
4. Inspects ALL buttons and inputs on the page
5. Saves screenshot and HTML for analysis
"""

import asyncio
import os
import sys
from pathlib import Path
from datetime import datetime
from playwright.async_api import async_playwright
import logging

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

async def inspect_coinpayu_button():
    """Inspect CoinPayU page to find login button selector after CAPTCHA."""
    
    # Load environment variables
    from dotenv import load_dotenv
    load_dotenv()
    
    username = os.getenv("COINPAYU_USERNAME")
    password = os.getenv("COINPAYU_PASSWORD")
    captcha_api_key = os.getenv("TWOCAPTCHA_API_KEY")
    
    if not username or not password:
        logger.error("❌ COINPAYU_USERNAME and COINPAYU_PASSWORD must be set in .env")
        return
    
    if not captcha_api_key:
        logger.warning("⚠️  2CAPTCHA_API_KEY not set - CAPTCHA solving may fail")
    
    async with async_playwright() as p:
        # Launch browser
        headless = os.getenv("HEADLESS", "false").lower() == "true"
        logger.info(f"🚀 Launching browser (headless={headless})...")
        browser = await p.firefox.launch(headless=headless)
        context = await browser.new_context()
        page = await context.new_page()
        
        try:
            logger.info("🌐 Navigating to CoinPayU login page...")
            await page.goto("https://www.coinpayu.com/login", wait_until="domcontentloaded", timeout=30000)
            await asyncio.sleep(3)
            
            # Fill login form
            logger.info("📝 Filling login credentials...")
            
            # Try multiple email selectors
            email_selectors = [
                'input[placeholder="Email"]',
                'input[type="email"]',
                'input[name="email"]',
                'input#email',
                'input[name="login"]',
            ]
            
            email_filled = False
            for selector in email_selectors:
                try:
                    if await page.locator(selector).count() > 0:
                        await page.locator(selector).first.fill(username)
                        logger.info(f"✅ Filled email using selector: {selector}")
                        email_filled = True
                        break
                except Exception as e:
                    logger.debug(f"Email selector {selector} failed: {e}")
                    continue
            
            if not email_filled:
                logger.error("❌ Could not find email field")
                return
            
            await asyncio.sleep(1)
            
            # Try multiple password selectors
            password_selectors = [
                'input[placeholder="Password"]',
                'input[type="password"]',
                'input[name="password"]',
                'input#password',
            ]
            
            password_filled = False
            for selector in password_selectors:
                try:
                    if await page.locator(selector).count() > 0:
                        await page.locator(selector).first.fill(password)
                        logger.info(f"✅ Filled password using selector: {selector}")
                        password_filled = True
                        break
                except Exception as e:
                    logger.debug(f"Password selector {selector} failed: {e}")
                    continue
            
            if not password_filled:
                logger.error("❌ Could not find password field")
                return
            
            await asyncio.sleep(2)
            
            # Check for CAPTCHA
            logger.info("🔍 Checking for CAPTCHA...")
            captcha_present = False
            
            # Check for Turnstile
            if await page.locator("#turnstile-container, .cf-turnstile, iframe[src*='turnstile']").count() > 0:
                logger.info("🧩 Cloudflare Turnstile CAPTCHA detected")
                captcha_present = True
            
            # Check for hCaptcha
            if await page.locator(".h-captcha, iframe[src*='hcaptcha']").count() > 0:
                logger.info("🧩 hCaptcha detected")
                captcha_present = True
            
            # Check for reCAPTCHA
            if await page.locator(".g-recaptcha, iframe[src*='recaptcha']").count() > 0:
                logger.info("🧩 reCAPTCHA detected")
                captcha_present = True
            
            if captcha_present:
                logger.info("⏳ Waiting for CAPTCHA to be solved (manual or via solver)...")
                logger.info("   You have 60 seconds to solve it manually if 2CAPTCHA_API_KEY not set")
                await asyncio.sleep(60)  # Wait for manual or automatic solve
            else:
                logger.info("✅ No CAPTCHA detected")
            
            # Now inspect ALL buttons and inputs on the page
            logger.info("\n" + "="*80)
            logger.info("🔍 INSPECTING ALL BUTTONS AND INPUTS ON PAGE")
            logger.info("="*80)
            
            # JavaScript to get all buttons and relevant inputs
            elements_data = await page.evaluate("""
                () => {
                    const results = [];
                    
                    // Get all buttons
                    const buttons = document.querySelectorAll('button');
                    buttons.forEach((btn, idx) => {
                        const rect = btn.getBoundingClientRect();
                        results.push({
                            type: 'button',
                            index: idx,
                            tagName: btn.tagName,
                            id: btn.id || '',
                            className: btn.className || '',
                            textContent: btn.textContent?.trim() || '',
                            innerHTML: btn.innerHTML?.substring(0, 100) || '',
                            visible: rect.width > 0 && rect.height > 0,
                            type_attr: btn.type || '',
                            onclick: btn.onclick ? 'has onclick' : '',
                            form: btn.form ? btn.form.id || 'in-form' : 'no-form',
                            disabled: btn.disabled,
                            attributes: Array.from(btn.attributes).map(a => `${a.name}="${a.value}"`).join(' ')
                        });
                    });
                    
                    // Get submit inputs
                    const inputs = document.querySelectorAll('input[type="submit"], input[type="button"]');
                    inputs.forEach((inp, idx) => {
                        const rect = inp.getBoundingClientRect();
                        results.push({
                            type: 'input',
                            index: idx,
                            tagName: inp.tagName,
                            id: inp.id || '',
                            className: inp.className || '',
                            value: inp.value || '',
                            visible: rect.width > 0 && rect.height > 0,
                            type_attr: inp.type || '',
                            form: inp.form ? inp.form.id || 'in-form' : 'no-form',
                            disabled: inp.disabled,
                            attributes: Array.from(inp.attributes).map(a => `${a.name}="${a.value}"`).join(' ')
                        });
                    });
                    
                    return results;
                }
            """)
            
            # Print all elements
            logger.info(f"\nFound {len(elements_data)} button/input elements:\n")
            
            for i, elem in enumerate(elements_data):
                logger.info(f"--- Element #{i+1} ---")
                logger.info(f"  Type: {elem['type']}")
                logger.info(f"  Tag: {elem['tagName']}")
                logger.info(f"  ID: {elem.get('id', 'N/A')}")
                logger.info(f"  Class: {elem.get('className', 'N/A')}")
                logger.info(f"  Text: {elem.get('textContent', elem.get('value', 'N/A'))}")
                logger.info(f"  Visible: {elem['visible']}")
                logger.info(f"  Disabled: {elem['disabled']}")
                logger.info(f"  Type attr: {elem.get('type_attr', 'N/A')}")
                logger.info(f"  In form: {elem.get('form', 'N/A')}")
                logger.info(f"  All attributes: {elem.get('attributes', 'N/A')}")
                logger.info("")
            
            # Highlight login-related buttons
            logger.info("\n" + "="*80)
            logger.info("🎯 LIKELY LOGIN BUTTON CANDIDATES")
            logger.info("="*80)
            
            login_keywords = ['login', 'log in', 'sign in', 'submit', 'enter']
            candidates = []
            
            for elem in elements_data:
                text = elem.get('textContent', elem.get('value', '')).lower()
                classes = elem.get('className', '').lower()
                elem_id = elem.get('id', '').lower()
                
                if any(kw in text or kw in classes or kw in elem_id for kw in login_keywords):
                    candidates.append(elem)
            
            if candidates:
                for i, elem in enumerate(candidates):
                    logger.info(f"\nCandidate #{i+1}:")
                    logger.info(f"  Selector suggestions:")
                    if elem.get('id'):
                        logger.info(f"    - #{elem['id']}")
                        logger.info(f"    - {elem['tagName'].lower()}#{elem['id']}")
                    if elem.get('className'):
                        classes = elem['className'].split()
                        for cls in classes:
                            logger.info(f"    - .{cls}")
                        logger.info(f"    - {elem['tagName'].lower()}.{classes[0]}")
                    
                    text = elem.get('textContent', elem.get('value', ''))
                    if text:
                        logger.info(f"    - {elem['tagName'].lower()}:has-text('{text}')")
                    
                    logger.info(f"  Visible: {elem['visible']}")
                    logger.info(f"  Disabled: {elem['disabled']}")
            else:
                logger.warning("⚠️  No obvious login button candidates found!")
                logger.info("Check screenshot and HTML dump for manual inspection")
            
            # Save screenshot
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            screenshot_path = f"coinpayu_after_captcha_{timestamp}.png"
            await page.screenshot(path=screenshot_path, full_page=True)
            logger.info(f"\n📸 Screenshot saved: {screenshot_path}")
            
            # Save HTML
            html_content = await page.content()
            html_path = f"coinpayu_after_captcha_{timestamp}.html"
            with open(html_path, 'w', encoding='utf-8') as f:
                f.write(html_content)
            logger.info(f"📄 HTML saved: {html_path}")
            
            # Save element data to JSON for reference
            import json
            json_path = f"coinpayu_elements_{timestamp}.json"
            with open(json_path, 'w', encoding='utf-8') as f:
                json.dump(elements_data, f, indent=2)
            logger.info(f"📋 Element data saved: {json_path}")
            
            logger.info("\n" + "="*80)
            logger.info("✅ DIAGNOSTIC COMPLETE")
            logger.info("="*80)
            logger.info(f"Review the files:")
            logger.info(f"  - {screenshot_path}")
            logger.info(f"  - {html_path}")
            logger.info(f"  - {json_path}")
            
        except Exception as e:
            logger.error(f"❌ Error during inspection: {e}", exc_info=True)
            
            # Try to save screenshot even on error
            try:
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                await page.screenshot(path=f"coinpayu_error_{timestamp}.png")
                logger.info(f"📸 Error screenshot saved")
            except:
                pass
        
        finally:
            await browser.close()
            logger.info("🔚 Browser closed")

if __name__ == "__main__":
    asyncio.run(inspect_coinpayu_button())
