# Quick Start: Immediate Proxy Fix (5 Minutes)

**Goal:** Optimize your existing setup to avoid proxy detection issues **right now** with zero cost.

---

## 🚀 **Solution: Use Direct Connection for Problem Faucets**

Your bot already has direct connection fallback built-in. Just optimize the configuration.

---

## 📋 **Step-by-Step Implementation**

### Step 1: SSH to Your VM

```bash
ssh azureuser@4.155.230.212
cd ~/Repositories/cryptobot
```

### Step 2: Edit .env File

```bash
nano .env
```

Find and update these lines:

```bash
# Enable direct connection fallback (should already be true)
ENABLE_DIRECT_FALLBACK=true

# Try direct connection after just 1 proxy failure (was 2)
PROXY_FALLBACK_THRESHOLD=1

# List of faucets that should bypass proxy entirely
# These are the ones with aggressive datacenter IP detection
PROXY_BYPASS_FAUCETS=["dutchy","coinpayu","adbtc","freebitcoin"]
```

Save and exit (Ctrl+X, Y, Enter)

### Step 3: Restart the Service

```bash
sudo systemctl restart faucet_worker
```

### Step 4: Verify It's Working

```bash
# Check service status
sudo systemctl status faucet_worker

# Watch logs in real-time
journalctl -u faucet_worker -f

# Or check log file
tail -f ~/Repositories/cryptobot/logs/faucet_bot.log | grep -E '(DIRECT|Proxy|proxy)'
```

Look for messages like:
```
[INFO] 🔄 [DIRECT FALLBACK] Proxy failed for DutchyCorp. Retrying with direct connection...
[INFO] ✅ [DIRECT FALLBACK SUCCESS] DutchyCorp Claim completed via direct connection!
```

---

## 🎯 **What This Does**

1. **Proxy bypass list:** Dutchy, CoinPayU, AdBTC, FreeBitcoin will use direct connection (no proxy)
2. **Quick fallback:** Other faucets will try direct connection after just 1 proxy failure
3. **Zero cost:** Uses your VM's IP address (no proxy service needed)

---

## 📊 **Expected Results**

### Before (with proxy detection)
```
[ERROR] [DutchyCorp] Proxy Detected - DutchyCorp blocks datacenter IPs
[ERROR] Claim failed: proxy_issue
```

### After (with direct connection)
```
[INFO] ✅ [DIRECT FALLBACK SUCCESS] DutchyCorp Claim completed via direct connection!
[INFO] Claim successful: 0.00001234 BTC
```

---

## ⚠️ **Important Notes**

### Limitations
- All bypassed faucets will see the same IP (your VM's IP: 4.155.230.212)
- You can only claim once per timer period per faucet
- If VM IP gets banned, all accounts affected (low risk with legit use)

### Benefits
- ✅ No proxy detection errors
- ✅ Zero additional cost
- ✅ Faster claims (no proxy latency)
- ✅ Works immediately

---

## 🔍 **Troubleshooting**

### Issue: Still seeing proxy detection errors

**Check 1:** Verify .env changes applied
```bash
grep PROXY_BYPASS_FAUCETS ~/Repositories/cryptobot/.env
```

**Check 2:** Ensure service restarted
```bash
sudo systemctl restart faucet_worker
journalctl -u faucet_worker --since "5 minutes ago" | head -n 20
```

**Check 3:** Watch for direct connection attempts
```bash
tail -f ~/Repositories/cryptobot/logs/faucet_bot.log | grep -i "direct"
```

### Issue: Faucets not loading

**Check 1:** Verify proxy bindings file is valid JSON
```bash
cat ~/Repositories/cryptobot/config/proxy_bindings.json | python -m json.tool
```

**Check 2:** Clear proxy bindings for bypassed faucets
```bash
cd ~/Repositories/cryptobot
python3 -c "
import json
from pathlib import Path

bindings_file = Path('config/proxy_bindings.json')
if bindings_file.exists():
    with open(bindings_file, 'r') as f:
        bindings = json.load(f)
    
    # Remove bindings for bypassed faucets
    bypassed = ['dutchy', 'coinpayu', 'adbtc', 'freebitcoin']
    for account in list(bindings.keys()):
        if any(faucet in account.lower() for faucet in bypassed):
            del bindings[account]
    
    with open(bindings_file, 'w') as f:
        json.dump(bindings, f, indent=2)
    
    print('Cleared proxy bindings for bypassed faucets')
"
```

---

## 🎬 **Next Steps**

After this immediate fix, you can:

1. **Monitor results** for 24 hours to see which faucets work better
2. **Add more free proxies** from Oracle Cloud (see [ORACLE_CLOUD_PROXY_SETUP.md](ORACLE_CLOUD_PROXY_SETUP.md))
3. **Activate GitHub Student Pack** for DigitalOcean credits
4. **Optimize further** by testing each faucet individually

---

## 📈 **Testing Individual Faucets**

Test which faucets work best with/without proxy:

### Test WITH proxy (current Azure VMs)
```bash
cd ~/Repositories/cryptobot
HEADLESS=true python main.py --single faucetcrypto --once
```

### Test WITHOUT proxy (direct connection)
```bash
cd ~/Repositories/cryptobot

# Temporarily disable proxies
export USE_2CAPTCHA_PROXIES=false
export USE_AZURE_PROXIES=false

HEADLESS=true python main.py --single dutchy --once
```

Compare success rates and adjust PROXY_BYPASS_FAUCETS accordingly.

---

## 💡 **Pro Tips**

1. **Keep proxy bypass list minimal** - Only add faucets that consistently fail with proxies
2. **Monitor logs daily** - Look for patterns in which faucets get detected
3. **Test new faucets** - Always test with proxy first, add to bypass list only if needed
4. **Document results** - Keep notes on which faucets work with datacenter IPs

---

**Total Time:** 5 minutes  
**Total Cost:** $0  
**Expected Success Rate Improvement:** 50-80% for bypassed faucets
