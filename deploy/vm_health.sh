#!/bin/bash
# VM Health Check Script
# Usage: ./vm_health.sh --resource-group <RG> --vm-name <VM>

set -e

RESOURCE_GROUP=$1
VM_NAME=$2

if [ -z "$RESOURCE_GROUP" ] || [ -z "$VM_NAME" ]; then
    echo "Usage: $0 <resource-group> <vm-name>"
    exit 1
fi

echo "🔍 Checking health for VM: $VM_NAME in Resource Group: $RESOURCE_GROUP"

# 1. OS and VM Status
echo "--------------------------------------------------"
echo "💻 VM Status:"
az vm get-instance-view --resource-group "$RESOURCE_GROUP" --name "$VM_NAME" --query "instanceView.statuses[1].displayStatus" -o tsv

# 2. Disk Usage
echo "--------------------------------------------------"
echo "💾 Disk Usage:"
az vm run-command invoke --resource-group "$RESOURCE_GROUP" --name "$VM_NAME" --command-id RunShellScript --scripts "df -h / | tail -1" --query "value[0].message" -o tsv

# 3. CPU / Memory
echo "--------------------------------------------------"
echo "🧠 CPU/Memory Load:"
az vm run-command invoke --resource-group "$RESOURCE_GROUP" --name "$VM_NAME" --command-id RunShellScript --scripts "uptime && free -h | grep Mem" --query "value[0].message" -o tsv

# 4. Git Sync Status
echo "--------------------------------------------------"
echo "🔗 Git Sync Status:"
az vm run-command invoke --resource-group "$RESOURCE_GROUP" --name "$VM_NAME" --command-id RunShellScript --scripts "cd ~/Repositories/cryptobot && git fetch && git status -sb" --query "value[0].message" -o tsv

# 5. Bot Heartbeat
echo "--------------------------------------------------"
echo "❤️ Bot Heartbeat:"
az vm run-command invoke --resource-group "$RESOURCE_GROUP" --name "$VM_NAME" --command-id RunShellScript --scripts "cat ~/Repositories/cryptobot/logs/heartbeat.txt 2>/dev/null || echo 'No heartbeat found'" --query "value[0].message" -o tsv

echo "--------------------------------------------------"
echo "✅ Health check complete!"
