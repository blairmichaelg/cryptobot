#!/bin/bash
export DEBIAN_FRONTEND=noninteractive

# Update and install Tinyproxy
apt-get update -qq
apt-get install -y tinyproxy

# Configure Tinyproxy for our use
cat > /etc/tinyproxy/tinyproxy.conf <<'TINYPROXY_EOF'
User tinyproxy
Group tinyproxy
Port 8888
Timeout 600
DefaultErrorFile "/usr/share/tinyproxy/default.html"
StatFile "/usr/share/tinyproxy/stats.html"
LogFile "/var/log/tinyproxy/tinyproxy.log"
LogLevel Info
PidFile "/run/tinyproxy/tinyproxy.pid"
MaxClients 100
MinSpareServers 5
MaxSpareServers 20
StartServers 10
MaxRequestsPerChild 0

# Allow DevNode01 Azure VM
Allow DEVNODE_IP_ACTUAL

# Disable ViaProxyName for stealth
DisableViaHeader Yes

# Filters
FilterURLs Off
FilterExtended Off

# Connection settings
ConnectPort 443
ConnectPort 563
TINYPROXY_EOF

# Replace placeholder with actual IP
sed -i "s/DEVNODE_IP_ACTUAL/4.155.230.212/g" /etc/tinyproxy/tinyproxy.conf

# Configure UFW firewall
ufw --force enable
ufw allow from 4.155.230.212 to any port 8888
ufw allow ssh

# Restart Tinyproxy
systemctl restart tinyproxy
systemctl enable tinyproxy

# Install curl for health checks
apt-get install -y curl

echo "Proxy setup complete on port 8888"
