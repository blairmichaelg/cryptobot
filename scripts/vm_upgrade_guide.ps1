# Quick VM Upgrade Guide
# For win11-dev in rg-win11-test

Write-Host "=== VM Upgrade via Azure Portal ===" -ForegroundColor Cyan
Write-Host @"

CURRENT CONFIG:
- VM: win11-dev
- Resource Group: rg-win11-test
- Size: Standard_D4s_v5 (4 vCPU, 16GB RAM)
- Disk: StandardSSD_LRS

TARGET CONFIG:
- Size: Standard_D8s_v5 (8 vCPU, 32GB RAM)
- Disk: Premium_LRS

STEPS TO UPGRADE:

1. RESIZE VM (via Azure Portal or PowerShell)
   -------------------------------
   Azure Portal:
   a. Go to: https://portal.azure.com
   b. Search for "win11-dev" VM
   c. Click "Size" under Settings
   d. Select "Standard_D8s_v5" (8 vCPU, 32GB)
   e. Click "Resize" button
   f. Wait ~3-5 minutes for resize

   OR via PowerShell:
   
"@ -ForegroundColor White

$portalScript = @'
# Resize using Azure PowerShell (if Az module installed)
Connect-AzAccount
Set-AzContext -SubscriptionName "<your-subscription>"
$vm = Get-AzVM -ResourceGroupName "rg-win11-test" -Name "win11-dev"
$vm.HardwareProfile.VmSize = "Standard_D8s_v5"
Update-AzVM -VM $vm -ResourceGroupName "rg-win11-test"
'@

Write-Host $portalScript -ForegroundColor Gray

Write-Host @"

2. UPGRADE DISK TO PREMIUM SSD
   -------------------------------
   Azure Portal:
   a. Go to VM → Disks
   b. Click on OS disk name
   c. Click "Size + performance"
   d. Select "Premium SSD"
   e. Choose appropriate size (keep current or larger)
   f. Click "Save"
   
   OR via PowerShell:

"@ -ForegroundColor White

$diskScript = @'
# Upgrade disk using Azure PowerShell
$diskName = "win11-dev_OsDisk_1_e44b3ee7d5f54179891da208795b26a7"
$disk = Get-AzDisk -ResourceGroupName "rg-win11-test" -DiskName $diskName
$disk.Sku = [Microsoft.Azure.Management.Compute.Models.DiskSku]::new('Premium_LRS')
Update-AzDisk -ResourceGroupName "rg-win11-test" -DiskName $diskName -Disk $disk
'@

Write-Host $diskScript -ForegroundColor Gray

Write-Host @"

3. ESTIMATED COSTS
   -------------------------------
   Standard_D8s_v5: ~$0.384/hour (~$280/month)
   Premium SSD (128GB): ~$20/month
   
   Total increase: ~$140/month from D4s_v5 + Standard SSD

4. ALTERNATIVE: Use Azure CLI (after fixing)
   -------------------------------
   
"@ -ForegroundColor White

$cliScript = @'
# Login to correct account
az login

# Resize VM
az vm deallocate -g rg-win11-test -n win11-dev
az vm resize -g rg-win11-test -n win11-dev --size Standard_D8s_v5
az vm start -g rg-win11-test -n win11-dev

# Upgrade disk (VM must be deallocated)
az vm deallocate -g rg-win11-test -n win11-dev
az disk update -g rg-win11-test \
  -n win11-dev_OsDisk_1_e44b3ee7d5f54179891da208795b26a7 \
  --sku Premium_LRS
az vm start -g rg-win11-test -n win11-dev
'@

Write-Host $cliScript -ForegroundColor Gray

Write-Host "`n=== RECOMMENDATION ===" -ForegroundColor Cyan
Write-Host @"
Use Azure Portal for quickest upgrade:
1. Open: https://portal.azure.com
2. Navigate to win11-dev VM
3. Resize to D8s_v5 (takes 3-5 min)
4. Upgrade disk to Premium (takes 5-10 min)
5. Reconnect to VM

Total time: ~10-15 minutes
"@ -ForegroundColor Yellow

# Try to open portal
$open = Read-Host "`nOpen Azure Portal now? (yes/no)"
if ($open -eq "yes") {
    Start-Process "https://portal.azure.com/#view/HubsExtension/BrowseResource/resourceType/Microsoft.Compute%2FVirtualMachines"
}
