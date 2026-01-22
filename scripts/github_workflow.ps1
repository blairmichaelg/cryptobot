# PowerShell wrapper for GitHub workflow automation
# Usage: .\scripts\github_workflow.ps1 [-Execute] [-AutoMerge]

param(
    [switch]$Execute,
    [switch]$AutoMerge
)

$scriptPath = Join-Path $PSScriptRoot "github_workflow.py"
$repoRoot = Split-Path $PSScriptRoot -Parent

# Activate virtual environment if it exists
$venvActivate = Join-Path $repoRoot ".venv\Scripts\Activate.ps1"
if (Test-Path $venvActivate) {
    & $venvActivate
}

# Build arguments
$args = @()
if ($Execute) {
    $args += "--execute"
}
if ($AutoMerge) {
    $args += "--auto-merge"
}

# Run the Python script
python $scriptPath @args
