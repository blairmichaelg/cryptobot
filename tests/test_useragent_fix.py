"""Test that User-Agent is properly sent to 2Captcha API"""
import asyncio
import os
import aiohttp
from pathlib import Path
from dotenv import load_dotenv

async def main():
    # Load environment
    env_path = Path(__file__).parent / ".env"
    load_dotenv(env_path)
    
    api_key = os.getenv("TWOCAPTCHA_API_KEY")
    
    # Simulate what the fixed code does
    test_user_agent = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
    # Proxy format: user:pass@host:port (2Captcha format)
    proxy_string = "ifrttfdd:5qv5xepphv4s@89.116.241.109:14725"
    
    print("🧪 Testing 2Captcha API with User-Agent parameter...")
    print(f"📱 User-Agent: {test_user_agent}")
    print(f"🔒 Proxy: {proxy_string.split(':')[:2]}")
    
    async with aiohttp.ClientSession() as session:
        # Submit CAPTCHA with User-Agent (what our fix does)
        params = {
            "key": api_key,
            "method": "userrecaptcha",
            "googlekey": "6LfVIQ4UAAAAAG5vQLEf2E6PpIIv3XQ_BW-BU9NZ",
            "pageurl": "https://firefaucet.win/login",
            "proxy": proxy_string,
            "proxytype": "HTTP",
            "userAgent": test_user_agent,  # THIS IS THE FIX
            "json": 1
        }
        
        print("\n📤 Submitting to 2Captcha with userAgent parameter...")
        async with session.post("https://2captcha.com/in.php", data=params) as response:
            result = await response.json()
            print(f"Response: {result}")
            
            if result.get("status") == 1:
                captcha_id = result.get("request")
                print(f"✅ CAPTCHA submitted successfully! ID: {captcha_id}")
                print("🎯 User-Agent parameter was accepted by 2Captcha!")
                
                # Wait before polling
                print("\n⏳ Waiting 15 seconds before polling...")
                await asyncio.sleep(15)
                
                # Poll for result
                get_url = f"https://2captcha.com/res.php?key={api_key}&action=get&id={captcha_id}&json=1"
                async with session.get(get_url) as poll_response:
                    poll_result = await poll_response.json()
                    print(f"\n📥 Poll result: {poll_result}")
                    
                    if poll_result.get("status") == 1:
                        print(f"✅ SUCCESS! Token: {poll_result.get('request')[:50]}...")
                        print("🎯 CAPTCHA was solved WITH User-Agent!")
                    elif poll_result.get("request") == "CAPCHA_NOT_READY":
                        print("⏳ Still processing (would continue polling in real code)")
                    else:
                        print(f"❌ Error: {poll_result.get('request')}")
            else:
                print(f"❌ Submission failed: {result.get('request')}")

if __name__ == "__main__":
    asyncio.run(main())
