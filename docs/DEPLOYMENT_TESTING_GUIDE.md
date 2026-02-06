# Health Monitoring Deployment and Testing Guide

## Overview

This guide provides step-by-step instructions for deploying and testing the new health monitoring and alerting features on the Azure VM (DevNode01).

## Prerequisites

- Azure VM deployed and accessible (4.155.230.212)
- SSH access to the VM: `ssh azureuser@4.155.230.212`
- Azure CLI configured (optional, for Azure Monitor)
- Notification channels configured (webhook/email)

## Deployment Steps

### 1. Pre-Deployment Verification

Run existing tests to ensure code quality:

```bash
# On your local machine or CI/CD
cd /home/runner/work/cryptobot/cryptobot

# Run existing health monitor tests
pytest tests/test_health_monitor.py -v

# Run Azure monitor tests
pytest tests/test_azure_monitor.py -v

# Run proxy health tests
pytest tests/test_proxy_health_persistence.py -v

# Check syntax
python -m py_compile core/azure_monitor.py core/health_monitor.py core/orchestrator.py core/proxy_manager.py
```

### 2. Deploy to Azure VM

Use the existing deployment script with the updated code:

```bash
# Deploy to Azure VM
./deploy/azure_deploy.sh --resource-group APPSERVRG --vm-name DevNode01

# Or manually deploy via SSH
ssh azureuser@4.155.230.212 << 'EOF'
  cd ~/Repositories/cryptobot
  git fetch origin
  git checkout origin/copilot/add-health-monitoring-alerts
  git pull
EOF
```

### 3. Configure Environment Variables

SSH to the VM and configure alerting:

```bash
ssh azureuser@4.155.230.212

cd ~/Repositories/cryptobot

# Edit .env file
nano .env
```

Add/update these configuration values:

```bash
# Azure Monitor (optional but recommended)
APPLICATIONINSIGHTS_CONNECTION_STRING=InstrumentationKey=xxx;IngestionEndpoint=https://xxx.in.applicationinsights.azure.com/

# Webhook notifications (Slack, Discord, Teams)
ALERT_WEBHOOK_URL=https://hooks.slack.com/services/YOUR/WEBHOOK/URL

# Email notifications
ALERT_EMAIL=your-email@example.com
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USER=your-smtp-user@gmail.com
SMTP_PASSWORD=your-app-password
```

### 4. Restart Services

```bash
# On the Azure VM
sudo systemctl restart faucet_worker

# Verify service started
sudo systemctl status faucet_worker

# Check logs for health monitoring initialization
tail -f ~/Repositories/cryptobot/logs/faucet_bot.log | grep -i "health\|monitor\|alert"
```

## Testing Steps

### Test 1: Metric Retention Store

Verify the metric retention system is working:

```bash
# On the Azure VM
cd ~/Repositories/cryptobot

# Check if metrics directory was created
ls -la config/metrics/

# After service runs for a few minutes, check metrics file
cat config/metrics/retained_metrics.json | python -m json.tool | head -50

# Verify metrics are being recorded
python3 << 'EOF'
from core.azure_monitor import get_metric_store

store = get_metric_store()
metrics = store.get_metrics(hours=1)
print(f"Total metrics in last hour: {len(metrics)}")

# Get summary
summary = store.get_daily_summary(days=1)
print(f"\nMetrics tracked: {list(summary['metrics'].keys())}")
EOF
```

**Expected Output:**
- Metrics directory exists: `config/metrics/retained_metrics.json`
- Metrics file contains recent entries
- Summary shows tracked metrics like `service.uptime_seconds`, `service.restart`, etc.

### Test 2: Proxy Health Monitoring

Test proxy health status monitoring:

```bash
# On the Azure VM
cd ~/Repositories/cryptobot

python3 << 'EOF'
from core.config import load_settings
from core.proxy_manager import ProxyManager

settings = load_settings()
proxy_manager = ProxyManager(settings)

# Get health status
health = proxy_manager.get_health_status()

print("Proxy Health Status:")
print(f"  Healthy: {health['healthy']}")
print(f"  Total Proxies: {health['total_proxies']}")
print(f"  Active Proxies: {health['active_proxies']}")
print(f"  Avg Latency: {health['avg_latency_ms']:.0f}ms")
print(f"  Meets Min Threshold: {health['meets_min_threshold']}")
print(f"  Latency OK: {health['latency_ok']}")

if health['alerts']:
    print(f"\nAlerts:")
    for alert in health['alerts']:
        print(f"  - {alert}")
else:
    print("\nNo alerts (healthy)")
EOF
```

**Expected Output:**
- Health status dictionary with all fields
- Alerts if proxy count <50 or latency >5000ms
- "No alerts" if system is healthy

### Test 3: Queue Stall Detection

Simulate and test queue stall detection:

