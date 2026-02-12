#!/bin/bash
# Quick proxy configuration optimization
# Run this on your main VM to enable direct connection fallback

set -e

echo "🔧 Cryptobot Proxy Optimization"
echo "================================"
echo ""

cd ~/Repositories/cryptobot

# Backup current .env
cp .env .env.backup.$(date +%Y%m%d_%H%M%S)
echo "✅ Backed up .env"

# Update configuration
echo "⚙️ Updating proxy settings..."

# Enable direct fallback
if grep -q "ENABLE_DIRECT_FALLBACK=" .env; then
    sed -i 's/ENABLE_DIRECT_FALLBACK=.*/ENABLE_DIRECT_FALLBACK=true/' .env
else
    echo "ENABLE_DIRECT_FALLBACK=true" >> .env
fi

# Set fallback threshold to 1
if grep -q "PROXY_FALLBACK_THRESHOLD=" .env; then
    sed -i 's/PROXY_FALLBACK_THRESHOLD=.*/PROXY_FALLBACK_THRESHOLD=1/' .env
else
    echo "PROXY_FALLBACK_THRESHOLD=1" >> .env
fi

# Add bypass list for problem faucets
if grep -q "PROXY_BYPASS_FAUCETS=" .env; then
    sed -i 's/PROXY_BYPASS_FAUCETS=.*/PROXY_BYPASS_FAUCETS=["dutchy","coinpayu","adbtc","freebitcoin"]/' .env
else
    echo 'PROXY_BYPASS_FAUCETS=["dutchy","coinpayu","adbtc","freebitcoin"]' >> .env
fi

echo "✅ Configuration updated"
echo ""

echo "📋 New Settings:"
echo "==============="
grep -E "(ENABLE_DIRECT_FALLBACK|PROXY_FALLBACK_THRESHOLD|PROXY_BYPASS_FAUCETS)" .env
echo ""

# Clear proxy bindings for bypassed faucets
echo "🧹 Clearing proxy bindings for bypassed faucets..."
python3 - <<'PYTHON'
import json
from pathlib import Path

bindings_file = Path('config/proxy_bindings.json')
if bindings_file.exists():
    try:
        with open(bindings_file, 'r') as f:
            bindings = json.load(f)
        
        # Remove bindings for bypassed faucets
        bypassed = ['dutchy', 'coinpayu', 'adbtc', 'freebitcoin']
        removed_count = 0
        
        for account in list(bindings.keys()):
            if any(faucet in account.lower() for faucet in bypassed):
                del bindings[account]
                removed_count += 1
        
        with open(bindings_file, 'w') as f:
            json.dump(bindings, f, indent=2)
        
        print(f"✅ Cleared {removed_count} proxy binding(s)")
    except Exception as e:
        print(f"⚠️  Warning: {e}")
else:
    print("ℹ️  No proxy bindings file found (will be created on first run)")
PYTHON

echo ""
echo "🔄 Restarting faucet_worker service..."
sudo systemctl restart faucet_worker

echo ""
echo "⏳ Waiting for service to start..."
sleep 3

echo ""
echo "📊 Service Status:"
sudo systemctl status faucet_worker --no-pager | head -n 15

echo ""
echo "✅ Optimization complete!"
echo ""
echo "📝 What Changed:"
echo "================"
echo "1. Direct connection fallback enabled"
echo "2. Fallback threshold set to 1 (quick retry)"
echo "3. Bypassed faucets: DutchyCorp, CoinPayU, AdBTC, FreeBitcoin"
echo "4. Cleared proxy bindings for bypassed faucets"
echo ""
echo "🔍 Monitor Results:"
echo "=================="
echo "Watch logs: journalctl -u faucet_worker -f"
echo "Or: tail -f ~/Repositories/cryptobot/logs/faucet_bot.log"
echo ""
echo "Look for: [DIRECT FALLBACK SUCCESS] messages"
echo ""
