# FreeBitcoin Balance/Timer Fix - Deployment Instructions

**Fix Branch:** `copilot/fix-freebitcoin-balance-timer`  
**Target:** Azure VM (DevNode01, APPSERVRG, 4.155.230.212)

---

## Quick Deployment (Azure VM)

### Option A: Automated Deployment Script

```bash
# From your local machine (with Azure CLI and SSH access)
cd /path/to/cryptobot
./deploy/azure_deploy.sh --resource-group APPSERVRG --vm-name DevNode01
```

This will:
1. SSH into the VM
2. Pull latest code from this branch
3. Restart the faucet_worker service
4. Verify service is running

### Option B: Manual Deployment

```bash
# 1. SSH into Azure VM
ssh azureuser@4.155.230.212

# 2. Navigate to the repository
cd ~/Repositories/cryptobot

# 3. Fetch and checkout the fix branch
git fetch origin copilot/fix-freebitcoin-balance-timer
git checkout copilot/fix-freebitcoin-balance-timer
git pull origin copilot/fix-freebitcoin-balance-timer

# 4. Restart the service
sudo systemctl restart faucet_worker

# 5. Check service status
sudo systemctl status faucet_worker

# 6. Monitor logs
tail -f logs/faucet_bot.log | grep -i freebitcoin
```

---

## Testing the Fix

### Step 1: Run Diagnostic Script (Optional)

This verifies the selectors work on the live FreeBitcoin site:

```bash
# On Azure VM
cd ~/Repositories/cryptobot
HEADLESS=true python diagnose_freebitcoin_selectors.py
```

**Expected output:**
```
💰 SEARCHING FOR BALANCE ELEMENTS
✅ #balance_small: FOUND (visible: True, text: 0.00012345)

⏰ SEARCHING FOR TIMER ELEMENTS
✅ #time_remaining: FOUND (visible: True, text: 59:45)
```

### Step 2: Test FreeBitcoin Claim

```bash
# On Azure VM
cd ~/Repositories/cryptobot

# Test with visible browser (if you have X11 forwarding)
python main.py --single freebitcoin --visible --once

# OR headless mode (recommended for VM)
HEADLESS=true python main.py --single freebitcoin --once
```

### Step 3: Verify Success in Logs

```bash
# Check logs for successful extraction
tail -100 logs/faucet_bot.log | grep -A 5 "FreeBitcoin"
```

**Look for these success indicators:**

✅ **Before Fix (FAILED):**
```
[DEBUG] Getting balance...
[DEBUG] Balance: 0
[DEBUG] Checking timer...
[DEBUG] Timer: 0.0 minutes
[FreeBitcoin] Claim result found but not confirmed by timer/balance
```

✅ **After Fix (SUCCESS):**
```
[DEBUG] Getting balance...
[FreeBitcoin] Balance extracted from #balance_small: 0.00012345
[DEBUG] Balance: 0.00012345
[DEBUG] Checking timer...
[FreeBitcoin] Timer extracted from #time_remaining: 59:45
[DEBUG] Timer: 59.75 minutes
FreeBitcoin Claimed! Won: 0.00000123 BTC
```

---

## Verification Checklist

After deployment, verify the following:

- [ ] Code deployed to VM successfully
- [ ] Service restarted without errors
- [ ] Diagnostic script shows balance selector works
- [ ] Diagnostic script shows timer selector works
- [ ] FreeBitcoin login succeeds
- [ ] Balance extraction returns non-zero value
- [ ] Timer extraction returns correct wait time
- [ ] Claim confirmation succeeds (no "not confirmed" error)
- [ ] No errors in service logs

---

## Troubleshooting

### Issue: Service won't start

```bash
# Check service status
sudo systemctl status faucet_worker

# Check logs
sudo journalctl -u faucet_worker -n 50

# Common fixes:
# 1. Wrong working directory - update systemd service
# 2. Missing dependencies - pip install -r requirements.txt
# 3. Permission issues - check file ownership
```

### Issue: Selectors still failing

```bash
# Run diagnostic script to find correct selectors
HEADLESS=true python diagnose_freebitcoin_selectors.py

# Check screenshot
ls -lh logs/freebitcoin_dashboard.png

# Copy screenshot to local machine for review
scp azureuser@4.155.230.212:~/Repositories/cryptobot/logs/freebitcoin_dashboard.png ./
```

### Issue: Claims not confirmed

Check if balance/timer changed after claim:
```bash
grep "Confirm claim" logs/faucet_bot.log -A 10
grep "balance_changed\|timer_after" logs/faucet_bot.log
```

---

## Rollback Instructions

If the fix causes issues:

```bash
# On Azure VM
cd ~/Repositories/cryptobot

# Checkout previous working version
git checkout ac114e1  # Commit before this fix

# Restart service
sudo systemctl restart faucet_worker
```

---

## Post-Deployment Monitoring

Monitor for 24-48 hours:

```bash
# Check claim success rate
grep "FreeBitcoin Claimed" logs/faucet_bot.log | wc -l

# Check confirmation failures
grep "not confirmed" logs/faucet_bot.log | grep FreeBitcoin | wc -l

# Watch live logs
tail -f logs/faucet_bot.log | grep -i freebitcoin
```

**Success criteria:**
- Balance extraction: 100% success (returns non-zero value)
- Timer extraction: 100% success (returns valid time)
- Claim confirmation: >95% success
- No "not confirmed" errors

---

## Files Changed in This Fix

1. `faucets/freebitcoin.py` - Updated selectors (lines 769, 778, 876, 881, 994)
2. `docs/FREEBITCOIN_BALANCE_TIMER_FIX.md` - Documentation

**Key Changes:**
- Balance selector: `#balance` → `#balance_small`
- Added 5 fallback selectors for balance
- Added 6 fallback selectors for timer

---

## Support

If issues persist after deployment:
1. Save logs: `cp logs/faucet_bot.log freebitcoin_fix_test_$(date +%Y%m%d_%H%M%S).log`
2. Run diagnostic script and save output
3. Check `docs/FREEBITCOIN_BALANCE_TIMER_FIX.md` for detailed technical info
4. Review screenshots in `logs/` directory

---

**Deployed by:** Automated via GitHub Copilot  
**Branch:** copilot/fix-freebitcoin-balance-timer  
**Commits:** 55ede95 and predecessors
