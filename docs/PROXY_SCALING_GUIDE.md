# Proxy Scaling Guide

## Current Status

- **Active Proxies**: 3 DigitalOcean Droplets
- **Operation Mode**: LOW_PROXY (automatically activated when < 10 healthy proxies)
- **Concurrency**: Reduced to 2 concurrent bots (from normal max of 3)
- **Limitation**: DigitalOcean new account droplet limit = 3

## Impact of LOW_PROXY Mode

When the system detects fewer than 10 healthy proxies, it automatically enters LOW_PROXY mode:

```python
# From core/config.py
low_proxy_threshold: int = 10  # Threshold for NORMAL mode
low_proxy_max_concurrent_bots: int = 2  # Reduced concurrency in LOW_PROXY
```

**Effects**:
- ✅ Reduced concurrency preserves proxy health
- ✅ Prevents proxy burnout and rate limiting
- ⚠️ Lower throughput and earnings potential
- ⚠️ Longer claim cycles for multiple accounts

## Scaling Options

### Option 1: Request DigitalOcean Droplet Limit Increase ⭐ RECOMMENDED

**Pros**:
- Same infrastructure as current setup
- No code changes required
- Clean, homogeneous proxy pool
- Cost-effective ($4-6/month per droplet)

**Process**:
1. Open DigitalOcean Support Ticket
2. Request: "Increase droplet limit for proxy infrastructure"
3. Mention: "Legitimate use case for faucet automation with 3 existing droplets"
4. Typical approval: 24-48 hours
5. Common increase: 3 → 10-25 droplets

**Setup Steps**:
```bash
# After approval, deploy additional droplets:
cd deploy
./deploy_digitalocean_proxies.sh --count 7  # Add 7 more (total = 10)

# Proxies auto-added to config/digitalocean_proxies.txt
# System will auto-detect and exit LOW_PROXY mode
```

**Cost**: ~$28-42/month for 7 additional droplets

---

### Option 2: Add Azure VM Proxies

**Pros**:
- Multi-region distribution (better geo-diversity)
- Existing Azure account and infrastructure
- Can mix with DigitalOcean for redundancy

**Cons**:
- Slightly higher cost (~$8-15/month per VM)
- Requires Azure CLI/Portal setup
- Mixed provider management

**Setup Steps**:
```bash
# 1. Deploy Azure VM proxies (pick available regions)
cd deploy
./deploy_azure_proxies.sh --region westus2 --count 3
./deploy_azure_proxies.sh --region eastus --count 2
./deploy_azure_proxies.sh --region centralus --count 2

# 2. Update .env
USE_AZURE_PROXIES=true

# 3. Restart service
sudo systemctl restart faucet_worker
```

**Available SKUs**: Check `docs/azure/AZURE_VM_STATUS.md` for regions with available Standard_B1s

**Cost**: ~$56-105/month for 7 VMs

---

### Option 3: Mix Residential + Datacenter Proxies 🔥 BEST PERFORMANCE

**Pros**:
- Residential IPs bypass most anti-bot measures
- Higher success rates on strict faucets (FreeBitcoin, Cointiply)
- Can use fewer proxies with better results

**Cons**:
- Higher cost ($50-200/month for residential pool)
- Requires proxy provider subscription (Webshare, Zyte, Bright Data)
- More complex configuration

**Setup Steps**:

#### Using Webshare Residential
```bash
# 1. Sign up at webshare.io
# 2. Get API key from dashboard
# 3. Update .env
PROXY_PROVIDER=webshare
WEBSHARE_API_KEY=your_api_key_here
WEBSHARE_PAGE_SIZE=50

# 4. Keep existing DigitalOcean as backup
USE_DIGITALOCEAN_PROXIES=true

# System will auto-mix residential + datacenter
```

#### Using Zyte Smart Proxy
```bash
# 1. Sign up at zyte.com
# 2. Update .env
PROXY_PROVIDER=zyte
ZYTE_API_KEY=your_api_key_here
ZYTE_POOL_SIZE=20  # Logical sticky sessions

# Zyte auto-rotates from pool of 100M+ IPs
```

**Cost**: 
- Webshare: ~$50-100/month (residential)
- Zyte: ~$100-200/month (premium rotating)

---

### Option 4: 2Captcha Proxy Integration (Already Configured)

**Status**: ✅ Available but not currently active

**Pros**:
- Already implemented in code
- No infrastructure management
- Pay-as-you-go pricing

**Cons**:
- Shared proxy pool (less reliable)
- Limited geo-targeting
- Adds to captcha costs

