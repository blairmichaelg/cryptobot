# Action Plan: Fix All Faucets - Step by Step

## Current Status
- ✅ All 18 faucets: Code complete, imports successful
- ✅ Testing tools created
- ⏳ Waiting: Live testing with credentials to identify selector issues

## What You Need to Do

### Step 1: Set Up Environment (5 minutes)

On Azure VM (4.155.230.212) or Linux CI:

```bash
cd ~/Repositories/cryptobot  # Or your repo location

# Copy and configure .env
cp .env.example .env
nano .env  # Fill in all credentials

# Ensure these are set at minimum:
# - TWOCAPTCHA_API_KEY or CAPSOLVER_API_KEY
# - FIREFAUCET_USERNAME and FIREFAUCET_PASSWORD
# - FREEBITCOIN_USERNAME and FREEBITCOIN_PASSWORD
# - ... (all 18 faucets)
```

### Step 2: Run Comprehensive Test (10 minutes)

```bash
HEADLESS=true python scripts/test_all_faucets.py 2>&1 | tee test_results.log
```

**Expected Output**:
```
Testing 18 faucet(s)
================================================================================
Testing FireFaucet
================================================================================
✅ FireFaucet: Import successful
✅ FireFaucet: Credentials found
🔐 FireFaucet: Testing login...
✅ FireFaucet: Login successful
💰 FireFaucet: Testing claim...
⚠️  FireFaucet: Claim failed - Claim button not found

[... continues for all faucets ...]

TEST SUMMARY
================================================================================
Total Faucets:   18
Imports OK:      18/18
Credentials OK:  18/18
Logins OK:       14/18
Claims OK:       8/18
```

### Step 3: Fix Each Failing Faucet

For each faucet that fails, follow this process:

#### Example: FireFaucet Claim Button Fix

**Problem**: "Claim button not found"

**Debug**:
```bash
# Visual inspection
HEADLESS=false python main.py --single firefaucet --once
# Watch where it fails, note the button ID/class
```

**Fix** (in `faucets/firefaucet.py`):

Find the claim button selector section (around line 763):
```python
# BEFORE
faucet_btn_selectors = [
    "#get_reward_button",
    "button:has-text('Get reward')",
]

# AFTER - add more fallbacks based on what you see
faucet_btn_selectors = [
    "#get_reward_button",
    "#claim_button",  # NEW - found on current page
    "button.faucet-btn",  # NEW - found on current page
    "button:has-text('Get reward')",
    "button:has-text('Claim Now')",  # NEW - text changed
]
```

**Test**:
```bash
HEADLESS=true python scripts/test_all_faucets.py --faucet firefaucet
```

**Commit**:
```bash
git add faucets/firefaucet.py
git commit -m "Fix FireFaucet claim button selector"
git push
```

#### Example: FreeBitcoin Balance Selector Fix

**Problem**: "Balance extraction failed"

**Known Fix** (from memory): Use `#balance_small` instead of `#balance`

**Fix** (in `faucets/freebitcoin.py`):

Find balance extraction (search for "balance_selectors"):
```python
# UPDATE PRIMARY SELECTOR
balance_selectors = [
    "#balance_small",  # PRIMARY - this is the correct one
    "#balance",        # Fallback
    ".balance",
]
```

#### Example: CoinPayU Login Button

**Problem**: "Login button not found after CAPTCHA"

**Already Fixed**: The code already has fallback logic (lines 229-252), but may need selector update

**Verify**:
```bash
HEADLESS=false python main.py --single coinpayu --once
```

If still fails, add more selectors to the list at line 229-241.

## Known Issues from Previous Tests

Based on test logs, here are likely issues to fix:

### 1. FireFaucet
- **Issue**: Claim button selectors stale
- **File**: `faucets/firefaucet.py` line 763
- **Action**: Add fallback selectors found on current page

### 2. FreeBitcoin
- **Issue**: Balance/timer extraction
- **File**: `faucets/freebitcoin.py` 
- **Action**: Verify `#balance_small` and `#time_remaining` are primary selectors

### 3. CoinPayU
- **Issue**: Login button after CAPTCHA
- **File**: `faucets/coinpayu.py` line 229
- **Action**: May need additional fallback selectors

### 4. AdBTC
- **Issue**: Cloudflare timeout
- **File**: `faucets/adbtc.py`
- **Action**: Increase `max_wait_seconds` from 30 to 120

### 5. Dutchy
- **Issue**: Proxy detection (requires residential)
- **File**: N/A (infrastructure issue)
- **Action**: Configure residential proxies OR skip in production

### 6. Cointiply
- **Issue**: hCaptcha support
- **File**: N/A (already fixed with fallback)
- **Action**: Verify `.env` has `CAPTCHA_FALLBACK_PROVIDER=capsolver`

### 7-18. Pick.io Family
- **Likely Working**: Login is implemented, just need credentials
- **Action**: Ensure all 11 Pick faucets have credentials in `.env`
- **Verify**: Run quick test: `HEADLESS=true python scripts/test_all_faucets.py --quick`

## Batch Fix Strategy

Instead of fixing one at a time, you can:

1. **Run full test** to get all failures
2. **Group by issue type**:
   - Selector issues: Update selectors
   - Timeout issues: Increase timeouts
   - Proxy issues: Document requirements
3. **Fix all similar issues** in one session
4. **Re-test all** to verify

## Estimated Time

- **Setup**: 5 minutes
- **Initial test**: 10 minutes (18 faucets × 30 seconds each)
- **Fixing**:
  - Simple selector updates: 5 minutes each
  - Complex debugging: 15-30 minutes each
  - Residential proxy setup: 1 hour

**Total**: 2-4 hours to get all faucets working (assuming no major site changes)

## Success Criteria

After all fixes:

```bash
HEADLESS=true python scripts/test_all_faucets.py
```

Should output:
```
TEST SUMMARY
================================================================================
Total Faucets:   18
Imports OK:      18/18
Credentials OK:  18/18
Logins OK:       18/18
Claims OK:       16-18/18

FireFaucet       ✅ ✅ ✅ ✅
Cointiply        ✅ ✅ ✅ ✅
FreeBitcoin      ✅ ✅ ✅ ✅
[...]
```

(16-18 because Dutchy and possibly others need residential proxies)

## Pro Tips

1. **Use visual mode** (`HEADLESS=false`) to quickly identify selector issues
2. **Test in batches**: Fix 3-4 faucets, commit, test, repeat
3. **Document issues**: If a site is completely broken, document it and move on
4. **Git often**: Commit after each working fix so you can rollback if needed
5. **Check site first**: Before spending time debugging, check if site is actually up

## Emergency Fallback

If you can't fix a faucet after 30 minutes of trying:
1. Document the issue in `docs/faucet_issues.md`
2. Disable it in production: Add to `DISABLED_FAUCETS` in config
3. Move on to next faucet
4. Come back later or get help

Not every site can be automated - some add anti-bot measures that are too strong.

## Next Action

```bash
# On Azure VM or Linux CI
cd ~/Repositories/cryptobot
cp .env.example .env
# Edit .env with your credentials
HEADLESS=true python scripts/test_all_faucets.py 2>&1 | tee test_results.log
# Review test_results.log
# Fix failing faucets one by one
```

The tools are ready. The fixes are straightforward. Just need to run the tests and update selectors.
