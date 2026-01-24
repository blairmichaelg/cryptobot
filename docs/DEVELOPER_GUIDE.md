# Developer Guide & Agent Workflow

This guide outlines the standard operating procedures, architecture, and workflows for developing and deploying the Gen 3.0 Crypto Faucet Farm.

> [!IMPORTANT]
> **CRITICAL CONTEXT**
>
> 1. **OS**: Development is on Windows (Git Bash/Powershell), Production is Linux (Azure VM).
> 2. **Current Deployment**: System is NOT deployed to Azure - runs locally on Windows dev machine only.
> 3. **Paths**: Always use `pathlib` for cross-platform compatibility.
> 4. **Stealth**: Standardized on `Camoufox` with session-based proxy rotation.

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

**Current Status**: No active Azure VM deployment. System runs locally on Windows development machine.

See [docs/DEPLOYMENT_STATUS.md](DEPLOYMENT_STATUS.md) for complete deployment documentation.

### When Azure VM Deployment is Active

The production environment is designed for an Azure VM running Ubuntu.

### Deployment Checklist

1. **Code Sync**: Use `deploy/deploy.sh` or `deploy/azure_deploy.sh` to sync code.
2. **Dependency Update**: If `requirements.txt` changed, install updates on VM.
3. **Service Restart**:

    ```bash
    sudo systemctl restart faucet_worker
    ```

4. **Health Check**:

    ```bash
    python meta.py health
    # OR from local machine:
    ./deploy/vm_health.sh <resource-group> <vm-name>
    ```

### Local Development (Current Mode)

Run the bot locally for testing:

```powershell
# Standard run
python main.py

# Visible browser (for debugging)
python main.py --visible

# Single faucet test
python main.py --single firefaucet

# Health check
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

### Common Issues

#### FreeBitcoin Login Failures
**Status**: Known issue - 100% failure rate as of Jan 24, 2026

**Symptoms**: 
- "Login failed, recording analytics and returning" in logs
- All FreeBitcoin claims return failed status

**Potential Causes**:
- Site selectors changed (needs investigation)
- Invalid credentials
- Anti-bot detection triggering
- Proxy IP blocking

**Debug Steps**:
```powershell
# Run with visible browser to see actual behavior
python main.py --single freebitcoin --visible

# Check logs for specific error
Get-Content logs/production_run.log | Select-String "FreeBitcoin"
```

#### Pick.io Family Implementation
**Status**: Incomplete - 10/11 faucets missing implementation

**Working**: TronPick (reference implementation)
**Missing**: LitePick, DogePick, SolPick, BchPick, BinPick, DashPick, EthPick, PolygonPick, TonPick, UsdPick

**Implementation Pattern** (use TronPick as reference):
1. Inherit from `PickFaucetBase`
2. Set `base_url` in __init__
3. Implement coin-specific methods (login is in base class)
4. Add to `core/registry.py`

### System Health

- **Earnings**: Monitor `earnings_analytics.json`.
- **Proxies**: Check health with `python meta.py health` - Dead proxies are automatically rotated. 
  - Current: 98/101 healthy, avg latency 1767ms
  - Check `logs/faucet_bot.log` for "Proxy mismatch" warnings if issues persist.
- **Browser**: If `Camoufox` fails to launch, check for zombie Firefox processes.
- **Heartbeat**: File `logs/heartbeat.txt` should update every 60 seconds when system is running.

### Performance Monitoring

```powershell
# Check current system health
python meta.py health

# View recent activity
Get-Content logs/production_run.log -Tail 50

# Check heartbeat
Get-Content logs/heartbeat.txt

# Analyze profitability (when enough data exists)
python meta.py profitability
```
