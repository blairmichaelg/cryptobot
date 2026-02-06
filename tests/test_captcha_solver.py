"""
Test 2Captcha solver directly to verify it's working
"""
import asyncio
import logging
from solvers.captcha import CaptchaSolver
from core.config import BotSettings

# Setup logging to see what's happening
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s'
)

async def test_recaptcha_solver():
    """Test reCAPTCHA solving capability"""
    print("\n" + "="*60)
    print("TESTING 2CAPTCHA RECAPTCHA SOLVER")
    print("="*60)
    
    settings = BotSettings()
    print(f"\n[OK] API Key loaded: {settings.twocaptcha_api_key[:10]}...")
    print(f"[OK] Proxy Provider: {settings.proxy_provider}")
    
    solver = CaptchaSolver(settings)
    print("\n[OK] Solver initialized")
    
    # Test with FireFaucet's reCAPTCHA
    test_url = "https://firefaucet.win/login"
    test_sitekey = "6LfVIQ4UAAAAAG5vQLEf2E6PpIIv3XQ_BW-BU9NZ"  # FireFaucet's actual sitekey
    
    print(f"\nTest Parameters:")
    print(f"  URL: {test_url}")
    print(f"  Sitekey: {test_sitekey}")
    
    try:
        print(f"\n[WAIT] Submitting reCAPTCHA to 2Captcha...")
        print(f"       This may take 30-60 seconds...")
        
        token = await solver.solve_recaptcha(
            url=test_url,
            sitekey=test_sitekey
        )
        
        if token:
            print(f"\n[SUCCESS] Received token:")
            print(f"          {token[:50]}...{token[-20:]}")
            print(f"          Token length: {len(token)} chars")
            return True
        else:
            print(f"\n[FAIL] No token received")
            return False
            
    except Exception as e:
        print(f"\n[ERROR] {e}")
        logging.exception("Full error details:")
        return False

async def test_turnstile_solver():
    """Test Cloudflare Turnstile solving capability"""
    print("\n" + "="*60)
    print("TESTING 2CAPTCHA TURNSTILE SOLVER")
    print("="*60)
    
    settings = BotSettings()
    solver = CaptchaSolver(settings)
    
    # Test with a known Turnstile implementation
    test_url = "https://2captcha.com/demo/cloudflare-turnstile"
    test_sitekey = "0x4AAAAAAADnPIDROzbs0Aaj"  # Demo sitekey
    
    print(f"\nTest Parameters:")
    print(f"  URL: {test_url}")
    print(f"  Sitekey: {test_sitekey}")
    
    try:
        print(f"\n[WAIT] Submitting Turnstile to 2Captcha...")
        print(f"       This may take 30-60 seconds...")
        
        token = await solver.solve_turnstile(
            url=test_url,
            sitekey=test_sitekey
        )
        
        if token:
            print(f"\n[SUCCESS] Received token:")
            print(f"          {token[:50]}...{token[-20:]}")
            print(f"          Token length: {len(token)} chars")
            return True
        else:
            print(f"\n[FAIL] No token received")
            return False
            
    except Exception as e:
        print(f"\n[ERROR] {e}")
        logging.exception("Full error details:")
        return False

async def main():
    print("\n" + "="*60)
    print("2CAPTCHA SOLVER DIAGNOSTIC TEST")
    print("="*60)
    print("\nThis will verify your 2Captcha integration is working")
    print("by submitting test CAPTCHAs and checking the responses.\n")
    
    results = []
    
    # Test reCAPTCHA
    result1 = await test_recaptcha_solver()
    results.append(("reCAPTCHA", result1))
    
    # Wait between tests
    print("\n[PAUSE] Waiting 5 seconds before next test...")
    await asyncio.sleep(5)
    
    # Test Turnstile
    result2 = await test_turnstile_solver()
    results.append(("Turnstile", result2))
    
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
        print("\n[SUCCESS] All tests passed! 2Captcha solver is working correctly.")
        print("          The issue with faucets is NOT the solver.")
    elif total_passed > 0:
        print(f"\n[WARNING] Partial success - some solvers working.")
    else:
        print(f"\n[FAIL] All tests failed - 2Captcha integration has issues.")
    
    print("\n" + "="*60)

if __name__ == "__main__":
    asyncio.run(main())
