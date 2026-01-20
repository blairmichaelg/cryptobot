$ErrorActionPreference = "Stop"

$VM_IP = "4.155.230.212"
$USER = "azureuser"
$KEY_PATH = "$env:USERPROFILE\.ssh\id_rsa"
$SOURCE = "c:\Users\azureuser\Repositories\cryptobot"
$DEST_ZIP = "c:\Users\azureuser\Repositories\cryptobot\bundle.zip"

Write-Host "--- Packaging Service ---"
if (Test-Path $DEST_ZIP) { Remove-Item $DEST_ZIP }
# Use tar to exclude venv and hidden files/directories generally, but include everything else
cmd /c "tar -acvf bundle.zip --exclude=venv --exclude=.venv --exclude=__pycache__ --exclude=.git *"

Write-Host "--- Uploading to Azure VM ($VM_IP) ---"
# Note: Using strict host key checking=no to avoid prompt on first connect
scp -o StrictHostKeyChecking=no -i $KEY_PATH $DEST_ZIP "${USER}@${VM_IP}:~/bundle.zip"
scp -o StrictHostKeyChecking=no -i $KEY_PATH "$SOURCE\scripts\setup_remote.sh" "${USER}@${VM_IP}:~/setup_remote.sh"
scp -o StrictHostKeyChecking=no -i $KEY_PATH "$SOURCE\deploy\cryptobot.service" "${USER}@${VM_IP}:~/cryptobot.service"
scp -o StrictHostKeyChecking=no -i $KEY_PATH "$SOURCE\deploy\logrotate.conf" "${USER}@${VM_IP}:~/logrotate.conf"

Write-Host "--- Executing Remote Setup ---"
ssh -o StrictHostKeyChecking=no -i $KEY_PATH "${USER}@${VM_IP}" "chmod +x ~/setup_remote.sh && ./setup_remote.sh"

Write-Host "--- Deployment Finished ---"
