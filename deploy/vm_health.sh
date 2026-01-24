#!/bin/bash
# VM Health Check Script with Service Monitoring and Alerting
# Usage: ./vm_health.sh --resource-group <RG> --vm-name <VM> [--alert] [--restart]

set -e

# Parse arguments
RESOURCE_GROUP=""
VM_NAME=""
ALERT_ENABLED=false
AUTO_RESTART=false

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
        --alert)
            ALERT_ENABLED=true
            shift
            ;;
        --restart)
            AUTO_RESTART=true
            shift
            ;;
        *)
            echo "Unknown option: $1"
            echo "Usage: $0 --resource-group <RG> --vm-name <VM> [--alert] [--restart]"
            exit 1
            ;;
    esac
done

if [ -z "$RESOURCE_GROUP" ] || [ -z "$VM_NAME" ]; then
    echo "Usage: $0 --resource-group <RG> --vm-name <VM> [--alert] [--restart]"
    exit 1
fi

# Color codes for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Health status flags
HEALTH_STATUS="OK"
ALERTS=()

echo "🔍 Checking health for VM: $VM_NAME in Resource Group: $RESOURCE_GROUP"
echo "=================================================="

# 1. OS and VM Status
echo ""
echo "💻 VM Status:"
VM_STATUS=$(az vm get-instance-view --resource-group "$RESOURCE_GROUP" --name "$VM_NAME" --query "instanceView.statuses[1].displayStatus" -o tsv)
echo "   $VM_STATUS"
if [ "$VM_STATUS" != "VM running" ]; then
    HEALTH_STATUS="CRITICAL"
    ALERTS+=("VM is not running: $VM_STATUS")
fi

# 2. Faucet Worker Service Status
echo ""
echo "🤖 Faucet Worker Service:"
SERVICE_CHECK=$(az vm run-command invoke --resource-group "$RESOURCE_GROUP" --name "$VM_NAME" \
    --command-id RunShellScript \
    --scripts "systemctl is-active faucet_worker 2>&1 || echo 'inactive'" \
    --query "value[0].message" -o tsv 2>/dev/null | grep -o 'active\|inactive\|failed' | head -1)

SERVICE_STATUS=$(az vm run-command invoke --resource-group "$RESOURCE_GROUP" --name "$VM_NAME" \
    --command-id RunShellScript \
    --scripts "systemctl status faucet_worker --no-pager -l 2>&1 | head -20" \
    --query "value[0].message" -o tsv 2>/dev/null)

if [ "$SERVICE_CHECK" == "active" ]; then
    echo -e "   ${GREEN}✅ Service is active${NC}"
    
    # Check for recent restarts (crash loop detection)
    RESTART_COUNT=$(echo "$SERVICE_STATUS" | grep -o 'Restart' | wc -l)
    if [ "$RESTART_COUNT" -gt 5 ]; then
        HEALTH_STATUS="WARNING"
        ALERTS+=("Service has restarted $RESTART_COUNT times - possible crash loop")
        echo -e "   ${YELLOW}⚠️  Warning: Detected $RESTART_COUNT restarts${NC}"
    fi
elif [ "$SERVICE_CHECK" == "failed" ]; then
    HEALTH_STATUS="CRITICAL"
    ALERTS+=("faucet_worker service has failed")
    echo -e "   ${RED}❌ Service has failed${NC}"
    echo "   Status details:"
    echo "$SERVICE_STATUS" | sed 's/^/      /'
    
    # Auto-restart if enabled
    if [ "$AUTO_RESTART" = true ]; then
        echo ""
        echo "   🔄 Attempting automatic restart..."
        az vm run-command invoke --resource-group "$RESOURCE_GROUP" --name "$VM_NAME" \
            --command-id RunShellScript \
            --scripts "sudo systemctl restart faucet_worker" \
            --query "value[0].message" -o tsv
        sleep 5
        SERVICE_CHECK=$(az vm run-command invoke --resource-group "$RESOURCE_GROUP" --name "$VM_NAME" \
            --command-id RunShellScript \
            --scripts "systemctl is-active faucet_worker 2>&1 || echo 'inactive'" \
            --query "value[0].message" -o tsv 2>/dev/null | grep -o 'active\|inactive\|failed' | head -1)
        if [ "$SERVICE_CHECK" == "active" ]; then
            echo -e "   ${GREEN}✅ Service restarted successfully${NC}"
        else
            echo -e "   ${RED}❌ Service restart failed${NC}"
        fi
    fi
else
    HEALTH_STATUS="CRITICAL"
    ALERTS+=("faucet_worker service is not running")
    echo -e "   ${RED}❌ Service is not running${NC}"
fi

# 3. Service Logs (last 10 errors)
echo ""
echo "📋 Recent Service Errors:"
RECENT_ERRORS=$(az vm run-command invoke --resource-group "$RESOURCE_GROUP" --name "$VM_NAME" \
    --command-id RunShellScript \
    --scripts "journalctl -u faucet_worker -p err -n 10 --no-pager 2>&1 || echo 'No recent errors'" \
    --query "value[0].message" -o tsv 2>/dev/null)
if echo "$RECENT_ERRORS" | grep -q "No recent errors"; then
    echo -e "   ${GREEN}✅ No recent errors${NC}"
