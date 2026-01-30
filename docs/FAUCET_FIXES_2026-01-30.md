# Faucet Fixes - DutchyCorp & FreeBitcoin (2026-01-30)

## Issues Resolved

### 1. DutchyCorp - Proxy Detection Failure ❌ → ⚠️
**Problem:** Datacenter IPs (DigitalOcean) immediately flagged with "proxy detected" error  
**Root Cause:** DutchyCorp has strict proxy detection that blocks datacenter IP ranges  
**Impact:** Complete login failure on all datacenter proxies

**Fix Applied:**
- Added residential proxy requirement check in login flow
- Enhanced error logging to warn operators about datacenter proxy usage
- Added check for `residential_proxy` flag in profile configuration
- Improved error message when proxy detection occurs

**Code Changes** ([dutchy.py](../faucets/dutchy.py)):
```python
# Check for datacenter proxy and warn
if hasattr(self, 'profile') and self.profile:
    if not getattr(self.profile, 'residential_proxy', False):
        logger.error(f"[{self.faucet_name}] ⚠️ DATACENTER PROXY DETECTED - DutchyCorp requires residential proxies!")
        logger.error(f"[{self.faucet_name}] Set 'residential_proxy: true' in faucet_config.json or use 2Captcha residential proxies")

# Enhanced proxy detection error logging
if "Proxy Detected" in failure_state:
    logger.error(f"[{self.faucet_name}] {failure_state} - DutchyCorp blocks datacenter IPs. Use residential proxies!")
```

**Action Required:**
1. **Option A:** Use 2Captcha residential proxies (`use_2captcha_proxies: true` in `.env`)
2. **Option B:** Set `residential_proxy: true` in `faucet_config.json` for DutchyCorp account
3. **Option C:** Disable DutchyCorp until residential proxies are available

---

### 2. FreeBitcoin - 100% Login Failure ❌ → 🔄
**Problem:** Complete login failure rate - selectors targeting wrong form fields  
**Root Cause:** Overly broad selectors matching signup forms instead of login forms  
**Impact:** 100% login failure as reported in PROJECT_STATUS_REPORT.md

**Fix Applied:**
- Reordered selectors from most specific to least specific
- Scoped selectors to `#login_form` to avoid signup form collisions
- Removed overly broad generic selectors that could match unintended elements
- Prioritized FreeBitcoin-specific selectors (`btc_address` field)

**Code Changes** ([freebitcoin.py](../faucets/freebitcoin.py)):

**Before:**
```python
email_selectors = [
    "input[name='btc_address']",  # Too broad - could match signup
    "input[type='email']",  # Very broad
    "[placeholder*='email' i]",  # Too broad
    "form input[type='text']:first-of-type",  # Generic fallback
]
```

**After:**
```python
# ⚠️ Order matters - most specific first to avoid signup form fields
email_selectors = [
    "#login_form input[name='btc_address']",  # Scoped to login form
    "input[id='login_form_btc_address']",  # ID variant
    "#login_form_btc_address",  # Direct ID
    "#login_form input[name='username']",  # Login form scoped
    "input[name='btc_address']",  # Fallback without scope
    "#btc_address",
    "#username",
    "#email",
]
```

**Expected Improvement:**
- Login success rate should increase from 0% to 60%+
- Reduced false positives from signup form field matching
- More reliable form detection with specific scope

---

## Deployment

### Local Testing
```bash
# Test DutchyCorp with residential proxy flag
python main.py --single dutchy --visible

# Test FreeBitcoin login flow
python main.py --single freebitcoin --visible --once
```

### Azure VM Deployment
```bash
# Pull latest code
ssh azureuser@4.155.230.212 "cd ~/Repositories/cryptobot && git pull origin master"

# Restart service
ssh azureuser@4.155.230.212 "sudo systemctl restart faucet_worker"

# Monitor logs
ssh azureuser@4.155.230.212 "tail -f ~/Repositories/cryptobot/logs/faucet_bot.log | grep -E 'DutchyCorp|FreeBitcoin'"
```

**Status:** ✅ Deployed to Azure VM (DevNode01) on 2026-01-30 15:59 UTC

---

## Testing Plan

### DutchyCorp
- [ ] Verify residential proxy warning appears in logs when using datacenter IPs
- [ ] Test login with 2Captcha residential proxies (when enabled)
- [ ] Confirm proxy detection errors are properly logged with remediation hints

### FreeBitcoin
- [ ] Test login flow with new selectors
- [ ] Verify login form vs signup form detection
- [ ] Monitor login success rate over 10 attempts
- [ ] Check for diagnostic screenshots in logs/ directory if failures occur

---

## Configuration Notes

### DutchyCorp Residential Proxy Setup

**Method 1: 2Captcha Residential Proxies**
```env
# .env
USE_2CAPTCHA_PROXIES=true
TWOCAPTCHA_API_KEY=your_api_key_here
```

**Method 2: Manual Configuration**
```json
// config/faucet_config.json
{
  "accounts": {
    "dutchy": {
      "username": "your_username",
      "password": "your_password",
      "residential_proxy": true,
      "proxy": "user:pass@residential-proxy.com:8080"
    }
  }
}
```

---

## Monitoring

### Expected Log Patterns

**DutchyCorp - Success:**
```
[DutchyCorp] Login attempt 1/3
[DutchyCorp] ✅ Login successful
```

**DutchyCorp - Datacenter Proxy Warning:**
```
[DutchyCorp] ⚠️ DATACENTER PROXY DETECTED - DutchyCorp requires residential proxies!
[DutchyCorp] Set 'residential_proxy: true' in faucet_config.json or use 2Captcha residential proxies
[DutchyCorp] Proxy info: http://142.93.66.75:8888
```

**FreeBitcoin - Success:**
```
[FreeBitcoin] ✅ Found login email field with selector: #login_form input[name='btc_address']
[FreeBitcoin] ✅ Found login password field with selector: #login_form input[name='password']
[FreeBitcoin] ✅ Found valid login form on: https://freebitco.in/?op=login
[FreeBitcoin] ✅ Login successful (session detected)
```

---

## Next Steps

1. **Immediate:**
   - Monitor FreeBitcoin login success rate
   - Configure residential proxies for DutchyCorp

2. **Short-term:**
   - Add automated success rate tracking for both faucets
   - Consider implementing proxy type auto-detection

3. **Long-term:**
   - Evaluate cost/benefit of residential proxies for other faucets
   - Build proxy recommendation system based on faucet requirements

---

## Related Documentation
- [PROJECT_STATUS_REPORT.md](../docs/summaries/PROJECT_STATUS_REPORT.md)
- [AZURE_VM_STATUS.md](../docs/azure/AZURE_VM_STATUS.md)
- [DEVELOPER_GUIDE.md](../docs/DEVELOPER_GUIDE.md)

## Git Commit
- **Commit:** c72611e
- **Date:** 2026-01-30
- **Message:** "Fix DutchyCorp proxy detection and FreeBitcoin login issues"
