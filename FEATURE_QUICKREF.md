# Quick Reference: New Features

## 1. Shortlink Claiming

### Enable Globally
```bash
# Add to .env
ENABLE_SHORTLINKS=true
```

### Use Programmatically
```python
# In faucet bot
result = await firefaucet_bot.claim(enable_shortlinks=True)

# Or call directly
result = await firefaucet_bot.claim_shortlinks(separate_context=True)
```

### Check Earnings
```python
from core.analytics import AnalyticsTracker
tracker = AnalyticsTracker()
stats = tracker.get_faucet_stats(hours=24)
# Look for claim_type="shortlink" entries
```

---

## 2. Auto-Registration

### Register New Accounts
```bash
# Register on all configured faucets
python scripts/auto_register.py
```

### Rotate Burned Account
```python
from scripts.auto_register import FaucetRegistrar, AccountVault

# Mark old account as burned
vault = AccountVault()
vault.mark_burned("firefaucet", "old_username")

# Create replacement
registrar = FaucetRegistrar(browser_manager, captcha_solver)
new_account = await registrar.rotate_burned_accounts("firefaucet", "old_username")
print(f"New account: {new_account['username']}")
```

### View Stored Accounts
```python
vault = AccountVault()
accounts = vault.load_all_accounts()
for key, account in accounts.items():
    print(f"{key}: {account['email']}, created: {account['created_at']}")
```

---

## 3. ML-Based Timer Prediction

### Automatic Usage
Timer prediction is automatic in the orchestrator. It learns from each claim.

### Manual Usage
```python
from core.orchestrator import JobScheduler

# Initialize (normally done in main.py)
scheduler = JobScheduler(settings, browser_manager, proxy_manager)

# Predict next claim time
stated_timer = 30.0  # minutes
predicted_timer = scheduler.predict_next_claim_time("firefaucet", stated_timer)
print(f"Optimal claim time: {predicted_timer:.1f} minutes")

# Record actual timer (for learning)
scheduler.record_timer_observation("firefaucet", stated_timer=30.0, actual_timer=28.5)
```

### View Timer History
```python
# In orchestrator
print(scheduler.timer_predictions)
# Output: {'firefaucet': [{'stated': 30.0, 'actual': 28.5, 'timestamp': 1234567890}, ...]}
```

---

## 4. CI/CD Pipeline

### Trigger Deployment
```bash
# Auto-deploy on push to master
git push origin master

# Manual deploy via GitHub CLI
gh workflow run deploy.yml -f action=deploy

# Manual deploy with custom parameters
gh workflow run deploy.yml \
  -f action=deploy \
  -f resource_group=APPSERVRG \
  -f vm_name=DevNode01 \
  -f canary_profile=blazefoley97

# Rollback to specific commit
gh workflow run deploy.yml \
  -f action=rollback \
  -f rollback_commit=abc1234
```

### Monitor Deployment
```bash
# Watch live
gh run watch

# List recent runs
gh run list --workflow=deploy.yml

# View logs
gh run view <run_id> --log
```

### Health Check Locally
```bash
# Check service status
ssh azureuser@4.155.230.212 "sudo systemctl status faucet_worker"

# Check heartbeat
ssh azureuser@4.155.230.212 "cat /tmp/cryptobot_heartbeat"

# Check logs
ssh azureuser@4.155.230.212 "tail -100 ~/Repositories/cryptobot/logs/production_run.log"
```

---

## 5. Proxy Management

### Auto-Provision Proxies
```python
from core.proxy_manager import ProxyManager

proxy_manager = ProxyManager(settings)

# Auto-provision if count drops below 10
added = await proxy_manager.auto_provision_proxies(min_threshold=10, provision_count=5)
print(f"Added {added} new proxies")
```

### Auto-Remove Dead Proxies
```python
# Remove proxies with 3+ consecutive failures
removed = await proxy_manager.auto_remove_dead_proxies(failure_threshold=3)
print(f"Removed {removed} dead proxies")
```

### Integration in Main Loop
```python
# In main.py or orchestrator
async def maintenance_loop():
    while True:
        # Check every hour
        await asyncio.sleep(3600)
        
        # Provision if needed
        await proxy_manager.auto_provision_proxies()
        
        # Clean up dead proxies
        await proxy_manager.auto_remove_dead_proxies()
```

