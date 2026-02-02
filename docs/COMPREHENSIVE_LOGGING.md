# Comprehensive Logging System

## Overview

The cryptobot farm now includes comprehensive structured logging at all claim lifecycle stages. This enables detailed tracking, debugging, and analysis of bot behavior.

## Lifecycle Stages

### 1. Login Phase
- **login_start**: Login attempt initiated
- **login_success**: Successfully logged in
- **login_failed**: Login failed with error classification

### 2. Data Extraction Phase
- **balance_check_start**: Balance extraction initiated
- **balance_check**: Balance retrieved (success/failure)
- **timer_check_start**: Timer extraction initiated
- **timer_check**: Timer retrieved (success/failure)

### 3. Claim Phase
- **claim_submit_start**: Claim process initiated
- **claim_submit**: Claim submitted to faucet
- **claim_submit_failed**: Claim submission failed
- **claim_verify**: Claim result verified
- **result_record**: Final result recorded

### 4. Captcha Phase
- **captcha_solve_start**: Captcha solving initiated
- **captcha_solve**: Captcha solved (success/failure)

## Log Format

All lifecycle logs follow this structured format:

```
[LIFECYCLE] <stage> | <key=value pairs> | timestamp=<unix_timestamp>
```

### Example Logs

```log
[LIFECYCLE] login_start | faucet=FireFaucet | account=user@example.com | timestamp=1738368000
[LIFECYCLE] login_success | faucet=FireFaucet | account=user@example.com | already_logged_in=false | timestamp=1738368015
[LIFECYCLE] balance_check | faucet=FireFaucet | balance=0.00000123 | success=true | timestamp=1738368020
[LIFECYCLE] timer_check | faucet=FireFaucet | timer_minutes=60 | timer_raw=1h 0m | success=true | timestamp=1738368022
[LIFECYCLE] claim_submit_start | faucet=FireFaucet | account=user@example.com | proxy=http://proxy.example.com:8888 | timestamp=1738368025
[LIFECYCLE] captcha_solve_start | type=turnstile | provider=2captcha | timestamp=1738368030
[LIFECYCLE] captcha_solve | type=turnstile | provider=2captcha | duration=12.3s | success=true | timestamp=1738368042
[LIFECYCLE] claim_submit | faucet=FireFaucet | account=user@example.com | timestamp=1738368045
[LIFECYCLE] claim_verify | faucet=FireFaucet | account=user@example.com | success=true | status=Claimed successfully | timestamp=1738368050
[LIFECYCLE] result_record | faucet=FireFaucet | account=user@example.com | success=true | amount=0.00000050 | balance=0.00000173 | next_claim_min=60 | error_type=none | timestamp=1738368051
```

### Failure Example

```log
[LIFECYCLE] login_start | faucet=CoinPayu | account=user@example.com | timestamp=1738368100
[LIFECYCLE] login_failed | faucet=CoinPayu | account=user@example.com | error_type=proxy_issue | timestamp=1738368120
[LIFECYCLE] claim_submit_failed | faucet=CoinPayu | account=user@example.com | reason=login_failed | error_type=proxy_issue | timestamp=1738368121
[LIFECYCLE] result_record | faucet=CoinPayu | account=user@example.com | success=false | exception=Login/Access Failed | error_type=proxy_issue | timestamp=1738368122
```

## Log Fields

### Common Fields
- **faucet**: Faucet name (e.g., "FireFaucet", "FreeBitcoin")
- **account**: Account username/email
- **timestamp**: Unix timestamp (seconds since epoch)
- **success**: "true" or "false"
- **error_type**: Error classification (see Error Types below)

### Stage-Specific Fields

#### Login
- **already_logged_in**: Whether session was already active

#### Balance/Timer Check
- **balance**: Extracted balance value
- **timer_minutes**: Timer in minutes
- **timer_raw**: Raw timer text from page
- **selector**: CSS selector used

#### Claim
- **proxy**: Proxy server used for this claim
- **amount**: Amount claimed
- **next_claim_min**: Minutes until next claim
- **status**: Status message from claim result

#### Captcha
- **type**: Captcha type (turnstile, hcaptcha, userrecaptcha, image)
- **provider**: Solver provider (2captcha, capsolver)
- **duration**: Time taken to solve (in seconds)

## Error Types

The system classifies errors into the following categories:

- **transient**: Temporary network/connection issues
- **rate_limit**: Rate limiting or Cloudflare challenges
- **proxy_issue**: Proxy detected or blocked
- **permanent**: Account banned/suspended
- **faucet_down**: Server errors (500/503)
- **captcha_failed**: Captcha solve timeout or failure
- **config_error**: Configuration issue (bad API keys, etc.)
- **unknown**: Unclassified error

## Using the Log Analyzer

