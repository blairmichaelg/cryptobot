# 🚜 Gen 3.0 Crypto Faucet Farm

**Professional-Grade Autonomous Harvesting Infrastructure**

This project is a sophisticated, modular automation system designed to harvest high-value crypto faucets (FireFaucet, Cointiply, FreeBitco.in, DutchyCorp, CoinPayU) using advanced stealth technology (`Camoufox`) and automated CAPTCHA solving (`2Captcha`).

---

## ⚡ Key Features (Gen 3.0)

### Core Capabilities

- **🛡️ Advanced Stealth**: Uses **Camoufox** (Firefox fork) with fingerprint randomization to defeat sophisticated anti-bot detection
- **🤖 Auto-Solve Captchas**: Integration with 2Captcha and CapSolver for Turnstile, hCaptcha, reCaptcha, and image-based captchas
- **📊 Standardized Data Extraction**: Unified `get_balance()` and `get_timer()` methods across all faucets using `DataExtractor` utility
- **🔗 Smart Shortlink Traverser**: Generic solver with timer detection, captcha handling, and popup management
- **📺 PTC Support**: Automated ad-watching with active focus management for high-yield faucets
- **⚡ Job-Based Scheduler**: High-concurrency orchestrator eliminates idle time and maximizes crypto extraction

### Architecture

- **`core/`**: Configuration, wallet logic, data extraction, and job orchestration
- **`browser/`**: Stealth context management with Camoufox
- **`faucets/`**: Individual bot modules with standardized base class
- **`solvers/`**: Unified captcha and shortlink solving interfaces
- **`config/`**: Centralized configuration, state, and session management
- **`deploy/`**: Systemd service files (`faucet_worker.service`) and deployment configurations
- **`logs/`**: Rotating logs and heartbeat monitoring

### Advanced Features

- **💰 Golden Tier Targets**: Prioritizes high-yield, direct-deposit or reliable payers
- **🏦 Wallet Daemon**: (Optional) Ready for **Electrum** JSON-RPC integration
- **🎯 Zero Idle Time**: Job-based scheduler runs multiple earning methods simultaneously
- **🔍 Robust Error Handling**: Failure state detection, proxy detection, and automatic retries
- **🩺 Health Monitoring**: New suite of health check utilities for enterprise-grade uptime

---

## 🎯 Supported Targets

| Faucet | Status | Features | Notes |
| :--- | :--- | :--- | :--- |
| **FireFaucet** | ✅ Active | Auto-claims, PTC, Daily Bonus, Shortlinks | Turnstile selection, custom PTC captcha |
| **Cointiply** | ✅ Active | Hourly Roll, PTC Ads | Active focus required for PTC, unique image captcha |
| **FreeBitco.in** | ✅ Active | "Golden Tier" Hourly Roll | Standardized extraction |
| **DutchyCorp** | ⚠️ Limited | Auto-Rolls, Shortlinks, PTC | Proxy detection may block cloud IPs |
| **FaucetCrypto** | ✅ Active | Faucet claims, PTC | Standardized extraction |
| **CoinPayU** | ⚠️ Limited | Multi-coin faucet, Surf Ads | Proxy detection may block cloud IPs |
| **AdBTC** | ⚠️ Limited | Surf Ads, Math captcha | Proxy detection may block cloud IPs |
| **Pick.io Family** | ✅ Active | 11 faucets: LTC, TRX, DOGE, SOL, BNB, BCH, TON, MATIC, DASH, ETH, USDT | Automated registration available |

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

### Proxy Detection Issues

Some faucets (DutchyCorp, CoinPayU, AdBTC) have aggressive proxy detection that blocks cloud/VPS IPs.

**Symptoms**:

- "Proxy Detected" message in logs
- Login fails immediately
- Site shows blocking message

**Solutions**:

- Use residential proxies
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

Check logs in `faucet_bot.log` for detailed error messages.

---

## 📚 Additional Documentation

- **[IMPLEMENTATION_NOTES.md](file:///c:/Users/azureuser/Repositories/cryptobot/IMPLEMENTATION_NOTES.md)**: Detailed findings, selector updates, and technical notes
- **Test Coverage**: See `tests/` directory for automated test suite

---

## ⚠️ Disclaimer

This software is for **educational and research purposes only**. Using automation on websites may violate their Terms of Service. Use responsibly and at your own risk.
