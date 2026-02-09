"""Test different 2Captcha hCaptcha submission methods.

This is a manual diagnostic script, not an automated test.
Run directly: python tests/test_2captcha_methods.py
"""
import os
import aiohttp
import asyncio
from dotenv import load_dotenv

load_dotenv()


async def _try_method(session, api_key, method_name, extra_params=None):
    """Test a specific method configuration."""
    sitekey = "3c089553-e981-4f04-b63a-7db7b8c1f88e"
    url = "https://cointiply.com/login"
    
    params = {
        "key": api_key,
        "method": method_name,
        "sitekey": sitekey,
        "pageurl": url,
        "json": 1
    }
    
    if extra_params:
        params.update(extra_params)
    
    print(f"\n{'='*60}")
    print(f"Testing method: {method_name}")
    if extra_params:
        print(f"Extra params: {extra_params}")
    print(f"{'='*60}")
    
    try:
        async with session.post("http://2captcha.com/in.php", data=params) as resp:
            text = await resp.text()
            print(f"Response: {text}")
            
            try:
                data = await resp.json()
                if data.get("status") == 1:
                    print(f"✅ SUCCESS! Request ID: {data.get('request')}")
                    return True
                else:
                    print(f"❌ Failed: {data.get('request')}")
            except:
                pass
    except Exception as e:
        print(f"❌ Exception: {e}")
    
    return False

async def main():
    api_key = os.getenv("TWOCAPTCHA_API_KEY")
    
    async with aiohttp.ClientSession() as session:
        # Try different method variations
        methods_to_try = [
            ("hcaptcha", None),
            ("hcaptcha", {"invisible": 0}),
            ("hcaptcha", {"invisible": 1}),
            ("userrecaptcha", None),  # Try if maybe it's mislabeled
        ]
        
        for method, extra in methods_to_try:
            success = await _try_method(session, api_key, method, extra)
            if success:
                print(f"\n\n🎉 WORKING METHOD FOUND: {method} with params {extra}")
                return True
            await asyncio.sleep(1)
        
        print("\n\n❌ No working method found")
        print("\n💡 Possible solutions:")
        print("   1. This 2Captcha account may not support hCaptcha")
        print("   2. Need to enable hCaptcha in 2Captcha dashboard")
        print("   3. Try a different CAPTCHA service (CapSolver, AntiCaptcha)")
        return False

if __name__ == "__main__":
    asyncio.run(main())
