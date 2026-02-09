# Manual Deployment Instructions

The deployment script `deploy/azure_deploy.sh` failed to run in the current environment (likely due to missing `az` CLI or `wsl` environment).

Please perform the following steps to deploy the changes to the Azure VM:

## 1. Local Commit (Required)
I was unable to commit changes due to shell environment errors (`pty.node`). You MUST commit the local changes first:

```bash
# Verify the changes I made
git status

# Commit them
git add .
git commit -m "Optimize DutchyCorp, FreeBitcoin, and standardize architecture"
```

## 2. Push & Deploy
Once committed, push to the remote and deploy to Azure:

```bash
# Push to master
git push origin master

# Deploy using the script (if Azure CLI is installed)
./deploy/azure_deploy.sh --resource-group APPSERVRG --vm-name DevNode01
```

**OR** run manually via SSH:

```bash
# SSH into the VM
ssh azureuser@4.155.230.212

# Update the codebase
cd ~/Repositories/cryptobot
git pull origin master

# Update systemd service (if changed)
sudo cp deploy/faucet_worker.service /etc/systemd/system/
sudo systemctl daemon-reload

# Restart the service
sudo systemctl restart faucet_worker

# Verify status
sudo systemctl status faucet_worker
tail -f logs/faucet_bot.log
```

## 3. Verify
Check the logs to confirm the bot is running and successfully claiming from the updated faucets (especially FreeBitcoin and DutchyCorp).
