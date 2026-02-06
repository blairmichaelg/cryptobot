"""Test 2Captcha API key validity and balance."""
import os
import aiohttp
import asyncio
from dotenv import load_dotenv

load_dotenv()

async def check_2captcha():
    api_key = os.getenv("TWOCAPTCHA_API_KEY")
    
    if not api_key:
        print("❌ TWOCAPTCHA_API_KEY not found in .env")
        return False
    
    print(f"API Key found: {api_key[:10]}...")
    
    # Check balance
    balance_url = f"http://2captcha.com/res.php?key={api_key}&action=getbalance&json=1"
    
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(balance_url) as resp:
                data = await resp.json()
                print(f"\n2Captcha Response: {data}")
                
                if data.get("status") == 1:
                    balance = data.get("request", "0")
                    print(f"✅ API Key Valid!")
                    print(f"💰 Balance: ${balance}")
                    if float(balance) < 0.01:
                        print("⚠️  WARNING: Balance too low! Please add funds.")
                        print("   Visit: https://2captcha.com/enterpage")
                        return False
                    return True
                else:
                    error = data.get("request", "Unknown error")
                    print(f"❌ API Error: {error}")
                    if "ERROR_WRONG_USER_KEY" in error:
                        print("   The API key is invalid or incorrectly formatted")
                    elif "ERROR_KEY_DOES_NOT_EXIST" in error:
                        print("   The API key does not exist")
                    return False
    except Exception as e:
        print(f"❌ Connection Error: {e}")
        return False

if __name__ == "__main__":
    success = asyncio.run(check_2captcha())
    exit(0 if success else 1)
