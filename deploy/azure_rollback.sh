#!/bin/bash
# Azure VM Rollback Script for CryptoBot
# Usage: ./azure_rollback.sh --resource-group <RG> --vm-name <VM> [--commit <sha>] [--dry-run]

set -e

# Color output
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

# Defaults
DRY_RUN=false
RESOURCE_GROUP=""
VM_NAME=""
ROLLBACK_COMMIT=""

# Parse arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        --resource-group)
            RESOURCE_GROUP="$2"
            shift 2
            ;;
        --vm-name)
            VM_NAME="$2"
            shift 2
            ;;
        --commit)
            ROLLBACK_COMMIT="$2"
            shift 2
            ;;
        --dry-run)
            DRY_RUN=true
            shift
            ;;
        *)
            echo -e "${RED}Unknown option: $1${NC}"
            exit 1
            ;;
    esac
done

if [ -z "$RESOURCE_GROUP" ] || [ -z "$VM_NAME" ]; then
    echo -e "${RED}Error: --resource-group and --vm-name are required${NC}"
    exit 1
fi

echo -e "${GREEN}═══════════════════════════════════════${NC}"
echo -e "${GREEN}  CryptoBot Azure Rollback${NC}"
echo -e "${GREEN}═══════════════════════════════════════${NC}"
echo "Resource Group: $RESOURCE_GROUP"
echo "VM Name: $VM_NAME"
echo "Rollback Commit: ${ROLLBACK_COMMIT:-HEAD~1}"
echo "Dry Run: $DRY_RUN"

# Check Azure CLI login status
if ! az account show &>/dev/null; then
    echo -e "${RED}Not logged in to Azure CLI${NC}"
    echo "Please run: az login"
    exit 1
fi

# Create rollback script
cat > /tmp/rollback_cryptobot.sh <<'ROLLBACK_EOF'
#!/bin/bash
set -e

TARGET_DIR="/home/azureuser/Repositories/cryptobot"
if [ ! -d "$TARGET_DIR" ]; then
    echo "Directory $TARGET_DIR not found. Cannot rollback."
    exit 1
fi

cd "$TARGET_DIR"

echo "Fetching latest refs..."
git fetch --all

ROLLBACK_COMMIT="__ROLLBACK_COMMIT__"
if [ -n "$ROLLBACK_COMMIT" ]; then
    echo "Rolling back to $ROLLBACK_COMMIT..."
    git reset --hard "$ROLLBACK_COMMIT"
else
    echo "Rolling back one commit..."
    git reset --hard HEAD~1
fi

sudo systemctl restart faucet_worker
sudo systemctl restart health_monitor
sudo systemctl restart health_endpoint

echo "Rollback complete."
ROLLBACK_EOF

python - <<'PY'
from pathlib import Path
import os

path = Path("/tmp/rollback_cryptobot.sh")
text = path.read_text()
text = text.replace("__ROLLBACK_COMMIT__", os.environ.get("ROLLBACK_COMMIT", ""))
path.write_text(text)
PY

if [ "$DRY_RUN" = true ]; then
    echo -e "${YELLOW}[DRY RUN]${NC} Would execute rollback script on VM"
    cat /tmp/rollback_cryptobot.sh
    exit 0
fi

# Execute rollback on VM
az vm run-command invoke \
  --resource-group "$RESOURCE_GROUP" \
  --name "$VM_NAME" \
  --command-id RunShellScript \
  --scripts @/tmp/rollback_cryptobot.sh \
  --output json

echo -e "${GREEN}✓${NC} Rollback executed"
