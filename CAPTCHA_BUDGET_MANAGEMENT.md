# Captcha Budget Management Implementation

**Date:** January 24, 2026  
**Status:** ✅ Complete

## Overview

Implemented intelligent captcha budget management with provider fallback to prevent cost overruns while ensuring critical claims are never missed. The system includes pre-flight budget checks, automatic provider fallback, cost estimation, and budget-aware job selection.

## Implementation Summary

### 1. Pre-flight Budget Check (`solvers/captcha.py`)

**New Method:** `can_afford_captcha(captcha_type: str) -> bool`

Checks if we can afford a captcha solve within the daily budget **before** submitting to the provider.

**Features:**
- Checks if solve cost would exceed daily budget
- Warns when budget is low (< $0.50 remaining)
- Returns False if budget exhausted or insufficient
- Uses actual cost estimates per captcha type:
  - Turnstile: $0.003
  - hCaptcha: $0.003
  - reCaptcha: $0.003
  - Image: $0.001

**Example:**
```python
solver = CaptchaSolver(api_key="...", daily_budget=5.0)
if solver.can_afford_captcha("turnstile"):
    # Proceed with solve
    result = await solver.solve_captcha(page)
else:
    # Budget exhausted, fall back to manual
    logger.warning("Budget exhausted. Manual solve required.")
```

### 2. Provider Fallback (`solvers/captcha.py`)

**New Method:** `solve_with_fallback(page, captcha_type, sitekey, url, proxy_context) -> Optional[str]`

Attempts to solve with primary provider, automatically falls back to secondary on failure.

**Fallback Triggers:**
- `NO_SLOT` error (provider queue full)
- `ZERO_BALANCE` error (provider account depleted)
- Network timeout or connection errors

**Logic:**
1. Try primary provider (2captcha or capsolver)
2. If failure is fallback-worthy → try secondary provider
3. Track which provider succeeded for cost attribution
4. Return solution token or None if all providers fail

**Provider Stats Tracking:**
```python
stats = solver.get_provider_stats()
# Returns:
{
    "providers": {
        "2captcha": {"solves": 15, "failures": 2, "cost": 0.045},
        "capsolver": {"solves": 3, "failures": 0, "cost": 0.009}
    },
    "primary": "2captcha",
    "fallback": "capsolver"
}
```

### 3. Faucet Cost Estimation (`core/orchestrator.py`)

**New Method:** `estimate_claim_cost(faucet_type: str) -> float`

Estimates the total cost to claim a faucet based on historical data and known patterns.

**Estimation Factors:**
- Average captchas per claim (1-3)
- Captcha type (turnstile, hcaptcha, image)
- Historical success/retry rate
- Faucet-specific patterns

**Default Estimates:**
| Faucet | Captcha Type | Count | Cost |
|--------|--------------|-------|------|
| FireFaucet | Turnstile | 1 | $0.003 |
| FreeBitcoin | hCaptcha | 2 | $0.006 |
| CoinPay-U | Image | 1 | $0.001 |
| DutchyCorp | Turnstile | 1 | $0.003 |
| Pick.io Family | Turnstile | 1 | $0.003 |

**Dynamic Adjustment:**
- If success rate < 80%, multiply cost by retry rate
- Historical data overrides defaults after 5+ claims

### 4. Budget-Aware Job Selection (`core/orchestrator.py`)

Integrated into `scheduler_loop()` to check budget before launching jobs.

**Pre-Launch Checks:**
1. Get current budget status
2. Estimate cost for this faucet
3. Compare remaining budget vs estimated cost
4. If insufficient → defer job to next budget reset
5. If low budget but high-value claim → prompt for manual solve

**Decision Logic:**
```python
if remaining_budget < estimated_cost:
    # Defer to tomorrow
    job.next_run = tomorrow_midnight + 300
elif remaining_budget < $0.50 and avg_earnings > estimated_cost * 2:
    # High-value claim, worth manual effort
    logger.warning("Budget low but claim is profitable. Consider manual solve.")
    # Proceed - may prompt for manual CAPTCHA
else:
    # Skip low-value claims when budget is low
    job.next_run = now + 3600
```

### 5. Manual Solve Fallback

**Enhanced:** `_wait_for_human(page, timeout, high_value_claim=False)`

When budget is exhausted but claim is profitable, system prompts for manual solve.

**High-Value Detection:**
- Faucets: FireFaucet, FreeBitcoin, Cointiply
- Shows special warning for budget-exhausted high-value claims
- Only prompts if:
  - Not headless mode
  - Average earnings > 2x estimated cost
  - Remaining budget < $0.50

**Example Output:**
```
⚠️ BUDGET EXHAUSTED - HIGH VALUE CLAIM DETECTED ⚠️
Please solve CAPTCHA manually for profitable claim (timeout: 300s)
```

## Configuration

### Environment Variables (.env)

```bash
# Captcha Budget Settings
CAPTCHA_DAILY_BUDGET=5.0
CAPTCHA_PROVIDER=2captcha
TWOCAPTCHA_API_KEY=your_key_here

# Fallback Provider (Optional)
CAPTCHA_FALLBACK_PROVIDER=capsolver
CAPTCHA_FALLBACK_API_KEY=your_fallback_key
```

### BotSettings (core/config.py)

