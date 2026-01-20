# Cryptobot Optimal Workflow

> [!IMPORTANT]
> **AGENT CONTEXT - READ THIS FIRST**
>
> 1. **Azure CLI**: IS INSTALLED. Do not check for `az` command existence; assume it works.
> 2. **Proxy Strategy**: We use **Session-Based Rotation** (appending `-session-ID` to username), NOT IP Whitelisting.
> 3. **Deployment**: Always run tests with `HEADLESS=true` before deployment.

This document outlines the standard operating procedures for development, delegation, and deployment of the Cryptobot.

## 1. Task Delegation Strategy

We use two primary agents for autonomous work. Choose the right tool for the job:

### **Gemini (`gemini`)** - The Architect & Researcher

**Use for:**

- **Complex Research**: "Why is the 2Captcha API failing?" or "Analyze the profitability of adding a new faucet."
- **Codebase Audits**: "Check all faucet modules for consistent error handling."
- **Test Generation**: "Write comprehensive property-based tests for the solver."
- **Documentation**: "Update the README to reflect recent changes."

**Command:**

```bash
gemini "Your comprehensive instruction here"
```

### **GitHub Copilot (`@copilot` / `/delegate`)** - The Coder & Implementer

**Use for:**

- **Boilerplate/Repetitive Code**: "Create a new faucet file for LitePick."
- **Unit Tests**: "Add coverage for this specific function."
- **Refactoring**: "Split this large function into smaller ones."
- **Quick Fixes**: "Fix the linting errors in this file."

**Workflow:**

1. **CLI**: Use `gh copilot suggest` for quick snippets.
2. **Issue Delegation**: create an issue and assign to `@copilot` for background work.
3. **Chat**: Use `@copilot` in PR comments to request changes.

---

## 2. GitHub Workflow

To maintain a robust codebase, follow this strict process:

1. **Issue First**: Every task must return an Issue (e.g., "Fix 2Captcha Proxy Bug").
2. **Branching**: Create a branch from `master`: `fix/issue-number-description`.
3. **Development**: Make changes locally.
4. **Pull Request**: Open a PR using `gh pr create`.
    - **Description**: Link the issue (e.g., "Fixes #12").
    - **Review**: Assign `@copilot` or a team member to review.
5. **Merge**: Only merge after checks pass (tests, lint).

---

## 3. Deployment Consistency

The production environment (Azure VM) differs from local Windows dev. To ensure consistency:

### **Key Differences**

- **OS**: Windows (Local) vs Linux (Prod)
- **Headless**: Usually False (Local) vs True (Prod)
- **Paths**: `C:\Users\...` vs `/home/azureuser/...`

### **Consistency Checklist**

1. **Always use `pathlib`**: Never hardcode backslashes `\` or forward slashes `/`. Use `Path.joinpath()`.
2. **Test Headless**: Before pushing, run tests with headless mode enforced:

    ```powershell
    $env:HEADLESS="true"; pytest
    ```

3. **Docker Validation**: Use the `Dockerfile` to verify linux compatibility locally if needed.

    ```bash
    docker build -t cryptobot .
    ```

4. **Service Config**: Ensure `deploy/faucet_worker.service` env vars match your intended production settings.

---

## 4. Profitability & Robustness

- **Monitor**: Check `earnings_analytics.json` daily.
- **Stealth**: Ensure `ProxyManager` rotation is active.
- **Retry**: Never fail silently. Use `Page.reload()` and exponential backoff.
