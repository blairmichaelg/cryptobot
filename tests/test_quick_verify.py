"""
Quick test to verify key faucets can login and claim.
Tests representatives from each category.
"""
import asyncio
import sys
import os
from pathlib import Path
from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).parent))

# Load environment variables
load_dotenv()

from core.config import BotSettings
from browser.instance import BrowserManager
from core.registry import get_faucet_class
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Test these representative faucets
TEST_FAUCETS = [
    ("firefaucet", "FIREFAUCET"),
    ("tronpick", "TRONPICK"),
    ("litepick", "LITEPICK"),
    ("cointiply", "COINTIPLY"),
    ("dutchy", "DUTCHY"),
]

async def test_faucet(faucet_name: str, env_prefix: str, settings: BotSettings) -> dict:
    """Test a single faucet's login and basic operations."""
    result = {
        "name": faucet_name,
        "login": False,
        "balance": None,
        "timer": None,
        "error": None
    }
    
    browser = None
    try:
        # Get credentials
        username = os.getenv(f"{env_prefix}_USERNAME")
        password = os.getenv(f"{env_prefix}_PASSWORD")
        
        if not username or not password:
            result["error"] = f"Missing credentials: {env_prefix}_USERNAME/PASSWORD"
            return result
        
        print(f"\n{'='*60}")
        print(f"Testing: {faucet_name.upper()}")
        print(f"Account: {username}")
        print(f"{'='*60}")
        
        # Get faucet class
        faucet_class = get_faucet_class(faucet_name)
        if not faucet_class:
            result["error"] = "Faucet class not found"
            return result
        
        # Create browser
        headless = os.getenv('HEADLESS', 'false').lower() == 'true'
        browser = BrowserManager(
            headless=headless,
            timeout=90000,  # 90 second timeout
            block_images=settings.block_images,
            block_media=settings.block_media,
            user_agents=settings.user_agents
        )
        await browser.launch()
        
        # Create context and page
        context = await browser.create_context(
            proxy=None,
            user_agent=None,
            profile_name=username
        )
        page = await browser.new_page(context=context)
        
        # Create bot
        bot = faucet_class(settings, page)
        
        # Login
        print(f"\n🔐 Logging in...")
        login_success = await bot.login(username, password)
        result["login"] = login_success
        
        if not login_success:
            result["error"] = "Login returned False"
            return result
        
        print(f"✅ Login successful!")
        
        # Get balance
        try:
            balance = await bot.get_balance()
            result["balance"] = balance
            print(f"💰 Balance: {balance}")
        except Exception as e:
            print(f"⚠️  Balance check failed: {e}")
        
        # Get timer
        try:
            timer = await bot.get_timer()
            result["timer"] = timer
            print(f"⏰ Timer: {timer} seconds")
        except Exception as e:
            print(f"⚠️  Timer check failed: {e}")
        
        return result
        
    except Exception as e:
        result["error"] = str(e)
        logger.error(f"Test failed for {faucet_name}: {e}", exc_info=True)
        return result
        
    finally:
        if browser:
            try:
                await browser.close()
            except:
                pass

async def main():
    print("\n" + "="*80)
    print("QUICK FAUCET VERIFICATION TEST")
    print("Testing representative faucets from each category")
    print("="*80)
    
    settings = BotSettings()
    results = []
    
    for faucet_name, env_prefix in TEST_FAUCETS:
        result = await test_faucet(faucet_name, env_prefix, settings)
        results.append(result)
        await asyncio.sleep(1)  # Brief pause between tests
    
    # Summary
    print("\n" + "="*80)
    print("TEST SUMMARY")
    print("="*80)
    
    successful = [r for r in results if r["login"]]
    failed = [r for r in results if not r["login"]]
    
    print(f"\n✅ Successful: {len(successful)}/{len(results)}")
    for r in successful:
        print(f"   {r['name']}: Balance={r['balance']}, Timer={r['timer']}s")
    
    if failed:
        print(f"\n❌ Failed: {len(failed)}/{len(results)}")
        for r in failed:
            print(f"   {r['name']}: {r['error']}")
    
    return len(successful) == len(results)

if __name__ == "__main__":
    success = asyncio.run(main())
    sys.exit(0 if success else 1)