**Enable**:
```bash
# Update .env
USE_2CAPTCHA_PROXIES=true
USE_DIGITALOCEAN_PROXIES=false  # Optional: disable DigitalOcean
```

**Cost**: Included with captcha costs (~$0.001-0.003 per use)

---

## Recommended Scaling Strategy

### For Current Setup (3 Droplets)

**Short-term** (Next 24-48h):
1. ✅ Request DigitalOcean limit increase
2. ⏳ Continue running in LOW_PROXY mode (concurrency=2)
3. 📊 Monitor performance in `docs/summaries/PROJECT_STATUS_REPORT.md`

**Medium-term** (After DO approval):
1. Deploy 7 additional DigitalOcean droplets → Total = 10
2. System auto-exits LOW_PROXY mode → concurrency=3
3. Monitor proxy health: `config/proxy_health.json`

**Long-term** (If expansion needed):
1. Add 5-10 Azure VMs in different regions for geo-diversity
2. Consider residential proxies for high-value faucets (FreeBitcoin)
3. Implement smart routing: residential for login, datacenter for claims

### For Production Scale (10+ Accounts)

**Recommended Mix**:
- **10 DigitalOcean Droplets**: Base datacenter pool ($40-60/month)
- **5 Azure VMs**: Regional diversity ($40-75/month)
- **Webshare Residential Pool**: Premium faucets ($50-100/month)
- **Total Cost**: ~$130-235/month for robust 15+ proxy infrastructure

---

## Configuration Reference

### Current Settings (LOW_PROXY Mode)
```python
# core/config.py
low_proxy_threshold: int = 10  # Need 10+ for NORMAL mode
low_proxy_max_concurrent_bots: int = 2  # Current concurrency
max_concurrent_bots: int = 3  # Normal mode concurrency
```

### Proxy Provider Priority
```python
# Priority order (highest to lowest)
1. USE_DIGITALOCEAN_PROXIES=true  # Currently active
2. USE_AZURE_PROXIES=true  # Available, not active
3. PROXY_PROVIDER=webshare  # Requires subscription
4. PROXY_PROVIDER=zyte  # Requires subscription
5. USE_2CAPTCHA_PROXIES=true  # Fallback
```

### Health Monitoring
```bash
# Check proxy health
cat config/proxy_health.json | jq '.proxies[] | select(.is_dead==false)'

# Check current mode
tail -50 logs/faucet_bot.log | grep -E "LOW_PROXY|NORMAL|operation mode"

# Proxy binding status
cat config/proxy_bindings.json | jq .
```

---

## Troubleshooting

### System Stuck in LOW_PROXY Mode
```bash
# 1. Check proxy health
python3 -c "
from core.proxy_manager import ProxyManager
from core.config import BotSettings
pm = ProxyManager(BotSettings())
import asyncio
asyncio.run(pm.health_check_all())
print(f'Healthy: {len([p for p in pm.proxies if not pm.get_proxy_stats(p).get(\"is_dead\")])}')
"

# 2. If < 10 healthy, investigate dead proxies
# 3. Restart unhealthy droplets or deploy new ones
```

### Proxies Getting Rate Limited
```bash
# Increase cooldown windows
# Edit core/proxy_manager.py
COOLDOWN_WINDOW_SECONDS = 300  # 5 min → 10 min
BURN_WINDOW_SECONDS = 43200  # 12 hours → 24 hours
```

---

## Cost-Benefit Analysis

| Setup | Monthly Cost | Healthy Proxies | Concurrency | ROI Impact |
|-------|-------------|-----------------|-------------|------------|
| **Current (3 DO)** | $12-18 | 3 | 2 | Baseline (LOW_PROXY) |
| **10 DO Droplets** | $40-60 | 10 | 3 | +50% throughput |
| **10 DO + 5 Azure** | $80-135 | 15 | 3 | +50% + geo diversity |
| **Residential Mix** | $130-235 | 15+ | 3 | +100% (higher success rate) |

---

## Next Steps

1. **Immediate**: Request DigitalOcean droplet limit increase
2. **Week 1**: Deploy 7 additional droplets (post-approval)
3. **Week 2**: Monitor exit from LOW_PROXY mode
4. **Month 1**: Evaluate residential proxies for premium faucets
5. **Ongoing**: Monitor `config/proxy_health.json` and adjust

---

## References

- Proxy Manager Code: `core/proxy_manager.py`
- Configuration: `core/config.py`
- Azure Deployment: `deploy/deploy_azure_proxies.sh`
- DigitalOcean Deployment: `deploy/deploy_digitalocean_proxies.sh`
- Health Monitoring: `config/proxy_health.json`
- System Status: `docs/summaries/PROJECT_STATUS_REPORT.md`
