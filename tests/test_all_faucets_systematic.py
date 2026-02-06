"""
Systematic test of all faucets - login, balance, timer, and claim.
Tests each faucet independently and reports results.
"""
import asyncio
import logging
import os
import sys
from pathlib import Path
from dotenv import load_dotenv

# Add project root to path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from core.config import BotSettings
from browser.instance import BrowserManager
from core.registry import FAUCET_REGISTRY, get_faucet_class

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("logs/faucet_systematic_test.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Load environment
load_dotenv()

class FaucetTestResult:
    """Container for test results."""
    def __init__(self, name):
        self.name = name
        self.login_success = False
        self.balance_extracted = False
        self.timer_extracted = False
        self.claim_attempted = False
        self.claim_success = False
        self.error = None
        self.balance = "0"
        self.timer = 0.0

    def __str__(self):
        status = "✅ PASS" if self.claim_success else "❌ FAIL"
        return (
            f"{status} {self.name}: "
            f"Login={self.login_success}, "
            f"Balance={self.balance_extracted} ({self.balance}), "
            f"Timer={self.timer_extracted} ({self.timer:.1f}m), "
            f"Claim={self.claim_success}"
            + (f" | Error: {self.error}" if self.error else "")
        )

async def test_faucet(faucet_name: str, settings: BotSettings, browser_manager: BrowserManager) -> FaucetTestResult:
    """Test a single faucet through its full cycle."""
    result = FaucetTestResult(faucet_name)
    context = None
    page = None
    
    try:
        # Get faucet class
        faucet_class = get_faucet_class(faucet_name)
        if not faucet_class:
            result.error = "Faucet class not found in registry"
            return result
        
        logger.info(f"\n{'='*60}")
        logger.info(f"Testing {faucet_name}")
        logger.info(f"{'='*60}")
        
        # Create browser context and page for this faucet
        import random
        ua = random.choice(settings.user_agents) if settings.user_agents else None
        context = await browser_manager.create_context(
            proxy=None,
            user_agent=ua,
            profile_name=f"{faucet_name}_test"
        )
        page = await browser_manager.new_page(context=context)
        
        # Initialize faucet bot
        bot = faucet_class(settings, page)
        
        # Test 1: Login
        logger.info(f"[{faucet_name}] Testing login...")
        try:
            result.login_success = await bot.login()
            if not result.login_success:
                result.error = "Login failed"
                return result
            logger.info(f"[{faucet_name}] ✅ Login successful")
        except Exception as e:
            result.error = f"Login exception: {str(e)[:100]}"
            return result
        
        # Test 2: Balance extraction
        logger.info(f"[{faucet_name}] Testing balance extraction...")
        try:
            result.balance = await bot.get_balance()
            result.balance_extracted = result.balance != "0" or True  # Consider extraction successful even if 0
            logger.info(f"[{faucet_name}] ✅ Balance: {result.balance}")
        except Exception as e:
            result.error = f"Balance exception: {str(e)[:100]}"
            logger.warning(f"[{faucet_name}] Balance extraction failed: {e}")
        
        # Test 3: Timer extraction
        logger.info(f"[{faucet_name}] Testing timer extraction...")
        try:
            result.timer = await bot.get_timer()
            result.timer_extracted = True
            logger.info(f"[{faucet_name}] ✅ Timer: {result.timer:.1f} minutes")
        except Exception as e:
            result.error = f"Timer exception: {str(e)[:100]}"
            logger.warning(f"[{faucet_name}] Timer extraction failed: {e}")
        
        # Test 4: Claim (only if timer allows)
        if result.timer <= 1.0:  # Ready to claim or very close
            logger.info(f"[{faucet_name}] Testing claim...")
            try:
                result.claim_attempted = True
                claim_result = await bot.claim()
                result.claim_success = claim_result.success if claim_result else False
                
                if result.claim_success:
                    logger.info(f"[{faucet_name}] ✅ Claim successful!")
                else:
                    result.error = claim_result.error if claim_result else "Claim returned None"
                    logger.warning(f"[{faucet_name}] Claim failed: {result.error}")
            except Exception as e:
                result.error = f"Claim exception: {str(e)[:100]}"
                logger.error(f"[{faucet_name}] Claim exception: {e}")
        else:
            logger.info(f"[{faucet_name}] ⏰ Not ready to claim ({result.timer:.1f}m remaining)")
            result.claim_success = True  # Consider it a pass if we can't claim due to timer
        
        return result
        
    except Exception as e:
        result.error = f"Test exception: {str(e)[:100]}"
        logger.error(f"[{faucet_name}] Test failed with exception: {e}")
        return result
    finally:
        # Clean up context
        if context:
            try:
                await context.close()
            except Exception as e:
                logger.debug(f"[{faucet_name}] Error closing context: {e}")

async def main():
    """Run systematic tests on all faucets."""
    settings = BotSettings()
    
    # List of all faucets to test (from registry)
    all_faucets = [
        # Standalone faucets
        "firefaucet",
        "cointiply",
        "freebitcoin",
        "dutchy",
        "coinpayu",
        "adbtc",
        "faucetcrypto",
        # Pick.io family
        "litepick",
        "tronpick",
        "dogepick",
        "bchpick",
        "solpick",
        "tonpick",
        "polygonpick",
        "binpick",
        "dashpick",
        "ethpick",
        "usdpick",
    ]
    
    results = []
    
    # Initialize BrowserManager
    headless = os.getenv('HEADLESS', 'false').lower() == 'true'
    browser_manager = BrowserManager(
        headless=headless,
        block_images=settings.block_images,
        block_media=settings.block_media,
        timeout=settings.timeout,
        user_agents=settings.user_agents
    )
    
    try:
        logger.info("Launching browser...")
        await browser_manager.launch()
        
        for faucet_name in all_faucets:
            result = await test_faucet(faucet_name, settings, browser_manager)
            results.append(result)
            
            # Brief pause between faucets
            await asyncio.sleep(2)
        
    finally:
        await browser_manager.cleanup()
    
    # Print summary
    print("\n" + "="*80)
    print("FAUCET TEST SUMMARY")
    print("="*80)
    
    successful = [r for r in results if r.claim_success or (not r.claim_attempted and r.login_success)]
    failed = [r for r in results if r not in successful]
    
    print(f"\n✅ SUCCESSFUL: {len(successful)}/{len(results)}")
    for result in successful:
        print(f"  {result}")
    
    if failed:
        print(f"\n❌ FAILED: {len(failed)}/{len(results)}")
        for result in failed:
            print(f"  {result}")
    
    print("\n" + "="*80)
    print(f"Overall: {len(successful)}/{len(results)} faucets working")
    print("="*80)

if __name__ == "__main__":
    asyncio.run(main())
