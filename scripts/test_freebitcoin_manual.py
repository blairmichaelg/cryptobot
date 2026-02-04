#!/usr/bin/env python3
"""
Simple FreeBitcoin diagnostic - identify exact login failure point.
"""

import asyncio
import os
import sys
from pathlib import Path

# Force visible mode
os.environ['HEADLESS'] = 'false'

sys.path.insert(0, str(Path(__file__).parent.parent))

from playwright.async_api import async_playwright
from core.config import BotSettings

async def test_freebitcoin_manual():
    """Manually test FreeBitcoin login to identify failure point."""
    
    print("\n" + "="*70)
    print("FREEBITCOIN MANUAL LOGIN TEST")
    print("="*70)
    
    settings = BotSettings()
    username = settings.freebitcoin_username
    password = settings.freebitcoin_password
    
    if not username or not password:
        print("❌ No FreeBitcoin credentials configured")
        return
    
    print(f"\nUsername: {username}")
    print(f"Password: {'*' * len(password)}")
    
    async with async_playwright() as p:
        browser = await p.firefox.launch(headless=False)
        context = await browser.new_context()
        page = await context.new_page()
        
        try:
            # Step 1: Navigate
            print("\n[1/7] Navigating to freebitco.in...")
            await page.goto("https://freebitco.in", wait_until="domcontentloaded", timeout=30000)
            print(f"✅ Page loaded: {page.url}")
            await asyncio.sleep(3)
            
            # Step 2: Check for login form
            print("\n[2/7] Looking for login form...")
            
            # Try multiple selectors
            selectors_to_try = [
                'input[name="btc_address"]',
                '#login_form_btc_address',
                'input[type="text"]',
                'input[placeholder*="email" i]',
                'input[placeholder*="address" i]'
            ]
            
            email_field = None
            for selector in selectors_to_try:
                try:
                    email_field = await page.query_selector(selector)
                    if email_field:
                        visible = await email_field.is_visible()
                        if visible:
                            print(f"✅ Found email field: {selector}")
                            break
                except:
                    pass
            
            if not email_field:
                print("❌ Could not find email/address input field")
                print("⏸️  Browser kept open - inspect the page manually")
                await asyncio.sleep(60)
                return
            
            # Step 3: Fill email
            print(f"\n[3/7] Filling email: {username}")
            await email_field.fill(username)
            await asyncio.sleep(1)
            
            # Step 4: Find password field
            print("\n[4/7] Looking for password field...")
            password_selectors = [
                'input[name="password"]',
                '#login_form_password',
                'input[type="password"]'
            ]
            
            password_field = None
            for selector in password_selectors:
                try:
                    password_field = await page.query_selector(selector)
                    if password_field:
                        visible = await password_field.is_visible()
                        if visible:
                            print(f"✅ Found password field: {selector}")
                            break
                except:
                    pass
            
            if not password_field:
                print("❌ Could not find password field")
                print("⏸️  Browser kept open - inspect the page manually")
                await asyncio.sleep(60)
                return
            
            # Step 5: Fill password
            print(f"\n[5/7] Filling password")
            await password_field.fill(password)
            await asyncio.sleep(1)
            
            # Step 6: Find and click login button
            print("\n[6/7] Looking for login button...")
            login_selectors = [
                '#login_button',
                'button[type="submit"]',
                'input[type="submit"]',
                'button:has-text("login")',
                'button:has-text("sign in")'
            ]
            
            login_button = None
            for selector in login_selectors:
                try:
                    login_button = await page.query_selector(selector)
                    if login_button:
                        visible = await login_button.is_visible()
                        if visible:
                            print(f"✅ Found login button: {selector}")
                            break
                except:
                    pass
            
            if not login_button:
                print("❌ Could not find login button")
                print("⏸️  Browser kept open - inspect the page manually")
                await asyncio.sleep(60)
                return
            
            print(f"\n[7/7] Clicking login button...")
            await login_button.click()
            
            # Wait for navigation or error
            print("\n⏳ Waiting for login result...")
            await asyncio.sleep(5)
            
            print(f"\nCurrent URL: {page.url}")
            
            # Check for error messages
            error_selectors = [
                '.error',
                '.alert-danger',
                '#error_message',
                '[class*="error"]'
            ]
            
            for selector in error_selectors:
                try:
                    error = await page.query_selector(selector)
                    if error:
                        visible = await error.is_visible()
                        if visible:
                            text = await error.inner_text()
                            print(f"❌ Error found: {text}")
                except:
                    pass
            
            # Check if logged in
            success_indicators = [
                '#free_play_form_button',
                '.logout_button',
                'a[href*="logout"]',
                '#time_remaining'
            ]
            
            logged_in = False
            for selector in success_indicators:
                try:
                    element = await page.query_selector(selector)
                    if element:
                        logged_in = True
                        print(f"✅ Login SUCCESS - found: {selector}")
                        break
                except:
                    pass
            
            if not logged_in:
                print("❓ Login result unclear - check the page")
            
            print("\n⏸️  Browser kept open for 60 seconds - inspect the page!")
            await asyncio.sleep(60)
            
        finally:
            await browser.close()


if __name__ == "__main__":
    asyncio.run(test_freebitcoin_manual())
