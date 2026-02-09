# Developer Guide & Agent Workflow

This guide outlines the standard operating procedures, architecture, and workflows for developing and deploying the Gen 3.0 Crypto Faucet Farm.

> [!IMPORTANT]
> **CRITICAL CONTEXT**
>
> 1. **OS**: Development is on Windows (Git Bash/Powershell), Production is Linux (Azure VM at 4.155.230.212).
> 2. **Current Deployment**: Azure VM (DevNode01) is ACTIVE — `~/Repositories/cryptobot` with systemd `faucet_worker` service.
> 3. **Git**: Single branch (`master`) only. Keep local, remote (GitHub), and VM in sync at all times.
> 4. **Paths**: Always use `pathlib` for cross-platform compatibility.
> 5. **Stealth**: Standardized on `Camoufox` with session-based proxy rotation.

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

**Current Status**: Azure VM (DevNode01) is ACTIVE at 4.155.230.212.

The production deployment uses `~/Repositories/cryptobot` on the VM with systemd `faucet_worker` service.

### Deployment Workflow (Keep Everything in Sync)

1. **Push from local**: `git push origin master`
2. **Pull on VM**: `ssh azureuser@4.155.230.212 "cd ~/Repositories/cryptobot && git pull origin master"`
3. **Install deps** (if requirements.txt changed): `ssh azureuser@4.155.230.212 "cd ~/Repositories/cryptobot && pip install -r requirements.txt"`
4. **Restart**: `ssh azureuser@4.155.230.212 "sudo systemctl restart faucet_worker"`
5. **Verify**: `ssh azureuser@4.155.230.212 "sudo systemctl status faucet_worker"`

### Automated Deploy

```bash
./deploy/azure_deploy.sh --resource-group APPSERVRG --vm-name DevNode01
```

### Local Development (Code Editing Only)

The Windows machine is for editing code. Run tests and the bot on the Azure VM.

```powershell
# Edit code, then push
git add . && git commit -m "feat: description" && git push origin master

# Test on VM
ssh azureuser@4.155.230.212 "cd ~/Repositories/cryptobot && git pull && HEADLESS=true pytest"

# Run single faucet test on VM
ssh azureuser@4.155.230.212 "cd ~/Repositories/cryptobot && HEADLESS=true python main.py --single firefaucet --once"
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

**Debug Steps** (run on VM, not Windows):
```bash
# SSH to VM first
ssh azureuser@4.155.230.212

# Run with visible browser (if X11 forwarding or VNC available)
cd ~/Repositories/cryptobot
HEADLESS=true python main.py --single freebitcoin --once

# Check logs for specific error
grep "FreeBitcoin" logs/faucet_bot.log | tail -20
```

#### Pick.io Family
**Status**: All 11 faucets fully implemented (LTC, TRX, DOGE, SOL, BNB, BCH, TON, MATIC, DASH, ETH, USDT)

All Pick.io faucets inherit from `PickFaucetBase` in `faucets/pick_base.py` which provides the shared login implementation. Each coin-specific faucet sets its `base_url` and is registered in `core/registry.py`.

### System Health

- **Earnings**: Monitor `earnings_analytics.json`.
- **Proxies**: Check health with `python meta.py health` - Dead proxies are automatically rotated. 
  - Current: 98/101 healthy, avg latency 1767ms
  - Check `logs/faucet_bot.log` for "Proxy mismatch" warnings if issues persist.
- **Browser**: If `Camoufox` fails to launch, check for zombie Firefox processes.
- **Heartbeat**: File `logs/heartbeat.txt` should update every 60 seconds when system is running.

### Performance Monitoring (Run on VM)

```bash
# SSH to VM
ssh azureuser@4.155.230.212
cd ~/Repositories/cryptobot

# Check current system health
python meta.py health

# View recent activity
tail -50 logs/faucet_bot.log

# Check heartbeat
cat /tmp/cryptobot_heartbeat

# Analyze profitability (when enough data exists)
python meta.py profitability
```
