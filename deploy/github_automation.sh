#!/bin/bash
# GitHub CLI Automation Script for CryptoBot
# Handles PR and issue management, delegation, and auto-merge workflows

set -e

# Color output
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

DRY_RUN=false

# Parse arguments
while [[ $# -gt 0 ]]; do
    case $1 in
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

echo -e "${BLUE}═══════════════════════════════════════${NC}"
echo -e "${BLUE}  CryptoBot GitHub Automation${NC}"
echo -e "${BLUE}═══════════════════════════════════════${NC}"
echo ""

# Check if gh is installed and authenticated
if ! command -v gh &> /dev/null; then
    echo -e "${RED}GitHub CLI (gh) is not installed${NC}"
    echo "Install from: https://cli.github.com"
    exit 1
fi

if ! gh auth status &>/dev/null; then
    echo -e "${RED}Not authenticated with GitHub CLI${NC}"
    echo "Please run: gh auth login"
    exit 1
fi

echo -e "${GREEN}✓${NC} GitHub CLI authenticated"
echo ""

# Function to delegate issue to Copilot
delegate_to_copilot() {
    local issue_num=$1
    local task_description=$2
    
    if [ "$DRY_RUN" = true ]; then
        echo -e "${YELLOW}[DRY RUN]${NC} Would delegate issue #$issue_num to @copilot"
        echo "Comment: @copilot $task_description"
        return
    fi
    
    echo -e "${YELLOW}Delegating issue #$issue_num to Copilot...${NC}"
    gh issue comment $issue_num --body "@copilot $task_description"
    gh issue edit $issue_num --add-label "delegated"
    echo -e "${GREEN}✓${NC} Delegated issue #$issue_num"
}

# 1. List open PRs and issues
echo -e "${YELLOW}[1/5]${NC} Checking open PRs and issues..."
echo ""
echo -e "${BLUE}Open Pull Requests:${NC}"
gh pr list --state open
echo ""
echo -e "${BLUE}Open Issues:${NC}"
gh issue list --state open
echo ""

# 2. Check PR #3 status (Pick.io registrations)
echo -e "${YELLOW}[2/5]${NC} Reviewing PR #3 (Pick.io registrations)..."
PR_STATE=$(gh pr view 3 --json state -q '.state' 2>/dev/null || echo "NOT_FOUND")

if [ "$PR_STATE" = "OPEN" ]; then
    echo -e "${BLUE}PR #3 Status:${NC}"
    gh pr view 3
    echo ""
    
    # Check if CI passed
    CHECKS_PASSED=$(gh pr checks 3 --json state -q '.[].state' | grep -c "SUCCESS" || echo "0")
    
    if [ "$DRY_RUN" = true ]; then
        echo -e "${YELLOW}[DRY RUN]${NC} Would check if PR can be merged"
        echo "Checks passed: $CHECKS_PASSED"
    else
        if [ "$CHECKS_PASSED" -gt "0" ]; then
            echo -e "${GREEN}✓${NC} PR #3 checks passed, ready to merge"
            # Uncomment to auto-merge:
            # gh pr merge 3 --squash --auto
        else
            echo -e "${YELLOW}⚠${NC} PR #3 checks not yet passed"
        fi
    fi
else
    echo "PR #3 not found or already merged"
fi
echo ""

# 3. Delegate open issues
echo -e "${YELLOW}[3/5]${NC} Processing issue delegation..."

# Issue #27 - Profitability Monitoring (Code implementation)
if gh issue view 27 &>/dev/null; then
    delegate_to_copilot 27 "Please implement automated profitability monitoring as described in the issue. Use the existing EarningsTracker and ProfitabilityOptimizer classes in core/analytics.py. Create a monitoring script that can be run via cron or scheduled task."
fi

# Issue #21 - Analytics Dashboard (Code + UI)
if gh issue view 21 &>/dev/null; then
    delegate_to_copilot 21 "Please create a web-based analytics dashboard as described. Use Flask or FastAPI for the backend and integrate with the existing EarningsTracker. Include charts for earnings over time, success rates per faucet, and profitability metrics."
fi

# Issue #20 - High-Yield Faucets (Research)
if gh issue view 20 &>/dev/null; then
    if [ "$DRY_RUN" = true ]; then
        echo -e "${YELLOW}[DRY RUN]${NC} Would comment on issue #20 with research task"
    else
        echo -e "${YELLOW}Issue #20 requires manual research${NC}"
        gh issue comment 20 --body "📝 This issue requires research into new high-yield faucets. Will need to manually investigate and test candidate sites for proxy detection, payment reliability, and claim frequency before adding support."
        gh issue edit 20 --add-label "research,manual-task"
    fi
fi

# Issue #18 - Withdrawal Scheduling (Integration)
if gh issue view 18 &>/dev/null; then
    delegate_to_copilot 18 "Please integrate the WithdrawalAnalytics module into the JobScheduler in core/orchestrator.py. Use the existing withdrawal_wrapper method in faucets/base.py and add scheduling logic based on optimal timing (off-peak hours for lower fees)."
fi

echo ""

# 4. Weekly summary report
echo -e "${YELLOW}[4/5]${NC} Generating weekly activity summary..."
WEEK_AGO=$(date -d '7 days ago' +%Y-%m-%d 2>/dev/null || date -v-7d +%Y-%m-%d)

echo -e "${BLUE}Closed Issues (Last 7 Days):${NC}"
gh issue list --state closed --search "closed:>=$WEEK_AGO" --limit 10
echo ""

echo -e "${BLUE}Merged PRs (Last 7 Days):${NC}"
gh pr list --state merged --search "merged:>=$WEEK_AGO" --limit 10
echo ""

# 5. Cleanup old branches (optional)
echo -e "${YELLOW}[5/5]${NC} Branch cleanup check..."
MERGED_BRANCHES=$(git branch --merged master 2>/dev/null | grep -v "master" | grep -v "feature/consolidated-production-upgrade" | wc -l || echo "0")

if [ "$MERGED_BRANCHES" -gt "0" ]; then
    echo -e "${YELLOW}Found $MERGED_BRANCHES merged branches that can be cleaned up${NC}"
    if [ "$DRY_RUN" = false ]; then
        echo "Run 'git branch --merged master | grep -v master | xargs git branch -d' to clean up"
    fi
else
    echo -e "${GREEN}✓${NC} No merged branches to clean up"
fi

echo ""
echo -e "${BLUE}═══════════════════════════════════════${NC}"
echo -e "${BLUE}  Automation Complete!${NC}"
echo -e "${BLUE}═══════════════════════════════════════${NC}"
