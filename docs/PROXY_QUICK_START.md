# Quick Start: 2Captcha Proxy Integration

## TL;DR

Automatically fetch and manage 50-100+ residential proxies from 2Captcha.

## 30-Second Setup

1. **Get API Key**: Purchase proxies at https://2captcha.com/proxy/residential-proxies

2. **Configure** (add to `.env`):
```bash
TWOCAPTCHA_API_KEY=your_key_here
USE_2CAPTCHA_PROXIES=true
```

3. **Fetch Proxies**:
```bash
python3 fetch_proxies.py --count 100 --validate
```

Done! Proxies are now in `config/proxies.txt` and ready to use.

## Optional: Enable Auto-Refresh

Add to `.env`:
```bash
PROXY_AUTO_REFRESH_ENABLED=true
```

Then add to crontab (daily at 2 AM):
```bash
0 2 * * * /path/to/cryptobot/scripts/refresh_proxies.py
```

## Usage in Code

```python
from core.config import BotSettings
from core.proxy_manager import ProxyManager

settings = BotSettings()
pm = ProxyManager(settings)

# Fetch proxies
count = await pm.fetch_2captcha_proxies(count=100)
print(f"Added {count} proxies")
```

## Verify Setup

```bash
# Test the integration
python3 test_fetch_2captcha_proxies.py

# Check proxy file
cat config/proxies.txt
```

## Success Criteria

✅ 50+ proxies in config/proxies.txt  
✅ All proxies validated and working  
✅ <3000ms average latency  

## Help

- Full guide: `docs/2CAPTCHA_PROXY_INTEGRATION.md`
- Implementation details: `docs/IMPLEMENTATION_SUMMARY.md`
- Troubleshooting: See README.md proxy section

## Common Issues

**"No proxies fetched"**: You need to purchase residential proxy traffic first  
**"All proxies dead"**: Check your network connection and proxy credentials  
**"High latency"**: Increase `PROXY_MAX_LATENCY_MS` in .env or try different time of day
