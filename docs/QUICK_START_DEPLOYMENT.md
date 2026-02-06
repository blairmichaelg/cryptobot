# Health Monitoring - Deployment Quick Start

## For Azure VM Deployment

### 1. Deploy Code

```bash
# SSH to Azure VM
ssh azureuser@4.155.230.212

cd ~/Repositories/cryptobot
git fetch origin
git checkout copilot/add-health-monitoring-alerts
git pull
```

### 2. Run Verification Script

```bash
./scripts/verify_health_monitoring.sh
```

This will check:
- ✅ All required files present
- ✅ Python syntax valid
- ✅ Core features working
- ✅ Service status
- ✅ Configuration

### 3. Configure Alerts (Optional)

Edit `.env` to add:

```bash
# Webhook for Slack/Discord/Teams
ALERT_WEBHOOK_URL=https://hooks.slack.com/services/YOUR/WEBHOOK/URL

# Email alerts
ALERT_EMAIL=your-email@example.com

# Azure Monitor
APPLICATIONINSIGHTS_CONNECTION_STRING=InstrumentationKey=...
```

### 4. Restart Service

```bash
sudo systemctl restart faucet_worker
sudo systemctl status faucet_worker
```

### 5. Monitor

```bash
# Watch logs
tail -f logs/faucet_bot.log

# Check metrics
cat config/metrics/retained_metrics.json | python3 -m json.tool | head -50
```

## Features Deployed

✅ **30-Day Metric Retention** - Local storage in `config/metrics/`  
✅ **Proxy Health Monitoring** - Alerts when <50 proxies or >5000ms latency  
✅ **Queue Stall Detection** - Alerts after 10min of no progress  
✅ **Error Rate Tracking** - Alerts on >5 errors in 10min  
✅ **Daily Summary** - Automated report at 23:30  
✅ **Service Event Tracking** - Logs all restarts and crashes  
✅ **Uptime Tracking** - In every health check  

## Alert Types

- **Critical**: Service down, <50 proxies
- **Warning**: High latency, queue stalled, high error rate
- **Daily**: Summary at 23:30

## Quick Checks

```bash
# Service status
sudo systemctl status faucet_worker

# Recent logs
tail -50 logs/faucet_bot.log

# Metrics count
cat config/metrics/retained_metrics.json | python3 -c "import sys,json; print(len(json.load(sys.stdin)))"

# Proxy health
python3 -c "from core.proxy_manager import ProxyManager; from core.config import load_settings; h=ProxyManager(load_settings()).get_health_status(); print(f'Proxies: {h[\"active_proxies\"]}/{h[\"total_proxies\"]}')"
```

## Full Documentation

See **docs/DEPLOYMENT_TESTING_GUIDE.md** for comprehensive testing steps.

## Troubleshooting

**No metrics file?** - Run for a few minutes, metrics auto-created  
**No alerts?** - Check .env configuration  
**Service not starting?** - Check `sudo journalctl -u faucet_worker -n 50`

## Success Criteria

✅ Service running without errors  
✅ Metrics being collected  
✅ No alerts if system healthy  
✅ Daily summary at 23:30  

---

**Quick Start Version:** 1.0  
**Last Updated:** February 6, 2026
