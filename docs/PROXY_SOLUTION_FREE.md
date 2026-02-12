# Free Proxy Solution for Cryptobot

**Date:** February 11, 2026  
**Goal:** Solve proxy detection issues without spending additional money  
**Available Resources:** GitHub Student Developer Pack + Azure $1000 credits

---

## 🔍 Current Situation Analysis

### What We Have
- **8 Azure VM proxies** (datacenter IPs: 20.115.154.150, 4.155.110.28, etc.)
- **Azure $1000 credits** available
- **GitHub Student Developer Pack** with DigitalOcean $200 credit
- **Direct connection fallback** enabled (`ENABLE_DIRECT_FALLBACK=true`)
- System in **LOW_PROXY mode** (8 < 10 minimum threshold)

### The Problem
```
2026-02-11 11:33:31 [WARNING] [DutchyCorp] Proxy detection pattern found: 'proxy detected'
2026-02-11 11:33:31 [ERROR] [DutchyCorp] Proxy Detected - DutchyCorp blocks datacenter IPs
```

- Faucets (DutchyCorp, CoinPayU, AdBTC) detect cloud/datacenter IPs as proxies
- All cloud providers (Azure, AWS, DigitalOcean, Oracle) provide **datacenter IPs**
- Residential IPs cost money (2Captcha residential proxies: ~$3/GB)

---

## 🎯 **The Fundamental Challenge**

**You cannot get residential IPs for free from cloud providers.**

All free/student credits give you **datacenter IPs** which are:
- Listed in ASN databases as cloud providers
- Easily detected by anti-fraud systems
- Blocked by sites with aggressive proxy detection

| Provider | Cost | IP Type | Detection Risk |
|----------|------|---------|----------------|
| 2Captcha Residential | $3/GB | Residential | Low ✅ |
| Azure VMs | Credits | Datacenter | High ❌ |
| DigitalOcean Droplets | Credits | Datacenter | High ❌ |
| Oracle Cloud Free Tier | Free | Datacenter | High ❌ |
| AWS EC2 Free Tier | Free | Datacenter | High ❌ |

---

## 💡 **Practical Free Solutions**

### Solution 1: Strategic Direct Connection ✅ **RECOMMENDED**

**Status:** Already implemented, just optimize configuration

The bot already has direct connection fallback built-in. Configure it to use direct connections for problem sites:

**Current `.env` configuration:**
```bash
ENABLE_DIRECT_FALLBACK=true
PROXY_FALLBACK_THRESHOLD=2
```

**Optimization:** Create per-faucet routing rules

1. **Disable proxies for sites with aggressive detection:**

   Edit `.env`:
   ```bash
   # Sites that work better without proxy
   PROXY_BYPASS_FAUCETS=["freebitcoin","cointiply","firefaucet","dutchy","coinpayu","adbtc"]
   ```

2. **Use proxies only for sites that require them:**
   - Sites with IP-based rate limiting
   - Sites with geo-restrictions
   - Sites that don't have datacenter detection

**Pros:**
- ✅ Zero cost
- ✅ Already implemented
- ✅ Works with your home/VM IP
- ✅ No datacenter detection

**Cons:**
- ❌ Limited to one claim per IP per time period
- ❌ All accounts appear from same IP
- ❌ If your home IP gets banned, all accounts affected

---

### Solution 2: Optimize Azure VM Distribution 💰 **Using Your Credits**

Since you can't get residential IPs, maximize diversity with datacenter IPs across different:
- Regions (different IP ranges)
- ASNs (Autonomous System Numbers)
- Availability zones

**Action Plan:**

1. **Deploy Azure VMs in diverse regions** (use your $1000 credits):
   ```bash
   # Create VMs in different regions
   - West US 2 (existing)
   - East US
   - Central US
   - North Europe
   - Southeast Asia
   - Brazil South
   - Australia East
   - Japan East
   ```

2. **Use smallest VM size (B1s)** to maximize count:
   - Cost: ~$0.0104/hour = ~$7.50/month
   - Your $1000 credit = ~133 VM-months = ~16 VMs for 8 months

