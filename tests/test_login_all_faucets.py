"""
Comprehensive login test for all 18 faucets.
Tests each faucet's login capability and reports status.
"""
import asyncio
import logging
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent))

from core.config import BotSettings
from core.registry import FAUCET_REGISTRY, get_faucet_class
from browser.instance import BrowserManager

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Suppress verbose logs
logging.getLogger('playwright').setLevel(logging.WARNING)
logging.getLogger('urllib3').setLevel(logging.WARNING)

async def test_faucet_login(faucet_name: str, browser_manager: BrowserManager, settings: BotSettings, context, page) -> dict:
    """Test login for a single faucet.
    
    Returns:
        dict with status, message, and error details
    """
    result = {
        'name': faucet_name,
        'success': False,
        'message': '',
        'has_login_method': False,
        'has_credentials': False
    }
    
    try:
        # Get faucet class
        faucet_class = get_faucet_class(faucet_name)
        if not faucet_class:
            result['message'] = 'Not found in registry'
            return result
        
        # Check if login method exists
        result['has_login_method'] = hasattr(faucet_class, 'login')
        if not result['has_login_method']:
            result['message'] = 'No login method'
            return result
        
        # Initialize bot
        bot = faucet_class(settings, page)
        
        # Check credentials
        creds = bot.get_credentials(faucet_name.lower())
        result['has_credentials'] = bool(creds)
        if not creds:
            result['message'] = 'No credentials found'
            return result
        
        # Set account override
        override = {
            "username": creds.get('username') or creds.get('email'),
            "password": creds.get('password')
        }
        bot.settings_account_override = override
        
        # Attempt login
        logger.info(f"[{faucet_name}] Starting login test...")
        login_success = await asyncio.wait_for(bot.login(), timeout=120)
        
        result['success'] = login_success
        result['message'] = 'Login successful' if login_success else 'Login failed'
        
        return result
        
    except asyncio.TimeoutError:
        result['message'] = 'Login timeout (120s)'
        return result
    except Exception as e:
        result['message'] = f'Exception: {str(e)[:100]}'
        logger.error(f"[{faucet_name}] Login test error: {e}", exc_info=True)
        return result

async def main():
    """Test all faucets."""
    logger.info("=" * 80)
    logger.info("COMPREHENSIVE FAUCET LOGIN TEST")
    logger.info("=" * 80)
    
    # All faucets to test
    faucet_names = [
        # Direct imports (7 faucets)
        "firefaucet", "cointiply", "freebitcoin", "dutchy", 
        "coinpayu", "adbtc", "faucetcrypto",
        # Pick.io family (11 faucets)
        "litepick", "tronpick", "dogepick", "bchpick", "solpick", 
        "tonpick", "polygonpick", "binpick", "dashpick", "ethpick", "usdpick"
    ]
    
    import os
    settings = BotSettings()
    headless = os.getenv('HEADLESS', 'false').lower() == 'true'
    
    browser_manager = BrowserManager(
        headless=headless,
        block_images=settings.block_images,
        block_media=settings.block_media,
        timeout=settings.timeout,
        user_agents=settings.user_agents
    )
    
    try:
        # Launch browser
        logger.info("Launching browser...")
        await browser_manager.launch()
        
        # Create a single shared context and page for all tests
        import random
        ua = random.choice(settings.user_agents) if settings.user_agents else None
        context = await browser_manager.create_context(
            proxy=None,
            user_agent=ua,
            profile_name="test_profile"
        )
        page = await browser_manager.new_page(context=context)
        
        results = []
        
        # Test each faucet
        for faucet_name in faucet_names:
            logger.info(f"\n{'='*60}")
            logger.info(f"Testing: {faucet_name.upper()}")
            logger.info(f"{'='*60}")
            
            result = await test_faucet_login(faucet_name, browser_manager, settings, context, page)
            results.append(result)
            
            # Log result
            status_emoji = "✅" if result['success'] else "❌"
            logger.info(f"{status_emoji} {faucet_name}: {result['message']}")
            
            # Small delay between tests
            await asyncio.sleep(2)
        
        # Summary report
        logger.info("\n" + "=" * 80)
        logger.info("SUMMARY REPORT")
        logger.info("=" * 80)
        
        successful = [r for r in results if r['success']]
        failed = [r for r in results if not r['success']]
        
        logger.info(f"\nTotal faucets: {len(results)}")
        logger.info(f"✅ Successful logins: {len(successful)}")
        logger.info(f"❌ Failed logins: {len(failed)}")
        
        if failed:
            logger.info("\nFailed faucets breakdown:")
            no_login = [r for r in failed if not r['has_login_method']]
            no_creds = [r for r in failed if r['has_login_method'] and not r['has_credentials']]
            login_failed = [r for r in failed if r['has_login_method'] and r['has_credentials']]
            
            if no_login:
                logger.info(f"\n  Missing login method ({len(no_login)}):")
                for r in no_login:
                    logger.info(f"    - {r['name']}")
            
            if no_creds:
                logger.info(f"\n  Missing credentials ({len(no_creds)}):")
                for r in no_creds:
                    logger.info(f"    - {r['name']}")
            
            if login_failed:
                logger.info(f"\n  Login failures ({len(login_failed)}):")
                for r in login_failed:
                    logger.info(f"    - {r['name']}: {r['message']}")
        
        logger.info("\n" + "=" * 80)
        
    except Exception as e:
        logger.error(f"Test suite error: {e}", exc_info=True)
    finally:
        # Cleanup
        try:
            await browser_manager.cleanup()
        except Exception as e:
            logger.error(f"Cleanup error: {e}")

if __name__ == "__main__":
    asyncio.run(main())
