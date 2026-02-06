#!/usr/bin/env python3
"""
Test FireFaucet full claim flow WITHOUT proxy.
"""
import asyncio
import os
import logging
from dotenv import load_dotenv

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s - %(message)s")
logger = logging.getLogger(__name__)

async def main():
    from browser.instance import BrowserManager
    from faucets.firefaucet import FireFaucetBot
    from core.config import BotSettings
    
    load_dotenv()
    settings = BotSettings()
    browser = BrowserManager(headless=True)
    await browser.launch()
    
    try:
        creds = settings.get_account("fire_faucet")
        if not creds:
            logger.error("No fire_faucet credentials found!")
            return
            
        logger.info("Creating browser context WITHOUT proxy...")
        context = await browser.create_context(profile_name=creds["username"], proxy=None, allow_sticky_proxy=False)  # No proxy
        page = await context.new_page()
        
        faucet = FireFaucetBot(settings, page)
        
        # Test login
        logger.info("Testing login...")
        login_result = await faucet.login()
        logger.info(f"Login: {'SUCCESS' if login_result else 'FAILED'}")
        
        if login_result:
            # Take screenshot before claim
            await page.screenshot(path="/tmp/ff_noproxy_before_claim.png")
            logger.info("Screenshot saved: /tmp/ff_noproxy_before_claim.png")
            
            # Test claim
            logger.info("Testing claim...")
            claim_result = await faucet.claim()
            
            # Take screenshot after claim
            await page.screenshot(path="/tmp/ff_noproxy_after_claim.png")
            logger.info("Screenshot saved: /tmp/ff_noproxy_after_claim.png")
            
            # Show page state after claim
            url = page.url
            title = await page.title()
            logger.info(f"After claim - URL: {url}")
            logger.info(f"After claim - Title: {title}")
            
            # Get page body text to see error message
            body_text = await page.locator("body").text_content()
            logger.info(f"Page body (first 500 chars): {body_text[:500] if body_text else 'NO TEXT'}")
            
            # Look for success/error messages
            messages = await page.locator(".alert, .message, .notification, .toast").all()
            logger.info(f"Found {len(messages)} message elements")
            for msg in messages:
                text = await msg.text_content()
                logger.info(f"  Message: {text}")
            
            logger.info(f"Claim Result: {claim_result}")
            logger.info(f"  Success: {claim_result.success}")
            logger.info(f"  Status: {claim_result.status}")
            logger.info(f"  Amount: {claim_result.amount}")
            logger.info(f"  Next Claim: {claim_result.next_claim_minutes} minutes")
            
    finally:
        await browser.close()
        logger.info("Browser closed.")

if __name__ == "__main__":
    asyncio.run(main())
