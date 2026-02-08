#!/usr/bin/env python3
"""
Quick test to verify a single faucet can claim successfully.
Tests with minimal configuration to isolate issues.
"""
import asyncio
import logging
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent))

from core.config import BotSettings
from browser.instance import BrowserManager
from core.registry import get_faucet_class

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(name)s - %(message)s'
)

async def test_faucet_claim(faucet_name: str):
    """Test a single faucet claim end-to-end."""
    settings = BotSettings()
    browser_mgr = BrowserManager(settings)
    
    try:
        # Get account for faucet
        account = settings.get_account(faucet_name)
        if not account:
            print(f"❌ No account configured for {faucet_name}")
            print(f"Available accounts: {[a.faucet for a in settings.accounts]}")
            return False
        
        print(f"\n{'='*60}")
        print(f"🧪 Testing {faucet_name} Claim")
        print(f"{'='*60}")
        print(f"Account: {account.username}")
        print(f"Timeout: {settings.timeout}ms")
        print(f"Headless: {settings.headless}")
        print()
        
        # Get browser context
        print("🌐 Creating browser context...")
        page = await browser_mgr.get_page(
            profile=account.username,
            proxy=None  # No proxy for initial test
        )
        
        # Initialize faucet
        faucet_class = get_faucet_class(faucet_name)
        if not faucet_class:
            print(f"❌ Unknown faucet: {faucet_name}")
            return False
        
        print(f"🤖 Initializing {faucet_name} bot...")
        bot = faucet_class(settings, page, account=account)
        
        # Test login
        print("\n📝 Testing login...")
        login_success = await bot.login()
        
        if not login_success:
            print("❌ Login failed")
            # Take screenshot for debugging
            await page.screenshot(path=f"debug_{faucet_name}_login_failed.png")
            print(f"Screenshot saved: debug_{faucet_name}_login_failed.png")
            return False
        
        print("✅ Login successful!")
        
        # Test balance check
        print("\n💰 Checking balance...")
        balance = await bot.get_balance()
        print(f"Balance: {balance}")
        
        # Test timer check
        print("\n⏰ Checking claim timer...")
        timer_minutes = await bot.get_timer()
        print(f"Next claim in: {timer_minutes} minutes")
        
        if timer_minutes > 0:
            print(f"⏳ Claim not available yet, waiting {timer_minutes} minutes")
            return True  # Login worked, timer check worked
        
        # Test claim
        print("\n🎯 Attempting claim...")
        result = await bot.claim()
        
        print(f"\n{'='*60}")
        print(f"📊 Claim Result")
        print(f"{'='*60}")
        print(f"Success: {result.success}")
        print(f"Status: {result.status}")
        print(f"Amount: {result.amount}")
        print(f"Balance: {result.balance}")
        print(f"Next claim: {result.next_claim_minutes} minutes")
        print(f"{'='*60}\n")
        
        if result.success:
            print("✅ CLAIM SUCCESSFUL!")
            return True
        else:
            print(f"❌ Claim failed: {result.status}")
            await page.screenshot(path=f"debug_{faucet_name}_claim_failed.png")
            print(f"Screenshot saved: debug_{faucet_name}_claim_failed.png")
            return False
            
    except Exception as e:
        print(f"\n❌ Test failed with exception: {e}")
        import traceback
        traceback.print_exc()
        return False
    finally:
        print("\n🧹 Cleaning up...")
        await browser_mgr.close()

async def main():
    if len(sys.argv) < 2:
        print("Usage: python test_single_claim.py <faucet_name>")
        print("Example: python test_single_claim.py cointiply")
        sys.exit(1)
    
    faucet_name = sys.argv[1].lower()
    success = await test_faucet_claim(faucet_name)
    sys.exit(0 if success else 1)

if __name__ == "__main__":
    asyncio.run(main())
