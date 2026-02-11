# Faucet Selector Testing & Update Guide

**Last Updated**: 2026-02-11  
**Purpose**: Guide for testing faucet selectors and updating them when websites change

---

## Quick Reference

### Selector Priority Order (Always Follow)
```
1. ID selectors             (#user-balance, #claim_timer)
2. Data attributes          ([data-balance], [data-timer])
3. Name attributes          ([name="balance"])
4. Type attributes          ([type="password"])
5. Specific classes         (.user-balance, .timer-display)
6. Generic classes          (.balance, .timer)
7. Attribute patterns       ([class*='balance'])
8. Complex selectors        (.navbar .balance, .fa-clock + span)
9. Text-based (last resort) (button:has-text("Login"))
```

**Why?** ID and data attributes are most stable; classes and complex selectors break frequently.

---

## Testing Individual Faucets

### On Linux VM (Required for Browser Tests)

```bash
# SSH to VM
ssh azureuser@4.155.230.212

# Pull latest code
cd ~/Repositories/cryptobot
git pull origin master

# Test single faucet (one-time run)
HEADLESS=true python main.py --single firefaucet --once

# Test with verbose logging
HEADLESS=true python main.py --single litepick --once --log-level DEBUG

# Monitor live logs
journalctl -u faucet_worker -f | grep -E "(selector|CAPTCHA|balance|timer)"
```

### Common Test Scenarios

#### 1. Login Test
```bash
# Test login flow for a faucet
HEADLESS=true python main.py --single cointiply --once
```

**What to Check in Logs**:
- ✅ `Login successful`
- ❌ `Email input not found` → email selector stale
- ❌ `Password input not found` → password selector stale
- ❌ `Login submit button not found` → submit selector stale
- ⚠️ `CAPTCHA solving failed` → check CAPTCHA service balance

#### 2. Balance Extraction Test
Look for these log patterns:
```
✅ [FaucetName] Balance extracted: 0.00012345 using selector '#user-balance'
⚠️ [FaucetName] Balance extraction returned '0' - may indicate selector staleness
❌ [FaucetName] All balance selectors failed
```

#### 3. Timer Extraction Test
Look for:
```
✅ [FaucetName] Timer extracted: 45.5 minutes
✅ [FaucetName] Faucet on cooldown: 45m remaining
⚠️ [FaucetName] Timer extraction returned 0 minutes
```

#### 4. Claim Test
Full claim flow logs:
```
✅ [FaucetName] Starting claim process
✅ [FaucetName] Solving login captcha...
✅ [FaucetName] Claim button found
✅ [FaucetName] Claim successful: You received 0.00001 BTC
❌ [FaucetName] Claim button not visible
```

---

## Updating Selectors When Sites Change

### Step 1: Identify the Broken Selector

From logs, identify what's failing:
```
[FireFaucet] Email input not found on login page
```

### Step 2: Inspect the Live Page

**Option A: Local Browser (Manual)**
1. Visit the faucet website in Chrome/Firefox
2. Right-click → Inspect Element
3. Find the element (email field, claim button, timer, etc.)
4. Note the ID, data-attributes, classes, names

**Option B: Via Playwright (Automated)**
```python
# In scripts/verify_selectors.py or similar
async with async_playwright() as p:
    browser = await p.chromium.launch(headless=False)
    page = await browser.new_page()
    await page.goto("https://freebitcoin.io/login")
    
    # Print all input fields
    inputs = await page.query_selector_all("input")
    for inp in inputs:
        input_id = await inp.get_attribute("id")
        input_name = await inp.get_attribute("name")
        input_type = await inp.get_attribute("type")
        print(f"ID: {input_id}, Name: {input_name}, Type: {input_type}")
```

### Step 3: Update Selector List

**Example: Updating FireFaucet email selector**

**Before** (broken):
```python
email_selectors = [
    'input[type="email"]',       # Too generic, matches signup form
    'input[name="email"]',       # May not exist
]
```

**After** (found via inspection):
```python
email_selectors = [
    'input#login_email',         # ID (most stable)
    'input[data-field="email"]', # Data attribute
    'input[name="email"]:not([form*="signup"])',  # Name with exclusion
    'input[type="email"]:not([form*="signup"])',  # Type with exclusion
    'input[placeholder*="email" i]',  # Fallback
]
```

### Step 4: Test the Change

```bash
# Test locally on VM
cd ~/Repositories/cryptobot
nano faucets/firefaucet.py  # Make the change

# Test immediately
HEADLESS=true python main.py --single firefaucet --once

# Check logs
tail -n 50 logs/faucet_bot.log | grep -i email
```

### Step 5: Commit and Deploy

```bash
git add faucets/firefaucet.py
git commit -m "fix(firefaucet): update email selector for login form"
git push origin master

# Restart service
sudo systemctl restart faucet_worker

# Monitor
journalctl -u faucet_worker -f | grep FireFaucet
```

---

## Common Selector Issues & Solutions

