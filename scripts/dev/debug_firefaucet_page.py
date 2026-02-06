#!/usr/bin/env python3
"""
Quick diagnostic to inspect FireFaucet login page and find correct selectors.
"""
import asyncio
import os
import sys
import logging

logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(name)s - %(message)s')
logger = logging.getLogger(__name__)

async def main():
    from browser.instance import BrowserManager
    from dotenv import load_dotenv
    
    load_dotenv()
    
    headless = os.getenv("HEADLESS", "true").lower() == "true"
    logger.info(f"Browser mode: {'headless' if headless else 'headed'}")
    
    browser = BrowserManager(headless=headless)
    await browser.launch()
    
    try:
        context = await browser.create_context(profile_name="firefaucet_debug")
        page = await context.new_page()
        
        # Navigate to login page
        logger.info("Navigating to https://firefaucet.win/login ...")
        response = await page.goto("https://firefaucet.win/login", timeout=60000, wait_until="domcontentloaded")
        
        logger.info(f"Response status: {response.status if response else 'No response'}")
        logger.info(f"Current URL: {page.url}")
        
        # Wait a bit for any JS to load
        await asyncio.sleep(3)
        
        # Get page title
        title = await page.title()
        logger.info(f"Page title: {title}")
        
        # Check for Cloudflare indicators
        cf_patterns = [
            "Just a moment",
            "checking your browser",
            "Attention Required",
            "cf-browser-verification"
        ]
        
        content = await page.content()
        for pattern in cf_patterns:
            if pattern.lower() in content.lower():
                logger.warning(f"⚠️ Cloudflare indicator found: {pattern}")
                break
        else:
            logger.info("✅ No obvious Cloudflare block detected")
        
        # Check for common login form selectors
        selectors_to_check = [
            "#username",
            "#password", 
            "input[name='username']",
            "input[name='email']",
            "input[name='login']",
            "input[type='text']",
            "input[type='email']",
            "input[type='password']",
            "form",
            "button[type='submit']",
            "button.submitbtn",
            ".login-form",
            ".auth-form",
        ]
        
        logger.info("\n=== Selector Check ===")
        for sel in selectors_to_check:
            try:
                count = await page.locator(sel).count()
                if count > 0:
                    logger.info(f"  ✅ {sel}: {count} element(s)")
                    # Get more info on first match
                    if count > 0:
                        el = page.locator(sel).first
                        try:
                            tag = await el.evaluate("el => el.tagName")
                            visible = await el.is_visible()
                            logger.info(f"      Tag: {tag}, Visible: {visible}")
                        except:
                            pass
                else:
                    logger.info(f"  ❌ {sel}: not found")
            except Exception as e:
                logger.info(f"  ⚠️ {sel}: error - {e}")
        
        # Get all input elements
        logger.info("\n=== All Input Elements ===")
        inputs = await page.query_selector_all("input")
        for i, inp in enumerate(inputs[:10]):  # First 10
            try:
                attrs = await inp.evaluate("""el => ({
                    id: el.id,
                    name: el.name,
                    type: el.type,
                    class: el.className,
                    placeholder: el.placeholder
                })""")
                logger.info(f"  Input {i}: {attrs}")
            except Exception as e:
                logger.info(f"  Input {i}: error - {e}")
        
        # Get visible text (first 1000 chars, excluding scripts)
        logger.info("\n=== Visible Text (excerpt) ===")
        try:
            text = await page.evaluate("""() => {
                return document.body.innerText.substring(0, 1500);
            }""")
            logger.info(text[:1000])
        except Exception as e:
            logger.info(f"Error getting text: {e}")
        
        # Save screenshot if possible
        try:
            await page.screenshot(path="/tmp/firefaucet_login.png")
            logger.info("📸 Screenshot saved to /tmp/firefaucet_login.png")
        except Exception as e:
            logger.info(f"Screenshot failed: {e}")
            
    finally:
        await browser.close()
        logger.info("Browser closed.")

if __name__ == "__main__":
    asyncio.run(main())
