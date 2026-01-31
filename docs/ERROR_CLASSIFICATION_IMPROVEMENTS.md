# Error Classification & Monitoring Improvements

**Date:** January 30, 2026  
**Status:** Implemented

## Overview
Enhanced error classification, CAPTCHA cost tracking, and multi-account support to improve profitability monitoring and operational intelligence.

## Changes Implemented

### 1. Configuration Error Classification (CONFIG_ERROR)
**Problem:** Cointiply and other faucets were being permanently disabled when they encountered fixable configuration issues (e.g., hCaptcha solver settings).

**Solution:** Added new `ErrorType.CONFIG_ERROR` to distinguish configuration issues from permanent credential failures.

**Impact:**
- Configuration errors are now retryable with 30-minute cooldown instead of permanent account disable
- Prevents false positives where accounts are disabled due to fixable issues
- Does not trip circuit breaker (treated as retryable error)

**Detection Keywords:**
- `hcaptcha`, `recaptcha`, `turnstile`
- `captcha config`, `solver config`, `api key`

**Files Modified:**
- [core/orchestrator.py](../core/orchestrator.py) - Added CONFIG_ERROR enum value
- [core/orchestrator.py](../core/orchestrator.py) - Updated error classification logic
- [core/orchestrator.py](../core/orchestrator.py) - Added to retry delay calculation (1800s/30min)
- [core/orchestrator.py](../core/orchestrator.py) - Updated circuit breaker logic
- [faucets/base.py](../faucets/base.py) - Added to create_error_result() helper

### 2. Enhanced CAPTCHA Cost Logging
**Problem:** CAPTCHA costs ($0.0060 spent) not being tracked per faucet, making ROI analysis difficult.

**Solution:** Added detailed logging of CAPTCHA costs per successful claim.

**Features:**
- Logs cost per claim: `💰 CAPTCHA Cost for {faucet}: ${cost} | Earned: {amount} | Balance: {balance}`
- Tracks solver statistics per provider
- Enables profitability analysis: cost vs earnings

**Files Modified:**
- [core/orchestrator.py](../core/orchestrator.py) - Added CAPTCHA cost logging in job success handler

### 3. Multi-Account Usage Tracking
**Problem:** All jobs currently using same account (blazefoley97), no visibility into account distribution.

**Solution:** Added account usage tracking dictionary to monitor active accounts.

**Features:**
- Tracks which accounts are actively claiming
- Records faucet, last active time, status, and proxy per account
- Enhanced heartbeat file with account info
- Foundation for future concurrent multi-account support

**Heartbeat Format:**
```
{timestamp}
{queue_size} jobs
{running_count} running
Accounts: firefaucet:blazefoley97, cointiply:user2, ...
```

**Files Modified:**
- [core/orchestrator.py](../core/orchestrator.py) - Added account_usage dictionary
- [core/orchestrator.py](../core/orchestrator.py) - Track account usage in job wrapper
- [core/orchestrator.py](../core/orchestrator.py) - Enhanced heartbeat file

### 4. Helper Method for Error Classification
**Problem:** Faucet implementations inconsistently set error_type in ClaimResult.

**Solution:** Added `create_error_result()` helper method to FaucetBot base class.

**Usage Example:**
```python
# Old way (inconsistent):
return ClaimResult(success=False, status="hCaptcha failed", next_claim_minutes=30)

# New way (auto-classifies):
return self.create_error_result(
    status="hCaptcha configuration error",
    next_claim_minutes=30
)
# Automatically sets error_type=ErrorType.CONFIG_ERROR
```

**Features:**
- Automatic error type classification from status message
- Manual override via force_error_type parameter
- Consistent error handling across all faucets

**Files Modified:**
- [faucets/base.py](../faucets/base.py) - Added create_error_result() method

## Error Type Summary

| Error Type | Retry Delay | Circuit Breaker | Use Case |
|------------|-------------|-----------------|----------|
| TRANSIENT | 60s (10min after retry) | No | Temporary network issues |
| RATE_LIMIT | 600s (1hr exponential) | Yes | 429 errors, Cloudflare |
| PROXY_ISSUE | 300s (30min) | After 3x | Proxy detected/blocked |
| CONFIG_ERROR | **1800s (30min)** | **No** | **hCaptcha/solver config** |
| CAPTCHA_FAILED | 900s (15min) | Yes | CAPTCHA solve timeout |
| FAUCET_DOWN | 3600s (2hr) | Yes | 500/503 server errors |
| PERMANENT | Never retry | Yes | Banned/invalid credentials |

## Testing Recommendations

1. **Cointiply Test**: Verify CONFIG_ERROR classification works correctly
   - Check logs for "Config error (hCaptcha/solver)" message
   - Confirm 30-minute retry instead of permanent disable

2. **CAPTCHA Cost Tracking**: Monitor logs for cost per claim
   - Look for `💰 CAPTCHA Cost` log entries
   - Compare costs vs earnings

3. **Multi-Account**: Check heartbeat file for account distribution
   - File: `logs/heartbeat.txt` or `/tmp/cryptobot_heartbeat`
   - Verify "Accounts:" line shows active accounts

## Future Enhancements

1. **Multi-Account Rotation**: Use account_usage tracking to distribute claims across multiple accounts
2. **Cost/Benefit Analytics**: Automated profitability reports per faucet
3. **Smart Account Selection**: Route high-value faucets to premium accounts
4. **Budget Auto-Adjustment**: Reduce CAPTCHA spend on unprofitable faucets

## Migration Notes

**For Existing Faucet Implementations:**
- No breaking changes - existing code continues to work
- Recommended: Use `create_error_result()` for new error returns
- Optional: Update existing error returns to use helper method

**For Monitoring/Analytics:**
- Heartbeat file format changed (added Accounts line)
- Check parsing scripts if reading heartbeat programmatically

## Related Files
- [core/orchestrator.py](../core/orchestrator.py) - Main scheduler with error handling
- [faucets/base.py](../faucets/base.py) - Base class with error helpers
- [solvers/captcha.py](../solvers/captcha.py) - CAPTCHA cost tracking
- [docs/DEVELOPER_GUIDE.md](DEVELOPER_GUIDE.md) - Overall architecture
