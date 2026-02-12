#!/usr/bin/env pwsh
# Azure Multi-Region Proxy Deployment Script
# Deploys multiple B1s VMs across different Azure regions as Squid proxies
# Uses existing Azure credits - NO CREDIT CARD NEEDED

param(
    [int]$VmCount = 10,
    [string]$ResourceGroup = "APPSERVRG",
    [string]$AdminUsername = "azureuser",
    [string]$ProxyPassword = "",
    [switch]$DryRun = $false
)

$ErrorActionPreference = "Stop"

Write-Host "🚀 Azure Multi-Region Proxy Deployment" -ForegroundColor Cyan
Write-Host "======================================" -ForegroundColor Cyan
Write-Host ""

# Generate random proxy password if not provided
if (-not $ProxyPassword) {
    $ProxyPassword = -join ((65..90) + (97..122) + (48..57) | Get-Random -Count 16 | ForEach-Object {[char]$_})
    Write-Host "🔑 Generated proxy password: $ProxyPassword" -ForegroundColor Yellow
}

# Available Azure regions (good geographic diversity)
$regions = @(
    "eastus",
    "westus2",
    "centralus",
    "northeurope",
    "westeurope",
    "uksouth",
    "southeastasia",
    "australiaeast",
    "japaneast",
    "brazilsouth",
    "canadacentral",
    "francecentral",
    "koreacentral",
    "southafricanorth",
    "switzerlandnorth"
)

# Select regions to use
$selectedRegions = $regions | Select-Object -First ([Math]::Min($VmCount, $regions.Count))

Write-Host "📍 Selected regions:" -ForegroundColor Green
$selectedRegions | ForEach-Object { Write-Host "   - $_" }
Write-Host ""

# Cloud-init script for auto-configuring Squid proxy
$cloudInit = @"
#cloud-config
package_update: true
packages:
  - squid
  - apache2-utils
  - curl

runcmd:
  - |
    # Configure Squid
    cat > /etc/squid/squid.conf <<'EOF'
http_port 8888
auth_param basic program /usr/lib/squid/basic_ncsa_auth /etc/squid/passwords
auth_param basic realm Proxy
auth_param basic credentialsttl 2 hours
acl authenticated proxy_auth REQUIRED
acl safe_ports port 80 443 8080
acl CONNECT method CONNECT
http_access deny !safe_ports
http_access deny CONNECT !safe_ports
http_access allow authenticated
http_access deny all
cache deny all
access_log /var/log/squid/access.log squid
EOF
    
    # Create proxy user
    htpasswd -bc /etc/squid/passwords proxyuser '$ProxyPassword'
    chmod 640 /etc/squid/passwords
    chown proxy:proxy /etc/squid/passwords
    
    # Configure firewall
    ufw allow 22/tcp
    ufw allow 8888/tcp
    echo "y" | ufw enable
    
    # Start Squid
    systemctl restart squid
    systemctl enable squid
    
    # Test proxy
    PUBLIC_IP=`$(curl -s https://ifconfig.me)`
    echo "Proxy ready: http://proxyuser:****@`$PUBLIC_IP:8888" > /var/log/proxy-setup.log
"@

# Save cloud-init to temp file
$cloudInitFile = [System.IO.Path]::GetTempFileName()
$cloudInit | Out-File -FilePath $cloudInitFile -Encoding UTF8
Write-Host "💾 Cloud-init script saved to: $cloudInitFile" -ForegroundColor Gray
Write-Host ""

# Check Azure CLI
try {
    $null = az account show 2>&1
} catch {
    Write-Host "❌ Azure CLI not logged in. Please run: az login" -ForegroundColor Red
    exit 1
}

$currentSub = az account show --query name -o tsv
Write-Host "✅ Using Azure subscription: $currentSub" -ForegroundColor Green
Write-Host ""

if ($DryRun) {
    Write-Host "🔍 DRY RUN MODE - No actual deployments will be made" -ForegroundColor Yellow
    Write-Host ""
}

# Deploy VMs
$deployedVMs = @()
$vmNumber = 1

