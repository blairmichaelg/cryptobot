"""Direct test of FireFaucet login with User-Agent fix"""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from core.config import BotSettings
from core.registry import get_faucet_class
from browser.instance import BrowserManager

async def main():
    print("=" * 80)
    print("🔥 FIREFAUCET LOGIN TEST WITH USER-AGENT FIX")
    print("=" * 80)
    print()
    
    # Load settings
    settings = BotSettings()
    settings.headless = False  # Visible mode
    
    # Get account
    account = settings.get_account("firefaucet")
    if not account:
        print("❌ No FireFaucet account configured in .env")
        return
    
    print(f"📧 Account: {account['username']}")
    print(f"🔑 2Captcha Key: {settings.twocaptcha_api_key[:20]}...")
    print()
    
    # Create browser manager
    browser_mgr = BrowserManager(headless=False)
    
    try:
        # Launch browser
        print("🌐 Launching browser...")
        await browser_mgr.launch()
        
        # Create a new page using the default browser context
        print("📄 Creating new page...")
        page = await browser_mgr.new_page()
        
        # Get bot class
        bot_class = get_faucet_class("firefaucet")
        if not bot_class:
            print("❌ FireFaucet bot class not found")
            return
        
        # Create bot instance
        print("🤖 Creating FireFaucet bot...")
        bot = bot_class(settings, page)
        bot.settings_account_override = account
        
        # Attempt login
        print("\n" + "=" * 80)
        print("🔐 ATTEMPTING LOGIN (will test User-Agent in CAPTCHA)")
        print("=" * 80)
        print()
        
        success = await bot.login()
        
        print("\n" + "=" * 80)
        if success:
            print("✅ LOGIN SUCCESSFUL!")
            print("🎯 User-Agent fix is WORKING!")
            print("=" * 80)
            
            # Try to get balance
            print("\n💰 Getting balance...")
            balance = await bot.get_balance()
            print(f"Balance: {balance}")
            
            # Try to get timer
            print("\n⏰ Getting claim timer...")
            timer = await bot.get_timer()
            print(f"Next claim: {timer} minutes")
            
            # If timer is 0, try to claim
            if timer == 0:
                print("\n🎰 Timer is 0 - attempting claim...")
                result = await bot.claim()
                print(f"Claim result: {result}")
                
                if result.success:
                    print("\n" + "=" * 80)
                    print("🎉 FULL CLAIM CYCLE SUCCESSFUL!")
                    print(f"Amount claimed: {result.amount}")
                    print(f"New balance: {result.balance}")
                    print(f"Next claim: {result.next_claim_minutes} minutes")
                    print("=" * 80)
            else:
                print(f"⏳ Must wait {timer} minutes before claiming")
                
        else:
            print("❌ LOGIN FAILED")
            print("Check logs above for details")
            print("=" * 80)
        
        # Keep browser open for inspection
        print("\n⏸️  Browser will stay open for 20 seconds...")
        await asyncio.sleep(20)
        
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
        
    finally:
        print("\n🧹 Cleaning up...")
        if browser_mgr.camoufox:
            await browser_mgr.close()

if __name__ == "__main__":
    asyncio.run(main())
