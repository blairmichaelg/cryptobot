# 2Captcha Residential Proxy Integration

## Overview

This integration allows automatic fetching and management of residential proxies from 2Captcha's proxy service.

## Features

- **Automatic Proxy Fetching**: Fetch 50-100+ proxies from 2Captcha API
- **Proxy Validation**: Each proxy is validated before being added to the pool
- **Latency Filtering**: Only proxies with <3000ms latency are kept
- **Session Rotation**: Uses 2Captcha's session rotation for better anonymity
- **Auto-Refresh**: Automatically refreshes proxy pool when healthy count is low
- **Health Monitoring**: Tracks latency, failures, and reputation for each proxy

## Setup

### 1. Purchase 2Captcha Residential Proxies

Visit https://2captcha.com/proxy/residential-proxies and purchase traffic.

### 2. Configure Environment

Add to your `.env` file:

```bash
# 2Captcha API Key (required)
TWOCAPTCHA_API_KEY=your_api_key_here

# Enable 2Captcha proxy integration
USE_2CAPTCHA_PROXIES=true
PROXY_PROVIDER=2captcha

# Auto-refresh settings (optional, these are defaults)
PROXY_AUTO_REFRESH_ENABLED=true
PROXY_AUTO_REFRESH_INTERVAL_HOURS=24
PROXY_MIN_HEALTHY_COUNT=50
PROXY_TARGET_COUNT=100
PROXY_MAX_LATENCY_MS=3000
```

### 3. Fetch Proxies

#### Method 1: Using the new API method

```python
from core.config import BotSettings
from core.proxy_manager import ProxyManager

settings = BotSettings()
pm = ProxyManager(settings)

# Fetch 50-100 proxies with validation
count = await pm.fetch_2captcha_proxies(
    count=100,           # Number of proxies to generate
    validate=True,       # Validate before adding to pool
    max_latency_ms=3000  # Maximum acceptable latency
)

print(f"Added {count} valid proxies to pool")
```

#### Method 2: Using the test script

```bash
python3 test_fetch_2captcha_proxies.py
```

#### Method 3: Automatic on startup

The ProxyManager will automatically fetch proxies if:
- `USE_2CAPTCHA_PROXIES=true`
- `config/proxies.txt` is empty
- API key is configured

## Auto-Refresh

The auto-refresh mechanism keeps your proxy pool healthy by:

1. Checking proxy health periodically
2. Fetching new proxies when healthy count < 50
3. Validating and filtering by latency
4. Removing dead/slow proxies

### Manual Refresh

```python
# Refresh proxy pool if needed
success = await pm.auto_refresh_proxies(
    min_healthy_count=50,      # Trigger refresh if below this
    target_count=100,          # Target total proxies
    max_latency_ms=3000,       # Max acceptable latency
    refresh_interval_hours=24  # For logging only
)
```

### Scheduled Refresh

To schedule automatic refresh (e.g., daily at 2 AM), add to your crontab:

```bash
# Edit crontab
crontab -e

# Add this line (adjust path as needed)
0 2 * * * /path/to/cryptobot/scripts/refresh_proxies.py
```

The `refresh_proxies.py` script:
- Checks if auto-refresh is enabled in config
- Checks current proxy pool health
- Refreshes if needed
- Exits cleanly with status code for monitoring

Or integrate into your scheduler:

```python
# In your orchestrator or main loop
async def scheduled_proxy_refresh():
    """Run daily proxy refresh"""
    pm = ProxyManager(settings)
    await pm.auto_refresh_proxies()

# Schedule to run every 24 hours
scheduler.add_job(scheduled_proxy_refresh, interval_hours=24)
```

## How It Works

### 2Captcha Residential Proxy Architecture

2Captcha residential proxies work differently than traditional proxy lists:

1. **Single Gateway**: You get ONE proxy gateway endpoint (host:port)
2. **Session Rotation**: Different IPs are obtained by changing the username parameter
3. **Format**: `http://username-session-XXXX:password@gateway:port`
4. **Anonymity**: Each session ID gets a different residential IP from the pool

### Implementation Details

1. **Base Proxy Fetch**: 
   - Tries to fetch proxy config from 2Captcha API
   - Falls back to config/proxies.txt if API fetch fails
   - API endpoints tried: `/res.php?action=getproxies`, `/proxy/info`

2. **Session Generation**:
   - Takes base proxy credentials
   - Generates unique session IDs (e.g., `user-session-abc123xy`)
   - Creates 50-100 proxy entries, each with different session ID
   - Each session ID maps to a different IP from residential pool

