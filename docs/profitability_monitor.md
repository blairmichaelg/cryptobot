# Profitability Monitor

Automated profitability monitoring script for the CryptoBot.

## Features

- **Earnings Tracking**: Reads earnings data from `earnings_analytics.json`
- **Cost Calculation**: Calculates captcha and proxy costs
- **2Captcha Integration**: Fetches real-time API balance to track captcha spending
- **ROI Monitoring**: Calculates Return on Investment (ROI) percentage
- **Alert System**: Logs warnings when ROI drops below 50% threshold
- **Report Generation**: Saves detailed profitability reports to JSON

## Usage

### Manual Execution

```bash
python scripts/profitability_monitor.py
```

### Exit Codes
- `0`: Profitability check passed (ROI >= 50%)
- `1`: Alert triggered (ROI < 50%)
- `2`: Error during execution

### Automated Monitoring (Cron)

For hourly checks, add to crontab:

```bash
# Run profitability check every hour
0 * * * * cd /path/to/cryptobot && python scripts/profitability_monitor.py >> logs/profitability.log 2>&1
```

For custom intervals:

```bash
# Every 6 hours
0 */6 * * * cd /path/to/cryptobot && python scripts/profitability_monitor.py

# Twice daily (9 AM and 9 PM)
0 9,21 * * * cd /path/to/cryptobot && python scripts/profitability_monitor.py
```

## Configuration

The script uses settings from `core/config.py`:

- `twocaptcha_api_key`: Your 2Captcha API key (optional, will estimate costs if not provided)
- No additional configuration required

## Output

### Console Output

```
============================================================
CRYPTOBOT PROFITABILITY MONITOR
============================================================
2Captcha balance: $5.25
Total earnings (last 24h): 0.00015000 across 2 currencies
Estimated captcha costs: $0.15
Estimated proxy costs: $0.03
✅ ROI is healthy: 75.0% (threshold: 50.0%)
   Net profit: $0.12
📄 Profitability report saved to profitability_report.json
============================================================
```

### Alert Example

When ROI drops below threshold:

```
⚠️  PROFITABILITY ALERT: ROI is 30.0%, below threshold of 50.0%
   Net profit: -$0.50
   Earnings: $1.00
   Costs: $1.50
   - Captcha costs: $1.20
   - Proxy costs: $0.30
```

### JSON Report

Generated at `profitability_report.json`:

```json
{
  "timestamp": "2026-01-20T09:34:06.970528",
  "period_hours": 24,
  "earnings_usd": 1.50,
  "earnings_by_currency": {
    "BTC": 100.0,
    "LTC": 50.0
  },
  "costs": {
    "captcha_cost": 0.50,
    "proxy_cost": 0.15,
    "total_cost": 0.65
  },
  "net_profit": 0.85,
  "roi_percentage": 130.77,
  "captcha_balance": 5.25
}
```

## Cost Estimation

### Captcha Costs
- **With API Key**: Calculated from actual 2Captcha balance changes
- **Without API Key**: Estimated at $0.003 per claim

### Proxy Costs
- Estimated at $0.001 per claim (based on typical residential proxy pricing)

## Customization

### Adjust ROI Threshold

Edit `scripts/profitability_monitor.py`:

```python
# Change ROI threshold (default 50%)
ROI_THRESHOLD = 75.0  # Alert if ROI drops below 75%
```

### Custom Time Period

```bash
# Check profitability for last 48 hours
python scripts/profitability_monitor.py --hours 48  # (requires code modification)
```

## Testing

Run the test suite:

```bash
pytest tests/test_profitability_monitor.py -v
```

## Integration

The profitability monitor can be integrated with:

- **Email Alerts**: Add email sending functionality when alerts trigger
- **Slack/Discord**: Post alerts to messaging platforms
- **Dashboard**: Display metrics in a web dashboard
- **Auto-Scaling**: Reduce bot activity when profitability drops

## Troubleshooting

### "No 2Captcha API key configured"
- Add `TWOCAPTCHA_API_KEY` to your `.env` file
- Script will continue with cost estimation instead

### "No earnings data found"
- Ensure the bot has been running and recording claims
- Check that `earnings_analytics.json` exists and is readable

### Missing Dependencies
```bash
pip install -r requirements.txt
```

## Files Generated

- `profitability_report.json`: Latest profitability metrics
- `captcha_balance_tracking.json`: Tracks initial 2Captcha balance for cost calculation

These files are in `.gitignore` and won't be committed to the repository.