Already configured:
- `captcha_daily_budget`: Daily spend cap (default $5.00)
- `captcha_provider`: Primary provider (2captcha or capsolver)
- `captcha_fallback_provider`: Secondary provider (optional)
- `captcha_fallback_api_key`: Fallback API key (optional)

## Usage Examples

### Example 1: Basic Budget Check

```python
from solvers.captcha import CaptchaSolver

solver = CaptchaSolver(
    api_key="your_key",
    provider="2captcha",
    daily_budget=5.0
)

# Check budget before claim
if solver.can_afford_captcha("turnstile"):
    result = await solver.solve_captcha(page)
else:
    logger.warning("Budget exhausted. Deferring claim.")
```

### Example 2: Provider Fallback

```python
# Configure fallback
solver.set_fallback_provider("capsolver", "fallback_key")

# solve_with_fallback automatically tries both
token = await solver.solve_with_fallback(
    page, "turnstile", sitekey, page.url
)

# Check which provider was used
stats = solver.get_provider_stats()
print(f"Primary success rate: {stats['providers']['2captcha']['solves']}")
```

### Example 3: Cost Estimation

```python
from core.orchestrator import JobScheduler

scheduler = JobScheduler(settings, browser_manager)

# Estimate costs
ff_cost = scheduler.estimate_claim_cost("firefaucet")  # $0.003
fb_cost = scheduler.estimate_claim_cost("freebitcoin")  # $0.006

print(f"FireFaucet: ${ff_cost:.4f}")
print(f"FreeBitcoin: ${fb_cost:.4f}")
```

## Benefits

✅ **No Budget Overruns**  
- Pre-flight checks prevent unexpected costs
- Daily budget cap enforced automatically
- Clear warnings when budget is low

✅ **Critical Claims Never Missed**  
- High-value claims can trigger manual solve
- Budget deferral (not cancellation) for low-value claims
- Profitability analysis guides decisions

✅ **Provider Failures Handled Gracefully**  
- Automatic fallback on NO_SLOT/ZERO_BALANCE
- Provider performance tracking
- Cost attribution per provider

✅ **Clear Logging of Budget Decisions**  
- Budget status logged every claim
- Cost estimates shown for deferrals
- Provider stats available on demand

## Monitoring

### Budget Status

```python
solver = CaptchaSolver(...)
budget = solver.get_budget_stats()

print(f"Daily Budget: ${budget['daily_budget']}")
print(f"Spent Today: ${budget['spent_today']}")
print(f"Remaining: ${budget['remaining']}")
print(f"Solves Today: {budget['solves_today']}")
```

### Provider Performance

```python
stats = solver.get_provider_stats()
for provider, data in stats['providers'].items():
    success_rate = data['solves'] / max(data['solves'] + data['failures'], 1)
    print(f"{provider}: {success_rate:.1%} success, ${data['cost']:.4f} cost")
```

### Cost Estimates

Check logs for cost estimation messages:
```
Estimated claim cost for firefaucet: $0.0030
💰 Budget insufficient for FireFaucet claim: Need $0.0030, have $0.0012. Deferring claim.
⚠️ Budget low but firefaucet is profitable ($0.0045 avg). Consider manual CAPTCHA solve.
```

## Testing

Run validation test:
```bash
python -c "from solvers.captcha import CaptchaSolver; \
from core.orchestrator import JobScheduler; \
from core.config import BotSettings; \
from unittest.mock import Mock; \
solver = CaptchaSolver(api_key='test', daily_budget=5.0); \
print('✓ can_afford_captcha:', solver.can_afford_captcha('turnstile')); \
print('✓ Budget stats:', solver.get_budget_stats()); \
scheduler = JobScheduler(BotSettings(), Mock()); \
print('✓ Cost estimate:', scheduler.estimate_claim_cost('firefaucet'))"
```

Expected output:
```
✓ can_afford_captcha: True
✓ Budget stats: {'daily_budget': 5.0, 'spent_today': 0.0, 'remaining': 5.0, ...}
✓ Cost estimate: 0.003
```

## Implementation Files

- `solvers/captcha.py`: Budget checks, provider fallback, manual solve
- `core/orchestrator.py`: Cost estimation, budget-aware job selection
- `core/config.py`: Budget configuration (already present)
- `core/analytics.py`: Cost tracking (already present)

## Next Steps

1. **Monitor Budget Performance**  
   - Check logs for budget warnings
   - Adjust daily_budget based on profitability
   - Review provider stats weekly

2. **Fine-tune Cost Estimates**  
   - After 1 week, review actual costs per faucet
   - Update estimates in `estimate_claim_cost()`
   - Consider dynamic cost learning

3. **Optimize Provider Selection**  
   - Review provider success rates
   - Switch primary/fallback if needed
   - Consider dynamic provider selection based on performance

4. **Test Manual Solve Flow**  
   - Reduce budget to trigger manual prompts
   - Verify high-value claim detection
   - Ensure manual solve timeout works

## Notes

- Budget resets daily at midnight (UTC)
- Cost estimates are conservative (may overestimate)
- Manual solve requires non-headless mode
- Provider fallback only triggers on specific errors (NO_SLOT, ZERO_BALANCE)
- High-value claim threshold: avg_earnings > 2x estimated_cost

---

**Status:** ✅ Ready for Production  
**Last Updated:** January 24, 2026
