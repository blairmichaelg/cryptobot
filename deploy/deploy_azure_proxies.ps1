#Requires -Version 7.0
###############################################################################
# Azure Proxy Infrastructure Deployment Script (PowerShell)
# Purpose: Deploy stealth proxy farm for faucet automation
# Cost: ~$70/month for 8 Standard_D2s_v3 VMs
###############################################################################

$ErrorActionPreference = "Stop"

# Configuration
$RG_NAME = "InfraServicesRG"
$RG_LOCATION = "westus2"
$DEVNODE_IP = "4.155.230.212"
$ADMIN_USER = "azureuser"
$PROXY_PORT = "8888"
$VM_SIZE = "Standard_D2s_v3"

# VM Configurations - regions with confirmed Standard_D2s_v3 availability
$VMS = @{
    "edge-gateway-wu2-01" = "westus2"
    "edge-gateway-wu2-02" = "westus2"
    "edge-gateway-eu2-01" = "eastus2"
    "edge-gateway-eu2-02" = "eastus2"
    "edge-gateway-cu1-01" = "centralus"
    "edge-gateway-ne1-01" = "northeurope"
    "edge-gateway-ne1-02" = "northeurope"
    "edge-gateway-sea-01" = "southeastasia"
}

# Cloud-init configuration
$CLOUD_INIT = @"
#cloud-config
package_update: true
package_upgrade: true

packages:
  - tinyproxy
  - ufw
  - curl

write_files:
  - path: /etc/tinyproxy/tinyproxy.conf
    content: |
      User tinyproxy
      Group tinyproxy
      Port $PROXY_PORT
      Timeout 600
      DefaultErrorFile "/usr/share/tinyproxy/default.html"
      StatFile "/usr/share/tinyproxy/stats.html"
      LogFile "/var/log/tinyproxy/tinyproxy.log"
      LogLevel Info
      PidFile "/run/tinyproxy/tinyproxy.pid"
      MaxClients 100
      MinSpareServers 5
      MaxSpareServers 20
      StartServers 10
      MaxRequestsPerChild 0
      Allow $DEVNODE_IP
      ViaProxyName "tinyproxy"
      DisableViaHeader No

runcmd:
  - systemctl enable tinyproxy
  - systemctl restart tinyproxy
  - ufw allow $PROXY_PORT/tcp
  - ufw allow 22/tcp
  - ufw --force enable
"@

Write-Host "╔══════════════════════════════════════════════════════════════╗" -ForegroundColor Green
Write-Host "║     Azure Proxy Infrastructure Deployment                   ║" -ForegroundColor Green
Write-Host "║     8 VMs across 5 regions | Stealth configuration          ║" -ForegroundColor Green
Write-Host "╚══════════════════════════════════════════════════════════════╝" -ForegroundColor Green
Write-Host ""

# Check Azure CLI authentication
Write-Host "[1/6] Checking Azure CLI authentication..." -ForegroundColor Yellow
try {
    $account = az account show | ConvertFrom-Json
    Write-Host "✓ Authenticated to subscription: $($account.name)" -ForegroundColor Green
} catch {
    Write-Host "ERROR: Not logged in to Azure CLI" -ForegroundColor Red
    Write-Host "Run: az login" -ForegroundColor Red
    exit 1
}
Write-Host ""

# Create Resource Group
Write-Host "[2/6] Creating resource group: $RG_NAME..." -ForegroundColor Yellow
$rgExists = az group exists --name $RG_NAME
if ($rgExists -eq "true") {
    Write-Host "  Resource group already exists" -ForegroundColor Yellow
} else {
    az group create --name $RG_NAME --location $RG_LOCATION --output none
    Write-Host "✓ Resource group created" -ForegroundColor Green
}
Write-Host ""

# Deploy VMs in parallel
Write-Host "[3/6] Deploying 8 proxy VMs (Standard_D2s_v3)..." -ForegroundColor Yellow
Write-Host "  Regions: West US 2 (2), East US 2 (2), Central US (1), North Europe (2), Southeast Asia (1)" -ForegroundColor Cyan
Write-Host ""

$jobs = @()
$deployedIPs = @()

