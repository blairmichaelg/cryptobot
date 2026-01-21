
# Deploy to Azure VM
# Usage: ./deploy_vm.ps1 -VmIp "1.2.3.4" -SshKey "path/to/key.pem"

param(
    [string]$VmIp,
    [string]$SshKey = "~/.ssh/id_rsa",
    [string]$RemoteUser = "azureuser"
)

$RemotePath = "/home/$RemoteUser/Repositories/cryptobot"

Write-Host "Deploying to $RemoteUser@$VmIp..."

# 1. Sync Files
# Requires scp (OpenSSH) available in PowerShell
scp -i $SshKey -r core browser config deploy faucets solvers scripts main.py meta.py requirements.txt setup.py "$RemoteUser@$VmIp`:$RemotePath"

# 2. Update Remote
ssh -i $SshKey $RemoteUser@$VmIp "cd $RemotePath && python3 -m venv .venv && source .venv/bin/activate && pip install -r requirements.txt"

# 3. Restart Service
ssh -i $SshKey $RemoteUser@$VmIp "sudo cp $RemotePath/deploy/faucet_worker.service /etc/systemd/system/ && sudo systemctl daemon-reload && sudo systemctl restart faucet_worker"

# 4. Post-Deployment Health Check
Write-Host "Verifying deployment..."
ssh -i $SshKey $RemoteUser@$VmIp "if [ ! -f $RemotePath/.env ]; then echo '⚠️ WARNING: .env file missing on remote!'; fi"
ssh -i $SshKey $RemoteUser@$VmIp "sleep 5 && sudo systemctl is-active faucet_worker"

Write-Host "Deployment Complete!"
