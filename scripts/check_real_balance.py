#!/usr/bin/env python3
"""Check actual faucet balance from website to verify claims are real."""
import asyncio
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from faucets.freebitcoin import FreeBitcoin
from core.config import BotSettings

async def main():
    config = BotSettings()
    bot = FreeBitcoin(config)
    
    try:
        print("Logging in to FreeBitcoin...")
        # Get balance from actual website
        balance = await bot.get_balance()
        print(f"\n✅ ACTUAL BALANCE ON WEBSITE: {balance}")
        
        # Get timer
        timer = await bot.get_timer()
        print(f"⏰ Next claim available in: {timer} minutes")
        
    except Exception as e:
        print(f"❌ ERROR: {e}")
        import traceback
        traceback.print_exc()
    finally:
        await bot.browser_manager.close()

if __name__ == "__main__":
    asyncio.run(main())
