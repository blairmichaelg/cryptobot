# Azure-Based Proxy Solution for Cryptobot

## Overview
Use Azure VM-based proxies instead of 2Captcha residential proxies to bypass Cloudflare blocking.

## Benefits
- ✅ Azure IPs not on Cloudflare blocklists
- ✅ Full control over proxy infrastructure
- ✅ Covered by $1000 Azure startup credit
- ✅ Fast, reliable connections
- ✅ Can rotate IPs by creating multiple VMs

## Solution: Azure VM SOCKS/HTTP Proxies

### Option 1: Tinyproxy on Azure VMs (Recommended)

Deploy lightweight HTTP proxies on Azure VMs across different regions.

**Cost Estimate**: ~$5-10/month per VM (B1s instance)
**Setup Time**: 15 minutes

#### Step 1: Create Azure VMs

```bash
# Create resource group
az group create --name ProxyFarmRG --location westus2

# Create 3 VMs in different regions for IP diversity
az vm create \
  --resource-group ProxyFarmRG \
  --name proxy-vm-1 \
  --image Ubuntu2204 \
  --size Standard_B1s \
  --location westus2 \
  --admin-username azureuser \
  --generate-ssh-keys \
  --public-ip-sku Standard

az vm create \
  --resource-group ProxyFarmRG \
  --name proxy-vm-2 \
  --image Ubuntu2204 \
  --size Standard_B1s \
  --location eastus \
  --admin-username azureuser \
  --generate-ssh-keys \
  --public-ip-sku Standard

az vm create \
  --resource-group ProxyFarmRG \
  --name proxy-vm-3 \
  --image Ubuntu2204 \
  --size Standard_B1s \
  --location westeurope \
  --admin-username azureuser \
  --generate-ssh-keys \
  --public-ip-sku Standard
```

#### Step 2: Install Tinyproxy on Each VM

```bash
# SSH to each VM and run:
sudo apt update
sudo apt install -y tinyproxy

# Configure Tinyproxy
sudo tee /etc/tinyproxy/tinyproxy.conf > /dev/null <<EOF
Port 8888
Timeout 600
DefaultErrorFile "/usr/share/tinyproxy/default.html"
StatFile "/usr/share/tinyproxy/stats.html"
LogLevel Info
MaxClients 100
MinSpareServers 5
MaxSpareServers 20
StartServers 10
MaxRequestsPerChild 0
ViaProxyName "tinyproxy"
Allow 127.0.0.1
Allow <YOUR_FAUCET_VM_IP>
DisableViaHeader Yes
EOF

# Restart Tinyproxy
sudo systemctl restart tinyproxy
sudo systemctl enable tinyproxy
```

#### Step 3: Open Firewall Ports

```bash
# On each VM
sudo ufw allow 8888/tcp
sudo ufw enable

# Or via Azure CLI
az vm open-port --resource-group ProxyFarmRG --name proxy-vm-1 --port 8888 --priority 1001
az vm open-port --resource-group ProxyFarmRG --name proxy-vm-2 --port 8888 --priority 1001
az vm open-port --resource-group ProxyFarmRG --name proxy-vm-3 --port 8888 --priority 1001
```

#### Step 4: Get Public IPs

```bash
az vm list-ip-addresses --resource-group ProxyFarmRG --output table
```

#### Step 5: Update Cryptobot Config

Create `config/azure_proxies.txt`:
```
http://<proxy-vm-1-ip>:8888
http://<proxy-vm-2-ip>:8888
http://<proxy-vm-3-ip>:8888
```

Update `.env`:
```env
USE_2CAPTCHA_PROXIES=false
# ProxyManager will load from config/proxies.txt
```

---

### Option 2: Squid Proxy (More Features)

Squid offers caching and more control but uses slightly more resources.

```bash
# Install Squid
sudo apt update
sudo apt install -y squid

# Configure Squid
sudo tee /etc/squid/squid.conf > /dev/null <<EOF
http_port 3128

# Allow your faucet VM
acl faucet_vm src <FAUCET_VM_IP>
http_access allow faucet_vm

# Deny all others
http_access deny all

# Hide proxy headers
forwarded_for delete
request_header_access Via deny all
request_header_access X-Forwarded-For deny all

# Cache settings (optional)
cache deny all
EOF

# Restart Squid
sudo systemctl restart squid
sudo systemctl enable squid

# Open port
sudo ufw allow 3128/tcp
az vm open-port --resource-group ProxyFarmRG --name proxy-vm-1 --port 3128
```

---

### Option 3: Premium - Azure Load Balancer with Multiple VMs

For maximum performance and IP rotation:

1. Deploy 10+ VMs across regions
2. Use Azure Load Balancer to rotate between them
3. Each connection gets a different Azure IP
4. Cost: ~$50-100/month (covered by your $1000 credit for 10+ months)