3. **Validation**:
   - Tests each proxy against validation URL (default: google.com)
   - Measures latency for each proxy
   - Filters out dead or slow proxies
   - Keeps only proxies with <3000ms latency (configurable)

4. **Health Monitoring**:
   - Tracks latency history (last 5 measurements)
   - Records failures and implements cooldown
   - Calculates reputation score based on performance
   - Persists health data to `config/proxy_health.json`

5. **Auto-Refresh**:
   - Periodically checks proxy pool health
   - If healthy count < 50, fetches new proxies
   - Validates and adds to pool
   - Removes dead proxies

## File Locations

- **Proxies**: `config/proxies.txt` - List of proxy endpoints
- **Health Data**: `config/proxy_health.json` - Latency, failures, reputation
- **Config**: `.env` - API keys and settings

## Troubleshooting

### "No proxies fetched from API"

This means either:
1. You haven't purchased residential proxy traffic from 2Captcha
2. The API endpoints have changed
3. Your API key is invalid

**Solution**: Manually add your proxy credentials to `config/proxies.txt`:

```
# Format: username:password@proxy-gateway.2captcha.com:port
your-username:your-password@residential.2captcha.com:8080
```

Then run fetch again to generate session-rotated proxies.

### "All proxies have high latency"

This can happen if:
1. Your network connection is slow
2. 2Captcha's proxy pool is congested
3. You're far from proxy locations

**Solution**: 
- Increase `PROXY_MAX_LATENCY_MS` to 5000 or higher
- Try fetching at different times of day
- Contact 2Captcha support about proxy performance

### "LOW PROXY COUNT warnings"

After implementing this integration:
1. Run `python3 test_fetch_2captcha_proxies.py`
2. Check `config/proxies.txt` has entries
3. Verify `USE_2CAPTCHA_PROXIES=true` in `.env`
4. Enable auto-refresh: `PROXY_AUTO_REFRESH_ENABLED=true`

## Success Criteria

✅ 50+ proxies in config/proxies.txt  
✅ All proxies validated and working  
✅ <3000ms average latency  
✅ Auto-refresh functional  
✅ No LOW PROXY COUNT warnings  

## API Reference

### fetch_2captcha_proxies()

```python
async def fetch_2captcha_proxies(
    count: int = 100,
    validate: bool = True,
    max_latency_ms: float = 3000
) -> int
```

Fetch and populate residential proxies from 2Captcha API.

**Parameters:**
- `count` - Number of proxies to generate (default: 100)
- `validate` - Validate proxies before adding (default: True)
- `max_latency_ms` - Maximum acceptable latency in ms (default: 3000)

**Returns:** Number of valid proxies added to pool

### auto_refresh_proxies()

```python
async def auto_refresh_proxies(
    min_healthy_count: int = 50,
    target_count: int = 100,
    max_latency_ms: float = 3000,
    refresh_interval_hours: int = 24
) -> bool
```

Automatically refresh proxy pool when needed.

**Parameters:**
- `min_healthy_count` - Trigger refresh if below this (default: 50)
- `target_count` - Target total proxies (default: 100)
- `max_latency_ms` - Maximum acceptable latency (default: 3000)
- `refresh_interval_hours` - For logging only (default: 24)

**Returns:** True if refresh successful or not needed, False if failed

### get_refresh_schedule_info()

```python
def get_refresh_schedule_info() -> Dict[str, Any]
```

Get information about the auto-refresh schedule.

**Returns:** Dictionary with schedule information

## Example Output

```
[2CAPTCHA] Fetching 100 residential proxies from 2Captcha API...
[2CAPTCHA] ✓ Got base proxy: residential.2captcha.com:8080
[2CAPTCHA] Generating 100 session-rotated proxies...
[2CAPTCHA] ✓ Generated 101 proxies
[2CAPTCHA] Validating proxies (this may take a moment)...
[2CAPTCHA] ✓ Validation complete: 98/101 proxies are healthy
[2CAPTCHA] ✓ Filtered to 95 proxies with <3000ms latency
[2CAPTCHA] ═══ Proxy Pool Summary ═══
[2CAPTCHA]   Total proxies: 98
[2CAPTCHA]   Healthy: 95
[2CAPTCHA]   Dead: 3
[2CAPTCHA]   Avg latency: 1767ms
[2CAPTCHA]   File: /path/to/config/proxies.txt
[2CAPTCHA] ═══════════════════════════
```

## Related Issues

- Closes #70 - Fetch and populate residential proxies from 2Captcha API
