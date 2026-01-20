# Developer Guide & Agent Workflow

This guide outlines the standard operating procedures, architecture, and workflows for developing and deploying the Gen 3.0 Crypto Faucet Farm.

> [!IMPORTANT]
> **CRITICAL CONTEXT**
>
> 1. **OS**: Development is on Windows (Git Bash/Powershell), Production is Linux (Azure VM).
> 2. **Paths**: Always use `pathlib` for cross-platform compatibility.
> 3. **Stealth**: Standardized on `Camoufox` with session-based proxy rotation.

## 1. Development Workflow

### Branching Strategy

We follow a strict feature-branch workflow:

1. **Issue First**: Ensure every task has a corresponding GitHub Issue.
2. **Branch**: Create branches named `feat/<issue-id>-description` or `fix/<issue-id>-description`.
3. **Commit**: Use conventional commits (e.g., `feat: add fire faucet support`).
4. **Pull Request**: All changes merge via PR.

### Automated Testing

Before pushing, ensure tests pass.

- **Local**: `pytest`
- **Headless Check**: `$env:HEADLESS="true"; pytest` (simulates prod environment)

## 2. Agent Delegation Strategy

Use the right agent for the right task to maximize efficiency.

| Agent | Best For... | Command Example |
| :--- | :--- | :--- |
| **Gemini** | Research, Audits, Complex Refactors, Documentation | `gemini "Audit the solver for new site support"` |
| **Copilot** | Small Fixes, Unit Tests, Boilerplate, Linting | `/delegate create tests for core/extractor.py` |

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
