#!/bin/bash
###############################################################################
# Azure Proxy Health Check Script
# Tests connectivity and latency of all Azure VM proxies
###############################################################################

set -euo pipefail

GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m'

PROXY_FILE="$(dirname "$0")/../config/azure_proxies.txt"

if [ ! -f "$PROXY_FILE" ]; then
    echo -e "${RED}✗ Proxy file not found: $PROXY_FILE${NC}"
    exit 1
fi

echo -e "${GREEN}╔══════════════════════════════════════════════════════════════╗${NC}"
echo -e "${GREEN}║           Azure Proxy Health Check                          ║${NC}"
echo -e "${GREEN}╚══════════════════════════════════════════════════════════════╝${NC}"
echo ""

TOTAL=0
WORKING=0
FAILED=0

while IFS= read -r line; do
    # Skip comments and empty lines
    [[ "$line" =~ ^#.*$ ]] && continue
    [[ -z "$line" ]] && continue
    
    ((TOTAL++))
    
    echo -e "${YELLOW}Testing:${NC} $line"
    
    # Test Google (fast, reliable)
    START=$(date +%s%N)
    HTTP_CODE=$(timeout 15 curl -s -x "$line" -o /dev/null -w "%{http_code}" https://www.google.com 2>/dev/null || echo "000")
    END=$(date +%s%N)
    LATENCY=$(( (END - START) / 1000000 ))  # Convert to milliseconds
    
    if [ "$HTTP_CODE" = "200" ]; then
        ((WORKING++))
        echo -e "${GREEN}  ✓ OK${NC} - ${LATENCY}ms - HTTP $HTTP_CODE"
        
        # Test Cloudflare site (faucet simulation)
        echo -e "${YELLOW}  Testing Cloudflare bypass...${NC}"
        CF_CODE=$(timeout 15 curl -s -x "$line" -o /dev/null -w "%{http_code}" https://autofaucet.dutchycorp.space/ 2>/dev/null || echo "000")
        if [ "$CF_CODE" = "200" ]; then
            echo -e "${GREEN}  ✓ Cloudflare bypass successful${NC}"
        elif [ "$CF_CODE" = "403" ]; then
            echo -e "${RED}  ✗ Cloudflare 403 (proxy may be flagged)${NC}"
        else
            echo -e "${YELLOW}  ? Cloudflare returned HTTP $CF_CODE${NC}"
        fi
    else
        ((FAILED++))
        echo -e "${RED}  ✗ FAILED${NC} - HTTP $HTTP_CODE"
    fi
    
    echo ""
done < "$PROXY_FILE"

echo -e "${GREEN}╔══════════════════════════════════════════════════════════════╗${NC}"
echo -e "${GREEN}║                      Summary                                 ║${NC}"
echo -e "${GREEN}╚══════════════════════════════════════════════════════════════╝${NC}"
echo ""
echo -e "  Total Proxies: $TOTAL"
echo -e "  ${GREEN}Working: $WORKING${NC}"
echo -e "  ${RED}Failed: $FAILED${NC}"
echo ""

if [ $WORKING -eq $TOTAL ]; then
    echo -e "${GREEN}✓ All proxies are healthy!${NC}"
    exit 0
elif [ $WORKING -gt 0 ]; then
    echo -e "${YELLOW}⚠ Some proxies failed. Check logs above.${NC}"
    exit 0
else
    echo -e "${RED}✗ All proxies failed! Check Azure VM status.${NC}"
    exit 1
fi
