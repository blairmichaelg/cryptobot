#!/usr/bin/env pwsh
<#
.SYNOPSIS
    Fix existing Azure proxy VMs (tinyproxy configuration)
.DESCRIPTION
    Checks all edge-gateway VMs, fixes tinyproxy config, and generates working proxy list
#>

param(
    [string]$ResourceGroup = "INFRASERVICESRG",
    [switch]$Test
)

$ErrorActionPreference = "Stop"

Write-Host "`n🔧 Azure Proxy Fix Script" -ForegroundColor Cyan
Write-Host "==========================`n" -ForegroundColor Cyan

# Get all edge-gateway VMs
Write-Host "📋 Finding Azure proxy VMs..." -ForegroundColor Yellow
$vms = az vm list -g $ResourceGroup --query "[?starts_with(name, 'edge-gateway')].{name:name, ip:publicIps}" -o json | ConvertFrom-Json

if ($vms.Count -eq 0) {
    Write-Host "❌ No edge-gateway VMs found in $ResourceGroup" -ForegroundColor Red
    exit 1
}

Write-Host "✅ Found $($vms.Count) VMs`n" -ForegroundColor Green

# Get public IPs
$vmIPs = @()
foreach ($vm in $vms) {
    $ip = az vm list-ip-addresses -g $ResourceGroup -n $vm.name --query "[0].virtualMachine.network.publicIpAddresses[0].ipAddress" -o tsv
    if ($ip) {
        $vmIPs += @{
            Name = $vm.name
            IP = $ip
        }
        Write-Host "  • $($vm.name): $ip" -ForegroundColor Gray
    }
}

Write-Host "`n🔧 Fixing tinyproxy configuration on all VMs...`n" -ForegroundColor Yellow

$fixScript = @'
#!/bin/bash
# Fix tinyproxy configuration

# Check if tinyproxy is installed
if ! command -v tinyproxy &> /dev/null; then
    echo "Installing tinyproxy..."
    sudo apt-get update -qq
    sudo apt-get install -y tinyproxy
fi

# Configure tinyproxy
sudo tee /etc/tinyproxy/tinyproxy.conf > /dev/null <<EOF
User tinyproxy
Group tinyproxy
Port 8888
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
Allow 0.0.0.0/0
ViaProxyName "tinyproxy"
DisableViaHeader No
EOF

# Restart tinyproxy
sudo systemctl restart tinyproxy
sudo systemctl enable tinyproxy

# Check status
sudo systemctl is-active tinyproxy
'@

$successCount = 0
$failCount = 0
$workingProxies = @()

foreach ($vm in $vmIPs) {
    Write-Host "Fixing $($vm.Name) ($($vm.IP))..." -ForegroundColor Cyan
    
    try {
        # Create temp script file
        $tempScript = [System.IO.Path]::GetTempFileName()
        $fixScript | Out-File -FilePath $tempScript -Encoding UTF8 -NoNewline
        
        # Upload and execute
        scp -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -q $tempScript "azureuser@$($vm.IP):/tmp/fix_proxy.sh" 2>$null
        
        if ($LASTEXITCODE -eq 0) {
            $result = ssh -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null azureuser@$($vm.IP) "bash /tmp/fix_proxy.sh" 2>&1
            
            if ($result -match "active") {
                Write-Host "  ✅ Fixed and verified" -ForegroundColor Green
                $workingProxies += "http://$($vm.IP):8888"
                $successCount++
            } else {
                Write-Host "  ⚠️  Configured but status unclear: $result" -ForegroundColor Yellow
                $workingProxies += "http://$($vm.IP):8888"
                $successCount++
            }
        } else {
            Write-Host "  ❌ Failed to connect" -ForegroundColor Red
            $failCount++
        }
        
        Remove-Item $tempScript -Force
    }
    catch {
        Write-Host "  ❌ Error: $_" -ForegroundColor Red
        $failCount++
    }
}

Write-Host "`n📊 Results:" -ForegroundColor Cyan
Write-Host "  ✅ Fixed: $successCount" -ForegroundColor Green
Write-Host "  ❌ Failed: $failCount" -ForegroundColor Red

# Generate proxy list file
if ($workingProxies.Count -gt 0) {
    $proxyFile = "azure_proxies_fixed.txt"
    $workingProxies | Out-File -FilePath $proxyFile -Encoding UTF8
    
    Write-Host "`n✅ Generated proxy list: $proxyFile" -ForegroundColor Green
    Write-Host "`nProxy URLs:" -ForegroundColor Cyan
    $workingProxies | ForEach-Object { Write-Host "  $_" -ForegroundColor Gray }
    
    Write-Host "`n📤 Next steps:" -ForegroundColor Yellow
    Write-Host "  1. Upload to VM: scp $proxyFile azureuser@4.155.230.212:~/Repositories/cryptobot/config/" -ForegroundColor Gray
    Write-Host "  2. SSH to VM: ssh azureuser@4.155.230.212" -ForegroundColor Gray
    Write-Host "  3. Update config: cat config/$proxyFile > config/proxies.txt" -ForegroundColor Gray
    Write-Host "  4. Restart bot: sudo systemctl restart faucet_worker" -ForegroundColor Gray
}

# Test proxies if requested
if ($Test) {
    Write-Host "`n🧪 Testing proxies..." -ForegroundColor Yellow
    foreach ($proxy in $workingProxies) {
        $ip = $proxy -replace 'http://|:8888', ''
        Write-Host "  Testing $ip..." -ForegroundColor Gray
        
        $result = curl.exe -x $proxy -s -I http://api.ipify.org --connect-timeout 10 2>&1
        if ($result -match "200 OK") {
            Write-Host "    ✅ Working" -ForegroundColor Green
        } else {
            Write-Host "    ⚠️  Response: $($result[0])" -ForegroundColor Yellow
        }
    }
}

Write-Host "`n✅ Done!`n" -ForegroundColor Green
