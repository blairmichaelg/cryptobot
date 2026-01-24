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

Maintain a clean `master` branch by following these steps:

- **Always Branch**: Create a branch for every fix/feature (`fix/xx-desc` or `feat/xx-desc`).
- **Atomic Commits**: Keep commits focused and well-described.
- **Pull Requests**: Use `gh pr create` with a clear description linking back to the issue.
- **Review**: Use `gh pr status` and `gh pr diff` to review your own (or agent's) work before merging.

## 3. Azure & Deployment

**Current Status**: No active Azure VM deployment. See [DEPLOYMENT_STATUS.md](DEPLOYMENT_STATUS.md) for details.

### For Local Development (Current Mode)

Always run tests in headless mode locally first:

```powershell
$env:HEADLESS="true"; pytest
```

Run the bot:

```powershell
# Standard run
python main.py

# Debug mode (visible browser)
python main.py --visible

# Test specific faucet
python main.py --single firefaucet
```

### When Azure VM is Deployed (Future)

To maintain consistency and uptime on the production VM:

#### **Verification Before Deploy**

Always run tests in headless mode locally first:

```powershell
$env:HEADLESS="true"; pytest
```

#### **Deployment Steps**

1. **Provision VM** (if not exists):
   ```bash
   az group create --name cryptobot-rg --location eastus
   az vm create --resource-group cryptobot-rg --name cryptobot-vm \
     --image Ubuntu2204 --size Standard_B2s \
     --admin-username azureuser --generate-ssh-keys
   ```

2. **Deploy Code**:
   ```bash
   # Option A: Azure CLI-based deployment
   ./deploy/azure_deploy.sh --resource-group cryptobot-rg --vm-name cryptobot-vm
   
   # Option B: PowerShell-based deployment
   ./deploy/deploy_vm.ps1 -VmIp <IP> -SshKey ~/.ssh/id_rsa
   ```

3. **Restart Service**:

   ```bash
   ssh azureuser@<VM-IP> "sudo systemctl restart faucet_worker"
   ```

4. **Monitor Logs**: Keep an eye on the service log:

   ```bash
   ssh azureuser@<VM-IP> "journalctl -u faucet_worker -f"
   
   # OR use health check script
   ./deploy/vm_health.sh cryptobot-rg cryptobot-vm
   ```

## 4. Profitability & Stealth

- **Proxies**: We use session-based rotation. Ensure `config/proxies.txt` has a valid base proxy.
- **Analytics**: Check `config/earnings_analytics.json` to verify success rates.
- **Stealth**: Camoufox randomized fingerprints are enabled by default. Do not disable `SCREENS_RANDOM` or `TIMEZONE_SPOOF`.
