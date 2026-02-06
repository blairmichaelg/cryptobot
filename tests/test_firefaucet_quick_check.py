#!/usr/bin/env python3
"""Quick test for FireFaucet claim page"""
import asyncio
import logging
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from browser.instance import BrowserManager
from core.config import BotSettings
from core.registry import get_faucet_class

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


async def test_firefaucet_claim():
    """Test FireFaucet claim button finding"""
    
    settings = BotSettings()
    headless = os.getenv('HEADLESS', 'false').lower() == 'true'
    browser_mgr = BrowserManager(headless=headless)
    
    context = None
    try:
        await browser_mgr.launch()
        
        # Create context with existing cookies (fast login)
        context = await browser_mgr.create_context(profile_name="firefaucet")
        page = await context.new_page()
        
        # Get bot class
        bot_class = get_faucet_class("firefaucet")
        if not bot_class:
            logger.error("Bot class not found")
            return
        
        bot = bot_class(settings, page)
        
        # Navigate to faucet page
        logger.info("Navigating to faucet page...")
        await page.goto("https://firefaucet.win/faucet", wait_until="domcontentloaded")
        
        # Wait for dynamic content
        await asyncio.sleep(3)
        
        # Check what's on the page
        all_buttons = await page.locator('button').count()
        all_inputs = await page.locator('input[type="submit"], input[type="button"]').count()
        logger.info(f"Page has {all_buttons} buttons and {all_inputs} submit inputs")
        
        # Log page title and URL
        logger.info(f"Page title: {await page.title()}")
        logger.info(f"Page URL: {page.url}")
        
        # Check for specific FireFaucet elements
        balance = await page.locator("[class*='balance']").count()
        timer = await page.locator("[class*='timer']").count()
        logger.info(f"Balance elements: {balance}, Timer elements: {timer}")
        
        if all_buttons > 0:
            logger.info("Buttons on page:")
            for i in range(min(all_buttons, 20)):
                btn = page.locator('button').nth(i)
                text = await btn.text_content()
                logger.info(f"  [{i}] {text[:100]}")
        
        # Try specific selectors
        logger.info("\nTesting selectors:")
        test_selectors = [
            "button:has-text('Get reward')",
            "button:visible",
            "#get_reward_button",
            "button",
            "input[type='submit']:visible"
        ]
        
        for sel in test_selectors:
            count = await page.locator(sel).count()
            logger.info(f"  Selector '{sel}': {count} matches")
        
        # Save page HTML
        html = await page.content()
        with open("firefaucet_claim_page.html", "w") as f:
            f.write(html)
        logger.info("HTML saved to firefaucet_claim_page.html")
        
    finally:
        if context:
            await context.close()
        await browser_mgr.close()


if __name__ == "__main__":
    asyncio.run(test_firefaucet_claim())
