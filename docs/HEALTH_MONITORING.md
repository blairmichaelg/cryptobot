# Health Monitoring and Alerting Guide

This document describes the health monitoring and alerting system for Cryptobot on Azure VM deployments.

## Overview

The health monitoring system provides:
- **Automated service monitoring** - Detects when faucet_worker service crashes
- **Azure Monitor integration** - Sends telemetry to Application Insights
- **Automatic restart with backoff** - Restarts failed services with exponential backoff
- **Health endpoint** - HTTP endpoint for external monitoring
- **Comprehensive logging** - Detailed health logs for debugging

## Components

### 1. Health Monitor Daemon (`health_monitor.service`)

A background daemon that continuously monitors the faucet_worker service.

**Features:**
- Checks service status every 60 seconds
- Monitors disk usage, memory usage, and heartbeat
- Automatically restarts crashed services
- Implements exponential backoff to prevent restart loops
- Sends alerts to Azure Monitor

**Configuration:**
```bash
# View status
sudo systemctl status health_monitor

# View logs
sudo journalctl -u health_monitor -f

# Restart
sudo systemctl restart health_monitor
```

### 2. Health Endpoint Server (`health_endpoint.service`)

HTTP server that exposes health metrics for external monitoring.

**Endpoints:**
- `GET /health` - Simple health check (returns 200 if healthy, 503 if unhealthy)
- `GET /metrics` - Detailed metrics as JSON
- `GET /` - HTML documentation page

**Configuration:**
```bash
# View status
sudo systemctl status health_endpoint

# Test endpoint
curl http://localhost:8080/health
curl http://localhost:8080/metrics

# External access (if firewall allows)
curl http://VM_PUBLIC_IP:8080/health
```

### 3. Enhanced systemd Watchdog

The faucet_worker service includes systemd watchdog configuration:

**Features:**
- Service must send watchdog ping every 5 minutes
- Automatic restart if watchdog expires
- Resource limits (4GB memory, 200% CPU)
- Start limit burst protection (max 5 restarts in 5 minutes)

### 4. Azure Monitor Integration

Integration with Azure Application Insights for monitoring and alerting.

**Metrics tracked:**
- `health.disk_usage` - Disk usage percentage
- `health.memory_usage` - Memory usage percentage
- `health.heartbeat_age` - Age of heartbeat file in seconds
- `health.crash_count` - Number of service restarts
- `health.service_active` - Service active status (0 or 1)

**Errors tracked:**
- `health_critical` - Critical health issues
- `health_warning` - Warning-level health issues

## Setup

### Prerequisites

1. Azure Application Insights resource (optional)
2. Azure VM running Ubuntu 22.04 or later
3. Python 3.10+ with venv
4. Git and systemd

### Installation

#### Option 1: Full Deployment (Recommended)

Use the deployment script to install all services:

```bash
# From local machine - deploy to Azure VM
./deploy/azure_deploy.sh --resource-group APPSERVRG --vm-name DevNode01

# Or SSH to VM and run locally
ssh azureuser@VM_IP
cd ~/Repositories/cryptobot
./deploy/deploy.sh --install-service
```

This will:
- Update faucet_worker.service with watchdog configuration
- Install and enable health_monitor.service
- Install and enable health_endpoint.service
- Start all services

#### Option 2: Manual Installation

```bash
# SSH to VM
ssh azureuser@VM_IP

# Navigate to repository
cd ~/Repositories/cryptobot

# Pull latest changes
git pull

# Install dependencies
source .venv/bin/activate
pip install -r requirements.txt

# Copy service files
sudo cp deploy/faucet_worker.service /etc/systemd/system/
sudo cp deploy/health_monitor.service /etc/systemd/system/
sudo cp deploy/health_endpoint.service /etc/systemd/system/

# Reload systemd
sudo systemctl daemon-reload

# Enable and start services
sudo systemctl restart faucet_worker
sudo systemctl enable health_monitor
sudo systemctl start health_monitor
sudo systemctl enable health_endpoint
sudo systemctl start health_endpoint

# Verify
sudo systemctl status faucet_worker
sudo systemctl status health_monitor
sudo systemctl status health_endpoint
```

### Azure Monitor Configuration

