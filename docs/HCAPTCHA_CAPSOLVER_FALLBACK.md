# hCaptcha Support via CapSolver Fallback

## Overview

This document describes the implementation of hCaptcha support for Cointiply using CapSolver as a fallback provider when 2Captcha doesn't support or fails to solve hCaptcha challenges.

## Problem

Cointiply uses hCaptcha for login and claim operations. While 2Captcha is the primary CAPTCHA solving service, it may not always support hCaptcha or may return errors like `ERROR_METHOD_CALL` when encountering captcha types it doesn't handle well.

## Solution

Implement a robust fallback mechanism that:
1. Attempts to solve hCaptcha using 2Captcha first (primary provider)
2. If 2Captcha returns specific errors (ERROR_METHOD_CALL, ERROR_ZERO_BALANCE, ERROR_NO_SLOT_AVAILABLE), automatically falls back to CapSolver
3. CapSolver then solves the hCaptcha using its HCaptchaTaskProxyLess API

## Implementation Details

### 1. Auto-Configuration of Fallback API Key

**File**: `faucets/base.py` (lines 126-138)

Added logic to automatically select the appropriate API key when a fallback provider is configured but no fallback API key is explicitly provided:

```python
# Auto-select fallback API key if provider is set but key is not
if fallback_provider and not fallback_key:
    if fallback_provider.lower() == "capsolver":
        fallback_key = getattr(settings, "capsolver_api_key", None)
    elif fallback_provider.lower() == "2captcha":
        fallback_key = getattr(settings, "twocaptcha_api_key", None)
```

**Benefits**:
- Simplifies configuration - users only need to set `CAPTCHA_FALLBACK_PROVIDER` and `CAPSOLVER_API_KEY`
- No need to manually specify `CAPTCHA_FALLBACK_API_KEY` unless using a different key
- Reduces configuration errors

### 2. Enhanced Fallback Error Triggers

**File**: `solvers/captcha.py` (lines 369-371, 907-910, 941-945)

Updated the fallback logic to trigger on additional error types:

**In solve_with_fallback method**:
```python
# If not fallback-worthy, propagate
if not any(err in error_msg.upper() for err in ["NO_SLOT", "ZERO_BALANCE", "ERROR_METHOD_CALL", "METHOD_CALL"]):
    raise
```

**In _solve_2captcha method (submit phase)**:
```python
# Raise exception for errors that should trigger fallback to CapSolver
if error_code in ["ERROR_METHOD_CALL", "ERROR_ZERO_BALANCE", "ERROR_NO_SLOT_AVAILABLE"]:
    raise Exception(f"2Captcha Error: {error_code}")
```

**In _solve_2captcha method (polling phase)**:
```python
# Raise exception for errors that should trigger fallback to CapSolver
if error_code in ["ERROR_METHOD_CALL", "ERROR_ZERO_BALANCE", "ERROR_NO_SLOT_AVAILABLE"]:
    raise Exception(f"2Captcha Error: {error_code}")
```

**Benefits**:
- ERROR_METHOD_CALL triggers fallback when 2Captcha doesn't support a captcha type
- ERROR_ZERO_BALANCE triggers fallback when 2Captcha balance is depleted
- ERROR_NO_SLOT_AVAILABLE triggers fallback when 2Captcha is overloaded
- Ensures seamless failover without manual intervention

### 3. Updated Configuration Documentation

**File**: `.env.example` (lines 6-14)

Added clear documentation for CapSolver fallback configuration:

```bash
# Captcha providers (set at least one)
TWOCAPTCHA_API_KEY=your_2captcha_key
CAPSOLVER_API_KEY=

# Captcha fallback configuration (optional)
# If 2Captcha fails or doesn't support a captcha type (e.g., hCaptcha), use CapSolver as fallback
# Set CAPTCHA_FALLBACK_PROVIDER=capsolver to enable CapSolver fallback
# The API key will be auto-selected from CAPSOLVER_API_KEY
CAPTCHA_FALLBACK_PROVIDER=
```

## Configuration

### Minimum Configuration

To enable hCaptcha support with CapSolver fallback, add to your `.env` file:

```bash
# Primary provider (2Captcha)
TWOCAPTCHA_API_KEY=your_2captcha_api_key

# CapSolver for fallback
CAPSOLVER_API_KEY=your_capsolver_api_key
CAPTCHA_FALLBACK_PROVIDER=capsolver
```

### Advanced Configuration

If you want to use different API keys for fallback:

```bash
TWOCAPTCHA_API_KEY=your_primary_key
CAPSOLVER_API_KEY=your_capsolver_key
CAPTCHA_FALLBACK_PROVIDER=capsolver
CAPTCHA_FALLBACK_API_KEY=your_different_capsolver_key  # Optional: only if using different key
```

## How It Works

### Flow Diagram

```
┌─────────────────────────────────────┐
│  Cointiply Login Page               │
│  (hCaptcha detected)                │
└──────────────┬──────────────────────┘
               │
               ▼
┌─────────────────────────────────────┐
│  CaptchaSolver.solve_captcha()      │
│  - Detects hCaptcha iframe          │
│  - Extracts sitekey                 │
└──────────────┬──────────────────────┘
               │
               ▼
┌─────────────────────────────────────┐
│  solve_with_fallback()              │
│  - Primary: 2Captcha                │
└──────────────┬──────────────────────┘
               │
               ▼
┌─────────────────────────────────────┐
│  _solve_2captcha()                  │
│  - Attempts hCaptcha solve          │
└──────────────┬──────────────────────┘
               │
         ┌─────┴─────┐
         │           │
         ▼           ▼
    Success?    ERROR_METHOD_CALL?
         │           │
         │           ▼
         │    ┌─────────────────────────────┐
         │    │  Exception raised           │
         │    │  - Caught by fallback logic │
         │    └──────────┬──────────────────┘
         │               │
         │               ▼
         │    ┌─────────────────────────────┐
         │    │  _solve_capsolver()         │
         │    │  - Uses HCaptchaTaskProxyLess
         │    │  - Solves hCaptcha          │
         │    └──────────┬──────────────────┘
         │               │
         └───────┬───────┘
                 │
                 ▼
         ┌───────────────┐
         │  Token        │
         │  Injected     │
         └───────┬───────┘
                 │
                 ▼
         ┌───────────────┐
         │  Login        │
         │  Succeeds     │
         └───────────────┘
```