The `scripts/analyze_logs.py` script parses lifecycle logs and provides insights.

### Basic Usage

```bash
# Analyze last 24 hours
python scripts/analyze_logs.py

# Analyze last 7 days
python scripts/analyze_logs.py --hours 168

# Filter by specific faucet
python scripts/analyze_logs.py --faucet firefaucet

# Show only failures
python scripts/analyze_logs.py --failures-only

# Export as JSON
python scripts/analyze_logs.py --json > analysis.json
```

### Output Example

```
============================================================
📊 CRYPTOBOT LIFECYCLE ANALYSIS
============================================================

📈 SUMMARY (24h)
   Total Claims: 42
   ✅ Successful: 28
   ❌ Failed: 14
   Success Rate: 66.7%

🔐 LOGIN PERFORMANCE
   Attempts: 45
   ✅ Successful: 38
   ❌ Failed: 7
   Success Rate: 84.4%

🔑 CAPTCHA PERFORMANCE
   ✅ Solved: 32
   ❌ Failed: 3
   Avg Duration: 14.2s

🎯 PER-FAUCET BREAKDOWN
   FireFaucet:
      Attempts: 12 | Success: 10 | Failed: 2 | Rate: 83.3%
   FreeBitcoin:
      Attempts: 8 | Success: 5 | Failed: 3 | Rate: 62.5%
   CoinPayu:
      Attempts: 10 | Success: 6 | Failed: 4 | Rate: 60.0%

⚠️  ERROR DISTRIBUTION
   proxy_issue: 7
   rate_limit: 4
   transient: 2
   captcha_failed: 1

🚧 STAGE-SPECIFIC FAILURES
   login_failed: 7
   claim_submit_failed: 6
   captcha_solve: 3

⏱️  PERFORMANCE METRICS
   Avg Claim Duration: 45.3s
   Avg Captcha Duration: 14.2s

🌐 PROXY USAGE
   http://142.93.66.75:8888: 18 events
   http://167.99.207.160:8888: 15 events
   No Proxy: 9 events
```

## Debugging with Lifecycle Logs

### Find Failed Claims

```bash
grep "\[LIFECYCLE\] result_record.*success=false" logs/faucet_bot.log
```

### Find Login Failures

```bash
grep "\[LIFECYCLE\] login_failed" logs/faucet_bot.log
```

### Find Captcha Issues

```bash
grep "\[LIFECYCLE\] captcha_solve.*success=false" logs/faucet_bot.log
```

### Track Specific Faucet

```bash
grep "\[LIFECYCLE\].*faucet=FireFaucet" logs/faucet_bot.log
```

### Find Proxy-Related Issues

```bash
grep "\[LIFECYCLE\].*error_type=proxy_issue" logs/faucet_bot.log
```

## Integration with Analytics

The lifecycle logs complement the existing analytics system:

- **Lifecycle Logs**: Detailed step-by-step execution traces
- **Analytics**: Aggregate statistics and financial metrics
- **Health Monitor**: System-wide health and uptime tracking

Together, these provide complete observability of the bot farm.

## Performance Impact

The logging system is designed to be lightweight:
- Logs are written asynchronously
- Only key lifecycle events are logged at INFO level
- Detailed data extraction logs are DEBUG level
- No performance impact on critical path operations

## Future Enhancements

Potential improvements for the logging system:

1. **Real-time Dashboard**: Stream lifecycle logs to a web dashboard
2. **Alert System**: Trigger alerts on repeated failures
3. **ML Analysis**: Train models to predict claim success based on lifecycle patterns
4. **Log Rotation**: Automatic compression and archival of old logs
5. **Distributed Tracing**: Add correlation IDs to track multi-step operations

## Troubleshooting

### No Lifecycle Logs Found

If `analyze_logs.py` returns "No lifecycle events found":

1. Check that the bot is running and making claims
2. Verify log file path is correct (default: `logs/faucet_bot.log`)
3. Ensure logging level is set to INFO or DEBUG in configuration
4. Check that recent claims have been attempted

### Incomplete Lifecycle Traces

If claim lifecycles are incomplete (missing stages):

1. Check for exceptions interrupting the flow
2. Review error_type classifications in result_record
3. Look for browser crashes (check for "Target closed" errors)
4. Verify all faucet bots call the proper base class methods

## Best Practices

1. **Monitor Daily**: Run `analyze_logs.py` daily to track trends
2. **Investigate Failures**: When success rate drops, check error_distribution
3. **Optimize Timing**: Use avg_claim_duration to identify slow faucets
4. **Proxy Health**: Monitor proxy_usage to detect dead proxies
5. **Captcha Budget**: Track captcha_solve events to manage costs

---

**Last Updated**: 2026-01-31  
**Version**: 1.0
