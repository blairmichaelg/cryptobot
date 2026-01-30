#!/usr/bin/env bash
#
# deploy_digitalocean_proxies.sh
# Deploy 8 proxy servers on DigitalOcean using $200 GitHub Student Pack credit
#
# Usage: ./deploy_digitalocean_proxies.sh
#
# Prerequisites:
#   - DigitalOcean API token (from GitHub Student Pack)
#   - doctl CLI installed: snap install doctl
#

set -euo pipefail

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

# Configuration
REGION_1="nyc3"       # New York
REGION_2="sfo3"       # San Francisco  
REGION_3="lon1"       # London
REGION_4="fra1"       # Frankfurt
REGION_5="sgp1"       # Singapore

DROPLET_SIZE="s-1vcpu-1gb"  # $6/month = $48/month for 8 droplets = 4 months from $200 credit
DROPLET_IMAGE="ubuntu-22-04-x64"
PROXY_PORT="8888"
DEVNODE_IP="4.155.230.212"  # Azure VM that needs access

# Droplet names (stealth naming) - Limited to 4 due to new account restrictions
declare -A DROPLETS=(
    ["edge-node-ny1"]="$REGION_1"
    ["edge-node-ny2"]="$REGION_1"
    ["edge-node-sf1"]="$REGION_2"
    ["edge-node-lon1"]="$REGION_3"
)

# Cloud-init script to configure Tinyproxy
read -r -d '' CLOUD_INIT <<'EOF' || true
#!/bin/bash
export DEBIAN_FRONTEND=noninteractive

# Update and install Tinyproxy
apt-get update -qq
apt-get install -y tinyproxy

# Configure Tinyproxy for our use
cat > /etc/tinyproxy/tinyproxy.conf <<'TINYPROXY_EOF'
User tinyproxy
Group tinyproxy
Port 8888
Timeout 600
DefaultErrorFile "/usr/share/tinyproxy/default.html"
StatFile "/usr/share/tinyproxy/stats.html"
LogFile "/var/log/tinyproxy/tinyproxy.log"
LogLevel Info
PidFile "/run/tinyproxy/tinyproxy.pid"
MaxClients 100
MinSpareServers 5
MaxSpareServers 20
StartServers 10
MaxRequestsPerChild 0

# Allow DevNode01 Azure VM
Allow DEVNODE_IP_ACTUAL

# Disable ViaProxyName for stealth
DisableViaHeader Yes

# Filters
FilterURLs Off
FilterExtended Off

# Connection settings
ConnectPort 443
ConnectPort 563
TINYPROXY_EOF

# Replace placeholder with actual IP
sed -i "s/DEVNODE_IP_ACTUAL/DEVNODE_IP_PLACEHOLDER/g" /etc/tinyproxy/tinyproxy.conf

# Configure UFW firewall
ufw --force enable
ufw allow from DEVNODE_IP_PLACEHOLDER to any port 8888
ufw allow ssh

# Restart Tinyproxy
systemctl restart tinyproxy
systemctl enable tinyproxy

# Install curl for health checks
apt-get install -y curl

echo "Proxy setup complete on port 8888"
EOF

# Replace placeholder in cloud-init
CLOUD_INIT="${CLOUD_INIT//DEVNODE_IP_PLACEHOLDER/$DEVNODE_IP}"

echo -e "${GREEN}╔══════════════════════════════════════════════════════════════╗${NC}"
echo -e "${GREEN}║   DigitalOcean Proxy Infrastructure Deployment               ║${NC}"
echo -e "${GREEN}║   4 Droplets across 3 regions | \$200 Student credit        ║${NC}"
echo -e "${GREEN}╚══════════════════════════════════════════════════════════════╝${NC}"
echo ""

# Check if doctl is installed
echo -e "${YELLOW}[1/6] Checking doctl CLI installation...${NC}"
DOCTL_CMD=""
if command -v doctl &> /dev/null; then
    DOCTL_CMD="doctl"
elif command -v /snap/bin/doctl &> /dev/null; then
    DOCTL_CMD="/snap/bin/doctl"
else
    echo -e "${RED}ERROR: doctl CLI not found${NC}"
    echo "Install with: snap install doctl"
    echo "Then authenticate: doctl auth init"
    exit 1
fi

# Check authentication
echo -e "${YELLOW}[2/6] Checking DigitalOcean authentication...${NC}"
if ! $DOCTL_CMD account get &>/dev/null; then
    echo -e "${RED}ERROR: Not authenticated to DigitalOcean${NC}"
    echo "Run: $DOCTL_CMD auth init"
    exit 1
