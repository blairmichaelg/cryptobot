#!/usr/bin/env python3
"""
Test FireFaucet with multiple proxy sessions until we find one that works.
"""
import asyncio
import os
import logging
import random
import string
from dotenv import load_dotenv

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s - %(message)s")
logger = logging.getLogger(__name__)

async def test_with_proxy(session_id):
    """Test a single proxy session"""
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
            return False
            
        proxy_url = f"http://ub033d0d0583c05dd-zone-custom-session-{session_id}:ub033d0d0583c05dd@43.135.141.142:2334"
        
        logger.info(f"[{session_id}] Testing with proxy session: {session_id}")
        context = await browser.create_context(
            profile_name=creds["username"], 
            proxy=proxy_url,
            allow_sticky_proxy=False
        )
        page = await context.new_page()
        
        faucet = FireFaucetBot(settings, page)
        
        # Quick test - just try to navigate to faucet page
        try:
            await page.goto("https://firefaucet.win/faucet/", timeout=15000)
            title = await page.title()
            
            if "proxy" in title.lower() or "forbidden" in title.lower():
                logger.warning(f"[{session_id}] ❌ Proxy detected: {title}")
                return False
            else:
                logger.info(f"[{session_id}] ✅ Proxy seems OK: {title}")
                
                # Try full claim
                logger.info(f"[{session_id}] Attempting full claim...")
                claim_result = await faucet.claim()
                logger.info(f"[{session_id}] Result: {claim_result.success} - {claim_result.status}")
                
                return claim_result.success
                
        except Exception as e:
            if "PROXY_FORBIDDEN" in str(e) or "403" in str(e):
                logger.warning(f"[{session_id}] ❌ Proxy blocked: {e}")
            else:
                logger.error(f"[{session_id}] Error: {e}")
            return False
            
    finally:
        await browser.close()

async def main():
    """Try multiple proxy sessions"""
    logger.info("Testing multiple proxy sessions to find one that works...")
    
    for i in range(10):  # Try up to 10 different sessions
        session_id = ''.join(random.choices(string.ascii_lowercase + string.digits, k=8))
        
        success = await test_with_proxy(session_id)
        if success:
            logger.info(f"🎉 SUCCESS with session: {session_id}")
            break
        
        logger.info(f"Tried {i+1} sessions so far, trying next...")
        await asyncio.sleep(2)  # Brief pause between attempts
    else:
        logger.error("Failed to find a working proxy session after 10 attempts")

if __name__ == "__main__":
    asyncio.run(main())
