#!/bin/bash
# Azure VM Deployment Script for CryptoBot
# Usage: ./azure_deploy.sh --resource-group <RG> --vm-name <VM> [--dry-run]

set -e

# Color output
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

# Default values
DRY_RUN=false
RESOURCE_GROUP=""
VM_NAME=""

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

# Validate required parameters
if [ -z "$RESOURCE_GROUP" ] || [ -z "$VM_NAME" ]; then
    echo -e "${RED}Error: --resource-group and --vm-name are required${NC}"
    echo "Usage: $0 --resource-group <RG> --vm-name <VM> [--dry-run]"
    exit 1
fi

echo -e "${GREEN}═══════════════════════════════════════${NC}"
echo -e "${GREEN}  CryptoBot Azure Deployment${NC}"
echo -e "${GREEN}═══════════════════════════════════════${NC}"
echo ""
echo "Resource Group: $RESOURCE_GROUP"
echo "VM Name: $VM_NAME"
echo "Dry Run: $DRY_RUN"
echo ""

# Check Azure CLI login status
echo -e "${YELLOW}[1/6]${NC} Checking Azure CLI authentication..."
if ! az account show &>/dev/null; then
    echo -e "${RED}Not logged in to Azure CLI${NC}"
    echo "Please run: az login"
    exit 1
fi
ACCOUNT_NAME=$(az account show --query name -o tsv)
echo -e "${GREEN}✓${NC} Logged in as: $ACCOUNT_NAME"

# Verify resource group and VM exist
echo -e "${YELLOW}[2/6]${NC} Verifying Azure resources..."
if ! az group show --name "$RESOURCE_GROUP" &>/dev/null; then
    echo -e "${RED}Resource group '$RESOURCE_GROUP' not found${NC}"
    exit 1
fi
if ! az vm show --resource-group "$RESOURCE_GROUP" --name "$VM_NAME" &>/dev/null; then
    echo -e "${RED}VM '$VM_NAME' not found in resource group '$RESOURCE_GROUP'${NC}"
    exit 1
fi
echo -e "${GREEN}✓${NC} Resources validated"

# Create deployment script
echo -e "${YELLOW}[3/6]${NC} Generating deployment commands..."
cat > /tmp/deploy_cryptobot.sh <<'DEPLOY_EOF'
#!/bin/bash
set -e

echo "Starting CryptoBot deployment..."

# Navigate to app directory
# Default to Repositories/cryptobot as established
TARGET_DIR="/home/azureuser/Repositories/cryptobot"

if [ ! -d "$TARGET_DIR" ]; then
    echo "Directory $TARGET_DIR not found. Cloning..."
    mkdir -p /home/azureuser/Repositories
    cd /home/azureuser/Repositories
    git clone https://github.com/blairmichaelg/cryptobot.git
fi

cd "$TARGET_DIR"

# Ensure we are on the right branch
# For production, we might want 'main' or 'feature/consolidated-production-upgrade'
# Using current checked out for now or forcing checkout
BRANCH="feature/consolidated-production-upgrade"
echo "Switching to branch $BRANCH..."
git fetch
git checkout $BRANCH
git pull origin $BRANCH

# Make deploy script executable
chmod +x deploy/deploy.sh

# Run the unified deployment script
# passing --install-service to ensure systemd is set up
echo "Invoking local deploy script..."
./deploy/deploy.sh --install-service

DEPLOY_EOF

chmod +x /tmp/deploy_cryptobot.sh

if [ "$DRY_RUN" = true ]; then
    echo -e "${YELLOW}[DRY RUN]${NC} Would execute deployment script on VM"
    echo "--- Deployment Script Content ---"
    cat /tmp/deploy_cryptobot.sh
    echo "--- End of Script ---"
    echo ""
    echo -e "${YELLOW}Command that would run:${NC}"
    echo "az vm run-command invoke \\"
    echo "  --resource-group $RESOURCE_GROUP \\"
    echo "  --name $VM_NAME \\"
    echo "  --command-id RunShellScript \\"
    echo "  --scripts @/tmp/deploy_cryptobot.sh"
    exit 0
fi

# Execute deployment on VM
echo -e "${YELLOW}[4/6]${NC} Deploying to VM..."
DEPLOY_OUTPUT=$(az vm run-command invoke \
  --resource-group "$RESOURCE_GROUP" \
  --name "$VM_NAME" \
  --command-id RunShellScript \
  --scripts @/tmp/deploy_cryptobot.sh \
  --output json)

# Check deployment result
echo -e "${YELLOW}[5/6]${NC} Checking deployment status..."
EXIT_CODE=$(echo "$DEPLOY_OUTPUT" | jq -r '.value[0].code')
if [ "$EXIT_CODE" != "ComponentStatus/StdOut/succeeded" ]; then
    echo -e "${RED}Deployment failed${NC}"
    echo "$DEPLOY_OUTPUT" | jq -r '.value[0].message'
    exit 1
fi

echo -e "${GREEN}✓${NC} Deployment successful!"
echo ""
echo "$DEPLOY_OUTPUT" | jq -r '.value[0].message'

# Health check
echo -e "${YELLOW}[6/6]${NC} Running post-deployment health check..."
sleep 5
HEALTH_OUTPUT=$(az vm run-command invoke \
  --resource-group "$RESOURCE_GROUP" \
  --name "$VM_NAME" \
  --command-id RunShellScript \
  --scripts "tail -20 ~/Repositories/cryptobot/faucet_bot.log" \
  --output json)

echo -e "${GREEN}Recent log output:${NC}"
echo "$HEALTH_OUTPUT" | jq -r '.value[0].message'

echo ""
echo -e "${GREEN}═══════════════════════════════════════${NC}"
echo -e "${GREEN}  Deployment Complete!${NC}"
echo -e "${GREEN}═══════════════════════════════════════${NC}"
echo "Monitor logs with:"
echo "az vm run-command invoke --resource-group $RESOURCE_GROUP --name $VM_NAME --command-id RunShellScript --scripts 'tail -f ~/Repositories/cryptobot/faucet_bot.log'"