fi

ACCOUNT_EMAIL=$($DOCTL_CMD account get --format Email --no-header)
echo -e "${GREEN}✓ Authenticated as: $ACCOUNT_EMAIL${NC}"

# Create SSH key if needed
echo -e "${YELLOW}[3/6] Setting up SSH keys...${NC}"
SSH_KEY_NAME="cryptobot-proxy-key"
if ! $DOCTL_CMD compute ssh-key list --format Name --no-header | grep -q "^${SSH_KEY_NAME}$"; then
    if [ ! -f ~/.ssh/id_rsa.pub ]; then
        ssh-keygen -t rsa -b 4096 -f ~/.ssh/id_rsa -N ""
    fi
    $DOCTL_CMD compute ssh-key import "$SSH_KEY_NAME" --public-key-file ~/.ssh/id_rsa.pub
    echo -e "${GREEN}✓ SSH key uploaded${NC}"
else
    echo -e "${GREEN}✓ SSH key already exists${NC}"
fi

SSH_KEY_ID=$($DOCTL_CMD compute ssh-key list --format ID,Name --no-header | grep "$SSH_KEY_NAME" | awk '{print $1}')

# Deploy droplets
echo -e "${YELLOW}[4/6] Deploying 4 proxy droplets (~3 minutes)...${NC}"
echo -e "  Regions: NYC (2), SFO (1), LON (1)"
echo ""

# Write cloud-init to temp file
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CLOUD_INIT_FILE="$SCRIPT_DIR/.digitalocean-cloud-init.sh"
echo "$CLOUD_INIT" > "$CLOUD_INIT_FILE"

DROPLET_IDS=()

for DROPLET_NAME in "${!DROPLETS[@]}"; do
    REGION="${DROPLETS[$DROPLET_NAME]}"
    
    echo -e "  ${YELLOW}→${NC} Creating $DROPLET_NAME in $REGION..."
    
    DROPLET_ID=$($DOCTL_CMD compute droplet create "$DROPLET_NAME" \
        --region "$REGION" \
        --size "$DROPLET_SIZE" \
        --image "$DROPLET_IMAGE" \
        --ssh-keys "$SSH_KEY_ID" \
        --user-data-file "$CLOUD_INIT_FILE" \
        --wait \
        --format ID \
        --no-header)
    
    DROPLET_IDS+=("$DROPLET_ID")
    echo -e "  ${GREEN}✓${NC} Created droplet ID: $DROPLET_ID"
done

echo ""
echo -e "${GREEN}✓ All droplets created${NC}"

# Wait for droplets to become active
echo -e "${YELLOW}[5/6] Waiting for droplets to become active...${NC}"
sleep 30

# Collect proxy URLs
PROXY_FILE="$(dirname "$0")/../config/digitalocean_proxies.txt"
> "$PROXY_FILE"

echo -e "${YELLOW}[6/6] Collecting proxy IPs...${NC}"
echo ""

for DROPLET_ID in "${DROPLET_IDS[@]}"; do
    IP=$($DOCTL_CMD compute droplet get "$DROPLET_ID" --format PublicIPv4 --no-header)
    NAME=$($DOCTL_CMD compute droplet get "$DROPLET_ID" --format Name --no-header)
    
    echo "http://${IP}:${PROXY_PORT}" >> "$PROXY_FILE"
    echo -e "  ${GREEN}✓${NC} $NAME: http://${IP}:${PROXY_PORT}"
done

echo ""
echo -e "${GREEN}╔══════════════════════════════════════════════════════════════╗${NC}"
echo -e "${GREEN}║                  Deployment Complete!                        ║${NC}"
echo -e "${GREEN}╚══════════════════════════════════════════════════════════════╝${NC}"
echo ""
echo -e "${YELLOW}Proxy list:${NC} $PROXY_FILE"
echo -e "${YELLOW}Proxy count:${NC} $(wc -l < "$PROXY_FILE")"
echo ""
echo -e "${YELLOW}Next steps:${NC}"
echo "  1. Test proxies: ./deploy/test_digitalocean_proxies.sh"
echo "  2. Update .env: USE_DIGITALOCEAN_PROXIES=true"
echo "  3. Deploy to DevNode01: ./deploy/azure_deploy.sh"
echo ""
echo -e "${YELLOW}Monthly cost:${NC} \$48 (8 droplets × \$6/month)"
echo -e "${YELLOW}Credit remaining:${NC} \$152 from \$200 GitHub Student Pack"
echo ""
