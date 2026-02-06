"""
Minimal test to see if faucet bot can actually execute a claim.
Tests the full flow: browser launch -> login -> claim -> result
"""
import asyncio
import logging
from core.config import BotSettings
from browser.instance import BrowserManager
from faucets.tronpick import TronPickBot
from faucets.base import ClaimResult

logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(name)s - %(message)s')
logger = logging.getLogger(__name__)

async def test_tronpick_claim():
    """Test a single TronPick claim from start to finish"""
    
    logger.info("=" * 60)
    logger.info("TESTING: TronPick Full Claim Flow")
    logger.info("=" * 60)
    
    # 1. Initialize settings
    settings = BotSettings()
    logger.info(f"✓ Settings loaded")
    logger.info(f"  - Headless: {settings.headless}")
    logger.info(f"  - Timeout: {settings.timeout}ms")
    logger.info(f"  - CAPTCHA Provider: {settings.captcha_provider}")
    logger.info(f"  - CAPTCHA API Key: {'✓ Set' if settings.twocaptcha_api_key else '✗ MISSING'}")
    
    # 2. Initialize browser
    browser_manager = BrowserManager(
        headless=False,  # Force visible for debugging
        block_images=settings.block_images,
        timeout=settings.timeout
    )
    
    try:
        logger.info("\n📱 Launching browser...")
        await browser_manager.launch()
        logger.info("✓ Browser launched successfully")
        
        # 3. Create context and page
        logger.info("\n🌐 Creating browser context...")
        context = await browser_manager.create_context(proxy=None, profile_name="test_tronpick")
        page = await browser_manager.new_page(context=context)
        logger.info("✓ Page created successfully")
        
        # 4. Initialize bot
        logger.info("\n🤖 Initializing TronPick bot...")
        bot = TronPickBot(settings, page)
        
        # Set credentials
        bot.settings_account_override = {
            "email": settings.get_account("tronpick").get("username"),
            "username": settings.get_account("tronpick").get("username"),
            "password": settings.get_account("tronpick").get("password")
        }
        logger.info(f"✓ Bot initialized with account: {bot.settings_account_override.get('email')}")
        
        # 5. Test login
        logger.info("\n🔐 Testing login...")
        try:
            login_result = await asyncio.wait_for(bot.login(), timeout=120)
            if login_result:
                logger.info("✅ LOGIN SUCCESSFUL!")
            else:
                logger.error("❌ LOGIN FAILED")
                return False
        except asyncio.TimeoutError:
            logger.error("❌ LOGIN TIMEOUT (120s)")
            return False
        except Exception as e:
            logger.error(f"❌ LOGIN EXCEPTION: {e}", exc_info=True)
            return False
        
        # 6. Get balance and timer
        logger.info("\n💰 Checking balance and timer...")
        try:
            balance = await bot.get_balance()
            timer = await bot.get_timer()
            logger.info(f"✓ Balance: {balance} TRX")
            logger.info(f"✓ Timer: {timer} minutes")
        except Exception as e:
            logger.error(f"❌ Balance/Timer check failed: {e}")
        
        # 7. Attempt claim
        if timer == 0.0:
            logger.info("\n🎯 Attempting claim...")
            try:
                claim_result = await asyncio.wait_for(bot.claim(), timeout=180)
                logger.info(f"✓ Claim completed!")
                logger.info(f"  - Success: {claim_result.success}")
                logger.info(f"  - Status: {claim_result.status}")
                logger.info(f"  - Amount: {claim_result.amount if hasattr(claim_result, 'amount') else 'N/A'}")
                logger.info(f"  - Next claim: {claim_result.next_claim_minutes if hasattr(claim_result, 'next_claim_minutes') else 'N/A'} min")
                
                if claim_result.success:
                    logger.info("\n✅✅✅ FULL CLAIM SUCCESSFUL! ✅✅✅")
                    return True
                else:
                    logger.warning(f"\n⚠️ Claim unsuccessful: {claim_result.status}")
                    return False
                    
            except asyncio.TimeoutError:
                logger.error("❌ CLAIM TIMEOUT (180s)")
                return False
            except Exception as e:
                logger.error(f"❌ CLAIM EXCEPTION: {e}", exc_info=True)
                return False
        else:
            logger.info(f"\n⏱️ Timer active - waiting {timer} minutes before claim")
            return None  # Neutral - can't test claim yet
        
    finally:
        logger.info("\n🧹 Cleaning up...")
        await browser_manager.close()
        logger.info("=" * 60)

if __name__ == "__main__":
    result = asyncio.run(test_tronpick_claim())
    if result == True:
        print("\n✅ TEST PASSED - Claim successful!")
        exit(0)
    elif result == False:
        print("\n❌ TEST FAILED - Claim unsuccessful")
        exit(1)
    else:
        print("\n⏱️ TEST INCOMPLETE - Timer active, can't claim yet")
        exit(2)
