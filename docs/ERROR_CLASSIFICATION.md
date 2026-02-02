# Error Classification and Recovery Guide

## Overview

The bot uses intelligent error classification to determine appropriate recovery strategies for different types of failures. This prevents permanent account disabling on temporary issues like Cloudflare challenges or site maintenance.

## Error Types

### 1. TRANSIENT (Temporary Network Issues)
**Characteristics:**
- Network timeouts
- Temporary connection failures
- Brief unavailability

**Recovery Strategy:**
- Retry immediately (first attempt)
- 5-minute delay for subsequent retries
- Exponential backoff: 1min → 2min → 4min → 8min

**Examples:**
- "Connection timeout"
- "Network error"
- "Temporary unavailable"

---

### 2. RATE_LIMIT (Challenges & Security Checks)
**Characteristics:**
- Cloudflare challenges
- DDoS protection pages
- Security verification
- Site maintenance
- "Just a moment" pages
- Rate limiting (429 errors)

**Recovery Strategy:**
- **NOT treated as permanent failure**
- Allows up to **5 retries** per account per faucet
- Retry counter resets after 24 hours
- Base delay: 10 minutes
- Exponential backoff: 10min → 20min → 40min → 80min → 2hr

**Examples:**
- "Cloudflare protection active"
- "Security check required"
- "Site maintenance / blocked"
- "DDoS protection enabled"
- "Too many requests"
- "Please wait..."

**Important:** Previously these were misclassified as PERMANENT and would disable accounts immediately. Now they trigger retry logic with limits.

---

### 3. PROXY_ISSUE (IP/Proxy Detection)
**Characteristics:**
- Proxy/VPN detection
- IP address blocked
- Datacenter IP detected
- Residential IP required

**Recovery Strategy:**
- Rotate to next healthy proxy
- Mark current proxy as "burned" (12-hour cooldown)
- 30-minute delay before retry
- Exponential backoff with proxy rotation

**Examples:**
- "Proxy detected"
- "VPN detected"
- "Unusual activity from your IP"
- "Access denied"

---

### 4. CAPTCHA_FAILED (CAPTCHA Solve Failures)
**Characteristics:**
- CAPTCHA timeout
- Invalid CAPTCHA solution
- Solver API errors

**Recovery Strategy:**
- 15-minute delay
- Try alternative solver provider
- Exponential backoff: 15min → 30min → 60min

**Examples:**
- "Captcha failed to solve"
- "CAPTCHA timeout"
- "Invalid captcha solution"

---

### 5. CONFIG_ERROR (Configuration Problems)
**Characteristics:**
- Missing API keys
- Invalid solver configuration
- hCaptcha/reCAPTCHA setup issues

**Recovery Strategy:**
- 30-minute delay
- Manual intervention usually required
- Continues retrying to allow admin to fix config

**Examples:**
- "hCaptcha API key missing"
- "Invalid solver configuration"
- "API key expired"

---

### 6. FAUCET_DOWN (Server Errors)
**Characteristics:**
- 500 Internal Server Error
- 503 Service Unavailable
- Complete site outage

**Recovery Strategy:**
- Skip for 4 hours
- Prevents wasting resources on down sites
- Circuit breaker trips after 3 consecutive 500/503 errors

**Examples:**
- "500 Internal Server Error"
- "503 Service Unavailable"
- "Site is currently down"

---

### 7. PERMANENT (True Account Issues)
**Characteristics:**
- Account banned
- Account suspended
- Invalid credentials
- Authentication failures

**Recovery Strategy:**
- **No retry** - account permanently disabled
- Requires manual intervention
- Only triggered for true permanent failures

**Examples:**
- "Account banned"
- "Account suspended"
- "Invalid credentials"
- "Authentication failed"
- "Violation of terms"

**Important:** Security challenges are **NOT** classified as PERMANENT.

---

### 8. UNKNOWN (Unclassified Errors)
**Characteristics:**
- Errors that don't match any pattern
- New/unexpected error messages

**Recovery Strategy:**
- 10-minute delay (conservative)
- Exponential backoff
- Logged for investigation

---

## Security Challenge Retry Limits

### Problem Fixed
Previously, a single Cloudflare challenge would permanently disable an account because it was misclassified as PERMANENT.

