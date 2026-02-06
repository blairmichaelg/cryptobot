# Faucet Testing & Debugging Guide

## Quick Start - Get Faucets Working

This guide will help you test and fix all 18 faucets until they work.

### Prerequisites

1. **Linux Environment** (Azure VM or CI)
   - Camoufox browser requires Linux
   - Windows testing will fail

2. **Credentials Configured**
   - Copy `.env.example` to `.env`
   - Fill in all faucet credentials (18 faucets × 2 = 36 variables minimum)
   - Add CAPTCHA API keys (2Captcha or CapSolver)

3. **Dependencies Installed**
   ```bash
   pip install -r requirements.txt
   playwright install
   ```

## Testing Strategy

### Option 1: Automated Testing (Recommended)

Test all faucets systematically:

```bash
# Test all faucets (login + claim)
HEADLESS=true python scripts/test_all_faucets.py

# Test specific faucet
HEADLESS=true python scripts/test_all_faucets.py --faucet firefaucet

# Quick test (login only, no claim)
HEADLESS=true python scripts/test_all_faucets.py --quick
```

**Output**: Clear summary showing which faucets pass/fail at each stage (import, credentials, login, claim)

### Option 2: Selector Verification (Visual)

Check if selectors still work on live pages (no login required):

```bash
# Visual verification (browser window opens)
HEADLESS=false python scripts/verify_selectors.py

# Verify specific faucet
HEADLESS=true python scripts/verify_selectors.py --faucet firefaucet
```

**Output**: Shows which selectors are found/missing on actual pages

### Option 3: Manual Single Faucet Test

Test one faucet manually:

```bash
# With visible browser
HEADLESS=false python main.py --single firefaucet --once

# Headless
HEADLESS=true python main.py --single firefaucet --once
```

## Common Issues & Fixes

### Issue 1: "Selector not found"

**Cause**: Website changed HTML/CSS structure

**Fix**:
1. Run selector verification: `HEADLESS=false python scripts/verify_selectors.py --faucet <name>`
2. Inspect the page visually to find new selectors
3. Update selectors in `faucets/<faucet_name>.py`
4. Re-test

**Example**:
```python
# OLD selector (not working)
claim_btn = page.locator("#claim-button")

# NEW selector (found on current page)
claim_btn = page.locator("button.btn-primary:has-text('Claim')")
```

### Issue 2: "Cloudflare timeout"

**Cause**: Cloudflare challenge takes longer than timeout

**Fix**: Increase timeout in the faucet file
```python
# In faucets/<name>.py
await self.handle_cloudflare(max_wait_seconds=120)  # Increased from 30s to 120s
```

### Issue 3: "Login button not found after CAPTCHA"

**Cause**: DOM changes after CAPTCHA solve

**Fix**: Already implemented in most faucets - re-query button after CAPTCHA

### Issue 4: "Proxy detected" / "Access denied"

**Cause**: Site blocks datacenter IPs

**Fix**: 
- Configure residential proxies in `.env`
- Set `USE_2CAPTCHA_PROXIES=true` for residential proxy rotation
- Or add to proxy bypass list in `core/proxy_manager.py`

### Issue 5: "hCaptcha ERROR_METHOD_CALL"

**Fix**: Already implemented - set fallback in `.env`:
```bash
CAPTCHA_FALLBACK_PROVIDER=capsolver
CAPSOLVER_API_KEY=your_key_here
```

## Systematic Debugging Process

For each failing faucet:

1. **Identify Stage of Failure**
   ```bash
   HEADLESS=true python scripts/test_all_faucets.py --faucet <name>
   ```
   - Import? → Fix Python syntax
   - Credentials? → Add to `.env`
   - Login? → Update selectors, check Cloudflare
   - Claim? → Update claim button/timer/balance selectors

2. **Visual Inspection**
   ```bash
   HEADLESS=false python main.py --single <name> --once
   ```
   - Watch the browser to see exactly where it fails
   - Note which selectors don't match
   - Take screenshots if needed

3. **Update Code**
   - Edit `faucets/<name>.py`
   - Update selectors based on actual page structure
   - Commit changes

4. **Verify Fix**
   ```bash
   HEADLESS=true python scripts/test_all_faucets.py --faucet <name>
   ```

5. **Repeat** for next faucet

## Expected Results

After fixing all issues, you should see:

```
TEST SUMMARY
================================================================================
Total Faucets:   18
Imports OK:      18/18
Credentials OK:  18/18
Logins OK:       18/18
Claims OK:       16-18/18  (2 may require residential proxies)
```

## Files to Modify

When updating selectors:

- `faucets/firefaucet.py` - FireFaucet selectors
- `faucets/freebitcoin.py` - FreeBitcoin selectors
- `faucets/cointiply.py` - Cointiply selectors
- `faucets/pick_base.py` - Shared Pick.io family selectors
- `faucets/litepick.py`, etc. - Individual Pick faucet selectors

## Quick Reference: Selector Update Pattern

```python
# BEFORE: Single selector (fragile)
button = await page.locator("#claim").click()

# AFTER: Multiple fallbacks (robust)
selectors = [
    "#claim",                        # Primary ID
    "button:has-text('Claim')",     # Text match
    "button.btn-primary",           # Class
    "button[type='submit']",        # Type attribute
]

for sel in selectors:
    try:
        btn = page.locator(sel)
        if await btn.count() > 0 and await btn.is_visible():
            await btn.click()
            break
    except:
        continue
```

## Environment Setup (Example .env)

```bash
# Core
HEADLESS=true
TWOCAPTCHA_API_KEY=your_2captcha_key_here
CAPSOLVER_API_KEY=your_capsolver_key_here
CAPTCHA_FALLBACK_PROVIDER=capsolver

# FireFaucet
FIREFAUCET_USERNAME=your_email@example.com
FIREFAUCET_PASSWORD=your_password

# FreeBitcoin
FREEBITCOIN_USERNAME=your_email@example.com
FREEBITCOIN_PASSWORD=your_password

# ... (repeat for all 18 faucets)
```

## Troubleshooting

**"No module named 'camoufox'"**
```bash
pip install camoufox[geoip]
```

**"Browser not installed"**
```bash
playwright install firefox
```

**"Permission denied" on scripts**
```bash
chmod +x scripts/*.py
```

**Tests hang/timeout**
- Increase timeout in browser init: `BrowserManager(timeout=300000)`  # 5 minutes
- Check if CAPTCHA is blocking (need API keys)
- Check if Cloudflare is blocking (may need to adjust bypass logic)

## Success Criteria

✅ All 18 faucets import successfully
✅ All 18 faucets have valid credentials
✅ All 18 faucets can login
✅ 16-18 faucets can claim (some may require residential proxies)

## Getting Help

If a faucet continues to fail after fixing selectors:
1. Check the site directly in browser - is it down? Changed significantly?
2. Review error logs - what's the exact failure point?
3. Check if site added new anti-bot protection
4. Consider if site requires manual verification (email, phone, etc.)

Some faucets may become unfixable if:
- Site is permanently offline
- Site requires manual verification
- Site blocks all automation completely

Document these separately and skip them in production runs.