1. **Create Application Insights resource** (if not exists):
   ```bash
   az monitor app-insights component create \
     --app cryptobot-insights \
     --location westus2 \
     --resource-group APPSERVRG \
     --application-type web
   ```

2. **Get connection string**:
   ```bash
   az monitor app-insights component show \
     --app cryptobot-insights \
     --resource-group APPSERVRG \
     --query connectionString -o tsv
   ```

3. **Add to .env file** on VM:
   ```bash
   APPLICATIONINSIGHTS_CONNECTION_STRING="InstrumentationKey=xxx;IngestionEndpoint=https://..."
   ```

4. **Restart health monitor**:
   ```bash
   sudo systemctl restart health_monitor
   ```

## Usage

### Manual Health Check

Run a one-time health check:

```bash
# Simple check
python -m core.health_monitor --check

# With JSON output
python -m core.health_monitor --check --json

# With alerts to Azure Monitor
python -m core.health_monitor --check --alert

# With auto-restart on critical failures
python -m core.health_monitor --check --restart
```

### Health Check via Shell Script

Use the enhanced vm_health.sh script:

```bash
# From local machine
./deploy/vm_health.sh --resource-group APPSERVRG --vm-name DevNode01

# With alerting
./deploy/vm_health.sh --resource-group APPSERVRG --vm-name DevNode01 --alert

# With auto-restart on failure
./deploy/vm_health.sh --resource-group APPSERVRG --vm-name DevNode01 --restart
```

### Monitoring Logs

```bash
# Health monitor logs
sudo journalctl -u health_monitor -f

# Health endpoint logs
sudo journalctl -u health_endpoint -f

# Faucet worker logs
sudo journalctl -u faucet_worker -f

# Health log file
tail -f ~/Repositories/cryptobot/logs/vm_health.log
```

### External Monitoring

Set up external monitoring using the health endpoint:

**UptimeRobot:**
1. Create new HTTP monitor
2. URL: `http://VM_PUBLIC_IP:8080/health`
3. Expected status code: 200
4. Check interval: 5 minutes

**Azure Monitor Alert:**
```bash
az monitor metrics alert create \
  --name cryptobot-service-down \
  --resource-group APPSERVRG \
  --scopes /subscriptions/xxx/resourceGroups/APPSERVRG/providers/Microsoft.Insights/components/cryptobot-insights \
  --condition "count health.service_active < 1" \
  --window-size 5m \
  --evaluation-frequency 1m \
  --action email blazefoley97@gmail.com
```

## Health Status Levels

| Status | Description | Action |
|--------|-------------|--------|
| **HEALTHY** | All systems normal | None |
| **WARNING** | Minor issues detected | Monitor, may self-resolve |
| **CRITICAL** | Service down or major issue | Auto-restart triggered (if enabled) |
| **UNKNOWN** | Cannot determine status | Manual investigation required |

## Alerts

### Automatic Alerts

The health monitor automatically generates alerts for:

1. **Service not active** (CRITICAL)
2. **Service not running** (CRITICAL)
3. **Crash loop detected** - More than 5 restarts (WARNING)
4. **Disk usage > 90%** (CRITICAL)
5. **Disk usage > 80%** (WARNING)
6. **Memory usage > 90%** (WARNING)
7. **No heartbeat file** (WARNING)
8. **Stale heartbeat** - Older than 5 minutes (WARNING)
9. **Recent errors in logs** (WARNING)

### Manual Alerting

Configure webhook and email notifications in .env:

#### Webhook Notifications (Slack, Discord, Teams)

1. **Slack Webhook Setup:**
   ```bash
   # Create an Incoming Webhook in Slack:
   # 1. Go to https://api.slack.com/apps
   # 2. Create a new app or select existing
   # 3. Add "Incoming Webhooks" feature
   # 4. Create webhook for a channel
   # 5. Copy the webhook URL
   
   # Add to .env:
   ALERT_WEBHOOK_URL=https://hooks.slack.com/services/YOUR/WEBHOOK/URL
   ```

2. **Discord Webhook Setup:**
   ```bash
   # Create webhook in Discord:
   # 1. Go to Server Settings → Integrations → Webhooks
   # 2. Create New Webhook
   # 3. Copy webhook URL
   # 4. Append "/slack" to the URL for Slack-compatible format
   
   # Add to .env:
   ALERT_WEBHOOK_URL=https://discord.com/api/webhooks/YOUR_WEBHOOK_ID/YOUR_TOKEN/slack
   ```

