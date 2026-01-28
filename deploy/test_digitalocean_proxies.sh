#!/usr/bin/env bash
#
# test_digitalocean_proxies.sh
# Test DigitalOcean proxy health and Cloudflare bypass capability
#

set -euo pipefail

GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m'

PROXY_FILE="$(dirname "$0")/../config/digitalocean_proxies.txt"

if [ ! -f "$PROXY_FILE" ]; then
    echo -e "${RED}ERROR: Proxy file not found: $PROXY_FILE${NC}"
    echo "Run deploy_digitalocean_proxies.sh first"
    exit 1
fi

PROXY_COUNT=$(wc -l < "$PROXY_FILE")

echo -e "${GREEN}╔══════════════════════════════════════════════════════════════╗${NC}"
echo -e "${GREEN}║         DigitalOcean Proxy Health Check                      ║${NC}"
echo -e "${GREEN}╚══════════════════════════════════════════════════════════════╝${NC}"
echo ""
echo -e "${YELLOW}Testing $PROXY_COUNT proxies...${NC}"
echo ""

SUCCESS_COUNT=0
FAIL_COUNT=0

while IFS= read -r PROXY_URL; do
    [ -z "$PROXY_URL" ] && continue
    
    echo -e "${YELLOW}Testing:${NC} $PROXY_URL"
    
    # Test 1: Basic connectivity to Google (latency check)
    echo -n "  → Google connectivity... "
    START_TIME=$(date +%s%3N)
    if curl -s -x "$PROXY_URL" -o /dev/null -w "%{http_code}" --max-time 10 https://www.google.com | grep -q "200"; then
        END_TIME=$(date +%s%3N)
        LATENCY=$((END_TIME - START_TIME))
        echo -e "${GREEN}✓ ${LATENCY}ms${NC}"
        
        # Test 2: Cloudflare bypass (DutchyCorp faucet)
        echo -n "  → Cloudflare bypass... "
        CF_STATUS=$(curl -s -x "$PROXY_URL" -o /dev/null -w "%{http_code}" --max-time 15 https://autofaucet.dutchycorp.space || echo "TIMEOUT")
        
        if [ "$CF_STATUS" = "200" ] || [ "$CF_STATUS" = "301" ] || [ "$CF_STATUS" = "302" ]; then
            echo -e "${GREEN}✓ Status: $CF_STATUS${NC}"
            ((SUCCESS_COUNT++))
        elif [ "$CF_STATUS" = "403" ]; then
            echo -e "${RED}✗ BLOCKED (403)${NC}"
            ((FAIL_COUNT++))
        else
            echo -e "${YELLOW}⚠ Status: $CF_STATUS${NC}"
            ((FAIL_COUNT++))
        fi
    else
        echo -e "${RED}✗ FAILED${NC}"
        echo -e "  → Cloudflare bypass... ${RED}SKIPPED${NC}"
        ((FAIL_COUNT++))
    fi
    
    echo ""
done < "$PROXY_FILE"

echo -e "${GREEN}╔══════════════════════════════════════════════════════════════╗${NC}"
echo -e "${GREEN}║                    Test Summary                              ║${NC}"
echo -e "${GREEN}╚══════════════════════════════════════════════════════════════╝${NC}"
echo ""
echo -e "${GREEN}✓ Passed:${NC} $SUCCESS_COUNT / $PROXY_COUNT"
echo -e "${RED}✗ Failed:${NC} $FAIL_COUNT / $PROXY_COUNT"
echo ""

if [ $SUCCESS_COUNT -eq $PROXY_COUNT ]; then
    echo -e "${GREEN}All proxies operational! Ready for deployment.${NC}"
    exit 0
elif [ $SUCCESS_COUNT -gt 0 ]; then
    echo -e "${YELLOW}Some proxies working. You can proceed with $SUCCESS_COUNT working proxies.${NC}"
    exit 0
else
    echo -e "${RED}No proxies working. Check droplet status and firewall rules.${NC}"
    exit 1
fi