3. **Set up proxy servers on each VM:**
   ```bash
   # Install on each Azure VM
   sudo apt update
   sudo apt install squid -y
   
   # Configure Squid (/etc/squid/squid.conf)
   http_port 8888
   auth_param basic program /usr/lib/squid/basic_ncsa_auth /etc/squid/passwords
   auth_param basic realm proxy
   acl authenticated proxy_auth REQUIRED
   http_access allow authenticated
   
   # Create password
   sudo htpasswd -c /etc/squid/passwords proxyuser
   sudo systemctl restart squid
   
   # Open firewall
   sudo ufw allow 8888/tcp
   ```

4. **Add to config/azure_proxies.txt:**
   ```
   http://proxyuser:password@20.115.154.150:8888
   http://proxyuser:password@52.188.123.45:8888
   http://proxyuser:password@13.82.45.67:8888
   # ... add all 16+ VMs
   ```

5. **Enable in `.env`:**
   ```bash
   USE_AZURE_PROXIES=true
   PROXY_PROVIDER=azure
   ```

**Pros:**
- ✅ Free with your Azure credits
- ✅ 16+ different IP addresses
- ✅ Geographic diversity
- ✅ You control the infrastructure

**Cons:**
- ❌ Still datacenter IPs (detection risk remains)
- ❌ Setup time required
- ❌ Uses your Azure credits
- ❌ Sites with advanced detection will still block

---

### Solution 3: Oracle Cloud Always-Free Tier 🆓

Oracle Cloud offers **4 ARM-based VMs free forever** (no credit card needed after initial verification):

**Free Resources:**
- 4x ARM Ampere A1 VMs (4 OCPUs, 24 GB RAM total)
- Can split into 4 VMs with 1 OCPU, 6 GB RAM each
- Different IP addresses
- Different ASN from Azure

**Setup:**
1. Sign up: https://www.oracle.com/cloud/free/
2. Create 4 ARM instances in different regions
3. Install Squid proxy on each (same as Azure setup above)
4. Add to `config/oracle_proxies.txt`

**Pros:**
- ✅ Completely free forever
- ✅ Different ASN from Azure (more diversity)
- ✅ 4 additional IP addresses
- ✅ No cost

**Cons:**
- ❌ Still datacenter IPs
- ❌ Limited to 4 instances
- ❌ Slower ARM architecture
- ❌ Setup complexity

---

### Solution 4: DigitalOcean via GitHub Student Pack 🎓

**GitHub Student Pack includes:**
- $200 DigitalOcean credit (1 year)
- Can create ~26 droplets at $0.006/hour ($4.32/month each)

**Setup:**
1. Activate: https://education.github.com/pack
2. Redeem DigitalOcean credit
3. Create droplets in different regions (NYC, SF, London, Singapore, etc.)
4. Install Squid proxy on each
5. Add to `config/digitalocean_proxies.txt`

**Enable in `.env`:**
```bash
USE_DIGITALOCEAN_PROXIES=true
PROXY_PROVIDER=digitalocean
```

**Pros:**
- ✅ Free with student pack
- ✅ 26+ IP addresses from your $200 credit
- ✅ Different ASN from Azure
- ✅ Global regions

**Cons:**
- ❌ Still datacenter IPs
- ❌ Credit expires after 1 year
- ❌ Same detection issues

---

### Solution 5: IPv6 Rotation (If Available) 🌐

Some residential ISPs allocate huge IPv6 ranges (/64 = 18 quintillion addresses).

**Check if you have IPv6:**
```bash
# On your main VM
curl -6 https://ifconfig.me

# Check IPv6 range
ip -6 addr show

# If you see a /64 prefix, you have ~18 quintillion IPs!
```

**If you have IPv6:**

1. **Configure Squid with IPv6 rotation:**
   ```bash
   # /etc/squid/squid.conf
   acl to_ipv6 dst ipv6
   tcp_outgoing_address 2001:db8:1234:5678::1 to_ipv6
   tcp_outgoing_address 2001:db8:1234:5678::2 to_ipv6
   # ... add many more
   ```

2. **Script to generate random IPv6:**
   ```python
   import random
   prefix = "2001:db8:1234:5678:"  # Your /64 prefix
   suffix = f"{random.randint(0, 0xFFFFFFFFFFFFFFFF):016x}"
   ipv6 = prefix + ":".join([suffix[i:i+4] for i in range(0, 16, 4)])
   ```

