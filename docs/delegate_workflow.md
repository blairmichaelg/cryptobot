# Efficient Delegation Workflow

## Overview

This document outlines the optimal workflow for delegating tasks to AI agents (Gemini and GitHub Copilot) within the `cryptobot` project, with a focus on **parallel execution without branches**.

## ⚠️ CRITICAL: Single-Branch Policy

**There is only ONE branch: `master`. No feature branches, no worktrees.**

All agents work toward `master` directly. Parallel execution is achieved through:
- Independent commits on the same branch
- Stashing to prevent local conflicts
- Minimal merge conflicts (via focused tasks)

## 1. Parallel Delegation Workflow

### Before Delegating

```bash
# Stash any uncommitted work
git stash

# Sync to latest master
git pull origin master
```

### During Delegation

You can delegate **multiple tasks in parallel** to different agents. Each agent:
1. Works in the background (cloud execution via `#github-pull-request_copilot-coding-agent`)
2. Commits independently to `master`
3. Merges via PR (if review needed) or auto-merges (if configured)
4. Returns to `master` clean—no branch cleanup needed

### After All Agents Complete

```bash
# Fetch latest updates
git fetch origin

# Pull all merged commits
git pull origin master

# Restore your stashed work (if any)
git stash pop
```

### Example: Three Agents Working in Parallel

```
Time 0: You stash work and delegate:
  - Agent A: "Implement CoinPayU faucet with tests"
  - Agent B: "Refactor CaptchaSolver for CapSolver support"
  - Agent C: "Add Cloudflare WAF bypass to stealth_scripts.py"

Time T: All three agents work simultaneously, committing to master as they complete.

Time T+N: You pull once. All changes are merged into master. No branches to clean up.
```

## 2. Task Delegation Types

### A. Parallel Background Work (Copilot Coding Agent)

Use the GitHub Copilot coding agent (`#github-pull-request_copilot-coding-agent`) for:
- Adding new faucet implementations
- Refactoring core modules
- Multi-step feature development
- Any task requiring testing before merge

**Why**: Executes in cloud, doesn't block local work, commits directly to `master`.

**Example**:
```
"#github-pull-request_copilot-coding-agent: Add BitCoinFaucet bot with 
login, balance extraction, claim logic, and 100% unit test coverage. 
Follow the FaucetBot pattern in faucets/base.py. Include proxy rotation."
```

### B. Inline Edits (GitHub Copilot in Editor)

For small, immediate fixes (one-liners, typos, inline refactors).

### C. Research & Audits (Gemini or Plan Agent)

For analysis without code changes, use `runSubagent` with the "Plan" agent:
```
Use runSubagent to research architectural decisions, audit security, analyze logs.
```

## 3. Managing Parallel Delegations

### Conflict Prevention

Since all agents target `master`, conflicts can happen. **Minimize them by**:

1. **Task Isolation**: Ensure tasks modify different files or distant code sections.
2. **Stashing**: Always stash local changes before delegation.
3. **Pull Before Delegating**: Ensure you're on the latest `master` before each delegation round.

### If Conflicts Occur

1. One agent's commit merges first
2. The second agent's PR shows conflict markers
3. That agent resolves and re-pushes
4. You pull the final merged state

This is rare if tasks are well-scoped.

## 4. Deployment Consistency

To ensure behavior matches between Local and Production:

1. **Tests**: Include test execution in task descriptions for agents.
2. **Proxies**: Ensure `config/proxies.txt` on the server contains at least one valid base proxy.
3. **Environment**: Use `scripts/check_environment.py` on the VM to verify dependencies.
4. **Service**: Restart after deployment: `sudo systemctl restart faucet_worker`.

## 5. Best Practices

- **Atomic Tasks**: Delegate small, focused tasks (single faucet, single refactor, single feature).
- **Stash Discipline**: Always stash local changes before delegation.
- **Sync Habit**: Always `git pull origin master` after agents complete.
- **Include Tests**: Have agents write tests as part of the implementation.
- **Clear Scope**: Specify files, functions, and expected behavior in task descriptions.

## 6. Workflow Cheat Sheet

```bash
# START: Delegate a task
git stash                          # Stash local work
git pull origin master             # Sync
# Delegate Task A and Task B to different agents

# MONITOR
git fetch origin                   # Check for updates (don't pull yet)

# END: When agents are done
git pull origin master             # Pull all merged commits
git stash pop                      # Restore your work

# No branch cleanup. No PR management. Just clean master.
```

## 7. Example: Multi-Agent Parallel Development

**Scenario**: Add support for 3 new faucets in parallel.

```bash
# Setup
git stash && git pull origin master

# Delegate three agents (all at once)
#github-pull-request_copilot-coding-agent: Task 1 - Add CoinPayU faucet
#github-pull-request_copilot-coding-agent: Task 2 - Add BitcoinCore faucet
#github-pull-request_copilot-coding-agent: Task 3 - Add Uniswap faucet

# Each agent:
# 1. Writes faucets/coinpayu.py (Task 1)
# 2. Writes tests/test_coinpayu.py
# 3. Updates core/registry.py
# 4. Commits and pushes to master

# After ~N minutes, all three agents complete
git pull origin master             # One pull gets all three faucets

# Result: Clean master with 3 new features, zero branch management.
```
