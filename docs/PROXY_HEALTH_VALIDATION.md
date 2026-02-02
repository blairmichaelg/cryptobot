# Proxy Health Validation System

## Overview
Automated proxy health validation and monitoring system for the cryptobot application. Tests all configured proxies for connectivity, latency, and reliability.

## Latest Validation Results (Jan 31, 2026)

### Summary
- **Total Proxies**: 101
- **Healthy**: 97 (96.0%)
- **Degraded**: 0 (0.0%)
- **Dead**: 4 (4.0%)

### Latency Statistics (Healthy Proxies)
- **Average**: 1826ms
- **Median**: 1566ms
- **Min**: 788ms
- **Max**: 5133ms
- **Std Dev**: 770ms

### Top 5 Fastest Proxies
1. session-9oq0946b: 788ms avg (640-914ms range)
2. session-s0g4ah9d: 911ms avg (672-1073ms range)
3. session-ytauezoc: 974ms avg (737-1141ms range)
4. session-bk55r6o3: 985ms avg (655-1246ms range)
5. session-npkybvzo: 1022ms avg (748-1249ms range)

### Dead Proxies (Removed)
4 proxies were identified as dead and removed from health tracking:
- **session-c7vz7zsd**: HTTP 403 errors
- **session-tfhjsa0c**: HTTP 403 Forbidden
- **session-5qpp07bw**: HTTP 403 Forbidden
- **session-kmd4t7ax**: Timeout + SSL connection errors

These proxies failed all connectivity tests and have been removed from the active pool.

## Files and Scripts

### Configuration Files
- `config/proxy_health.json` - Persisted health metrics
  - Version: 1
  - Contains latency history (last 5 measurements per proxy)
  - Tracks failures, cooldowns, reputation scores
  - Dead proxies removed automatically
  
- `config/proxy_validation_report.json` - Detailed validation results
  - Full test results for each proxy
  - Timestamp and test configuration
  - Success/failure breakdown

### Scripts

#### 1. validate_proxy_health.py
**Purpose**: Comprehensive proxy validation with detailed reporting

**Usage**:
```bash
python scripts/validate_proxy_health.py
```

**Features**:
- Tests all proxies against 3 endpoints (ipinfo.io, google.com, ipify.org)
- Measures latency with statistics (avg, min, max, median, std dev)
- Identifies healthy, degraded, and dead proxies
- Generates detailed console report
- Updates proxy_health.json with latest metrics
- Saves detailed JSON report for analysis

**Test Criteria**:
- Timeout: 15 seconds per test
- Concurrent tests: 10 proxies at a time
- Healthy: ≥66% success rate (2/3 tests pass)
- Dead: 0% success rate (all tests fail)
- Degraded: Between 0-66% success

#### 2. proxy_health_check.py
**Purpose**: Fast automated health check for scheduled monitoring

**Usage**:
```bash
python scripts/proxy_health_check.py
```

**Features**:
- Lighter-weight than full validation
- Quick summary output (less verbose)
- Exit code 0 if healthy, 1 if >50% dead/degraded
- Suitable for cron jobs or task scheduler

**When to Use**:
- Daily automated checks
- Pre-deployment validation
- Continuous monitoring

#### 3. proxy_health_check.bat
**Purpose**: Windows Task Scheduler wrapper

**Setup Instructions**:
1. Open Task Scheduler (`taskschd.msc`)
2. Create Basic Task: "Cryptobot Proxy Health Check"
3. Trigger: Daily at 6:00 AM (or preferred schedule)
4. Action: Start a program
   - Program: `C:\Users\azureuser\Repositories\cryptobot\scripts\proxy_health_check.bat`
5. Enable "Run whether user is logged on or not"

**Logging**:
- Appends to `logs/proxy_health_check.log`
- Includes timestamps
- Records success/failure status

## Integration with ProxyManager

The health validation system integrates with `core/proxy_manager.py`:

### Health Data Loading
```python
def _load_health_data(self):
    """Load persisted proxy health data from disk."""
```
- Loads on ProxyManager initialization
- Version checking (expects version 1)
- Stale data filtering (max age: 7 days)
- Auto-cleanup of expired cooldowns

### Health Data Structure
```json
{
  "version": 1,
  "timestamp": 1769874492.622884,
  "proxy_latency": {
    "user:pass@ip:port": [1826.3, 1566.2, ...]  // Last 5 measurements
  },
  "proxy_failures": {},  // Consecutive failure counts
  "dead_proxies": [],    // Removed proxy keys
  "proxy_cooldowns": {}, // Timestamp when usable again
  "proxy_reputation": {},
  "proxy_soft_signals": {},
  "proxy_host_failures": {}
}
```

