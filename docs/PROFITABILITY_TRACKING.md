# Dynamic Faucet ROI Tracking & Profitability-Based Prioritization

## Overview

The cryptobot now features **dynamic profitability tracking** that automatically adjusts job priorities based on real-world ROI metrics. This system maximizes profits by:

- **Prioritizing high-earning faucets** for more frequent claims
- **Deprioritizing low-ROI faucets** to reduce wasted resources
- **Auto-disabling unprofitable faucets** that consistently lose money
- **Providing detailed profitability reports** for manual optimization

## Key Features

### 1. Comprehensive ROI Metrics (`get_faucet_profitability`)

Calculate detailed profitability for any faucet over a configurable time window:

```python
from core.analytics import get_tracker

tracker = get_tracker()
metrics = tracker.get_faucet_profitability("firefaucet", days=7)

# Returns:
{
    "total_earned_usd": 15.42,
    "total_cost_usd": 0.35,
    "net_profit_usd": 15.07,
    "roi_percentage": 4306.2,
    "avg_earnings_per_claim": 0.52,
    "claim_count": 30,
    "success_count": 28,
    "success_rate": 93.3,
    "captcha_failure_rate": 6.7,
    "profitability_score": 115.2,  # Composite score (0-100+)
    "time_weighted_earnings_usd": 16.1
}
```

### 2. Profitability Score Calculation

The **profitability_score** is a composite metric (0-100+) that combines:

| Component | Range | Description |
|-----------|-------|-------------|
| **Base ROI** | 0-100 | ROI percentage capped at 100 |
| **Success Rate Bonus** | 0-20 | +20 for >80%, +10 for >60%, +5 for >40% |
| **Captcha Penalty** | -50 to 0 | -5 points per 10% failure rate |
| **Time-Decay Bonus** | 0-10 | +10 if recent performance is >20% better |

**Example Scoring:**
- Score >100: Excellent (high priority)
- Score 50-100: Good (normal priority)  
- Score 0-50: Poor (low priority)
- Score <0: Unprofitable (auto-disable candidate)

### 3. Profitability Report (`get_profitability_report`)

Get a ranked list of all faucets by profitability:

```python
report = tracker.get_profitability_report(days=7, min_claims=3)

# Returns sorted list:
[
    {
        "faucet": "firefaucet",
        "profitability_score": 115.2,
        "roi_percentage": 4306.2,
        "net_profit_usd": 15.07,
        "total_earned_usd": 15.42,
        "total_cost_usd": 0.35,
        "claim_count": 30,
        "success_rate": 93.3,
        ...
    },
    {...}  # More faucets
]
```

### 4. Automatic Priority Adjustment (`update_job_priorities`)

The scheduler automatically recalculates job priorities **every hour** based on profitability:

```python
# Called automatically in scheduler_loop every 3600 seconds
scheduler.update_job_priorities()
```

**Priority Multipliers:**

| Profitability Score | Multiplier | Effect |
|---------------------|------------|--------|
| >200 | 0.5 | Highest priority (claim more often) |
| 100-200 | 0.6-0.8 | High priority |
| 50-100 | 0.9-1.0 | Normal priority |
| 0-50 | 1.0-1.5 | Low priority |
| <0 | 1.5-2.0 | Very low priority |

Lower multiplier = higher priority (jobs run sooner)

### 5. Auto-Disable Unprofitable Faucets

Faucets with **negative ROI for 3+ days** are automatically disabled:

```python
# Disabled faucets tracked in scheduler
scheduler.disabled_faucets = {
    "badfaucet": 1737653280.0  # timestamp when disabled
}
```

**Behavior:**
- Disabled faucets skip job execution for 24 hours
- After 24 hours, they're re-evaluated
- If still unprofitable, they remain disabled
- If profitable again, they're auto-enabled

**Logs:**
```
⛔ AUTO-DISABLED: badfaucet due to consistent losses (7d ROI: -45.2%, net: $-0.0234)
✅ AUTO-ENABLED: goodfaucet restored due to improved profitability (score: 85.3, ROI: 312.4%)
```

## Integration Points

### Scheduler Loop

Priority updates are integrated into the main scheduler loop:

```python
async def scheduler_loop(self):
    while not self._stop_event.is_set():
        now = time.time()
        
        # Update priorities every hour
        if now - self.last_priority_update_time >= 3600:
            logger.info("🔄 Updating job priorities based on profitability...")
            self.update_job_priorities()
            self.last_priority_update_time = now
        
        # Check if faucet is disabled before launching job
        for job in ready_jobs:
            if job.faucet_type in self.disabled_faucets:
                logger.debug(f"⛔ Skipping disabled faucet: {job.faucet_type}")
                continue
            
            # Launch job...
```

