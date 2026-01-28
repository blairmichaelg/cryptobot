# DigitalOcean Proxy Infrastructure Setup

## Overview

This document describes the DigitalOcean-based proxy infrastructure for Cloudflare bypass, deployed using GitHub Student Developer Pack credits ($200 free).

## Why DigitalOcean?

After encountering Azure Student subscription restrictions:
- **Azure Issue**: Standard_B1s and most VM SKUs unavailable in student subscription
- **DigitalOcean Advantages**:
  - Simple, predictable pricing: $6/month per droplet
  - No subscription restrictions
  - Fast deployment (~3 minutes vs ~15 minutes)
  - Simpler API and CLI (`doctl`)
  - $200 GitHub Student Pack credit = 33 months for 1 droplet or 4 months for 8 droplets
  
## Architecture

### Infrastructure Design

| Component | Details |
|-----------|---------|
| **Droplet Count** | 8 droplets across 5 regions |
| **Regions** | NYC×2, SFO×2, LON×2, FRA×1, SGP×1 |
| **Droplet Size** | s-1vcpu-1gb (1 vCPU, 1GB RAM, 25GB SSD) |
| **OS** | Ubuntu 22.04 LTS x64 |
| **Proxy Software** | Tinyproxy 1.11+ |
| **Proxy Port** | 8888 (TCP) |
| **Firewall** | UFW - allows DevNode01 IP only (4.155.230.212) |
| **Authentication** | None required (IP-restricted access) |

### Naming Convention

Droplets use stealth naming (no crypto/bot terms):
- `edge-node-ny1`, `edge-node-ny2` (NYC)
- `edge-node-sf1`, `edge-node-sf2` (SFO)
- `edge-node-lon1`, `edge-node-lon2` (London)
- `edge-node-fra1` (Frankfurt)
- `edge-node-sgp1` (Singapore)

### Cost Analysis

```
Cost Breakdown:
- Per Droplet: $6/month
- Total (8 droplets): $48/month
- GitHub Student Credit: $200
- Runtime Coverage: 4.16 months (~17 weeks)

After credit expires, consider:
- Reduce to 4 droplets ($24/month) for 8 months
- Reduce to 2 droplets ($12/month) for 16 months
- Use Azure $1000 credit for long-term proxies
```

## Deployment

### Prerequisites

1. **DigitalOcean Account** (via GitHub Student Pack)
   - Go to https://education.github.com/pack
   - Claim DigitalOcean offer ($200 credit)
   - Create DigitalOcean account

2. **Install doctl CLI**
   ```bash
   # On Ubuntu/Debian
   snap install doctl
   
   # On macOS
   brew install doctl
   
   # On Windows (WSL)
   sudo snap install doctl
   ```

3. **Authenticate doctl**
   ```bash
   doctl auth init
   # Paste your DigitalOcean API token when prompted
   # Get token from: https://cloud.digitalocean.com/account/api/tokens
   ```

### Deployment Script

```bash
cd ~/Repositories/cryptobot
chmod +x deploy/deploy_digitalocean_proxies.sh
./deploy/deploy_digitalocean_proxies.sh
```

**What it does:**
1. Validates doctl authentication
2. Creates/uploads SSH key for access
3. Deploys 8 droplets in parallel (sequential fallback if parallel fails)
4. Configures Tinyproxy via cloud-init:
   - Installs Tinyproxy
   - Configures port 8888
   - Sets firewall to allow DevNode01 IP only
   - Disables ViaHeader for stealth
5. Collects public IPs
6. Writes to `config/digitalocean_proxies.txt`

**Expected output:**
```
╔══════════════════════════════════════════════════════════════╗
║   DigitalOcean Proxy Infrastructure Deployment               ║
║   8 Droplets across 5 regions | $200 Student credit        ║
╚══════════════════════════════════════════════════════════════╝

[1/6] Checking doctl CLI installation...
✓ doctl found

[2/6] Checking DigitalOcean authentication...
✓ Authenticated as: your.email@example.com

[3/6] Setting up SSH keys...
✓ SSH key already exists

[4/6] Deploying 8 proxy droplets (~3 minutes)...
  Regions: NYC (2), SFO (2), LON (2), FRA (1), SGP (1)

  → Creating edge-node-ny1 in nyc3...
  ✓ Created droplet ID: 123456789
  ... (6 more droplets)

[5/6] Waiting for droplets to become active...

[6/6] Collecting proxy IPs...
  ✓ edge-node-ny1: http://1.2.3.4:8888
  ✓ edge-node-ny2: http://1.2.3.5:8888
  ... (6 more proxies)

╔══════════════════════════════════════════════════════════════╗
║                  Deployment Complete!                        ║
╚══════════════════════════════════════════════════════════════╝

Proxy list: config/digitalocean_proxies.txt
Proxy count: 8

Monthly cost: $48 (8 droplets × $6/month)
Credit remaining: $152 from $200 GitHub Student Pack
```

