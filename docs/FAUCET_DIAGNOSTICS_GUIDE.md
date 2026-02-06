# Faucet Diagnostics Tool

## Quick Start

Run the diagnostic tool to check your cryptobot setup:

```bash
python faucet_diagnostics.py
```

## What It Checks

### 1. Browser Instance Creation
- Tests that BrowserManager can be created
- Verifies no import errors or missing dependencies
- Checks headless mode configuration

### 2. Credential Configuration
- Scans for credentials for all 18 faucets
- Reports which faucets have complete credentials (username + password)
- Shows summary count

### 3. CAPTCHA Provider Configuration
- Checks for 2Captcha API key
- Checks for CapSolver API key
- Verifies fallback provider settings
- Explains what happens with current configuration

### 4. Basic Browser Navigation
- Downloads and installs Camoufox (first run only)
- Launches headless browser
- Tests navigation to https://www.google.com
- Verifies page can load successfully

## Expected Output

### ✅ Successful Setup
```
============================================================
DIAGNOSTIC SUMMARY
============================================================
Browser Instance:     ✅ PASS
Settings/Credentials: ✅ PASS
CAPTCHA Configuration:✅ PASS
Basic Navigation:     ✅ PASS

✅ All basic tests passed!
   You can proceed to test individual faucets
   Run: python main.py --single <faucet_name> --once --visible
```

### ⚠️  Missing Configuration
```
============================================================
DIAGNOSTIC SUMMARY
============================================================
Browser Instance:     ✅ PASS
Settings/Credentials: ❌ FAIL
CAPTCHA Configuration:❌ FAIL
Basic Navigation:     ✅ PASS

⚠️  Some tests failed - review the issues above
   → Configure credentials in .env file
   → Set TWOCAPTCHA_API_KEY and/or CAPSOLVER_API_KEY in .env
```

## Troubleshooting

### Browser Instance Fails
**Error**: `ModuleNotFoundError: No module named 'playwright'`

**Fix**:
```bash
pip install -r requirements.txt
```

### All Credentials Missing
**Error**: `❌ all faucets - Missing credentials`

**Fix**: Create/update `.env` file with credentials:
```bash
cp .env.example .env
# Edit .env and add your credentials
nano .env  # or vim, code, etc.
```

Required format:
```env
# Example for FreeBitcoin
FREEBITCOIN_USERNAME=your_email@example.com
FREEBITCOIN_PASSWORD=your_password

# Example for Pick.io family
LITEPICK_USERNAME=your_email@example.com
LITEPICK_PASSWORD=your_password
```

### CAPTCHA Configuration Fails
**Error**: `❌ No CAPTCHA provider configured`

**Fix**: Add at least one CAPTCHA API key to `.env`:
```env
# Option 1: 2Captcha (supports most CAPTCHAs)
TWOCAPTCHA_API_KEY=your_2captcha_key_here

# Option 2: CapSolver (better hCaptcha support)
CAPSOLVER_API_KEY=your_capsolver_key_here

# Option 3: Both (recommended - automatic fallback)
TWOCAPTCHA_API_KEY=your_2captcha_key_here
CAPSOLVER_API_KEY=your_capsolver_key_here
```

Get API keys:
- 2Captcha: https://2captcha.com
- CapSolver: https://www.capsolver.com

### Navigation Fails
**Error**: `❌ Navigation failed: Timeout`

**Fix**: 
1. Check internet connection
2. Check if behind firewall/proxy
3. Increase timeout in `core/config.py`:
   ```python
   timeout: int = 120000  # 120 seconds
   ```

## What's Next?

After diagnostics pass, test individual faucets:

```bash
# Test a single faucet with visible browser
python main.py --single firefaucet --once --visible

# Test with headless browser (production mode)
python main.py --single firefaucet --once

# Run all faucets
python main.py
```

## Faucet List

The diagnostic tool checks credentials for these 18 faucets:

### Core Faucets (7)
1. firefaucet
2. freebitcoin
3. cointiply
4. coinpayu
5. adbtc
6. faucetcrypto
7. dutchy

### Pick.io Family (11)
8. litepick (LTC)
9. tronpick (TRX)
10. dogepick (DOGE)
11. bchpick (BCH)
12. solpick (SOL)
13. tonpick (TON)
14. polygonpick (MATIC)
15. binpick (BNB)
16. dashpick (DASH)
17. ethpick (ETH)
18. usdpick (USDT)

## Advanced Usage

### Run Only Specific Tests

The diagnostic tool runs all tests by default. To modify, edit `faucet_diagnostics.py`:

```python
async def main():
    # Comment out tests you don't want to run
    browser_test = await test_browser_instance()
    # creds_results = await test_credentials(settings)  # Skip this
    # captcha_ok = await test_captcha_config(settings)  # Skip this
    nav_test = await test_basic_navigation()
```

### Add Custom Tests

Add your own diagnostic tests by creating new async functions:

```python
async def test_custom_feature():
    """Test a custom feature."""
    logger.info("Testing custom feature...")
    try:
        # Your test code here
        logger.info("✅ Custom test passed")
        return True
    except Exception as e:
        logger.error(f"❌ Custom test failed: {e}")
        return False
```

Then call it in `main()`:
```python
custom_test = await test_custom_feature()
```

## File Location

The diagnostic script is located in the repository root:
```
/home/runner/work/cryptobot/cryptobot/faucet_diagnostics.py
```

## See Also

- [FAUCET_INVESTIGATION_SUMMARY.md](FAUCET_INVESTIGATION_SUMMARY.md) - Complete investigation results
- [.env.example](.env.example) - Example environment configuration
- [README.md](README.md) - Main project documentation
- [DEBUG_SESSION_REPORT_20260206.md](DEBUG_SESSION_REPORT_20260206.md) - Original debug session
- [FAUCET_BUG_REPORT.md](FAUCET_BUG_REPORT.md) - Original bug report
