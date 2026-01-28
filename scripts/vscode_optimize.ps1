# VS Code Performance Optimization
Write-Host "=== VS Code Optimization ===" -ForegroundColor Cyan

# Settings to apply to VS Code user settings
$settingsPath = "$env:APPDATA\Code\User\settings.json"

Write-Host "`nOptimizing VS Code settings for performance..." -ForegroundColor Yellow

$optimizations = @'
{
    // Performance optimizations
    "files.watcherExclude": {
        "**/.git/objects/**": true,
        "**/.git/subtree-cache/**": true,
        "**/node_modules/*/**": true,
        "**/.hg/store/**": true,
        "**/__pycache__/**": true,
        "**/.venv/**": true,
        "**/venv/**": true,
        "**/*.pyc": true
    },
    "search.exclude": {
        "**/node_modules": true,
        "**/bower_components": true,
        "**/.venv": true,
        "**/venv": true,
        "**/__pycache__": true,
        "**/*.pyc": true
    },
    "files.exclude": {
        "**/__pycache__": true,
        "**/*.pyc": true
    },
    "python.terminal.activateEnvironment": false,
    "extensions.autoCheckUpdates": false,
    "extensions.autoUpdate": false,
    "terminal.integrated.gpuAcceleration": "off",
    "editor.formatOnSave": false,
    "editor.formatOnType": false,
    "editor.suggest.showStatusBar": false,
    "editor.minimap.enabled": false,
    "editor.lineNumbers": "on",
    "breadcrumbs.enabled": false,
    "workbench.editor.enablePreview": false,
    "workbench.editor.enablePreviewFromQuickOpen": false,
    "git.autofetch": false,
    "git.decorations.enabled": false
}
'@

Write-Host "`nRecommended VS Code optimizations saved to: $settingsPath.recommended" -ForegroundColor Green
$optimizations | Out-File "$settingsPath.recommended" -Encoding UTF8

Write-Host "`nTo apply these settings:" -ForegroundColor Yellow
Write-Host "1. Open VS Code Settings (Ctrl+,)" -ForegroundColor White
Write-Host "2. Click 'Open Settings (JSON)' in top right" -ForegroundColor White
Write-Host "3. Merge the settings from $settingsPath.recommended" -ForegroundColor White

Write-Host "`n=== VS Code Extensions to Consider Disabling ===" -ForegroundColor Cyan
$extensions = code --list-extensions 2>$null
if ($extensions) {
    Write-Host "Current extensions installed: $($extensions.Count)" -ForegroundColor Yellow
    $extensions | ForEach-Object {
        Write-Host "  - $_" -ForegroundColor Gray
    }
}

Write-Host "`n=== Clearing VS Code Cache ===" -ForegroundColor Cyan
$cachePaths = @(
    "$env:APPDATA\Code\Cache",
    "$env:APPDATA\Code\CachedData",
    "$env:APPDATA\Code\logs"
)

foreach ($path in $cachePaths) {
    if (Test-Path $path) {
        $size = (Get-ChildItem $path -Recurse -ErrorAction SilentlyContinue | Measure-Object -Property Length -Sum).Sum / 1MB
        Write-Host "Clearing $path ($([math]::round($size, 2)) MB)..." -ForegroundColor Yellow
        Remove-Item "$path\*" -Recurse -Force -ErrorAction SilentlyContinue
        Write-Host "  ✓ Cleared" -ForegroundColor Green
    }
}

Write-Host "`n=== Optimization Complete ===" -ForegroundColor Cyan
Write-Host "Restart VS Code for changes to take effect.`n" -ForegroundColor Yellow
