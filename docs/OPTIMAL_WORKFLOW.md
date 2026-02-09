# Cryptobot Optimal Workflow Guide

This guide provides a consolidated view of the best practices for managing, developing, and deploying the Cryptobot.

## 1. Task Delegation & `/delegate`

Use the appropriate tool based on the complexity and scope of the task:

| Agent | Best For... | Command Example |
| :--- | :--- | :--- |
| **Gemini** | Research, Audits, Complex Refactors, Documentation | `gemini "Audit the solver for new site support"` |
| **Copilot** | Small Fixes, Unit Tests, Boilerplate, Linting | `/delegate create tests for core/extractor.py` |

### **The `/delegate` Workflow**

1. **Define the Issue**: Clearly state the problem in a GitHub issue.
2. **Call Delegate**: `/delegate <issue_id>` in the chat or `@copilot` in a comment.
3. **Review PR**: Check the PR created by the agent, run tests, and merge if satisfied.

## 2. GitHub & Development Workflow

All work is done on a single `master` branch. No feature branches, no worktrees.

- **Single Branch**: Commit directly to `master`. Never create branches.
- **Sync Always**: `git pull` before work, `git push` after commits, `git pull` on VM before restarting service.
- **Atomic Commits**: Keep commits focused and well-described using conventional commit format.
- **Review**: Use `gh pr status` and `git log` to review agent work before deploying.

## 3. Azure & Deployment

**Current Status**: Azure VM (DevNode01) is ACTIVE at 4.155.230.212.

### Deployment Workflow (Keep Local, Remote, and VM in Sync)

```bash
# 1. Push changes from local to GitHub
git push origin master

# 2. SSH to VM and pull
ssh azureuser@4.155.230.212 "cd ~/Repositories/cryptobot && git pull origin master"

# 3. Restart service
ssh azureuser@4.155.230.212 "sudo systemctl restart faucet_worker"

# 4. Verify
ssh azureuser@4.155.230.212 "sudo systemctl status faucet_worker"
```

### Automated Deploy

```bash
./deploy/azure_deploy.sh --resource-group APPSERVRG --vm-name DevNode01
```

### Monitoring

```bash
# Live logs
ssh azureuser@4.155.230.212 "journalctl -u faucet_worker -f"

# Health check
ssh azureuser@4.155.230.212 "cd ~/Repositories/cryptobot && python meta.py health"
```

### For Local Development (Code Editing Only)

Windows is for editing code only. Do NOT run Camoufox or browser tests locally.

```powershell
# Run linting/type checking locally
$env:HEADLESS="true"; pytest tests/ -k "not browser"
```

To test changes, push and run on the VM:

```bash
ssh azureuser@4.155.230.212 "cd ~/Repositories/cryptobot && git pull && HEADLESS=true pytest"
```

## 4. Profitability & Stealth

- **Proxies**: We use session-based rotation. Ensure `config/proxies.txt` has a valid base proxy.
- **Analytics**: Check `config/earnings_analytics.json` to verify success rates.
- **Stealth**: Camoufox randomized fingerprints are enabled by default. Do not disable `SCREENS_RANDOM` or `TIMEZONE_SPOOF`.
