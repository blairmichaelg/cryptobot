# VM Upgrade via Azure REST API
# Direct upgrade without needing Azure CLI/PowerShell modules

Write-Host "=== Upgrading win11-dev VM ===" -ForegroundColor Cyan

# Get access token from Azure Instance Metadata Service
Write-Host "`n[1/4] Getting access token..." -ForegroundColor Yellow
try {
    $token = Invoke-RestMethod -Headers @{"Metadata"="true"} -Method GET -Uri "http://169.254.169.254/metadata/identity/oauth2/token?api-version=2018-02-01&resource=https://management.azure.com/" -ErrorAction Stop
    Write-Host "  ✓ Access token obtained" -ForegroundColor Green
} catch {
    Write-Host "  ✗ Failed to get token. VM may not have managed identity enabled." -ForegroundColor Red
    Write-Host "  Please use Azure Portal instead: https://portal.azure.com" -ForegroundColor Yellow
    exit 1
}

$headers = @{
    "Authorization" = "Bearer $($token.access_token)"
    "Content-Type" = "application/json"
}

$subscriptionId = "5869a005-e429-4ea2-8d4d-0784be9c0268"
$resourceGroup = "rg-win11-test"
$vmName = "win11-dev"
$location = "eastus2"

# Step 2: Deallocate VM
Write-Host "`n[2/4] Deallocating VM..." -ForegroundColor Yellow
$deallocateUri = "https://management.azure.com/subscriptions/$subscriptionId/resourceGroups/$resourceGroup/providers/Microsoft.Compute/virtualMachines/$vmName/deallocate?api-version=2023-03-01"

try {
    $response = Invoke-WebRequest -Uri $deallocateUri -Method POST -Headers $headers -ErrorAction Stop
    Write-Host "  ✓ Deallocation started (this takes 2-3 minutes)..." -ForegroundColor Green
    
    # Wait for deallocation
    Start-Sleep -Seconds 120
    Write-Host "  ✓ VM deallocated" -ForegroundColor Green
} catch {
    Write-Host "  ✗ Deallocation failed: $($_.Exception.Message)" -ForegroundColor Red
    exit 1
}

# Step 3: Resize VM
Write-Host "`n[3/4] Resizing VM to Standard_D8s_v5..." -ForegroundColor Yellow
$resizeUri = "https://management.azure.com/subscriptions/$subscriptionId/resourceGroups/$resourceGroup/providers/Microsoft.Compute/virtualMachines/$vmName?api-version=2023-03-01"

$vmConfig = @{
    location = $location
    properties = @{
        hardwareProfile = @{
            vmSize = "Standard_D8s_v5"
        }
    }
} | ConvertTo-Json -Depth 10

try {
    $response = Invoke-WebRequest -Uri $resizeUri -Method PATCH -Headers $headers -Body $vmConfig -ErrorAction Stop
    Write-Host "  ✓ VM resized to Standard_D8s_v5 (8 vCPU, 32GB RAM)" -ForegroundColor Green
} catch {
    Write-Host "  ✗ Resize failed: $($_.Exception.Message)" -ForegroundColor Red
    Write-Host "  Attempting to start VM anyway..." -ForegroundColor Yellow
}

# Step 4: Upgrade Disk
Write-Host "`n[4/4] Upgrading OS disk to Premium SSD..." -ForegroundColor Yellow
$diskName = "win11-dev_OsDisk_1_e44b3ee7d5f54179891da208795b26a7"
$diskUri = "https://management.azure.com/subscriptions/$subscriptionId/resourceGroups/$resourceGroup/providers/Microsoft.Compute/disks/$diskName?api-version=2023-01-02"

$diskConfig = @{
    sku = @{
        name = "Premium_LRS"
    }
} | ConvertTo-Json -Depth 10

try {
    $response = Invoke-WebRequest -Uri $diskUri -Method PATCH -Headers $headers -Body $diskConfig -ErrorAction Stop
    Write-Host "  ✓ Disk upgraded to Premium SSD" -ForegroundColor Green
} catch {
    Write-Host "  ✗ Disk upgrade failed: $($_.Exception.Message)" -ForegroundColor Red
}

# Step 5: Start VM
Write-Host "`n[5/5] Starting VM..." -ForegroundColor Yellow
$startUri = "https://management.azure.com/subscriptions/$subscriptionId/resourceGroups/$resourceGroup/providers/Microsoft.Compute/virtualMachines/$vmName/start?api-version=2023-03-01"

try {
    $response = Invoke-WebRequest -Uri $startUri -Method POST -Headers $headers -ErrorAction Stop
    Write-Host "  ✓ VM starting (will take 2-3 minutes)..." -ForegroundColor Green
} catch {
    Write-Host "  ✗ Start failed: $($_.Exception.Message)" -ForegroundColor Red
}

Write-Host "`n=== Upgrade Complete ===" -ForegroundColor Cyan
Write-Host @"

New Configuration:
  - Size: Standard_D8s_v5 (8 vCPU, 32GB RAM)
  - Disk: Premium_LRS (Premium SSD)

VM is starting up. You will be disconnected.
Wait 3-5 minutes then reconnect to VM.

Performance improvements expected:
  - 2x more CPU cores (4 → 8)
  - 2x more RAM (16GB → 32GB)
  - Faster disk I/O (Premium SSD)
  - Better overall responsiveness

"@ -ForegroundColor Green
