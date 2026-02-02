# Lifecycle Logging - Quick Reference

## Common Log Analysis Commands

### View Recent Activity
```bash
# Last 50 lifecycle events
grep "[LIFECYCLE]" logs/faucet_bot.log | tail -50

# Last hour of claims
python scripts/analyze_logs.py --hours 1

# Last 24 hours (default)
python scripts/analyze_logs.py
```

### Find Specific Issues

```bash
# All login failures
grep "[LIFECYCLE] login_failed" logs/faucet_bot.log

# All claim failures
grep "[LIFECYCLE] result_record.*success=false" logs/faucet_bot.log

# Captcha failures
grep "[LIFECYCLE] captcha_solve.*success=false" logs/faucet_bot.log

# Proxy issues
grep "[LIFECYCLE].*error_type=proxy_issue" logs/faucet_bot.log

# Cloudflare/rate limits
grep "[LIFECYCLE].*error_type=rate_limit" logs/faucet_bot.log
```

### Faucet-Specific Analysis

```bash
# All FireFaucet events
grep "[LIFECYCLE].*faucet=FireFaucet" logs/faucet_bot.log

# FreeBitcoin last 7 days
python scripts/analyze_logs.py --faucet freebitcoin --hours 168

# CoinPayu failures only
python scripts/analyze_logs.py --faucet coinpayu --failures-only
```

### Performance Metrics

```bash
# Average claim times
python scripts/analyze_logs.py | grep "Avg Claim Duration"

# Captcha performance
grep "[LIFECYCLE] captcha_solve.*duration" logs/faucet_bot.log | tail -20

# Success rates per faucet
python scripts/analyze_logs.py | grep -A 20 "PER-FAUCET"
```

### Export & Automation

```bash
# Export as JSON
python scripts/analyze_logs.py --json > daily_report.json

# Weekly report
python scripts/analyze_logs.py --hours 168 --json > weekly_report.json

# Email-friendly summary
python scripts/analyze_logs.py | mail -s "Cryptobot Daily Report" user@example.com
```

## Log Fields Quick Reference

| Field | Description | Example |
|-------|-------------|---------|
| `faucet` | Faucet name | `FireFaucet` |
| `account` | Username/email | `user@example.com` |
| `timestamp` | Unix epoch | `1738368000` |
| `success` | Result status | `true` or `false` |
| `error_type` | Error classification | `proxy_issue` |
| `amount` | Claim amount | `0.00000050` |
| `balance` | Current balance | `0.00000123` |
| `proxy` | Proxy server | `http://ip:port` |
| `duration` | Time taken | `12.3s` |
| `timer_minutes` | Next claim time | `60` |

## Error Types

| Type | Meaning | Action |
|------|---------|--------|
| `transient` | Temporary network issue | Retry automatically |
| `rate_limit` | Cloudflare/rate limit | Wait & retry |
| `proxy_issue` | Proxy blocked | Rotate proxy |
| `permanent` | Account banned | Disable account |
| `faucet_down` | Server error | Wait 1+ hour |
| `captcha_failed` | Captcha timeout | Check solver balance |
| `config_error` | Bad config | Fix settings |

## Lifecycle Stages

### Happy Path
```
login_start → login_success → claim_submit_start → 
captcha_solve_start → captcha_solve → claim_submit → 
claim_verify → result_record (success=true)
```

### Failed Login
```
login_start → login_failed → claim_submit_failed → 
result_record (success=false)
```

### Failed Captcha
```
login_start → login_success → claim_submit_start → 
captcha_solve_start → captcha_solve (success=false) → 
result_record (success=false)
```

## Debugging Workflows

### "Why is success rate dropping?"
1. `python scripts/analyze_logs.py` - Check error distribution
2. `grep "[LIFECYCLE].*error_type=" logs/faucet_bot.log | tail -50` - Recent errors
3. `python scripts/analyze_logs.py --hours 168` - Weekly trend

### "Why is FireFaucet failing?"
1. `python scripts/analyze_logs.py --faucet firefaucet`
2. `grep "[LIFECYCLE].*faucet=FireFaucet" logs/faucet_bot.log | tail -100`
3. Check for specific error_type pattern

### "Are proxies working?"
1. `python scripts/analyze_logs.py | grep -A 10 "PROXY USAGE"`
2. `grep "[LIFECYCLE].*error_type=proxy_issue" logs/faucet_bot.log`
3. `grep "[LIFECYCLE] claim_submit_start" logs/faucet_bot.log | tail -20`

### "Why are captchas failing?"
1. `grep "[LIFECYCLE] captcha_solve.*success=false" logs/faucet_bot.log`
2. Check solver balance: `grep "💰 Captcha cost" logs/faucet_bot.log | tail -10`
3. `python scripts/analyze_logs.py | grep "CAPTCHA PERFORMANCE"`

---

**Keep this handy for daily monitoring!**
