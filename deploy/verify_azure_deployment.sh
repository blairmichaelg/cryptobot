#!/bin/bash
# Azure VM Deployment Verification Script
# This script verifies that the faucet_worker service is correctly deployed and running
# Usage: ./deploy/verify_azure_deployment.sh

set -e

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

echo -e "${GREEN}╔════════════════════════════════════════════════════════════╗${NC}"
echo -e "${GREEN}║   Azure VM Deployment Verification                         ║${NC}"
echo -e "${GREEN}╔════════════════════════════════════════════════════════════╗${NC}"
echo ""

# Determine working directory
if [ -d "/home/azureuser/Repositories/cryptobot" ]; then
    WORK_DIR="/home/azureuser/Repositories/cryptobot"
elif [ -d "$HOME/Repositories/cryptobot" ]; then
    WORK_DIR="$HOME/Repositories/cryptobot"
else
    WORK_DIR="$(pwd)"
fi

echo -e "${YELLOW}Working Directory:${NC} $WORK_DIR"
echo ""

# Test 1: Verify typing imports in browser module
echo -e "${YELLOW}[1/8]${NC} Verifying typing imports in browser/instance.py..."
cd "$WORK_DIR"

if grep -q "from typing import.*Dict" browser/instance.py; then
    echo -e "${GREEN}✅${NC} Dict import found in browser/instance.py"
else
    echo -e "${RED}❌${NC} Dict import missing in browser/instance.py"
    echo "Expected line: from typing import Optional, List, Dict, Any"
    exit 1
fi

# Test 2: Verify __future__ annotations
if grep -q "from __future__ import annotations" browser/instance.py; then
    echo -e "${GREEN}✅${NC} Future annotations import found (enhanced guard)"
else
    echo -e "${YELLOW}⚠${NC}  Future annotations import not found (optional)"
fi

# Test 3: Python syntax check
echo -e "${YELLOW}[2/8]${NC} Checking Python syntax in browser module..."
python3 -m py_compile browser/instance.py 2>/dev/null && echo -e "${GREEN}✅${NC} browser/instance.py syntax valid" || {
    echo -e "${RED}❌${NC} Syntax error in browser/instance.py"
    exit 1
}

python3 -m py_compile browser/secure_storage.py 2>/dev/null && echo -e "${GREEN}✅${NC} browser/secure_storage.py syntax valid" || {
    echo -e "${RED}❌${NC} Syntax error in browser/secure_storage.py"
    exit 1
}

# Test 4: Import test
echo -e "${YELLOW}[3/8]${NC} Testing Python imports..."
python3 -c "from browser.instance import BrowserManager; print('✅ BrowserManager import successful')" 2>&1 | grep -q "✅" && echo -e "${GREEN}✅${NC} Browser module imports work" || {
    echo -e "${RED}❌${NC} Import error detected"
    python3 -c "from browser.instance import BrowserManager" 2>&1
    exit 1
}

# Test 5: Check systemd service exists
echo -e "${YELLOW}[4/8]${NC} Checking systemd service configuration..."
if [ -f "/etc/systemd/system/faucet_worker.service" ]; then
    echo -e "${GREEN}✅${NC} faucet_worker.service exists"
    
    # Show working directory from service file
    WORK_DIR_FROM_SERVICE=$(grep "^WorkingDirectory=" /etc/systemd/system/faucet_worker.service | cut -d= -f2)
    echo -e "   Service WorkingDirectory: ${WORK_DIR_FROM_SERVICE}"
    
    if [ "$WORK_DIR" != "$WORK_DIR_FROM_SERVICE" ]; then
        echo -e "${YELLOW}⚠${NC}  Warning: Current directory ($WORK_DIR) differs from service directory ($WORK_DIR_FROM_SERVICE)"
    fi
else
    echo -e "${RED}❌${NC} faucet_worker.service not found"
    exit 1
fi

# Test 6: Check service status
echo -e "${YELLOW}[5/8]${NC} Checking service status..."
if systemctl is-active --quiet faucet_worker; then
    echo -e "${GREEN}✅${NC} faucet_worker service is active (running)"
else
    echo -e "${RED}❌${NC} faucet_worker service is not running"
    echo -e "   Status:"
    sudo systemctl status faucet_worker --no-pager -n 10 || true
    exit 1
fi

# Test 7: Check for recent errors in logs
echo -e "${YELLOW}[6/8]${NC} Checking for NameError in recent logs..."
if sudo journalctl -u faucet_worker -n 100 --no-pager 2>/dev/null | grep -q "NameError.*Dict"; then
    echo -e "${RED}❌${NC} NameError: Dict found in recent logs"
    echo -e "   Recent errors:"
    sudo journalctl -u faucet_worker -n 20 --no-pager | grep -i "error\|dict" || true
    exit 1
else
    echo -e "${GREEN}✅${NC} No Dict-related errors in recent logs"
fi

# Test 8: Check heartbeat (if available)
echo -e "${YELLOW}[7/8]${NC} Checking heartbeat..."
HEARTBEAT_FILE="/tmp/cryptobot_heartbeat"
if [ -f "$HEARTBEAT_FILE" ]; then
    HB_TS=$(head -1 "$HEARTBEAT_FILE" | tr -d '\r')
    NOW=$(date +%s)
    
    if [ -n "$HB_TS" ] && [ "$((NOW - HB_TS))" -lt 300 ]; then
        AGE=$((NOW - HB_TS))
        echo -e "${GREEN}✅${NC} Heartbeat is fresh (${AGE}s old)"
    else
        echo -e "${YELLOW}⚠${NC}  Heartbeat is stale or invalid"
    fi
else
    echo -e "${YELLOW}⚠${NC}  Heartbeat file not found (service may be starting)"
fi

# Test 9: Service uptime
echo -e "${YELLOW}[8/8]${NC} Checking service uptime..."
UPTIME=$(systemctl show faucet_worker --property=ActiveEnterTimestamp --value 2>/dev/null || echo "unknown")
if [ "$UPTIME" != "unknown" ] && [ -n "$UPTIME" ]; then
    echo -e "${GREEN}✅${NC} Service started at: $UPTIME"
else
    echo -e "${YELLOW}⚠${NC}  Could not determine service uptime"
fi

echo ""
echo -e "${GREEN}╔════════════════════════════════════════════════════════════╗${NC}"
echo -e "${GREEN}║             ✅ ALL VERIFICATION CHECKS PASSED              ║${NC}"
echo -e "${GREEN}╔════════════════════════════════════════════════════════════╗${NC}"
echo ""
echo -e "The Azure VM deployment is ${GREEN}healthy${NC}."
echo -e "No Dict import errors detected."
echo ""
echo "To monitor logs in real-time, run:"
echo "  sudo journalctl -u faucet_worker -f"
echo ""
