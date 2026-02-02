# Monitoring Dashboard - Visual Guide

## Overview

The Cryptobot Monitoring Dashboard provides real-time visibility into your faucet farm's health and performance through a rich terminal interface.

## Dashboard Layout

```
╔════════════════════════════════════════════════════════════════════════╗
║                  Cryptobot Monitoring Dashboard                        ║
║              Period: Last 24h | Updated: 2026-01-31 09:50:21           ║
╚════════════════════════════════════════════════════════════════════════╝

┌────────────────────────────── 📊 Farm Summary ─────────────────────────┐
│                                                                         │
│  Faucets: 7 healthy / 4 unhealthy / 11 total                          │
│  Earnings: $0.8870                                                     │
│  Costs: $0.0600                                                        │
│  Net Profit: $0.8270 (1378.3% ROI)                                    │
│  Claims: 66/114 (57.9% success)                                       │
│  Active Alerts: 12                                                     │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────── 🔔 Alerts (3) ──────────────────────────┐
│                                                                         │
│  🔴 firefaucet: No successful claim in 173.3 hours                     │
│  🟡 FreeBitcoin: Success rate only 33.3%                               │
│  🟢 cointiply: Negative ROI ($-0.0020)                                 │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘

┌─────────────────── 🚰 Faucet Health Status ────────────────────────────┐
│                                                                         │
│  Faucet      │ Status │ Success │ Claims  │ Last      │ Avg   │ Net   │
│              │        │ Rate    │         │ Success   │ Time  │ Profit│
│ ─────────────┼────────┼─────────┼─────────┼───────────┼───────┼───────│
│  firefaucet  │   ✅   │  85.7%  │  12/14  │  2.3h ago │ 42s   │ $0.12 │
│  freebitcoin │   ⚠️   │  33.3%  │   2/6   │ 18.5h ago │ 67s   │ $0.01 │
│  cointiply   │   ❌   │   0.0%  │   0/5   │   Never   │  N/A  │ -$0.02│
│  tronpick    │   ✅   │  90.0%  │   9/10  │  1.2h ago │ 38s   │ $0.08 │
│  ...         │  ...   │  ...    │  ...    │   ...     │ ...   │  ...  │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
```

## Color Coding

### Status Indicators

| Icon | Status | Meaning |
|------|--------|---------|
| ✅ | Healthy | Successful claim within last 24 hours |
| ⚠️ | Warning | Last success 1-7 days ago |
| ❌ | Unhealthy | No success in 7+ days or never |

### Success Rate Colors

| Color | Range | Visual |
|-------|-------|--------|
| 🟢 Green | ≥80% | Excellent performance |
| 🟡 Yellow | 50-79% | Moderate performance |
| 🔴 Red | <50% | Poor performance |

### Alert Severity

| Icon | Level | Description |
|------|-------|-------------|
| 🔴 | HIGH | Requires immediate attention |
| 🟡 | MEDIUM | Should investigate soon |
| 🟢 | LOW | Minor issue, monitor |

### Profit Colors

| Color | Value | Meaning |
|-------|-------|---------|
| Green | Positive | Making profit |
| Red | Negative | Losing money |

## Dashboard Modes

### 1. Static View (Default)

Shows snapshot of current metrics:
```bash
python monitor.py
```

Best for: Quick status check

### 2. Live Mode

Auto-refreshing dashboard:
```bash
python monitor.py --live
```

Display updates:
- Automatically refreshes every 30 seconds (configurable)
- Press `Ctrl+C` to exit
- Shows live timestamp

Best for: Continuous monitoring

### 3. Alerts Only

Compact view showing only active alerts:
```bash
python monitor.py --alerts-only
```

Output:
```
┌─────────────── 🔔 Alerts (3) ────────────────┐
│ 🔴 firefaucet: No success in 173.3 hours    │
│ 🟡 FreeBitcoin: Success rate only 33.3%     │
│ 🟢 cointiply: Negative ROI ($-0.0020)       │
└──────────────────────────────────────────────┘
```

Best for: Quick alert check, scripts, notifications

### 4. Show All

Include all faucets, even inactive ones:
```bash
python monitor.py --show-all
```

Best for: Complete system overview

## Time Period Views

### 24-Hour View (Default)
```bash
python monitor.py --period 24
```
Shows: Recent performance, current issues

