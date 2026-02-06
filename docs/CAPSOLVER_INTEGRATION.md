# CapSolver Integration Guide  
**Issue #87: hCaptcha Support via CapSolver Fallback**

## Problem
2Captcha returns `ERROR_METHOD_CALL` for hCaptcha challenges on Cointiply and other sites, breaking automated claims.

## Solution  
CapSolver as fallback provider with automatic failover when 2Captcha can't handle hCaptcha.

## Setup

### 1. Get CapSolver API Key
1. Sign up at https://www.capsolver.com/
2. Add funds ($1 minimum)
3. Copy your API key from dashboard

### 2. Configure Environment
Add to `.env`:
```bash
# Primary provider (2Captcha)
TWOCAPTCHA_API_KEY=your_2captcha_key_here

# Fallback provider (CapSolver for hCaptcha)
CAPTCHA_FALLBACK_PROVIDER=capsolver
CAPSOLVER_API_KEY=your_capsolver_key_here
```

### 3. Test Configuration
```bash
# On Azure VM
cd ~/Repositories/cryptobot
python3 solvers/capsolver.py  # Tests CapSolver connection and balance

# Test Cointiply with CapSolver fallback
HEADLESS=true python3 test_all_claims.py
```

## How It Works

### Automatic Fallback Chain
1. **2Captcha tries first** - Fast and cheap for Turnstile/reCaptcha
2. **CapSolver activates** - When 2Captcha returns errors:
   - `ERROR_METHOD_CALL` (hCaptcha not supported)
   - `ERROR_NO_SLOT` (service busy)
   - `ERROR_ZERO_BALANCE` (out of funds)
3. **Up to 2 retries per provider** - Handles temporary timeouts

### Provider Selection Logic
Located in `solvers/captcha.py`:
```python
async def solve_with_fallback(self, page, captcha_type, sitekey, url, proxy_context):
    """
    Try primary provider → fallback provider → return None
    Retries each provider 2x before moving to next
    """
```

### Cost Structure (as of Feb 2026)
| CAPTCHA Type | 2Captcha | CapSolver |
|--------------|----------|-----------|
| hCaptcha     | ❌ Not supported | $0.0008/solve |
| reCaptcha v2 | $0.0029  | $0.0016 |
| Turnstile    | $0.0029  | $0.0014 |
| Image        | $0.00050 | $0.00050 |

**Recommendation**: Use 2Captcha primary + CapSolver fallback for best availability.

## Supported Faucets
✅ **Cointiply** - hCaptcha on login  
✅ **All faucets** - Improved reliability with dual-provider failover

## Verification

### Check Logs
Look for these messages in `logs/faucet_bot.log`:
```
🔑 Trying provider: 2captcha
❌ 2Captcha failed to return a solution after 2 attempts
🔑 Trying provider: capsolver
✅ CapSolver succeeded
```

### Monitor Spend
```bash
# Check daily captcha budget usage
grep "Daily budget" logs/faucet_bot.log

# Get CapSolver balance
python3 -c "import asyncio; from solvers.capsolver import CapSolverClient; import os; asyncio.run(CapSolverClient(os.getenv('CAPSOLVER_API_KEY')).get_balance())"
```

## Troubleshooting

### CapSolver Returns 403/401
- **Cause**: Invalid API key
- **Fix**: Verify `CAPSOLVER_API_KEY` in `.env` matches dashboard

### Still Getting hCaptcha Errors
- **Cause**: Fallback provider not configured
- **Fix**: Ensure `CAPTCHA_FALLBACK_PROVIDER=capsolver` in `.env`

### Balance Depleted
- **Cause**: Daily budget exceeded
- **Fix**: Increase `CAPTCHA_DAILY_BUDGET` in `.env` (default $5.00)

## Implementation Files
- `solvers/capsolver.py` - CapSolver API client (NEW)
- `solvers/captcha.py` - Main solver with fallback logic (EXISTING)
- `core/config.py` - Configuration fields (EXISTING)
- `.env.example` - Environment template (UPDATED)

## Next Steps
After CapSolver integration:
1. Test Cointiply login - Should now succeed ✅
2. Monitor solve success rate - Track in logs
3. Optimize provider routing - Adapt based on faucet-specificpatterns

---
**Related Issues**: #87 #90
**Updated**: 2025-02-06
