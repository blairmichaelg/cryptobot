# PowerShell Aliases for Quick Workflow Access
# Add these to your PowerShell profile for even faster access

# Workflow aliases
function workflow { python meta.py workflow }
function workflow-execute { python meta.py workflow --execute }
function workflow-auto { python meta.py workflow --execute --auto-merge }

# Other meta commands
function bot-health { python meta.py health }
function bot-profit { python meta.py profitability }
function bot-sync { python meta.py sync --merge --push }
function bot-clean { python meta.py clean }

Write-Host "✓ Workflow aliases loaded!" -ForegroundColor Green
Write-Host ""
Write-Host "Available commands:" -ForegroundColor Cyan
Write-Host "  workflow         - Preview GitHub workflow (dry-run)"
Write-Host "  workflow-execute - Execute GitHub workflow"
Write-Host "  workflow-auto    - Full automation (auto-merge PRs)"
Write-Host "  bot-health       - System health check"
Write-Host "  bot-profit       - Profitability dashboard"
Write-Host "  bot-sync         - Sync and merge"
Write-Host "  bot-clean        - Cleanup temp files"
Write-Host ""
