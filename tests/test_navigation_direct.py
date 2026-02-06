#!/usr/bin/env python3
"""Test direct navigation without proxies to diagnose Cloudflare/bot detection."""

import asyncio
import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent))

from browser.instance import BrowserManager
from core.config import BotSettings
import logging

logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(name)s - %(message)s')
logger = logging.getLogger(__name__)

async def test_navigation():
    """Test navigating to various sites without proxies."""
    
    settings = BotSettings()
    browser_mgr = BrowserManager(
        headless=True,
        proxy=None,  # NO PROXY
        block_images=False,  # Load images to appear more human
        block_media=False,
        timeout=30000  # 30s timeout
    )
    
    test_sites = [
        ("Google", "https://www.google.com"),
        ("Example.com", "https://example.com"),
        ("Cointiply", "https://cointiply.com"),
        ("UsdPick", "https://usdpick.io"),
        ("FireFaucet", "https://firefaucet.win"),
    ]
    
    try:
        await browser_mgr.launch()
        logger.info("✅ Browser launched successfully")
        
        # Create context without proxy
        context = await browser_mgr.create_context(
            proxy=None,
            profile_name="test_user",
            allow_sticky_proxy=False,
            block_images_override=False
        )
        logger.info("✅ Context created without proxy")
        
        page = await browser_mgr.new_page(context=context)
        logger.info("✅ Page created")
        
        for site_name, url in test_sites:
            logger.info(f"\n{'='*60}")
            logger.info(f"Testing: {site_name} - {url}")
            logger.info(f"{'='*60}")
            
            try:
                logger.info(f"Navigating to {url}...")
                await page.goto(url, wait_until="domcontentloaded", timeout=30000)
                logger.info(f"✅ {site_name}: Navigation succeeded!")
                
                # Get title
                title = await page.title()
                logger.info(f"   Page title: {title}")
                
                # Check for Cloudflare challenge
                content = await page.content()
                if "cloudflare" in content.lower() and "challenge" in content.lower():
                    logger.warning(f"⚠️  {site_name}: Cloudflare challenge detected!")
                elif "just a moment" in content.lower():
                    logger.warning(f"⚠️  {site_name}: Cloudflare 'Just a moment' page detected!")
                else:
                    logger.info(f"✅ {site_name}: No Cloudflare challenge detected")
                    
            except Exception as e:
                logger.error(f"❌ {site_name}: Navigation failed - {e}")
                
            await asyncio.sleep(2)  # Pause between tests
            
    except Exception as e:
        logger.error(f"❌ Test failed: {e}", exc_info=True)
    finally:
        try:
            await browser_mgr.close()
            logger.info("✅ Browser closed")
        except Exception as e:
            logger.error(f"Error closing browser: {e}")

if __name__ == "__main__":
    asyncio.run(test_navigation())
