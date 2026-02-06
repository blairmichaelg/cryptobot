"""
Minimal test to debug faucet issues with maximum error visibility.
"""
import asyncio
import sys
import traceback
import os
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

# Suppress fake_useragent warnings
import warnings
warnings.filterwarnings("ignore", module="fake_useragent")

async def test_firefaucet_minimal():
    """Minimal FireFaucet test with full error output."""
    print("=" * 60)
    print("MINIMAL FIREFAUCET TEST")
    print("=" * 60)
    
    from dotenv import load_dotenv
    load_dotenv()
    
    from core.config import BotSettings
    from core.registry import get_faucet_class
    from browser.instance import BrowserManager
    
    settings = BotSettings()
    settings.headless = False
    
    # Get credentials
    account = settings.get_account("firefaucet")
    if not account:
        print("ERROR: No firefaucet credentials")
        return
    
    print(f"Account: {account.get('username')}")
    
    browser_mgr = None
    page = None
    bot = None
    
    try:
        # Step 1: Launch browser
        print("\n[1] Launching browser...")
        browser_mgr = BrowserManager(headless=False, block_images=False)
        await browser_mgr.launch()
        print("    Browser launched OK")
        
        # Step 2: Create page
        print("\n[2] Creating page...")
        page = await browser_mgr.new_page()
        print(f"    Page created OK: {page}")
        
        # Step 3: Create bot
        print("\n[3] Creating bot...")
        bot_class = get_faucet_class("firefaucet")
        bot = bot_class(settings, page)
        bot.settings_account_override = account
        print(f"    Bot created OK: {bot}")
        
        # Step 4: Navigate to login
        print("\n[4] Navigating to login...")
        await page.goto("https://firefaucet.win/login", wait_until="domcontentloaded", timeout=30000)
        print(f"    Navigation OK, URL: {page.url}")
        
        # Step 5: Wait for form
        print("\n[5] Waiting for login form...")
        await page.wait_for_selector("#username", timeout=15000)
        print("    Form found OK")
        
        # Step 6: Type username
        print("\n[6] Typing username...")
        username_field = page.locator("#username")
        await username_field.click()
        await asyncio.sleep(0.5)
        await username_field.fill(account['username'])
        print(f"    Username typed OK")
        
        # Step 7: Type password
        print("\n[7] Typing password...")
        password_field = page.locator("#password")
        await password_field.click()
        await asyncio.sleep(0.5)
        await password_field.fill(account['password'])
        print("    Password typed OK")
        
        # Step 8: Handle captcha
        print("\n[8] Solving captcha...")
        try:
            captcha_result = await bot.solver.solve_captcha(page, timeout=120)
            print(f"    Captcha result: {captcha_result}")
        except Exception as e:
            print(f"    Captcha error: {e}")
            traceback.print_exc()
        
        # Step 9: Submit form
        print("\n[9] Submitting form...")
        submit_btn = page.locator('button.submitbtn, button[type="submit"]')
        if await submit_btn.count() > 0:
            await submit_btn.click()
            print("    Submit clicked OK")
        else:
            print("    No submit button found - trying form submit")
            await page.evaluate("document.forms[0]?.submit()")
        
        # Step 10: Wait for login result
        print("\n[10] Checking login result...")
        await asyncio.sleep(5)
        
        current_url = page.url
        print(f"    Current URL: {current_url}")
        
        if "/dashboard" in current_url:
            print("\n✅ LOGIN SUCCESS!")
            
            # Try to get balance
            print("\n[11] Getting balance...")
            try:
                balance = await bot.get_balance()
                print(f"    Balance: {balance}")
            except Exception as e:
                print(f"    Balance error: {e}")
            
            # Try to get timer
            print("\n[12] Getting timer...")
            try:
                timer = await bot.get_timer()
                print(f"    Timer: {timer} minutes")
                
                if timer == 0:
                    print("\n[13] Attempting claim...")
                    try:
                        result = await bot.claim()
                        print(f"    Claim result: {result}")
                        if result and result.success:
                            print(f"\n🎉 CLAIM SUCCESS! Amount: {result.amount}")
                    except Exception as e:
                        print(f"    Claim error: {e}")
                        traceback.print_exc()
            except Exception as e:
                print(f"    Timer error: {e}")
        else:
            print("\n❌ LOGIN FAILED - not on dashboard")
            
            # Check for error messages
            error = await page.locator('.alert-danger, .error-message').first.text_content() if await page.locator('.alert-danger, .error-message').count() > 0 else None
            if error:
                print(f"    Error message: {error}")
        
        print("\nKeeping browser open for 20 seconds...")
        await asyncio.sleep(20)
        
    except Exception as e:
        print(f"\n❌ EXCEPTION: {type(e).__name__}: {e}")
        traceback.print_exc()
        
        # Keep browser open on error
        print("\nKeeping browser open for 30 seconds after error...")
        await asyncio.sleep(30)
        
    finally:
        print("\n[CLEANUP] Closing browser...")
        if browser_mgr:
            try:
                await browser_mgr.close()
            except:
                pass
        print("Done.")


if __name__ == "__main__":
    asyncio.run(test_firefaucet_minimal())
