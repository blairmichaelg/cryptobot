# Pick.io Faucet Family - Automated Registration Guide

## Overview

This guide covers the automated registration system for all 11 Pick.io cryptocurrency faucet sites. These sites share a common backend infrastructure, allowing a unified registration approach.

## Supported Faucets

| # | Faucet | Cryptocurrency | URL |
|---|--------|---------------|-----|
| 1 | LitePick | LTC (Litecoin) | https://litepick.io |
| 2 | TronPick | TRX (Tron) | https://tronpick.io |
| 3 | DogePick | DOGE (Dogecoin) | https://dogepick.io |
| 4 | SolPick | SOL (Solana) | https://solpick.io |
| 5 | BinPick | BNB (Binance Coin) | https://binpick.io |
| 6 | BchPick | BCH (Bitcoin Cash) | https://bchpick.io |
| 7 | TonPick | TON (The Open Network) | https://tonpick.io |
| 8 | PolygonPick | MATIC (Polygon) | https://polygonpick.io |
| 9 | DashPick | DASH (Dash) | https://dashpick.io |
| 10 | EthPick | ETH (Ethereum) | https://ethpick.io |
| 11 | UsdPick | USDT (Tether) | https://usdpick.io |

## Quick Start

### Prerequisites

```bash
# Install required dependencies
pip install -r requirements.txt

# Ensure Camoufox browser is installed
python -c "from camoufox.async_api import AsyncCamoufox"
```

### Basic Usage

```bash
# Register all 11 faucets with the same email and password
python register_faucets.py --email your@email.com --password yourpassword
```

### Advanced Options

```bash
# Register only specific faucets
python register_faucets.py \
    --email your@email.com \
    --password yourpassword \
    --faucets litepick tronpick ethpick

# Run in visible mode (watch the browser)
python register_faucets.py \
    --email your@email.com \
    --password yourpassword \
    --visible

# Enable debug logging
python register_faucets.py \
    --email your@email.com \
    --password yourpassword \
    --log-level DEBUG
```

## Command-Line Arguments

| Argument | Required | Description | Example |
|----------|----------|-------------|---------|
| `--email` | Yes | Email address for registration | `--email user@example.com` |
| `--password` | Yes | Password for all accounts | `--password MySecurePass123` |
| `--faucets` | No | Specific faucets to register (space-separated) | `--faucets litepick tronpick` |
| `--visible` | No | Run browser in visible mode (not headless) | `--visible` |
| `--log-level` | No | Set logging level (DEBUG, INFO, WARNING, ERROR) | `--log-level DEBUG` |

## Registration Process

### What Happens During Registration

1. **Browser Launch**: Starts Camoufox browser with anti-detection features
2. **For Each Faucet**:
   - Creates isolated browser context
   - Navigates to registration page with retry logic
   - Handles Cloudflare challenges automatically
   - Fills registration form:
     - Email address
     - Password
     - Confirm password
     - Wallet address (if configured)
   - Solves CAPTCHA (hCaptcha or Turnstile)
   - Submits registration
   - Verifies success
   - Saves cookies for future sessions
3. **Summary Report**: Displays success/failure for each faucet

### Success Indicators

The script checks for these indicators to confirm successful registration:

- "successfully registered"
- "registration successful"
- "account created"
- "welcome"
- "check your email"
- "verification email"
- Auto-redirect to dashboard

## Configuration

### Wallet Addresses (Optional)

To include wallet addresses during registration, configure them in your `.env` file or `BotSettings`:

```python
# In core/config.py or .env
WALLET_ADDRESSES = {
    "LTC": "your_litecoin_address",
    "TRX": "your_tron_address",
    "DOGE": "your_dogecoin_address",
    "SOL": "your_solana_address",
    "BNB": "your_binance_address",
    "BCH": "your_bitcoin_cash_address",
    "TON": "your_ton_address",
    "MATIC": "your_polygon_address",
    "DASH": "your_dash_address",
    "ETH": "your_ethereum_address",
    "USDT": "your_tether_address",
}
```

### Proxy Configuration (Optional)

For registration through a proxy:

```python
# In .env or settings
REGISTRATION_PROXY = "http://proxy.example.com:8080"
```

## Example Output

