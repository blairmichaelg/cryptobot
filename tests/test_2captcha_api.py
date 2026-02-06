"""
Direct test of 2Captcha API to verify service is working
"""
import asyncio
import aiohttp
import time

API_KEY = "8861c78a551888d0d10a7f0624cee04c"
BASE_URL = "https://2captcha.com"

async def test_balance():
    """Test: Check account balance"""
    print("\n" + "="*60)
    print("TEST 1: Check Account Balance")
    print("="*60)
    
    async with aiohttp.ClientSession() as session:
        url = f"{BASE_URL}/res.php?key={API_KEY}&action=getbalance&json=1"
        
        try:
            async with session.get(url) as resp:
                data = await resp.json()
                
                if data.get("status") == 1:
                    balance = data.get("request")
                    print(f"\n[SUCCESS] Balance: ${balance}")
                    return True, float(balance)
                else:
                    print(f"\n[FAIL] Error: {data}")
                    return False, 0.0
        except Exception as e:
            print(f"\n[ERROR] {e}")
            return False, 0.0

async def submit_recaptcha(sitekey: str, url: str):
    """Submit reCAPTCHA to 2Captcha"""
    async with aiohttp.ClientSession() as session:
        submit_url = f"{BASE_URL}/in.php"
        params = {
            "key": API_KEY,
            "method": "userrecaptcha",
            "googlekey": sitekey,
            "pageurl": url,
            "json": 1
        }
        
        print(f"  Submitting to 2Captcha...")
        try:
            async with session.post(submit_url, data=params) as resp:
                data = await resp.json()
                
                if data.get("status") == 1:
                    captcha_id = data.get("request")
                    print(f"  CAPTCHA ID: {captcha_id}")
                    return captcha_id
                else:
                    error = data.get("request", "Unknown error")
                    print(f"  [FAIL] Submission error: {error}")
                    return None
        except Exception as e:
            print(f"  [ERROR] {e}")
            return None

async def get_result(captcha_id: str, max_attempts: int = 24):
    """Poll for CAPTCHA solution"""
    async with aiohttp.ClientSession() as session:
        result_url = f"{BASE_URL}/res.php"
        
        print(f"  Waiting for solution (max {max_attempts * 5}s)...")
        
        for attempt in range(max_attempts):
            await asyncio.sleep(5)
            
            params = {
                "key": API_KEY,
                "action": "get",
                "id": captcha_id,
                "json": 1
            }
            
            try:
                async with session.get(result_url, params=params) as resp:
                    data = await resp.json()
                    
                    if data.get("status") == 1:
                        token = data.get("request")
                        print(f"  [SUCCESS] Received token after {(attempt + 1) * 5}s")
                        return token
                    elif data.get("request") == "CAPCHA_NOT_READY":
                        print(f"    Attempt {attempt + 1}/{max_attempts}...")
                        continue
                    else:
                        error = data.get("request", "Unknown error")
                        print(f"  [FAIL] Error: {error}")
                        return None
            except Exception as e:
                print(f"  [ERROR] {e}")
                return None
        
        print(f"  [TIMEOUT] No solution after {max_attempts * 5}s")
        return None

async def test_recaptcha():
    """Test: Solve a real reCAPTCHA"""
    print("\n" + "="*60)
    print("TEST 2: Solve reCAPTCHA V2")
    print("="*60)
    
    # FireFaucet's reCAPTCHA parameters
    sitekey = "6LfVIQ4UAAAAAG5vQLEf2E6PpIIv3XQ_BW-BU9NZ"
    page_url = "https://firefaucet.win/login"
    
    print(f"\nParameters:")
    print(f"  Sitekey: {sitekey}")
    print(f"  Page URL: {page_url}")
    
    # Submit
    captcha_id = await submit_recaptcha(sitekey, page_url)
    if not captcha_id:
        return False
    
    # Get result
    token = await get_result(captcha_id)
    if token:
        print(f"\n[SUCCESS] Token received:")
        print(f"          Length: {len(token)} chars")
        print(f"          Sample: {token[:50]}...{token[-20:]}")
        return True
    else:
        return False

async def test_turnstile():
    """Test: Solve Cloudflare Turnstile"""
    print("\n" + "="*60)
    print("TEST 3: Solve Cloudflare Turnstile")
    print("="*60)
    
    # Demo Turnstile parameters
    sitekey = "0x4AAAAAAADnPIDROzbs0Aaj"
    page_url = "https://2captcha.com/demo/cloudflare-turnstile"
    
    print(f"\nParameters:")
    print(f"  Sitekey: {sitekey}")
    print(f"  Page URL: {page_url}")
    
    async with aiohttp.ClientSession() as session:
        # Submit
        submit_url = f"{BASE_URL}/in.php"
        params = {
            "key": API_KEY,
            "method": "turnstile",
            "sitekey": sitekey,
            "pageurl": page_url,
            "json": 1
        }
        
        print(f"  Submitting to 2Captcha...")
        try:
            async with session.post(submit_url, data=params) as resp:
                data = await resp.json()
                
                if data.get("status") == 1:
                    captcha_id = data.get("request")
                    print(f"  CAPTCHA ID: {captcha_id}")
                else:
                    error = data.get("request", "Unknown error")
                    print(f"  [FAIL] Submission error: {error}")
                    return False
        except Exception as e:
            print(f"  [ERROR] {e}")
            return False
    
    # Get result
    token = await get_result(captcha_id)
    if token:
        print(f"\n[SUCCESS] Token received:")
        print(f"          Length: {len(token)} chars")
        print(f"          Sample: {token[:50]}...")
        return True
    else:
        return False

async def main():
    print("\n" + "="*60)
    print("2CAPTCHA API DIRECT TEST")
    print("="*60)
    print("\nThis tests 2Captcha service directly via HTTP API")
    print("to verify your account and solver are working.\n")
    
    results = []
    
    # Test 1: Check balance
    success, balance = await test_balance()
    results.append(("Balance Check", success))
    
    if not success or balance < 0.01:
        print("\n[ABORT] Insufficient balance or API error")
        print("        Add funds at: https://2captcha.com/")
        return
    
    # Test 2: Solve reCAPTCHA
    print("\n[PAUSE] Waiting 3 seconds...")
    await asyncio.sleep(3)
    
    success = await test_recaptcha()
    results.append(("reCAPTCHA V2", success))
    
    # Test 3: Solve Turnstile
    print("\n[PAUSE] Waiting 3 seconds...")
    await asyncio.sleep(3)
    
    success = await test_turnstile()
    results.append(("Turnstile", success))
    
    # Summary
    print("\n" + "="*60)
    print("TEST SUMMARY")
    print("="*60)
    
    for test_name, success in results:
        status = "[PASS]" if success else "[FAIL]"
        print(f"{status}  {test_name}")
    
    total_passed = sum(1 for _, s in results if s)
    print(f"\nPassed: {total_passed}/{len(results)}")
    
    if total_passed == len(results):
        print("\n[SUCCESS] All tests passed!")
        print("          2Captcha is working correctly.")
        print("          Your faucet issues are NOT due to the solver.")
    elif total_passed > 0:
        print(f"\n[WARNING] Partial success ({total_passed}/{len(results)} passed)")
    else:
        print(f"\n[FAIL] All tests failed")
        print("       Check your API key and account status")
    
    print("\n" + "="*60)

if __name__ == "__main__":
    asyncio.run(main())
