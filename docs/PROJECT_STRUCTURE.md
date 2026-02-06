# Cryptobot Project Structure

This document describes the organization and purpose of each directory and key file in the cryptobot repository.

## Directory Structure

```
cryptobot/
├── browser/               # Browser automation and stealth technology
│   ├── instance.py       # BrowserManager with Camoufox context management
│   └── stealth.py        # Fingerprint randomization and anti-detection
│
├── config/               # Configuration and persistent state
│   ├── accounts.json     # Faucet account credentials (encrypted)
│   ├── faucet_state.json # Job queue and claim scheduling
│   ├── proxy_*.json      # Proxy management and health tracking
│   └── session_state.json # Browser session persistence
│
├── core/                 # Core infrastructure and business logic
│   ├── analytics.py      # Earnings tracking and analytics
│   ├── config.py         # Settings and environment management
│   ├── extractor.py      # Data extraction utilities (DataExtractor)
│   ├── orchestrator.py   # Job scheduler and orchestration
│   ├── proxy_manager.py  # Proxy rotation and health monitoring
│   ├── registry.py       # Faucet registration and discovery
│   └── wallet_manager.py # Wallet operations and Electrum integration
│
├── deploy/               # Deployment scripts and configurations
│   ├── deploy.sh         # Main deployment script
│   ├── azure_deploy.sh   # Azure VM deployment automation
│   └── faucet_worker.service # Systemd service configuration
│
├── docs/                 # Documentation
│   ├── azure/           # Azure deployment documentation
│   ├── fixes/           # Bug fix documentation
│   ├── operations/      # Operational guides
│   ├── quickrefs/       # Quick reference guides
│   ├── summaries/       # Status reports and summaries
│   ├── API.md           # API documentation
│   ├── DEVELOPER_GUIDE.md # Developer onboarding
│   └── OPTIMAL_WORKFLOW.md # Best practices
│
├── faucets/             # Faucet bot implementations
│   ├── base.py          # FaucetBot base class
│   ├── pick_base.py     # Base class for Pick.io family
│   ├── firefaucet.py    # FireFaucet bot
│   ├── cointiply.py     # Cointiply bot
│   ├── freebitcoin.py   # FreeBitcoin bot
│   └── [15+ other faucet implementations]
│
├── fixes/               # Historical fix implementations
│   └── [archived fixes from major debugging sessions]
│
├── logs/                # Application logs (gitignored)
│   ├── faucet_bot.log   # Main application log
│   └── [rotating logs]
│
├── reports/             # Analytics and profitability reports
│   └── [generated reports]
│
├── scripts/             # Utility scripts
│   ├── monitor.py       # Real-time farm monitoring dashboard
│   ├── deploy.sh        # Deployment automation
│   ├── health_check.py  # System health verification
│   ├── proxy_health_check.py # Proxy validation
│   └── dev/             # Development and debugging tools
│       ├── meta.py      # Unified management interface
│       ├── register_faucets.py # Auto-registration for Pick.io family
│       ├── debug_*.py   # Debugging utilities
│       ├── diagnose_*.py # Diagnostic tools
│       └── [other dev utilities]
│
├── solvers/             # CAPTCHA and challenge solvers
│   ├── captcha.py       # Unified CAPTCHA solving (2Captcha, CapSolver)
│   └── shortlink.py     # Shortlink traversal automation
│
└── tests/               # Test suite
    ├── conftest.py      # Pytest configuration
    ├── test_*.py        # Unit and integration tests
    └── [100+ test files]
```

## Key Files in Root

| File | Purpose |
|------|---------|
| `main.py` | Primary entry point for the bot |
| `setup.py` | Package installation configuration |
| `requirements.txt` | Python dependencies |
| `pytest.ini` | Test configuration |
| `.env` | Environment variables and secrets (gitignored) |
| `.env.example` | Template for environment configuration |
| `docker-compose.yml` | Docker deployment configuration |
| `Dockerfile` | Container build instructions |
| `README.md` | Project documentation and usage guide |
| `CHANGELOG.md` | Version history and updates |
| `CONTRIBUTING.md` | Contribution guidelines |
| `LICENSE` | Software license |
| `IMPLEMENTATION_NOTES.md` | Technical implementation details |

## Important Patterns

### Test Organization

All test files are located in the `tests/` directory:
- Unit tests: `test_<module>.py`
- Integration tests: `test_<feature>_integration.py`
- Coverage tests: `test_<module>_coverage.py`
- Verification tests: `test_<feature>_verification.py`

### Script Organization

Production scripts in `scripts/`:
- `monitor.py` - Farm monitoring and alerts
- `health_check.py` - System health verification
- `profitability_monitor.py` - Earnings analytics

Development scripts in `scripts/dev/`:
- `meta.py` - Management interface
- `register_faucets.py` - Account registration
- `debug_*.py` - Debugging utilities
- `diagnose_*.py` - Diagnostic tools

### Documentation Organization

- `docs/azure/` - Azure deployment and VM management
- `docs/fixes/` - Historical bug fixes and solutions
- `docs/operations/` - Operational guides and runbooks
- `docs/quickrefs/` - Quick reference cards
- `docs/summaries/` - Status reports and summaries

## Development Workflow

1. **Local Development**: Edit code on Windows machine
2. **Testing**: SSH to Azure VM (Linux) for browser/faucet tests
3. **Commit**: Use GitRepoHandler agent for version control
4. **Deploy**: Run `deploy/azure_deploy.sh` for production updates

## Production Environment

- **Platform**: Azure VM (DevNode01, West US 2)
- **Service**: `faucet_worker.service` (systemd)
- **Logs**: `~/Repositories/cryptobot/logs/faucet_bot.log`
- **State**: `~/Repositories/cryptobot/config/`

## .gitignore Strategy

The `.gitignore` file is configured to exclude:
- Temporary files (logs, cache, temp directories)
- Sensitive data (credentials, keys, session data)
- Build artifacts (Python cache, dist, build)
- Local state (faucet_state.json, analytics databases)
- Root-level debug/test scripts (but NOT in organized directories)

This ensures the repository stays clean while allowing development tools in their proper locations.
