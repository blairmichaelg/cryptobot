#!/bin/bash
# Azure VM Testing Script for CoinPayU Login Fix
# Run on VM: ssh azureuser@4.155.230.212

set -e  # Exit on error

echo "======================================"
echo "CoinPayU Login Fix - Azure VM Testing"
echo "======================================"
echo ""

# Check we're on the VM
if [ "$(hostname)" != "DevNode01" ]; then
    echo "❌ This script must run on Azure VM (DevNode01)"
    echo "Run: ssh azureuser@4.155.230.212"
    exit 1
fi

# Navigate to repo
cd ~/Repositories/cryptobot
echo "✅ Changed to: $(pwd)"
echo ""

# Pull latest changes
echo "Pulling latest changes..."
git fetch origin
git checkout copilot/fix-coinpayu-login-button-selector
git pull origin copilot/fix-coinpayu-login-button-selector
echo "✅ Latest code pulled"
echo ""

# Check Python and dependencies
echo "Checking Python version..."
python3 --version
echo ""

# Run diagnostic script
echo "======================================"
echo "Step 1: Running Diagnostic Script"
echo "======================================"
echo "This will capture page HTML after CAPTCHA solve..."
echo ""
HEADLESS=true python3 test_coinpayu.py
echo ""
echo "✅ Diagnostic complete - check coinpayu_login_page.html"
echo ""

# List generated files
echo "Generated diagnostic files:"
ls -lh coinpayu_login*.html 2>/dev/null || echo "No HTML files generated (might be an error)"
echo ""

# Run unit tests
echo "======================================"
echo "Step 2: Running Unit Tests"
echo "======================================"
HEADLESS=true python3 -m pytest tests/test_coinpayu.py -v --tb=short
echo ""

# Run actual login test
echo "======================================"
echo "Step 3: Testing Actual Login"
echo "======================================"
echo "Attempting real login to CoinPayU..."
echo ""
HEADLESS=true timeout 180 python3 main.py --single coinpayu --once || true
echo ""

echo "======================================"
echo "Testing Complete"
echo "======================================"
echo ""
echo "Review the output above for:"
echo "1. Diagnostic script - which selectors were found"
echo "2. Unit tests - should have 24+ passing"
echo "3. Actual login - should see 'Login successful'"
echo ""
echo "Check logs for details:"
echo "  tail -100 logs/faucet_bot.log"
echo ""