---

## Testing Your Azure Proxies

```bash
# Test from DevNode01 VM
curl -x http://<proxy-vm-1-ip>:8888 https://api.ipify.org
curl -x http://<proxy-vm-2-ip>:8888 https://api.ipify.org

# Test Cloudflare sites
curl -x http://<proxy-vm-1-ip>:8888 -I https://autofaucet.dutchycorp.space/login.php
```

---

## Cost Management

### B1s VM Pricing (~$0.007/hour)
- 1 CPU, 1GB RAM
- ~$5/month per VM
- 10 VMs = $50/month
- Your $1000 credit lasts ~20 months

### B1ms VM Pricing (~$0.02/hour)
- 1 CPU, 2GB RAM  
- ~$15/month per VM
- Better for high-traffic scenarios

---

## Automation Script

Create `deploy/setup_azure_proxies.sh`:

```bash
#!/bin/bash
REGIONS=("westus2" "eastus" "centralus" "westeurope" "eastasia")
RG="ProxyFarmRG"
FAUCET_VM_IP="<DevNode01_PRIVATE_IP>"

az group create --name $RG --location westus2

for i in "${!REGIONS[@]}"; do
  echo "Creating proxy-vm-$i in ${REGIONS[$i]}"
  az vm create \
    --resource-group $RG \
    --name proxy-vm-$i \
    --image Ubuntu2204 \
    --size Standard_B1s \
    --location ${REGIONS[$i]} \
    --admin-username azureuser \
    --generate-ssh-keys \
    --public-ip-sku Standard \
    --no-wait
done

# Wait for all VMs to be created
az vm wait --resource-group $RG --name proxy-vm-0 --created

# Get IPs and configure proxies
echo "Configuring Tinyproxy on all VMs..."
for i in "${!REGIONS[@]}"; do
  VM_IP=$(az vm list-ip-addresses -g $RG -n proxy-vm-$i --query "[0].virtualMachine.network.publicIpAddresses[0].ipAddress" -o tsv)
  
  ssh azureuser@$VM_IP << 'ENDSSH'
    sudo apt update -qq
    sudo apt install -y tinyproxy
    sudo sed -i "s/^Port .*/Port 8888/" /etc/tinyproxy/tinyproxy.conf
    echo "Allow $FAUCET_VM_IP" | sudo tee -a /etc/tinyproxy/tinyproxy.conf
    sudo systemctl restart tinyproxy
    sudo systemctl enable tinyproxy
    sudo ufw allow 8888/tcp -y
    sudo ufw --force enable
ENDSSH
  
  echo "http://$VM_IP:8888" >> config/azure_proxies.txt
  az vm open-port -g $RG -n proxy-vm-$i --port 8888 --priority 100$i
done

echo "✅ Azure proxy farm deployed!"
cat config/azure_proxies.txt
```

---

## Integration with Cryptobot

Update `core/proxy_manager.py` to support direct HTTP proxies:

```python
# Load Azure proxies if USE_2CAPTCHA_PROXIES is false
if not self.settings.use_2captcha_proxies:
    azure_proxy_file = Path("config/azure_proxies.txt")
    if azure_proxy_file.exists():
        with open(azure_proxy_file) as f:
            self.proxies = [line.strip() for line in f if line.strip()]
        logger.info(f"Loaded {len(self.proxies)} Azure VM proxies")
```

---

## Next Steps

1. **Claim your GitHub Student Pack**: https://education.github.com/pack
2. **Activate Azure for Students**: $100 free credit (in addition to your $1000 startup credit)
3. **Deploy 5-10 proxy VMs** across different regions
4. **Test against Cloudflare sites**
5. **Monitor costs** in Azure Portal (should be <$100/month for 10 VMs)

---

## Alternative: DigitalOcean ($200 Free from GitHub Pack)

You also get $200 DigitalOcean credit for 1 year. You can use the same setup:

```bash
# Create Droplet
doctl compute droplet create proxy-do-1 \
  --region nyc1 \
  --size s-1vcpu-1gb \
  --image ubuntu-22-04-x64 \
  --ssh-keys <your-key>

# Same Tinyproxy setup as above
```

---

## Comparison

| Solution | Monthly Cost | IPs Available | Cloudflare Block Risk |
|----------|--------------|---------------|----------------------|
| 2Captcha Residential | $15-50 | 1000s (shared) | **HIGH** ✗ |
| Azure VMs | $50-100 | 5-20 (dedicated) | **LOW** ✓ |
| DigitalOcean VMs | $50-100 | 5-20 (dedicated) | **LOW** ✓ |
| Bright Data | $500+ | 1000s (shared) | **MEDIUM** ? |

**Recommendation**: Start with 5 Azure VMs ($25/month) covered by your $1000 credit.