**Pros:**
- ✅ Massive IP pool
- ✅ Residential ISP range (if from home)
- ✅ Very hard to block entire /64
- ✅ No cost

**Cons:**
- ❌ Requires IPv6 connectivity
- ❌ Not all sites support IPv6
- ❌ Your ISP must allow this
- ❌ Complex setup

---

## 🚀 **RECOMMENDED IMPLEMENTATION PLAN**

### Phase 1: Immediate (No Cost, 5 minutes)

Optimize existing direct connection fallback:

```bash
# Edit .env on VM
ssh azureuser@4.155.230.212

cd ~/Repositories/cryptobot
nano .env

# Update these lines:
ENABLE_DIRECT_FALLBACK=true
PROXY_FALLBACK_THRESHOLD=1  # Try direct faster
PROXY_BYPASS_FAUCETS=["dutchy","coinpayu","adbtc","freebitcoin"]

# Restart service
sudo systemctl restart faucet_worker
sudo systemctl status faucet_worker
```

**Result:** Sites with aggressive detection will use direct connection, bypassing datacenter IP detection.

---

### Phase 2: Free Expansion (This week)

Add Oracle Cloud Always-Free instances:

1. **Sign up for Oracle Cloud Free Tier**
   - https://www.oracle.com/cloud/free/
   - Get 4 ARM VMs free forever

2. **Create instances in different regions:**
   - Ashburn (us-ashburn-1)
   - Phoenix (us-phoenix-1)
   - Frankfurt (eu-frankfurt-1)
   - London (uk-london-1)

3. **Install Squid proxy** (see Solution 2 above)

4. **Add to config/oracle_proxies.txt:**
   ```
   http://proxyuser:password@oracle-ip-1:8888
   http://proxyuser:password@oracle-ip-2:8888
   http://proxyuser:password@oracle-ip-3:8888
   http://proxyuser:password@oracle-ip-4:8888
   ```

5. **Merge with existing Azure proxies:**
   ```bash
   cat config/oracle_proxies.txt >> config/azure_proxies.txt
   # Now you have 12+ proxies (8 Azure + 4 Oracle)
   ```

**Result:** 50% more proxies (8 → 12), exit LOW_PROXY mode, zero cost.

---

### Phase 3: Student Pack (This month)

Activate GitHub Student Developer Pack:

1. **Activate pack:**
   - https://education.github.com/pack
   - Verify student status

2. **Redeem DigitalOcean credit ($200):**
   - Create account
   - Add student pack coupon
   - Deploy 10-20 droplets in different regions

3. **Automated setup script:**
   ```bash
   # deploy/digitalocean_proxy_setup.sh
   #!/bin/bash
   
   REGIONS=("nyc1" "sfo3" "lon1" "sgp1" "fra1" "tor1" "blr1")
   
   for region in "${REGIONS[@]}"; do
       doctl compute droplet create \
           "proxy-$region" \
           --size s-1vcpu-1gb \
           --image ubuntu-24-04-x64 \
           --region $region \
           --ssh-keys YOUR_SSH_KEY_ID \
           --user-data-file cloud-init-squid.yml
   done
   ```

4. **Cloud-init script (cloud-init-squid.yml):**
   ```yaml
   #cloud-config
   package_update: true
   packages:
     - squid
     - apache2-utils
   
   runcmd:
     - echo "http_port 8888" >> /etc/squid/squid.conf
     - echo "auth_param basic program /usr/lib/squid/basic_ncsa_auth /etc/squid/passwords" >> /etc/squid/squid.conf
     - echo "acl authenticated proxy_auth REQUIRED" >> /etc/squid/squid.conf
     - echo "http_access allow authenticated" >> /etc/squid/squid.conf
     - htpasswd -bc /etc/squid/passwords proxyuser CHANGE_THIS_PASSWORD
     - systemctl restart squid
     - ufw allow 8888/tcp
   ```

**Result:** 20+ total proxies, different ASNs, still free.

---

### Phase 4: Azure Expansion (Next month)

If you still need more diversity, use Azure credits:

```bash
# Deploy 10 VMs across global regions using your $1000 credits
./deploy/azure_proxy_deployment.sh

# Cost: ~$75/month for 10 B1s VMs
# Your $1000 lasts ~13 months
```

---

## 📊 **Cost Comparison**

