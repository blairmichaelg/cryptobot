"""
Quick test of representative faucets to identify failure patterns.
"""
import asyncio
import logging
import os
import sys
from pathlib import Path
from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).parent))

from core.config import BotSettings
from browser.instance import BrowserManager
from core.registry import get_faucet_class

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

load_dotenv()

async def quick_test(faucet_name: str):
    """Quick test of login and basic functionality."""
    settings = BotSettings()
    headless = os.getenv('HEADLESS', 'false').lower() == 'true'
    
    browser_mgr = BrowserManager(
        headless=headless,
        block_images=settings.block_images,
        block_media=settings.block_media,
        timeout=settings.timeout,
        user_agents=settings.user_agents
    )
    
    try:
        await browser_mgr.launch()
        
        import random
        ua = random.choice(settings.user_agents) if settings.user_agents else None
        context = await browser_mgr.create_context(
            proxy=None,
            user_agent=ua,
            profile_name=f"{faucet_name}_quick"
        )
        page = await browser_mgr.new_page(context=context)
        
        faucet_class = get_faucet_class(faucet_name)
        if not faucet_class:
            print(f"❌ {faucet_name}: Class not found")
            return False
        
        bot = faucet_class(settings, page)
        
        print(f"\n{'='*60}")
        print(f"Testing: {faucet_name}")
        print(f"{'='*60}")
        
        # Test login
        try:
            login_ok = await bot.login()
            if not login_ok:
                print(f"❌ {faucet_name}: Login failed")
                print(f"   URL: {page.url}")
                return False
            print(f"✅ {faucet_name}: Login successful")
        except Exception as e:
            print(f"❌ {faucet_name}: Login exception - {str(e)[:100]}")
            return False
        
        # Test balance
        try:
            balance = await bot.get_balance()
            print(f"   Balance: {balance}")
        except Exception as e:
            print(f"   ⚠️  Balance error: {str(e)[:50]}")
        
        # Test timer
        try:
            timer = await bot.get_timer()
            print(f"   Timer: {timer:.1f} minutes")
        except Exception as e:
            print(f"   ⚠️  Timer error: {str(e)[:50]}")
        
        return True
        
    finally:
        await browser_mgr.cleanup()

async def main():
    """Test representative faucets from each category."""
    faucets_to_test = [
        # Standalone faucets
        "firefaucet",
        "freebitcoin",
        # Pick.io family samples
        "tronpick",      # Reference implementation
        "litepick",      # Should work (inherits pick_base)
        "dogepick",      # Check if working
    ]
    
    results = {}
    for faucet in faucets_to_test:
        try:
            success = await quick_test(faucet)
            results[faucet] = "PASS" if success else "FAIL"
        except Exception as e:
            results[faucet] = f"ERROR: {str(e)[:50]}"
        await asyncio.sleep(1)
    
    print("\n" + "="*60)
    print("QUICK TEST SUMMARY")
    print("="*60)
    for faucet, status in results.items():
        symbol = "✅" if status == "PASS" else "❌"
        print(f"{symbol} {faucet}: {status}")
    print("="*60)

if __name__ == "__main__":
    asyncio.run(main())
