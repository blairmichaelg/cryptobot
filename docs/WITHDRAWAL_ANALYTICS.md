# WithdrawalAnalytics Module

## Overview

The WithdrawalAnalytics module provides comprehensive tracking and optimization for cryptocurrency withdrawals across faucets and wallet services. It enables data-driven decision-making to maximize profitability by analyzing fees, timing, and withdrawal methods.

## Features

### Core Capabilities
- ✅ **Transaction Tracking**: SQLite database storage for all withdrawal transactions
- ✅ **Profitability Analysis**: Calculate earnings, fees, net profit, and effective hourly rates
- ✅ **Smart Recommendations**: ML/rule-based engine for optimal withdrawal timing and methods
- ✅ **Performance Reports**: Daily, weekly, and monthly summaries with best/worst performers
- ✅ **Automatic Integration**: Seamless tracking through existing withdraw() methods

### Data Tracked
- Faucet name
- Cryptocurrency type (BTC, LTC, DOGE, etc.)
- Amount withdrawn
- Network fees and platform fees
- Timestamp
- Withdrawal method (FaucetPay vs Direct vs Wallet Daemon)
- Success/failure status
- Balance before/after withdrawal
- Transaction IDs
- Custom notes

## Installation

The module is already integrated into the cryptobot project. No additional installation is required.

## Usage

### Basic Usage

```python
from core.withdrawal_analytics import get_analytics

# Get analytics instance (singleton)
analytics = get_analytics()

# Record a withdrawal
analytics.record_withdrawal(
    faucet="FreeBitcoin",
    cryptocurrency="BTC",
    amount=0.00015,
    network_fee=0.000015,
    platform_fee=0.000005,
    withdrawal_method="faucetpay",
    status="success",
    balance_before=0.0005,
    balance_after=0.00035,
    tx_id="btc_tx_abc123"
)
```

### Calculate Profitability

```python
# Get overall metrics for last 24 hours
rates = analytics.calculate_effective_rate(hours=24)

print(f"Net Profit: {rates['net_profit']}")
print(f"Fee Percentage: {rates['fee_percentage']:.2f}%")
print(f"Hourly Rate: {rates['hourly_rate']}")

# Filter by specific faucet
btc_rates = analytics.calculate_effective_rate(
    faucet="FreeBitcoin",
    hours=168  # Last week
)

# Filter by cryptocurrency
doge_rates = analytics.calculate_effective_rate(
    cryptocurrency="DOGE",
    hours=720  # Last month
)
```

### Get Recommendations

```python
# Get withdrawal recommendation
recommendation = analytics.recommend_withdrawal_strategy(
    current_balance=0.001,
    cryptocurrency="BTC",
    faucet="FreeBitcoin"
)

print(f"Action: {recommendation['action']}")  # 'withdraw' or 'wait'
print(f"Reason: {recommendation['reason']}")
print(f"Best Method: {recommendation['optimal_method']}")
print(f"Best Timing: {recommendation['optimal_timing']}")
```

### Generate Reports

```python
# Daily report
daily_report = analytics.generate_report(period="daily")
print(daily_report)

# Weekly report for specific cryptocurrency
weekly_btc = analytics.generate_report(
    period="weekly",
    cryptocurrency="BTC"
)

# Monthly report
monthly_report = analytics.generate_report(period="monthly")
```

### Query History

```python
# Get recent withdrawals
history = analytics.get_withdrawal_history(limit=10)

for record in history:
    print(f"{record['faucet']}: {record['amount']} {record['cryptocurrency']}")

# Filter by faucet
fb_history = analytics.get_withdrawal_history(faucet="FreeBitcoin")

# Filter by cryptocurrency
btc_history = analytics.get_withdrawal_history(cryptocurrency="BTC")
```

### Per-Faucet Performance

```python
# Get performance metrics for all faucets
performance = analytics.get_faucet_performance(hours=168)  # Last week

for faucet, stats in performance.items():
    print(f"\n{faucet}:")
    print(f"  Success Rate: {stats['success_rate']:.1f}%")
    print(f"  Net Profit: {stats['net_profit']}")
    print(f"  Fee %: {stats['fee_percentage']:.2f}%")
```