foreach ($vmName in $VMS.Keys) {
    $region = $VMS[$vmName]
    Write-Host "  → Deploying $vmName in $region..." -ForegroundColor Yellow
    
    # Save cloud-init to temp file
    $tempCloudInit = [System.IO.Path]::GetTempFileName()
    $CLOUD_INIT | Out-File -FilePath $tempCloudInit -Encoding UTF8
    
    # Start deployment job
    $job = Start-Job -ScriptBlock {
        param($vmName, $region, $rgName, $adminUser, $vmSize, $cloudInitPath)
        
        $result = az vm create `
            --resource-group $rgName `
            --name $vmName `
            --location $region `
            --image "Ubuntu2204" `
            --size $vmSize `
            --admin-username $adminUser `
            --generate-ssh-keys `
            --public-ip-sku "Standard" `
            --custom-data $cloudInitPath `
            --output json 2>&1
            
        return @{
            VMName = $vmName
            Region = $region
            Output = $result
        }
    } -ArgumentList $vmName, $region, $RG_NAME, $ADMIN_USER, $VM_SIZE, $tempCloudInit
    
    $jobs += @{Job = $job; VMName = $vmName; CloudInitFile = $tempCloudInit}
}

Write-Host ""
Write-Host "  Waiting for deployments to complete (this takes ~10 minutes)..." -ForegroundColor Cyan
Write-Host ""

# Wait for all jobs and collect results
$successCount = 0
$failCount = 0

foreach ($jobInfo in $jobs) {
    $result = Receive-Job -Job $jobInfo.Job -Wait
    Remove-Job -Job $jobInfo.Job
    Remove-Item -Path $jobInfo.CloudInitFile -ErrorAction SilentlyContinue
    
    if ($result.Output -match '"powerState":\s*"VM running"') {
        # Extract IP from JSON output
        try {
            $vmData = $result.Output | ConvertFrom-Json
            $ip = $vmData.publicIpAddress
            $deployedIPs += "http://$($ip):$PROXY_PORT"
            Write-Host "  ✓ $($result.VMName) deployed successfully ($ip)" -ForegroundColor Green
            $successCount++
        } catch {
            Write-Host "  ✓ $($result.VMName) deployed (IP extraction pending)" -ForegroundColor Green
            $successCount++
        }
    } else {
        Write-Host "  ✗ $($result.VMName) FAILED" -ForegroundColor Red
        Write-Host "     Error: $($result.Output | Select-String -Pattern 'ERROR|error' | Select-Object -First 1)" -ForegroundColor Red
        $failCount++
    }
}

Write-Host ""
Write-Host "[4/6] Deployment Summary" -ForegroundColor Yellow
Write-Host "  Success: $successCount | Failed: $failCount" -ForegroundColor Cyan
Write-Host ""

if ($successCount -eq 0) {
    Write-Host "ERROR: All deployments failed" -ForegroundColor Red
    exit 1
}

# Extract IPs if not already done
Write-Host "[5/6] Extracting public IPs..." -ForegroundColor Yellow
$proxyList = @()

foreach ($vmName in $VMS.Keys) {
    try {
        $ip = az vm list-ip-addresses `
            --resource-group $RG_NAME `
            --name $vmName `
            --query "[0].virtualMachine.network.publicIpAddresses[0].ipAddress" `
            --output tsv 2>$null
        
        if ($ip) {
            $proxyList += "http://$($ip):$PROXY_PORT"
            Write-Host "  ✓ $vmName`: $ip" -ForegroundColor Green
        }
    } catch {
        Write-Host "  ⚠ $vmName`: IP not available yet" -ForegroundColor Yellow
    }
}

Write-Host ""

# Save proxy list
$proxyFile = "config/azure_proxies.txt"
Write-Host "[6/6] Saving proxy list to $proxyFile..." -ForegroundColor Yellow
$proxyList | Out-File -FilePath $proxyFile -Encoding UTF8
Write-Host "✓ Saved $($proxyList.Count) proxies" -ForegroundColor Green
Write-Host ""

# Deployment complete
Write-Host "╔══════════════════════════════════════════════════════════════╗" -ForegroundColor Green
Write-Host "║              DEPLOYMENT COMPLETE                             ║" -ForegroundColor Green
Write-Host "╚══════════════════════════════════════════════════════════════╝" -ForegroundColor Green
Write-Host ""
Write-Host "Summary:" -ForegroundColor Cyan
Write-Host "  • VMs Deployed: $successCount/$($VMS.Count)" -ForegroundColor White
Write-Host "  • Proxy File: $proxyFile" -ForegroundColor White
Write-Host "  • Resource Group: $RG_NAME" -ForegroundColor White
Write-Host ""
Write-Host "Next Steps:" -ForegroundColor Cyan
Write-Host "  1. Update VM .env: USE_AZURE_PROXIES=true" -ForegroundColor White
Write-Host "  2. Restart service: sudo systemctl restart faucet_worker" -ForegroundColor White
Write-Host "  3. Verify exit from LOW_PROXY mode" -ForegroundColor White
Write-Host ""