### Issue 1: "Element not found"
**Cause**: Selector doesn't match current HTML  
**Solution**: Inspect page, update selector list with current IDs/classes

### Issue 2: "Element not visible"
**Cause**: Element exists but hidden (CSS display: none)  
**Solution**: Add `:visible` pseudo-class or check parent visibility first

### Issue 3: Clicks wrong button
**Cause**: Selector too broad (e.g., `button.btn` matches Cancel AND Login)  
**Solution**: Use more specific selector:
```python
# Before (ambiguous)
'button.btn'

# After (specific)
'button.btn:has-text("Login")'
'button[data-action="login"]'
'button#login_submit'
```

### Issue 4: Form matches signup instead of login
**Cause**: Both forms have similar selectors  
**Solution**: Exclude signup forms:
```python
'input[type="email"]:not([form*="signup"]):not([form*="register"])'
```

### Issue 5: Timer returns 0 minutes
**Cause**: Timer selector stale or timer element not loaded yet  
**Solutions**:
- Wait for page load: `await page.wait_for_load_state("networkidle")`
- Add fallback selectors: `[data-timer], #timer, .countdown, .time-remaining`
- Check if timer is in iframe: `page.frame_locator("iframe").locator("#timer")`

---

## Selector Update Checklist

When updating any selector:

- [ ] **Follow priority order**: ID > data-* > name > type > class
- [ ] **Add 3-5 fallbacks**: Don't rely on a single selector
- [ ] **Exclude signup/register forms**: Use `:not([form*="signup"])`
- [ ] **Test on live page**: Verify selector works in browser DevTools
- [ ] **Test programmatically**: Run faucet with `--once` flag
- [ ] **Check logs**: Ensure no errors about element not found
- [ ] **Commit with message**: `fix(faucetname): update [element] selector`
- [ ] **Monitor after deploy**: Check production logs for 24 hours

---

## Debugging Tips

### Enable Debug Logging
```bash
# In .env on VM
LOG_LEVEL=DEBUG

# Or via CLI
HEADLESS=true python main.py --single faucetcrypto --once --log-level DEBUG
```

### Check What Selectors Are Being Tried
Look for logs like:
```
[DEBUG] Trying email selector: input#login_email
[DEBUG] Email selector found: input[data-field="email"]
```

### Verify Element Exists on Page
```python
# Add temporary debug code
all_inputs = await page.query_selector_all("input")
logger.debug(f"Page has {len(all_inputs)} input elements")
for inp in all_inputs[:5]:  # Show first 5
    logger.debug(f"Input: type={await inp.get_attribute('type')}, id={await inp.get_attribute('id')}")
```

### Check if Element is in Shadow DOM
Some modern sites use Shadow DOM. Standard selectors won't work.
```python
# Check for shadow root
shadow_host = await page.query_selector("#some-element")
if shadow_host:
    shadow_root = await shadow_host.evaluate_handle("el => el.shadowRoot")
    # Can't use standard selectors inside shadow DOM
```

---

## Best Practices

### DO ✅
- **Use ID selectors first**: `#user-balance` is most stable
- **Add data-* attributes**: `[data-balance]` is semantic and stable
- **Exclude forms**: `:not([form*="signup"])` avoids ambiguity
- **Log extraction results**: Know when selectors fail
- **Test after updates**: Don't deploy untested selector changes

### DON'T ❌
- **Don't use complex CSS**: `.parent > .child + .sibling` is fragile
- **Don't rely on text**: `button:has-text("Login")` breaks if language changes
- **Don't use classes alone**: `.btn` is too generic
- **Don't skip fallbacks**: Always have 3-5 alternative selectors
- **Don't commit without testing**: Broken selectors break all claims

---

## Automated Selector Verification (Future)

**Planned feature**: `scripts/verify_selectors.py`

```bash
# Check all faucets without credentials
python scripts/verify_selectors.py --all

# Check specific faucet
python scripts/verify_selectors.py --faucet firefaucet

# Output: Selector health report
✅ FireFaucet: 8/10 selectors found on page
❌ FreeBitcoin: 2/10 selectors found (UPDATE NEEDED)
```

---

## Resources

- **Playwright Selectors**: https://playwright.dev/python/docs/selectors
- **CSS Selectors Reference**: https://developer.mozilla.org/en-US/docs/Web/CSS/CSS_Selectors
- **Project Selector Conventions**: `.github/copilot-instructions.md` (Faucet selector update strategy)
- **Existing Selector Patterns**: `docs/summaries/FAUCET_DEBUGGING_SUMMARY_FEB6.md`

---

## Support

If selectors keep breaking:
1. Check if site added anti-bot protection (Cloudflare, etc.)
2. Verify proxy isn't being blocked
3. Check if site requires JavaScript rendering (Playwright handles this)
4. Consider if site changed authentication flow entirely (may need refactor)

For persistent issues, document in `docs/summaries/FAUCET_BUG_REPORT.md`
