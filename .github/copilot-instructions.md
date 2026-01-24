# Copilot Instructions (Cryptobot Gen 3.0)

## Branch & Repo Safety
- Work only on master in C:\Users\azureuser\Repositories\cryptobot; never create branches/worktrees; pull before changes, push after.
- Do not force reset/delete/push; if extra branches exist, review PRs/issues, sync, then delete only with approval.

## Current Project Status (Last Updated: 2026-01-24)
- **Environment**: Running on local Windows dev machine (C:\Users\azureuser)
- **Deployment**: No active Azure VM deployment (deployment scripts exist but unused)
- **Faucet Status**: 7 fully implemented, 11 Pick.io faucets partially implemented (missing login)
- **Known Issues**: FreeBitcoin bot has 100% login failure rate - needs investigation
- **Testing Phase**: Most analytics data is test data, limited production usage
- See PROJECT_STATUS_REPORT.md for complete system audit

## Architecture Snapshot
- main.py bootstraps JobScheduler in core/orchestrator.py; jobs carry next_run and requeue themselves—avoid manual event loops or asyncio.sleep in main flows.
- BrowserManager in browser/instance.py keeps Camoufox contexts per account, persisting encrypted cookies under config/cookies_encrypted/; proxies bind via config/proxy_bindings.json.
- Faucet bots in faucets/*.py inherit faucets/base.py (FaucetBot) and rely on core/extractor.py (DataExtractor) for timers/balances and solvers/captcha.py for Turnstile/hCaptcha/reCaptcha/image tokens.
- ProxyManager in core/proxy_manager.py rotates residential proxies with cooldown/burn windows (101 proxies, 98 healthy, 1767ms avg latency); analytics and wallet helpers live in core/analytics.py and core/wallet_manager.py.

## Implementation Patterns
- Faucets must implement async login/get_balance/get_timer/claim returning ClaimResult; never parse timers manually—use DataExtractor helpers.
- **Pick.io Family**: 11 faucets (LTC, TRX, DOGE, SOL, BNB, BCH, TON, MATIC, DASH, ETH, USDT) should inherit from pick_base.py which provides login implementation.
  - TronPick is correctly implemented as reference (has login via base, implements get_balance/get_timer/claim).
  - Other Pick.io faucets need same pattern: inherit pick_base, set base_url, implement coin-specific methods.
- **Known Issue**: FreeBitcoin login failing 100% - selectors may need update or credentials issue.
- Use human_type/idle_mouse anti-detection helpers; webRTC hardening is automatic.
- All I/O async; public funcs typed; logging module only (no print); paths via pathlib.Path.
- Persisted state: config/faucet_state.json (queue), config/session_state.json, earnings_analytics.json; keep JSON valid to avoid scheduler stalls.

## Local Ops
- Setup: cp .env.example .env and fill 2Captcha/CapSolver + faucet creds; optional Electrum RPC and Azure Monitor in core/azure_monitor.py.
- Run farm: python main.py; debug visibility: --visible; single faucet: --single firefaucet (or others); one-shot: --once; wallet check: --wallet-check.
- Logs: logs/faucet_bot.log and heartbeat.txt; watch proxy binding in config/proxy_bindings.json.

## Testing & Quality
- Tests: pytest or HEADLESS=true pytest; single: pytest -k name; pytest.ini uses asyncio_mode=auto.
- Prefer HEADLESS=true for prod parity; bots should catch/log exceptions instead of propagating.

## Deployment
- Azure VM/Linux: deploy/deploy.sh (installs/updates systemd via deploy/faucet_worker.service, logrotate); health check: python meta.py health.
- **Current Status**: No active Azure VM deployment. Scripts are ready but system runs locally on Windows dev machine.
- To deploy to Azure: Use deploy/azure_deploy.sh --resource-group <RG> --vm-name <VM> OR deploy/deploy_vm.ps1 -VmIp <IP> -SshKey <path>
- Service runs: python main.py via systemd on Linux; logs to logs/production_run.log.
- Health monitoring: Heartbeat file updates every 60s; check with meta.py health.

## Common Tasks
- New faucet: create faucets/<name>.py subclassing FaucetBot; wire login/claim/balance/timer via DataExtractor; register in core/registry.py; add env creds and tests in tests/.
- Proxy updates: add to config/proxies.txt (user:pass@ip:port); set BotSettings.use_2captcha_proxies in .env to auto-fetch; proxies cooldown 5m, burn 12h.

## Troubleshooting Tips
- Browser fail: kill stray firefox; increase BotSettings.timeout for slow proxies; captcha issues → verify provider balance; job stalls → validate config/faucet_state.json; IP blocks → rotate residential proxies.

## Key References
- docs/DEVELOPER_GUIDE.md (workflow), docs/OPTIMAL_WORKFLOW.md (deploy), IMPLEMENTATION_NOTES.md (site specifics), docs/API.md (RPC), deploy/deploy.sh.
