# Captcha Budget Management - Quick Reference

## Key Features

### 1. Pre-flight Budget Check
```python
solver.can_afford_captcha("turnstile")  # Returns True/False
```

### 2. Provider Fallback
```python
# Automatically tries fallback on primary failure
token = await solver.solve_with_fallback(page, "turnstile", sitekey, url)
```

### 3. Cost Estimation
```python
scheduler.estimate_claim_cost("firefaucet")  # Returns $0.003
```

### 4. Budget Monitoring
```python
solver.get_budget_stats()  # Returns budget status
solver.get_provider_stats()  # Returns provider performance
```

## Configuration

**.env File:**
```bash
CAPTCHA_DAILY_BUDGET=5.0
CAPTCHA_PROVIDER=2captcha
TWOCAPTCHA_API_KEY=your_key

# Optional fallback
CAPTCHA_FALLBACK_PROVIDER=capsolver
CAPTCHA_FALLBACK_API_KEY=your_fallback_key
```

## Common Scenarios

### Budget Exhausted
```
💰 Cannot afford turnstile solve ($0.0030). Remaining budget: $0.0012
💰 Budget insufficient for FireFaucet claim. Deferring claim.
```
**Action:** Job deferred to next budget reset (midnight UTC)

### Low Budget, High-Value Claim
```
⚠️ Budget low but firefaucet is profitable ($0.0045 avg). Consider manual solve.
⚠️ BUDGET EXHAUSTED - HIGH VALUE CLAIM DETECTED ⚠️
Please solve CAPTCHA manually for profitable claim (timeout: 300s)
```
**Action:** Prompts for manual CAPTCHA solve (non-headless only)

### Provider Failure
```
🔑 Trying primary provider: 2captcha
❌ 2captcha failed to return a solution
🔁 Trying fallback provider: capsolver
✅ capsolver fallback succeeded
```
**Action:** Automatically switches to fallback provider

## Cost Estimates (Default)

| Faucet | Type | Cost |
|--------|------|------|
| FireFaucet | Turnstile | $0.003 |
| FreeBitcoin | hCaptcha x2 | $0.006 |
| CoinPay-U | Image | $0.001 |
| DutchyCorp | Turnstile | $0.003 |
| Pick.io* | Turnstile | $0.003 |

*Includes: LTCPick, TRXPick, DOGEPick, SOLPick, BNBPick, BCHPick, TONPick, MATICPick, DASHPick, ETHPick, USDTPick

## Monitoring Commands

**Check Budget:**
```python
from solvers.captcha import CaptchaSolver
solver = CaptchaSolver(api_key="...", daily_budget=5.0)
print(solver.get_budget_stats())
```

**Check Provider Stats:**
```python
stats = solver.get_provider_stats()
for provider, data in stats['providers'].items():
    print(f"{provider}: {data['solves']} solves, ${data['cost']:.4f} spent")
```

**View Logs:**
```bash
grep "Budget\|Provider" logs/faucet_bot.log | tail -20
```

## Troubleshooting

**Issue:** Budget resets too often  
**Fix:** Increase `CAPTCHA_DAILY_BUDGET` in .env

**Issue:** Too many manual solve prompts  
**Fix:** Reduce high-value threshold or increase budget

**Issue:** Provider fallback not working  
**Fix:** Verify `CAPTCHA_FALLBACK_PROVIDER` and `CAPTCHA_FALLBACK_API_KEY` in .env

**Issue:** Cost estimates inaccurate  
**Fix:** Wait for historical data (5+ claims) or manually update estimates in `orchestrator.py`

## Files Modified

- `solvers/captcha.py`: Budget logic, provider fallback
- `core/orchestrator.py`: Cost estimation, job selection
- `core/config.py`: Configuration (already present)

## Testing

```bash
# Quick test
python -c "from solvers.captcha import CaptchaSolver; \
solver = CaptchaSolver(api_key='test', daily_budget=5.0); \
print('Budget:', solver.get_budget_stats()); \
print('Can afford turnstile:', solver.can_afford_captcha('turnstile'))"
```

Expected: `Can afford turnstile: True`, Budget shows $5.00 remaining

---

For full documentation, see [CAPTCHA_BUDGET_MANAGEMENT.md](CAPTCHA_BUDGET_MANAGEMENT.md)