```bash
# On the Azure VM
cd ~/Repositories/cryptobot

# Monitor logs for queue stall messages
tail -f logs/faucet_bot.log | grep -i "queue stall\|no progress"

# In another terminal, check queue status
python3 << 'EOF'
import json
from pathlib import Path

# Check session state
session_file = Path("config/session_state.json")
if session_file.exists():
    with open(session_file) as f:
        data = json.load(f)
        queue = data.get("queue", [])
        print(f"Jobs in queue: {len(queue)}")
        print(f"Domains tracked: {len(data.get('domain_last_access', {}))}")
EOF
```

**Expected Output:**
- No queue stall warnings if jobs are processing normally
- Queue stall warning after 10 minutes of no progress (if applicable)

### Test 4: Error Rate Tracking

Test error rate tracking and alerting:

```bash
# On the Azure VM
cd ~/Repositories/cryptobot

# Monitor logs for error rate alerts
tail -f logs/faucet_bot.log | grep -i "high error rate\|errors in.*s"
```

**Expected Output:**
- Alert logged when >5 errors occur within 10 minute window
- Error tracking working with sliding window cleanup

### Test 5: Daily Summary Generation

Test daily summary scheduling (can simulate time):

```bash
# On the Azure VM
cd ~/Repositories/cryptobot

# Check if daily summary is scheduled
python3 << 'EOF'
from datetime import datetime
print(f"Current time: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
print("Daily summary scheduled for 23:30 daily")
print("Check logs at 23:30 for summary generation")
EOF

# Manually trigger summary generation (for testing)
python3 << 'EOF'
import asyncio
from core.config import load_settings
from core.orchestrator import JobScheduler
from unittest.mock import Mock

settings = load_settings()
browser_manager = Mock()
scheduler = JobScheduler(settings, browser_manager)

async def test_summary():
    await scheduler.generate_and_send_daily_summary()
    
asyncio.run(test_summary())
EOF
```

**Expected Output:**
- Summary generated with claims, success rates, earnings
- Notification sent via configured channels
- Log entry confirming summary generation

### Test 6: Service Restart Event Logging

Test restart event tracking:

```bash
# On the Azure VM

# Restart the service
sudo systemctl restart faucet_worker

# Wait a moment for service to start
sleep 5

# Check metrics for restart event
python3 << 'EOF'
from core.azure_monitor import get_metric_store

store = get_metric_store()
restarts = store.get_metrics(name="service.restart", hours=1)
print(f"Restart events in last hour: {len(restarts)}")

for restart in restarts[-3:]:  # Last 3 restarts
    import datetime
    ts = datetime.datetime.fromtimestamp(restart['timestamp'])
    print(f"  {ts}: {restart['tags']}")
EOF
```

**Expected Output:**
- Restart event recorded with timestamp
- Tags include restart count and backoff seconds

### Test 7: Uptime Tracking

Verify uptime is being tracked:

```bash
# On the Azure VM
cd ~/Repositories/cryptobot

# Check uptime in health check results
python3 << 'EOF'
from core.health_monitor import HealthMonitor

monitor = HealthMonitor(enable_azure=False)
result = monitor.perform_health_check()

print(f"Service Status: {result.status.value}")
print(f"Service Active: {result.service_active}")
print(f"Service Running: {result.service_running}")
print(f"Uptime: {result.metrics.get('uptime_hours', 0):.2f} hours")
print(f"Heartbeat Age: {result.heartbeat_age_seconds}s")

if result.alerts:
    print("\nAlerts:")
    for alert in result.alerts:
        print(f"  - {alert}")
EOF
```

**Expected Output:**
- Uptime in hours (should be >0 if service running)
- Health status showing service is active and running
- No alerts if system is healthy

### Test 8: Webhook Notifications

Test webhook integration (if configured):

```bash
# On the Azure VM
cd ~/Repositories/cryptobot

# Trigger a test alert
python3 << 'EOF'
import asyncio
from core.health_monitor import HealthMonitor

async def test_webhook():
    monitor = HealthMonitor(enable_azure=False)
    
    # Send test alert
    await monitor.send_health_alert(
        severity="info",
        message="Test alert from health monitoring system deployment",
        component="deployment_test"
    )
    print("Test alert sent")

asyncio.run(test_webhook())
EOF
```

**Expected Output:**
- Alert received in configured webhook channel (Slack/Discord/Teams)
- Log entry confirming alert was sent

### Test 9: Comprehensive Health Check

Run full health check:

```bash
# On the Azure VM
cd ~/Repositories/cryptobot

python3 << 'EOF'
import asyncio
from core.health_monitor import HealthMonitor
from core.config import load_settings
from core.proxy_manager import ProxyManager

async def full_health_check():
    settings = load_settings()
    proxy_manager = ProxyManager(settings)
    
    monitor = HealthMonitor(
        enable_azure=False,
        proxy_manager=proxy_manager
    )
    
    # Run full health check
    results = await monitor.run_full_health_check()
    
    print("=== Full Health Check Results ===")
    print(f"Overall Healthy: {results['overall_healthy']}")
    print(f"\nBrowser Health: {results.get('browser', {}).get('healthy', 'N/A')}")
    print(f"Proxy Health: {results.get('proxy', {}).get('healthy', 'N/A')}")
    print(f"System Health: {results.get('system', {}).get('healthy', 'N/A')}")
    
    # Show proxy details
    if 'proxy' in results:
        proxy = results['proxy']
        print(f"\nProxy Details:")
        print(f"  Active: {proxy.get('active_proxies', 0)}")
        print(f"  Total: {proxy.get('total_proxies', 0)}")
        print(f"  Avg Latency: {proxy.get('avg_latency_ms', 0):.0f}ms")

asyncio.run(full_health_check())
EOF
```

