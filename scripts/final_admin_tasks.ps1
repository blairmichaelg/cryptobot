# Final Admin Tasks
# Run as Administrator

Write-Host "=== Final Optimization Tasks (Admin Required) ===" -ForegroundColor Cyan

# 1. Add Defender Exclusion
Write-Host "`n[1/2] Adding Windows Defender exclusion..." -ForegroundColor Yellow
try {
    Add-MpPreference -ExclusionPath "C:\Users\azureuser\Repositories\cryptobot" -ErrorAction Stop
    Write-Host "  ✓ Cryptobot folder excluded from Defender scanning" -ForegroundColor Green
} catch {
    Write-Host "  ✗ Failed: $_" -ForegroundColor Red
}

# 2. Disable SysMain (SuperFetch)
Write-Host "`n[2/2] Disabling SysMain service..." -ForegroundColor Yellow
try {
    Stop-Service "SysMain" -Force -ErrorAction Stop
    Set-Service "SysMain" -StartupType Disabled -ErrorAction Stop
    Write-Host "  ✓ SysMain disabled (reduces disk thrashing)" -ForegroundColor Green
} catch {
    Write-Host "  ✗ Failed: $_" -ForegroundColor Red
}

Write-Host "`n=== Complete ===" -ForegroundColor Cyan
Write-Host "All optimizations applied! Restart VS Code for settings to take effect.`n" -ForegroundColor Green
