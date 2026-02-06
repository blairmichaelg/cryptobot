"""Simple direct test of CAPTCHA solving with User-Agent"""
import asyncio
import os
from pathlib import Path
from dotenv import load_dotenv

# Direct imports
import sys
sys.path.insert(0, str(Path(__file__).parent))

async def main():
    from solvers.captcha import CaptchaSolver
    from camoufox.async_api import AsyncCamoufox
    
    # Load environment
    env_path = Path(__file__).parent / ".env"
    load_dotenv(env_path)
    
    api_key = os.getenv("TWOCAPTCHA_API_KEY")
    
    print("=" * 80)
    print("🧪 DIRECT CAPTCHA SOLVE TEST WITH USER-AGENT")
    print("=" * 80)
    print()
    
    # Initialize solver
    solver = CaptchaSolver(api_key=api_key, provider="2captcha")
    
    # Set proxy
    proxy_file = Path(__file__).parent / "config" / "digitalocean_proxies.txt"
    if proxy_file.exists():
        proxies = proxy_file.read_text().strip().split('\n')
        proxy = proxies[0].strip() if proxies else None
        if proxy:
            print(f"🔒 Using proxy: {proxy.split(':')[:2]}")
            solver.set_proxy(proxy)
    
    # Launch browser
    print("\n🌐 Launching Camoufox browser...")
    async with AsyncCamoufox(headless=False, humanize=True) as browser:
        context = await browser.new_context()
        page = await context.new_page()
        
        # Navigate to FireFaucet login
        print("🔥 Loading FireFaucet login page...")
        await page.goto("https://firefaucet.win/login", wait_until="networkidle", timeout=30000)
        
        # Wait a moment for page to settle
        await asyncio.sleep(2)
        
        # Check for CAPTCHA
        print("\n🔍 Looking for CAPTCHA...")
        
        # Try to solve CAPTCHA
        print("🧩 Attempting to solve CAPTCHA with User-Agent...")
        print("   (This should now extract User-Agent and send to 2Captcha)")
        print()
        
        token = await solver.solve_captcha(page, timeout=180)
        
        print("\n" + "=" * 80)
        if token:
            print("✅ SUCCESS! CAPTCHA SOLVED!")
            print(f"🎯 Token received: {token[:60]}...")
            print("=" * 80)
            print()
            print("🎉 User-Agent fix is WORKING!")
            print("   The CAPTCHA solver now properly sends browser fingerprint to 2Captcha")
        else:
            print("❌ CAPTCHA solving failed")
            print("   Check logs above for details")
            print("=" * 80)
        
        # Keep browser open briefly
        if token:
            print("\n⏸️  Browser will stay open for 10 seconds...")
            await asyncio.sleep(10)
        else:
            print("\n⏸️  Browser will stay open for 30 seconds for debugging...")
            await asyncio.sleep(30)
    
    await solver.close()
    print("\n✨ Test complete")

if __name__ == "__main__":
    asyncio.run(main())
