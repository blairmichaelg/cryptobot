# 🚜 Gen 3.0 Crypto Faucet Farm

**Professional-Grade Autonomous Harvesting Infrastructure**

[![Production Status](https://img.shields.io/badge/Status-OPERATIONAL-brightgreen)](PRODUCTION_STATUS.md)
[![Azure VM](https://img.shields.io/badge/Azure%20VM-RUNNING-blue)](docs/azure/AZURE_VM_STATUS.md)
[![Week 1 Fixes](https://img.shields.io/badge/Week%201%20Fixes-COMPLETE-success)](AGENT_TASKS.md)

This project is a sophisticated, modular automation system designed to harvest high-value crypto faucets using advanced stealth technology (`Camoufox`) and automated CAPTCHA solving (`2Captcha`). **Production deployed and running 24/7 on Azure VM.**

**Latest Update (Feb 1, 2026)**: All Week 1 critical fixes complete! Browser crash prevention, Cloudflare bypass, enhanced selectors, and claim tracking all operational. See [PRODUCTION_STATUS.md](PRODUCTION_STATUS.md) for details.

---

## ⚡ Key Features (Gen 3.0)

### Core Capabilities

- **🛡️ Advanced Stealth**: Uses **Camoufox** (Firefox fork) with fingerprint randomization to defeat sophisticated anti-bot detection
- **🤖 Auto-Solve Captchas**: Integration with 2Captcha and CapSolver for Turnstile, hCaptcha, reCaptcha, and image-based captchas
- **📊 Standardized Data Extraction**: Unified `get_balance()` and `get_timer()` methods across all faucets using `DataExtractor` utility
- **🔗 Smart Shortlink Traverser**: Generic solver with timer detection, captcha handling, and popup management
- **📺 PTC Support**: Automated ad-watching with active focus management for high-yield faucets
- **⚡ Job-Based Scheduler**: High-concurrency orchestrator eliminates idle time and maximizes crypto extraction
- **🩹 Crash Prevention**: Safe browser context management with health checks (Task 2 - Feb 2026)
- **☁️ Cloudflare Bypass**: Progressive retry with automatic Turnstile solving (Task 3 - Jan 2026)

### Architecture

- **`core/`**: Configuration, wallet logic, data extraction, and job orchestration
- **`browser/`**: Stealth context management with Camoufox + crash prevention
- **`faucets/`**: Individual bot modules with standardized base class + safe operations
- **`solvers/`**: Unified captcha and shortlink solving interfaces
- **`config/`**: Centralized configuration, state, and session management
- **`deploy/`**: Systemd service files (`faucet_worker.service`) and deployment configurations
- **`logs/`**: Rotating logs and heartbeat monitoring

### Advanced Features

- **💰 Golden Tier Targets**: Prioritizes high-yield, direct-deposit or reliable payers
- **🏦 Wallet Daemon**: (Optional) Ready for **Electrum** JSON-RPC integration
- **🎯 Zero Idle Time**: Job-based scheduler runs multiple earning methods simultaneously
- **🔍 Robust Error Handling**: Failure state detection, proxy detection, and automatic retries
- **🩺 Health Monitoring**: Enterprise-grade uptime monitoring with alerting
- **📊 Real-Time Monitoring Dashboard**: Track per-faucet health, success rates, and profitability
- **🚀 Azure Deployment**: Production-ready systemd service running 24/7

---

## 🎯 Supported Targets

| Faucet | Status | Features | Notes |
| :--- | :--- | :--- | :--- |
| **FireFaucet** | ✅ Active | Auto-claims, PTC, Daily Bonus, Shortlinks, Cloudflare Bypass | Turnstile selection, custom PTC captcha |
| **Cointiply** | ✅ Enhanced | Hourly Roll, PTC Ads, Safe Operations | Task 7 improvements: enhanced selectors + crash prevention |
| **FreeBitcoin** | ✅ Enhanced | "Golden Tier" Hourly Roll | Task 1 improvements: HTML5 selectors + Cloudflare timeout |
| **DutchyCorp** | ⚠️ Limited | Auto-Rolls, Shortlinks, PTC | Proxy detection may block cloud IPs |
| **FaucetCrypto** | ✅ Active | Faucet claims, PTC | Standardized extraction |
| **CoinPayU** | ⚠️ Limited | Multi-coin faucet, Surf Ads | Proxy detection may block cloud IPs |
| **Pick.io Family** | ✅ Ready | 11 faucets (LTC, TRX, DOGE, SOL, etc.) | Code complete, needs credentials |
| **AdBTC** | ⚠️ Limited | Surf Ads, Math captcha | Proxy detection may block cloud IPs |
| **Pick.io Family** | ⚠️ Partial | TronPick fully working; 10 others need implementation | TronPick is reference implementation |

---

## 🚀 Installation & Setup

### 1. Prerequisites

- Python 3.10+
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
python monitor.py

# Live auto-refreshing dashboard
python monitor.py --live

# Check active alerts only
python monitor.py --alerts-only

# Show 7-day metrics
python monitor.py --period 168
```

See [docs/MONITORING.md](docs/MONITORING.md) for complete monitoring documentation.

### Register New Accounts (Pick.io Family)

Automate registration for all 11 Pick.io faucet sites with a single command:

```bash
# Register all 11 Pick.io faucets with the same credentials
python register_faucets.py --email your@email.com --password yourpassword

# Register specific faucets only
python register_faucets.py --email your@email.com --password yourpassword --faucets litepick tronpick dogepick

# Show browser during registration (for debugging)
python register_faucets.py --email your@email.com --password yourpassword --visible
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

The bot includes a unified management interface (`meta.py`) for common operations:

```bash
# GitHub workflow automation (sync, PR review, issue delegation)
python meta.py workflow                      # Dry run (preview changes)
python meta.py workflow --execute            # Execute workflow
python meta.py workflow --execute --auto-merge  # Full automation

# System health check
python meta.py health

# Profitability dashboard
python meta.py profitability                 # Last 24 hours
python meta.py profitability --hours 168     # Last 7 days

# Repository sync
python meta.py sync --merge --push

# Other utilities
python meta.py clean      # Cleanup temp files
python meta.py audit      # Check project state
python meta.py report     # Earnings report
python meta.py dashboard  # Interactive dashboard
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
python meta.py health
```

---

## 📊 Profitability Analytics Dashboard

The bot includes a comprehensive profitability analytics dashboard accessible via `meta.py`. This dashboard provides real-time insights into earnings, costs, ROI, and performance metrics.

### Usage

```bash
# View profitability dashboard for the last 24 hours (default)
python meta.py profitability

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

The bot supports automatic proxy fetching from 2Captcha residential proxy service.

**Setup**:

1. Purchase residential proxy traffic at [2Captcha Residential Proxies](https://2captcha.com/proxy/residential-proxies)
2. Enable in `.env`:
   ```
   USE_2CAPTCHA_PROXIES=true
   ```
3. The bot will automatically:
   - Fetch proxy configuration from 2Captcha API
   - Generate session-rotated proxies
   - Save them to `config/proxies.txt`
   - Assign proxies to accounts (sticky sessions)

**Manual Configuration** (if API fetch fails):

Add your proxy credentials to `config/proxies.txt`:
```
# Format: username:password@host:port
your-username:your-password@proxy.2captcha.com:8080
```

**How It Works**:

- The bot uses session-based rotation (appends `-session-XXXXX` to username)
- Each account gets a sticky proxy assignment
- Proxies respect cooldown (5 min for failures, 1 hour for detection/403) windows
- Health monitoring tracks latency and failures
- Dead proxies are automatically rotated out

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
