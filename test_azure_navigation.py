#!/usr/bin/env python3
"""
Minimal test to debug navigation timeouts on Azure VM.
Tests direct connection vs proxy connection.
"""
import asyncio
import time
import sys
import os

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

async def test_navigation():
    """Test basic browser navigation with and without proxy."""
    from camoufox.async_api import AsyncCamoufox
    from browserforge.fingerprints import Screen
    
    test_urls = [
        "https://httpbin.org/ip",
        "https://firefaucet.win",
        "https://cointiply.com",
    ]
    
    # Common browser options - matching main app config
    browser_opts = {
        "headless": True,
        "geoip": False,  # Skip geoip to avoid DB issues
        "humanize": True,
        "screen": Screen(max_width=1920, max_height=1080),
        "i_know_what_im_doing": True,  # Suppress warnings
    }
    
    # Test 1: Direct connection (no proxy)
    print("\n" + "="*60)
    print("TEST 1: Direct connection (no proxy)")
    print("="*60)
    
    try:
        async with AsyncCamoufox(**browser_opts) as browser:
            context = await browser.new_context()
            page = await context.new_page()
            
            for url in test_urls:
                start = time.time()
                try:
                    await page.goto(url, timeout=30000, wait_until="domcontentloaded")
                    elapsed = time.time() - start
                    title = await page.title()
                    print(f"  ✓ {url} - {elapsed:.2f}s - Title: {title[:50]}")
                except Exception as e:
                    elapsed = time.time() - start
                    print(f"  ✗ {url} - {elapsed:.2f}s - Error: {str(e)[:80]}")
            
            await context.close()
    except Exception as e:
        print(f"  ✗ Browser launch failed: {e}")
    
    # Test 2: With proxy
    print("\n" + "="*60)
    print("TEST 2: With proxy")
    print("="*60)
    
    proxy_url = "http://ub033d0d0583c05dd-zone-custom-session-test123:ub033d0d0583c05dd@43.135.141.142:2334"
    
    try:
        async with AsyncCamoufox(**browser_opts) as browser:
            context = await browser.new_context(
                proxy={"server": proxy_url}
            )
            page = await context.new_page()
            
            for url in test_urls:
                start = time.time()
                try:
                    await page.goto(url, timeout=30000, wait_until="domcontentloaded")
                    elapsed = time.time() - start
                    title = await page.title()
                    print(f"  ✓ {url} - {elapsed:.2f}s - Title: {title[:50]}")
                except Exception as e:
                    elapsed = time.time() - start
                    print(f"  ✗ {url} - {elapsed:.2f}s - Error: {str(e)[:80]}")
            
            await context.close()
    except Exception as e:
        print(f"  ✗ Browser launch failed: {e}")
    
    print("\n" + "="*60)
    print("Test complete!")
    print("="*60)

if __name__ == "__main__":
    asyncio.run(test_navigation())
