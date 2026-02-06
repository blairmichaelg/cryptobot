#!/usr/bin/env python3
"""
Simple script to log in via existing cookies and navigate to the faucet page
"""
import asyncio
import logging
import os
import sys
from pathlib import Path
from urllib.parse import urlparse

sys.path.insert(0, str(Path(__file__).parent))

from browser.instance import BrowserManager
from core.config import BotSettings
from core.registry import get_faucet_class

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


async def navigate_to_faucet_page(faucet_name: str):
    """Navigate to faucet page and save HTML."""
    
    logger.info(f"\n{'='*60}\nNAVIGATING TO FAUCET PAGE: {faucet_name}\n{'='*60}")
    
    settings = BotSettings()
    headless = os.getenv('HEADLESS', 'false').lower() == 'true'
    browser_mgr = BrowserManager(headless=headless)
    
    context = None
    try:
        await browser_mgr.launch()
        
        # Create context with existing cookies (faster login)
        context = await browser_mgr.create_context(profile_name=faucet_name)
        page = await context.new_page()
        
        # Get faucet class to determine base URL
        bot_class = get_faucet_class(faucet_name)
        if not bot_class:
            logger.error(f"Bot class not found for {faucet_name}")
            return
        
        bot = bot_class(settings, page)
        base_url = bot.base_url if hasattr(bot, 'base_url') else 'https://firefaucet.win'
        
        # Try to navigate directly to faucet page
        faucet_urls = [f"{base_url}/faucet/", f"{base_url}/faucet"]
        
        for faucet_url in faucet_urls:
            try:
                logger.info(f"[{faucet_name}] Navigating to: {faucet_url}")
                await page.goto(faucet_url, wait_until='domcontentloaded', timeout=30000)
                await asyncio.sleep(5)  # Wait for page to load fully
                
                current_url = page.url
                logger.info(f"[{faucet_name}] Current URL: {current_url}")
                
                # Check if we're on the faucet page
                parsed = urlparse(current_url)
                if 'faucet' in parsed.path.lower():
                    logger.info(f"[{faucet_name}] ✓ Successfully on faucet page!")
                    
                    # Wait a bit for dynamic content to load
                    await page.wait_for_timeout(3000)
                    
                    # Inspect page elements
                    logger.info(f"\n[{faucet_name}] INSPECTING PAGE ELEMENTS:\n")
                    
                    # Find all buttons
                    buttons = await page.locator('button').all()
                    logger.info(f"Found {len(buttons)} buttons:")
                    for i, btn in enumerate(buttons[:10]):  # Show first 10
                        try:
                            text = await btn.text_content(timeout=1000)
                            id_attr = await btn.get_attribute('id')
                            class_attr = await btn.get_attribute('class')
                            logger.info(f"  [{i}] text='{text}', id='{id_attr}', class='{class_attr}'")
                        except:
                            pass
                    
                    # Find all inputs
                    inputs = await page.locator('input[type="submit"], input[type="button"]').all()
                    logger.info(f"\nFound {len(inputs)} submit/button inputs:")
                    for i, inp in enumerate(inputs[:10]):
                        try:
                            value = await inp.get_attribute('value')
                            id_attr = await inp.get_attribute('id')
                            class_attr = await inp.get_attribute('class')
                            logger.info(f"  [{i}] value='{value}', id='{id_attr}', class='{class_attr}'")
                        except:
                            pass
                    
                    # Save HTML and screenshot
                    html = await page.content()
                    html_file = f"faucet_page_{faucet_name}.html"
                    with open(html_file, 'w', encoding='utf-8') as f:
                        f.write(html)
                    logger.info(f"\n[{faucet_name}] HTML saved to: {html_file}")
                    
                    screenshot_file = f"faucet_page_{faucet_name}.png"
                    await page.screenshot(path=screenshot_file, full_page=True)
                    logger.info(f"[{faucet_name}] Screenshot saved to: {screenshot_file}")
                    
                    break
            except Exception as e:
                logger.error(f"[{faucet_name}] Error navigating to {faucet_url}: {e}")
    
    except Exception as e:
        logger.error(f"[{faucet_name}] Error: {e}", exc_info=True)
    
    finally:
        if context:
            try:
                await context.close()
            except:
                pass
        await browser_mgr.close()
    
    logger.info("="*60)


async def main():
    """Main entry point."""
    await navigate_to_faucet_page("firefaucet")


if __name__ == "__main__":
    asyncio.run(main())