## Testing

### Health Check Script

```bash
./deploy/test_digitalocean_proxies.sh
```

**Tests performed:**
1. **Google Connectivity**: Measures latency to google.com through each proxy
2. **Cloudflare Bypass**: Tests access to `autofaucet.dutchycorp.space` (Cloudflare-protected)

**Expected output:**
```
╔══════════════════════════════════════════════════════════════╗
║         DigitalOcean Proxy Health Check                      ║
╚══════════════════════════════════════════════════════════════╝

Testing 8 proxies...

Testing: http://1.2.3.4:8888
  → Google connectivity... ✓ 245ms
  → Cloudflare bypass... ✓ Status: 200

Testing: http://1.2.3.5:8888
  → Google connectivity... ✓ 312ms
  → Cloudflare bypass... ✓ Status: 200

... (6 more proxies)

╔══════════════════════════════════════════════════════════════╗
║                    Test Summary                              ║
╚══════════════════════════════════════════════════════════════╝

✓ Passed: 8 / 8
✗ Failed: 0 / 8

All proxies operational! Ready for deployment.
```

### Manual Testing

```bash
# Test single proxy
curl -x http://PROXY_IP:8888 https://www.google.com
curl -x http://PROXY_IP:8888 https://autofaucet.dutchycorp.space

# Check Tinyproxy status
doctl compute ssh edge-node-ny1
sudo systemctl status tinyproxy
sudo tail -f /var/log/tinyproxy/tinyproxy.log
```

## Integration

### Update Application Configuration

1. **Edit `.env` on DevNode01:**
   ```bash
   USE_DIGITALOCEAN_PROXIES=true
   USE_AZURE_PROXIES=false
   USE_2CAPTCHA_PROXIES=false
   ```

2. **Deploy updated code:**
   ```bash
   cd ~/Repositories/cryptobot
   git pull origin master
   ```

3. **Copy proxy list to DevNode01:**
   ```bash
   # From local machine
   scp config/digitalocean_proxies.txt azureuser@4.155.230.212:~/Repositories/cryptobot/config/
   ```

4. **Restart service:**
   ```bash
   ssh azureuser@4.155.230.212
   cd ~/Repositories/cryptobot
   sudo systemctl restart faucet_worker
   sudo systemctl status faucet_worker
   ```

5. **Monitor logs:**
   ```bash
   sudo journalctl -u faucet_worker -f
   # Look for: "[DIGITALOCEAN] Using DigitalOcean Droplet proxies for stealth and Cloudflare bypass"
   ```

### Proxy Manager Integration

The `ProxyManager` in [core/proxy_manager.py](core/proxy_manager.py) automatically handles DigitalOcean proxies with priority:

**Proxy Selection Priority:**
1. DigitalOcean Droplets (if `USE_DIGITALOCEAN_PROXIES=true`)
2. Azure VMs (if `USE_AZURE_PROXIES=true`)
3. 2Captcha residential (default)

**Code:**
```python
if use_digitalocean:
    file_path = self.settings.digitalocean_proxies_file
    logger.info("[DIGITALOCEAN] Using DigitalOcean Droplet proxies for stealth and Cloudflare bypass")
elif use_azure:
    file_path = self.settings.azure_proxies_file
    logger.info("[AZURE] Using Azure VM proxies for stealth and Cloudflare bypass")
else:
    file_path = self.settings.residential_proxies_file
```

## Maintenance

### View Droplets

```bash
doctl compute droplet list
```

### SSH Access

```bash
doctl compute ssh edge-node-ny1
```

### Check Proxy Logs

```bash
doctl compute ssh edge-node-ny1
sudo tail -f /var/log/tinyproxy/tinyproxy.log
```

### Update Firewall Rules

```bash
doctl compute ssh edge-node-ny1
sudo ufw status
sudo ufw allow from NEW_IP to any port 8888
sudo ufw reload
```

### Destroy Droplets (Cleanup)

```bash
# Delete single droplet
doctl compute droplet delete edge-node-ny1 --force

# Delete all proxy droplets
for name in edge-node-{ny1,ny2,sf1,sf2,lon1,lon2,fra1,sgp1}; do
    doctl compute droplet delete $name --force
done
```

## Monitoring

### DigitalOcean Dashboard

