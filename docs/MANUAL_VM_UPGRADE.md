# MANUAL VM UPGRADE STEPS

## Current VM Status
- **Name**: win11-dev
- **Resource Group**: rg-win11-test  
- **Current Size**: Standard_D4s_v5 (4 vCPU, 16GB RAM)
- **Current Disk**: StandardSSD_LRS
- **Location**: East US 2

## Target Configuration
- **Size**: Standard_D8s_v5 (8 vCPU, 32GB RAM)
- **Disk**: Premium_LRS (Premium SSD)

---

## STEP 1: Resize VM (5 minutes)

1. **Open Azure Portal**: https://portal.azure.com
2. **Search** for "win11-dev" in the search bar
3. Click on the **win11-dev** virtual machine
4. In left menu, click **"Size"** (under Settings)
5. In the size selector:
   - Filter or search for "D8s_v5"
   - Select **"Standard_D8s_v5"**
     - 8 vCPUs
     - 32 GiB RAM
     - 16 data disks max
     - ~$0.384/hour
6. Click **"Resize"** button at bottom
7. **Wait 3-5 minutes** for resize to complete
   - VM will automatically stop and restart
   - You'll lose connection temporarily

---

## STEP 2: Upgrade Disk to Premium SSD (5-10 minutes)

### Method A: While VM is Running (Recommended - No Downtime)

1. In VM page, click **"Disks"** (left menu under Settings)
2. Click on the OS disk name: **"win11-dev_OsDisk_1_e44b3ee7d5f54179891da208795b26a7"**
3. Click **"Size + performance"** (left menu)
4. Under **"Account type"**, select **"Premium SSD"**
5. Review size (keep at 128 GiB or larger)
6. Click **"Save"**
7. Wait for operation to complete (~5-10 minutes)

### Method B: If Method A Fails (Requires Downtime)

1. Go back to VM overview
2. Click **"Stop"** button at top
3. Wait for VM to fully stop (~2 minutes)
4. Follow steps 1-6 from Method A
5. Go to VM overview and click **"Start"**

---

## STEP 3: Verify Upgrade

After VM restarts and you reconnect, run in PowerShell:

```powershell
# Verify CPU and RAM
Get-CimInstance Win32_ComputerSystem | Select-Object NumberOfLogicalProcessors, @{N="RAM(GB)";E={[math]::round($_.TotalPhysicalMemory/1GB,2)}}

# Should show:
# NumberOfLogicalProcessors: 8
# RAM(GB): 32

# Verify disk type via Azure metadata
Invoke-RestMethod -Headers @{"Metadata"="true"} -Uri "http://169.254.169.254/metadata/instance/compute/storageProfile/osDisk/managedDisk/storageAccountType?api-version=2021-02-01&format=text"

# Should show: Premium_LRS
```

---

## Cost Impact

**Before:**
- D4s_v5: $0.192/hour × 730 hours = ~$140/month
- Standard SSD 128GB: ~$10/month
- **Total: ~$150/month**

**After:**
- D8s_v5: $0.384/hour × 730 hours = ~$280/month  
- Premium SSD 128GB: ~$20/month
- **Total: ~$300/month**

**Increase: ~$150/month**

---

## Performance Improvements Expected

✅ **CPU**: 4 → 8 cores (2x)
✅ **RAM**: 16GB → 32GB (2x)
✅ **Disk IOPS**: ~500 → ~240 (Premium SSD P10)
✅ **Disk Throughput**: ~60 MB/s → ~500 MB/s

**Result**: Significantly reduced lag, faster file operations, better multitasking

---

## Troubleshooting

**If resize fails:**
- Try stopping VM first, then resize, then start
- Ensure region (East US 2) supports D8s_v5
- Check quota limits in subscription

**If disk upgrade fails:**
- Must deallocate (stop) VM first
- Cannot downgrade from Premium to Standard
- Size must be ≥ current size

**If performance still poor after upgrade:**
- Reboot VM: `Restart-Computer -Force`
- Increase pagefile: See docs/VM_OPTIMIZATION_GUIDE.md
- Check RDP connection quality (lower graphics if remote)

---

## Quick Links

- **Azure Portal VMs**: https://portal.azure.com/#view/HubsExtension/BrowseResource/resourceType/Microsoft.Compute%2FVirtualMachines
- **VM Direct Link**: https://portal.azure.com/#@<tenant>/resource/subscriptions/5869a005-e429-4ea2-8d4d-0784be9c0268/resourceGroups/rg-win11-test/providers/Microsoft.Compute/virtualMachines/win11-dev/overview