else
    echo "$RECENT_ERRORS" | sed 's/^/   /'
    if [ "$HEALTH_STATUS" == "OK" ]; then
        HEALTH_STATUS="WARNING"
    fi
    ALERTS+=("Service has recent errors in logs")
fi

# 4. Disk Usage
echo ""
echo "💾 Disk Usage:"
DISK_USAGE=$(az vm run-command invoke --resource-group "$RESOURCE_GROUP" --name "$VM_NAME" \
    --command-id RunShellScript \
    --scripts "df -h / | tail -1 | awk '{print \$5}' | sed 's/%//'" \
    --query "value[0].message" -o tsv 2>/dev/null)
DISK_FULL=$(az vm run-command invoke --resource-group "$RESOURCE_GROUP" --name "$VM_NAME" \
    --command-id RunShellScript \
    --scripts "df -h / | tail -1" \
    --query "value[0].message" -o tsv 2>/dev/null)
echo "   $DISK_FULL"
if [ "$DISK_USAGE" -gt 90 ]; then
    HEALTH_STATUS="WARNING"
    ALERTS+=("Disk usage is high: ${DISK_USAGE}%")
    echo -e "   ${RED}⚠️  Disk usage critical: ${DISK_USAGE}%${NC}"
elif [ "$DISK_USAGE" -gt 80 ]; then
    echo -e "   ${YELLOW}⚠️  Disk usage warning: ${DISK_USAGE}%${NC}"
fi

# 5. CPU / Memory
echo ""
echo "🧠 CPU/Memory Load:"
az vm run-command invoke --resource-group "$RESOURCE_GROUP" --name "$VM_NAME" \
    --command-id RunShellScript \
    --scripts "uptime && free -h | grep Mem" \
    --query "value[0].message" -o tsv | sed 's/^/   /'

# 6. Git Sync Status
echo ""
echo "🔗 Git Sync Status:"
GIT_STATUS=$(az vm run-command invoke --resource-group "$RESOURCE_GROUP" --name "$VM_NAME" \
    --command-id RunShellScript \
    --scripts "cd ~/Repositories/cryptobot && git fetch && git status -sb 2>&1" \
    --query "value[0].message" -o tsv 2>/dev/null)
echo "$GIT_STATUS" | sed 's/^/   /'
if echo "$GIT_STATUS" | grep -q "behind"; then
    HEALTH_STATUS="WARNING"
    ALERTS+=("Code is behind remote repository")
fi

# 7. Bot Heartbeat
echo ""
echo "❤️  Bot Heartbeat:"
HEARTBEAT=$(az vm run-command invoke --resource-group "$RESOURCE_GROUP" --name "$VM_NAME" \
    --command-id RunShellScript \
    --scripts "if [ -f /tmp/cryptobot_heartbeat ]; then cat /tmp/cryptobot_heartbeat; elif [ -f ~/Repositories/cryptobot/logs/heartbeat.txt ]; then cat ~/Repositories/cryptobot/logs/heartbeat.txt; else echo 'No heartbeat found'; fi" \
    --query "value[0].message" -o tsv 2>/dev/null)
echo "   $HEARTBEAT"
if echo "$HEARTBEAT" | grep -q "No heartbeat found"; then
    HEALTH_STATUS="WARNING"
    ALERTS+=("No heartbeat file found")
fi

# 8. Log File Size
echo ""
echo "📁 Log File Size:"
LOG_SIZE=$(az vm run-command invoke --resource-group "$RESOURCE_GROUP" --name "$VM_NAME" \
    --command-id RunShellScript \
    --scripts "du -h ~/Repositories/cryptobot/logs/*.log 2>/dev/null | sort -h -r | head -5 || echo 'No logs found'" \
    --query "value[0].message" -o tsv 2>/dev/null)
echo "$LOG_SIZE" | sed 's/^/   /'

# Summary
echo ""
echo "=================================================="
if [ "$HEALTH_STATUS" == "OK" ]; then
    echo -e "${GREEN}✅ Overall Status: HEALTHY${NC}"
    exit 0
elif [ "$HEALTH_STATUS" == "WARNING" ]; then
    echo -e "${YELLOW}⚠️  Overall Status: WARNING${NC}"
    echo ""
    echo "Alerts:"
    for alert in "${ALERTS[@]}"; do
        echo -e "   ${YELLOW}• $alert${NC}"
    done
    
    # Send alerts if enabled
    if [ "$ALERT_ENABLED" = true ]; then
        echo ""
        echo "📧 Sending alerts..."
        # Alert logic would go here (webhook, email, etc.)
        # For now, just log the alerts
        for alert in "${ALERTS[@]}"; do
            logger -t cryptobot-health "WARNING: $alert"
        done
    fi
    exit 1
else
    echo -e "${RED}❌ Overall Status: CRITICAL${NC}"
    echo ""
    echo "Critical Alerts:"
    for alert in "${ALERTS[@]}"; do
        echo -e "   ${RED}• $alert${NC}"
    done
    
    # Send alerts if enabled
    if [ "$ALERT_ENABLED" = true ]; then
        echo ""
        echo "📧 Sending critical alerts..."
        # Alert logic would go here (webhook, email, etc.)
        for alert in "${ALERTS[@]}"; do
            logger -t cryptobot-health "CRITICAL: $alert"
        done
    fi
    exit 2
fi
