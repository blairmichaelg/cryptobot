"""
Simple test script to verify faucet claims work on Azure VM.
Usage: HEADLESS=true python test_simple_claim.py <faucet_name>
Example: HEADLESS=true python test_simple_claim.py firefaucet
"""
import asyncio
import sys
import os
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent))

from core.config import BotSettings
from browser.instance import BrowserManager
from core.registry import get_faucet_class


async def test_faucet(faucet_name: str):
    """Test a single faucet's login and claim flow."""
    print(f"\n{'='*80}")
    print(f"🧪 TESTING: {faucet_name.upper()}")
    print(f"{'='*80}\n")
    
    # Load settings
    settings = BotSettings()
    headless = os.getenv('HEADLESS', 'true').lower() == 'true'
    settings.headless = headless
    
    # Get account credentials
    account = settings.get_account(faucet_name)
    if not account:
        print(f"❌ No account credentials found for {faucet_name}")
        print(f"   Check .env for {faucet_name.upper()}_USERNAME and {faucet_name.upper()}_PASSWORD")
        return False
    
    print(f"📧 Account: {account.get('username', account.get('email', 'N/A'))}")
    print(f"🖥️  Headless: {headless}\n")
    
    # Initialize browser
    browser_mgr = BrowserManager(
        headless=headless,
        block_images=settings.block_images,
        block_media=settings.block_media,
        timeout=settings.timeout,
        user_agents=settings.user_agents
    )
    
    try:
        print("🌐 Launching browser...")
        await browser_mgr.launch()
        
        # Create context and page
        context = await browser_mgr.create_context(
            proxy=None,
            user_agent=settings.user_agents[0] if settings.user_agents else None,
            profile_name=account.get('username', account.get('email'))
        )
        page = await browser_mgr.new_page(context=context)
        
        # Get faucet bot class
        BotClass = get_faucet_class(faucet_name)
        if not BotClass:
            print(f"❌ Unknown faucet: {faucet_name}")
            return False
        
        # Create bot instance
        bot = BotClass(settings, page)
        bot.settings_account_override = account
        
        # Test login
        print("🔐 Testing login...")
        try:
            login_result = await bot.login()
            
            if not login_result:
                print("❌ Login failed")
                print(f"   Current URL: {page.url}")
                await page.screenshot(path=f"logs/{faucet_name}_login_failed.png")
                print(f"   Screenshot: logs/{faucet_name}_login_failed.png")
                return False
            
            print("✅ Login successful!\n")
        except Exception as login_error:
            print(f"❌ Login threw exception: {login_error}")
            import traceback
            traceback.print_exc()
            await page.screenshot(path=f"logs/{faucet_name}_login_error.png")
            return False
        
        # Get balance
        print("💰 Getting balance...")
        try:
            balance = await bot.get_balance()
            print(f"   Balance: {balance}\n")
        except Exception as e:
            print(f"   ⚠️  Balance check failed: {e}\n")
            balance = "Unknown"
        
        # Get timer
        print("⏰ Getting timer...")
        try:
            timer = await bot.get_timer()
            print(f"   Timer: {timer}s\n")
        except Exception as e:
            print(f"   ⚠️  Timer check failed: {e}\n")
            timer = -1
        
        # Attempt claim if ready
        if timer > 0:
            print(f"⏳ Claim not ready - need to wait {timer}s")
            print(f"\n{'='*80}")
            print("✅ TEST PASSED: Login successful, timer active")
            print(f"{'='*80}\n")
            return True
        
        print("🎯 Attempting claim...")
        try:
            result = await bot.claim()
            
            print(f"\n📊 Claim Result:")
            print(f"   Success: {result.success}")
            print(f"   Status: {result.status}")
            print(f"   Amount: {result.amount}")
            print(f"   Balance: {result.balance}")
            print(f"   Next claim: {result.next_claim_minutes} minutes")
            
            if result.success:
                print(f"\n{'='*80}")
                print("✅ TEST PASSED: Claim successful!")
                print(f"{'='*80}\n")
                return True
            else:
                print(f"\n{'='*80}")
                print(f"⚠️  TEST PARTIAL: Login OK, claim failed: {result.status}")
                print(f"{'='*80}\n")
                await page.screenshot(path=f"logs/{faucet_name}_claim_failed.png")
                print(f"   Screenshot: logs/{faucet_name}_claim_failed.png")
                return False
                
        except Exception as claim_error:
            print(f"\n❌ Claim threw exception: {claim_error}")
            import traceback
            traceback.print_exc()
            await page.screenshot(path=f"logs/{faucet_name}_claim_error.png")
            return False
        
    except Exception as e:
        print(f"\n❌ Test error: {e}")
        import traceback
        traceback.print_exc()
        return False
    finally:
        print("\n🧹 Cleaning up...")
        await browser_mgr.cleanup()


async def main():
    if len(sys.argv) < 2:
        print("Usage: python test_simple_claim.py <faucet_name>")
        print("\nAvailable faucets:")
        print("  firefaucet, cointiply, freebitcoin, dutchy, faucetcrypto,")
        print("  litepick, tronpick, dogepick, bchpick, solpick, tonpick,")
        print("  polygonpick, binpick, dashpick, ethpick, usdpick, etc.")
        sys.exit(1)
    
    faucet_name = sys.argv[1].lower()
    success = await test_faucet(faucet_name)
    
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    asyncio.run(main())
