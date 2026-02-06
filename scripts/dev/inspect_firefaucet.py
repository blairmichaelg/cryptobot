#!/usr/bin/env python3
"""
Inspect FireFaucet page structure to find correct selectors.
"""
import asyncio
import os
import logging
from dotenv import load_dotenv

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def main():
    from browser.instance import BrowserManager
    from core.config import BotSettings
    
    load_dotenv()
    settings = BotSettings()
    browser = BrowserManager(headless=True)
    await browser.launch()
    
    try:
        creds = settings.get_account("fire_faucet")
        context = await browser.create_context(profile_name=creds["username"])
        page = await context.new_page()
        
        # Go directly to faucet page (should already be logged in)
        await page.goto('https://firefaucet.win/faucet/', wait_until='domcontentloaded')
        await asyncio.sleep(5)
        
        # Get page HTML
        html = await page.content()
        
        # Save HTML for inspection
        with open('/tmp/firefaucet_page.html', 'w', encoding='utf-8') as f:
            f.write(html)
        
        print("HTML saved to /tmp/firefaucet_page.html")
        
        # Check for common elements
        print("\n=== Checking common selectors ===")
        
        # Balance selectors
        balance_selectors = [".user-balance", ".balance", "#balance", "[class*='balance']", 
                           ".wallet-balance", ".account-balance"]
        for sel in balance_selectors:
            count = await page.locator(sel).count()
            if count > 0:
                try:
                    text = await page.locator(sel).first.text_content()
                    print(f"Balance [{sel}]: {count} found, text: {text[:50]}")
                except:
                    print(f"Balance [{sel}]: {count} found, but couldn't get text")
        
        # Claim button selectors
        button_selectors = ["button:has-text('Get reward')", "button:has-text('Claim')", 
                          "button.btn-primary", ".claim-button", "button[type='submit']"]
        for sel in button_selectors:
            count = await page.locator(sel).count()
            if count > 0:
                try:
                    text = await page.locator(sel).first.text_content()
                    visible = await page.locator(sel).first.is_visible()
                    print(f"Button [{sel}]: {count} found, visible: {visible}, text: {text[:30]}")
                except:
                    print(f"Button [{sel}]: {count} found, but couldn't check visibility")
        
        # Check page text
        page_text = await page.evaluate("() => document.body.innerText")
        print(f"\n=== Page text (first 1000 chars) ===")
        print(page_text[:1000])
        
        # Take screenshot
        await page.screenshot(path="/tmp/firefaucet_inspect.png")
        print("\nScreenshot saved to /tmp/firefaucet_inspect.png")
        
    finally:
        await browser.close()

if __name__ == "__main__":
    asyncio.run(main())
