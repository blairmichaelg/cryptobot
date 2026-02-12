# 🤖 Cryptobot Gen 3.0 - Multi-Purpose Browser Automation Platform

**Professional-Grade Infrastructure for Web Automation & Monetization**

[![Infrastructure](https://img.shields.io/badge/Infrastructure-OPERATIONAL-brightgreen)](docs/DEPLOYMENT_INSTRUCTIONS.md)
[![Azure VMs](https://img.shields.io/badge/Azure%20VMs-9%20ACTIVE-blue)](docs/DEPLOY_AZURE_PROXIES_QUICK.md)
[![Clean Codebase](https://img.shields.io/badge/Codebase-CLEANED-success)](#)

A sophisticated, production-ready automation platform featuring:
- **8 Azure proxy VMs** across global regions
- **Stealth browser automation** (Camoufox + anti-detection)
- **Multi-account orchestration** (12 profiles with session persistence)
- **Enterprise captcha solving** (2Captcha + CapSolver)
- **Analytics & monitoring** (detailed logging, performance tracking)

**Latest Update (Feb 11, 2026)**: Infrastructure optimized. Cleaned codebase. Researching profitable monetization strategies. See [QUICK_START_GUIDE.md](QUICK_START_GUIDE.md) for next steps.

> **Note**: Originally built for crypto faucets (unprofitable in 2026). Infrastructure is solid and being redirected to actually profitable opportunities. See [docs/PROFITABLE_OPPORTUNITIES.md](docs/PROFITABLE_OPPORTUNITIES.md) for research.

---

## 🎯 What's Next

This infrastructure is **production-ready** and looking for profitable applications:

1. **📋 [QUICK_START_GUIDE.md](QUICK_START_GUIDE.md)** - 3 immediate monetization paths
2. **📚 [docs/PROFITABLE_OPPORTUNITIES.md](docs/PROFITABLE_OPPORTUNITIES.md)** - 6 tiers of researched strategies
3. **🔬 [RESEARCH_PROMPT.md](RESEARCH_PROMPT.md)** - Copy this to Gemini/Perplexity for current 2026 research

**Best opportunities being evaluated**:
- Crypto airdrop farming ($2,400-12,000 potential per campaign)
- Web scraping services ($300-1,500/month recurring)
- Passive income on VMs ($120/month guaranteed)

---

## ⚡ Key Features

### Infrastructure

- **8 Azure B1s VMs** - Global proxy network (West US, East US, Europe, Asia)
- **Main production VM** - DevNode01 (West US 2) running systemd service
- **Rotating proxies** - Automatic rotation with cooldown/burn windows
- **Monthly cost**: ~$55 (Azure credits available)

### Automation Capabilities

- **🛡️ Advanced Stealth**: Camoufox (Firefox fork) with fingerprint randomization, WebRTC hardening, human-like behavior
- **🤖 Captcha Solving**: 2Captcha and CapSolver integration (Turnstile, hCaptcha, reCaptcha, image captchas)
- **👥 Multi-Account**: 12 profiles with unique fingerprints, encrypted session cookies, proxy binding
- **⚡ Job Scheduler**: High-concurrency orchestrator with retry logic, error handling, state persistence
- **🩹 Crash Prevention**: Safe browser context management with health checks and recovery
- **☁️ Cloudflare Bypass**: Progressive retry with automatic Turnstile solving

### Architecture

- **`core/`**: Configuration, wallet logic, data extraction, and job orchestration
- **`browser/`**: Stealth context management with Camoufox + crash prevention
- **`faucets/`**: Individual bot modules with standardized base class + safe operations
- **`solvers/`**: Unified captcha and shortlink solving interfaces
- **`config/`**: Centralized configuration, state, and session management
- **`deploy/`**: Systemd service files (`faucet_worker.service`) and deployment configurations
- **`logs/`**: Rotating logs and heartbeat monitoring
- **`tests/`**: Comprehensive test suite for all modules
- **`scripts/`**: Utility scripts for monitoring, deployment, and administration
- **`scripts/dev/`**: Development and debugging utilities
- **`docs/`**: Complete documentation including guides, API docs, and summaries

### Tech Stack

- **Language**: Python 3.11+ with asyncio
- **Browser**: Playwright + Camoufox (stealth Firefox)
- **Data**: Pydantic v2 models, JSON persistence
- **Deployment**: systemd service on Ubuntu (Azure VM)
- **Proxies**: tinyproxy on 8 Azure B1s VMs
- **Version Control**: Git + GitHub (single master branch)

### Codebase Structure

- **`core/`** - Orchestration, scheduling, configuration, data extraction, analytics
- **`browser/`** - Stealth browser management, session persistence, fingerprinting
- **`faucets/`** - Bot modules (18 implemented, currently disabled - see note)
- **`tasks/`** - New automation tasks (airdrop farming, etc.)
- **`solvers/`** - Captcha solving, shortlink traversal
- **`scripts/`** - Diagnostic tools, deployment scripts, analysis
- **`deploy/`** - Systemd service, Azure deployment automation
- **`config/`** - Configuration, session state, encrypted cookies
- **`docs/`** - Comprehensive documentation, guides, research

> **Current Status**: Faucet bots are implemented but disabled (unprofitable). Infrastructure is being redirected to airdrop farming, web scraping services, and passive income opportunities.

---

## 🚀 Quick Start

### For Development

```bash
# Clone repo
git clone https://github.com/blairmichaelg/cryptobot.git
cd cryptobot

# Setup environment
python3 -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -r requirements.txt

# Configure
cp .env.example .env
# Edit .env with your credentials

# Run tests
pytest

# Run single automation (example)
python main.py --single firefaucet --once
```

### For Production (Azure VM)

```bash
# Deploy to existing Azure VM
./deploy/azure_deploy.sh --resource-group APPSERVRG --vm-name DevNode01

# Or setup new infrastructure
./scripts/setup_azure_infrastructure.sh  # Creates 8 proxy VMs
```

See [DEPLOYMENT_INSTRUCTIONS.md](DEPLOYMENT_INSTRUCTIONS.md) for full setup guide.

---

## 📚 Documentation

- **[QUICK_START_GUIDE.md](QUICK_START_GUIDE.md)** - Pick a monetization path and start TODAY
- **[docs/PROFITABLE_OPPORTUNITIES.md](docs/PROFITABLE_OPPORTUNITIES.md)** - 6 tiers of researched opportunities
- **[RESEARCH_PROMPT.md](RESEARCH_PROMPT.md)** - Prompt for Gemini/Perplexity to research current opportunities
- **[docs/DEVELOPER_GUIDE.md](docs/DEVELOPER_GUIDE.md)** - Architecture and development workflow
- **[IMPLEMENTATION_NOTES.md](IMPLEMENTATION_NOTES.md)** - Site-specific implementation details
- **[docs/DEPLOY_AZURE_PROXIES_QUICK.md](docs/DEPLOY_AZURE_PROXIES_QUICK.md)** - Azure proxy setup

### Key Files

- **Configuration**: `.env`, `config/profiles.json`, `config/proxies.txt`
- **Analytics**: `earnings_analytics.json`, `logs/faucet_bot.log`
- **State**: `config/faucet_state.json`, `config/session_state.json`

---

## 💰 Current Monetization Research

**Status**: Pivoting from unprofitable faucets to high-value automation

**Top 3 Opportunities Being Evaluated** (Feb 2026):

1. **Crypto Airdrop Farming** - $2,400-12,000 per campaign
   - LayerZero, zkSync, Scroll, Linea
   - Perfect fit: multi-account + proxies + automation
   - [Implementation template](tasks/airdrop_farmer_template.py) ready

2. **Web Scraping Services** - $300-1,500/month recurring
   - Unique selling point: 8 geographic proxy locations
   - Fiverr/Upwork gigs for e-commerce, leads, price monitoring
   - Existing infrastructure handles anti-scraping measures

3. **Passive Income** - $120/month guaranteed
   - Earnapp, Peer2Profit on 8 VMs
   - Zero effort after 2-hour setup
   - First payments in 4-6 weeks

See [QUICK_START_GUIDE.md](QUICK_START_GUIDE.md) to pick a path and start.

---

## 🔧 Customizing for New Automation Tasks

The infrastructure is designed to be repurposed:

```python
# tasks/your_automation.py
from faucets.base import FaucetBot, ClaimResult

class YourBot(FaucetBot):
    async def login(self):
        await self.page.goto("https://example.com/login")
        await self.page.fill("input[name='email']", self.email)
        await self.page.fill("input[name='password']", self.password)
        await self.page.click("button[type='submit']")
        
    async def claim(self):
        # Your automation logic
        # Uses: self.page (Playwright), self.solver (captchas), anti-detection
        result = await self.perform_your_actions()
        return ClaimResult(success=True, amount=result.amount)
```

**You get for free**:
- Stealth browser with fingerprint randomization
- Automatic proxy rotation
- Captcha solving (2Captcha/CapSolver)
- Session persistence (encrypted cookies)
- Error handling and retries
- Analytics and logging

Just implement `login()` and `claim()` - the framework handles everything else.

---

## 📊 Current Status

**Infrastructure**: ✅ Fully operational (9 Azure VMS)  
**Codebase**: ✅ Cleaned and documented  
**Original Purpose** (faucets): ❌ Unprofitable ($0.264 spent, $0.00 earned)  
**New Direction**: 🔄 Researching profitable applications  
**Best Leads**: Airdrops ($2.4k-12k), Scraping ($300-1500/mo), Passive ($120/mo)

**Next Step**: Pick ONE opportunity from [QUICK_START_GUIDE.md](QUICK_START_GUIDE.md) and implement it this week.

---

## 🤝 Contributing

This is currently a personal project, but if you're interested in collaborating or have ideas for profitable uses of this infrastructure:

1. Check [RESEARCH_PROMPT.md](RESEARCH_PROMPT.md) for what we're researching
2. See [docs/PROFITABLE_OPPORTUNITIES.md](docs/PROFITABLE_OPPORTUNITIES.md) for current ideas
3. Open an issue or discussion with your suggestions

---

## 📝 License

MIT License - See [LICENSE](LICENSE) for details.

**Note**: This software is for educational and research purposes. Users are responsible for complying with the terms of service of any websites they interact with and all applicable laws.

---

## 🔗 Links

- **GitHub**: [blairmichaelg/cryptobot](https://github.com/blairmichaelg/cryptobot)
- **Deployment**: Azure VM (DevNode01, West US 2) + 8 proxy VMs
- **Status**: Infrastructure operational, seeking profitable use cases

---

**Built with 💻 by an automation enthusiast. Infrastructure is solid - just needs the right target market. Got ideas? Let's talk.**
- A **2Captcha** API Key (Required for automation)
- `pytest` (for running tests)

### 2. Clone & Install

```bash
git clone https://github.com/your-repo/crypto-bot-gen3.git
cd crypto-bot-gen3

# One-step setup (installs dependencies, venv, and logs)
./deploy/deploy.sh
```

### 3. Running Tests

Run the full test suite with:

```bash
pytest
```

or run specific tests:

```bash
pytest tests/test_captcha_verification.py
```

### 4. Configuration (.env)

Create a `.env` file in the root directory. Copy the structure from `.env.example`:

```ini
# --- Core Credentials ---
TWOCAPTCHA_API_KEY=your_2captcha_key_here

# --- Faucet Credentials ---
FIREFAUCET_USERNAME=email@example.com
FIREFAUCET_PASSWORD=secret

COINTIPLY_USERNAME=email@example.com
COINTIPLY_PASSWORD=secret

FAUCETCRYPTO_USERNAME=email@example.com
FAUCETCRYPTO_PASSWORD=secret

FREEBITCOIN_USERNAME=email@example.com
FREEBITCOIN_PASSWORD=secret

DUTCHY_USERNAME=email@example.com
DUTCHY_PASSWORD=secret

# --- Optional: Wallet Daemon ---
ELECTRUM_RPC_URL=http://127.0.0.1:7777
# ELECTRUM_RPC_USER=user
# ELECTRUM_RPC_PASS=pass
```

---

## 🕹️ Usage

### Run the Farm (Continuous Mode)

This is the standard operating mode. It will cycle through all enabled faucets, sleep for ~1 hour (plus random jitter), and repeat forever.

```bash
python main.py
```

### Run with Visible Browser (Debugging)

See what the bot is doing:

```bash
python main.py --visible
```

### Run a Single Faucet

Test a specific module (e.g., just FireFaucet):

```bash
python main.py --single firefaucet --visible
```

### Run Once & Exit

Do one round of claims and stop:

```bash
python main.py --once
```

### Monitor Farm Health

View real-time dashboard with faucet health metrics:

```bash
# Show 24-hour metrics
python scripts/monitor.py

# Live auto-refreshing dashboard
python scripts/monitor.py --live

# Check active alerts only
python scripts/monitor.py --alerts-only

# Show 7-day metrics
python scripts/monitor.py --period 168
```

See [docs/MONITORING.md](docs/MONITORING.md) for complete monitoring documentation.

### Register New Accounts (Pick.io Family)

Automate registration for all 11 Pick.io faucet sites with a single command:

```bash
# Register all 11 Pick.io faucets with the same credentials
python scripts/dev/register_faucets.py --email your@email.com --password yourpassword

# Register specific faucets only
python scripts/dev/register_faucets.py --email your@email.com --password yourpassword --faucets litepick tronpick dogepick

# Show browser during registration (for debugging)
python scripts/dev/register_faucets.py --email your@email.com --password yourpassword --visible
```

**Supported Pick.io Faucets:**

- LitePick.io (LTC)
- TronPick.io (TRX)
- DogePick.io (DOGE)
- SolPick.io (SOL)
- BinPick.io (BNB)
- BchPick.io (BCH)
- TonPick.io (TON)
- PolygonPick.io (MATIC)
- DashPick.io (DASH)
- EthPick.io (ETH)
- UsdPick.io (USDT)

The script will:

1. Navigate to each registration page
2. Fill in email, password, and wallet address (if configured)
3. Solve any CAPTCHAs automatically
4. Verify successful registration
5. Provide a summary report

**Note:** Configure wallet addresses in your `.env` file to automatically populate wallet fields during registration:

```ini
WALLET_ADDRESSES='{"LTC": "your_ltc_address", "TRX": "your_trx_address", "DOGE": "your_doge_address"}'
```

### Check Wallet Connection

Verify if your local Electrum daemon is reachable:

```bash
python main.py --wallet-check
```

### Meta Management Commands

The bot includes a unified management interface (`scripts/dev/meta.py`) for common operations:

```bash
# GitHub workflow automation (sync, PR review, issue delegation)
python scripts/dev/meta.py workflow                      # Dry run (preview changes)
python scripts/dev/meta.py workflow --execute            # Execute workflow
python scripts/dev/meta.py workflow --execute --auto-merge  # Full automation

# System health check
python scripts/dev/meta.py health

# Profitability dashboard
python scripts/dev/meta.py profitability                 # Last 24 hours
python scripts/dev/meta.py profitability --hours 168     # Last 7 days

# Repository sync
python scripts/dev/meta.py sync --merge --push

# Other utilities
python scripts/dev/meta.py clean      # Cleanup temp files
python scripts/dev/meta.py audit      # Check project state
python scripts/dev/meta.py report     # Earnings report
python scripts/dev/meta.py dashboard  # Interactive dashboard
```

See [docs/GITHUB_WORKFLOW.md](docs/GITHUB_WORKFLOW.md) for complete workflow documentation.

---

### 5. Deployment (Azure VM / Linux)

For production deployment on an Azure VM or Linux server, use the unified deployment script with the service installation flag.

```bash
# Installs systemd service, logrotate, and starts the bot
./deploy/deploy.sh --install-service
```

This will:

1. Update dependencies
2. Install/Update `faucet_worker.service`
3. Configure `logrotate`
4. Start the service
5. Tail the logs to confirm startup

**Check Service Status:**

```bash
python scripts/dev/meta.py health
```

---

## 📊 Profitability Analytics Dashboard

The bot includes a comprehensive profitability analytics dashboard accessible via `meta.py`. This dashboard provides real-time insights into earnings, costs, ROI, and performance metrics.

### Usage

```bash
# View profitability dashboard for the last 24 hours (default)
python scripts/dev/meta.py profitability

# View profitability for the last 12 hours
python meta.py profitability --hours 12

# View profitability for the last 7 days
python meta.py profitability --hours 168
```

### Dashboard Features

The profitability dashboard displays:

1. **Summary Metrics**
   - Total earnings in USD (with real-time cryptocurrency price conversion)
   - Total costs (captcha solving, proxies, etc.)
   - Net profit and ROI percentage
   - Total claims and success rate

2. **Per-Faucet Performance**
   - Claims breakdown (successful/total)
   - Success rate percentage with color coding
   - Earnings and costs per faucet
   - Net profit and hourly earning rate

3. **Monthly Projections**
   - Projected daily and monthly income based on current performance
   - Performance alerts for low success rates or negative ROI
   - System health indicators

4. **Cost Breakdown**
   - Detailed breakdown of costs by faucet and type
   - Average cost per service
   - Total cost tracking

5. **Withdrawal Performance**
   - Recent withdrawal transactions
   - Network and platform fees
   - Net amounts received
   - Transaction status tracking

### Data Sources

The dashboard aggregates data from:
- `earnings_analytics.json` - Claim records and operational costs (auto-created, gitignored)
- `withdrawal_analytics.db` - Withdrawal transaction history (auto-created, gitignored)
- Real-time cryptocurrency prices via CoinGecko API

**Note**: Both analytics files are gitignored and auto-created with clean schemas on first run. For production deployment, the bot starts with empty analytics and builds data from actual claims. Test faucets (names starting with `test_`) are automatically filtered from analytics. See [docs/EARNINGS_ANALYTICS.md](docs/EARNINGS_ANALYTICS.md) for details.

### Example Output

```
================================================================================
                    CRYPTOBOT PROFITABILITY DASHBOARD                          
         Analysis Period: Last 24 hours | Generated: 2026-01-22 01:34:49       
================================================================================

╭────────────────────────────── Summary Metrics (Last 24h) ──────────────────╮
│ Total Earnings:  $2.45 USD                                                 │
│ Total Costs:     $0.58 USD                                                 │
│ Net Profit:      $1.87 USD                                                 │
│ ROI:             +322.41%                                                  │
│ Total Claims:    195 (157 successful)                                      │
╰────────────────────────────────────────────────────────────────────────────╯

                    Per-Faucet Performance (Last 24h)                         
╭──────────────┬────────┬───────────┬──────────────┬────────────┬──────────╮
│ Faucet       │ Claims │ Success % │ Earnings USD │ Net Profit │ Hourly   │
├──────────────┼────────┼───────────┼──────────────┼────────────┼──────────┤
│ freebitcoin  │  32/41 │     78.0% │      $0.92   │    $0.80   │ $0.03/hr │
│ firefaucet   │  38/42 │     90.5% │      $0.78   │    $0.66   │ $0.03/hr │
│ cointiply    │  41/45 │     91.1% │      $0.52   │    $0.39   │ $0.02/hr │
│ faucetcrypto │  28/38 │     73.7% │      $0.23   │    $0.12   │ $0.01/hr │
╰──────────────┴────────┴───────────┴──────────────┴────────────┴──────────╯
```

## 🧠 Architecture Overview

### The Loop (`main.py`)

The entry point. It handles the lifecycle, ensuring the browser is completely restarted between cycles to clear memory and cookies (mimicking a fresh session).

### Stealth Browser (`browser/instance.py`)

Wraps `AsyncCamoufox`. It automatically handles:

- User-Agent rotation
- Canvas noise injection (via Camoufox)
- GeoIP matching (if configured)
- Viewport randomization

### Solvers

#### Captcha Solver (`solvers/captcha.py`)

A unified interface that detects and solves multiple captcha types:

- **Turnstile** (Cloudflare)
- **hCaptcha**
- **reCaptcha v2**
- **Image-based captchas** (with detailed logging for debugging)

Supports both 2Captcha and CapSolver providers. Automatically extracts sitekeys, polls for solutions, injects tokens, and triggers callbacks.

#### Shortlink Solver (`solvers/shortlink.py`)

Generic solver for crypto shortlinks that:

- Detects and waits for countdown timers using `DataExtractor`
- Solves captchas during traversal
- Clicks through multiple steps ("Get Link", "Continue", "Next")
- Handles popup windows and redirects
- Uses heuristics to avoid clicking ad elements

### Data Extraction (`core/extractor.py`)

Standardized utility for parsing timers and balances:

- **Timer formats**: HH:MM:SS, MM:SS, "Xh Ym", "X days", "X hours", "X minutes"
- **Balance extraction**: Removes commas, extracts numeric values
- **Logging**: Debug-level logging for troubleshooting

---

## 🔧 Troubleshooting

### Residential Proxy Configuration

The bot supports **automatic proxy fetching** from 2Captcha residential proxy service with validation, latency filtering, and auto-refresh.

**Quick Setup (Automatic)**:

1. Purchase residential proxy traffic at [2Captcha Residential Proxies](https://2captcha.com/proxy/residential-proxies)
2. Enable in `.env`:
   ```bash
   USE_2CAPTCHA_PROXIES=true
   PROXY_AUTO_REFRESH_ENABLED=true  # Optional: enable auto-refresh
   ```
3. Run the fetch script:
   ```bash
   python3 fetch_proxies.py --count 100 --validate
   ```

The bot will automatically:
- Fetch proxy configuration from 2Captcha API
- Generate 50-100+ session-rotated proxies
- Validate each proxy before adding to pool
- Filter by latency (<3000ms by default)
- Save to `config/proxies.txt`
- Auto-refresh daily when healthy count is low

**Manual Configuration** (if API fetch fails):

Add your proxy credentials to `config/proxies.txt`:
```
# Format: username:password@host:port
your-username:your-password@proxy.2captcha.com:8080
```

**How It Works**:

- 2Captcha provides ONE gateway endpoint with session rotation
- Each unique session ID (e.g., `user-session-abc123`) gets a different residential IP
- The bot generates 100+ unique sessions for maximum anonymity
- Each account gets a sticky proxy assignment for consistent fingerprinting
- Auto-refresh keeps the pool healthy (replaces dead/slow proxies)
- Proxies respect cooldown (5 min for failures, 1 hour for detection/403) windows
- Health monitoring tracks latency and failures
- Dead proxies are automatically rotated out

**Advanced Configuration**:

Add to `.env` to customize:
```bash
PROXY_MIN_HEALTHY_COUNT=50      # Minimum before auto-refresh
PROXY_TARGET_COUNT=100          # Target proxy pool size
PROXY_MAX_LATENCY_MS=3000       # Maximum acceptable latency
PROXY_AUTO_REFRESH_INTERVAL_HOURS=24  # How often to check
```

See [docs/2CAPTCHA_PROXY_INTEGRATION.md](docs/2CAPTCHA_PROXY_INTEGRATION.md) for complete documentation.

### Proxy Detection Issues

Some faucets (DutchyCorp, CoinPayU, AdBTC) have aggressive proxy detection that blocks cloud/VPS IPs.

**Symptoms**:

- "Proxy Detected" message in logs
- Login fails immediately
- Site shows blocking message

**Solutions**:

- Use residential proxies (see above)
- Run from home internet connection
- Disable affected faucets in configuration

### Captcha Solving Failures

**Symptoms**:

- "Manual solve timed out" messages
- Captcha not being detected
- Token injection not working

**Solutions**:

- Verify 2Captcha/CapSolver API key is valid and has credits
- Check logs for sitekey extraction errors
- Enable `--visible` mode to manually solve and observe behavior
- For image captchas, manual solving is currently required

### Timer/Balance Extraction Issues

**Symptoms**:

- "Failed to parse timer text" warnings
- Balance shows as "0"
- Incorrect wait times

**Solutions**:

- Enable debug logging: `export LOG_LEVEL=DEBUG`
- Check `IMPLEMENTATION_NOTES.md` for site-specific selectors
- Verify site hasn't changed its layout
- Report new timer formats for enhancement

### PTC Ads Not Working

**Symptoms**:

- Ads not being detected
- Timer not counting down
- "Continue" button not appearing

**Solutions**:

- Ensure browser is in visible mode for sites requiring active focus (Cointiply)
- Check for anti-adblocker messages
- Verify ad availability (some sites have limited ads)

### General Debugging

Enable visible mode and verbose logging:

```bash
python main.py --visible --single <faucet_name>
```

Check logs in `logs/faucet_bot.log` for detailed error messages.

---

## 📚 Additional Documentation

- **[IMPLEMENTATION_NOTES.md](file:///c:/Users/azureuser/Repositories/cryptobot/IMPLEMENTATION_NOTES.md)**: Detailed findings, selector updates, and technical notes
- **Test Coverage**: See `tests/` directory for automated test suite

---

## 🤝 Contributing

We welcome contributions! Please see [CONTRIBUTING.md](CONTRIBUTING.md) for details on how to get started, run tests, and submit pull requests.

## 📜 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## ⚠️ Disclaimer

This software is for **educational and research purposes only**. Using automation on websites may violate their Terms of Service. Use responsibly and at your own risk.
