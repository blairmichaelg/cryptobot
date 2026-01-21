# Developer Guide & Agent Workflow

This guide outlines the standard operating procedures, architecture, and workflows for developing and deploying the Gen 3.0 Crypto Faucet Farm.

> [!IMPORTANT]
> **CRITICAL CONTEXT**
>
> 1. **OS**: Development is on Windows (Git Bash/Powershell), Production is Linux (Azure VM).
> 2. **Paths**: Always use `pathlib` for cross-platform compatibility.
> 3. **Stealth**: Standardized on `Camoufox` with session-based proxy rotation.

## 1. Development Workflow

### Branching Strategy: Single Branch (`master`)

**CRITICAL**: There is only ONE branch: `master`. No feature branches, no worktrees.

1. **Always Work on `master`**: All local development and agent delegations target `master`.
2. **Stash Before Delegating**: If you have uncommitted work, stash it before delegating tasks to agents.
3. **Parallel Agent Execution**: Multiple agents can work simultaneously—they commit independently to `master`.
4. **Commit Convention**: Use conventional commits (e.g., `feat: add fire faucet support`).
5. **Pull After Agents Complete**: When agents finish, `git pull origin master` to merge all changes.

See [delegate_workflow.md](delegate_workflow.md) for detailed parallel delegation patterns.

### Automated Testing

Before pushing, ensure tests pass.

- **Local**: `pytest`
- **Headless Check**: `$env:HEADLESS="true"; pytest` (simulates prod environment)

## 2. Agent Delegation Strategy

Delegate tasks to agents for parallel, cloud-based execution without creating branches.

| Agent | Best For... | How to Use |
| :--- | :--- | :--- |
| **Copilot Coding Agent** | Adding faucets, refactoring modules, multi-step features | Use `#github-pull-request_copilot-coding-agent` tag in your request |
| **Copilot (Editor)** | Small inline fixes, one-liners, typos | Use inline Copilot suggestions in VS Code |
| **Plan Agent (runSubagent)** | Research, audits, architecture analysis | Use `runSubagent` tool with "Plan" agent |

### Parallel Delegation Example

```bash
# Setup
git stash && git pull origin master

# Delegate multiple agents at once
# (via Copilot: use #github-pull-request_copilot-coding-agent tag)

# Agent A: Implement faucet X
# Agent B: Implement faucet Y  
# Agent C: Refactor solver

# Each agent works in the cloud, commits independently to master

# After all complete
git pull origin master
```

**Result**: Clean `master` with all changes merged, zero branch cleanup.

## 3. Deployment (Azure VM)

The production environment is an Azure VM running Ubuntu.

### Deployment Checklist

1. **Code Sync**: Ensure `deploy/deploy.sh` is used to sync code.
2. **Dependency Update**: If `requirements.txt` changed, install updates on VM.
3. **Service Restart**:

    ```bash
    sudo systemctl restart faucet_worker
    ```

4. **Health Check**:

    ```bash
    python meta.py health
    ```

## 4. Architecture Standards

### Code Style

- **Type Hints**: Strongly encouraged for all new code.
- **Docstrings**: Required for all public modules, classes, and functions.
- **Logging**: Use `logging` module, never `print`.

### Directory Structure

- `core/`: Business logic (Orchestrator, Wallet, Config).
- `faucets/`: Bot implementations inheriting from `BaseFaucet`.
- `browser/`: Browser automation wrappers (Camoufox).
- `solvers/`: CAPTCHA and Shortlink logic.

## 5. Troubleshooting & Maintenance

- **Earnings**: Monitor `earnings_analytics.json`.
- **Proxies**: Dead proxies are automatically rotated. Check `logs/faucet_bot.log` for "Proxy mismatch" warnings if issues persist.
- **Browser**: If `Camoufox` fails to launch, check for zombie Firefox processes.
