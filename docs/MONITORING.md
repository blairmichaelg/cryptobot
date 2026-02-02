# Cryptobot Monitoring Dashboard

Real-time monitoring and alerting system for tracking faucet farm health and performance.

## Features

### Per-Faucet Metrics
- **Success Rate**: Percentage of successful claims (24h, 7d, 30d periods)
- **Average Claim Time**: Mean time to complete a claim
- **Failure Breakdown**: Categorized failure reasons with counts
- **Last Successful Claim**: Timestamp of last successful claim
- **Profitability**: Earnings vs costs, ROI percentage
- **Health Status**: Visual indicators (✅ healthy, ⚠️ warning, ❌ unhealthy)

### Alerting System
Automatic alerts for:
- **No Success >24h**: Faucet hasn't had successful claim in 24+ hours (HIGH severity)
- **Low Success Rate**: Success rate below 40% with >5 attempts (MEDIUM severity)
- **Negative ROI**: Costs exceeding earnings (LOW severity)

### Display Options
- **CLI Dashboard**: Rich terminal interface with color-coded metrics
- **Live Mode**: Auto-refreshing dashboard (default 30s refresh)
- **Historical Periods**: View metrics for 24h, 7d (168h), or 30d (720h)
- **Show All**: Include inactive faucets in report
- **Alerts Only**: Quick view of active alerts

## Usage

### Basic Monitoring

```bash
# Show 24-hour metrics (default)
python monitor.py

# Show 7-day metrics
python monitor.py --period 168

# Show 30-day metrics
python monitor.py --period 720

# Show all faucets including inactive ones
python monitor.py --show-all
```

### Live Monitoring

```bash
# Live dashboard with auto-refresh every 30 seconds
python monitor.py --live

# Custom refresh interval (e.g., every 10 seconds)
python monitor.py --live --refresh 10
```

### Alerts Only

```bash
# Show only active alerts
python monitor.py --alerts-only
```

### Testing

```bash
# Test the dashboard with current data
python test_monitoring.py
```

## Integration with Main Bot

The monitoring system automatically tracks data from the main bot's analytics:

- **Claims Data**: Read from `earnings_analytics.json`
- **Costs Data**: Captcha and proxy costs tracked
- **Monitoring State**: Persisted to `config/monitoring_state.json`

### Enhanced Analytics Recording

The bot now records additional claim metadata:

```python
from core.analytics import get_tracker

tracker = get_tracker()

# Record claim with timing and failure reason
tracker.record_claim(
    faucet="firefaucet",
    success=False,
    amount=0.0,
    currency="BTC",
    claim_time=45.3,  # Seconds taken
    failure_reason="Cloudflare challenge timeout"
)
```

## Dashboard Components

### Summary Panel
```
┌─ 📊 Farm Summary ────────────────────────┐
│ Faucets: 7 healthy / 4 unhealthy / 11   │
│ Earnings: $0.0234                        │
│ Costs: $0.0180                           │
│ Net Profit: $0.0054 (30.0% ROI)          │
│ Claims: 45/67 (67.2% success)            │
│ Active Alerts: 2                         │
└──────────────────────────────────────────┘
```

### Faucet Health Table
```
┌─ 🚰 Faucet Health Status ────────────────────────────────────────────┐
│ Faucet       │ Status │ Success Rate │ Claims  │ Last Success │ ... │
├──────────────┼────────┼──────────────┼─────────┼──────────────┼─────┤
│ firefaucet   │   ✅   │    85.7%     │  12/14  │   2.3h ago   │ ... │
│ freebitcoin  │   ⚠️   │    33.3%     │   2/6   │  18.5h ago   │ ... │
│ cointiply    │   ❌   │     0.0%     │   0/5   │    Never     │ ... │
└──────────────────────────────────────────────────────────────────────┘
```

### Alerts Panel
```
┌─ 🔔 Alerts (2) ──────────────────────────────────────┐
│ 🔴 cointiply: No successful claim in 26.3 hours     │
│ 🟡 freebitcoin: Success rate only 33.3%             │
└──────────────────────────────────────────────────────┘
```

## File Structure

```
cryptobot/
├── core/
│   └── monitoring.py          # Core monitoring logic
├── config/
│   └── monitoring_state.json  # Persisted metrics
├── monitor.py                 # CLI entry point
└── test_monitoring.py         # Test script
```

## API Usage

### Programmatic Access

```python
from core.monitoring import FaucetMonitor, MonitoringDashboard

# Create monitor
monitor = FaucetMonitor()

# Update from analytics
monitor.update_from_analytics()

# Get summary stats
stats = monitor.get_summary_stats()
print(f"Total faucets: {stats['total_faucets']}")
print(f"Success rate: {stats['overall_success_rate']:.1f}%")

# Check alerts
alerts = monitor.check_alerts()
for alert in alerts:
    print(f"[{alert['severity']}] {alert['message']}")

# Display dashboard
dashboard = MonitoringDashboard(monitor)
dashboard.display(hours=24)
```

### Singleton Pattern

```python
from core.monitoring import get_monitor

# Get global monitor instance
monitor = get_monitor()
monitor.update_from_analytics()
```

## Configuration

### Alert Thresholds (in `core/monitoring.py`)

```python
class FaucetMonitor:
    ALERT_NO_SUCCESS_HOURS = 24      # Alert if no success in 24h
    ALERT_LOW_SUCCESS_RATE = 40.0    # Alert if <40% success
    ALERT_NEGATIVE_ROI_HOURS = 72    # Alert if negative ROI for 72h
```

### Metric Definitions

- **Healthy**: Successful claim within last 24 hours
- **Unhealthy**: No successful claim in 24+ hours
- **Success Rate**: (successful_claims / total_claims) × 100
- **ROI**: ((earnings - costs) / costs) × 100
- **Avg Claim Time**: total_claim_time / successful_claims

## Troubleshooting

### No Data Showing

**Problem**: Dashboard shows no faucets or all zeros

**Solution**:
1. Check `earnings_analytics.json` exists and has data
2. Run the bot to generate some claims data
3. Run `python test_monitoring.py` to verify setup

### Incorrect Metrics

**Problem**: Metrics don't match expected values

**Solution**:
1. Delete `config/monitoring_state.json` to reset cache
2. Run `monitor.py` to rebuild from analytics
3. Verify `earnings_analytics.json` has valid JSON

### Live Mode Not Updating

**Problem**: Dashboard not refreshing in live mode

**Solution**:
- Press Ctrl+C and restart
- Check refresh interval (default 30s)
- Verify analytics file is being updated by bot

## Integration with Auto-Withdrawal

The monitoring system integrates with the auto-withdrawal feature:

```python
from core.monitoring import get_monitor

monitor = get_monitor()
stats = monitor.get_summary_stats()

# Only withdraw if profitable
if stats['net_profit_usd'] > 0:
    # Trigger withdrawal logic
    pass
```

## Future Enhancements

Planned features:
- [ ] Web dashboard (Flask/FastAPI)
- [ ] Export to CSV/JSON
- [ ] Email/SMS alerts
- [ ] Grafana integration
- [ ] Historical trend graphs
- [ ] Per-proxy performance tracking
- [ ] Cost breakdown by captcha provider

## Contributing

When adding new metrics:

1. Update `FaucetMetrics` dataclass in `core/monitoring.py`
2. Add calculation logic in `FaucetMonitor.update_from_analytics()`
3. Update display rendering in `MonitoringDashboard`
4. Document in this README

## License

Same as parent project (cryptobot).
