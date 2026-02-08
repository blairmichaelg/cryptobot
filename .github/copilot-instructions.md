# Copilot Instructions (Cryptobot Gen 3.0)

## Branch & Repo Safety
- Work only on master in C:\Users\azureuser\Repositories\cryptobot; never create branches/worktrees; pull before changes, push after.
- Do not force reset/delete/push; if extra branches exist, review PRs/issues, sync, then delete only with approval.

## ⚠️ CRITICAL: Testing Environment Rules
**DO NOT run Camoufox or browser tests on this Windows machine.**
- The local Windows environment is for **code editing only** - NOT for running browser automation.
- Camoufox (Firefox-based stealth browser) requires **Linux** and will fail or behave incorrectly on Windows.
- All browser/faucet tests MUST be run on the **Azure VM (Linux, headless)**: `ssh azureuser@4.155.230.212`
- Production deployment is **Linux headless only** - tests must match production environment.
- Use `HEADLESS=true` when running any browser tests on the VM.
- If you need to test code changes: push to repo, pull on VM, run tests there.
- **Never suggest running `python test_*.py` or `python main.py` locally** - always SSH to the VM first.

## Current Project Status (Last Updated: 2026-01-24)
- **Environment**: Dual - Local Windows dev machine + Azure VM (DevNode01 in APPSERVRG)
- **Azure VM**: 4.155.230.212 (West US 2) - RUNNING but service CRASHING
- **Critical Issue**: faucet_worker service in crash loop - NameError: Dict not defined in browser/instance.py
- **VM Has Two Installations**: ~/backend_service (active, broken) + ~/Repositories/cryptobot (newer, not used)
- **Faucet Status**: 18 fully implemented (Pick.io family verified complete)
- **Known Issues**: FreeBitcoin bot has 100% login failure rate - needs investigation
- **Testing Phase**: Most analytics data is test data, limited production usage
- See docs/summaries/PROJECT_STATUS_REPORT.md and docs/azure/AZURE_VM_STATUS.md for complete details

## Architecture Snapshot
- main.py bootstraps JobScheduler in core/orchestrator.py; jobs carry next_run and requeue themselves—avoid manual event loops or asyncio.sleep in main flows.
- BrowserManager in browser/instance.py keeps Camoufox contexts per account, persisting encrypted cookies under config/cookies_encrypted/; proxies bind via config/proxy_bindings.json.
- Faucet bots in faucets/*.py inherit faucets/base.py (FaucetBot) and rely on core/extractor.py (DataExtractor) for timers/balances and solvers/captcha.py for Turnstile/hCaptcha/reCaptcha/image tokens.
- ProxyManager in core/proxy_manager.py rotates residential proxies with cooldown/burn windows (101 proxies, 98 healthy, 1767ms avg latency); analytics and wallet helpers live in core/analytics.py and core/wallet_manager.py.

## Implementation Patterns
- Faucets must implement async login/get_balance/get_timer/claim returning ClaimResult; never parse timers manually—use DataExtractor helpers.
- **Pick.io Family**: 11 faucets (LTC, TRX, DOGE, SOL, BNB, BCH, TON, MATIC, DASH, ETH, USDT) inherit from pick_base.py which provides login implementation.
- **Known Issue**: FreeBitcoin login failing 100% - selectors may need update or credentials issue.
- Use human_type/idle_mouse anti-detection helpers; webRTC hardening is automatic.
- All I/O async; public funcs typed; logging module only (no print); paths via pathlib.Path.
- Persisted state: config/faucet_state.json (queue), config/session_state.json, earnings_analytics.json; keep JSON valid to avoid scheduler stalls.

## Local Ops (Windows - Code Editing Only)
- Setup: cp .env.example .env and fill 2Captcha/CapSolver + faucet creds; optional Electrum RPC and Azure Monitor in core/azure_monitor.py.
- **DO NOT run browser tests on Windows** - Camoufox requires Linux. Use Windows only for editing code.
- To test changes: push code, SSH to VM (`ssh azureuser@4.155.230.212`), pull, then run tests there.
- Logs on VM: ~/Repositories/cryptobot/logs/faucet_bot.log; local logs are from old/broken test runs.

## Testing & Quality (Run on Linux VM Only)
- **All tests must run on the Azure VM**, not Windows: `ssh azureuser@4.155.230.212`
- On VM: `cd ~/Repositories/cryptobot && HEADLESS=true pytest` or `HEADLESS=true python main.py`
- Single faucet test on VM: `HEADLESS=true python main.py --single firefaucet --once`
- pytest.ini uses asyncio_mode=auto; always use HEADLESS=true for prod parity.
- Bots should catch/log exceptions instead of propagating.

## Deployment
- Azure VM: DevNode01 in APPSERVRG (4.155.230.212, West US 2) - RUNNING but service FAILING
- **Critical Issue**: faucet_worker service crashing - missing Dict import in browser/instance.py
- **Two Code Locations**: ~/backend_service (systemd active, has bugs) vs ~/Repositories/cryptobot (newer, not used)
- **Fix Required**: Either update ~/backend_service code OR reconfigure systemd to use ~/Repositories/cryptobot
- To deploy updates: Use deploy/azure_deploy.sh --resource-group APPSERVRG --vm-name DevNode01
- Health check: ssh azureuser@4.155.230.212 "sudo systemctl status faucet_worker"
- See docs/azure/AZURE_VM_STATUS.md for critical service failure details and remediation steps

## Common Tasks
- New faucet: create faucets/<name>.py subclassing FaucetBot; wire login/claim/balance/timer via DataExtractor; register in core/registry.py; add env creds and tests in tests/.
- Proxy updates: add to config/proxies.txt (user:pass@ip:port); set BotSettings.use_2captcha_proxies in .env to auto-fetch; proxies cooldown 5m, burn 12h.

## Troubleshooting Tips
- Browser fail: kill stray firefox; increase BotSettings.timeout for slow proxies; captcha issues → verify provider balance; job stalls → validate config/faucet_state.json; IP blocks → rotate residential proxies.

## Key References
- docs/DEVELOPER_GUIDE.md (workflow), docs/OPTIMAL_WORKFLOW.md (deploy), IMPLEMENTATION_NOTES.md (site specifics), docs/API.md (RPC), deploy/deploy.sh.
