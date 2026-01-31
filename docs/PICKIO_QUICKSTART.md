# Pick.io Family Quick Start Guide

Quick guide for setting up and testing the 11 Pick.io faucets.

---

## Setup (5 minutes)

### 1. Add Credentials to .env

Open your `.env` file and add credentials for each Pick.io faucet you want to use:

```bash
# Example: LitePick
LITEPICK_USERNAME=your_email@example.com
LITEPICK_PASSWORD=your_password

# Example: TronPick
TRONPICK_USERNAME=your_email@example.com
TRONPICK_PASSWORD=your_password
```

**All 11 Pick.io Faucets:**
- `LITEPICK_USERNAME` / `LITEPICK_PASSWORD`
- `TRONPICK_USERNAME` / `TRONPICK_PASSWORD`
- `DOGEPICK_USERNAME` / `DOGEPICK_PASSWORD`
- `BCHPICK_USERNAME` / `BCHPICK_PASSWORD`
- `SOLPICK_USERNAME` / `SOLPICK_PASSWORD`
- `TONPICK_USERNAME` / `TONPICK_PASSWORD`
- `POLYGONPICK_USERNAME` / `POLYGONPICK_PASSWORD`
- `BINPICK_USERNAME` / `BINPICK_PASSWORD`
- `DASHPICK_USERNAME` / `DASHPICK_PASSWORD`
- `ETHPICK_USERNAME` / `ETHPICK_PASSWORD`
- `USDPICK_USERNAME` / `USDPICK_PASSWORD`

### 2. (Optional) Add Wallet Addresses

For withdrawals, add your wallet addresses:

```bash
WALLET_ADDRESSES='{"LTC":"your_ltc_address","TRX":"your_trx_address","DOGE":"your_doge_address","SOL":"your_sol_address","BNB":"your_bnb_address","BCH":"your_bch_address","TON":"your_ton_address","MATIC":"your_matic_address","DASH":"your_dash_address","ETH":"your_eth_address","USDT":"your_usdt_address"}'
```

---

## Testing

### Test All Faucets

```bash
python scripts/test_pickio_login.py
```

### Test Specific Faucet

```bash
python scripts/test_pickio_login.py --faucet litepick
```

### Test with Visible Browser

```bash
python scripts/test_pickio_login.py --faucet tronpick --visible
```

---

## Running Production

### Run All Faucets

```bash
python main.py
```

### Run Single Faucet

```bash
python main.py --single litepick
```

### Run with Visible Browser (Debugging)

```bash
python main.py --single tronpick --visible
```

### Run Once (No Loop)

```bash
python main.py --single dogepick --once
```

---

## Pick.io Faucet List

| Faucet | URL | Coin | ENV Prefix |
|--------|-----|------|------------|
| LitePick | https://litepick.io | Litecoin (LTC) | `LITEPICK_` |
| TronPick | https://tronpick.io | Tron (TRX) | `TRONPICK_` |
| DogePick | https://dogepick.io | Dogecoin (DOGE) | `DOGEPICK_` |
| BchPick | https://bchpick.io | Bitcoin Cash (BCH) | `BCHPICK_` |
| SolPick | https://solpick.io | Solana (SOL) | `SOLPICK_` |
| TonPick | https://tonpick.io | Toncoin (TON) | `TONPICK_` |
| PolygonPick | https://polygonpick.io | Polygon (MATIC) | `POLYGONPICK_` |
| BinPick | https://binpick.io | Binance Coin (BNB) | `BINPICK_` |
| DashPick | https://dashpick.io | Dash (DASH) | `DASHPICK_` |
| EthPick | https://ethpick.io | Ethereum (ETH) | `ETHPICK_` |
| UsdPick | https://usdpick.io | USDT Tether | `USDPICK_` |

---

## Troubleshooting

### "No credentials found"

**Solution**: Add credentials to `.env` file (see Setup section)

### "Login failed"

**Possible causes**:
1. Wrong credentials - verify email/password
2. Account not registered - create account on the site
3. Cloudflare blocking - system will retry automatically
4. Site changed HTML - may need selector updates

**Debug**: Run with `--visible` flag to watch the browser

### "Captcha solve failed"

**Solution**: Verify your 2Captcha or CapSolver API key is set:
```bash
TWOCAPTCHA_API_KEY=your_key_here
# OR
CAPSOLVER_API_KEY=your_key_here
```

### "Connection timeout"

**Solution**: Site may be slow or down. The bot will retry automatically.

---

## Features

All Pick.io faucets include:

✅ **Automatic Login** - Inherited from `PickFaucetBase`  
✅ **Cloudflare Bypass** - Automatic handling with Camoufox  
✅ **Captcha Solving** - Supports hCaptcha, Turnstile, reCAPTCHA  
✅ **Stealth Mode** - Human-like typing and mouse movement  
✅ **Proxy Support** - Automatic proxy rotation  
✅ **Error Handling** - Retry logic for network issues  
✅ **Balance Tracking** - Automatic earnings analytics  
✅ **Timer Management** - Waits for cooldown automatically  

---

## Getting Help

- **Full Documentation**: See `docs/PICKIO_IMPLEMENTATION_STATUS.md`
- **General Guide**: See `docs/DEVELOPER_GUIDE.md`
- **Task Details**: See `AGENT_TASKS.md` (Task 4)

---

## Registration (First Time Only)

If you don't have accounts yet, register on each site:

1. Visit the site (e.g., https://litepick.io)
2. Click "Register" or "Sign Up"
3. Fill in email, password
4. Solve captcha (if present)
5. Verify email (check inbox)
6. Log in manually once to confirm
7. Add credentials to `.env`

**Tip**: Use email aliases to use one email for all sites:
- `yourname+litepick@gmail.com`
- `yourname+tronpick@gmail.com`
- etc.

All emails go to `yourname@gmail.com` but sites see different addresses.
