# Oracle Cloud Free Tier - Quick Setup Guide

**Time:** 10 minutes per VM  
**Cost:** $0 (free forever)  
**Result:** 4 additional proxy IPs

---

## 🚀 **Fastest Path to 4 Free Proxies**

### Step 1: Create Oracle Cloud Account (5 minutes)

1. **Sign up:** https://signup.cloud.oracle.com/
   - Use your email (student email if you have one)
   - Verify phone number
   - Add credit card (for verification only - **will NOT be charged**)

2. **Choose home region** (You can't change this later!)
   - **Recommended:** US East (Ashburn) - best availability
   - Alternative: US West (Phoenix) or EU (Frankfurt)

3. **Wait for activation** (~30-60 minutes after signup)
   - You'll get an email when ready
   - Check spam folder if you don't see it

---

### Step 2: Create SSH Key (1 minute)

**On your Windows machine:**

```powershell
# Open PowerShell
ssh-keygen -t rsa -b 4096 -f ~\.ssh\oracle_key -N ""

# View public key (copy this - you'll need it)
cat ~\.ssh\oracle_key.pub
```

Keep this window open.

---

### Step 3: Create Oracle VM (3 minutes each)

1. **Go to:** https://cloud.oracle.com/ → Sign in
2. **Navigate:** ☰ Menu → Compute → Instances
3. **Click:** "Create Instance"

**Configure:**

| Setting | Value |
|---------|-------|
| Name | `proxy-oracle-1` |
| Image | Ubuntu 24.04 (Canonical) |
| Shape | VM.Standard.A1.Flex (ARM) |
| OCPUs | 1 |
| Memory | 6 GB |
| Network | Keep default VCN |
| Public IP | ✅ Assign |
| SSH Key | Paste your public key from Step 2 |

4. **Click:** "Create"
5. **Wait 2-3 minutes** for provisioning
6. **Copy the Public IP address** (e.g., 129.146.123.45)

---

### Step 4: Configure Firewall (1 minute)

1. **In Oracle Console:**
   - Go to: Networking → Virtual Cloud Networks
   - Click your VCN → Security Lists → Default Security List
   - Click "Add Ingress Rules"

**Add Rule:**
- Source CIDR: `0.0.0.0/0`
- IP Protocol: TCP
- Destination Port: `8888`
- Description: "Squid Proxy"
- Click "Add"

---

### Step 5: Install Proxy (30 seconds)

**From your Windows machine:**

```powershell
# SSH to the Oracle VM (use the IP from Step 3)
ssh -i ~\.ssh\oracle_key ubuntu@129.146.123.45

# Download and run auto-setup script
curl -sSL https://raw.githubusercontent.com/blairmichaelg/cryptobot/master/scripts/oracle_vm_auto_setup.sh | bash
```

The script will output something like:

```
✅ Setup Complete!
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
📋 PROXY DETAILS
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

URL: http://proxyuser:Abc123Xyz789@129.146.123.45:8888

Add this to your cryptobot VM:
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
echo 'http://proxyuser:Abc123Xyz789@129.146.123.45:8888' >> ~/Repositories/cryptobot/config/oracle_proxies.txt
```

**COPY AND SAVE THIS OUTPUT!**

---

### Step 6: Add to Cryptobot (30 seconds)

**SSH to your main VM:**

```bash
ssh azureuser@4.155.230.212

# Add the Oracle proxy (use the command from setup output)
echo 'http://proxyuser:Abc123Xyz789@129.146.123.45:8888' >> ~/Repositories/cryptobot/config/oracle_proxies.txt

# Merge with Azure proxies
cat ~/Repositories/cryptobot/config/oracle_proxies.txt >> ~/Repositories/cryptobot/config/azure_proxies.txt

# Check total
wc -l ~/Repositories/cryptobot/config/azure_proxies.txt

# Restart bot
sudo systemctl restart faucet_worker
```

---

### Step 7: Repeat for 3 More VMs

Create 3 more instances (repeat Steps 3-6):

- `proxy-oracle-2`
- `proxy-oracle-3`
- `proxy-oracle-4`

**Total time:** 12-15 minutes for all 4 VMs

---

## 📊 **Expected Result**

**Before:**
- 8 Azure proxies
- System in LOW_PROXY mode

**After:**
- 12 total proxies (8 Azure + 4 Oracle)
- ✅ Exit LOW_PROXY mode
- ✅ Different ASN (Oracle Cloud vs Microsoft Azure)
- ✅ Free forever (no expiration)

---

## 🔧 **Troubleshooting**

### "Out of host capacity"

Oracle free tier has limited ARM capacity. Solutions:

1. Try different availability domain (AD-1, AD-2, AD-3)
2. Try at different time (early morning UTC is best)
3. Try different region (switch to Phoenix or Frankfurt)
4. Keep trying - capacity refreshes hourly

### Can't SSH to VM

```bash
# Check if using correct key
ssh -i ~\.ssh\oracle_key ubuntu@ORACLE_IP

# Verify firewall allows SSH
# Oracle Console → Instance → Details
# Check "Primary VNIC" has security list with SSH rule
```

### Proxy connection refused

```bash
# SSH to Oracle VM
ssh -i ~\.ssh\oracle_key ubuntu@ORACLE_IP

# Check Squid status
sudo systemctl status squid

# Check firewall
sudo ufw status

# Test locally
curl -x http://proxyuser:PASSWORD@localhost:8888 https://ifconfig.me
```

---

## 💰 **Cost Breakdown**

| Resource | Cost | Forever? |
|----------|------|----------|
| 4x ARM VMs | $0 | ✅ Yes |
| 200 GB bandwidth/month | $0 | ✅ Yes |
| Outbound traffic | $0 | ✅ Yes |

**Total: $0/month forever**

---

## 🎯 **Next Steps After Setup**

1. **Monitor proxy health:**
   ```bash
   ssh azureuser@4.155.230.212 "tail -f ~/Repositories/cryptobot/logs/faucet_bot.log | grep proxy"
   ```

2. **Check proxy count:**
   ```bash
   ssh azureuser@4.155.230.212 "cat ~/Repositories/cryptobot/config/azure_proxies.txt | wc -l"
   ```

3. **Verify service status:**
   ```bash
   ssh azureuser@4.155.230.212 "sudo systemctl status faucet_worker"
   ```

---

## 📝 **Important Notes**

- ✅ Oracle free tier is **actually free forever** (not a trial)
- ✅ No credit card charges (ever)
- ✅ 4 VMs is the maximum for free tier
- ⚠️ Can only create VMs in your home region (choose wisely)
- ⚠️ Keep VMs running - stopped VMs count toward limit
- ⚠️ Backup your SSH key - can't access VMs without it

---

**Need help?** Check the full guide: [docs/ORACLE_CLOUD_PROXY_SETUP.md](ORACLE_CLOUD_PROXY_SETUP.md)
