#!/usr/bin/env python3
"""
Direct test of Pick.io login using Camoufox browser.
This bypasses the orchestrator and tests login directly.
"""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from camoufox.async_api import AsyncCamoufox
from core.config import BotSettings
from faucets.tronpick import TronPickBot

async def test_tronpick_direct():
    """Test TronPick login directly with Camoufox."""
    print("=" * 80)
    print("Direct TronPick Login Test with Camoufox")
    print("=" * 80)
    
    settings = BotSettings()
    
    # Check credentials
    creds = settings.get_account("tronpick")
    if not creds:
        print("ERROR: No credentials found for TronPick")
        print("   Make sure TRONPICK_USERNAME and TRONPICK_PASSWORD are set in .env")
        return False
    
    email = creds.get("email") or creds.get("username")
    print(f"Credentials found: {email}")
    print(f"Base URL: https://tronpick.io")
    print()
    
    # Launch Camoufox
    print("Launching Camoufox browser...")
    async with AsyncCamoufox(headless=False) as browser:
        page = await browser.new_page()
        
        # Create bot instance
        bot = TronPickBot(settings, page)
        
        print(f"✓ Bot initialized: {bot.faucet_name}")
        print()
        
        # Attempt login
        print("→ Attempting login...")
        try:
            login_success = await bot.login()
            
            if login_success:
                print("LOGIN SUCCESS!")
                print()
                
                # Try to get balance
                print("Fetching balance...")
                try:
                    balance = await bot.get_balance()
                    print(f"Balance: {balance} TRX")
                except Exception as e:
                    print(f"⚠️  Could not fetch balance: {e}")
                
                # Try to get timer
                print("Checking timer...")
                try:
                    timer = await bot.get_timer()
                    print(f"Timer: {timer:.2f} minutes")
                except Exception as e:
                    print(f"⚠️  Could not fetch timer: {e}")
                
                return True
            else:
                print("LOGIN FAILED")
                
                # Check for error messages on page
                try:
                    content = await page.content()
                    if "cloudflare" in content.lower():
                        print("   Cloudflare protection detected")
                    if "maintenance" in content.lower():
                        print("   Site maintenance detected")
                    if "blocked" in content.lower():
                        print("   Access blocked")
                except:
                    pass
                
                return False
                
        except Exception as e:
            print(f"ERROR during login: {e}")
            import traceback
            traceback.print_exc()
            return False
        
        finally:
            # Keep browser open for manual inspection
            print()
            print("=" * 80)
            print("Press Enter to close browser...")
            input()

if __name__ == "__main__":
    success = asyncio.run(test_tronpick_direct())
    sys.exit(0 if success else 1)
