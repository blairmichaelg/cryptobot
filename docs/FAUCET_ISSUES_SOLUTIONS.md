# Faucet Issues Solutions Report
**Date**: February 6, 2026  
**Resources Available**: GitHub Student Pack, $1000 Azure Credits, 2Captcha (no CapSolver)

---

## Summary of Issues & Solutions

| Issue | Status | Solution | Priority |
|-------|--------|----------|----------|
| Dead Pick.io domains (4 faucets) | ✅ Fixed | Disabled in config | Done |
| AdBTC 403 Forbidden | ⚠️ Blocked | Needs residential IP outside 2Captcha | Low |
| TonPick browser timeouts | 🔧 Code fix needed | Reduce CF timeout, add early exit | High |
| CoinPayU browser timeouts | 🔧 Code fix needed | Same as TonPick | High |

---

## Issue 1: Dead Pick.io Domains (4 Faucets)

**Status**: ✅ RESOLVED - Disabled in configuration

**Domains confirmed dead (NXDOMAIN)**:
- `bchpick.io` → BchPick
- `polygonpick.io` → PolygonPick  
- `ltcpick.io` → LitePick
- `dashpick.io` → DashPick

**Action Taken**: 
- Disabled in `config/faucet_config.json`
- Removed from `enabled_faucets` list
- Added `disabled_faucets_notes` section for documentation

**Replacement Sites**: None found. Crypto faucets frequently shut down due to low profitability. Monitor for new Pick.io family sites at:
- `tronpick.io` (still active)
- `dogepick.io` (still active)
- `solpick.io` (still active)

---

## Issue 2: AdBTC 403 Forbidden

**Root Cause**: AdBTC.top blocks:
- Azure datacenter IPs (direct VM connection)
- 2Captcha residential proxy IPs (shared residential pool likely flagged)

**Why 2Captcha proxies fail**: 2Captcha's residential proxy pool is shared among thousands of users for CAPTCHA solving. Sites like AdBTC that track/block suspicious traffic likely have these IPs flagged.

### Solution Options (Priority Order)

#### Option A: Try Different 2Captcha Regions (FREE)
The 2Captcha proxy supports geo-targeting. Try different regions:

```bash
# On Azure VM, test different geo zones
ssh azureuser@4.155.230.212

# Your current proxy format:
# http://ub033d0d0583c05dd-zone-custom-session-XXX:ub033d0d0583c05dd@43.135.141.142:2334

# Try zone-residential (different IP pool):
curl -x 'http://ub033d0d0583c05dd-zone-residential-session-test1:ub033d0d0583c05dd@43.135.141.142:2334' -s https://adbtc.top -o /dev/null -w '%{http_code}\n'

# Try zone-datacenter (might be different):
curl -x 'http://ub033d0d0583c05dd-zone-datacenter-session-test1:ub033d0d0583c05dd@43.135.141.142:2334' -s https://adbtc.top -o /dev/null -w '%{http_code}\n'
```

#### Option B: GitHub Student Pack Offerings (FREE)

**Available proxy/networking benefits**:

1. **DigitalOcean** - $200 credit for 12 months
   - Deploy B1-equivalent droplets in residential-adjacent regions
   - Cost: $4-6/month per droplet (covered by credit)
   - IPs are considered "clean" cloud IPs, less likely blocked than Azure

2. **Namecheap** - Free domain + SSL
   - Not directly useful for proxies but can help with reverse proxy setup

3. **No direct residential proxy credits** in Student Pack

#### Option C: Deploy Multi-Region Azure VMs ($5-10/month each)

Your existing docs mention this (see `docs/AZURE_PROXY_SETUP.md`). **This won't work for AdBTC** because:
- Azure IPs are still datacenter IPs
- AdBTC blocks datacenter ranges

#### Option D: Purchase Dedicated Residential Proxy (PAID)

If AdBTC earnings justify it, consider:
- **BrightData/Luminati** - ~$15/GB residential
- **SmartProxy** - ~$12/GB residential  
- **Oxylabs** - ~$10/GB residential
- **SOAX** - ~$99/month for 5GB residential

**ROI Analysis**: AdBTC typically earns $0.01-0.05/day. Annual earnings ~$3-18. Not worth $100+/year for dedicated residential proxies.

### Recommendation for AdBTC

**Keep disabled**. The economics don't justify the proxy cost. If you want to test occasionally:

```bash
# Test from a different network (home WiFi, mobile hotspot) to confirm site works
# If it does, the issue is purely IP-based
```

---

## Issue 3: TonPick/CoinPayU Browser Timeouts

**Root Cause**: Cloudflare JavaScript challenges blocking browser automation:
1. `handle_cloudflare()` waits 30-120 seconds even when CF can't be bypassed
2. Turnstile challenges have misconfigured sitekeys on some sites
3. No early exit when CF is clearly unsolvable

