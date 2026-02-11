# Selector Update Guide

When faucet sites update their HTML structure, our bot's CSS/XPath selectors can break, causing login failures, claim errors, or balance extraction issues. This guide shows you how to identify, fix, and test selector changes.

---

## Table of Contents

1. [Identifying When Selectors Need Updating](#identifying-when-selectors-need-updating)
2. [Finding Current Selectors on Faucet Sites](#finding-current-selectors-on-faucet-sites)
3. [Testing Selector Changes](#testing-selector-changes)
4. [Best Practices for Fallback Selectors](#best-practices-for-fallback-selectors)
5. [Common Selector Patterns](#common-selector-patterns)
6. [Troubleshooting Tips](#troubleshooting-tips)

---

## Identifying When Selectors Need Updating

### Symptoms of Broken Selectors

1. **Login Failures**
   - Error: "Login button not found"
   - Error: "Email/password field not visible"
   - Bot repeatedly tries to login but never succeeds

2. **Claim Failures**
   - Error: "Claim button not found"
   - Error: "Element not found" during claim process
   - Claims timeout without completing

3. **Balance Extraction Failures**
   - Balance shows as 0.0 when you know you have funds
   - Error: "Could not extract balance"
   - Balance extraction times out

4. **Timer Extraction Failures**
   - Next claim timer always shows 0
   - Error: "Could not find timer element"
   - Bot tries to claim too frequently

### Where to Look

Check the logs at `/home/runner/work/cryptobot/cryptobot/logs/faucet_bot.log` for errors like:

```
[FreeBitcoin] Error: Timeout waiting for selector '#login_form_btc_address'
[FireFaucet] Element not found: button.claim-button
[Cointiply] Could not extract balance - no matching elements
```

---

## Finding Current Selectors on Faucet Sites

### Step 1: Open the Site in a Browser

1. Navigate to the faucet site (e.g., `https://freebitco.in`)
2. Open Developer Tools:
   - **Chrome/Edge**: Press `F12` or `Ctrl+Shift+I` (Windows) / `Cmd+Option+I` (Mac)
   - **Firefox**: Press `F12` or `Ctrl+Shift+I` (Windows) / `Cmd+Option+I` (Mac)

### Step 2: Locate the Element

1. Click the **Element Picker** tool (usually looks like an arrow in a box, or press `Ctrl+Shift+C`)
2. Hover over and click the element you need (e.g., login button, email field, balance display)
3. The HTML for that element will be highlighted in the Elements/Inspector panel

### Step 3: Extract a Robust Selector

#### For Input Fields (Email, Password, Wallet Address)

Look for these attributes in order of preference:
1. `id` attribute - Most stable (e.g., `#login_form_btc_address`)
2. `name` attribute - Good for forms (e.g., `input[name="email"]`)
3. `type` + unique class (e.g., `input[type="email"].form-control`)

**Example HTML:**
```html
<input type="text" id="btc_address" name="address" class="form-control" placeholder="Enter BTC address">
```

**Selector options (best to worst):**
```python
# Best - ID is unique and stable
"#btc_address"

# Good - name attribute
'input[name="address"]'

# Acceptable - type + class
'input[type="text"].form-control'
```

#### For Buttons (Login, Claim, Submit)

Look for:
1. `id` attribute
2. `name` or `value` attribute (for submit buttons)
3. Button text content
4. Unique class combinations

**Example HTML:**
```html
<button id="free_play_form_button" class="btn btn-primary">ROLL!</button>
```

**Selector options:**
```python
# Best - ID
"#free_play_form_button"

# Good - text content
'button:has-text("ROLL!")'

# Acceptable - class combination
"button.btn.btn-primary"
```

#### For Balance/Timer Display Elements

Look for:
1. Elements with `id` containing "balance", "timer", "amount"
2. Specific classes or data attributes
3. Parent containers with meaningful IDs

**Example HTML:**
```html
<div class="user-balance">
    <span id="balance" data-currency="BTC">0.00001234</span> BTC
</div>
```

**Selector options:**
```python
# Best - direct ID
"#balance"

# Good - data attribute
'span[data-currency="BTC"]'

# Acceptable - class + context
".user-balance span"
```

### Step 4: Test the Selector in DevTools Console

In the browser console, test your selector:

```javascript
// CSS selector
document.querySelector('#balance')
document.querySelectorAll('input[name="email"]')

// Should return the element if selector is correct
// If it returns null, the selector doesn't match
```

For Playwright locators (what we use in the bot):

```python
# Test in Python REPL or debugging session
await page.locator('#balance').count()  # Should return 1 if found
await page.locator('input[name="email"]').is_visible()  # Should return True
```

---

## Testing Selector Changes

### Method 1: Single Faucet Test (Recommended)

Run just the faucet you're testing on the Azure VM:

```bash
# SSH to the VM
ssh azureuser@4.155.230.212

# Navigate to cryptobot directory
cd ~/Repositories/cryptobot

# Pull latest changes if you've pushed
git pull origin master

# Run single faucet in headless mode with once flag
HEADLESS=true python main.py --single freebitcoin --once
```

Watch the logs for:
- Successful login confirmation
- Balance extraction success
- Timer extraction success
- Claim completion

### Method 2: Local Testing with Visible Browser

On your local dev machine (NOT recommended for production testing):

```bash
# Run with visible browser to see what's happening
HEADLESS=false python main.py --single freebitcoin --once
```

**Note:** This only works on Linux VM. Windows cannot run Camoufox browser tests.

### Method 3: Unit Test (For Selector Validation)

Create a minimal test script:

```python
# test_selectors.py
import asyncio
from playwright.async_api import async_playwright

async def test_freebitcoin_selectors():
    async with async_playwright() as p:
        browser = await p.firefox.launch(headless=False)
        page = await browser.new_page()
        
        await page.goto("https://freebitco.in")
        
        # Test each selector
        email_field = page.locator('#login_form_btc_address')
        assert await email_field.count() > 0, "Email field not found"
        
        password_field = page.locator('#login_form_password')
        assert await password_field.count() > 0, "Password field not found"
        
        login_button = page.locator('#login_button')
        assert await login_button.count() > 0, "Login button not found"
        
        print("✓ All selectors found!")
        
        await browser.close()

asyncio.run(test_freebitcoin_selectors())
```

Run on the VM:
```bash
python test_selectors.py
```

---

## Best Practices for Fallback Selectors

### Use Playwright's Flexible Locators

Playwright provides powerful built-in fallback mechanisms:

```python
# Single selector with multiple fallbacks using comma
email_field = page.locator(
    '#login_form_btc_address, '
    'input[name="btc_address"], '
    'input[type="text"][placeholder*="address"]'
).first

# Check which strategy worked
if await email_field.count() > 0:
    await email_field.fill(email)
```

### Create Multi-Strategy Selectors in Your Faucet Bot

```python
async def _get_email_field(self):
    """Get email field with multiple fallback strategies."""
    # Try ID first (most stable)
    locator = self.page.locator('#login_form_btc_address')
    if await locator.count() > 0:
        return locator.first
    
    # Fallback to name attribute
    locator = self.page.locator('input[name="btc_address"]')
    if await locator.count() > 0:
        return locator.first
    
    # Fallback to type + placeholder (least stable)
    locator = self.page.locator('input[type="text"][placeholder*="address"]')
    if await locator.count() > 0:
        return locator.first
    
    raise Exception("Email field not found with any selector strategy")
```

### Use Data Attributes When Available

Modern sites often use `data-*` attributes:

```python
# More stable than classes which change frequently
claim_button = page.locator('[data-action="claim"]')
balance_display = page.locator('[data-testid="balance"]')
```

### Avoid Overly Specific Selectors

❌ **Bad** - Too specific, breaks easily:
```python
"div.container > div.row > div.col-md-6 > form > div.form-group:nth-child(1) > input"
```

✅ **Good** - Specific enough but flexible:
```python
"form input[type='email']"
"#login_form input[name='email']"
```

### Account for Dynamic Content

Some elements load asynchronously:

```python
# Wait for element before interacting
await page.wait_for_selector('#balance', state='visible', timeout=10000)

# Or use Playwright's auto-waiting
balance = await page.locator('#balance').text_content()  # Waits automatically
```

---

## Common Selector Patterns

### Login Forms

```python
# Email/Username field patterns
email_selectors = [
    '#email', '#username', '#login_email',
    'input[name="email"]', 'input[name="username"]',
    'input[type="email"]',
    'input[placeholder*="email" i]',  # Case-insensitive
]

# Password field patterns
password_selectors = [
    '#password', '#login_password',
    'input[name="password"]',
    'input[type="password"]',
]

# Login button patterns
login_button_selectors = [
    '#login_button', '#submit',
    'button[type="submit"]',
    'button:has-text("Login")',
    'button:has-text("Sign In")',
    'input[type="submit"][value*="Login"]',
]
```

### Claim/Faucet Buttons

```python
claim_button_selectors = [
    '#free_play_form_button',
    'button:has-text("ROLL")',
    'button:has-text("Claim")',
    'button.claim-button',
    '[data-action="claim"]',
]
```

### Balance Display

```python
balance_selectors = [
    '#balance',
    '.user-balance',
    '[data-testid="balance"]',
    'span:has-text("Balance:")',
]
```

### Timer/Countdown

```python
timer_selectors = [
    '#time_remaining',
    '.countdown-timer',
    '[data-timer]',
    'span:has-text("Next claim in")',
]
```

---

## Troubleshooting Tips

### Selector Works in Browser But Not in Bot

**Problem:** Selector works in DevTools but fails in Playwright.

**Solutions:**

1. **Wait for element to load**
   ```python
   await page.wait_for_selector('#element', state='visible', timeout=15000)
   ```

2. **Check for iframes**
   ```python
   # If element is in an iframe
   frame = page.frame_locator('iframe[name="login_frame"]')
   email = frame.locator('#email')
   ```

3. **Verify element is actually visible (not `display: none`)**
   ```python
   is_visible = await page.locator('#element').is_visible()
   logger.debug(f"Element visible: {is_visible}")
   ```

### Multiple Elements Match Selector

**Problem:** `count() > 1` when you expected one element.

**Solutions:**

1. **Use `.first` or `.nth(index)`**
   ```python
   button = page.locator('button.claim').first
   ```

2. **Make selector more specific**
   ```python
   # Add parent context
   button = page.locator('#faucet-container button.claim')
   ```

### Element Changes After Page Interaction

**Problem:** Selector works initially but fails after clicking/navigating.

**Solutions:**

1. **Wait for navigation to complete**
   ```python
   async with page.expect_navigation():
       await page.click('#submit')
   ```

2. **Wait for specific element to appear after action**
   ```python
   await page.click('#claim')
   await page.wait_for_selector('.success-message', state='visible')
   ```

### Cloudflare/Anti-Bot Interference

**Problem:** Selectors work but Cloudflare blocks requests.

**Solutions:**

1. **Ensure proper browser stealth setup** (already configured in BrowserManager)
2. **Add longer timeouts for Cloudflare challenges**
   ```python
   await page.goto(url, timeout=90000)  # 90 seconds
   await self.handle_cloudflare()  # Built-in helper
   ```

3. **Use residential proxies** (configured in ProxyManager)

---

## Example: Fixing FreeBitcoin Login Selectors

Let's walk through a complete example of updating FreeBitcoin selectors:

### 1. Identify the Problem

```
[FreeBitcoin] Error: Timeout waiting for selector '#login_form_btc_address'
```

### 2. Inspect the Site

1. Go to `https://freebitco.in`
2. Open DevTools (F12)
3. Use Element Picker on the email field
4. Find the HTML:

```html
<input type="text" id="btc_login_address" name="login_address" class="form-control">
```

**The ID changed from `login_form_btc_address` to `btc_login_address`!**

### 3. Update the Code

In `faucets/freebitcoin.py`, find the login method:

```python
async def login(self) -> bool:
    # OLD - Broken
    # email_field = self.page.locator('#login_form_btc_address')
    
    # NEW - Updated with fallbacks
    email_field = self.page.locator(
        '#btc_login_address, '          # New primary selector
        '#login_form_btc_address, '     # Old selector (might come back)
        'input[name="login_address"]'   # Fallback
    ).first
```

### 4. Test the Fix

```bash
ssh azureuser@4.155.230.212
cd ~/Repositories/cryptobot
git pull origin master
HEADLESS=true python main.py --single freebitcoin --once
```

### 5. Verify Success

Check logs for:
```
[FreeBitcoin] Login successful
[FreeBitcoin] Balance: 0.00001234 BTC
```

---

## When to Update vs When to Rewrite

### Update Selectors If:
- ✅ Only IDs/classes changed
- ✅ Element structure is similar
- ✅ Core logic still works

### Rewrite the Bot If:
- ❌ Complete site redesign
- ❌ New anti-bot measures (new captcha type, etc.)
- ❌ Fundamental workflow changes (e.g., faucet now requires 2FA)

---

## Quick Reference Card

### Browser DevTools Shortcuts
| Action | Chrome/Edge | Firefox |
|--------|-------------|---------|
| Open DevTools | F12 or Ctrl+Shift+I | F12 or Ctrl+Shift+I |
| Element Picker | Ctrl+Shift+C | Ctrl+Shift+C |
| Console | Ctrl+Shift+J | Ctrl+Shift+K |

### Selector Priority (Best to Worst)
1. 🥇 `id` attribute: `#unique_id`
2. 🥈 `data-*` attribute: `[data-testid="value"]`
3. 🥉 `name` attribute: `[name="field_name"]`
4. 👍 Unique class: `.unique-class`
5. 👎 Generic path: `div > span.class`

### Testing Commands
```bash
# Single faucet test on VM
HEADLESS=true python main.py --single <faucet_name> --once

# Check logs
tail -f ~/Repositories/cryptobot/logs/faucet_bot.log

# Verify service after deploy
sudo systemctl status faucet_worker
```

---

## Resources

- [Playwright Selectors Documentation](https://playwright.dev/python/docs/selectors)
- [CSS Selectors Reference](https://developer.mozilla.org/en-US/docs/Web/CSS/CSS_Selectors)
- [XPath Cheatsheet](https://devhints.io/xpath)

---

**Last Updated:** 2026-02-09  
**Maintained by:** Cryptobot Gen 3.0 Team
