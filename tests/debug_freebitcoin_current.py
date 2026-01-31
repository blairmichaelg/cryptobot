#!/usr/bin/env python3
"""
Debug script to inspect current FreeBitcoin login page structure
"""
import asyncio
from playwright.async_api import async_playwright
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def inspect_freebitcoin():
    """Inspect FreeBitcoin login page to identify current selectors"""
    async with async_playwright() as p:
        browser = await p.firefox.launch(headless=False)
        context = await browser.new_context()
        page = await context.new_page()
        
        logger.info("Navigating to FreeBitcoin...")
        await page.goto("https://freebitco.in/?op=login", wait_until="domcontentloaded", timeout=60000)
        await asyncio.sleep(3)
        
        # Check for Cloudflare
        logger.info("Checking for Cloudflare...")
        try:
            cf_title = await page.title()
            logger.info(f"Page title: {cf_title}")
            if "cloudflare" in cf_title.lower() or "just a moment" in cf_title.lower():
                logger.warning("Cloudflare detected. Waiting...")
                await asyncio.sleep(10)
        except Exception as e:
            logger.warning(f"Error checking title: {e}")
        
        # Get page URL
        current_url = page.url
        logger.info(f"Current URL: {current_url}")
        
        # Extract all forms
        logger.info("\n=== FORMS ON PAGE ===")
        forms = await page.evaluate("""
            () => Array.from(document.querySelectorAll('form')).map(form => ({
                id: form.id || null,
                name: form.name || null,
                action: form.action || null,
                method: form.method || null
            }))
        """)
        for i, form in enumerate(forms):
            logger.info(f"Form {i+1}: {form}")
        
        # Extract all input fields
        logger.info("\n=== INPUT FIELDS ===")
        inputs = await page.evaluate("""
            () => Array.from(document.querySelectorAll('input')).map(el => ({
                type: el.type || null,
                name: el.name || null,
                id: el.id || null,
                placeholder: el.placeholder || null,
                className: el.className || null,
                visible: el.offsetParent !== null
            }))
        """)
        for i, inp in enumerate(inputs):
            if inp['visible'] and (inp['type'] in ['text', 'email', 'password', 'submit']):
                logger.info(f"Input {i+1}: {inp}")
        
        # Extract all buttons
        logger.info("\n=== BUTTONS ===")
        buttons = await page.evaluate("""
            () => Array.from(document.querySelectorAll('button')).map(el => ({
                type: el.type || null,
                id: el.id || null,
                className: el.className || null,
                text: el.textContent.trim(),
                visible: el.offsetParent !== null
            }))
        """)
        for i, btn in enumerate(buttons):
            if btn['visible']:
                logger.info(f"Button {i+1}: {btn}")
        
        # Check for login-related elements
        logger.info("\n=== LOGIN ELEMENTS CHECK ===")
        
        # Try all email selectors
        email_selectors = [
            "input[name='btc_address']",
            "input[name='login_form[btc_address]']",
            "input[type='email']",
            "input[name='email']",
            "#email",
            "#login_form_btc_address",
            "input#login_form_btc_address",
        ]
        
        logger.info("Checking email/username selectors:")
        for selector in email_selectors:
            try:
                count = await page.locator(selector).count()
                if count > 0:
                    visible = await page.locator(selector).first.is_visible()
                    logger.info(f"  ✅ {selector} - Found ({count}), Visible: {visible}")
                else:
                    logger.info(f"  ❌ {selector} - Not found")
            except Exception as e:
                logger.info(f"  ❌ {selector} - Error: {e}")
        
        # Try all password selectors
        password_selectors = [
            "input[name='password']",
            "input[type='password']",
            "#password",
            "#login_form_password",
        ]
        
        logger.info("\nChecking password selectors:")
        for selector in password_selectors:
            try:
                count = await page.locator(selector).count()
                if count > 0:
                    visible = await page.locator(selector).first.is_visible()
                    logger.info(f"  ✅ {selector} - Found ({count}), Visible: {visible}")
                else:
                    logger.info(f"  ❌ {selector} - Not found")
            except Exception as e:
                logger.info(f"  ❌ {selector} - Error: {e}")
        
        # Try all submit selectors
        submit_selectors = [
            "#login_button",
            "button[type='submit']",
            "input[type='submit']",
            "button:has-text('Login')",
            "button:has-text('Log In')",
        ]
        
        logger.info("\nChecking submit button selectors:")
        for selector in submit_selectors:
            try:
                count = await page.locator(selector).count()
                if count > 0:
                    visible = await page.locator(selector).first.is_visible()
                    logger.info(f"  ✅ {selector} - Found ({count}), Visible: {visible}")
                else:
                    logger.info(f"  ❌ {selector} - Not found")
            except Exception as e:
                logger.info(f"  ❌ {selector} - Error: {e}")
        
        # Take screenshot
        await page.screenshot(path="logs/freebitcoin_current_state.png")
        logger.info("\n📸 Screenshot saved to logs/freebitcoin_current_state.png")
        
        # Wait for manual inspection
        logger.info("\nBrowser will stay open for 60 seconds for manual inspection...")
        await asyncio.sleep(60)
        
        await browser.close()

if __name__ == "__main__":
    asyncio.run(inspect_freebitcoin())
