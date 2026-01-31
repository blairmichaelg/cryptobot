# Azure Proxy Infrastructure Fix

## Date: 2026-01-31

## Problem
- Production system stuck in LOW_PROXY mode despite deploying 8 Azure VMs
- Proxy count: 11 total (3 DigitalOcean + 8 Azure)
- Threshold: 10 healthy proxies
- Issue: Azure proxies weren't accessible due to missing NSG rules and Tinyproxy configuration

## Root Cause Analysis

### Issue 1: Orchestrator Proxy Health Check
The orchestrator determines operation mode based on **healthy** proxy count, not total count:

```python
# core/orchestrator.py line 957-962
healthy_proxies = len([
    p for p in self.proxy_manager.proxies
    if not self.proxy_manager.get_proxy_stats(p).get("is_dead")
])
```

This means proxies must be:
1. Loaded into the proxy list
2. NOT marked as dead in proxy health tracking
3. Successfully tested/validated

### Issue 2: Network Security Groups (NSG)
Azure VMs deployed without allowing inbound traffic on port 8888:
- Default NSG only allows SSH (22) and optionally RDP (3389)
- Tinyproxy listens on port 8888
- All connection attempts were blocked at the firewall level

### Issue 3: Tinyproxy Access Control
Default Tinyproxy configuration denies all connections:
- Returns "HTTP/1.0 403 Access denied"
- Needs `Allow 0.0.0.0/0` directive to accept connections from anywhere
- Configuration was missing from cloud-init script

## Solution Implemented

### Step 1: Add NSG Rules
Created inbound security rules for all 8 Azure VMs:

```powershell
az network nsg rule create \
    --resource-group InfraServicesRG \
    --nsg-name edge-gateway-{vm}-NSG \
    --name AllowTinyproxy \
    --priority 1001 \
    --source-address-prefixes '*' \
    --destination-port-ranges 8888 \
    --access Allow \
    --protocol Tcp
```

**Result**: All 8 NSGs updated successfully ✓

### Step 2: Configure Tinyproxy
Updated `/etc/tinyproxy/tinyproxy.conf` on all VMs:

```conf
User tinyproxy
Group tinyproxy
Port 8888
Timeout 600
DefaultErrorFile "/usr/share/tinyproxy/default.html"
StatFile "/usr/share/tinyproxy/stats.html"
LogFile "/var/log/tinyproxy/tinyproxy.log"
LogLevel Info
MaxClients 100
MinSpareServers 5
MaxSpareServers 20
StartServers 10
MaxRequestsPerChild 0
Allow 0.0.0.0/0  # KEY FIX: Allow all connections
ViaProxyName "tinyproxy"
DisableViaHeader No
```

**Result**: All 8 VMs configured and Tinyproxy restarted ✓

### Step 3: Verify Connectivity
Tested all 8 Azure proxies:

| VM | IP | Port | Status |
|----|---|------|--------|
| edge-gateway-wu2-01 | 20.115.154.150 | 8888 | ✓ |
| edge-gateway-wu2-02 | 4.155.110.28 | 8888 | ✓ |
| edge-gateway-eu2-01 | 20.114.194.171 | 8888 | ✓ |
| edge-gateway-eu2-02 | 20.246.4.49 | 8888 | ✓ |
| edge-gateway-cu1-01 | 20.12.225.26 | 8888 | ✓ |
| edge-gateway-ne1-01 | 52.236.59.43 | 8888 | ✓ |
| edge-gateway-ne1-02 | 20.166.90.199 | 8888 | ✓ |
| edge-gateway-sea-01 | 4.193.112.144 | 8888 | ✓ |

### Step 4: Restart Production Service
```bash
ssh azureuser@4.155.230.212
sudo systemctl restart faucet_worker
```

Expected outcome:
- 11 healthy proxies (3 DO + 8 Azure)
- Exit LOW_PROXY mode → NORMAL mode
- Concurrency increases from 2 → 3 bots

## Azure VM Infrastructure

### Deployed Resources
- **Resource Group**: InfraServicesRG
- **VM Size**: Standard_D2s_v3 (2 vCPUs, 8GB RAM)
- **Total VMs**: 8
- **Monthly Cost**: ~$70 USD total
- **Regions**: 
  - westus2 (2 VMs)
  - eastus2 (2 VMs)
  - centralus (1 VM)
  - northeurope (2 VMs)
  - southeastasia (1 VM)

### VM Naming Convention
- `edge-gateway-{region}-{number}`
- Example: `edge-gateway-wu2-01` = West US 2, VM #1

