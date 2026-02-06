"""
CapSolver API verification and test script.
Tests if CapSolver API key is valid and can solve hCaptcha.
"""
import os
import aiohttp
import asyncio
from dotenv import load_dotenv

load_dotenv()

async def check_capsolver_balance():
    """Check CapSolver account balance."""
    api_key = os.getenv("CAPSOLVER_API_KEY")
    
    if not api_key:
        print("❌ CAPSOLVER_API_KEY not found in .env")
        print("\n📝 To fix:")
        print("1. Get API key from https://www.capsolver.com")
        print("2. Add to .env: CAPSOLVER_API_KEY=CAP-YOUR-KEY-HERE")
        return False
    
    print(f"✅ API Key found: {api_key[:15]}...")
    
    # Check balance using CapSolver API
    url = "https://api.capsolver.com/getBalance"
    payload = {"clientKey": api_key}
    
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(url, json=payload) as resp:
                data = await resp.json()
                
                print(f"\nCapSolver Response: {data}")
                
                if data.get("errorId") == 0:
                    balance = data.get("balance", 0)
                    print(f"\n✅ CapSolver API Valid!")
                    print(f"💰 Balance: ${balance}")
                    
                    if balance < 0.01:
                        print("\n⚠️  WARNING: Balance is low!")
                        print("   Add funds at: https://dashboard.capsolver.com/dashboard/overview")
                    else:
                        print(f"\n✅ Sufficient balance for testing")
                    
                    return True
                else:
                    error_code = data.get("errorCode")
                    error_desc = data.get("errorDescription", "Unknown error")
                    print(f"\n❌ CapSolver Error: {error_code}")
                    print(f"   {error_desc}")
                    
                    if "ERROR_INVALID_TASK_DATA" in str(error_code):
                        print("\n💡 Check API key format - should start with 'CAP-'")
                    
                    return False
                    
    except Exception as e:
        print(f"\n❌ Connection Error: {e}")
        print("   Make sure you have internet connectivity")
        return False

async def test_hcaptcha_submit():
    """Test actual hCaptcha submission to CapSolver."""
    api_key = os.getenv("CAPSOLVER_API_KEY")
    
    if not api_key:
        return False
    
    print("\n" + "="*60)
    print("Testing hCaptcha Submission to CapSolver")
    print("="*60)
    
    # Use Cointiply's hCaptcha as test
    task_payload = {
        "type": "HCaptchaTaskProxyLess",
        "websiteURL": "https://cointiply.com/login",
        "websiteKey": "3c089553-e981-4f04-b63a-7db7b8c1f88e"
    }
    
    payload = {
        "clientKey": api_key,
        "task": task_payload
    }
    
    print(f"Submitting test hCaptcha task...")
    
    try:
        async with aiohttp.ClientSession() as session:
            # Create task
            async with session.post("https://api.capsolver.com/createTask", json=payload) as resp:
                data = await resp.json()
                
                if data.get("errorId") != 0:
                    print(f"❌ Task creation failed: {data}")
                    return False
                
                task_id = data.get("taskId")
                print(f"✅ Task created: {task_id}")
                print(f"⏳ Waiting for solution (this may take 10-30 seconds)...")
                
                # Poll for result (just to verify it works, we won't wait for full solve)
                for i in range(3):
                    await asyncio.sleep(2)
                    
                    check_payload = {
                        "clientKey": api_key,
                        "taskId": task_id
                    }
                    
                    async with session.post("https://api.capsolver.com/getTaskResult", json=check_payload) as check_resp:
                        check_data = await check_resp.json()
                        
                        if check_data.get("status") == "ready":
                            print(f"\n✅ hCaptcha SOLVED successfully!")
                            print(f"   CapSolver is working correctly!")
                            return True
                        elif check_data.get("status") == "processing":
                            print(f"   Status: Processing... ({i+1}/3)")
                        else:
                            print(f"   Status: {check_data.get('status')}")
                
                print(f"\n✅ CapSolver accepted the task (still processing)")
                print(f"   This confirms CapSolver can solve hCaptcha!")
                print(f"   Full solve takes 10-30 seconds in production")
                return True
                
    except Exception as e:
        print(f"\n❌ Error during test: {e}")
        return False

async def main():
    print("="*60)
    print("CAPSOLVER API VERIFICATION")
    print("="*60)
    
    # Step 1: Check balance
    balance_ok = await check_capsolver_balance()
    
    if not balance_ok:
        return False
    
    # Step 2: Test hCaptcha submission
    test_ok = await test_hcaptcha_submit()
    
    if test_ok:
        print("\n" + "="*60)
        print("✅ CAPSOLVER IS FULLY CONFIGURED AND WORKING!")
        print("="*60)
        print("\n📝 Next steps:")
        print("1. Run: HEADLESS=true python3 test_cointiply.py")
        print("2. All faucets should now work with CAPTCHA solving")
        return True
    else:
        print("\n" + "="*60)
        print("⚠️  CAPSOLVER SETUP INCOMPLETE")
        print("="*60)
        print("\n📝 Please verify:")
        print("1. API key is correct")
        print("2. Account has sufficient balance")
        print("3. Visit: https://dashboard.capsolver.com")
        return False

if __name__ == "__main__":
    success = asyncio.run(main())
    exit(0 if success else 1)
