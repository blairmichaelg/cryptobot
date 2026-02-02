# Security Challenge Retry - Quick Reference

## What Changed?

Previously: **Cloudflare challenge → Account permanently disabled**  
Now: **Cloudflare challenge → Retry up to 5 times → Auto-reset after 24h**

---

## Quick Commands

### Check Status
```python
from main import scheduler
status = scheduler.get_security_retry_status()
print(status)
```

### Reset All Accounts
```python
scheduler.reset_security_retries()
```

### Reset Specific Faucet
```python
scheduler.reset_security_retries("fire_faucet")
```

### Reset Specific Account
```python
scheduler.reset_security_retries("fire_faucet", "user@example.com")
```

---

## Error Types Quick Reference

| Error Type | Examples | Retryable? | Retry Delay |
|------------|----------|------------|-------------|
| **RATE_LIMIT** | Cloudflare, security check, maintenance | ✅ Yes (5x) | 10min - 2hr |
| **TRANSIENT** | Network timeout, connection error | ✅ Yes | 1min - 8min |
| **PROXY_ISSUE** | Proxy detected, VPN detected | ✅ Yes | 5min - 2hr |
| **CAPTCHA_FAILED** | CAPTCHA timeout | ✅ Yes | 15min - 1hr |
| **CONFIG_ERROR** | Invalid API key | ✅ Yes | 30min |
| **FAUCET_DOWN** | 500/503 errors | ✅ Yes | 4hr |
| **PERMANENT** | Account banned, auth failed | ❌ No | Never |

---

## Retry Limits

- **Max Retries**: 5 attempts per account per faucet
- **Auto-Reset**: After 24 hours of no challenges
- **Manual Reset**: Available anytime via `reset_security_retries()`

---

## Status Indicators

```python
{
  "fire_faucet:user@example.com": {
    "retries": 3,              # Current retry count
    "max_retries": 5,          # Limit before disable
    "status": "ACTIVE",        # ACTIVE or DISABLED
    "hours_since_last_retry": 2.5,
    "will_reset_in_hours": 21.5
  }
}
```

---

## Log Messages to Watch For

### Good Signs ✅
```
🔍 Error classified as: rate_limit for FireFaucet Claim
⚠️ Security challenge retry 2/5 for FireFaucet Claim
🔄 Resetting security retry counter (last retry was 25.3h ago)
```

### Warning Signs ⚠️
```
⚠️ Security challenge retry 4/5 for FireFaucet Claim
⚠️ Reclassifying security challenge as RATE_LIMIT instead of PERMANENT
```

### Action Required 🚨
```
❌ Security challenge retry limit exceeded (5) for FireFaucet
💡 TIP: Retry counter will reset after 24h
💡 To manually re-enable, use reset_security_retries()
```

---

## When to Reset Manually

1. **After fixing proxies** - Updated proxy pool or quality
2. **After site maintenance** - Faucet was down, now back up
3. **After stealth updates** - Changed browser fingerprinting
4. **For testing** - Want to retry immediately
5. **False positives** - Cloudflare lifted but counter still high

---

## Troubleshooting

### Account keeps getting disabled after 5 retries
- **Check**: Proxy quality (residential vs datacenter)
- **Check**: Stealth settings (browser fingerprinting)
- **Action**: Improve proxies or reduce `max_security_retries` to 3

### Counter not auto-resetting
- **Cause**: Requires 24h with NO challenges
- **Fix**: Manual reset if underlying issue fixed

### All accounts stuck at DISABLED
- **Cause**: All hit retry limit
- **Fix**: `scheduler.reset_security_retries()` then fix root cause

---

## Best Practices

1. ✅ Monitor `get_security_retry_status()` weekly
2. ✅ Reset after major changes (proxies, stealth)
3. ✅ Check logs for retry patterns
4. ✅ Don't reset if underlying issue not fixed
5. ✅ Use specific resets (faucet/account) over mass resets

---

## Full Documentation

See `docs/ERROR_CLASSIFICATION.md` for complete guide.