### Retry Logic

1. **2Captcha Retries**: Each provider is retried up to 2 times on timeout (None return)
2. **Fallback Trigger**: Exceptions with ERROR_METHOD_CALL, ERROR_ZERO_BALANCE, or ERROR_NO_SLOT_AVAILABLE trigger immediate fallback
3. **CapSolver Attempt**: If 2Captcha fails after retries, CapSolver is tried
4. **Total Failure**: If both providers fail, solve_captcha returns False

## Testing

### Unit Tests

Comprehensive test suite in `tests/test_hcaptcha_fallback.py`:

1. **TestHCaptchaFallback**: Tests fallback triggering on various errors
   - ERROR_METHOD_CALL triggers fallback
   - ERROR_ZERO_BALANCE triggers fallback
   - Timeout retries before fallback
   - Both providers fail scenario

2. **TestHCaptchaDetection**: Tests hCaptcha iframe detection

3. **TestCapSolverHCaptchaAPI**: Tests CapSolver API integration
   - HCaptchaTaskProxyLess task type
   - Correct parameters passed

4. **TestAutoConfigFallbackAPIKey**: Tests auto-configuration logic

### Running Tests Locally

```bash
pytest tests/test_hcaptcha_fallback.py -v
```

### Testing on Azure VM

```bash
ssh azureuser@4.155.230.212
cd ~/Repositories/cryptobot

# Set environment variables
export TWOCAPTCHA_API_KEY=your_key
export CAPSOLVER_API_KEY=your_key
export CAPTCHA_FALLBACK_PROVIDER=capsolver
export COINTIPLY_USERNAME=your_email
export COINTIPLY_PASSWORD=your_password

# Run Cointiply login test
HEADLESS=true python3 test_cointiply.py
```

## Cost Optimization

### Provider Pricing (as of 2024)

- **2Captcha hCaptcha**: $0.003 per solve
- **CapSolver hCaptcha**: $0.003 per solve

Both providers have similar pricing, so fallback doesn't increase costs.

### Budget Management

The daily captcha budget (default $5.00) applies to both providers combined. The fallback ensures:

1. Maximum uptime - if one provider is down, the other takes over
2. Cost control - budget limits apply regardless of which provider is used
3. Success rate - better overall solve rate by using multiple providers

## Monitoring

### Logs

Look for these log messages to monitor fallback behavior:

```
🔑 Trying provider: 2captcha
❌ 2Captcha error: 2Captcha Error: ERROR_METHOD_CALL
🔑 Trying provider: capsolver
✅ CapSolver succeeded
```

### Statistics

Provider statistics are tracked in `solver.provider_stats`:

```python
{
    "providers": {
        "2captcha": {"solves": 45, "failures": 3, "cost": 0.15},
        "capsolver": {"solves": 3, "failures": 0, "cost": 0.009}
    },
    "primary": "2captcha",
    "fallback": "capsolver"
}
```

## Troubleshooting

### Issue: Fallback not triggering

**Symptom**: 2Captcha fails but CapSolver is never tried

**Solutions**:
1. Verify `CAPTCHA_FALLBACK_PROVIDER=capsolver` is set in `.env`
2. Verify `CAPSOLVER_API_KEY` is set and valid
3. Check logs for "Trying provider: capsolver" message
4. Ensure error is fallback-worthy (ERROR_METHOD_CALL, etc.)

### Issue: Both providers fail

**Symptom**: Login fails with "All captcha providers failed"

**Solutions**:
1. Check API key balances on both services
2. Verify API keys are correct
3. Check if services are experiencing downtime
4. Review logs for specific error messages

### Issue: Auto-configuration not working

**Symptom**: Error "No fallback API key configured"

**Solutions**:
1. Ensure `CAPSOLVER_API_KEY` is set in `.env`
2. Restart the application to reload environment variables
3. Verify `.env` file is in the correct location
4. Check for typos in environment variable names

## Future Enhancements

1. **Adaptive Routing**: Automatically choose the best provider based on historical success rates
2. **Provider Health Monitoring**: Track provider uptime and response times
3. **Cost Tracking**: Per-faucet cost attribution for better ROI analysis
4. **Additional Providers**: Support for more CAPTCHA solving services (AntiCaptcha, etc.)

## Related Files

- `faucets/base.py`: Auto-configuration logic
- `solvers/captcha.py`: Fallback mechanism and error handling
- `faucets/cointiply.py`: Cointiply bot with hCaptcha support
- `core/config.py`: Configuration schema
- `.env.example`: Configuration documentation
- `tests/test_hcaptcha_fallback.py`: Test suite

## References

- [2Captcha hCaptcha Documentation](https://2captcha.com/2captcha-api#solving_hcaptcha)
- [CapSolver hCaptcha Documentation](https://docs.capsolver.com/guide/captcha/HCaptcha.html)
- [Cointiply Login Issue #87](https://github.com/blairmichaelg/cryptobot/issues/87)
