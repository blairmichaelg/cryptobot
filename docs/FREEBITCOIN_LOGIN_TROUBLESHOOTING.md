# FreeBitcoin Login Troubleshooting Guide

## Overview
This document provides troubleshooting steps for FreeBitcoin login failures and explains the selector strategy used.

## Current Selector Strategy (Updated 2026-01)

The FreeBitcoin bot uses a fallback selector strategy to handle website changes. Multiple selectors are tried in order until one is found.

### Login Form Selectors

#### Email/Username Field
The bot tries these selectors in order:
1. `input[name='btc_address']` - FreeBitcoin often uses BTC address as login
2. `input[name='login_email_input']` - Legacy selector
3. `input[type='email']` - Standard email input
4. `input[name='email']` - Common alternative
5. `#email` - Simple ID selector
6. `#login_form_bt_address` - Specific FreeBitcoin selector
7. `form input[type='text']:first-of-type` - Generic fallback

#### Password Field
The bot tries these selectors:
1. `input[name='password']` - Standard password field
2. `input[name='login_password_input']` - Legacy selector
3. `input[type='password']` - Standard password input
4. `#password` - Simple ID selector
5. `#login_form_password` - Specific FreeBitcoin selector

#### Submit Button
The bot tries these selectors:
1. `#login_button` - Legacy selector
2. `button[type='submit']` - Standard submit button
3. `input[type='submit']` - Alternative submit
4. `button:has-text('Login')` - Button with "Login" text
5. `button:has-text('Log In')` - Alternative text
6. `button:has-text('Sign In')` - Alternative text
7. `.login-button` - Common class name
8. `#login_form_button` - Specific FreeBitcoin selector

#### Balance (Login Verification)
After login, the bot checks for these elements to verify success:
1. `#balance` - Primary balance element
2. `.balance` - Class-based selector
3. `[data-balance]` - Data attribute selector
4. `.user-balance` - Alternative class
5. `span.balance` - Specific span element

## Debugging Login Issues

### 1. Run the Debug Script

Use the provided debug script to see which selectors are found:

```bash
# Make sure you have credentials in .env
export FREEBITCOIN_USERNAME="your_email@example.com"
export FREEBITCOIN_PASSWORD="your_password"

# Run debug script in visible mode
python debug_freebitcoin_login.py
```

The script will:
- Navigate to the login page
- Try all selector combinations
- Log which selectors are found
- Show the actual HTML structure
- Keep the browser open for 30 seconds for inspection

### 2. Check Screenshots

When login fails, screenshots are automatically saved to the `logs/` directory:
- `logs/freebitcoin_login_failed_no_email_field.png` - Email field not found
- `logs/freebitcoin_login_failed_no_password_field.png` - Password field not found
- `logs/freebitcoin_login_failed_no_submit.png` - Submit button not found
- `logs/freebitcoin_login_failed.png` - General login failure
- `logs/freebitcoin_login_exception.png` - Exception during login

### 3. Review Logs

Check the logs for detailed error messages:

```bash
tail -100 logs/faucet_bot.log | grep -i freebitcoin
```

Look for messages like:
- `Could not find email/username field`
- `Could not find password field`
- `Could not find submit button`
- `Login error message: ...`

### 4. Test in Visible Mode

Run the bot in visible mode to see what's happening:

```bash
python main.py --single freebitcoin --visible --once
```

## Common Issues and Solutions

### Issue 1: Wrong Selectors
**Symptom**: "Could not find email/username field" or similar messages

**Solution**: 
1. Check the screenshots to see the actual page
2. Inspect the HTML (right-click → Inspect in the browser window)
3. Add new selectors to the fallback list in `faucets/freebitcoin.py`

### Issue 2: Cloudflare Blocking
**Symptom**: Page shows Cloudflare challenge or "Checking your browser"

**Solution**:
1. The bot has automatic Cloudflare handling via `handle_cloudflare()`
2. If it's failing, you may need to:
   - Use a different proxy
   - Wait longer for Cloudflare to complete
   - Update the Cloudflare handling logic

### Issue 3: Wrong Credentials
**Symptom**: Error message about invalid credentials

**Solution**:
1. Verify credentials in `.env`:
   ```
   FREEBITCOIN_USERNAME=your_email@example.com
   FREEBITCOIN_PASSWORD=your_password
   ```
2. Test logging in manually to verify credentials work
3. Check if FreeBitcoin requires email confirmation or other verification

### Issue 4: 2FA Required
**Symptom**: "2FA DETECTED!" message

**Solution**:
Currently, 2FA is not supported for automated login. You need to:
1. Disable 2FA on your FreeBitcoin account, OR
2. Manually complete the 2FA step when prompted

### Issue 5: CAPTCHA Issues
**Symptom**: Login fails with CAPTCHA-related errors

**Solution**:
1. Ensure you have a valid CAPTCHA solver API key in `.env`:
   ```
   TWOCAPTCHA_API_KEY=your_key_here
   # OR
   CAPSOLVER_API_KEY=your_key_here
   ```
2. Check your CAPTCHA service balance
3. The login CAPTCHA is optional - bot continues even if it fails

## Adding New Selectors

If the website changes and you need to add new selectors:

1. Open `faucets/freebitcoin.py`
2. Find the `login()` method
3. Add your new selector to the appropriate list:

```python
# Example: Adding a new email field selector
email_selectors = [
    "input[name='btc_address']",  # Existing
    "input[name='login_email_input']",  # Existing
    "input[name='your_new_selector']",  # Add your new one here
    # ... rest of selectors
]
```

4. Test the change:
```bash
python main.py --single freebitcoin --visible --once
```

## Testing Changes

After making changes to the login logic:

### 1. Run Unit Tests
```bash
pytest tests/test_freebitcoin.py -v
```

### 2. Run Integration Test
```bash
python main.py --single freebitcoin --visible --once
```

### 3. Update Documentation
If you discover new selectors or patterns, update this document!

## Technical Details

### Selector Discovery Process

The `_find_selector()` method:
1. Iterates through each selector in the provided list
2. Checks if the element exists (count > 0)
3. Checks if the element is visible
4. Returns the first matching locator
5. Returns `None` if no selector matches

This approach makes the bot resilient to website changes by automatically trying alternatives.

### Login Flow

1. Navigate to `https://freebitco.in/login`
2. Handle Cloudflare challenges
3. Close popups/cookie banners
4. Find and fill email/username field
5. Find and fill password field
6. Check for 2FA (abort if present)
7. Solve CAPTCHA if present
8. Find and click submit button
9. Wait for navigation
10. Verify login by checking for balance element

## Need Help?

If you're still having issues:

1. Collect the following information:
   - Screenshots from `logs/` directory
   - Relevant log excerpts
   - Output from debug script
   - Description of what you see vs. what you expect

2. Create an issue on GitHub with this information

## Related Files

- `faucets/freebitcoin.py` - Main bot implementation
- `tests/test_freebitcoin.py` - Unit tests
- `debug_freebitcoin_login.py` - Debug script
- `.env.example` - Credentials template