| Solution | Monthly Cost | Setup Time | IP Count | Detection Risk | Sustainability |
|----------|--------------|------------|----------|----------------|----------------|
| **Direct Connection** | $0 | 5 min | 1 | Low ✅ | ♾️ Forever |
| **Oracle Free Tier** | $0 | 2 hours | 4 | Medium | ♾️ Forever |
| **GitHub Student Pack** | $0* | 4 hours | 20+ | Medium | 1 year |
| **Azure VMs** | Credits | 4 hours | 16+ | Medium | 13 months |
| **2Captcha Residential** | $90/month | 5 min | ~100 | Very Low ✅ | $ required |

*Free for 1 year with student pack

---

## ⚠️ **Important Limitations**

### The Hard Truth About Free Proxies

**You cannot eliminate proxy detection with free datacenter IPs.**

Sites like DutchyCorp use services that maintain databases of:
- Cloud provider IP ranges (Azure, AWS, DigitalOcean, Oracle)
- Datacenter ASNs
- Hosting provider networks

**These IPs will always be detected as non-residential.**

### What This Means

1. **Accept some failures** - Sites with aggressive detection will always block datacenter IPs
2. **Use direct connection** - For those sites, direct connection is better
3. **Focus on ROI** - Only claim from faucets that work with your setup
4. **Consider paid residential proxies** - If ROI justifies the cost (~$90/month for 30GB)

---

## 🎯 **Final Recommendation**

### Best Strategy for Zero Cost

1. ✅ **Phase 1:** Enable direct connection for problem faucets (5 minutes, $0)
2. ✅ **Phase 2:** Add Oracle Cloud free tier (2 hours, $0 forever)
3. ✅ **Phase 3:** Use GitHub Student Pack for DigitalOcean (4 hours, $0 for 1 year)
4. ⏸️ **Phase 4:** Only use Azure credits if you need 30+ total proxies

### Expected Results

- **Total proxies:** 24+ (8 Azure + 4 Oracle + 12 DigitalOcean)
- **Monthly cost:** $0 (using only credits)
- **Setup time:** ~6 hours
- **Duration:** 12+ months of zero-cost operation

### Reality Check

Even with 24+ proxies, sites with advanced detection will still block datacenter IPs. The **direct connection fallback** is your most reliable solution for those sites.

### When to Consider Paid Residential Proxies

If your faucet earnings exceed **$100/month**, investing $90/month in residential proxies becomes profitable. Calculate your ROI:

```
Monthly earnings: $X
Proxy cost: $90
Net profit: $X - $90

If net profit > 0 → Buy residential proxies
If net profit < 0 → Use free datacenter + direct connection
```

---

## 📝 **Next Steps**

1. **Today:** Implement Phase 1 (direct connection optimization)
2. **This week:** Sign up for Oracle Cloud and add 4 free VMs
3. **This month:** Activate GitHub Student Pack and deploy DigitalOcean droplets
4. **Monitor:** Track which faucets work with datacenter IPs vs need residential
5. **Optimize:** Disable faucets that consistently fail, focus on ones that work

---

## 🔧 **Implementation Scripts**

### Script 1: Test Direct Connection

```bash
#!/bin/bash
# Test which faucets work without proxy

cd ~/Repositories/cryptobot

# Test each faucet with direct connection
for faucet in dutchy coinpayu adbtc faucetcrypto; do
    echo "Testing $faucet with direct connection..."
    HEADLESS=true python main.py --single $faucet --once --no-proxy
    sleep 5
done
```

### Script 2: Deploy Oracle Proxies

See `docs/ORACLE_CLOUD_PROXY_SETUP.md` (create this)

### Script 3: Deploy DigitalOcean Proxies

See `docs/DIGITALOCEAN_PROXY_SETUP.md` (create this)

---

## 📚 **Additional Resources**

- [Oracle Cloud Free Tier](https://www.oracle.com/cloud/free/)
- [GitHub Student Developer Pack](https://education.github.com/pack)
- [Squid Proxy Documentation](http://www.squid-cache.org/Doc/)
- [IPv6 Rotation Guide](https://github.com/bendavis78/ipv6-proxy)

---

**Last Updated:** February 11, 2026  
**Status:** Ready for implementation  
**Estimated Total Cost:** $0 (using only free credits)
