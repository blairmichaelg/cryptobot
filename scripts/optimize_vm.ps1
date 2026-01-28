# VM Performance Optimization Script
# Run as Administrator

Write-Host "=== VM Performance Optimization ===" -ForegroundColor Cyan

# 1. Increase Pagefile (Virtual Memory)
Write-Host "`n[1/8] Configuring Pagefile..." -ForegroundColor Yellow
try {
    # Set pagefile to 1.5x RAM (24GB) to 2x RAM (32GB)
    $computerSystem = Get-WmiObject Win32_ComputerSystem -EnableAllPrivileges
    $computerSystem.AutomaticManagedPagefile = $false
    $computerSystem.Put() | Out-Null
    
    $pageFile = Get-WmiObject -Query "SELECT * FROM Win32_PageFileSetting WHERE Name='C:\\pagefile.sys'"
    if ($pageFile) {
        $pageFile.InitialSize = 24576  # 24GB
        $pageFile.MaximumSize = 32768  # 32GB
        $pageFile.Put() | Out-Null
        Write-Host "  ✓ Pagefile configured: 24GB-32GB (requires reboot)" -ForegroundColor Green
    }
} catch {
    Write-Host "  ✗ Failed to configure pagefile: $_" -ForegroundColor Red
}

# 2. Disable unnecessary visual effects
Write-Host "`n[2/8] Disabling visual effects..." -ForegroundColor Yellow
try {
    $path = "HKCU:\Software\Microsoft\Windows\CurrentVersion\Explorer\VisualEffects"
    Set-ItemProperty -Path $path -Name "VisualFXSetting" -Value 2 -ErrorAction Stop
    Write-Host "  ✓ Visual effects set to 'Best Performance'" -ForegroundColor Green
} catch {
    Write-Host "  ✗ Failed to set visual effects: $_" -ForegroundColor Red
}

# 3. Disable Windows Defender real-time scanning (dev machine only)
Write-Host "`n[3/8] Configuring Windows Defender..." -ForegroundColor Yellow
try {
    # Add project folder to exclusions
    Add-MpPreference -ExclusionPath "C:\Users\azureuser\Repositories\cryptobot" -ErrorAction Stop
    Write-Host "  ✓ Added project folder to Defender exclusions" -ForegroundColor Green
} catch {
    Write-Host "  ✗ Failed to configure Defender: $_" -ForegroundColor Red
}

# 4. Disable SuperFetch/SysMain (can cause disk thrashing)
Write-Host "`n[4/8] Disabling SysMain (SuperFetch)..." -ForegroundColor Yellow
try {
    Stop-Service "SysMain" -Force -ErrorAction SilentlyContinue
    Set-Service "SysMain" -StartupType Disabled -ErrorAction Stop
    Write-Host "  ✓ SysMain disabled" -ForegroundColor Green
} catch {
    Write-Host "  ✗ Failed to disable SysMain: $_" -ForegroundColor Red
}

# 5. Optimize power settings
Write-Host "`n[5/8] Setting power plan to High Performance..." -ForegroundColor Yellow
try {
    $highPerf = powercfg -l | Where-Object { $_ -match "High performance" } | ForEach-Object { ($_ -split "\s+")[3] }
    if ($highPerf) {
        powercfg -setactive $highPerf
        Write-Host "  ✓ High Performance power plan activated" -ForegroundColor Green
    } else {
        Write-Host "  ✗ High Performance plan not found" -ForegroundColor Red
    }
} catch {
    Write-Host "  ✗ Failed to set power plan: $_" -ForegroundColor Red
}

# 6. Disable Windows Tips and Suggestions
Write-Host "`n[6/8] Disabling Windows tips and suggestions..." -ForegroundColor Yellow
try {
    Set-ItemProperty -Path "HKCU:\Software\Microsoft\Windows\CurrentVersion\ContentDeliveryManager" -Name "SubscribedContent-338389Enabled" -Value 0 -ErrorAction Stop
    Write-Host "  ✓ Windows tips disabled" -ForegroundColor Green
} catch {
    Write-Host "  ✗ Failed to disable tips: $_" -ForegroundColor Red
}

# 7. Clear DNS cache and reset network
Write-Host "`n[7/8] Clearing DNS cache..." -ForegroundColor Yellow
try {
    Clear-DnsClientCache
    Write-Host "  ✓ DNS cache cleared" -ForegroundColor Green
} catch {
    Write-Host "  ✗ Failed to clear DNS cache: $_" -ForegroundColor Red
}

# 8. Disable background apps
Write-Host "`n[8/8] Disabling background apps..." -ForegroundColor Yellow
try {
    Set-ItemProperty -Path "HKCU:\Software\Microsoft\Windows\CurrentVersion\BackgroundAccessApplications" -Name "GlobalUserDisabled" -Value 1 -ErrorAction Stop
    Write-Host "  ✓ Background apps disabled" -ForegroundColor Green
} catch {
    Write-Host "  ✗ Failed to disable background apps: $_" -ForegroundColor Red
}

Write-Host "`n=== Optimization Complete ===" -ForegroundColor Cyan
Write-Host "`nNOTE: Some changes require a reboot to take effect." -ForegroundColor Yellow
Write-Host "Run 'Restart-Computer' to reboot now.`n" -ForegroundColor Yellow
