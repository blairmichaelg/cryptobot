"""Test basic browser launch to identify timeout issue."""
import asyncio
import logging
from browser.instance import BrowserManager

logging.basicConfig(level=logging.DEBUG)

async def main():
    print("Creating BrowserManager (headless=False)...")
    mgr = BrowserManager(headless=False)
    
    try:
        print("Launching browser (30s timeout)...")
        await asyncio.wait_for(mgr.launch(), timeout=30)
        print("✓ Browser launched successfully!")
        
        await mgr.close()
        print("✓ Browser closed")
    except asyncio.TimeoutError:
        print("✗ TIMEOUT: Browser launch took > 30s")
    except Exception as e:
        print(f"✗ ERROR: {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(main())
