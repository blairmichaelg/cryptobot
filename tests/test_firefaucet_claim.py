"""
Test FireFaucet claim flow end-to-end
"""
import asyncio
import sys
import random
import os
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent))

from core.config import BotSettings
from faucets.firefaucet import FireFaucetBot
from browser.instance import BrowserManager
from core.proxy_manager import ProxyManager


async def main():
    print("\n" + "="*80)
    print("🔥 FIREFAUCET CLAIM TEST")
    print("="*80)
    
    # Load config
    settings = BotSettings()
    headless = os.getenv('HEADLESS', 'false').lower() == 'true'
    account = settings.get_account('firefaucet')
    
    if not account:
        print("❌ No FireFaucet account found in config")
        return
    
    print(f"\n📧 Account: {account['username']}")
    print(f"🖥️  Headless: {headless}\n")
    
    # Initialize managers
    browser_mgr = BrowserManager(
        headless=headless,
        block_images=settings.block_images,
        block_media=settings.block_media,
        timeout=settings.timeout,
        user_agents=settings.user_agents
    )
    
    try:
        print("\n🌐 Launching browser...")
        await browser_mgr.launch()
        
        # Create context and page (similar to orchestrator)
        ua = random.choice(settings.user_agents) if settings.user_agents else None
        context = await browser_mgr.create_context(
            proxy=None,  # No proxy for testing
            user_agent=ua,
            profile_name=account['username']
        )
        page = await browser_mgr.new_page(context=context)
        
        # Create bot instance (like orchestrator does)
        bot = FireFaucetBot(settings, page)
        
        # Set account credentials
        override = {
            "username": account['username'],
            "password": account['password']
        }
        bot.settings_account_override = override
        
        print("\n🔐 Testing login...")
        try:
            login_result = await bot.login()
            
            if not login_result:
                print("❌ Login failed - returned False")
                # Try to get more details
                print("Checking page state...")
                print(f"Current URL: {page.url}")
                return
            
            print("✅ Login successful!")
        except Exception as login_error:
            print(f"❌ Login threw exception: {login_error}")
            import traceback
            traceback.print_exc()
            return
        
        print("\n💰 Getting balance...")
        balance_selectors = [".user-balance", ".balance", "#user-balance", "#balance"]
        balance = await bot.get_balance(balance_selectors[0], fallback_selectors=balance_selectors[1:])
        print(f"Balance: {balance}")
        
        print("\n⏰ Getting timer...")
        timer_selectors = [".fa-clock + span", "#claim_timer", "#time", ".timer"]
        timer = await bot.get_timer(timer_selectors[0], fallback_selectors=timer_selectors[1:])
        print(f"Timer: {timer}s")
        
        if timer > 0:
            print(f"⏳ Need to wait {timer}s before claiming")
            return
        
        print("\n🎯 Attempting claim...")
        result = await bot.claim()
        
        print(f"\n📊 Result: {result}")
        
        if result.success:
            print("✅ CLAIM SUCCESSFUL!")
            print(f"💎 Amount: {result.amount}")
            print(f"💵 Currency: {result.currency if hasattr(result, 'currency') else 'Unknown'}")
            print(f"📝 Status: {result.status}")
        else:
            print("❌ CLAIM FAILED")
            print(f"📝 Status: {result.status}")
            
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
    finally:
        print("\n🧹 Cleaning up...")
        try:
            await browser_mgr.close()
        except Exception:
            pass


if __name__ == "__main__":
    asyncio.run(main())
