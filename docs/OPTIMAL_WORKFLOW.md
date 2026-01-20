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

To maintain consistency and uptime on the production VM:

### **Verification Before Deploy**

Always run tests in headless mode locally first:

```powershell
$env:HEADLESS="true"; pytest
```

### **Deployment Steps**

1. **Sync Code**: Use `deploy/deploy_vm.ps1` to push latest changes to the VM.
2. **Update Deps**: Run `pip install -r requirements.txt` on the VM if dependencies changed.
3. **Restart Service**:

   ```bash
   sudo systemctl restart faucet_worker
   ```

4. **Monitor Logs**: Keep an eye on the service log:

   ```bash
   journalctl -u faucet_worker -f
   ```

## 4. Profitability & Stealth

- **Proxies**: We use session-based rotation. Ensure `config/proxies.txt` has a valid base proxy.
- **Analytics**: Check `config/earnings_analytics.json` to verify success rates.
- **Stealth**: Camoufox randomized fingerprints are enabled by default. Do not disable `SCREENS_RANDOM` or `TIMEZONE_SPOOF`.
