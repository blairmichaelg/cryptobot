# Earnings Analytics Module

## Overview

The Earnings Analytics module tracks faucet claim performance, costs, and profitability metrics. It provides comprehensive reporting and analysis to optimize bot performance.

## Data Storage

Analytics data is stored in `earnings_analytics.json` in the repository root. This file is **gitignored** and not committed to version control as it contains runtime state.

### File Structure

```json
{
  "claims": [],
  "costs": [],
  "last_updated": null
}
```

### Schema Details

#### Claims Array

Each claim record contains:

```json
{
  "timestamp": 1706072400.0,
  "faucet": "firefaucet",
  "success": true,
  "amount": 100.0,
  "currency": "BTC",
  "balance_after": 500.0
}
```

Fields:
- `timestamp` (float): Unix timestamp of the claim attempt
- `faucet` (string): Name of the faucet (e.g., "firefaucet", "cointiply")
- `success` (boolean): Whether the claim succeeded
- `amount` (float): Amount claimed in smallest unit (satoshi for BTC, etc.)
- `currency` (string): Currency code (BTC, LTC, DOGE, etc.)
- `balance_after` (float): Balance after the claim in smallest unit

#### Costs Array

Each cost record contains:

```json
{
  "timestamp": 1706072400.0,
  "type": "captcha",
  "amount_usd": 0.003,
  "faucet": "firefaucet"
}
```

Fields:
- `timestamp` (float): Unix timestamp when the cost was incurred
- `type` (string): Type of cost ("captcha", "proxy")
- `amount_usd` (float): Cost in USD
- `faucet` (string, optional): Associated faucet name

#### Metadata

- `last_updated` (float or null): Unix timestamp of last save operation

## Production vs Test Data

### Test Data Filtering

The analytics module **automatically filters out test faucets** to keep production data clean:

```python
# This will NOT be recorded in production analytics
tracker.record_claim("test_faucet", True, 100, "BTC")

# This will also be filtered out
tracker.record_claim("test_firefaucet", True, 100, "BTC")

# To explicitly allow test data (for testing)
tracker.record_claim("test_faucet", True, 100, "BTC", allow_test=True)
```

Any faucet name that:
- Equals `"test_faucet"`, or
- Starts with `"test_"`

...will be automatically skipped unless `allow_test=True` is passed.

### Clean State for Production

For production deployment, the `earnings_analytics.json` file should be initialized as:

```json
{
  "claims": [],
  "costs": [],
  "last_updated": null
}
```

This ensures:
- No test data pollutes production metrics
- Clean baseline for analytics
- Accurate profitability calculations

## Usage

### Recording Claims

```python
from core.analytics import get_tracker

tracker = get_tracker()

# Record a successful claim
tracker.record_claim(
    faucet="firefaucet",
    success=True,
    amount=100,  # satoshi
    currency="BTC",
    balance_after=500
)

# Record a failed claim
tracker.record_claim(
    faucet="cointiply",
    success=False,
    amount=0,
    currency="BTC"
)
```

### Recording Costs

```python
# Record captcha cost
tracker.record_cost(
    cost_type="captcha",
    amount_usd=0.003,
    faucet="firefaucet"
)

# Record proxy cost
tracker.record_cost(
    cost_type="proxy",
    amount_usd=0.50,
    faucet=None  # Global cost
)
```

### Analytics Queries

```python
# Get session statistics
stats = tracker.get_session_stats()
print(f"Success Rate: {stats['success_rate']:.1f}%")
print(f"Total Claims: {stats['total_claims']}")

# Get per-faucet stats (last 24 hours)
faucet_stats = tracker.get_faucet_stats(hours=24)
for faucet, data in faucet_stats.items():
    print(f"{faucet}: {data['success_rate']:.0f}% success")

# Calculate profitability (uses real-time crypto prices)
profit = tracker.get_profitability(hours=24)
print(f"Net Profit: ${profit['net_profit_usd']:.2f}")
print(f"ROI: {profit['roi']:.1f}%")

# Get hourly earning rates
rates = tracker.get_hourly_rate(hours=24)
for faucet, rate in rates.items():
    print(f"{faucet}: {rate:.2f} satoshi/hour")
```

### Generate Reports

```python
# Human-readable daily summary
summary = tracker.get_daily_summary()
print(summary)

# Automated comprehensive report (saved to reports/ directory)
report = tracker.generate_automated_report(save_to_file=True)
print(report)
```

## Data Retention

The module implements automatic data retention limits to prevent unbounded growth:

