# Monitoring Dashboard - Quick Reference

## Commands

```bash
# Basic Usage
python monitor.py                    # Show 24h metrics
python monitor.py --show-all         # Include inactive faucets
python monitor.py --alerts-only      # Only show alerts

# Time Periods
python monitor.py --period 24        # 24 hours (default)
python monitor.py --period 168       # 7 days
python monitor.py --period 720       # 30 days

# Live Mode
python monitor.py --live             # Auto-refresh every 30s
python monitor.py --live --refresh 10  # Custom refresh interval

# Testing
python test_monitoring.py            # Test with current data
```

## Key Metrics

| Metric | Formula | Good Value |
|--------|---------|------------|
| Success Rate | (successful / total) × 100 | >80% |
| ROI | (earnings - costs) / costs × 100 | >0% |
| Health Status | Last success < 24h | ✅ |
| Avg Claim Time | total_time / successful_claims | <60s |

## Alert Severity

| Level | Icon | Meaning | Action |
|-------|------|---------|--------|
| HIGH | 🔴 | No success >24h | Investigate immediately |
| MEDIUM | 🟡 | Success rate <40% | Review selectors/logic |
| LOW | 🟢 | Negative ROI | Consider disabling |

## Dashboard Components

### Summary Panel
- Total/healthy/unhealthy faucets
- Farm-wide earnings, costs, ROI
- Overall success rate
- Active alert count

### Faucet Table
- Per-faucet status indicators
- Color-coded success rates
- Last success timestamp
- Average claim time
- Net profit/loss

### Alerts Panel
- Severity-sorted alerts
- Actionable messages
- Faucet-specific issues

## Files

| File | Purpose |
|------|---------|
| `core/monitoring.py` | Core monitoring logic |
| `monitor.py` | CLI entry point |
| `config/monitoring_state.json` | Cached metrics |
| `earnings_analytics.json` | Source data |
| `docs/MONITORING.md` | Full documentation |

## Integration Example

```python
from core.monitoring import get_monitor

# Get monitor instance
monitor = get_monitor()

# Update from analytics
monitor.update_from_analytics()

# Get summary
stats = monitor.get_summary_stats()
print(f"Success rate: {stats['overall_success_rate']:.1f}%")

# Check alerts
alerts = monitor.check_alerts()
for alert in alerts:
    if alert['severity'] == 'high':
        print(f"⚠️ {alert['message']}")
```

## Troubleshooting

**No data showing?**
- Check `earnings_analytics.json` exists
- Run bot to generate claim data
- Delete `config/monitoring_state.json` to rebuild cache

**Metrics seem wrong?**
- Verify analytics file has valid JSON
- Check for test data contamination
- Review alert thresholds in `core/monitoring.py`

**Live mode not updating?**
- Ensure bot is running and creating new claims
- Check refresh interval setting
- Verify file permissions on analytics file

## Next Steps

See [docs/MONITORING.md](../MONITORING.md) for:
- Detailed API documentation
- Configuration options
- Advanced usage examples
- Contributing guidelines
