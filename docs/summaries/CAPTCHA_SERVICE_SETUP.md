# CAPTCHA Service Setup Guide

## Current Issue

**2Captcha does not support hCaptcha** for this account. Testing confirms:
- API Key: Valid ✅
- Balance: $3.82 ✅  
- hCaptcha Support: ❌ NOT ENABLED

## Solution: Use CapSolver

CapSolver fully supports hCaptcha, Turnstile, and reCAPTCHA.

### Setup Steps

1. **Create CapSolver Account**
   - Visit: https://www.capsolver.com/
   - Sign up for a free account
   - Get API key from dashboard

2. **Add to .env File**
   ```bash
   # Add this line to your .env file
   CAPSOLVER_API_KEY=CAP-YOUR-API-KEY-HERE
   ```

3. **Configure as Primary Provider** (Optional)
   ```bash
   # In .env, you can set provider order
   CAPTCHA_PROVIDER=capsolver  # Primary provider
   CAPTCHA_FALLBACK_PROVIDER=2captcha  # Fallback
   ```

4. **Verify Setup**
   ```bash
   cd ~/Repositories/cryptobot
   python3 check_capsolver.py  # Test script to verify
   ```

### Pricing Comparison

| Service | hCaptcha | Turnstile | reCAPTCHA v2 |
|---------|----------|-----------|--------------|
| **CapSolver** | $0.80/1K | $2.00/1K | $0.80/1K |
| **2Captcha** | Not Supported | $2.99/1K | $2.99/1K |

**Recommendation**: Use CapSolver for better pricing and hCaptcha support.

### Current Code Support

The codebase **already supports CapSolver**! Check `solvers/captcha.py`:
- Lines 960-1020: CapSolver integration
- Automatic fallback if primary fails
- Adaptive routing based on success rates

### Test CapSolver

After adding the API key, test it:

```bash
cd ~/Repositories/cryptobot
HEADLESS=true python3 test_cointiply.py
```

## Alternative: Manual CAPTCHA Solving (Development Only)

For development/testing without a CAPTCHA service:

1. **Run in Non-Headless Mode**
   ```bash
   HEADLESS=false python3 test_cointiply.py
   ```

2. **Solve CAPTCHAs Manually**
   - Browser window will appear
   - Solver will wait 120 seconds for you to solve
   - Continue automated testing after

**Note**: Not suitable for production 24/7 automation.

## Quick Fix: Free CapSolver Credits

CapSolver offers free credits for new accounts:
1. Sign up at https://www.capsolver.com
2. Email verification gives initial credits
3. Test with free credits before committing

## Files Modified

- `solvers/captcha.py` - Already has CapSolver support ✅
- `.env` - Add CAPSOLVER_API_KEY ⚠️ Required
- `core/config.py` - Reads CAPSOLVER_API_KEY ✅

## Summary

**To fix all faucets immediately:**

```bash
# 1. Get CapSolver API key from https://www.capsolver.com
# 2. Add to .env:
echo "CAPSOLVER_API_KEY=CAP-YOUR-KEY-HERE" >> .env

# 3. Test
HEADLESS=true python3 test_cointiply.py
```

That's it! All faucets will work once CapSolver is configured.
