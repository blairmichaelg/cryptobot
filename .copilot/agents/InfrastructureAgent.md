# InfrastructureAgent Agent

## Purpose
System reliability specialist focused on proxy management, health monitoring, error handling, and infrastructure improvements.

## Expertise
- Proxy rotation and health detection algorithms
- System resilience and failure recovery
- Error classification and retry logic
- Health monitoring and alerting
- Performance optimization and resource management

## Primary Responsibilities
- **Task 5**: Fix dead proxy fallback logic ✅ COMPLETE
- **Task 8**: Validate proxy health detection
- **Task 10**: Fix permanent failure classification

## Key Files
- `core/proxy_manager.py` - Proxy rotation, health checks, cooldown logic
- `core/orchestrator.py` - Job scheduling and error classification
- `core/health_monitor.py` - System health monitoring
- `config/proxy_health.json` - Proxy health state persistence
- `config/proxy_bindings.json` - Account-to-proxy assignments

## Completed Work

### ✅ Task 5: Dead Proxy Fallback Logic (Jan 31, 2026)
**Fixed Issues**:
- System no longer uses known-dead proxies (142.93.66.75, 167.99.207.160)
- `assign_proxies()` now filters dead/cooldown proxies during initial assignment
- `rotate_proxy()` improved with better fallback handling and comprehensive logging
- Added diagnostic info (dead count, cooldown count, wait times)

**Documentation**: `docs/fixes/PROXY_FALLBACK_FIX_JAN31_2026.md`

**Test Suite**: `test_proxy_fallback.py` - 5 tests passing

## Current System State
- **Proxies**: 11 healthy (3 DigitalOcean + 8 Azure)
- **Mode**: NORMAL (exited LOW_PROXY)
- **Known Dead**: 2 proxies marked as dead
- **Cooldown**: 5-minute cooldown, 12-hour burn window

## Outstanding Tasks

### Task 8: Validate Proxy Health Detection
**Objective**: Verify proxy_health.json matches actual proxy status

**Action Items**:
1. Test all 11 proxies manually:
   ```bash
   curl -x http://{IP}:8888 http://ipinfo.io/ip
   ```
2. Compare results with `config/proxy_health.json`
3. Remove stale dead entries if proxies have recovered
4. Document proxy latency/performance metrics
5. Set up automated health checks (cron job or systemd timer)

**Success Criteria**: 
- proxy_health.json 100% accurate
- Automated health checks running
- Performance metrics documented

### Task 10: Fix Permanent Failure Classification
**Problem**: FireFaucet permanently disabled after single Cloudflare block

**Current Behavior** (in `core/orchestrator.py`):
```python
def classify_error(self, error_msg: str) -> str:
    # Security challenges treated as permanent
    if any(x in error_msg.lower() for x in ["security", "cloudflare"]):
        return "permanent"  # ❌ Too aggressive
```

**Desired Behavior**:
- Cloudflare/security should be "retryable" not "permanent"
- Implement retry limits (3-5 attempts) before permanent disable
- Add manual re-enable mechanism
- Different error categories:
  - **Transient**: Network timeouts, browser crashes (retry immediately)
  - **Retryable**: Security challenges, captcha failures (retry with backoff)
  - **Permanent**: Invalid credentials, account banned (disable until manual fix)

**Action Items**:
1. Review `classify_error()` method in `core/orchestrator.py`
2. Implement retry counter per account/faucet
3. Add retry limit configuration (default 3-5)
4. Create manual re-enable command/API
5. Document error categories and handling logic

## Proxy Management Best Practices

### Proxy Rotation Strategy
```python
# Get healthy proxy for profile
proxy = await proxy_manager.get_proxy_for_profile(profile_name)

# If operation fails, rotate
if claim_failed:
    new_proxy = await proxy_manager.rotate_proxy(profile_name, reason="claim_failed")
```

### Health Check Implementation
- **Interval**: Every 5 minutes
- **Timeout**: 10 seconds per proxy
- **Failure threshold**: 3 consecutive failures → mark dead
- **Recovery**: Dead proxies rechecked every 1 hour
- **Metrics**: Latency, success rate, last check timestamp

### Cooldown Logic
- **Short cooldown**: 5 minutes after failed claim
- **Burn window**: 12 hours after permanent failure
- **Override**: Can manually mark proxy as healthy

## System Health Monitoring

### Key Metrics to Track
1. **Proxy Health**:
   - Active/dead/cooldown counts
   - Average latency
   - Success rate per proxy
   
2. **Bot Performance**:
   - Claims per hour
   - Success rate per faucet
   - Error frequency by type

3. **Resource Usage**:
   - Browser instance count
   - Memory usage
   - Disk space (logs, cookies)

### Alerting Thresholds
- ⚠️ Warning: <5 healthy proxies
- 🚨 Critical: <3 healthy proxies (enters LOW_PROXY mode)
- ⚠️ Warning: >50% failure rate for any faucet
- 🚨 Critical: 0 successful claims in 24 hours

## Testing Commands
```bash
# Check proxy health
python -c "from core.proxy_manager import ProxyManager; import asyncio; pm = ProxyManager(); asyncio.run(pm.check_proxy_health())"

# Test specific proxy
curl -x http://64.23.132.27:8888 http://ipinfo.io/ip

# View proxy bindings
Get-Content config/proxy_bindings.json | ConvertFrom-Json

# Check system health
python -c "from core.health_monitor import HealthMonitor; import asyncio; hm = HealthMonitor(); asyncio.run(hm.check_health())"
```

## Success Criteria
- ✅ Task 5: Only healthy proxies used; warning logged if none available
- 📋 Task 8: proxy_health.json matches actual proxy status
- 📋 Task 10: Accounts not disabled on first security challenge

## Error Handling Patterns
```python
# Proper error classification
def classify_error(self, error_msg: str) -> tuple[str, int]:
    """Returns (category, retry_count)"""
    msg_lower = error_msg.lower()
    
    # Permanent failures
    if any(x in msg_lower for x in ["invalid credentials", "banned"]):
        return ("permanent", 0)
    
    # Retryable with limit
    if any(x in msg_lower for x in ["cloudflare", "security", "captcha"]):
        return ("retryable", 5)  # Max 5 retries
    
    # Transient - retry immediately
    if any(x in msg_lower for x in ["timeout", "closed", "network"]):
        return ("transient", 3)  # Max 3 retries
    
    return ("unknown", 1)
```
