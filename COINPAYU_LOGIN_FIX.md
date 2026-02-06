# CoinPayU Login Button Selector Fix

## Problem
CAPTCHA solves successfully but login button is not found on CoinPayU due to DOM changes after CAPTCHA completion.

## Solution Implemented

### 1. Multiple Fallback Selectors
Added the following fallback selectors in priority order:
```python
login_selectors = [
    'button.btn-primary:has-text("Login")',  # Primary selector
    'button:has-text("Login")',              # Fallback without class
    'button:has-text("Log in")',             # Alternative text
    'button.btn-primary',                    # Just the class
    'button[type="submit"]',                 # Submit button
    'input[type="submit"]',                  # Input submit
    'button.btn',                            # Generic button class
    '#login_button',                         # Common ID
    '.login-btn',                            # Common class
]
```

### 2. DOM Stabilization Wait
After CAPTCHA solve, added:
- `wait_for_load_state("domcontentloaded")` with timeout
- Additional 0.3-0.7s random delay
- Graceful handling if wait times out

### 3. Selector Visibility Check
Each selector is tested for:
- Element existence (`count() > 0`)
- Element visibility (`is_visible()`)
- First matching visible element is used

## Files Modified
- `faucets/coinpayu.py` - Lines 215-258
- `tests/test_coinpayu.py` - Added 2 new tests, updated existing tests

## Testing

### Local Testing (Linux sandbox)
```bash
cd /home/runner/work/cryptobot/cryptobot
python -m pytest tests/test_coinpayu.py -v
```
Result: **24/25 tests passing** (1 pre-existing test issue unrelated to changes)

### Azure VM Testing (Production Environment)
**IMPORTANT**: Must test on Azure VM, not Windows machine!

#### SSH to Azure VM:
```bash
ssh azureuser@4.155.230.212
```

#### Navigate to cryptobot directory:
```bash
cd ~/Repositories/cryptobot
```

#### Pull latest changes:
```bash
git pull origin copilot/fix-coinpayu-login-button-selector
```

#### Run diagnostic script (captures HTML for inspection):
```bash
HEADLESS=true python3 test_coinpayu.py
```

This will:
- Navigate to login page
- Fill credentials
- Solve CAPTCHA
- Capture all button selectors and HTML
- Save to `coinpayu_login_page.html` and `coinpayu_login_form.html`

#### Test actual login:
```bash
HEADLESS=true python3 main.py --single coinpayu --once
```

Or test with pytest:
```bash
HEADLESS=true python3 -m pytest tests/test_coinpayu.py::test_coinpayu_login_success -v
```

## Expected Behavior

### Before Fix
- CAPTCHA solves ✅
- Login button search fails ❌
- Login attempt fails

### After Fix
- CAPTCHA solves ✅
- Tries primary selector (may fail if DOM changed)
- Falls back to alternative selectors
- Finds visible login button ✅
- Clicks button ✅
- Login succeeds ✅

## Diagnostic Output
The diagnostic script will show:
1. All buttons found on page after CAPTCHA solve
2. Each button's:
   - Visible state
   - Text content
   - Classes
   - ID
   - Type attribute
3. Which selectors match
4. Recommended selector to use

## Rollback Plan
If this fix causes issues:
```bash
git revert fd64e0b
```

## Related
- Issue #88
- Pattern follows `faucets/pick_base.py` (lines 323-327)
- Pattern follows `faucets/faucetcrypto.py` (line 80)