### Manual Health Check
```python
# View proxy health stats
print(f"Total proxies: {len(proxy_manager.proxies)}")
print(f"Dead proxies: {len(proxy_manager.dead_proxies)}")
print(f"Latency data: {proxy_manager.proxy_latency}")
print(f"Failure counts: {proxy_manager.proxy_failures}")
```

---

## Environment Variables

```bash
# .env additions

# Shortlinks
ENABLE_SHORTLINKS=true

# Auto-provisioning (optional)
WEBSHARE_API_KEY=your_api_key_here

# Proxy provider
PROXY_PROVIDER=webshare  # or 2captcha, brightdata
```

---

## GitHub Secrets (for CI/CD)

Required secrets in GitHub repository settings:

```
VM_SSH_KEY: <paste your private SSH key>
AZURE_CREDENTIALS: <paste Azure service principal JSON>
```

Optional:
```
DISCORD_WEBHOOK: <webhook URL for notifications>
```

---

## Testing Commands

```bash
# Test shortlinks
ENABLE_SHORTLINKS=true python main.py --single firefaucet --once

# Test auto-registration
python scripts/auto_register.py

# Test proxy auto-provisioning
python -c "
import asyncio
from core.config import BotSettings
from core.proxy_manager import ProxyManager

async def test():
    settings = BotSettings()
    pm = ProxyManager(settings)
    added = await pm.auto_provision_proxies(min_threshold=100, provision_count=5)
    print(f'Added: {added}')

asyncio.run(test())
"

# Test timer prediction (needs history first)
python -c "
from core.orchestrator import JobScheduler
from core.config import BotSettings

settings = BotSettings()
scheduler = JobScheduler(settings, None, None)
scheduler.record_timer_observation('test', 30.0, 28.5)
scheduler.record_timer_observation('test', 30.0, 29.0)
scheduler.record_timer_observation('test', 30.0, 28.0)
predicted = scheduler.predict_next_claim_time('test', 30.0)
print(f'Predicted: {predicted:.1f} min')
"

# Run full test suite
pytest -v

# Run with coverage
pytest --cov=core --cov=faucets
```

---

## Troubleshooting

### Shortlinks not working
```bash
# Check setting
grep ENABLE_SHORTLINKS .env

# Check logs for shortlink errors
grep -i shortlink logs/faucet_bot.log | tail -20

# Test manually
python -c "
import asyncio
from faucets.firefaucet import FireFaucetBot
# ... setup and call claim_shortlinks()
"
```

### Auto-registration fails
```bash
# Check temp-mail API
curl https://api.temp-mail.org/request/domains/format/json

# Check vault encryption
ls -la config/.vault_key config/accounts_vault.enc

# Test credential generation
python -c "
from scripts.auto_register import FaucetRegistrar
from faker import Faker
fake = Faker()
print(fake.user_name())
"
```

### CI/CD deployment fails
```bash
# Check GitHub Actions logs
gh run view --log

# SSH to VM manually
ssh azureuser@4.155.230.212

# Check service logs
sudo journalctl -u faucet_worker -n 100
```

### Proxy auto-provision fails
```bash
# Check API key
echo $WEBSHARE_API_KEY

# Test API manually
curl -H "Authorization: Token $WEBSHARE_API_KEY" \
  https://proxy.webshare.io/api/v2/proxy/list/

# Check proxy file
cat config/proxies.txt | wc -l
```

---

## Performance Monitoring

```python
# Check shortlink ROI
from core.analytics import get_tracker
tracker = get_tracker()
stats = tracker.get_faucet_stats(24)

for faucet, data in stats.items():
    shortlink_earnings = data.get('shortlink_earnings', 0)
    total_earnings = data.get('earnings', 0)
    pct = (shortlink_earnings / total_earnings * 100) if total_earnings > 0 else 0
    print(f"{faucet}: {shortlink_earnings:.6f} from shortlinks ({pct:.1f}%)")

# Check timer prediction accuracy
scheduler = ...  # get scheduler instance
for faucet, history in scheduler.timer_predictions.items():
    if len(history) >= 5:
        avg_drift = sum([(h['actual'] - h['stated']) / h['stated'] for h in history]) / len(history)
        print(f"{faucet}: avg drift = {avg_drift*100:.1f}%")

# Check proxy health
healthy = len([p for p in proxy_manager.proxies if proxy_manager._proxy_key(p) not in proxy_manager.dead_proxies])
total = len(proxy_manager.proxies)
print(f"Proxy health: {healthy}/{total} ({healthy/total*100:.1f}%)")
```
