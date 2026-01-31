#!/bin/bash
###############################################################################
# Post-Deployment Configuration Script
# Run this on the production VM after Azure proxies are deployed
###############################################################################

set -e

cd ~/Repositories/cryptobot

echo "╔════════════════════════════════════════════════╗"
echo "║  Configuring Azure Proxies on Production VM   ║"
echo "╚════════════════════════════════════════════════╝"
echo ""

# Backup .env
echo "[1/5] Backing up .env..."
cp .env .env.backup.$(date +%Y%m%d_%H%M%S)
echo "✓ Backed up"
echo ""

# Add Azure proxy configuration
echo "[2/5] Updating .env with Azure proxy settings..."
if grep -q "USE_AZURE_PROXIES" .env; then
    sed -i 's/^USE_AZURE_PROXIES=.*/USE_AZURE_PROXIES=true/' .env
    echo "✓ Updated USE_AZURE_PROXIES=true"
else
    echo "USE_AZURE_PROXIES=true" >> .env
    echo "✓ Added USE_AZURE_PROXIES=true"
fi
echo ""

# Verify proxy files exist
echo "[3/5] Verifying proxy files..."
if [ -f "config/azure_proxies.txt" ]; then
    proxy_count=$(wc -l < config/azure_proxies.txt)
    echo "✓ Azure proxies: $proxy_count"
else
    echo "⚠ Warning: config/azure_proxies.txt not found"
fi

if [ -f "config/digitalocean_proxies.txt" ]; then
    do_count=$(wc -l < config/digitalocean_proxies.txt)
    echo "✓ DigitalOcean proxies: $do_count"
fi
echo ""

# Restart service
echo "[4/5] Restarting faucet_worker service..."
sudo systemctl restart faucet_worker
sleep 3
echo "✓ Service restarted"
echo ""

# Check service status
echo "[5/5] Verifying service status..."
if sudo systemctl is-active --quiet faucet_worker; then
    echo "✓ Service is active"
else
    echo "✗ Service is not active - check logs"
    sudo systemctl status faucet_worker --no-pager -l | tail -20
    exit 1
fi
echo ""

# Check logs for proxy count
echo "Checking operation mode..."
sleep 5
tail -100 logs/faucet_bot.log | grep -E "(operation mode|proxy|PROXY)" | tail -10

echo ""
echo "╔════════════════════════════════════════════════╗"
echo "║  Configuration Complete                        ║"
echo "╚════════════════════════════════════════════════╝"
echo ""
echo "Monitor logs with:"
echo "  tail -f logs/faucet_bot.log | grep -E '(proxy|concurrency|operation mode)'"
echo ""
