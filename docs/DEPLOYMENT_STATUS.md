# Cryptobot Deployment Status

**Last Updated:** February 8, 2026

---

## Current Deployment: Azure VM (ACTIVE)

### Production VM Details
- **VM Name**: DevNode01
- **Resource Group**: APPSERVRG
- **Location**: West US 2
- **Public IP**: 4.155.230.212
- **Size**: Standard_D2s_v3 (2 vCPUs, 8 GB RAM)
- **OS**: Ubuntu 22.04 LTS (Jammy)
- **Status**: Running

### Service Configuration
- **systemd service**: `faucet_worker`
- **Working Directory**: `/home/azureuser/Repositories/cryptobot`
- **Proxy Provider**: Zyte (100 endpoints, `USE_2CAPTCHA_PROXIES=true`)
- **Faucets**: 18 total (7 standard + 11 Pick.io family)

### Local Development Environment
- **Host**: Windows development machine
- **User**: azureuser
- **Path**: `C:\Users\azureuser\Repositories\cryptobot`
- **Purpose**: Code editing only — do NOT run browser tests locally

---

## Git Workflow: Single Branch (`master`)

All three locations must stay in sync:

| Location | Path | Purpose |
|----------|------|---------|
| Local (Windows) | `C:\Users\azureuser\Repositories\cryptobot` | Code editing |
| Remote (GitHub) | `github.com/blairmichaelg/cryptobot` | Central repo |
| VM (Linux) | `~/Repositories/cryptobot` | Production runtime |

**Sync workflow:**
1. Edit code locally
2. `git push origin master`
3. SSH to VM: `cd ~/Repositories/cryptobot && git pull origin master`
4. `sudo systemctl restart faucet_worker`

---

## Deployment Steps

### Manual Deploy

```bash
# 1. Push from local
git push origin master

# 2. SSH to VM and pull
ssh azureuser@4.155.230.212 "cd ~/Repositories/cryptobot && git pull origin master"

# 3. Install deps if requirements.txt changed
ssh azureuser@4.155.230.212 "cd ~/Repositories/cryptobot && pip install -r requirements.txt"

# 4. Restart service
ssh azureuser@4.155.230.212 "sudo systemctl restart faucet_worker"

# 5. Verify
ssh azureuser@4.155.230.212 "sudo systemctl status faucet_worker"
```

### Automated Deploy

```bash
./deploy/azure_deploy.sh --resource-group APPSERVRG --vm-name DevNode01
```

---

## Deployment Infrastructure

| Component | Status | Notes |
|-----------|--------|-------|
| deploy/deploy.sh | Ready | Full systemd setup, health checks |
| deploy/azure_deploy.sh | Ready | Azure CLI deployment automation |
| deploy/deploy_vm.ps1 | Ready | PowerShell SSH-based deployment |
| deploy/faucet_worker.service | Ready | systemd unit file |
| deploy/vm_health.sh | Ready | VM health monitoring |
| Azure VM (DevNode01) | Active | Running in APPSERVRG |

---

## Monitoring & Health Checks

```bash
# Service status
ssh azureuser@4.155.230.212 "sudo systemctl status faucet_worker"

# Live logs
ssh azureuser@4.155.230.212 "journalctl -u faucet_worker -f"

# Application health
ssh azureuser@4.155.230.212 "cd ~/Repositories/cryptobot && python meta.py health"

# Monitor claims
ssh azureuser@4.155.230.212 "tail -f ~/Repositories/cryptobot/logs/production_run.log | grep -E '(SUCCESS|FAILED|Claim)'"

# Check proxy config
ssh azureuser@4.155.230.212 "grep USE_2CAPTCHA_PROXIES ~/Repositories/cryptobot/.env"
```

---

## Security

- SSH key authentication (no passwords)
- `.env` file transferred securely via scp, never committed to git
- systemd runs as non-root user (azureuser)
- Encrypted cookie storage (`CRYPTOBOT_COOKIE_KEY`)

---

**Document maintained by:** Project team
**Review frequency:** After each deployment change
