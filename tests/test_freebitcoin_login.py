"""
Test FreeBitcoin login with the fixed code.
"""
import asyncio
import sys
import os
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from core.config import BotSettings
from faucets.freebitcoin import FreeBitcoinBot
from browser.instance import BrowserManager


async def main():
    print("\n" + "="*80)
    print("🪙 FREEBITCOIN LOGIN TEST")
    print("="*80)
    
    settings = BotSettings()
    headless = os.getenv('HEADLESS', 'false').lower() == 'true'
    account = settings.get_account('freebitcoin')
    
    if not account:
        print("❌ No FreeBitcoin account found in config")
        return
    
    print(f"\n📧 Account: {account.get('username') or account.get('email')}")
    print(f"🖥️  Headless: {headless}\n")
    
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
        
        import random
        ua = random.choice(settings.user_agents) if settings.user_agents else None
        context = await browser_mgr.create_context(
            proxy=None,
            user_agent=ua,
            profile_name=account.get('username', 'freebitcoin_test')
        )
        page = await browser_mgr.new_page(context=context)
        
        bot = FreeBitcoinBot(settings, page)
        
        # Set account credentials
        override = {
            "username": account.get('username') or account.get('email'),
            "password": account['password']
        }
        bot.settings_account_override = override
        
        print("\n🔐 Testing login...")
        try:
            login_result = await asyncio.wait_for(bot.login(), timeout=120)
            
            if not login_result:
                print("❌ Login failed - returned False")
                print(f"Current URL: {page.url}")
                
                # Take screenshot
                try:
                    await page.screenshot(path="logs/freebitcoin_login_failed.png", full_page=True)
                    print("📸 Screenshot saved: logs/freebitcoin_login_failed.png")
                except Exception:
                    pass
                return
            
            print("✅ Login successful!")
            
            # Check if actually logged in
            if await bot.is_logged_in():
                print("✅ Confirmed logged in via is_logged_in() check")
            else:
                print("⚠️  Login returned True but is_logged_in() returned False")
            
            # Try to get balance
            print("\n💰 Getting balance...")
            balance = await bot.get_balance()
            print(f"Balance: {balance} BTC")
            
            # Try to get timer
            print("\n⏰ Getting claim timer...")
            timer = await bot.get_timer()
            print(f"Next claim in: {timer:.2f} minutes")
            
        except asyncio.TimeoutError:
            print("❌ Login timeout (120s)")
        except Exception as login_error:
            print(f"❌ Login error: {login_error}")
            import traceback
            traceback.print_exc()
        
        print("\n" + "="*80)
        print("✅ Test complete")
        print("="*80)
        
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
    finally:
        try:
            await browser_mgr.close()
        except Exception as e:
            print(f"Cleanup error: {e}")


if __name__ == "__main__":
    asyncio.run(main())