- **Claims**: Keeps last 2,000 records
- **Costs**: Keeps last 1,000 records
- Older records are automatically pruned during save operations

## Auto-Flush

Analytics are automatically flushed to disk:
- **Immediately** after each claim/cost recording (for data protection)
- **Every 5 minutes** if the auto-flush interval is exceeded
- Ensures minimal data loss in case of crashes

## Error Handling

The module is designed for resilience:

- **Missing file**: Automatically created with empty schema
- **Corrupted JSON**: Falls back to empty state with warning logged
- **Load failures**: Initializes with empty claims/costs arrays
- **Save failures**: Logs warning but doesn't crash the application

## Integration with Other Modules

### Dashboard Builder

The `DashboardBuilder` in `core/dashboard_builder.py` reads `earnings_analytics.json` to generate comprehensive profitability dashboards with:
- Summary metrics (earnings USD, costs, net profit, ROI)
- Per-faucet performance tables
- Monthly projections
- Cost breakdowns

### Profitability Optimizer

The `ProfitabilityOptimizer` uses analytics data to:
- Calculate dynamic job priorities
- Identify underperforming faucets
- Suggest optimizations

### Price Feed Integration

The analytics module integrates with `CryptoPriceFeed` to:
- Fetch real-time crypto prices from CoinGecko
- Convert earnings to USD
- Calculate accurate profitability metrics
- Cache prices for 5 minutes to reduce API calls

## Configuration

No configuration required. The module uses sensible defaults:

- **File location**: `{repo_root}/earnings_analytics.json`
- **Auto-flush interval**: 300 seconds (5 minutes)
- **Claims retention**: 2,000 records
- **Costs retention**: 1,000 records

## Testing

### Unit Tests

Run analytics tests:

```bash
pytest tests/test_analytics.py -v
pytest tests/test_analytics_extra.py -v
```

### Test Data Isolation

Tests use temporary files via pytest fixtures:

```python
@pytest.fixture
def temp_analytics_file(tmp_path):
    p = tmp_path / "test_analytics.json"
    with patch("core.analytics.ANALYTICS_FILE", str(p)):
        yield p
```

This ensures test data never pollutes production analytics.

## Migration from Test to Production

### Steps to Clean Test Data

1. **Stop the bot** (if running)
2. **Reset analytics file**:
   ```bash
   echo '{"claims": [], "costs": [], "last_updated": null}' > earnings_analytics.json
   ```
3. **Restart the bot**
4. Analytics will now track only production claims

### Preserving Historical Data

To backup test data before cleaning:

```bash
# Backup existing data
cp earnings_analytics.json earnings_analytics_backup_$(date +%Y%m%d).json

# Reset to clean state
echo '{"claims": [], "costs": [], "last_updated": null}' > earnings_analytics.json
```

## Best Practices

1. **Don't commit** `earnings_analytics.json` - it's gitignored for a reason
2. **Use test filtering** - never set `allow_test=True` in production code
3. **Monitor file size** - retention limits prevent unbounded growth
4. **Regular reports** - use `generate_automated_report()` for daily insights
5. **Backup important data** - though retention limits keep file manageable

## Troubleshooting

### File Not Found Errors

The module automatically creates the file on initialization. If you see errors:

1. Check file permissions on the repository directory
2. Ensure the directory is writable
3. Verify disk space is available

### Empty Analytics

If analytics appear empty:

1. Check if test data filtering is active (faucet names starting with `test_`)
2. Verify claims are being recorded with `logger.info` messages
3. Check `last_updated` timestamp to ensure saves are working

### Corrupted JSON

If the file becomes corrupted:

1. The module will automatically fall back to empty state
2. Previous data will be lost (check for backups)
3. New data will be recorded normally

### Memory Issues

If analytics are consuming too much memory:

1. Verify retention limits are being enforced (2,000 claims, 1,000 costs)
2. Check for save failures preventing pruning
3. Consider shortening the retention window if needed

## Related Documentation

- [Withdrawal Analytics](WITHDRAWAL_ANALYTICS.md) - Withdrawal tracking and optimization
- [Developer Guide](DEVELOPER_GUIDE.md) - General development guidelines
- [Profitability Monitor](profitability_monitor.md) - Profitability monitoring features

## Support

For issues or questions:
1. Check test files (`tests/test_analytics*.py`) for usage examples
2. Review inline documentation in `core/analytics.py`
3. Examine dashboard implementation in `core/dashboard_builder.py`
