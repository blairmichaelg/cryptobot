#Requires -Version 7.0
###############################################################################
# Azure Proxy Infrastructure Deployment Script (Sequential)
# Purpose: Deploy stealth proxy farm - one VM at a time for reliability
###############################################################################

$ErrorActionPreference = "Continue"

# Configuration
$RG_NAME = "InfraServicesRG"
$ADMIN_USER = "azureuser"
$PROXY_PORT = "8888"
$VM_SIZE = "Standard_D2s_v3"
$DEVNODE_IP = "4.155.230.212"

# VM Configurations
$VMS = @(
    @{Name="edge-gateway-wu2-01"; Region="westus2"},
    @{Name="edge-gateway-wu2-02"; Region="westus2"},
    @{Name="edge-gateway-eu2-01"; Region="eastus2"},
    @{Name="edge-gateway-eu2-02"; Region="eastus2"},
    @{Name="edge-gateway-cu1-01"; Region="centralus"},
    @{Name="edge-gateway-ne1-01"; Region="northeurope"},
    @{Name="edge-gateway-ne1-02"; Region="northeurope"},
    @{Name="edge-gateway-sea-01"; Region="southeastasia"}
)

# Cloud-init
$CLOUD_INIT_FILE = "deploy/cloud-init.yaml"
@"
#cloud-config
package_update: true
package_upgrade: true
packages:
  - tinyproxy
  - ufw
write_files:
  - path: /etc/tinyproxy/tinyproxy.conf
    content: |
      User tinyproxy
      Group tinyproxy
      Port $PROXY_PORT
      Timeout 600
      LogLevel Info
      MaxClients 100
      Allow $DEVNODE_IP
runcmd:
  - systemctl enable tinyproxy
  - systemctl restart tinyproxy
  - ufw allow $PROXY_PORT/tcp
  - ufw allow 22/tcp
  - ufw --force enable
"@ | Out-File -FilePath $CLOUD_INIT_FILE -Encoding UTF8

Write-Host "`n╔════════════════════════════════════════════════╗" -ForegroundColor Green
Write-Host "║  Azure Proxy Deployment (8 VMs)               ║" -ForegroundColor Green
Write-Host "╚════════════════════════════════════════════════╝`n" -ForegroundColor Green

# Verify auth
Write-Host "[1/3] Verifying Azure CLI auth..." -ForegroundColor Yellow
$account = az account show 2>$null | ConvertFrom-Json
if (-not $account) {
    Write-Host "ERROR: Not logged in. Run 'az login'" -ForegroundColor Red
    exit 1
}
Write-Host "✓ Subscription: $($account.name)`n" -ForegroundColor Green

# Ensure resource group
Write-Host "[2/3] Ensuring resource group exists..." -ForegroundColor Yellow
az group create --name $RG_NAME --location westus2 --output none 2>$null
Write-Host "✓ Resource group ready`n" -ForegroundColor Green

# Deploy VMs
Write-Host "[3/3] Deploying VMs sequentially...`n" -ForegroundColor Yellow

$deployed = @()
$failed = @()

foreach ($vm in $VMS) {
    Write-Host "  Deploying $($vm.Name) in $($vm.Region)..." -ForegroundColor Cyan -NoNewline
    
    $output = az vm create `
        --resource-group $RG_NAME `
        --name $vm.Name `
        --location $vm.Region `
        --image "Ubuntu2204" `
        --size $VM_SIZE `
        --admin-username $ADMIN_USER `
        --generate-ssh-keys `
        --public-ip-sku "Standard" `
        --custom-data $CLOUD_INIT_FILE `
        --output json 2>&1
    
    if ($LASTEXITCODE -eq 0) {
        try {
            $vmData = $output | ConvertFrom-Json
            $ip = $vmData.publicIpAddress
            $deployed += "http://$($ip):$PROXY_PORT"
            Write-Host " ✓ $ip" -ForegroundColor Green
        } catch {
            Write-Host " ✓ (deployed)" -ForegroundColor Green
            $deployed += $vm.Name
        }
    } else {
        Write-Host " ✗ FAILED" -ForegroundColor Red
        $failed += $vm.Name
        Write-Host "     $(($output | Select-String -Pattern '(SkuNotAvailable|ERROR|InvalidTemplate)' | Select-Object -First 1).Line)" -ForegroundColor DarkRed
    }
}

Write-Host "`n╔════════════════════════════════════════════════╗" -ForegroundColor Green
Write-Host "║  Deployment Complete                           ║" -ForegroundColor Green
Write-Host "╚════════════════════════════════════════════════╝`n" -ForegroundColor Green

Write-Host "Success: $($deployed.Count) | Failed: $($failed.Count)`n" -ForegroundColor Cyan

if ($deployed.Count -gt 0) {
    # Extract all IPs
    Write-Host "Extracting final IP list...`n" -ForegroundColor Yellow
    $proxyList = @()
    
    foreach ($vm in $VMS) {
        $ip = az vm list-ip-addresses --resource-group $RG_NAME --name $vm.Name --query "[0].virtualMachine.network.publicIpAddresses[0].ipAddress" --output tsv 2>$null
        if ($ip) {
            $proxyList += "http://$($ip):$PROXY_PORT"
            Write-Host "  $($vm.Name): $ip" -ForegroundColor Green
        }
    }
    
    # Save proxy list
    $proxyFile = "config/azure_proxies.txt"
    $proxyList | Out-File -FilePath $proxyFile -Encoding UTF8 -NoNewline
    Write-Host "`n✓ Saved $($proxyList.Count) proxies to $proxyFile`n" -ForegroundColor Green
    
    Write-Host "Next steps:" -ForegroundColor Yellow
    Write-Host "1. ssh azureuser@4.155.230.212" -ForegroundColor White
    Write-Host "2. Add to .env: USE_AZURE_PROXIES=true" -ForegroundColor White
    Write-Host "3. sudo systemctl restart faucet_worker`n" -ForegroundColor White
} else {
    Write-Host "ERROR: All deployments failed`n" -ForegroundColor Red
    exit 1
}

# Cleanup
Remove-Item -Path $CLOUD_INIT_FILE -ErrorAction SilentlyContinue