### Solution: Improve handle_cloudflare() with Early Exit

The code already has partial early-exit logic, but the login timeouts are still too high. Here are the improvements:

#### Fix 1: Reduce Default CF Wait in pick_base.py (Already 30s - OK)

The current code at [pick_base.py](faucets/pick_base.py#L259) already uses 30s:
```python
await self.handle_cloudflare(max_wait_seconds=30)
```

#### Fix 2: Add Turnstile Error Detection

Add detection for broken Turnstile challenges:

```python
# In handle_cloudflare(), add check for Turnstile errors
# If Turnstile throws JavaScript errors, exit early instead of waiting
```

#### Fix 3: Increase Browser Navigation Timeout

The Pick.io sites are slow. Update `_navigate_with_retry()` in pick_base.py:

**Current**: 45s minimum  
**Recommended**: 90s minimum for slow-loading Pick.io sites behind Cloudflare

### Code Change for Browser Timeout

Update [pick_base.py](faucets/pick_base.py#L48-L49):

```python
# Current:
nav_timeout = max(getattr(self.settings, "timeout", 60000), 45000)  # At least 45s

# Change to:
nav_timeout = max(getattr(self.settings, "timeout", 60000), 90000)  # At least 90s for slow CF sites
```

### Stealth Improvements for Cloudflare

The browser stealth is good but can be improved:

1. **Randomize viewport sizes** more aggressively
2. **Add mouse movement patterns** before any navigation
3. **Use realistic page warm-up** time

These are already partially implemented in `warm_up_page()` - ensure it's called before every navigation.

---

## Issue 4: Resource Allocation Recommendations

### Azure Credits ($1000) - Best Use

| Purpose | Monthly Cost | Value |
|---------|--------------|-------|
| Main faucet VM (current) | ~$20 | Essential |
| Additional proxy VMs | $5-10 each | Low value (still datacenter IPs) |
| Azure Functions monitoring | ~$5 | Nice-to-have |
| **SAVE for production scaling** | - | Best ROI |

**Recommendation**: Don't spend Azure credits on proxy VMs for AdBTC. Use for:
- Production reliability (larger VM if needed)
- Database/logging (CosmosDB for analytics)
- Monitoring (Application Insights)

### GitHub Student Pack - Best Use

| Benefit | Value for This Project |
|---------|------------------------|
| DigitalOcean $200 | Alternative hosting if Azure issues |
| JetBrains IDEs | Development quality |
| GitHub Pro | Private repos, Actions minutes |

---

## Priority Implementation Order

### Immediate (Do Now)

1. ✅ **Disable dead faucets** - Done
2. ✅ **Disable AdBTC** - Done (keep disabled until residential proxy solution found)
3. 🔧 **Increase Pick.io navigation timeout** to 90s

### Short-term (This Week)

4. 🔧 **Add Turnstile error detection** to handle_cloudflare()
5. 🔧 **Test remaining Pick.io faucets** (tronpick, dogepick, solpick, etc.)
6. 📊 **Monitor claim success rates** after fixes

### Medium-term (If Needed)

7. Research alternative residential proxy providers if economics change
8. Consider DigitalOcean droplets as alternative to Azure VM

---

## Working Faucets After Fixes

After applying fixes, these faucets should work:

| Faucet | Status | Notes |
|--------|--------|-------|
| FireFaucet | ✅ Working | No CF issues |
| Cointiply | ✅ Working | No CF issues |  
| FaucetCrypto | ✅ Working | No CF issues |
| FreeBitcoin | ⚠️ Login issues | Separate investigation needed |
| Dutchy | ✅ Working | No CF issues |
| CoinPayU | 🔧 Needs testing | After timeout fix |
| TronPick | 🔧 Needs testing | After timeout fix |
| DogePick | 🔧 Needs testing | After timeout fix |
| SolPick | 🔧 Needs testing | After timeout fix |
| BinPick | 🔧 Needs testing | After timeout fix |
| TonPick | 🔧 Needs testing | After timeout fix |
| EthPick | 🔧 Needs testing | After timeout fix |
| UsdPick | 🔧 Needs testing | After timeout fix |

**Disabled permanently**:
- BchPick (domain dead)
- PolygonPick (domain dead)
- LitePick/LTCPick (domain dead)
- DashPick (domain dead)
- AdBTC (IP blocked, not worth fixing)

---

## Commands to Test Fixes

```bash
# SSH to Azure VM
ssh azureuser@4.155.230.212

# Pull latest changes
cd ~/Repositories/cryptobot
git pull

# Test a single working faucet first
HEADLESS=true python main.py --single firefaucet --once

# Test Pick.io faucets after timeout fix
HEADLESS=true python main.py --single tronpick --once
HEADLESS=true python main.py --single dogepick --once
```