foreach ($region in $selectedRegions) {
    $vmName = "proxy-$region-$vmNumber"
    
    Write-Host "🚀 Deploying VM $vmNumber/$($selectedRegions.Count): $vmName in $region" -ForegroundColor Cyan
    
    if ($DryRun) {
        Write-Host "   [DRY RUN] Would deploy: $vmName" -ForegroundColor Yellow
        $vmNumber++
        continue
    }
    
    try {
        # Create VM
        Write-Host "   📦 Creating VM..." -NoNewline
        
        $result = az vm create `
            --resource-group $ResourceGroup `
            --name $vmName `
            --location $region `
            --size Standard_B1s `
            --image Ubuntu2204 `
            --admin-username $AdminUsername `
            --generate-ssh-keys `
            --public-ip-sku Standard `
            --custom-data $cloudInitFile `
            --output json 2>&1 | ConvertFrom-Json
        
        if ($LASTEXITCODE -ne 0) {
            Write-Host " ❌ Failed" -ForegroundColor Red
            Write-Host "   Error: $result" -ForegroundColor Red
            continue
        }
        
        $publicIP = $result.publicIpAddress
        Write-Host " ✅" -ForegroundColor Green
        Write-Host "   📍 Public IP: $publicIP" -ForegroundColor White
        
        # Open port 8888 for proxy
        Write-Host "   🔓 Opening port 8888..." -NoNewline
        
        $null = az vm open-port `
            --resource-group $ResourceGroup `
            --name $vmName `
            --port 8888 `
            --priority 1001 `
            --output none 2>&1
        
        if ($LASTEXITCODE -eq 0) {
            Write-Host " ✅" -ForegroundColor Green
        } else {
            Write-Host " ⚠️  Manual configuration needed" -ForegroundColor Yellow
        }
        
        # Add to deployed list
        $deployedVMs += [PSCustomObject]@{
            Name = $vmName
            Region = $region
            IP = $publicIP
            ProxyURL = "http://proxyuser:$ProxyPassword@${publicIP}:8888"
        }
        
        Write-Host "   ✅ VM deployed successfully!" -ForegroundColor Green
        Write-Host ""
        
    } catch {
        Write-Host " ❌ Failed" -ForegroundColor Red
        Write-Host "   Error: $_" -ForegroundColor Red
        Write-Host ""
    }
    
    $vmNumber++
    
    # Small delay between deployments
    if ($vmNumber -le $selectedRegions.Count) {
        Write-Host "   ⏳ Waiting 5 seconds before next deployment..." -ForegroundColor Gray
        Start-Sleep -Seconds 5
    }
}

# Clean up temp file
Remove-Item $cloudInitFile -ErrorAction SilentlyContinue

Write-Host ""
Write-Host "="*80 -ForegroundColor Cyan
Write-Host "📊 DEPLOYMENT SUMMARY" -ForegroundColor Cyan
Write-Host "="*80 -ForegroundColor Cyan
Write-Host ""

if ($deployedVMs.Count -eq 0) {
    Write-Host "❌ No VMs were deployed successfully" -ForegroundColor Red
    exit 1
}

Write-Host "✅ Successfully deployed: $($deployedVMs.Count)/$($selectedRegions.Count) VMs" -ForegroundColor Green
Write-Host ""

# Display all proxy URLs
Write-Host "📋 PROXY URLs (save these!):" -ForegroundColor Yellow
Write-Host ""
foreach ($vm in $deployedVMs) {
    Write-Host "  $($vm.Name) ($($vm.Region)):" -ForegroundColor White
    Write-Host "    $($vm.ProxyURL)" -ForegroundColor Cyan
}

# Generate proxy list file
$proxyListPath = ".\azure_proxies_new.txt"
$deployedVMs | ForEach-Object { $_.ProxyURL } | Out-File -FilePath $proxyListPath -Encoding UTF8

Write-Host ""
Write-Host "💾 Proxy URLs saved to: $proxyListPath" -ForegroundColor Green
Write-Host ""

# Generate commands to add to main VM
Write-Host "📝 NEXT STEPS:" -ForegroundColor Yellow
Write-Host ""
Write-Host "1️⃣  Upload proxy file to main VM:" -ForegroundColor White
Write-Host "   scp $proxyListPath azureuser@4.155.230.212:~/Repositories/cryptobot/config/azure_proxies_new.txt" -ForegroundColor Cyan
Write-Host ""
Write-Host "2️⃣  SSH to main VM and merge:" -ForegroundColor White
Write-Host "   ssh azureuser@4.155.230.212" -ForegroundColor Cyan
Write-Host "   cat ~/Repositories/cryptobot/config/azure_proxies_new.txt >> ~/Repositories/cryptobot/config/azure_proxies.txt" -ForegroundColor Cyan
Write-Host ""
Write-Host "3️⃣  Restart the bot:" -ForegroundColor White
Write-Host "   sudo systemctl restart faucet_worker" -ForegroundColor Cyan
Write-Host ""
Write-Host "4️⃣  Verify proxy count:" -ForegroundColor White
Write-Host "   wc -l ~/Repositories/cryptobot/config/azure_proxies.txt" -ForegroundColor Cyan
Write-Host ""

# Estimate cost
$monthlyCostPerVM = 7.50
$totalMonthlyCost = $deployedVMs.Count * $monthlyCostPerVM
$creditsRemaining = 1000 - $totalMonthlyCost
$monthsUntilDepletion = [Math]::Floor(1000 / $totalMonthlyCost)

Write-Host "💰 COST ESTIMATE:" -ForegroundColor Yellow
Write-Host "   Per VM: `$$monthlyCostPerVM/month" -ForegroundColor White
Write-Host "   Total: `$$totalMonthlyCost/month for $($deployedVMs.Count) VMs" -ForegroundColor White
Write-Host "   Your `$1000 credits will last: ~$monthsUntilDepletion months" -ForegroundColor Green
Write-Host ""
Write-Host "   Note: You already have 8 existing VMs (+ ~`$60/month)" -ForegroundColor Gray
Write-Host "Total cost: ~`$$($totalMonthlyCost + 60)/month for $($deployedVMs.Count + 8) VMs" -ForegroundColor White
Write-Host "Credits last: ~$([Math]::Floor(1000 / ($totalMonthlyCost + 60))) months" -ForegroundColor Green
Write-Host ""

Write-Host "🎉 Deployment complete!" -ForegroundColor Green
Write-Host ""
Write-Host "⏳ Wait 2-3 minutes for cloud-init to configure proxies, then test:" -ForegroundColor Yellow
Write-Host "   curl -x http://proxyuser:$ProxyPassword@<VM_IP>:8888 https://ifconfig.me" -ForegroundColor Cyan
Write-Host ""
