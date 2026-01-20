#!/bin/bash
# Deployment script for Cryptobot on Azure VM
# Usage: ./deploy.sh [vm_name] [resource_group]

VM_NAME="${1:-DevNode01}"
RESOURCE_GROUP="${2:-APPSERVRG}"

echo "🚀 Deploying Cryptobot to $VM_NAME ($RESOURCE_GROUP)..."

# Command to run on the VM
REMOTE_SCRIPT="
set -e
echo '📥 Pulling latest changes...'
cd /home/azureuser/Repositories/cryptobot
git fetch origin
git reset --hard origin/master

echo '📦 Installing dependencies...'
source .venv/bin/activate
pip install -r requirements.txt

echo '⚙️  Updating systemd service...'
sudo cp deploy/faucet_worker.service /etc/systemd/system/
sudo systemctl daemon-reload

echo '🔄 Restarting service...'
sudo systemctl restart faucet_worker
sudo systemctl status faucet_worker --no-pager
"

# Execute via Azure CLI
az vm run-command invoke \
  --resource-group "$RESOURCE_GROUP" \
  --name "$VM_NAME" \
  --command-id RunShellScript \
  --scripts "$REMOTE_SCRIPT"

if [ $? -eq 0 ]; then
    echo "✅ Deployment Successful!"
else
    echo "❌ Deployment Failed!"
    exit 1
fi
