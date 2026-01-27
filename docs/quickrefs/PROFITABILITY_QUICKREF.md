# 🎯 Profitability System - Quick Reference

## ✨ What It Does

Your bot now **automatically optimizes** for maximum profit by:
- 📈 Claiming high-ROI faucets more frequently
- 📉 Reducing claims on low-ROI faucets
- ⛔ Auto-disabling money-losing faucets
- 🔄 Re-evaluating disabled faucets after 24 hours

## 🔥 Key Features

### Automatic Priority Adjustment (Every Hour)
```
High ROI (score >200)     → 2x more claims (0.5x multiplier)
Good ROI (100-200)        → 1.5x more claims (0.6-0.8x)
Normal ROI (50-100)       → Standard frequency (0.9-1.0x)
Low ROI (0-50)            → Fewer claims (1.0-1.5x)
Negative ROI              → Auto-disable or very low priority
```

### Auto-Disable Logic
- Faucet loses money for **3+ days** → Disabled for 24 hours
- After 24 hours → Re-evaluated automatically
- If profitable → Auto-enabled with notification

## 📊 Quick Commands

### Check Profitability
```python
from core.analytics import get_tracker

tracker = get_tracker()

# Single faucet
metrics = tracker.get_faucet_profitability("firefaucet", days=7)
print(f"Score: {metrics['profitability_score']:.1f}")
print(f"ROI: {metrics['roi_percentage']:.1f}%")
print(f"Net: ${metrics['net_profit_usd']:.4f}")

# All faucets (ranked)
report = tracker.get_profitability_report()
for f in report[:5]:  # Top 5
    print(f"{f['faucet']}: Score {f['profitability_score']:.1f}, ROI {f['roi_percentage']:.1f}%")
```

### Check Scheduler Status
```python
from main import scheduler  # Your scheduler instance

print(f"Disabled: {list(scheduler.disabled_faucets.keys())}")
print(f"Priorities: {scheduler.faucet_priority_multipliers}")
```

## 📝 What to Watch For

### Log Messages

**Priority Updates (Every Hour):**
```
🔄 Updating job priorities based on profitability...
📊 PRIORITY UPDATE: 5 changes
  ↑ firefaucet: 1.00 → 0.76 (score: 115.2, ROI: 4306.2%)
💹 Profitability Summary: 3 high-ROI, 2 low-ROI, 1 disabled
```

**Auto-Disable:**
```
⛔ AUTO-DISABLED: badfaucet due to consistent losses (7d ROI: -45.2%, net: $-0.0234)
```

**Auto-Enable:**
```
✅ AUTO-ENABLED: goodfaucet restored due to improved profitability (score: 85.3, ROI: 312.4%)
```

## 🎮 No Configuration Needed!

The system works **automatically** using your existing analytics data. Just run your bot normally and it will optimize itself.

## 🔧 Optional Tuning

Want to adjust the behavior? Edit these values in `core/orchestrator.py`:

```python
# Change update frequency (default: 1 hour)
if now - self.last_priority_update_time >= 7200:  # 2 hours

# Change disable duration (default: 24 hours)
if now - disabled_time < 172800:  # 48 hours

# Change minimum claims for auto-disable (default: 10)
if net_profit < 0 and metrics["claim_count"] >= 20:  # More conservative
```

## 📚 Full Documentation

See `docs/PROFITABILITY_TRACKING.md` for complete details.

## 🚀 Deploy to Azure VM

```bash
deploy/azure_deploy.sh --resource-group APPSERVRG --vm-name DevNode01
```

## 🎉 That's It!

Your bot is now **self-optimizing for maximum profit**. Just watch the logs for priority updates and enjoy higher ROI!

---
**Version:** Gen 3.0  
**Status:** ✅ Production Ready