**Expected Output:**
- Comprehensive health report
- All components reporting status
- Proxy health details included

## Validation Checklist

After deployment and testing, verify:

- [ ] Metric retention store created and receiving data
- [ ] Proxy health monitoring active with correct thresholds
- [ ] Queue stall detection functioning
- [ ] Error rate tracking working
- [ ] Daily summary scheduled for 23:30
- [ ] Service restart events being logged
- [ ] Uptime tracking in health checks
- [ ] Webhook notifications working (if configured)
- [ ] Email notifications working (if configured)
- [ ] Azure Monitor receiving telemetry (if configured)
- [ ] No new errors in service logs
- [ ] Service running stable after deployment

## Monitoring Post-Deployment

### 1. Check Service Logs

```bash
# Real-time monitoring
tail -f ~/Repositories/cryptobot/logs/faucet_bot.log

# Check for health-related messages
grep -i "health\|alert\|monitor" logs/faucet_bot.log | tail -50

# Check for errors
grep -i "error\|exception\|failed" logs/faucet_bot.log | tail -50
```

### 2. Monitor Health Metrics

```bash
# Check metrics file growth
watch -n 60 'wc -l config/metrics/retained_metrics.json'

# Monitor proxy health
watch -n 300 'python3 -c "from core.proxy_manager import ProxyManager; from core.config import load_settings; pm = ProxyManager(load_settings()); h = pm.get_health_status(); print(f\"Proxies: {h[\"active_proxies\"]}/{h[\"total_proxies\"]}, Latency: {h[\"avg_latency_ms\"]:.0f}ms\")"'
```

### 3. Check Daily Summaries

```bash
# After 23:30, check if summary was generated
grep "Daily summary" logs/faucet_bot.log | tail -5

# Check notification logs
grep "webhook\|email\|alert" logs/faucet_bot.log | grep -i "summary" | tail -10
```

## Troubleshooting

### Issue: Metrics not being stored

**Check:**
1. Directory permissions: `ls -la config/metrics/`
2. Disk space: `df -h`
3. Logs for errors: `grep "metric" logs/faucet_bot.log | grep -i error`

**Fix:**
```bash
mkdir -p config/metrics
chmod 755 config/metrics
```

### Issue: No alerts received

**Check:**
1. Environment variables set: `cat .env | grep ALERT`
2. Webhook URL valid
3. SMTP credentials correct

**Test:**
```bash
# Test webhook manually
curl -X POST $ALERT_WEBHOOK_URL -H 'Content-Type: application/json' -d '{"text":"Test alert"}'
```

### Issue: Queue stall false positives

**Check:**
1. Queue activity: `cat config/session_state.json | python -m json.tool`
2. Running jobs: `ps aux | grep python | grep -v grep`

**Adjust:**
- Increase threshold in `core/orchestrator.py` if needed

### Issue: High memory usage from metrics

**Check:**
```bash
# Check metrics file size
ls -lh config/metrics/retained_metrics.json

# Count metrics
cat config/metrics/retained_metrics.json | python -m json.tool | grep '"timestamp"' | wc -l
```

**Fix:**
- Metrics are auto-cleaned after 30 days
- Manual cleanup if needed: `python3 -c "from core.azure_monitor import get_metric_store; s = get_metric_store(); s._save_metrics()"`

## Rollback Procedure

If issues arise, rollback to previous version:

```bash
ssh azureuser@4.155.230.212

cd ~/Repositories/cryptobot

# Checkout previous commit
git checkout ac1f87a  # Commit before health monitoring changes

# Restart service
sudo systemctl restart faucet_worker

# Verify
sudo systemctl status faucet_worker
```

## Success Criteria

Deployment is successful when:

1. ✅ All tests pass
2. ✅ Service runs without errors
3. ✅ Metrics being collected and stored
4. ✅ Alerts triggered appropriately
5. ✅ Daily summary generated at 23:30
6. ✅ No performance degradation
7. ✅ Notifications delivered to configured channels

## Next Steps

After successful deployment:

1. Monitor system for 24 hours
2. Verify daily summary is received
3. Review metrics for any anomalies
4. Adjust thresholds if needed
5. Document any issues or improvements
6. Update monitoring dashboards (if using Azure Monitor)

## Support

For issues:
1. Check logs: `~/Repositories/cryptobot/logs/faucet_bot.log`
2. Review this guide's troubleshooting section
3. Check GitHub issues
4. Contact maintainer

---

**Deployment Guide Version:** 1.0  
**Last Updated:** February 6, 2026  
**Related PR:** Add health monitoring with metric retention and automated alerting
