# Copilot Instructions for Cryptobot Gen 3.0

## ⚠️ CRITICAL: Branch & Worktree Policy

**THERE IS ONLY ONE BRANCH: `master`. DO NOT CREATE OTHER BRANCHES OR WORKTREES.**

- **NEVER** create worktrees, feature branches, or copilot/* branches
- **NEVER** use `git worktree add` 
- **NEVER** create pull requests - commit directly to master
- **ALWAYS** work in `C:\Users\azureuser\Repositories\cryptobot` on `master`
- **ALWAYS** `git pull` before starting work and `git push` after committing
- **NEVER** force reset, force delete, or force push without explicit user permission
- **NEVER** delete branches without checking if they have unmerged/uncommitted work

If you find multiple worktrees or branches exist, ASK THE USER before deleting anything.

## Project Overview

**Gen 3.0 Crypto Faucet Farm** is a professional autonomous harvesting system for high-yield cryptocurrency faucets. It combines advanced browser stealth (Camoufox), CAPTCHA solving (2Captcha/CapSolver), and job-based concurrency orchestration to maximize earnings.

- **Language**: Python 3.10+
- **OS**: Windows dev, Linux production (Azure VM)
- **Core Pattern**: Async job scheduler with persistent browser contexts and proxy rotation

## Architecture at a Glance

```
main.py (entry point)
  └─> JobScheduler (core/orchestrator.py)
       ├─> BrowserManager (browser/instance.py) [Camoufox stealth contexts]
       ├─> ProxyManager (core/proxy_manager.py) [rotating residential IPs]
       └─> Faucet Bots (faucets/*.py)
            ├─> FaucetBot base class with standardized extraction
            ├─> CaptchaSolver (solvers/captcha.py)
            └─> DataExtractor (core/extractor.py)
```

**Key principle**: Jobs are enqueued with next-run times and executed by the scheduler in priority order, with domain-based rate limiting and proxy rotation built-in.

## Critical Patterns & Conventions

### 1. Standardized Faucet Implementation
All faucet bots inherit from `FaucetBot` and implement:
- `async def login()` - Authenticate with credentials
- `async def get_balance(selector)` - Extract balance using CSS selector
- `async def get_timer(selector)` - Extract countdown timer (returns minutes)
- `async def claim()` - Main claiming logic returning `ClaimResult(success, status, next_claim_minutes, amount, balance)`

**Example** ([faucets/firefaucet.py](faucets/firefaucet.py)):
```python
async def claim(self) -> ClaimResult:
    await self.page.goto(self.base_url, wait_until="networkidle")
    balance = await self.get_balance(".user-balance")
    timer_mins = await self.get_timer("#claim_timer")
    # ... solve captcha, click button
    return ClaimResult(success=True, status="claimed", next_claim_minutes=timer_mins, balance=balance)
```

### 2. DataExtractor for Consistent Parsing
Use `DataExtractor` for all timer and balance extractions—it handles multiple formats (HH:MM:SS, "Xh Ym Zs", etc.). Never parse timers manually.

```python
from core.extractor import DataExtractor
extractor = DataExtractor(page, logger)
minutes = await extractor.get_timer_minutes("#timer-selector")
balance = await extractor.get_balance(".balance-selector")
```

### 3. Job-Based Scheduling (Not Time-Based)
Jobs enqueue with `next_run` timestamps. The scheduler executes them in priority order and automatically re-enqueues with new `next_run` times. Never use `asyncio.sleep()` for main loop delays.

**Key files**: [core/orchestrator.py](core/orchestrator.py) (JobScheduler class) and [main.py](main.py)

### 4. Browser Context Persistence
Each account profile has a sticky browser context bound by username in `instance.py`. Cookies are encrypted and persisted in `config/cookies_encrypted/`. Proxies are bound to profiles in `config/proxy_bindings.json` to maintain IP consistency.

### 5. Anti-Detection Primitives (Built-in)
Use helper methods from `FaucetBot`:
- `self.human_type(text)` - Types with human-like delays
- `self.idle_mouse()` - Moves mouse naturalistically
- WebRTC leaking prevention is auto-applied

### 6. CAPTCHA Solving Pattern
`CaptchaSolver` auto-detects Turnstile, hCaptcha, reCaptcha v2, and image captchas. After solving, it injects tokens and triggers callbacks. Provider (2Captcha/CapSolver) set in `.env`:

```python
# Captcha solved and injected automatically
success = await self.solver.solve_captcha(page)
```

## Development Workflow

### Testing
```bash
pytest                           # Full suite
pytest -k test_name              # Single test
HEADLESS=true pytest             # Headless mode (production-like)
```

Configuration: [pytest.ini](pytest.ini) uses `asyncio_mode = auto`

### Running Locally
```bash
cp .env.example .env             # Set TWOCAPTCHA_API_KEY, credentials
python main.py --visible         # Show browser during execution
python main.py --single firefaucet  # Test one faucet
```

### Deployment to Azure VM
Use [deploy/deploy.sh](deploy/deploy.sh):
```bash
./deploy/deploy.sh               # Remote trigger (pulls + restarts systemd service)
./deploy/deploy.sh --install-service  # Local installation
```

Service file: [deploy/faucet_worker.service](deploy/faucet_worker.service)

Health check: `python meta.py health` on VM

## Key Files to Know

| File | Purpose |
|------|---------|
| [core/config.py](core/config.py) | `BotSettings` (global config) & `AccountProfile` (per-account) |
| [core/orchestrator.py](core/orchestrator.py) | `JobScheduler` - core concurrency engine |
| [core/extractor.py](core/extractor.py) | `DataExtractor` - standardized timer/balance parsing |
| [browser/instance.py](browser/instance.py) | `BrowserManager` - Camoufox stealth contexts & cookie persistence |
| [faucets/base.py](faucets/base.py) | `FaucetBot` base class with helper methods |
| [solvers/captcha.py](solvers/captcha.py) | `CaptchaSolver` - auto-detection & token injection |
| [core/proxy_manager.py](core/proxy_manager.py) | Residential proxy rotation & health tracking |
| [core/registry.py](core/registry.py) | Faucet factory registry for dynamic instantiation |

## Code Style & Requirements

- **Type hints**: Mandatory for all public functions
- **Logging**: Use `logging` module, never `print()`
- **Paths**: Always use `pathlib.Path` for cross-platform compatibility
- **Async**: All I/O operations must be `async def`
- **Error handling**: Faucet bots must catch and log errors, never raise uncaught exceptions

## Common Tasks

### Adding a New Faucet
1. Create `faucets/newfaucet.py` inheriting from `FaucetBot`
2. Implement `login()`, `claim()`, `get_balance()`, `get_timer()`
3. Register in [core/registry.py](core/registry.py)
4. Add credentials to `.env` (e.g., `NEWFAUCET_USERNAME`, `NEWFAUCET_PASSWORD`)
5. Add test file `tests/test_newfaucet.py` with login/claim scenarios

### Debugging a Faucet
- Check logs in `logs/faucet_bot.log`
- Use `--visible` flag to watch browser: `python main.py --visible --single faucetname`
- Check `earnings_analytics.json` for success rates by faucet
- Use `HEADLESS=false` to debug captcha solving

### Proxy Issues
- Add proxies to `config/proxies.txt` (one per line: `user:pass@ip:port`)
- Set `BotSettings.use_2captcha_proxies = True` in `.env` to auto-fetch from 2Captcha
- Dead proxies are auto-cooldown (5 min), burned proxies (12 hours)
- Monitor "Proxy mismatch" warnings in logs

## Integration Points

- **2Captcha API**: Balance check & proxy fetching (`core/proxy_manager.py`)
- **Azure Monitor** (optional): Enterprise telemetry via `core/azure_monitor.py`
- **Electrum RPC** (optional): Wallet balance queries via `core/wallet_manager.py`

## Troubleshooting Tips

1. **Browser won't launch**: Kill zombie Firefox processes (`taskkill /F /IM firefox.exe`)
2. **Timeouts on slow proxies**: Increase `BotSettings.timeout` (default 180s)
3. **Captcha fails silently**: Check 2Captcha balance and API key in `.env`
4. **Jobs not running**: Verify `config/faucet_state.json` is valid JSON; scheduler persists queue every 5 min
5. **IP detection**: Ensure WebRTC poisoning is enabled (default in `FaucetBot.__init__`)

## References

- [Developer Guide](docs/DEVELOPER_GUIDE.md) - Branching & agent delegation
- [Optimal Workflow](docs/OPTIMAL_WORKFLOW.md) - Full deployment checklist
- [Implementation Notes](IMPLEMENTATION_NOTES.md) - Detailed design decisions by component
- [API Documentation](docs/API.md) - RPC & external service contracts
