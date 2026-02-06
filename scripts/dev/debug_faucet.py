"""
Debug script to test faucet claims with verbose output.
Tests login, balance, timer, and claim in sequence.
"""
import asyncio
import sys
import traceback
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from core.config import BotSettings
from core.registry import get_faucet_class
from browser.instance import BrowserManager
import logging

# Set up verbose logging
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s [%(levelname)s] %(name)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)

async def test_faucet(faucet_name: str = "firefaucet"):
    """Test a single faucet with full debug output."""
    print("=" * 80)
    print(f"🔧 DEBUG FAUCET TEST: {faucet_name.upper()}")
    print("=" * 80)
    
    # Load settings
    settings = BotSettings()
    settings.headless = False  # Visible mode for debugging
    
    # Get account
    account = settings.get_account(faucet_name)
    if not account:
        print(f"❌ No {faucet_name} account configured in .env")
        return False
    
    print(f"📧 Account: {account.get('username', 'N/A')}")
    print(f"🔑 2Captcha: {'✓' if settings.twocaptcha_api_key else '✗'}")
    print(f"🔑 CapSolver: {'✓' if settings.capsolver_api_key else '✗'}")
    
    # Create browser manager
    browser_mgr = BrowserManager(
        headless=False,
        block_images=False,  # Don't block images for debugging
        block_media=True
    )
    
    page = None
    bot = None
    success = False
    
    try:
        # Launch browser
        print("\n🌐 Launching browser...")
        await browser_mgr.launch()
        print("✅ Browser launched")
        
        # Create page
        print("📄 Creating new page...")
        page = await browser_mgr.new_page()
        print(f"✅ Page created")
        
        # Get bot class
        bot_class = get_faucet_class(faucet_name)
        if not bot_class:
            print(f"❌ {faucet_name} bot class not found in registry")
            return False
        
        print(f"🤖 Creating {faucet_name} bot...")
        bot = bot_class(settings, page)
        bot.settings_account_override = account
        
        # Test Login
        print("\n" + "-" * 40)
        print("🔐 TESTING LOGIN...")
        print("-" * 40)
        
        try:
            login_result = await bot.login()
            print(f"Login result: {login_result}")
            
            if not login_result:
                print("❌ Login FAILED")
                # Keep browser open for inspection
                print("\n⏸️ Browser stays open for 30 seconds for inspection...")
                await asyncio.sleep(30)
                return False
            
            print("✅ Login SUCCESSFUL!")
            
        except Exception as e:
            print(f"❌ Login exception: {e}")
            traceback.print_exc()
            await asyncio.sleep(30)
            return False
        
        # Test Balance
        print("\n" + "-" * 40)
        print("💰 TESTING GET_BALANCE...")
        print("-" * 40)
        
        try:
            balance = await bot.get_balance()
            print(f"Balance: {balance}")
        except Exception as e:
            print(f"⚠️ Balance error: {e}")
            traceback.print_exc()
        
        # Test Timer
        print("\n" + "-" * 40)
        print("⏰ TESTING GET_TIMER...")
        print("-" * 40)
        
        timer = None
        try:
            timer = await bot.get_timer()
            print(f"Timer: {timer} minutes until next claim")
        except Exception as e:
            print(f"⚠️ Timer error: {e}")
            traceback.print_exc()
        
        # Test Claim if timer is 0
        print("\n" + "-" * 40)
        print("🎰 TESTING CLAIM...")
        print("-" * 40)
        
        if timer == 0:
            try:
                result = await bot.claim()
                print(f"Claim result: {result}")
                
                if result and result.success:
                    print("\n" + "=" * 80)
                    print("🎉 CLAIM SUCCESSFUL!")
                    print(f"   Amount: {result.amount}")
                    print(f"   Balance: {result.balance}")
                    print(f"   Next claim: {result.next_claim_minutes} min")
                    print("=" * 80)
                    success = True
                else:
                    print(f"❌ Claim failed: {result.error if result else 'No result'}")
            except Exception as e:
                print(f"❌ Claim exception: {e}")
                traceback.print_exc()
        else:
            print(f"⏳ Timer not at 0 (is {timer}), skipping claim")
            # Still count as partial success if login worked
            success = True
        
        print("\n⏸️ Browser stays open for 15 seconds...")
        await asyncio.sleep(15)
        
    except Exception as e:
        print(f"\n❌ CRITICAL ERROR: {e}")
        traceback.print_exc()
        await asyncio.sleep(30)
        
    finally:
        print("\n🧹 Cleaning up...")
        try:
            await browser_mgr.close()
        except Exception as e:
            print(f"Cleanup error: {e}")
    
    return success


async def main():
    """Test multiple faucets in order of likelihood to work."""
    # Priority order: faucets most likely to work first
    faucets_to_test = [
        "firefaucet",    # Usually reliable
        "cointiply",     # Good success rate
        "freebitcoin",   # Known login issues but worth trying
        "dutchy",        # Sometimes works
        # Pick.io faucets have broken Turnstile, skip for now
    ]
    
    # Check which faucets have accounts
    settings = BotSettings()
    available_faucets = []
    for f in faucets_to_test:
        account = settings.get_account(f)
        if account:
            available_faucets.append(f)
            print(f"✓ {f}: {account.get('username', 'configured')}")
        else:
            print(f"✗ {f}: no credentials")
    
    if not available_faucets:
        print("\n❌ No faucets configured! Check your .env file.")
        return
    
    print(f"\n🎯 Will test: {', '.join(available_faucets)}")
    print("=" * 80)
    
    # Test faucets until one succeeds
    for faucet in available_faucets:
        print(f"\n\n{'='*80}")
        print(f"TESTING: {faucet.upper()}")
        print(f"{'='*80}\n")
        
        success = await test_faucet(faucet)
        
        if success:
            print(f"\n\n✅ SUCCESS with {faucet}!")
            break
        else:
            print(f"\n⚠️ {faucet} test completed (may have issues)")
            
        # Brief pause between faucets
        await asyncio.sleep(3)
    
    print("\n" + "=" * 80)
    print("DEBUG SESSION COMPLETE")
    print("=" * 80)


if __name__ == "__main__":
    asyncio.run(main())