### Analytics Recording

Make sure to record costs for accurate ROI:

```python
from core.analytics import get_tracker

tracker = get_tracker()

# Record claim
tracker.record_claim("firefaucet", success=True, amount=1000, currency="BTC")

# Record associated costs
tracker.record_cost("captcha", 0.003, faucet="firefaucet")
```

## Usage Examples

### Manual Priority Check

```python
from core.analytics import get_tracker

tracker = get_tracker()

# Get top 5 most profitable faucets
report = tracker.get_profitability_report(days=7)
for faucet_data in report[:5]:
    print(f"{faucet_data['faucet']}: Score {faucet_data['profitability_score']:.1f}")
```

### Identify Problem Faucets

```python
# Find faucets losing money
report = tracker.get_profitability_report(days=7)
losing_faucets = [f for f in report if f['net_profit_usd'] < 0]

for faucet in losing_faucets:
    print(f"❌ {faucet['faucet']}: Loss ${abs(faucet['net_profit_usd']):.4f}")
```

### Check Scheduler Status

```python
from core.orchestrator import scheduler  # Your scheduler instance

print(f"Disabled faucets: {len(scheduler.disabled_faucets)}")
print(f"Priority multipliers: {scheduler.faucet_priority_multipliers}")
```

## Configuration

No additional configuration required! The system works automatically using existing analytics data.

**Optional Tuning:**

Edit `core/orchestrator.py` to adjust:

```python
# Change priority update interval (default: 3600s = 1 hour)
if now - self.last_priority_update_time >= 7200:  # 2 hours
    self.update_job_priorities()

# Change disable duration (default: 24 hours)
if now - disabled_time < 172800:  # 48 hours
    continue
```

## Logging

The system provides detailed logging:

```
📊 PRIORITY UPDATE: 5 changes
  ↑ firefaucet: 1.00 → 0.76 (score: 115.2, ROI: 4306.2%)
  ↓ slowfaucet: 0.80 → 1.20 (score: 35.8, ROI: 85.3%)
  ⛔ DISABLED badfaucet (negative ROI)
  ✅ ENABLED goodfaucet (score 92.1)

💹 Profitability Summary: 3 high-ROI, 2 low-ROI, 1 disabled
```

## Performance Impact

- **CPU:** Minimal (<0.1% overhead)
- **Memory:** ~50KB for profitability data
- **I/O:** Priority updates write to job queue (already persisted)
- **Network:** None (uses cached analytics data)

## Testing

Run the included test script:

```bash
python test_profitability.py
```

Expected output:
```
✓ Recorded 10 test claims
✓ Generated report with 3 faucets
✓ Priority update test complete
```

## Troubleshooting

### No Priority Changes

**Problem:** `update_job_priorities()` doesn't change anything

**Solutions:**
1. Ensure analytics has data: Check `earnings_analytics.json`
2. Wait for enough claims: Need minimum 3 claims per faucet
3. Check time window: Default is 7 days; ensure you have recent data

### Faucet Disabled Too Aggressively

**Problem:** Good faucet gets disabled temporarily

**Solution:** Increase the claim count threshold in `update_job_priorities()`:

```python
if net_profit < 0 and metrics["claim_count"] >= 20:  # Increase from 10
    # Check 3-day trend...
```

### Priority Not Applied

**Problem:** Jobs still run with same priority

**Check:**
1. Verify `update_job_priorities()` is being called (check logs)
2. Ensure jobs are in queue (not already running)
3. Verify `faucet_priority_multipliers` dict has entries

## Future Enhancements

Planned improvements:

- [ ] **ML-based prediction** of future profitability
- [ ] **Cost forecasting** based on captcha difficulty trends
- [ ] **Multi-currency optimization** (ETH vs BTC vs altcoins)
- [ ] **Time-of-day optimization** (claim when network fees are low)
- [ ] **Dashboard integration** for real-time profitability charts

## References

- **Analytics Module:** `core/analytics.py`
- **Orchestrator:** `core/orchestrator.py`
- **Test Script:** `test_profitability.py`
- **Data Storage:** `earnings_analytics.json`

---

**Last Updated:** 2026-01-24  
**Version:** Gen 3.0 - Dynamic Profitability System
