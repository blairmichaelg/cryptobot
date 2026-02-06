#!/usr/bin/env python3
"""
Test FireFaucet full claim flow.
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
            
        logger.info("Creating browser context...")
        context = await browser.create_context(profile_name=creds["username"])
        page = await context.new_page()
        
        faucet = FireFaucetBot(settings, page)
        
        # Test login
        logger.info("Testing login...")
        login_result = await faucet.login()
        logger.info(f"Login: {'SUCCESS' if login_result else 'FAILED'}")
        
        if login_result:
            # Take screenshot before claim
            await page.screenshot(path="/tmp/ff_before_claim.png")
            logger.info("Screenshot saved: /tmp/ff_before_claim.png")
            
            # Test claim
            logger.info("Testing claim...")
            claim_result = await faucet.claim()
            
            # Take screenshot after claim
            await page.screenshot(path="/tmp/ff_after_claim.png")
            logger.info("Screenshot saved: /tmp/ff_after_claim.png")
            
            # Get page info for debugging
            page_url = page.url
            page_title = await page.title()
            logger.info(f"After claim - URL: {page_url}")
            logger.info(f"After claim - Title: {page_title}")
            
            # Check for any visible messages
            try:
                messages = await page.locator(".alert, .toast, .modal, .swal2-popup, [class*='message'], [class*='success'], [class*='error']").all()
                logger.info(f"Found {len(messages)} message elements")
                for idx, msg in enumerate(messages[:5]):
                    try:
                        if await msg.is_visible():
                            text = await msg.text_content()
                            logger.info(f"  Message {idx+1}: {text[:200]}")
                    except:
                        pass
            except Exception as e:
                logger.error(f"Error checking messages: {e}")
            
            logger.info(f"Claim Result: {claim_result}")
            logger.info(f"  Success: {claim_result.success}")
            logger.info(f"  Status: {claim_result.status}")
            logger.info(f"  Amount: {claim_result.amount}")
            logger.info(f"  Next Claim: {claim_result.next_claim_minutes} minutes")
    except Exception as e:
        logger.error(f"Error: {e}", exc_info=True)
    finally:
        await browser.close()
        logger.info("Browser closed.")

if __name__ == "__main__":
    asyncio.run(main())
