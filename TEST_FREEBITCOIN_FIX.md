# TEST INSTRUCTIONS FOR FREEBITCOIN FIX

## Quick Test (5 minutes)

### 1. Run Debug Script
```bash
cd c:\Users\azureuser\Repositories\cryptobot
python debug_freebitcoin_current.py
```

**What to look for:**
- Browser opens and navigates to FreeBitcoin
- Console shows list of forms, inputs, buttons
- Lines like "✅ input[name='btc_address'] - Found (1), Visible: True"
- Screenshot saved to `logs/freebitcoin_current_state.png`

### 2. Review Screenshot
```bash
start logs\freebitcoin_current_state.png
```

**What to check:**
- Is there a login form visible?
- Does it have email/username and password fields?
- Is there a login/submit button?

### 3. Test Actual Login
```bash
# Make sure you have credentials in .env
python main.py --single freebitcoin --visible --once
```

**What to expect:**
- Browser opens
- Navigates to FreeBitcoin
- Fills in credentials
- Clicks login button
- Either succeeds or fails with detailed error message

### 4. Check Logs
```bash
tail -50 logs/faucet_bot.log | findstr /I "freebitcoin"
```

**What to look for:**
- "[FreeBitcoin] Email field found" 
- "[FreeBitcoin] Both email and password fields found"
- "✅ [FreeBitcoin] Login successful"
- OR specific error messages like "Could not find email/username field"

## Full Test (15 minutes)

### 1. Test with Headless Mode
```bash
python main.py --single freebitcoin --once
```

### 2. Check Screenshots (if failed)
```bash
dir logs\freebitcoin_*.png
```

Review any screenshots generated:
- `freebitcoin_login_failed_no_email_field.png`
- `freebitcoin_login_failed_no_password_field.png`
- `freebitcoin_login_failed.png`

### 3. Check Analytics
```python
from core.analytics import AnalyticsManager
am = AnalyticsManager()
stats = am.get_faucet_stats('freebitcoin')
print(f"Login success: {stats.get('login_success', 0)}")
print(f"Login failures: {stats.get('login_failures', 0)}")
```

## Expected Results

### ✅ Success Indicators
- Console shows "✅ [FreeBitcoin] Login successful"
- No error screenshots generated
- Analytics shows login_success incremented
- Bot continues to claim process

### ❌ Failure Indicators
- Error: "Could not find email/username field"
- Screenshots show unexpected page layout
- Logs show "All navigation strategies failed"
- Cloudflare or CAPTCHA blocking

## Next Steps Based on Results

### If Successful ✅
1. Update PROJECT_STATUS_REPORT.md to reflect fixed status
2. Deploy to Azure VM
3. Monitor for 24-48 hours

### If Failed ❌

#### Selector Mismatch
- Run debug script
- Review actual element names/IDs in console output
- Add new selectors to `email_selectors` or `password_selectors`
- Test again

#### Cloudflare Blocking
- Check if proxy is blocked
- Rotate to different proxy
- Increase `handle_cloudflare()` timeout

#### CAPTCHA Required
- Verify 2Captcha/CapSolver API key
- Check API balance
- Enable CAPTCHA solving if disabled

#### Site Structure Changed
- Review screenshots
- Inspect page with browser DevTools
- Update login URLs if endpoint changed
- Update selectors based on new structure

## Troubleshooting Commands

```bash
# Check if credentials are set
grep FREEBITCOIN .env

# Test with maximum verbosity
python main.py --single freebitcoin --visible --once 2>&1 | tee freebitcoin_test.log

# Check last 100 log lines
tail -100 logs/faucet_bot.log

# Find all FreeBitcoin-related screenshots
dir /s logs\*freebitcoin*.png
```

## Contact/Escalation
If all tests fail after trying above steps:
1. Save screenshots
2. Save log output
3. Note the exact error message
4. Check docs/FREEBITCOIN_FIX_JANUARY_2026.md for detailed technical info
