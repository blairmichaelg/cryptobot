
#!/bin/bash
# -----------------------------------------------------------------------------
# Deployment Wrapper Script using Azure CLI
#
# This script handles two modes:
# 1. Remote Trigger (Default): Connects to Azure VM and pulls changes + restarts service.
#    Usage: ./deploy/deploy.sh [vm_name] [resource_group]
#
# 2. Local Installation (--install-service): Sets up systemd service on the CURRENT machine.
#    Usage: ./deploy/deploy.sh --install-service
# -----------------------------------------------------------------------------

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

    if [ "$CANARY_RESET" = true ]; then
        echo "🧹 Clearing canary settings from .env..."
        sed -i '/^CANARY_PROFILE=/d' .env || true
        sed -i '/^CANARY_ONLY=/d' .env || true
    fi

    if [ -n "$CANARY_PROFILE" ]; then
        echo "🧪 Enabling canary profile: $CANARY_PROFILE"
        sed -i '/^CANARY_PROFILE=/d' .env || true
        sed -i '/^CANARY_ONLY=/d' .env || true
        echo "CANARY_PROFILE=$CANARY_PROFILE" >> .env
        echo "CANARY_ONLY=true" >> .env
    fi
    
    echo "⚙️  Updating systemd services..."
    # Ensure the service files exist
    if [ -f "deploy/faucet_worker.service" ]; then
        sudo cp deploy/faucet_worker.service /etc/systemd/system/
        
        # Install health monitoring services
        if [ -f "deploy/health_monitor.service" ]; then
            echo "📊 Installing health monitor service..."
            sudo cp deploy/health_monitor.service /etc/systemd/system/
        fi
        
        if [ -f "deploy/health_endpoint.service" ]; then
            echo "🌐 Installing health endpoint service..."
            sudo cp deploy/health_endpoint.service /etc/systemd/system/
        fi
        
        sudo systemctl daemon-reload
        
        echo "🔄 Restarting services..."
        sudo systemctl restart faucet_worker
        
        # Enable and start health monitoring services
        if [ -f "deploy/health_monitor.service" ]; then
            sudo systemctl enable health_monitor
            sudo systemctl restart health_monitor
        fi
        
        if [ -f "deploy/health_endpoint.service" ]; then
            sudo systemctl enable health_endpoint
            sudo systemctl restart health_endpoint
        fi
        
        # Show service status
        echo ""
        echo "📊 Service Status:"
        sudo systemctl status faucet_worker --no-pager | head -15
        
        if [ -f "deploy/health_monitor.service" ]; then
            echo ""
            echo "🔍 Health Monitor Status:"
            sudo systemctl status health_monitor --no-pager | head -10
        fi
        
        if [ -f "deploy/health_endpoint.service" ]; then
            echo ""
            echo "🌐 Health Endpoint Status:"
            sudo systemctl status health_endpoint --no-pager | head -10
        fi
        
        echo ""
        echo "🩺 Running health gate..."
        python meta.py health || true
        HEARTBEAT_FILE="/tmp/cryptobot_heartbeat"
        if [ -f "$HEARTBEAT_FILE" ]; then
            HB_TS=$(head -1 "$HEARTBEAT_FILE" | tr -d '\r')
            NOW=$(date +%s)
            if [ -z "$HB_TS" ] || [ $((NOW - HB_TS)) -gt 300 ]; then
                echo "❌ Health gate failed: stale heartbeat."
                exit 1
            fi
        else
            echo "❌ Health gate failed: heartbeat missing."
            exit 1
        fi
        echo "✅ Health gate passed."
        echo "✅ Local Installation & Service Restart Complete!"
        echo ""
        echo "🌐 Health endpoint available at: http://localhost:8080/health"
    else
        echo "❌ Service file not found at deploy/faucet_worker.service"
        exit 1
    fi
}

# Parse Arguments
VM_NAME=""
RESOURCE_GROUP=""
LOCAL_MODE=false
CHECK_STATUS=false
CANARY_PROFILE=""
CANARY_RESET=false

