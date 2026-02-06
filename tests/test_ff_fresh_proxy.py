#!/usr/bin/env python3
"""
Test FireFaucet with a fresh proxy session.
"""
import asyncio
import os
import logging
import random
import string
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
            
        # Generate a fresh proxy session ID
        session_id = ''.join(random.choices(string.ascii_lowercase + string.digits, k=8))
        proxy_url = f"http://ub033d0d0583c05dd-zone-custom-session-{session_id}:ub033d0d0583c05dd@43.135.141.142:2334"
        
        logger.info(f"Creating browser context with FRESH proxy session: {session_id}")
        # Use allow_sticky_proxy=False to force the new proxy
        context = await browser.create_context(
            profile_name=creds["username"], 
            proxy=proxy_url,
            allow_sticky_proxy=False
        )
        page = await context.new_page()
        
        faucet = FireFaucetBot(settings, page)
        
        # Test login
        logger.info("Testing login...")
        login_result = await faucet.login()
        logger.info(f"Login: {'SUCCESS' if login_result else 'FAILED'}")
        
        if login_result:
            # Take screenshot before claim
            await page.screenshot(path="/tmp/ff_fresh_before.png")
            logger.info("Screenshot saved before claim")
            
            # Test claim
            logger.info("Testing claim...")
            claim_result = await faucet.claim()
            
            # Take screenshot after claim
            await page.screenshot(path="/tmp/ff_fresh_after.png")
            logger.info("Screenshot saved after claim")
            
            url = page.url
            title = await page.title()
            logger.info(f"URL: {url}")
            logger.info(f"Title: {title}")
            
            # Check for proxy detection
            body_text = await page.locator("body").text_content()
            if "proxy" in body_text.lower() or "vpn" in body_text.lower():
                logger.error(f"PROXY DETECTED! Body: {body_text[:300]}")
            
            logger.info(f"Result: {claim_result}")
            logger.info(f"  Success: {claim_result.success}")
            logger.info(f"  Status: {claim_result.status}")
            logger.info(f"  Amount: {claim_result.amount}")
            
    finally:
        await browser.close()
        logger.info("Browser closed.")

if __name__ == "__main__":
    asyncio.run(main())