### Network Security Groups
- Each VM has its own NSG: `{vm-name}NSG`
- Port 8888 inbound rule priority: 1001
- Source: Any (*)
- Destination: Any (*) Port 8888
- Protocol: TCP

## Testing Proxy Functionality

### Quick Test
```powershell
# Test connectivity
Test-NetConnection -ComputerName 20.115.154.150 -Port 8888

# Test proxy functionality
curl.exe -x http://20.115.154.150:8888 http://ipinfo.io/ip
```

### Expected Output
```
20.115.154.150  # Should return the Azure VM's public IP
```

### Comprehensive Test (All 8)
```powershell
$proxies = @('20.115.154.150','4.155.110.28','20.114.194.171','20.246.4.49',
              '20.12.225.26','52.236.59.43','20.166.90.199','4.193.112.144')

foreach ($ip in $proxies) {
    Write-Host "$ip - " -NoNewline
    $result = curl.exe -x "http://$ip:8888" http://ipinfo.io/ip 2>$null
    Write-Host $result
}
```

## Production Impact

### Before Fix
- **Mode**: LOW_PROXY
- **Concurrency**: 2 bots
- **Available Proxies**: 3 (DigitalOcean only)
- **Throttling**: Severe rate limiting

### After Fix
- **Mode**: NORMAL (expected)
- **Concurrency**: 3 bots (expected)
- **Available Proxies**: 11 (3 DO + 8 Azure)
- **Geographic Distribution**: 5 Azure regions
- **Throttling**: Minimal

## Maintenance

### Check Tinyproxy Status
```bash
# SSH to any Azure VM
ssh azureuser@{vm-ip}

# Check service status
sudo systemctl status tinyproxy

# View logs
sudo journalctl -u tinyproxy -n 50
```

### Restart Tinyproxy
```bash
sudo systemctl restart tinyproxy
```

### Update Tinyproxy Config
```bash
sudo nano /etc/tinyproxy/tinyproxy.conf
sudo systemctl restart tinyproxy
```

### Check NSG Rules
```powershell
az network nsg rule list \
    --resource-group InfraServicesRG \
    --nsg-name edge-gateway-wu2-01NSG \
    --output table
```

## Future Improvements

1. **Automated Health Checks**: Add monitoring to detect when proxies go down
2. **Auto-Scaling**: Deploy additional VMs when healthy proxy count drops
3. **Cost Optimization**: Use B-series burstable VMs to reduce costs
4. **Geographic Rotation**: Rotate through regions to avoid IP blocks
5. **Proxy Authentication**: Add username/password authentication to Tinyproxy
6. **TLS/HTTPS**: Configure Tinyproxy to support HTTPS connections
7. **Load Balancing**: Distribute traffic across regions more evenly

## Rollback Plan

If issues arise, rollback steps:

1. **Disable Azure Proxies**:
```bash
ssh azureuser@4.155.230.212
nano .env
# Set USE_AZURE_PROXIES=false
sudo systemctl restart faucet_worker
```

2. **Remove VMs** (saves cost):
```powershell
az vm delete --resource-group InfraServicesRG --name edge-gateway-wu2-01 --yes
# Repeat for all 8 VMs
```

3. **Revert to DigitalOcean Only**:
- System will use 3 DigitalOcean proxies
- LOW_PROXY mode will remain active
- Concurrency will stay at 2

## Related Files

- `config/azure_proxies.txt` - List of Azure proxy URLs
- `config/digitalocean_proxies.txt` - List of DigitalOcean proxy URLs
- `core/proxy_manager.py` - Multi-source proxy loading logic
- `core/orchestrator.py` - Operation mode determination
- `deploy/deploy_azure_sequential.ps1` - VM deployment script
- `deploy/configure_azure_proxies.sh` - Proxy configuration script

## Success Criteria

✅ All 8 Azure VMs deployed and running
✅ All 8 NSG rules created (port 8888 allowed)
✅ All 8 Tinyproxy services configured and running
✅ All 8 proxies accessible from external network
✅ Multi-source proxy loading working (DO + Azure)
⏳ Production service restarted
⏳ Verified NORMAL mode (healthy proxies >= 10)
⏳ Verified concurrency increased to 3

## Next Steps

1. Wait for production service to restart
2. Monitor logs for proxy loading and health checks
3. Verify operation mode switches from LOW_PROXY to NORMAL
4. Monitor bot concurrency (should be 3, not 2)
5. Track proxy usage and health metrics over 24-48 hours
6. Document any issues or further optimizations needed

---

**Status**: Infrastructure deployed and configured ✓
**Verification**: In progress ⏳
**Expected Completion**: Within 5-10 minutes of service restart