while [[ $# -gt 0 ]]; do
    case $1 in
        --install-service)
            LOCAL_MODE=true
            shift
            ;;
        --check-status)
            CHECK_STATUS=true
            shift
            ;;
        --canary-profile)
            CANARY_PROFILE="$2"
            shift 2
            ;;
        --canary-reset)
            CANARY_RESET=true
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
git pull origin master

# Pre-flight Check
echo '🔍 Checking Environment...'
if [ -f \".env\" ]; then
    echo '✅ .env found'
else
    echo '⚠️ .env missing! Please configure environment.'
fi

# Install Dependencies
if [ "$CANARY_RESET" = true ]; then
    echo '🧹 Clearing canary settings from .env...'
    sed -i '/^CANARY_PROFILE=/d' .env || true
    sed -i '/^CANARY_ONLY=/d' .env || true
fi

if [ -n "$CANARY_PROFILE" ]; then
    echo '🧪 Enabling canary profile: $CANARY_PROFILE'
    sed -i '/^CANARY_PROFILE=/d' .env || true
    sed -i '/^CANARY_ONLY=/d' .env || true
    echo "CANARY_PROFILE=$CANARY_PROFILE" >> .env
    echo "CANARY_ONLY=true" >> .env
fi
echo '📦 Installing Python dependencies...'
if [ -d ".venv" ]; then
    source .venv/bin/activate
else
    python3 -m venv .venv
    source .venv/bin/activate
fi
pip install -r requirements.txt


echo '⚙️  Updating systemd services...'
# Cleanup old service if exists
sudo systemctl stop faucet_bot || true
sudo systemctl disable faucet_bot || true

# Install main service
sudo cp deploy/faucet_worker.service /etc/systemd/system/

# Install health monitoring services
if [ -f deploy/health_monitor.service ]; then
    echo '📊 Installing health monitor service...'
    sudo cp deploy/health_monitor.service /etc/systemd/system/
fi

if [ -f deploy/health_endpoint.service ]; then
    echo '🌐 Installing health endpoint service...'
    sudo cp deploy/health_endpoint.service /etc/systemd/system/
fi

sudo systemctl daemon-reload

echo '🔄 Restarting services...'
sudo systemctl restart faucet_worker

# Enable and start health monitoring
if [ -f deploy/health_monitor.service ]; then
    sudo systemctl enable health_monitor
    sudo systemctl restart health_monitor
fi

if [ -f deploy/health_endpoint.service ]; then
    sudo systemctl enable health_endpoint
    sudo systemctl restart health_endpoint
fi

# Show status
echo ''
echo '📊 Service Status:'
sudo systemctl status faucet_worker --no-pager | head -15

if [ -f deploy/health_monitor.service ]; then
    echo ''
    echo '🔍 Health Monitor Status:'
    sudo systemctl status health_monitor --no-pager | head -10
fi

if [ -f deploy/health_endpoint.service ]; then
    echo ''
    echo '🌐 Health Endpoint Status:'
    sudo systemctl status health_endpoint --no-pager | head -10
fi

echo ''
echo '🩺 Running health gate...'
python meta.py health || true
HEARTBEAT_FILE="/tmp/cryptobot_heartbeat"
if [ ! -f "$HEARTBEAT_FILE" ]; then
    echo '❌ Health gate failed: heartbeat missing.'
    exit 1
fi
HB_TS=$(head -1 "$HEARTBEAT_FILE" | tr -d '\r')
NOW=$(date +%s)
if [ -z "$HB_TS" ] || [ $((NOW - HB_TS)) -gt 300 ]; then
    echo '❌ Health gate failed: stale heartbeat.'
    exit 1
fi
echo '✅ Health gate passed.'
echo ''
echo '🌐 Health endpoint available at: http://localhost:8080/health'
"

# Execute via Azure CLI
if [ "$CHECK_STATUS" = true ]; then
  echo "📊 Checking Remote Status..."
  az vm run-command invoke \
    --resource-group "$RESOURCE_GROUP" \
    --name "$VM_NAME" \
    --command-id RunShellScript \
    --scripts "sudo -u azureuser bash -c 'cd /home/azureuser/Repositories/cryptobot && source .venv/bin/activate && python meta.py report'"
else
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
fi
