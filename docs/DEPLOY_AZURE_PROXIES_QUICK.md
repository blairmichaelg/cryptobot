# Quick Deploy: 10 More Azure Proxies in 10 Minutes

**Best solution for your situation:** Use your existing Azure credits to deploy more VMs!

**Why this works:**
- ✅ You already have $1000 Azure credits
- ✅ You're already logged into Azure
- ✅ NO credit card needed
- ✅ You have 8 Azure VMs working already
- ✅ Just deploy 10 more in different regions

---

## 🚀 **One-Command Deployment**

**Open PowerShell on your Windows machine:**

```powershell
cd C:\Users\azureuser\Repositories\cryptobot

# Deploy 10 VMs across different regions (default)
.\scripts\deploy_azure_proxies.ps1

# Or specify custom count
.\scripts\deploy_azure_proxies.ps1 -VmCount 15

# Dry run to see what would happen
.\scripts\deploy_azure_proxies.ps1 -DryRun
```

**The script will:**
1. Deploy VMs in 10 different Azure regions
2. Auto-install Squid proxy on each
3. Configure firewall automatically
4. Generate all proxy URLs
5. Save to `azure_proxies_new.txt`

**Total time:** ~10 minutes (1 min per VM)

---

## 📋 **After Deployment**

The script will output commands for you. Follow them:

**1. Upload proxy file to your main VM:**
```powershell
scp .\azure_proxies_new.txt azureuser@4.155.230.212:~/Repositories/cryptobot/config/
```

**2. SSH and merge proxies:**
```bash
ssh azureuser@4.155.230.212
cd ~/Repositories/cryptobot
cat config/azure_proxies_new.txt >> config/azure_proxies.txt
wc -l config/azure_proxies.txt  # Should show 18 total (8 old + 10 new)
```

**3. Restart bot:**
```bash
sudo systemctl restart faucet_worker
```

**4. Verify:**
```bash
tail -f logs/faucet_bot.log | grep -i proxy
```

---

## 💰 **Cost with Your Credits**

| VMs | Monthly Cost | Your $1000 Lasts | Total IPs |
|-----|--------------|------------------|-----------|
| 8 (current) | $60 | 16 months | 8 |
| +10 more | +$75 | 7 months | 18 |
| +15 more | +$112 | 5 months | 23 |

**Recommended:** Deploy 10 more = 18 total proxies for 7 months

---

## 🗺️ **Regions Used (Maximum Diversity)**

The script deploys to these regions for different IP ranges:

1. East US
2. West US 2
3. Central US
4. North Europe
5. West Europe
6. UK South
7. Southeast Asia
8. Australia East
9. Japan East
10. Brazil South

**10 regions = 10 different Microsoft IP ranges = Better for avoiding detection**

---

## ⚠️ **Troubleshooting**

### "Azure CLI not found"

Install Azure CLI:
```powershell
winget install Microsoft.AzureCLI
```

Then login:
```powershell
az login
```

### "Insufficient quota" error

Some regions may hit quota limits. The script will skip them and continue with others.

### "Port 8888 not opening"

Check VM's Network Security Group in Azure Portal, manually add inbound rule for port 8888.

---

## 🎯 **Alternative: Deploy Manually (If Script Fails)**

If PowerShell script doesn't work, use Azure Portal:

1. Go to portal.azure.com
2. Create VM → Ubuntu 24.04, Standard_B1s, region: `eastus`
3. Copy cloud-init from `scripts/deploy_azure_proxies.ps1`
4. Paste in "Advanced" → "Custom data"
5. Review + Create
6. Open port 8888 in NSG
7. Get public IP
8. Proxy URL: `http://proxyuser:PASSWORD@IP:8888`
9. Repeat for each region

---

## 🚀 **Do It Now!**

```powershell
# Open PowerShell
cd C:\Users\azureuser\Repositories\cryptobot
.\scripts\deploy_azure_proxies.ps1 -VmCount 10
```

**10 minutes later, you'll have 18 total proxies!** 🎉
