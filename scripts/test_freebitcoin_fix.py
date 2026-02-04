#!/usr/bin/env python3
"""
Test FreeBitcoin login with the CAPTCHA-before-login fix.
Run in visible mode to observe the fix working.
"""

import asyncio
import os
import sys
from pathlib import Path

os.environ['HEADLESS'] = 'false'

sys.path.insert(0, str(Path(__file__).parent.parent))

from core.config import BotSettings
from faucets.freebitcoin import FreeBitcoinBot

async def test_freebitcoin_login_fix():
    """Test FreeBitcoin login with CAPTCHA fix."""
    
    print("\n" + "="*70)
    print("FREEBITCOIN LOGIN FIX TEST")
    print("Testing: CAPTCHA-before-login fix")
    print("="*70)
    
    settings = BotSettings()
    
    profile = {
        'faucet': 'freebitcoin',
        'username': settings.freebitcoin_username,
        'password': settings.freebitcoin_password,
        'proxy': None,
        'residential_proxy': False,
        'enabled': True
    }
    
    if not profile['username'] or not profile['password']:
        print("❌ No FreeBitcoin credentials configured")
        return
    
    print(f"\nCredentials: {profile['username']} / {'*' * len(profile['password'])}")
    print("\n" + "="*70)
    print("EXPECTED FLOW:")
    print("1. Navigate to FreeBitcoin (redirects to /signup/?op=s)")
    print("2. SOLVE LANDING PAGE CAPTCHA (NEW FIX)")
    print("3. Find and fill login form")
    print("4. Solve login form CAPTCHA if present")
    print("5. Submit and verify login")
    print("="*70)
    
    # Import browser manager
    from browser.instance import BrowserManager
    
    browser_mgr = BrowserManager(settings)
    
    try:
        # Create browser context
        print("\n[1/5] Launching browser...")
        context, page = await browser_mgr.get_or_create_context(profile)
        print("✅ Browser launched")
        
        # Create bot instance
        print("\n[2/5] Creating FreeBitcoin bot...")
        bot = FreeBitcoinBot(settings, page)
        print("✅ Bot created")
        
        # Test login
        print("\n[3/5] Testing login (watch browser for CAPTCHA solving)...")
        print("⏱️  This may take 30-60 seconds for CAPTCHA solving...")
        
        login_success = await bot.login()
        
        if login_success:
            print("\n✅ LOGIN SUCCESS!")
            print(f"Current URL: {page.url}")
            
            # Test balance extraction
            print("\n[4/5] Testing balance extraction...")
            try:
                balance = await bot.get_balance()
                if balance is not None:
                    print(f"✅ Balance: {balance}")
                else:
                    print("⚠️  Balance: Could not extract")
            except Exception as e:
                print(f"❌ Balance error: {e}")
            
            # Test timer extraction
            print("\n[5/5] Testing timer extraction...")
            try:
                timer = await bot.get_timer()
                if timer is not None:
                    hours = timer // 3600
                    minutes = (timer % 3600) // 60
                    print(f"✅ Timer: {timer}s ({hours}h {minutes}m)")
                else:
                    print("⚠️  Timer: Could not extract")
            except Exception as e:
                print(f"❌ Timer error: {e}")
            
            print("\n" + "="*70)
            print("SUCCESS - FreeBitcoin fix is working!")
            print("="*70)
            
        else:
            print("\n❌ LOGIN FAILED")
            print(f"Current URL: {page.url}")
            print("\nCheck browser window for details")
        
        print("\n⏸️  Browser kept open for 30 seconds - inspect the result")
        await asyncio.sleep(30)
        
    finally:
        try:
            await browser_mgr.close_all()
        except:
            pass


if __name__ == "__main__":
    asyncio.run(test_freebitcoin_login_fix())
