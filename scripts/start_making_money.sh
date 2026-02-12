#!/bin/bash
# Quick Action Checklist - Start Making Money This Week
# Run: bash scripts/start_making_money.sh

echo "💰 CRYPTOBOT PROFIT ACTIVATION CHECKLIST"
echo "=========================================="
echo ""

# Track progress
PROGRESS_FILE=~/cryptobot_progress.txt
touch $PROGRESS_FILE

echo "✅ COMPLETED: Faucets disabled (saving ~$0.02/day in wasted captchas)"
echo ""

echo "📋 WEEK 1 CHECKLIST - Pick 1-2 to start:"
echo ""

echo "[ ] OPTION A: Passive Income (EASIEST - 2 hours total)"
echo "    1. Sign up: https://earnapp.com (referral gets you $1 bonus)"
echo "    2. Get install command from dashboard"
echo "    3. SSH to each Azure VM and install"
echo "    4. Expected: $15/VM/month = $120/month total"
echo "    5. Time to first payment: 4-6 weeks"
echo ""

echo "[ ] OPTION B: Airdrop Research (HIGHEST UPSIDE - 4 hours)"
echo "    1. Twitter: Follow @0xLarry, @Defi_Airdrops"
echo "    2. Find current active: 'LayerZero airdrop guide'"
echo "    3. Test manually with 1 wallet first"
echo "    4. If profitable, automate with your bot"
echo "    5. Potential: $200-1000 per wallet × 12 = $2400-12000"
echo ""

echo "[ ] OPTION C: Fiverr Gig (RECURRING INCOME - 3 hours)"
echo "    1. Create account: fiverr.com"
echo "    2. Gig: 'I will scrape [website] data using 8 proxies'"
echo "    3. Price: $100-200 per project"
echo "    4. Deliver 1-2 projects = $200-400"
echo "    5. Build reviews, raise prices"
echo ""

echo "================================================"
echo ""

read -p "Which option do you want to START with? (A/B/C): " choice

case $choice in
  [Aa])
    echo ""
    echo "🎉 GREAT CHOICE! Passive income is the easiest."
    echo ""
    echo "Action steps:"
    echo "1. Open browser: https://earnapp.com"
    echo "2. Sign up and get your install command"
    echo "3. Come back here and I'll help install on all 8 VMs"
    echo ""
    echo "Your 8 Azure VMs:"
    ssh azureuser@4.155.230.212 'grep "edge-gateway" ~/Repositories/cryptobot/azure_proxies_fixed.txt || cat ~/Repositories/cryptobot/config/proxies.txt'
    echo ""
    echo "Once you have the install command, run:"
    echo "  bash scripts/install_passive_income.sh <YOUR_INSTALL_COMMAND>"
    ;;
    
  [Bb])
    echo ""
    echo "🎉 HIGH RISK, HIGH REWARD! Let's find a profitable airdrop."
    echo ""
    echo "Action steps:"
    echo "1. Open Twitter"
    echo "2. Search: 'LayerZero airdrop tutorial'"
    echo "3. Also search: 'zkSync airdrop guide'"
    echo "4. Look for guides with step-by-step tasks"
    echo ""
    echo "What you're looking for:"
    echo "- Clear qualification criteria"
    echo "- Tasks your bot can automate (bridge, swap, interact)"
    echo "- Active community (not dead project)"
    echo ""
    echo "Test with $20-50 on ONE wallet first as proof of concept"
    echo ""
    echo "When ready to automate, we'll create:"
    echo "  tasks/layerzero_farmer.py"
    echo "  tasks/zksync_farmer.py"
    ;;
    
  [Cc])
    echo ""
    echo "🎉 SMART! Recurring income is the most stable."
    echo ""
    echo "Action steps:"
    echo "1. Go to: fiverr.com"
    echo "2. Sign up as seller"
    echo "3. Create gig with this template:"
    echo ""
    echo "---COPY BELOW---"
    echo "Title: I will scrape any website data with 8 geographic proxies"
    echo ""
    echo "Description:"
    echo "Professional web scraping service using:"
    echo "- 8 different geographic locations (US, EU, Asia)"
    echo "- Anti-detection browser automation"
    echo "- Rotating proxies to avoid rate limits"
    echo "- Delivered as clean CSV/JSON/Excel"
    echo ""
    echo "Perfect for:"
    echo "- E-commerce product data"
    echo "- Price monitoring"
    echo "- Lead generation"
    echo "- Market research"
    echo ""
    echo "Price: $100 (starter), $200 (standard), $350 (premium)"
    echo "Delivery: 3-5 days"
    echo "---END COPY---"
    echo ""
    echo "Tags: web scraping, data extraction, python, automation"
    echo ""
    echo "When you get first order, message me and I'll help automate it"
    ;;
    
  *)
    echo "No problem! Read docs/PROFITABLE_OPPORTUNITIES.md"
    echo "Pick what sounds best and let's do it."
    ;;
esac

echo ""
echo "================================================"
echo "📚 Full Research: docs/PROFITABLE_OPPORTUNITIES.md"
echo "💪 You've got professional infrastructure worth $$$"
echo "🎯 Time to make it profitable!"
echo "================================================"
