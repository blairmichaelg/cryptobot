"""End-to-end test: Verify CAPTCHA solving with User-Agent fix"""
import asyncio
import os
import sys
from pathlib import Path
from dotenv import load_dotenv

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent))

from core.config import BotSettings
from faucets.firefaucet import FireFaucetBot
from browser.instance import BrowserManager

async def main():
    # Load environment
    env_path = Path(__file__).parent / ".env"
    load_dotenv(env_path)
    
    print("=" * 80)
    print("🧪 END-TO-END CAPTCHA TEST WITH USER-AGENT FIX")
    print("=" * 80)
    
    # Initialize settings
    settings = BotSettings()
    settings.headless = False  # Run visible to see what happens
    
    # Get credentials
    username = os.getenv("FIREFAUCET_USERNAME")
    password = os.getenv("FIREFAUCET_PASSWORD")
    
    if not username or not password:
        print("❌ Missing FIREFAUCET_USERNAME or FIREFAUCET_PASSWORD in .env")
        return
    
    print(f"📧 Testing with account: {username}")
    print(f"🔑 2Captcha API Key: {settings.twocaptcha_api_key[:20]}...")
    print()
    
    # Initialize browser manager
    browser_mgr = BrowserManager()
    
    try:
        # Get proxy (use first available)
        proxy_file = Path(__file__).parent / "config" / "digitalocean_proxies.txt"
        if proxy_file.exists():
            proxies = proxy_file.read_text().strip().split('\n')
            proxy = proxies[0].strip() if proxies else None
            if proxy:
                print(f"🔒 Using proxy: {proxy.split(':')[:2]}")
        else:
            proxy = None
            print("⚠️ No proxy configured - using direct connection")
        
        # Create browser context
        print("\n🌐 Launching browser...")
        context = await browser_mgr.new_context(
            account_name="test_firefaucet",
            proxy=proxy
        )
        
        page = await browser_mgr.new_page(context)
        
        # Create faucet bot
        print("🔥 Initializing FireFaucet bot...")
        faucet = FireFaucetBot(settings, page)
        
        # Override credentials
        faucet.settings_account_override = {
            "username": username,
            "password": password
        }
        
        # Attempt login (this will test CAPTCHA solving)
        print("\n" + "=" * 80)
        print("🔐 ATTEMPTING LOGIN (will test User-Agent in CAPTCHA solving)")
        print("=" * 80)
        print()
        
        success = await faucet.login()
        
        print("\n" + "=" * 80)
        if success:
            print("✅ LOGIN SUCCESS!")
            print("🎯 User-Agent fix is WORKING - CAPTCHA was solved!")
            print("=" * 80)
            
            # Try to get balance
            print("\n💰 Checking balance...")
            balance = await faucet.get_balance()
            print(f"Balance: {balance}")
            
            # Try to get timer
            print("\n⏰ Checking claim timer...")
            timer = await faucet.get_timer()
            print(f"Next claim in: {timer} minutes")
            
        else:
            print("❌ LOGIN FAILED")
            print("🔍 Check logs above for details")
            print("=" * 80)
        
        # Keep browser open for inspection
        if not success:
            print("\n⏸️  Browser will stay open for 30 seconds for inspection...")
            await asyncio.sleep(30)
        
    except Exception as e:
        print(f"\n❌ Test failed with exception: {e}")
        import traceback
        traceback.print_exc()
        
    finally:
        print("\n🧹 Cleaning up...")
        await browser_mgr.cleanup()

if __name__ == "__main__":
    asyncio.run(main())
