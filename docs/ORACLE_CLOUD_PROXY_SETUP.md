# Oracle Cloud Free Tier Proxy Setup

**Goal:** Add 4 free forever proxy servers using Oracle Cloud's Always-Free tier

**Cost:** $0 (free forever, no credit card charges)  
**Time:** ~2 hours  
**Result:** 4 additional proxy IP addresses in different regions

---

## 🎯 **What You Get**

Oracle Cloud Always-Free tier includes:
- **4 ARM-based Ampere A1 instances** (free forever)
- **Total: 4 OCPUs + 24 GB RAM** (can split into 4 VMs: 1 OCPU + 6 GB each)
- **Different ASN** from Azure (more IP diversity)
- **Global regions:** Ashburn, Phoenix, Frankfurt, London, Tokyo, etc.

---

## 📋 **Prerequisites**

- Email address (preferably .edu for student verification)
- Phone number for verification
- Credit card for identity verification (will NOT be charged)
- SSH key pair for VM access

---

## 🚀 **Step-by-Step Setup**

### Step 1: Create Oracle Cloud Account

1. **Sign up:**
   - Go to https://www.oracle.com/cloud/free/
   - Click "Start for free"
   - Fill in details (use your student email if you have one)

2. **Verify identity:**
   - Provide credit card (for verification only, won't be charged)
   - Verify phone number
   - Wait for account activation (1-2 hours)

3. **Sign in:**
   - https://cloud.oracle.com/
   - Choose your home region (can't change later!)
   - Recommended: US East (Ashburn) - best availability

---

### Step 2: Create SSH Key Pair

On your local Windows machine:

```powershell
# Open PowerShell
cd ~\.ssh

# Generate SSH key
ssh-keygen -t rsa -b 4096 -f oracle_cloud_key -C "oracle-proxy"

# View public key (you'll need this)
cat oracle_cloud_key.pub
```

Keep this window open - you'll copy the public key content later.

---

### Step 3: Create First ARM Instance

1. **Navigate to Compute:**
   - Oracle Cloud Console → ☰ Menu → Compute → Instances
   - Click "Create Instance"

2. **Configure instance:**

   **Name:** `proxy-ashburn-1`

   **Placement:**
   - Availability Domain: AD-1 (or any available)

   **Image:**
   - Click "Change Image"
   - Select "Canonical Ubuntu 24.04"
   - ARM-based (Ampere)
   - Click "Select Image"

   **Shape:**
   - Click "Change Shape"
   - Select "Ampere" (ARM)
   - Choose "VM.Standard.A1.Flex"
   - Set OCPUs: 1
   - Set Memory: 6 GB
   - Click "Select Shape"

   **Networking:**
   - Use default VCN (or create new)
   - Assign a public IPv4 address: ✅ YES
   - Use network security group: ❌ NO

   **SSH Keys:**
   - Paste your public key from Step 2
   - Or upload `oracle_cloud_key.pub` file

3. **Create:**
   - Click "Create"
   - Wait 2-3 minutes for provisioning
   - Note the **Public IP address** (e.g., 129.146.123.45)

---

### Step 4: Configure Firewall

1. **In Oracle Cloud Console:**
   - Go to: Networking → Virtual Cloud Networks
   - Click on your VCN (e.g., "vcn-20260211-1234")
   - Click "Security Lists" → "Default Security List"
   - Click "Add Ingress Rules"

   **Ingress Rule:**
   - Source CIDR: `0.0.0.0/0`
   - IP Protocol: TCP
   - Destination Port Range: `8888`
   - Description: "Squid Proxy"
   - Click "Add Ingress Rules"

2. **On the VM (we'll do this in Step 5):**
   - Configure UFW firewall

---

### Step 5: Install Squid Proxy

From your Windows machine, SSH to the new VM:

```powershell
# Use the public IP from Step 3
ssh -i ~\.ssh\oracle_cloud_key ubuntu@129.146.123.45
```

Once connected, run:

```bash
# Update system
sudo apt update && sudo apt upgrade -y

# Install Squid and password tools
sudo apt install -y squid apache2-utils

# Backup original config
sudo cp /etc/squid/squid.conf /etc/squid/squid.conf.backup

# Create new minimal config
sudo tee /etc/squid/squid.conf > /dev/null <<'EOF'
# Squid Proxy Configuration for Cryptobot
http_port 8888

# Authentication
auth_param basic program /usr/lib/squid/basic_ncsa_auth /etc/squid/passwords
auth_param basic realm Proxy Authentication
auth_param basic credentialsttl 2 hours

# ACLs
acl authenticated proxy_auth REQUIRED
acl safe_ports port 80          # http
acl safe_ports port 443         # https
acl safe_ports port 8080        # http-alt
acl CONNECT method CONNECT

# Access rules
http_access deny !safe_ports
http_access deny CONNECT !safe_ports
http_access allow authenticated
http_access deny all

# Disable caching (we're a forward proxy)
cache deny all

# Logging
access_log /var/log/squid/access.log squid
cache_log /var/log/squid/cache.log
EOF

# Create proxy user (change password!)
sudo htpasswd -bc /etc/squid/passwords proxyuser 'YourSecurePassword123!'

# Set permissions
sudo chmod 640 /etc/squid/passwords
sudo chown proxy:proxy /etc/squid/passwords

# Configure Ubuntu firewall
sudo ufw allow 22/tcp    # SSH
sudo ufw allow 8888/tcp  # Proxy
sudo ufw --force enable

# Start Squid
sudo systemctl restart squid
sudo systemctl enable squid

# Check status
sudo systemctl status squid

# Test locally
curl -x http://proxyuser:YourSecurePassword123!@localhost:8888 https://ifconfig.me
```

If the last command shows an IP address, your proxy is working! ✅

---

### Step 6: Test from Your Main VM

From your cryptobot VM (4.155.230.212):

```bash
# Test the Oracle proxy
curl -x http://proxyuser:YourSecurePassword123!@129.146.123.45:8888 https://ifconfig.me

# Should show the Oracle Cloud IP (129.146.123.45)
# If it shows your Oracle IP, the proxy works!

# Test with timeout
timeout 10 curl -x http://proxyuser:YourSecurePassword123!@129.146.123.45:8888 https://www.google.com
```

---

### Step 7: Create 3 More Instances

Repeat Steps 3-6 for three more regions:

**Instance 2: Phoenix**
- Region: US West (Phoenix)
- Name: `proxy-phoenix-1`
- Note IP: e.g., 138.1.45.67

**Instance 3: Frankfurt**
- Region: EU Central (Frankfurt)
- Name: `proxy-frankfurt-1`
- Note IP: e.g., 130.61.78.90

**Instance 4: London**
- Region: UK South (London)
- Name: `proxy-london-1`
- Note IP: e.g., 132.145.23.45

**Note:** You can only create instances in your **home region** in the free tier. To use multiple regions, you need to:
- Create account → Set home region → Create 1 instance
- OR split your 4 OCPUs across 4 instances in the SAME region

**Recommendation:** Create all 4 in one region (same datacenter, different IPs) for simplicity.

---

### Step 8: Add to Cryptobot Config

On your main VM (4.155.230.212):

```bash
cd ~/Repositories/cryptobot

# Create Oracle proxies file
cat > config/oracle_proxies.txt <<'EOF'
http://proxyuser:YourSecurePassword123!@129.146.123.45:8888
http://proxyuser:YourSecurePassword123!@138.1.45.67:8888
http://proxyuser:YourSecurePassword123!@130.61.78.90:8888
http://proxyuser:YourSecurePassword123!@132.145.23.45:8888
EOF

# Merge with existing Azure proxies
cat config/oracle_proxies.txt >> config/azure_proxies.txt

# Verify
echo "Total proxies:"
wc -l config/azure_proxies.txt
```

---

### Step 9: Restart Cryptobot

```bash
# Restart the service to pick up new proxies
sudo systemctl restart faucet_worker

# Check logs
journalctl -u faucet_worker --since "1 minute ago" | grep -i proxy

# Should see something like:
# [INFO] [AZURE] Loaded 12 proxies
# [INFO] [OK] Total proxies loaded: 12
```

---

### Step 10: Monitor Performance

```bash
# Watch claims in real-time
tail -f ~/Repositories/cryptobot/logs/faucet_bot.log | grep -E '(Executing|SUCCESS|FAILED)'

# Check proxy usage
tail -f ~/Repositories/cryptobot/logs/faucet_bot.log | grep -i "proxy"

# Check proxy health
cat ~/Repositories/cryptobot/config/proxy_health.json | python -m json.tool
```

---

## 🔧 **Troubleshooting**

### Issue: "No space available" when creating instance

**Solution:** Oracle free tier has limited ARM capacity per region.

1. Try different availability domain (AD-1, AD-2, AD-3)
2. Try at different time of day (less busy hours)
3. Try different region
4. Be persistent - keep trying every few hours

### Issue: Can't connect to proxy (connection refused)

**Checklist:**
1. ✅ Security List has ingress rule for port 8888
2. ✅ UFW firewall on VM allows port 8888 (`sudo ufw status`)
3. ✅ Squid is running (`sudo systemctl status squid`)
4. ✅ Using correct IP address (check Oracle console)
5. ✅ Password doesn't have special chars that need escaping

**Test locally on the Oracle VM:**
```bash
# This should work
curl -x http://proxyuser:password@localhost:8888 https://ifconfig.me

# This should show the VM's public IP
curl https://ifconfig.me
```

### Issue: Squid authentication failed

**Fix:**
```bash
# Recreate password file
sudo rm /etc/squid/passwords
sudo htpasswd -bc /etc/squid/passwords proxyuser 'NewPassword123'
sudo chown proxy:proxy /etc/squid/passwords
sudo chmod 640 /etc/squid/passwords
sudo systemctl restart squid

# Test
curl -x http://proxyuser:NewPassword123@localhost:8888 https://ifconfig.me
```

### Issue: Proxy works but very slow

**Check latency:**
```bash
# From your main VM
time curl -x http://proxyuser:password@ORACLE_IP:8888 https://www.google.com

# Should be < 3 seconds
# If > 5 seconds, the region is too far or overloaded
```

---

## 📊 **Expected Results**

**Before:**
- 8 Azure proxies
- System in LOW_PROXY mode
- Some proxy detection errors

**After:**
- 12 total proxies (8 Azure + 4 Oracle)
- Exit LOW_PROXY mode ✅
- More IP diversity
- Different ASN (Oracle Cloud vs Microsoft Azure)

---

## 💡 **Optimization Tips**

1. **Use different passwords** for each proxy (security)
2. **Label proxies** by region in config comments
3. **Monitor latency** - disable slow proxies
4. **Rotate regularly** - Oracle IPs can still get flagged as datacenter
5. **Combine with direct connection** for best results

---

## 🔒 **Security Best Practices**

1. **Change default password** immediately
2. **Use strong passwords** (20+ chars, mixed case, numbers, symbols)
3. **Only allow port 8888** in firewall (close all other ports except 22)
4. **Keep system updated:** `sudo apt update && sudo apt upgrade`
5. **Monitor access logs:** `sudo tail -f /var/log/squid/access.log`
6. **Disable SSH password auth** (key-only)

---

## 📈 **Next Steps**

After Oracle setup:
1. ✅ Monitor for 24 hours
2. 🎓 Activate GitHub Student Pack for DigitalOcean
3. 💰 Consider Azure expansion if needed (use credits strategically)
4. 📊 Track which faucets work best with which proxy provider

---

**Total Cost:** $0  
**Time Investment:** 2 hours  
**Benefit:** 4 free proxies forever  
**Status:** Always-Free (no expiration)