3. **Microsoft Teams Webhook Setup:**
   ```bash
   # Create webhook in Teams:
   # 1. Go to channel → Connectors → Incoming Webhook
   # 2. Configure and create
   # 3. Copy webhook URL
   
   # Add to .env:
   ALERT_WEBHOOK_URL=https://outlook.office.com/webhook/YOUR_WEBHOOK_URL
   ```

#### Email Notifications

1. **Gmail SMTP Setup:**
   ```bash
   # Enable "App Passwords" in Google Account:
   # 1. Go to Google Account → Security
   # 2. Enable 2-Step Verification
   # 3. Generate App Password for "Mail"
   
   # Add to .env:
   ALERT_EMAIL=recipient@example.com
   SMTP_HOST=smtp.gmail.com
   SMTP_PORT=587
   SMTP_USER=your-gmail@gmail.com
   SMTP_PASSWORD=your-app-password
   ```

2. **Other SMTP Providers:**
   ```bash
   # Outlook/Office365:
   SMTP_HOST=smtp-mail.outlook.com
   SMTP_PORT=587
   
   # SendGrid:
   SMTP_HOST=smtp.sendgrid.net
   SMTP_PORT=587
   SMTP_USER=apikey
   SMTP_PASSWORD=your-sendgrid-api-key
   
   # Mailgun:
   SMTP_HOST=smtp.mailgun.org
   SMTP_PORT=587
   ```

3. **Test Notifications:**
   ```bash
   # Run a health check with alerts enabled
   python -m core.health_monitor --check --alert
   
   # This will send notifications if status is WARNING or CRITICAL
   ```


## Auto-Restart Behavior

The health monitor implements exponential backoff for service restarts:

1. **Initial restart delay**: 10 seconds
2. **Subsequent delays**: Doubles each time (10s, 20s, 40s, 80s, 160s)
3. **Maximum delay**: 300 seconds (5 minutes)
4. **Reset**: Backoff resets when service is healthy

**Example restart timeline:**
```
Crash #1 → Wait 10s → Restart
Crash #2 → Wait 20s → Restart
Crash #3 → Wait 40s → Restart
Crash #4 → Wait 80s → Restart
Crash #5 → Wait 160s → Restart
Crash #6+ → Wait 300s → Restart
```

**Backoff state** is persisted in `logs/restart_backoff.json`.

## Troubleshooting

### Health Monitor Not Starting

```bash
# Check service status
sudo systemctl status health_monitor

# Check for errors
sudo journalctl -u health_monitor -n 50

# Verify Python module
python -m core.health_monitor --check

# Check permissions
ls -la ~/Repositories/cryptobot/logs/
```

### Health Endpoint Not Responding

```bash
# Check if service is running
sudo systemctl status health_endpoint

# Check if port is listening
sudo netstat -tlnp | grep 8080

# Test locally
curl http://localhost:8080/health

# Check firewall (if external access needed)
sudo ufw status
sudo ufw allow 8080/tcp
```

### Service Keeps Restarting

```bash
# Check restart count
python -m core.health_monitor --check --json | jq .crash_count

# Check backoff state
cat ~/Repositories/cryptobot/logs/restart_backoff.json

# View recent errors
sudo journalctl -u faucet_worker -p err -n 20

# Reset backoff manually
rm ~/Repositories/cryptobot/logs/restart_backoff.json
sudo systemctl restart health_monitor
```

### Azure Monitor Not Receiving Data

```bash
# Verify connection string is set
grep APPLICATIONINSIGHTS .env

# Test Azure Monitor connectivity
python -c "from core.azure_monitor import initialize_azure_monitor; print(initialize_azure_monitor())"

# Check health monitor is sending metrics
sudo journalctl -u health_monitor | grep "Sent metrics"

# Verify in Azure Portal
# Navigate to Application Insights → Metrics → Custom metrics
```

## Architecture Diagram

