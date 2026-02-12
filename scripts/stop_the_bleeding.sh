#!/bin/bash
# Emergency Stop - Disable Money-Losing Faucets
# This stops FreeBitcoin & FireFaucet which have 100% loss rate

echo "🚨 STOPPING THE BLEEDING - Disabling unprofitable faucets..."
echo ""

cd ~/Repositories/cryptobot

# Backup current .env
cp .env .env.backup.$(date +%Y%m%d_%H%M%S)
echo "✅ Backed up .env"

# Update .env to disable FreeBitcoin and FireFaucet# These faucets cost $0.003 per captcha but pay $0 (confirmed zero balance)
echo ""
echo "Disabling faucets with confirmed losses:"
echo "  - FreeBitcoin: $0.264 spent, $0.00 earned (100% loss)"
echo "  - FireFaucet: Multiple captchas, $0.00 earned"

# Option 1: Completely disable these faucets
echo ""
echo "Choose action:"
echo "1) Disable FreeBitcoin & FireFaucet completely (recommended)"
echo "2) Add them to bypass list (skip claims but keep in rotation)"
echo "3) Cancel (keep losing money)"
read -p "Enter choice (1-3): " choice

case $choice in
  1)
    echo ""
    echo "Creating script to disable faucets..."
    
    # Comment out or remove from profiles
    cat > ~/Repositories/cryptobot/scripts/disable_losers.py <<'EOF'
#!/usr/bin/env python3
"""Disable money-losing faucets."""
import json
from pathlib import Path

# Load profiles
profiles_file = Path.home() / "Repositories/cryptobot/config/profiles.json"
profiles = json.loads(profiles_file.read_text())

disabled_count = 0
for profile in profiles:
    if profile.get('faucet') in ['freebitcoin', 'fire_faucet', 'firefaucet']:
        profile['enabled'] = False
        disabled_count += 1
        print(f"❌ Disabled {profile['faucet']} for {profile['email']}")

profiles_file.write_text(json.dumps(profiles, indent=2))
print(f"\n✅ Disabled {disabled_count} money-losing faucet profiles")
print("💰 Estimated savings: $0.01-0.02 per day in wasted captchas")
EOF
    
    python3 ~/Repositories/cryptobot/scripts/disable_losers.py
    
    echo ""
    echo "Restarting service..."
    sudo systemctl restart faucet_worker
    
    echo ""
    echo "✅ Done! FreeBitcoin & FireFaucet disabled."
    echo "📊 Check status: sudo systemctl status faucet_worker"
    ;;
    
  2)
    echo ""
    echo "Adding to bypass list..."
    sed -i 's/PROXY_BYPASS_FAUCETS=\[\]/PROXY_BYPASS_FAUCETS=["freebitcoin","firefaucet","fire_faucet"]/' .env
    
    echo "Restarting service..."
    sudo systemctl restart faucet_worker
    
    echo "✅ Done! Faucets added to bypass list."
    ;;
    
  3)
    echo "❌ Cancelled. Continuing to lose money on bad faucets."
    exit 0
    ;;
    
  *)
    echo "Invalid choice. Exiting."
    exit 1
    ;;
esac

echo ""
echo "================================================"
echo "NEXT STEPS TO ACTUALLY MAKE MONEY:"
echo "================================================"
echo ""
echo "Option A: Pivot to Airdrops ($50-500 per qualifying wallet)"
echo "  1. Research: Twitter search 'testnet airdrop tutorial'"
echo "  2. Find simple task (bridge testnet ETH, swap, etc)"
echo "  3. Test manually with one account"
echo "  4. Automate if profitable"
echo ""
echo "Option B: Shut Down Infrastructure (save $55/month)"
echo "  1. Stop all Azure VMs except main"
echo "  2. Keep code as portfolio piece"
echo "  3. Apply software engineering skills to real job"
echo ""
echo "Option C: Sell the Bot ($200-500)"
echo "  1. List on Flippa.com or BlackHatWorld"
echo "  2. Pitch: 'Turnkey automation with 8 proxies'"
echo "  3. Recoup costs + profit"
echo ""
echo "See docs/MONETIZATION_STRATEGY.md for full details"
echo ""