- **URL**: https://cloud.digitalocean.com/
- **Metrics**: CPU, bandwidth, disk I/O
- **Alerts**: Set up email alerts for high CPU/bandwidth

### Local Health Monitoring

```bash
# Run health check every hour
crontab -e
# Add: 0 * * * * /path/to/cryptobot/deploy/test_digitalocean_proxies.sh >> /var/log/proxy-health.log 2>&1
```

### Bandwidth Usage

Each droplet gets **1TB outbound transfer/month**:
- Proxy requests: ~1-5KB average per request
- Estimated capacity: 200M-1B requests/month per droplet
- **Total capacity**: 1.6B - 8B requests/month across 8 droplets
- **More than sufficient** for faucet bot usage

## Troubleshooting

### Droplet Creation Fails

**Error**: "Error creating droplet: unable to create: region unavailable"

**Solution**: Change region in deployment script:
```bash
# Edit deploy/deploy_digitalocean_proxies.sh
REGION_1="nyc1"  # Try different NYC region
```

### Proxy Connection Timeout

**Error**: `curl: (28) Connection timed out after 10001 milliseconds`

**Possible causes:**
1. Firewall blocking DevNode01 IP
2. Tinyproxy not running
3. Cloud-init script didn't complete

**Debug:**
```bash
doctl compute ssh edge-node-ny1

# Check Tinyproxy status
sudo systemctl status tinyproxy

# Check firewall
sudo ufw status

# Check cloud-init logs
sudo cat /var/log/cloud-init-output.log

# Restart Tinyproxy
sudo systemctl restart tinyproxy
```

### Cloudflare Still Blocking (403)

**Possible causes:**
1. IP already flagged (unlikely for new droplets)
2. Need to rotate to different region
3. Need to add more droplets

**Solutions:**
```bash
# Destroy flagged droplet
doctl compute droplet delete edge-node-ny1 --force

# Recreate in different region
doctl compute droplet create edge-node-ny1 \
    --region sfo3 \  # Changed from nyc3
    --size s-1vcpu-1gb \
    --image ubuntu-22-04-x64 \
    --ssh-keys YOUR_KEY_ID \
    --user-data-file /tmp/digitalocean-cloud-init.sh
```

## Cost Optimization

### Current Configuration (4 months)

- 8 droplets × $6/month = $48/month
- $200 credit / $48 = 4.16 months

### Extended Runtime Options

1. **Reduce to 4 droplets (8 months)**
   - Keep 2 regions (NYC, SFO)
   - 2 droplets per region
   - Cost: $24/month
   - Runtime: 8.3 months

2. **Reduce to 2 droplets (16 months)**
   - Keep NYC only
   - 2 droplets for redundancy
   - Cost: $12/month
   - Runtime: 16.6 months

3. **Single droplet (33 months)**
   - Minimal redundancy
   - Cost: $6/month
   - Runtime: 33 months

4. **Switch to Azure VMs**
   - Use $1000 Azure credit
   - Standard_B2pts_v2 (ARM64) with ARM64 Ubuntu
   - ~24 months coverage

## Security

### Firewall Configuration

- **UFW enabled** on all droplets
- **Port 8888**: Restricted to DevNode01 IP (4.155.230.212)
- **Port 22**: Allowed for SSH management
- **All other ports**: Blocked by default

### SSH Key Management

- RSA 4096-bit key auto-generated if not exists
- Public key uploaded to DigitalOcean
- Private key stored at `~/.ssh/id_rsa`
- **Backup private key securely**

### Proxy Authentication

- **No password authentication** (IP-based restriction only)
- **Stealth configuration**: ViaHeader disabled
- **Logging**: Minimal logging to `/var/log/tinyproxy/tinyproxy.log`

## References

- **DigitalOcean Docs**: https://docs.digitalocean.com/
- **doctl CLI**: https://docs.digitalocean.com/reference/doctl/
- **Tinyproxy**: https://tinyproxy.github.io/
- **GitHub Student Pack**: https://education.github.com/pack
- **Architecture Design**: [deploy/digitalocean_proxy_architecture.json](deploy/digitalocean_proxy_architecture.json)
- **Deployment Script**: [deploy/deploy_digitalocean_proxies.sh](deploy/deploy_digitalocean_proxies.sh)
- **Health Check Script**: [deploy/test_digitalocean_proxies.sh](deploy/test_digitalocean_proxies.sh)

---

**Next Steps:**
1. Install and authenticate `doctl` CLI
2. Run `./deploy/deploy_digitalocean_proxies.sh`
3. Test proxies with `./deploy/test_digitalocean_proxies.sh`
4. Deploy to DevNode01 and configure `.env`
5. Monitor logs for successful Cloudflare bypass
