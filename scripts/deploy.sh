#!/bin/bash
# Cryptobot Deployment Script

set -e

VM_NAME="DevNode01"
RG_NAME="APPSERVRG"
REMOTE_PATH="/home/azureuser/cryptobot"

echo "🚀 Starting deployment to $VM_NAME..."

# 1. Sync files to VM (Using rsync via SSH if available, or Azure CLI)
# Since we are in PowerShell/Windows, we might use az vm run-command for some tasks
# but here's the logical bash version for the VM.

echo "📂 Syncing local changes to remote repository..."
git push origin master

echo "🔄 Pulling changes on VM and restarting services..."
az vm run-command invoke \
  --resource-group "$RG_NAME" \
  --name "$VM_NAME" \
  --command-id RunShellScript \
  --scripts "cd $REMOTE_PATH && git pull origin master && pip install -r requirements.txt && sudo systemctl restart faucet_worker.service"

echo "✅ Deployment complete!"
