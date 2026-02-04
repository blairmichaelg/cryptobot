#!/usr/bin/env python3
"""Quick test for FireFaucet login and claim flow."""
import asyncio
import logging
import os
import sys

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(name)s - %(message)s')
logger = logging.getLogger(__name__)

async def test_firefaucet():
    """Test FireFaucet login and claim."""
    from browser.instance import BrowserManager
    from faucets.firefaucet import FireFaucetBot
    from core.config import BotSettings
    
    settings = BotSettings()
    bm = BrowserManager()
    
    # Check headless mode
    headless = os.environ.get('HEADLESS', '').lower() == 'true' or sys.platform == 'linux'
    logger.info(f"Browser mode: {'headless' if headless else 'visible'}")
    
    try:
        await bm.launch(headless=headless)
        ctx = await bm.create_context('test_firefaucet')
        page = await ctx.new_page()
        
        bot = FireFaucetBot(settings, page)
        
        # Test login
        logger.info("Testing login...")
        login_result = await bot.login()
        logger.info(f"Login result: {login_result}")
        
        if login_result:
            logger.info("✅ Login successful! Testing faucet page...")
            
            # Navigate to faucet
            await page.goto('https://firefaucet.win/faucet')
            await asyncio.sleep(3)
            
            # Log page info
            logger.info(f"Page title: {await page.title()}")
            logger.info(f"URL: {page.url}")
            
            # Check for buttons
            buttons = await page.locator('button').all()
            logger.info(f"Found {len(buttons)} buttons on page")
            for i, btn in enumerate(buttons[:10]):
                try:
                    text = await btn.text_content()
                    visible = await btn.is_visible()
                    logger.info(f"  Button {i+1}: '{text.strip()[:50]}' visible={visible}")
                except:
                    pass
            
            # Check balance/timer using bot methods
            balance_selectors = [".user-balance", ".balance", "#user-balance"]
            timer_selectors = [".fa-clock + span", "#claim_timer", ".timer"]
            
            balance = await bot.get_balance(balance_selectors[0], fallback_selectors=balance_selectors[1:])
            timer = await bot.get_timer(timer_selectors[0], fallback_selectors=timer_selectors[1:])
            logger.info(f"Balance: {balance}, Timer: {timer} minutes")
            
            # Try claim
            if timer == 0:
                logger.info("Attempting claim...")
                claim_result = await bot.claim()
                logger.info(f"Claim result: {claim_result}")
            else:
                logger.info(f"Timer active, claim not ready ({timer} min remaining)")
                
        else:
            logger.error("❌ Login failed")
            
    except Exception as e:
        logger.error(f"Test error: {e}", exc_info=True)
    finally:
        try:
            await bm.close()
        except:
            pass

if __name__ == "__main__":
    asyncio.run(test_firefaucet())
