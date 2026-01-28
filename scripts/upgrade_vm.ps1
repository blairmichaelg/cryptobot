# Azure VM Upgrade Script
# Upgrades win11-dev to 8 vCPU, 32GB RAM with Premium SSD

Write-Host "=== Azure VM Upgrade Script ===" -ForegroundColor Cyan
Write-Host "VM: win11-dev" -ForegroundColor Yellow
Write-Host "Resource Group: rg-win11-test" -ForegroundColor Yellow
Write-Host "Target: Standard_D8s_v5 (8 vCPU, 32GB RAM)" -ForegroundColor Yellow
Write-Host "Target Disk: Premium_LRS`n" -ForegroundColor Yellow

# Step 1: Authenticate to correct account
Write-Host "[1/5] Authenticating to Azure (blairmichaelg account)..." -ForegroundColor Cyan
Write-Host "Opening browser for authentication..." -ForegroundColor Gray
az login --only-show-errors

if ($LASTEXITCODE -ne 0) {
    Write-Host "✗ Authentication failed!" -ForegroundColor Red
    exit 1
}

# Step 2: Verify we're in the right subscription
Write-Host "`n[2/5] Verifying subscription..." -ForegroundColor Cyan
$subscription = az account show --query "{Name:name, SubscriptionId:id}" -o json | ConvertFrom-Json
Write-Host "Current subscription: $($subscription.Name)" -ForegroundColor Green

# Step 3: Get current VM info
Write-Host "`n[3/5] Getting current VM configuration..." -ForegroundColor Cyan
$vm = az vm show -g "rg-win11-test" -n "win11-dev" --query "{Name:name, Size:hardwareProfile.vmSize, Location:location, OSDisk:storageProfile.osDisk.name, OSDiskType:storageProfile.osDisk.managedDisk.storageAccountType}" -o json | ConvertFrom-Json

if ($vm) {
    Write-Host "  Current Size: $($vm.Size)" -ForegroundColor Yellow
    Write-Host "  Current Disk Type: $($vm.OSDiskType)" -ForegroundColor Yellow
    Write-Host "  Location: $($vm.Location)" -ForegroundColor Yellow
} else {
    Write-Host "✗ Failed to get VM info!" -ForegroundColor Red
    exit 1
}

# Step 4: Resize VM to Standard_D8s_v5
Write-Host "`n[4/5] Resizing VM to Standard_D8s_v5 (8 vCPU, 32GB RAM)..." -ForegroundColor Cyan
Write-Host "  This will deallocate and resize the VM (a few minutes)..." -ForegroundColor Gray

$resize = Read-Host "Proceed with VM resize? (yes/no)"
if ($resize -ne "yes") {
    Write-Host "Resize cancelled." -ForegroundColor Yellow
    exit 0
}

Write-Host "  Deallocating VM..." -ForegroundColor Gray
az vm deallocate -g "rg-win11-test" -n "win11-dev" --no-wait

# Wait for deallocation
Start-Sleep -Seconds 5
Write-Host "  Waiting for deallocation to complete..." -ForegroundColor Gray
az vm wait -g "rg-win11-test" -n "win11-dev" --custom "instanceView.statuses[?code=='PowerState/deallocated']"

Write-Host "  Resizing to Standard_D8s_v5..." -ForegroundColor Gray
az vm resize -g "rg-win11-test" -n "win11-dev" --size "Standard_D8s_v5"

if ($LASTEXITCODE -eq 0) {
    Write-Host "  ✓ VM resized successfully!" -ForegroundColor Green
} else {
    Write-Host "  ✗ Resize failed!" -ForegroundColor Red
    exit 1
}

# Step 5: Upgrade OS Disk to Premium SSD
Write-Host "`n[5/5] Upgrading OS disk to Premium SSD..." -ForegroundColor Cyan

if ($vm.OSDiskType -eq "Premium_LRS") {
    Write-Host "  ✓ Already using Premium SSD" -ForegroundColor Green
} else {
    Write-Host "  Current: $($vm.OSDiskType) → Premium_LRS" -ForegroundColor Yellow
    
    $diskUpgrade = Read-Host "Upgrade disk to Premium SSD? (yes/no)"
    if ($diskUpgrade -eq "yes") {
        Write-Host "  Updating disk SKU..." -ForegroundColor Gray
        az disk update -g "rg-win11-test" -n "$($vm.OSDisk)" --sku "Premium_LRS"
        
        if ($LASTEXITCODE -eq 0) {
            Write-Host "  ✓ Disk upgraded to Premium SSD!" -ForegroundColor Green
        } else {
            Write-Host "  ✗ Disk upgrade failed!" -ForegroundColor Red
        }
    }
}

# Start the VM
Write-Host "`n[6/6] Starting VM..." -ForegroundColor Cyan
az vm start -g "rg-win11-test" -n "win11-dev" --no-wait

Write-Host "`n=== Upgrade Complete ===" -ForegroundColor Cyan
Write-Host "`nNew Configuration:" -ForegroundColor Green
Write-Host "  - Size: Standard_D8s_v5 (8 vCPU, 32GB RAM)" -ForegroundColor White
Write-Host "  - Disk: Premium_LRS" -ForegroundColor White
Write-Host "`nVM is starting up. Wait ~2 minutes then reconnect." -ForegroundColor Yellow
Write-Host "You may get disconnected during the startup process.`n" -ForegroundColor Yellow

# Show final config
Write-Host "Verifying new configuration in 30 seconds..." -ForegroundColor Gray
Start-Sleep -Seconds 30
az vm show -g "rg-win11-test" -n "win11-dev" --query "{Size:hardwareProfile.vmSize, OSDiskType:storageProfile.osDisk.managedDisk.storageAccountType}" -o table
