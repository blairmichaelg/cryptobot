#!/bin/bash
# Deployment script for Cryptobot on Azure VM
# Usage: ./deploy.sh [vm_name] [resource_group]

#!/bin/bash
# Deployment script for Cryptobot on Azure VM
# Usage: ./deploy.sh [vm_name] [resource_group] [--install-service]

# Function to perform local installation
install_service() {
    echo "⚙️  Running Local Installation..."
    
    # We assume we are already in the repository root or the script is called from there
    # But let's be safe and find the repo root
    REPO_ROOT=$(git rev-parse --show-toplevel 2>/dev/null || pwd)
    cd "$REPO_ROOT"
    
    echo "📦 Installing dependencies..."
    if [ -d ".venv" ]; then
        source .venv/bin/activate
    else
        python3 -m venv .venv
        source .venv/bin/activate
    fi
    pip install -r requirements.txt
    
    echo "⚙️  Updating systemd service..."
    # Ensure the service file exists
    if [ -f "deploy/faucet_worker.service" ]; then
        sudo cp deploy/faucet_worker.service /etc/systemd/system/
        sudo systemctl daemon-reload
        
        echo "🔄 Restarting service..."
        sudo systemctl restart faucet_worker
        sudo systemctl status faucet_worker --no-pager
        echo "✅ Local Installation & Service Restart Complete!"
    else
        echo "❌ Service file not found at deploy/faucet_worker.service"
        exit 1
    fi
}

# Parse Arguments
VM_NAME=""
RESOURCE_GROUP=""
LOCAL_MODE=false

while [[ $# -gt 0 ]]; do
    case $1 in
        --install-service)
            LOCAL_MODE=true
            shift
            ;;
        *)
            if [ -z "$VM_NAME" ]; then
                VM_NAME="$1"
            elif [ -z "$RESOURCE_GROUP" ]; then
                RESOURCE_GROUP="$1"
            fi
            shift
            ;;
    esac
done

# Dispatch
if [ "$LOCAL_MODE" = true ]; then
    install_service
    exit 0
fi

# Fallback to existing Remote Trigger logic (only if NOT local mode)
VM_NAME="${VM_NAME:-DevNode01}"
RESOURCE_GROUP="${RESOURCE_GROUP:-APPSERVRG}"

echo "🚀 Deploying Cryptobot to $VM_NAME ($RESOURCE_GROUP)..."

# Command to run on the VM (Remote Trigger)
REMOTE_SCRIPT="
set -e
echo '📥 Pulling latest changes...'
cd /home/azureuser/Repositories/cryptobot
# Update Code
echo '🔄 Pulling latest code...'
git reset --hard
git pull origin main

# Pre-flight Check
echo '🔍 Checking Environment...'
if [ -f \".env\" ]; then
    echo '✅ .env found'
else
    echo '⚠️ .env missing! Please configure environment.'
fi

# Install Dependencies
echo '📦 Installing Python dependencies...'
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
    echo "✅ Remote Deployment Triggered Successfully!"
else
    echo "❌ Remote Deployment Failed!"
    exit 1
fi
