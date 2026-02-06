#!/usr/bin/env python3
"""
Test FreeBitcoin claim end-to-end to identify the real issue.
"""

import asyncio
import os
import sys
from pathlib import Path
from dotenv import load_dotenv
import logging

# Add project root to path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from browser.instance import BrowserManager
from config.settings import BotSettings
from faucets.freebitcoin import FreeBitcoinBot

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

async def test_freebitcoin_claim():
    """Test full FreeBitcoin claim flow."""
    load_dotenv()
    
    settings = BotSettings()
    browser_manager = BrowserManager(settings)
    
    try:
        logger.info("🚀 Starting FreeBitcoin claim test...")
        
        # Create browser context
        context = await browser_manager.get_or_create_context(account_key="freebitcoin")
        page = await context.new_page()
        
        # Create bot instance
        bot = FreeBitcoinBot(settings, page)
        
        # Test login
        logger.info("\n" + "="*60)
        logger.info("STEP 1: LOGIN")
        logger.info("="*60)
        login_result = await bot.login()
        logger.info(f"Login result: {login_result}")
        
        if not login_result:
            logger.error("❌ Login failed!")
            return
        
        logger.info("✅ Login successful!")
        
        # Test balance extraction
        logger.info("\n" + "="*60)
        logger.info("STEP 2: BALANCE EXTRACTION")
        logger.info("="*60)
        balance = await bot.get_balance("#balance", fallback_selectors=["span.balance", ".user-balance"])
        logger.info(f"Balance: {balance}")
        
        # Test timer extraction
        logger.info("\n" + "="*60)
        logger.info("STEP 3: TIMER EXTRACTION")
        logger.info("="*60)
        timer = await bot.get_timer("#time_remaining", fallback_selectors=["span#timer", ".countdown"])
        logger.info(f"Timer (minutes): {timer}")
        
        # Test full claim
        logger.info("\n" + "="*60)
        logger.info("STEP 4: FULL CLAIM")
        logger.info("="*60)
        claim_result = await bot.claim()
        logger.info(f"\nClaim Result:")
        logger.info(f"  Success: {claim_result.success}")
        logger.info(f"  Status: {claim_result.status}")
        logger.info(f"  Balance: {claim_result.balance}")
        logger.info(f"  Amount: {claim_result.amount}")
        logger.info(f"  Next Claim: {claim_result.next_claim_minutes} minutes")
        
        if claim_result.success:
            logger.info("✅ Claim test PASSED!")
        else:
            logger.error(f"❌ Claim test FAILED: {claim_result.status}")
            
    except Exception as e:
        logger.error(f"❌ Test error: {e}", exc_info=True)
    finally:
        await browser_manager.close()

if __name__ == "__main__":
    asyncio.run(test_freebitcoin_claim())