```
============================================================
Starting Pick.io Faucet Registration Process
============================================================
Email: user@example.com
Password: **********
Headless Mode: True

Registering 11 faucet(s)

============================================================
Registering: LitePick
============================================================
[LitePick] Registering at https://litepick.io/register.php
[LitePick] Registration successful for user@example.com

============================================================
Registering: TronPick
============================================================
[TronPick] Registering at https://tronpick.io/register.php
[TronPick] Registration successful for user@example.com

... (continues for all 11 faucets)

============================================================
REGISTRATION SUMMARY
============================================================
Successful: 11/11
   - LitePick
   - TronPick
   - DogePick
   - SolPick
   - BinPick
   - BchPick
   - TonPick
   - PolygonPick
   - DashPick
   - EthPick
   - UsdPick

============================================================
```

## Troubleshooting

### Common Issues

#### 1. Connection Errors

**Symptom**: `ERR_CONNECTION_CLOSED` or `ERR_CONNECTION_RESET`

**Solution**: The script includes automatic retry logic with exponential backoff. If issues persist:
- Check your internet connection
- Try using `--visible` mode to see what's happening
- Consider using a proxy with `REGISTRATION_PROXY` setting

#### 2. CAPTCHA Failures

**Symptom**: Registration fails at CAPTCHA step

**Solution**: 
- Ensure your CAPTCHA solver API key is configured in `.env`
- Check CAPTCHA solver account balance
- Try running in `--visible` mode to manually solve CAPTCHAs

#### 3. Email Already Registered

**Symptom**: Error message about email being already registered

**Solution**: 
- Use a different email address
- Or proceed to login instead of registration

#### 4. Module Import Errors

**Symptom**: `ModuleNotFoundError` for playwright, camoufox, etc.

**Solution**:
```bash
pip install -r requirements.txt
```

### Debug Mode

For detailed troubleshooting information:

```bash
python register_faucets.py \
    --email your@email.com \
    --password yourpassword \
    --log-level DEBUG \
    --visible
```

This will:
- Show detailed logs of each step
- Display the browser window
- Help identify where the process fails

## Architecture

### Component Overview

```
register_faucets.py         # Main registration script
├── PICK_FAUCETS[]         # Registry of all 11 faucets
├── register_single_faucet() # Handles individual faucet registration
└── register_all_faucets()  # Orchestrates batch registration

faucets/pick_base.py       # Base class with shared logic
├── PickFaucetBase
│   ├── register()         # Registration implementation
│   ├── login()            # Login functionality
│   ├── claim()            # Faucet claim logic
│   └── withdraw()         # Withdrawal automation

faucets/pick.py            # Dynamic bot class
└── PickFaucetBot          # Used by registration script

faucets/{coin}pick.py      # Individual faucet classes
├── LitePickBot
├── TronPickBot
└── ... (11 total)
```

### Design Principles

1. **DRY (Don't Repeat Yourself)**: All shared logic in `PickFaucetBase`
2. **Single Responsibility**: Each faucet class only sets name and URL
3. **Robustness**: Retry logic for connection issues, comprehensive error handling
4. **Flexibility**: Support for batch or selective registration
5. **Observability**: Detailed logging and summary reports

## Security Considerations

### Password Security

- Passwords are masked in logs (shown as `***`)
- Never commit passwords or API keys to version control
- Use environment variables or `.env` files for sensitive data

### Session Management

- Each faucet gets an isolated browser context
- Cookies are saved with profile names `register_{FaucetName}`
- Sessions persist for future bot operations (login, claim, withdraw)

### Anti-Bot Measures

The Pick family sites employ:
- TLS fingerprinting
- Cloudflare protection
- hCaptcha/Turnstile challenges
- Connection throttling

Our implementation handles these with:
- Camoufox browser (anti-detection)
- Exponential backoff retry logic
- Automatic CAPTCHA solving
- Cloudflare challenge handling

## Future Enhancements

Potential improvements:

- [ ] Email verification automation
- [ ] Parallel registration (currently sequential)
- [ ] Registration status database
- [ ] Automatic retry for failed registrations
- [ ] Integration with password managers
- [ ] Multi-account support

## Support

For issues or questions:

1. Check the troubleshooting section above
2. Review logs with `--log-level DEBUG`
3. Open an issue on GitHub with:
   - Command used
   - Error messages (sanitize sensitive data)
   - Log output

## License

This registration system is part of the cryptobot project. See main repository for license information.
