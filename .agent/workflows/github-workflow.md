---
description: Optimal workflow for GitHub PR and issue management with delegation
---

# GitHub Management Workflow

Systematic approach to managing GitHub issues, PRs, and delegation to Copilot and Gemini agents.

## Daily Checkin

> **REMINDER**: This project uses `master` only. No feature branches. Keep local, remote, and VM in sync.

```bash
# Quick status check
gh pr list --state open
gh issue list --state open --label priority:high

# Verify no stale branches exist
git branch -a
# Should only show: master, remotes/origin/HEAD, remotes/origin/master
```

## PR Review Process

### 1. Review Open PRs

```bash
# List all open PRs with details
gh pr list --state open

# View specific PR (e.g., PR #3)
gh pr view 3

# Check CI/CD status
gh pr checks 3
```

### 2. Auto-Merge Strategy

**This project uses `master` only. Merge PRs via squash-merge and delete the branch immediately.**

**Criteria for auto-merge:**

- All CI checks passed
- At least 1 approval (or auto-approve for Copilot PRs)
- No merge conflicts
- Squash merge to keep history clean

```bash
# Squash merge and delete branch
gh pr merge 3 --squash --delete-branch

# Or enable auto-merge when checks pass
gh pr merge 3 --auto --squash --delete-branch
```

**After merging, sync everywhere:**
```bash
# Pull locally
git pull origin master

# Pull on VM
ssh azureuser@4.155.230.212 "cd ~/Repositories/cryptobot && git pull origin master"

# Prune stale remote refs
git remote prune origin
```

## Issue Delegation Strategy

### Agent Assignments

**Copilot** → Code implementation, test coverage, refactoring
**Gemini** → Research, documentation, analysis, optimization
**Antigravity** → Architecture, integration, complex debugging

### Delegation Commands

#### To Copilot (Code Tasks)

```bash
# Issue #27 - Profitability Monitoring
gh issue comment 27 --body "@copilot Please implement automated profitability monitoring as described. Use existing EarningsTracker and ProfitabilityOptimizer classes in core/analytics.py. Create a monitoring script that can be run via cron."

# Issue #21 - Analytics Dashboard  
gh issue comment 21 --body "@copilot Please create a web-based analytics dashboard. Use Flask or FastAPI for backend, integrate with EarningsTracker. Include charts for earnings over time, success rates, and profitability metrics."

# Issue #18 - Withdrawal Scheduling
gh issue comment 18 --body "@copilot Please integrate WithdrawalAnalytics into JobScheduler (core/orchestrator.py). Use existing withdrawal_wrapper in faucets/base.py and add scheduling based on optimal timing (off-peak hours)."

# Mark as delegated
gh issue edit 27 --add-label "delegated,copilot"
```

#### To Gemini (Research/Docs)

```bash
# Issue #20 - High-Yield Faucets Research
# Note: Gemini doesn't have GitHub integration, use gemini CLI directly
gemini "Research new high-yield crypto faucets for the cryptobot project. Focus on sites that: 1) Allow automation 2) Don't have aggressive proxy detection 3) Have reliable payment history 4) Support common cryptocurrencies. Document findings in docs/faucet_research.md"
```

#### Complex Issues (Antigravit)

- Multi-component changes requiring architectural decisions
- Integration between multiple systems (proxy + captcha + browser)
- Performance optimization across modules
- Complex debugging (site blocks, session management)

## Automation Script

Use the GitHub automation script for batch operations:

```bash
// turbo
# Dry run to see what would happen
bash deploy/github_automation.sh --dry-run

# Execute delegation and cleanup
bash deploy/github_automation.sh
```

## Weekly Maintenance

### Monday: Planning & Priority

```bash
# Review open issues by priority
gh issue list --state open --label priority:high

# Triage new issues
gh issue list --state open --label needs-triage

# Assign priorities
gh issue edit <NUM> --add-label "priority:high"
```

### Wednesday: Mid-Week Check

```bash
# Check delegated work progress
gh issue list --label delegated

# Review draft PRs from Copilot
gh pr list --draft

# Merge ready PRs
bash deploy/github_automation.sh
```

### Friday: Weekly Summary & Sync Check

```bash
# Generate weekly report (last 7 days)
gh issue list --state closed --search "closed:>=WEEK_AGO"
gh pr list --state merged --search "merged:>=WEEK_AGO"

# Verify no stale branches (should only be master)
git branch -a
git remote prune origin

# Verify VM is in sync with remote
ssh azureuser@4.155.230.212 "cd ~/Repositories/cryptobot && git log -1 --oneline"
git log -1 --oneline
# Both should show the same commit
```

## Best Practices

1. **Be Specific**: When delegating, provide exact file paths and method names
2. **Set Context**: Reference related issues, PRs, or documentation
3. **Define Success**: Clearly state what "done" looks like
4. **Review Promptly**: Don't let PRs sit open for days
5. **Communicate**: Add comments to PRs with questions or concerns

## Emergency Workflow

### Critical Bug Found

```bash
# Create high-priority issue
gh issue create --title "[CRITICAL] Proxy rotation causing bot bans" \
  --body "Description of issue..." \
  --label "bug,priority:high"

# Immediately delegate if straightforward
gh issue comment <NUM> --body "@copilot Please fix urgently..."

# Or handle directly if complex
# Work on fix → commit → push → create PR
```

### Production Outage

1. Check bot logs for errors
2. Create issue documenting the outage
3. Disable affected faucets in config if needed
4. Fix and deploy ASAP
5. Post-mortem analysis after resolution

## Monitoring Delegated Work

### Copilot PRs

- Usually created within 1-2 hours
- Review code quality and test coverage
- Check for edge cases and error handling
- Merge if satisfactory or request changes

### Tracking Progress

```bash
# Check if Copilot created a PR yet
gh issue view <NUM>

# See related PRs
gh pr list --search "linked:issue-<NUM>"
```

## Notes

- **Copilot Limits**: May struggle with very large scope changes (break into smaller issues)
- **Gemini CLI**: Better for research and documentation generation
- **Antigravity**: Use for strategic planning, architecture, and multi-system integration