```
┌─────────────────────────────────────────────────────────┐
│                     Azure VM (DevNode01)                 │
├─────────────────────────────────────────────────────────┤
│                                                           │
│  ┌──────────────────┐        ┌────────────────────┐    │
│  │ faucet_worker    │◄───────│ health_monitor     │    │
│  │ (main service)   │        │ (daemon)           │    │
│  └────────┬─────────┘        └─────────┬──────────┘    │
│           │                             │                │
│           │ heartbeat.txt              │ checks every   │
│           ▼                             │ 60s            │
│  ┌──────────────────┐                  │                │
│  │ logs/            │                  │                │
│  │ - heartbeat.txt  │                  │                │
│  │ - vm_health.log  │◄─────────────────┘                │
│  └──────────────────┘                                    │
│           ▲                                               │
│           │                                               │
│  ┌────────┴─────────┐                                    │
│  │ health_endpoint  │                                    │
│  │ (HTTP :8080)     │                                    │
│  └────────┬─────────┘                                    │
│           │                                               │
└───────────┼───────────────────────────────────────────────┘
            │
            │ HTTP /health, /metrics
            │
    ┌───────▼────────┐       ┌─────────────────────┐
    │  External      │       │  Azure Monitor      │
    │  Monitoring    │       │  (App Insights)     │
    │  (UptimeRobot) │       │                     │
    └────────────────┘       └──────▲──────────────┘
                                    │
                                    │ telemetry
                             health_monitor sends
                             metrics & errors
```

## Best Practices

1. **Monitor the health endpoint** - Set up external monitoring (UptimeRobot, Pingdom, etc.)
2. **Configure Azure Monitor** - Enable Application Insights for centralized monitoring
3. **Set up alerts** - Configure email/webhook notifications for critical failures
4. **Review logs regularly** - Check vm_health.log weekly for patterns
5. **Test auto-restart** - Periodically verify auto-restart works correctly
6. **Keep backoff state** - Don't delete restart_backoff.json unless debugging
7. **Monitor resource usage** - Watch disk and memory trends to prevent issues

## Future Enhancements

- [x] Email notifications via SMTP
- [x] Slack/Discord webhook integration
- [ ] Grafana dashboard integration
- [ ] Predictive failure detection
- [ ] Auto-scaling based on load
- [ ] Integration with Azure Logic Apps for complex workflows

## Enhanced Monitoring Features (v2.0)

The following enhanced features were added in version 2.0:

### 30-Day Metric Retention

- **Local Storage**: Metrics stored in `config/metrics/retained_metrics.json`
- **Auto-Cleanup**: Metrics older than 30 days automatically removed
- **Historical Analysis**: Support for trend analysis and reporting

### Enhanced Proxy Health Monitoring

- **Configurable Thresholds**: 
  - Minimum 50 healthy proxies
  - Maximum 5000ms average latency
- **Detailed Health Status**: Active count, latency, cooldowns, dead proxies
- **Automated Alerts**: Critical alerts when thresholds breached

### Queue Stall Detection

- **Detection Window**: 10 minutes of no progress
- **Smart Tracking**: Monitors queue size changes and running jobs
- **Automatic Alerts**: Notifies when queue appears stalled

### Error Rate Tracking

- **Sliding Window**: 10-minute error tracking window
- **Threshold Alerts**: Alert when >5 errors in window
- **Auto-Cleanup**: Expired errors automatically removed

### Daily Summary Reports

- **Scheduled Generation**: Automatic reports at 23:30 daily
- **Comprehensive Data**:
  - Claims attempted and success rate
  - Earnings by currency
  - Per-faucet performance
  - Proxy health status
- **Multi-Channel Delivery**: Webhook, email, and Azure Monitor

### Service Event Tracking

All service lifecycle events now tracked with 30-day retention:
- Service starts
- Service restarts (with attempt count)
- Restart successes/failures
- Crash events

Access metrics programmatically:
```python
from core.azure_monitor import get_metric_store

store = get_metric_store()
summary = store.get_daily_summary(days=7)
restarts = store.get_metrics(name="service.restart", hours=24)
```

## Support

For issues or questions:
1. Check logs: `sudo journalctl -u health_monitor -f`
2. Run manual health check: `python -m core.health_monitor --check`
3. Review this documentation
4. Check GitHub issues: https://github.com/blairmichaelg/cryptobot/issues

---

**Last Updated:** February 6, 2026  
**Version:** 2.0 (Enhanced Monitoring)
