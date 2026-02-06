"""Direct test of 2Captcha hCaptcha submission."""
import os
import aiohttp
import asyncio
from dotenv import load_dotenv

load_dotenv()

async def test_hcaptcha_submit():
    api_key = os.getenv("TWOCAPTCHA_API_KEY")
    
    # Test with known hCaptcha site (Cointiply's sitekey from the logs)
    sitekey = "3c089553-e981-4f04-b63a-7db7b8c1f88e"
    url = "https://cointiply.com/login"
    
    params = {
        "key": api_key,
        "method": "hcaptcha",
        "sitekey": sitekey,
        "pageurl": url,
        "json": 1
    }
    
    print(f"Submitting hCaptcha request...")
    print(f"  Sitekey: {sitekey}")
    print(f"  URL: {url}")
    print(f"  Method: hcaptcha")
    
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post("http://2captcha.com/in.php", data=params) as resp:
                text = await resp.text()
                print(f"\nRaw Response: {text}")
                
                try:
                    data = await resp.json()
                    print(f"JSON Response: {data}")
                    
                    if data.get("status") == 1:
                        print(f"✅ Request accepted!")
                        print(f"📝 Request ID: {data.get('request')}")
                        return True
                    else:
                        error = data.get("request", "Unknown")
                        print(f"❌ Error: {error}")
                        
                        if error == "ERROR_METHOD_CALL":
                            print("\n💡 ERROR_METHOD_CALL means:")
                            print("   1. The 'method' parameter value is invalid")
                            print("   2. Required parameters are missing")
                            print("   3. The method is not supported for this account")
                        
                        return False
                except Exception as e:
                    print(f"Could not parse as JSON: {e}")
                    return False
    except Exception as e:
        print(f"❌ Connection Error: {e}")
        return False

if __name__ == "__main__":
    success = asyncio.run(test_hcaptcha_submit())
    exit(0 if success else 1)