## Automatic Integration

The module automatically tracks withdrawals when using the standard faucet `withdraw_wrapper()` method:

```python
# In your faucet bot
result = await bot.withdraw_wrapper(page)

# Withdrawal is automatically recorded in analytics if successful!
# No manual tracking needed.
```

## Automated Withdrawal Scheduling (New in Gen 3.0)

The JobScheduler now includes automated withdrawal scheduling that intelligently manages when and how withdrawals are executed across all faucets.

### Overview

The orchestrator automatically schedules withdrawal jobs for all supported faucets based on:
- **Earnings rate**: High-earning faucets checked more frequently (24h vs 72h)
- **Off-peak timing**: Withdrawals preferred during low-fee hours (22:00-05:00 UTC, weekends)
- **Balance thresholds**: Only withdraws when balance meets minimum threshold
- **Network fees**: Defers withdrawals during high-fee periods
- **Retry logic**: Exponential backoff (1h, 6h, 24h) with max 3 attempts

### Features

- ✅ **Automatic Scheduling**: Withdrawal jobs auto-created on scheduler startup
- ✅ **Smart Timing**: Prefers off-peak hours for lower network fees
- ✅ **Analytics Integration**: Uses earnings data to optimize scheduling frequency
- ✅ **WalletDaemon Integration**: Checks network fees before executing
- ✅ **Retry Logic**: Exponential backoff with configurable intervals
- ✅ **Failure Tracking**: Logs failed withdrawals to analytics
- ✅ **Priority Management**: Withdrawals run at low priority (don't interfere with claiming)

### Configuration

Add these settings to your `.env` or `BotSettings`:

```python
# Withdrawal Timing Strategy
prefer_off_peak_withdrawals = True  # Prefer off-peak hours for withdrawals
withdrawal_schedule = "off_peak"     # Options: immediate, off_peak, weekly_batch
off_peak_hours = [0, 1, 2, 3, 4, 5, 22, 23]  # UTC hours (low network activity)

# Retry Configuration
withdrawal_retry_intervals = [3600, 21600, 86400]  # Retry intervals: 1h, 6h, 24h
withdrawal_max_retries = 3  # Maximum retry attempts before marking as failed

# Account Profiles (required for withdrawal scheduling)
accounts = [
    AccountProfile(faucet="firefaucet", username="user1", password="pass1", enabled=True),
    AccountProfile(faucet="cointiply", username="user2", password="pass2", enabled=True),
]
```

### Usage

The scheduler automatically calls `schedule_withdrawal_jobs()` on startup. No manual intervention needed!

```python
from core.orchestrator import JobScheduler
from core.config import BotSettings

settings = BotSettings()
scheduler = JobScheduler(settings, browser_manager, proxy_manager)

# Start the scheduler - withdrawal jobs are auto-scheduled
await scheduler.scheduler_loop()
```

### Manual Scheduling (Optional)

You can also manually schedule withdrawal jobs:

```python
# Schedule withdrawal jobs for all supported faucets
await scheduler.schedule_withdrawal_jobs()

# Or execute a single withdrawal
from core.config import AccountProfile

profile = AccountProfile(faucet="firefaucet", username="user", password="pass")
result = await scheduler.execute_consolidated_withdrawal("firefaucet", profile)

if result.success:
    print(f"Withdrawal successful: {result.status}")
else:
    print(f"Withdrawal failed: {result.status}")
```

### Withdrawal Job Lifecycle

1. **Scheduling**: Jobs created on startup with 24-72h initial delay
2. **Pre-Execution Checks**:
   - Balance meets minimum threshold
   - Current time is off-peak (if enabled)
   - Network fees are acceptable (if WalletDaemon configured)
3. **Execution**: Calls faucet's `withdraw_wrapper()` method
4. **Analytics**: Logs result to WithdrawalAnalytics database
5. **Retry Logic**: On failure, reschedules with exponential backoff
6. **Completion**: Success or max retries reached

### Scheduling Strategy

The scheduler uses analytics to determine optimal withdrawal frequency:

| Earnings Rate | Check Interval | Rationale |
|---------------|---------------|-----------|
| > 100 sat/h   | 24 hours      | High earner, check daily |
| 50-100 sat/h  | 36 hours      | Medium earner, check every 1.5 days |
| < 50 sat/h    | 72 hours      | Low earner, check every 3 days |

### Off-Peak Timing

When `prefer_off_peak_withdrawals=True`, withdrawals are deferred to optimal hours:

- **Time**: 22:00-05:00 UTC (late night/early morning)
- **Days**: Weekends (Saturday, Sunday)
- **Benefit**: 20-50% lower network fees on average

### Retry Behavior

Failed withdrawals retry with exponential backoff:

| Attempt | Delay    | Cumulative |
|---------|----------|------------|
| 1       | 1 hour   | 1h         |
| 2       | 6 hours  | 7h         |
| 3       | 24 hours | 31h        |

After 3 failures, the withdrawal is marked as permanently failed and logged to analytics.

### Monitoring

Check withdrawal job status:

```python
# Get all withdrawal jobs in queue
withdrawal_jobs = [j for j in scheduler.queue if "withdraw" in j.job_type.lower()]

for job in withdrawal_jobs:
    print(f"{job.name}: Next run at {datetime.fromtimestamp(job.next_run)}")
    print(f"  Priority: {job.priority}, Retries: {job.retry_count}")
```

### Testing

Run the withdrawal scheduling tests:

```bash
pytest tests/test_orchestrator.py::TestWithdrawalScheduling -v
```

9 comprehensive tests cover:
- Job creation and scheduling
- Off-peak time detection
- Balance threshold checking
- Retry logic with exponential backoff
- Max retries enforcement
- Analytics integration

## Recommendation Engine Rules

The recommendation engine uses the following logic:

1. **Balance Threshold**: Ensures balance is at least 20x the average fee to minimize fee impact
2. **Fee Percentage**: Rejects withdrawals if estimated fee exceeds 10% of balance
3. **Off-Peak Hours**: Recommends withdrawals during 22:00-05:00 UTC for lower network fees
4. **Method Selection**: 
   - FaucetPay for amounts < 0.001 (better for micro-transactions)
   - Direct for amounts >= 0.001 (lower fees for larger amounts)

## Database Schema

```sql
CREATE TABLE withdrawals (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp REAL NOT NULL,
    faucet TEXT NOT NULL,
    cryptocurrency TEXT NOT NULL,
    amount REAL NOT NULL,
    network_fee REAL DEFAULT 0.0,
    platform_fee REAL DEFAULT 0.0,
    withdrawal_method TEXT NOT NULL,
    status TEXT NOT NULL,
    balance_before REAL DEFAULT 0.0,
    balance_after REAL DEFAULT 0.0,
    tx_id TEXT,
    notes TEXT
);

-- Indexes for performance
CREATE INDEX idx_timestamp ON withdrawals(timestamp);
CREATE INDEX idx_faucet ON withdrawals(faucet);
CREATE INDEX idx_crypto ON withdrawals(cryptocurrency);
```

## Metrics Calculated

### Overall Metrics
- **Total Earned**: Sum of all successful withdrawal amounts
- **Total Fees**: Sum of network and platform fees
- **Net Profit**: Total earned minus total fees
- **Hourly Rate**: Net profit divided by time period
- **Fee Percentage**: Fees as percentage of total earned

### Per-Faucet Metrics
- **Total Withdrawals**: Count of all withdrawal attempts
- **Successful Withdrawals**: Count of successful withdrawals
- **Success Rate**: Percentage of successful withdrawals
- **Total Earned**: Sum of amounts for this faucet
- **Net Profit**: Earnings minus fees for this faucet
- **Average Fee**: Mean fee per withdrawal
- **Fee Percentage**: Fees as percentage of earnings

## Demo Script

Run the demo to see analytics in action:

```bash
python demo_withdrawal_analytics.py
```

## Testing

The module includes comprehensive test coverage:

```bash
# Run unit tests (22 tests)
pytest tests/test_withdrawal_analytics.py -v

# Run integration tests (5 tests)
pytest tests/test_withdrawal_analytics_integration.py -v

# Run all analytics tests
pytest tests/test_withdrawal_analytics*.py -v
```

## Best Practices

1. **Always use the wrapper methods**: The `withdraw_wrapper()` handles analytics automatically
2. **Check recommendations before manual withdrawals**: Use `recommend_withdrawal_strategy()` for optimal timing
3. **Review reports regularly**: Generate weekly/monthly reports to identify trends
4. **Monitor fee percentages**: High fees indicate need to accumulate more before withdrawing
5. **Use off-peak hours**: Network fees are typically lower during 22:00-05:00 UTC

## Error Handling

The module is designed to fail gracefully:
- Analytics failures don't break withdrawal flows
- Database errors are logged but don't crash the application
- Missing data defaults to sensible values
- All exceptions are caught and logged

## Performance Considerations

- Database uses indexes on timestamp, faucet, and cryptocurrency for fast queries
- Only keeps most recent 1000 records in memory (older data persists in DB)
- Singleton pattern ensures single database connection
- Efficient SQL queries with proper WHERE clauses

## Future Enhancements

Potential improvements for future versions:
- Machine learning model for fee prediction
- Integration with external price APIs for USD value tracking
- ~~Automated withdrawal scheduling based on recommendations~~ ✅ **Implemented in Gen 3.0**
- Batch withdrawal optimization across multiple faucets
- Email/webhook notifications for optimal withdrawal windows
- Export to CSV/JSON for external analysis
- Gas price prediction for ERC-20 tokens
- Multi-signature wallet support

## API Reference

### Class: `WithdrawalAnalytics`

#### `record_withdrawal(faucet, cryptocurrency, amount, ...)`
Records a withdrawal transaction to the database.

**Parameters:**
- `faucet` (str): Name of the faucet
- `cryptocurrency` (str): Crypto symbol (BTC, LTC, etc.)
- `amount` (float): Amount withdrawn
- `network_fee` (float): Network transaction fee
- `platform_fee` (float): Platform/service fee
- `withdrawal_method` (str): Method used (faucetpay, direct, wallet_daemon)
- `status` (str): Transaction status (success, failed, pending)
- `balance_before` (float): Balance before withdrawal
- `balance_after` (float): Balance after withdrawal
- `tx_id` (str, optional): Blockchain transaction ID
- `notes` (str, optional): Additional notes

**Returns:** int - Database record ID

#### `calculate_effective_rate(faucet=None, cryptocurrency=None, hours=24)`
Calculates net earning rate after fees.

**Returns:** Dict with keys:
- `total_earned`: Total amount withdrawn
- `total_fees`: Total fees paid
- `net_profit`: Earned minus fees
- `hourly_rate`: Profit per hour
- `fee_percentage`: Fees as % of earnings

#### `recommend_withdrawal_strategy(current_balance, cryptocurrency, faucet)`
Recommends optimal withdrawal strategy based on historical data.

**Returns:** Dict with keys:
- `action`: 'withdraw' or 'wait'
- `reason`: Explanation for recommendation
- `optimal_method`: Best withdrawal method
- `estimated_fee`: Expected fee amount
- `optimal_timing`: Best time to withdraw

#### `generate_report(period='daily', cryptocurrency=None)`
Generates a formatted performance report.

**Parameters:**
- `period`: 'daily', 'weekly', or 'monthly'
- `cryptocurrency`: Optional filter by crypto

**Returns:** str - Formatted report

#### `get_faucet_performance(hours=168)`
Gets performance statistics per faucet.

**Returns:** Dict mapping faucet names to their stats

#### `get_withdrawal_history(limit=100, faucet=None, cryptocurrency=None)`
Retrieves withdrawal transaction history.

**Returns:** List of dicts containing withdrawal records

### Function: `get_analytics()`
Returns the global WithdrawalAnalytics singleton instance.

## Support

For issues or questions:
1. Check the test files for usage examples
2. Run the demo script to see it in action
3. Review the inline documentation in `core/withdrawal_analytics.py`

## License

Same as the parent project.
