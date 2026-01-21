# Cryptobot Workflow

> [!IMPORTANT]
> - Azure CLI is available; do not gate on checking `az`.
> - Proxy strategy uses session-based rotation; avoid IP allowlists.
> - Always run headless tests before deployment.

Operational guardrails and delegation guidance for the faucet farm.

## 1. Delegation

- Gemini (Plan agent): research, audits, complex analysis.
- Copilot: quick fixes, unit tests, boilerplate.
- Copilot Coding Agent: multi-step coding tasks; invoke with `#github-pull-request_copilot-coding-agent` when offloading.

Delegation flow: pull `master`, stash/commit local changes, delegate, then pull and test before pushing.

## 2. Repository Workflow

- Single branch: `master` only within this repo. No worktrees.
- Fork users may branch in their fork; PRs must target `master`.
- Keep commits small and descriptive; prefer conventional prefixes.
- Run `pytest` and `$env:HEADLESS="true"; pytest` before pushing.

## 3. Deployment Consistency

- Local (Windows) vs prod (Linux/Azure VM): use `pathlib.Path` everywhere.
- Headless parity: run tests with `HEADLESS=true` locally.
- Optional Docker parity: `docker build -t cryptobot .`.
- Service settings live in `deploy/faucet_worker.service`; deploy with `./deploy/deploy.sh --install-service` and restart via `sudo systemctl restart faucet_worker`.

## 4. Profitability and Robustness

- Monitor `earnings_analytics.json` and reports for regression detection.
- Keep ProxyManager active; update `config/proxies.txt` if failures spike.
- Use retries and page reloads instead of silent failures; log diagnostics with context.

## 5. Coordination & Handoffs

- Update `task.md` when you finish a session or major task; keep status lists current.
- Leave a brief summary in `COORDINATION.md` (or the latest walkthrough) using the handoff template:
  - Last Active Agent: <name>
  - Task Completed: <brief>
  - Current Blockers: <issues>
  - Next Steps Planned: <immediate actions>
- Label issues/PRs (`enhancement`, `bug`, `priority:high`) and reference issue numbers in PRs.
- Avoid force pushes; stay synced with `git pull origin master`.