### New Behavior
1. Security challenges classified as **RATE_LIMIT**
2. Each faucet+account combination gets **5 retry attempts**
3. Retry counter **resets after 24 hours** of no challenges
4. After 5 failed retries, account is **temporarily disabled** (not permanent)
5. Manual re-enable available via `scheduler.reset_security_retries()`

### Example Flow
```
Attempt 1: Cloudflare challenge → RATE_LIMIT → Retry in 10min
Attempt 2: Still blocked → RATE_LIMIT → Retry in 20min
Attempt 3: Still blocked → RATE_LIMIT → Retry in 40min
Attempt 4: Still blocked → RATE_LIMIT → Retry in 80min
Attempt 5: Still blocked → RATE_LIMIT → Retry in 2hr
Attempt 6: Still blocked → Temporarily disabled (can be re-enabled)
```

After 24 hours with no challenges, counter resets to 0.

---

## Manual Re-Enable Mechanism

### Checking Status
```python
# Get status of all accounts
status = scheduler.get_security_retry_status()
print(status)

# Example output:
# {
#   "fire_faucet:user@example.com": {
#     "retries": 5,
#     "max_retries": 5,
#     "status": "DISABLED",
#     "hours_since_last_retry": 2.5,
#     "will_reset_in_hours": 21.5
#   }
# }
```

### Reset Retry Counters
```python
# Reset all accounts for all faucets
scheduler.reset_security_retries()

# Reset all accounts for specific faucet
scheduler.reset_security_retries("fire_faucet")

# Reset specific account
scheduler.reset_security_retries("fire_faucet", "user@example.com")
```

### When to Use
- After fixing proxy issues
- After confirming Cloudflare has lifted challenges
- After site maintenance is complete
- Testing new stealth settings

---

## Circuit Breaker System

The circuit breaker prevents wasting resources on consistently failing faucets.

### Trigger Conditions
- **PERMANENT errors**: Trips immediately
- **PROXY_ISSUE**: Trips after 3 consecutive failures
- **FAUCET_DOWN**: Trips after 3 consecutive 500/503 errors
- **Other errors**: Don't trip circuit breaker

### When Circuit Breaker Trips
- Faucet disabled for 2 hours
- All accounts for that faucet skipped
- Automatically resets on next success

### Exceptions
- **TRANSIENT errors**: Never trip circuit breaker
- **CONFIG_ERROR**: Never trip circuit breaker
- Individual security challenges: Tracked separately from circuit breaker

---

## Retry Delay Calculation

Base delays by error type:
```
TRANSIENT:       60s base
RATE_LIMIT:     600s base (10 minutes)
PROXY_ISSUE:    300s base (5 minutes)
CAPTCHA_FAILED: 900s base (15 minutes)
CONFIG_ERROR:  1800s base (30 minutes)
FAUCET_DOWN:   3600s base (1 hour)
UNKNOWN:        300s base (5 minutes)
PERMANENT:      ∞ (never retry)
```

### Exponential Backoff Formula
```
delay = min(base_delay * (2 ^ consecutive_failures) + jitter, max_delay)
```

Where:
- `consecutive_failures`: Number of failures since last success (capped at 5)
- `jitter`: Random 0-30% of base delay (prevents thundering herd)
- `max_delay`: 2 hours (7200 seconds)

### Example: RATE_LIMIT
```
Failure 1: 600s * 2^0 + jitter =  600s (~10 min)
Failure 2: 600s * 2^1 + jitter = 1200s (~20 min)
Failure 3: 600s * 2^2 + jitter = 2400s (~40 min)
Failure 4: 600s * 2^3 + jitter = 4800s (~80 min)
Failure 5: 600s * 2^4 + jitter = 7200s (2 hr, capped)
```

---

## Logs and Debugging

### Error Classification Logs
```
🔍 Error classified as: rate_limit for FireFaucet Claim
⚠️ Security challenge retry 2/5 for FireFaucet Claim
📅 Rescheduling FireFaucet Claim in 1200s with backoff (failures: 2)
```

### Security Retry Logs
```
⚠️ Reclassifying security challenge as RATE_LIMIT instead of PERMANENT for FireFaucet
⚠️ Security challenge retry 3/5 for FireFaucet Claim
💡 TIP: Retry counter will reset after 24h of no challenges
```

