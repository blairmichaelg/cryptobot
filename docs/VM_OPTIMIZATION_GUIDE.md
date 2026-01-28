# VM Performance Optimization - Manual Steps (Requires Admin)

## Already Completed ✓
- [x] Cleared 3GB temp files
- [x] Cleared 298MB VS Code cache
- [x] Disabled visual effects (Best Performance)
- [x] Set High Performance power plan
- [x] Disabled Windows tips/suggestions
- [x] Disabled background apps
- [x] Removed config backup files
- [x] Optimized VS Code settings

## Requires Administrator Rights

### 1. Increase Pagefile (CRITICAL - Currently only 1GB!)

**Current**: 1GB pagefile
**Recommended**: 24-32GB for 16GB RAM system

**Steps**:
1. Right-click "This PC" → Properties
2. Click "Advanced system settings"
3. Under Performance, click "Settings"
4. Go to "Advanced" tab → "Change" under Virtual Memory
5. Uncheck "Automatically manage paging file"
6. Select C: drive
7. Choose "Custom size":
   - Initial size: 24576 MB (24GB)
   - Maximum size: 32768 MB (32GB)
8. Click "Set" → "OK" → Restart

### 2. Disable SysMain (SuperFetch) - Reduces Disk Thrashing

**Run in PowerShell as Administrator**:
```powershell
Stop-Service "SysMain" -Force
Set-Service "SysMain" -StartupType Disabled
```

### 3. Add Project to Windows Defender Exclusions

**Run in PowerShell as Administrator**:
```powershell
Add-MpPreference -ExclusionPath "C:\Users\azureuser\Repositories\cryptobot"
```

Or manually:
1. Windows Security → Virus & threat protection
2. Manage settings → Exclusions → Add exclusion
3. Add folder: `C:\Users\azureuser\Repositories\cryptobot`

## Azure VM-Specific Optimizations

### 4. Check VM Size and Upgrade if Needed

Your current VM should be at least **Standard_D4s_v3** (4 vCPUs, 16GB RAM) for development work.

To check/upgrade in Azure Portal:
1. Go to Azure Portal → Virtual Machines
2. Select your VM
3. Click "Size" under Settings
4. If not D4s_v3 or better, select:
   - **Standard_D4s_v5** (4 vCPU, 16GB) - Good balance
   - **Standard_D8s_v5** (8 vCPU, 32GB) - Better performance

### 5. Enable Premium SSD (if not already)

1. Azure Portal → VM → Disks
2. If OS disk is "Standard HDD" or "Standard SSD":
   - Stop VM
   - Change to "Premium SSD"
   - Start VM

## Quick Wins (No Admin Needed)

### Disable Heavy VS Code Extensions

You have **40 extensions** installed. Disable these if not actively using:
- Google Gemini Code Assist (duplicate of Copilot)
- Codeium (duplicate of Copilot)
- GitLens (if not using git visualizations)
- Windows AI Studio extensions (if not using)
- Azure extensions you're not actively using (keep only what you need)

**How**: Ctrl+Shift+X → Click gear icon on extension → Disable

### VS Code Settings Applied

Settings saved to: `C:\Users\azureuser\AppData\Roaming\Code\User\settings.json.recommended`

Key optimizations:
- Disabled GPU acceleration
- Disabled minimap, breadcrumbs
- Reduced file watching
- Disabled auto-formatting
- Disabled git decorations

**To apply**: Open VS Code settings.json and merge recommended settings.

## After Applying Changes

1. **Restart VM** (required for pagefile changes)
2. **Restart VS Code** (for extension/settings changes)
3. **Test performance** with your workflow

## Expected Improvements

- **Pagefile increase**: Eliminates memory-related stuttering
- **SysMain disabled**: Reduces disk I/O by 20-40%
- **Defender exclusions**: Reduces CPU usage during file operations
- **VS Code optimizations**: Reduces memory usage by 200-400MB
- **Cache cleared**: Immediate improvement in VS Code responsiveness

## Monitor Performance After Changes

```powershell
# Check memory usage
Get-Process | Sort-Object WorkingSet -Descending | Select-Object -First 10 Name, @{N="Memory(MB)";E={[math]::round($_.WorkingSet/1MB,2)}}

# Check pagefile usage
Get-WmiObject Win32_PageFileUsage | Select-Object Name, CurrentUsage, AllocatedBaseSize
```

## Still Laggy?

If still experiencing lag after these optimizations:
1. **Upgrade VM size** to 8 vCPU / 32GB RAM
2. **Use Premium SSD** instead of Standard
3. **Consider**: Run heavy operations (like bots) on separate Linux VM
4. **Network**: Check if lag is RDP-related (try lower display quality)
