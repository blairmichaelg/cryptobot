#!/usr/bin/env python3
"""Direct test of TronPick login functionality"""
import asyncio
import sys
from pathlib import Path

# Add parent to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from camoufox.async_api import AsyncCamoufox
from core.config import BotSettings
from faucets.tronpick import TronPickBot

async def test_tronpick_login():
    """Test TronPick login directly"""
    settings = BotSettings()
    
    print("\n" + "="*60)
    print("TronPick Login Test")
    print("="*60)
    
    # Check credentials
    username = getattr(settings, "TRONPICK_USERNAME", None)
    password = getattr(settings, "TRONPICK_PASSWORD", None)
    
    print(f"\nCredentials check:")
    print(f"  Username: {username[:20] if username else 'NOT SET'}...")
    print(f"  Password: {'*' * len(password) if password else 'NOT SET'}")
    
    if not username or not password:
        print("\n❌ ERROR: TRONPICK credentials not set in .env")
        return False
    
    # Create Camoufox browser
    print("\n→ Launching Camoufox browser...")
    async with AsyncCamoufox(headless=False) as browser:
        page = await browser.new_page()
        
        # Create bot instance
        bot = TronPickBot(settings, page)
        
        print(f"→ Testing login to {bot.base_url}")
        
        # Attempt login
        print("→ Calling bot.login()...")
        login_success = await bot.login()
        
        if login_success:
            print("\n✅ LOGIN SUCCESSFUL!")
            
            # Try to get balance
            print("\n→ Testing get_balance()...")
            balance = await bot.get_balance()
            print(f"  Balance: {balance}")
            
            # Try to get timer
            print("\n→ Testing get_timer()...")
            timer = await bot.get_timer()
            print(f"  Next claim: {timer} seconds")
            
        else:
            print("\n❌ LOGIN FAILED")
            
        print("\n→ Press Enter to close browser and exit...")
        input()
        
        return login_success

if __name__ == "__main__":
    success = asyncio.run(test_tronpick_login())
    sys.exit(0 if success else 1)