### Reset Logs
```
🔄 Resetting security retry counter for fire_faucet:user@example.com (last retry was 25.3h ago)
✅ Reset security retry counter for fire_faucet:user@example.com (was 5/5)
🔄 Reset 1 security retry counter(s). Accounts can now retry.
```

---

## Best Practices

### For Operators
1. Monitor `logs/faucet_bot.log` for error patterns
2. Check security retry status weekly: `scheduler.get_security_retry_status()`
3. Reset counters after resolving proxy/stealth issues
4. Don't manually mark RATE_LIMIT as PERMANENT
5. Update proxy pool if seeing consistent PROXY_ISSUE errors

### For Developers
1. Always set `error_type` in `ClaimResult` when possible
2. Use `ErrorType.RATE_LIMIT` for security challenges, not `PERMANENT`
3. Don't override orchestrator's error classification without good reason
4. Test new faucets with `--once` to verify error classification
5. Log detailed error messages for better classification

### Common Mistakes
❌ Classifying Cloudflare as PERMANENT  
✅ Classify Cloudflare as RATE_LIMIT

❌ Returning generic "Error" status  
✅ Return specific status: "Cloudflare challenge detected"

❌ Permanent disabling on first proxy detection  
✅ Rotate proxy and retry with PROXY_ISSUE

---

## Configuration

### Adjusting Retry Limits
Edit in `core/orchestrator.py`:
```python
self.max_security_retries = 5  # Number of retries before temp disable
self.security_retry_reset_hours = 24  # Hours before counter resets
```

### Adjusting Circuit Breaker
```python
self.CIRCUIT_BREAKER_THRESHOLD = 3  # Failures before circuit trips
self.CIRCUIT_BREAKER_COOLDOWN = 7200  # Seconds (2 hours)
```

### Adjusting Base Delays
Edit `base_delays` dict in `calculate_retry_delay()` method.

---

## Testing

### Test Error Classification
```bash
# Single faucet with visible browser
python main.py --single firefaucet --visible

# Check logs for classification
grep "Error classified as" logs/faucet_bot.log

# Verify retries not permanent
grep "PERMANENT" logs/faucet_bot.log
```

### Test Manual Reset
```python
# In Python REPL or test script
from core.orchestrator import JobScheduler
# ... initialize scheduler ...

# Check status before
print(scheduler.get_security_retry_status())

# Reset specific account
scheduler.reset_security_retries("fire_faucet", "user@example.com")

# Verify reset
print(scheduler.get_security_retry_status())
```

---

## Troubleshooting

### Account keeps getting disabled
**Symptom:** Account disabled after 1 Cloudflare challenge  
**Cause:** Old code classified Cloudflare as PERMANENT  
**Fix:** This is now fixed. Update to latest code. Reset existing counters with `reset_security_retries()`.

### Too many retries
**Symptom:** Bot retrying security challenges endlessly  
**Cause:** Proxy pool quality or stealth settings  
**Fix:** 
1. Check proxy health: Most proxies should be residential
2. Update stealth settings in `browser/stealth_hub.py`
3. Consider reducing `max_security_retries` to 3

### Retry counter not resetting
**Symptom:** Counter stays at 5/5 for weeks  
**Cause:** Automatic reset requires 24h with **no challenges**  
**Fix:** Manually reset with `reset_security_retries()` or fix underlying issue (proxies, stealth)

---

## Migration Notes

### Upgrading from Previous Versions
If you have existing disabled accounts from old classification:

1. Check which accounts are disabled:
   ```python
   scheduler.get_security_retry_status()
   ```

2. Reset all counters:
   ```python
   scheduler.reset_security_retries()
   ```

3. Restart bot - accounts will retry with new classification

### Backwards Compatibility
- Existing `ClaimResult.error_type` values still work
- Old PERMANENT classifications for security challenges will be auto-corrected
- Session state compatible with previous versions

---

## Summary

**Key Changes:**
1. ✅ Cloudflare/security challenges → RATE_LIMIT (not PERMANENT)
2. ✅ 5 retry limit before temporary disable
3. ✅ Auto-reset after 24 hours
4. ✅ Manual re-enable via `reset_security_retries()`
5. ✅ Better error classification in fallback logic
6. ✅ Detailed logging for debugging

**Result:**  
FireFaucet (and other faucets) no longer permanently disabled on first Cloudflare challenge!