### Health Metrics Used By ProxyManager
1. **Latency Tracking**: Average of last 5 measurements
2. **Dead Proxy Detection**: Removed from pool if avg > 5000ms
3. **Cooldown Management**: Temporary bans for detected/failed proxies
4. **Reputation Scoring**: Performance-based proxy selection

## Manual Testing Commands

### Test All Proxies
```bash
python scripts/validate_proxy_health.py
```

### Test Specific Proxy (using curl)
```bash
# Example for one of the fastest proxies
curl -x http://ub033d0d0583c05dd-zone-custom-session-9oq0946b:ub033d0d0583c05dd@43.135.141.142:2334 http://ipinfo.io/ip

# Test latency
curl -x http://[proxy] -w "@curl-format.txt" -o /dev/null -s http://ipinfo.io/ip
```

### Check Proxy Health File
```bash
# View current health metrics
cat config/proxy_health.json | python -m json.tool

# Count tracked proxies
python -c "import json; data=json.load(open('config/proxy_health.json')); print(f'Tracked: {len(data[\"proxy_latency\"])}')"
```

## Troubleshooting

### Common Proxy Errors

#### HTTP 403 Forbidden
- **Cause**: IP blocked by target site or proxy provider
- **Action**: Proxy marked as dead and removed
- **Prevention**: Rotate proxies more frequently

#### HTTP 407 Proxy Authentication Required
- **Cause**: Credentials expired or invalid
- **Action**: Check proxy provider account status
- **Fix**: Update credentials in proxies.txt

#### Connection Timeout
- **Cause**: Proxy server down or network issues
- **Action**: Temporary failure, retry on next check
- **Threshold**: 3 consecutive timeouts → marked dead

#### SSL Connection Errors
- **Cause**: TLS/SSL handshake failure
- **Action**: Check if proxy supports HTTPS
- **Note**: Some residential proxies only support HTTP

### Health Check Issues

#### All Proxies Show as Dead
1. Check internet connectivity
2. Verify proxies.txt format is correct
3. Check proxy provider service status
4. Try manual curl test to isolate issue

#### Inconsistent Results
1. Proxies may be location-dependent
2. Time of day affects residential proxy availability
3. Target sites may rate-limit
4. Run validation 2-3 times to confirm

#### Health File Not Updating
1. Check file permissions on config/proxy_health.json
2. Verify Python has write access
3. Look for errors in script output
4. Check disk space

## Performance Tuning

### Adjust Validation Settings
Edit `scripts/validate_proxy_health.py`:

```python
TIMEOUT_SECONDS = 15        # Increase for slow proxies
MAX_CONCURRENT = 10         # Lower if overwhelming network
DEAD_THRESHOLD_MS = 5000    # Adjust dead proxy cutoff
```

### Modify Test URLs
```python
TEST_URLS = [
    "http://ipinfo.io/ip",           # Fast, reliable
    "https://www.google.com",        # Tests HTTPS
    "https://api.ipify.org?format=json"  # JSON endpoint
]
```
Add/remove URLs based on your target sites.

### Schedule Frequency
- **Development**: Manual validation as needed
- **Testing**: Every 6 hours
- **Production**: Daily at low-traffic times (6 AM)
- **Critical**: Every 2 hours (if proxy pool is limited)

## Maintenance Checklist

### Daily
- [x] Review automated health check logs
- [x] Verify healthy proxy count > 90%

### Weekly
- [x] Run full validation manually
- [x] Review latency trends
- [x] Check for new dead proxies
- [x] Update proxy pool if needed

### Monthly
- [x] Audit proxy provider costs vs usage
- [x] Review top performers for optimization
- [x] Clean up stale health data (auto-cleaned after 7 days)

## Metrics and Alerting

### Key Metrics to Monitor
1. **Healthy Percentage**: Should stay > 90%
2. **Average Latency**: Target < 2000ms
3. **Dead Count**: Should not increase rapidly
4. **Degraded Count**: Investigate if > 5%

### Alerting Thresholds
```python
# Add to proxy_health_check.py for alerting
if healthy_percent < 0.80:
    send_alert("WARNING: Only {}% of proxies healthy".format(healthy_percent))
    
if avg_latency > 3000:
    send_alert("WARNING: Average latency {}ms exceeds threshold".format(avg_latency))
```

## Future Enhancements
- [ ] Web dashboard for real-time monitoring
- [ ] Grafana integration for metrics visualization
- [ ] Auto-retry failed proxies after cooldown period
- [ ] Geographic distribution analysis
- [ ] Provider performance comparison (2Captcha vs Azure vs DO)
- [ ] Cost per successful request tracking
- [ ] Predictive proxy failure detection

## References
- ProxyManager: `core/proxy_manager.py`
- Proxy Configuration: `config/proxies.txt`
- Health Data Schema: `config/proxy_health.json`
- Validation Reports: `config/proxy_validation_report.json`
