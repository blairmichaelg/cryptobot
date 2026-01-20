#!/bin/bash
# Cryptobot Automated Deployment Script
# Optimized for Azure VM (DevNode01)

set -e

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SERVICE_NAME="faucet_worker.service"

echo "🚀 Starting Cryptobot Deployment at $PROJECT_ROOT..."

cd "$PROJECT_ROOT"

# 1. Pull latest changes
CURRENT_BRANCH=$(git rev-parse --abbrev-ref HEAD)
echo "📥 Pulling latest changes from $CURRENT_BRANCH..."
git pull origin "$CURRENT_BRANCH"

# 2. Update dependencies
echo "📦 Updating dependencies..."
pip install -r requirements.txt --quiet

# 3. Validate .env
if [ ! -f .env ]; then
    echo "❌ Error: .env file missing!"
    exit 1
fi

if ! grep -q "CRYPTOBOT_COOKIE_KEY" .env; then
    echo "⚠️ Warning: CRYPTOBOT_COOKIE_KEY not found in .env"
    # The bot will generate it on first run if missing, now safely
fi

# 4. Ensure proxy bindings file exists
mkdir -p config
if [ ! -f config/proxy_bindings.json ]; then
    echo "{}" > config/proxy_bindings.json
fi

# 5. Restart service
echo "🔄 Restarting $SERVICE_NAME..."
sudo systemctl daemon-reload
sudo systemctl restart $SERVICE_NAME

# 6. Verify startup
echo "🕒 Waiting for startup..."
sleep 5

if systemctl is-active --quiet $SERVICE_NAME; then
    echo "✅ Service is active!"
    echo "📝 Recent logs:"
    sudo journalctl -u $SERVICE_NAME -n 20 --no-pager
else
    echo "❌ Service failed to start!"
    sudo journalctl -u $SERVICE_NAME -n 50 --no-pager
    exit 1
fi

echo "✨ Deployment complete!"