### 7-Day View
```bash
python monitor.py --period 168
```
Shows: Weekly trends, persistent problems

### 30-Day View
```bash
python monitor.py --period 720
```
Shows: Long-term performance, overall success rate

## Reading the Metrics

### Success Rate
- **Formula**: (successful_claims / total_claims) × 100
- **Good**: >80%
- **Concerning**: <50%
- **Action**: If low, check logs for failure patterns

### Average Claim Time
- **Normal**: 30-60 seconds
- **High**: >90 seconds (may indicate captcha issues)
- **Action**: If high, check captcha solver performance

### Last Success
- **Healthy**: Within 24 hours
- **Warning**: 1-3 days ago
- **Critical**: 3+ days or "Never"
- **Action**: If old, check faucet login/selectors

### Net Profit
- **Target**: Positive value
- **ROI**: Should be >100% (earnings > costs)
- **Action**: If negative, consider disabling faucet

## Alert Interpretation

### "No successful claim in X hours"
**Severity**: HIGH 🔴

**Meaning**: Faucet hasn't worked in over 24 hours

**Possible Causes**:
- Login failing (credentials issue)
- Selectors outdated (site changed)
- Persistent Cloudflare blocks
- Account banned/disabled

**Action**: Test with `python main.py --single <faucet> --visible`

### "Success rate only X%"
**Severity**: MEDIUM 🟡

**Meaning**: More failures than successes (but some work)

**Possible Causes**:
- Intermittent captcha failures
- Proxy quality issues
- Timer extraction problems
- Rate limiting

**Action**: Review logs for failure patterns

### "Negative ROI"
**Severity**: LOW 🟢

**Meaning**: Costs exceed earnings

**Possible Causes**:
- Low-paying faucet
- High captcha costs
- Frequent retries needed

**Action**: Consider disabling or optimizing

## Best Practices

### Regular Checks
- Run `monitor.py` daily
- Use `--alerts-only` for quick status
- Check full dashboard weekly

### Live Monitoring
- Use live mode during active troubleshooting
- Set refresh to 10s for real-time debugging
- Normal monitoring: 30-60s refresh

### Alert Response
1. **HIGH alerts**: Investigate within hours
2. **MEDIUM alerts**: Review within 1-2 days
3. **LOW alerts**: Monitor trend, act if worsening

### Performance Optimization
- Disable faucets with sustained <40% success
- Focus on faucets with positive ROI
- Use metrics to prioritize fixes

## Integration Tips

### With Main Bot
```bash
# Terminal 1: Run bot
python main.py

# Terminal 2: Monitor live
python monitor.py --live
```

### Scheduled Checks
```bash
# Cron job for daily alert email
0 8 * * * /path/to/monitor.py --alerts-only | mail -s "Faucet Alerts" you@email.com
```

### Health Checks
```bash
# Check if any alerts exist (for scripts)
python monitor.py --alerts-only | grep -q "🔴" && echo "CRITICAL ALERTS!"
```

## Troubleshooting Display

### Terminal Too Small
- Resize terminal window
- Some columns may wrap
- Minimum recommended: 120 columns × 40 rows

### Colors Not Showing
- Ensure terminal supports ANSI colors
- Windows: Use Windows Terminal or modern PowerShell
- Linux/Mac: Most terminals support by default

### Data Not Loading
- Check `earnings_analytics.json` exists
- Verify JSON is valid
- Run `python test_monitoring.py` to diagnose

## Example Workflows

### Daily Check
```bash
# Quick morning check
python monitor.py --alerts-only

# If alerts, view full dashboard
python monitor.py --show-all
```

### Troubleshooting Session
```bash
# Start live monitoring
python monitor.py --live --refresh 10

# In another terminal, test specific faucet
python main.py --single firefaucet --visible

# Watch metrics update in real-time
```

### Weekly Review
```bash
# View 7-day trends
python monitor.py --period 168 --show-all

# Export summary to file
python monitor.py --period 168 > weekly_report.txt
```

## Summary

The monitoring dashboard provides:
- **Visibility**: See all faucet health at a glance
- **Alerting**: Know immediately when something breaks
- **Analytics**: Track performance over time
- **Efficiency**: Focus on profitable faucets

Use it regularly to maintain a healthy, profitable faucet farm! 🚜💰
