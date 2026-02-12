#!/bin/bash
# Oracle Cloud VM Proxy Quick Setup
# Run this on each Oracle Cloud VM instance after creation

set -e

echo "🚀 Oracle Cloud Proxy Auto-Setup"
echo "=================================="
echo ""

# Generate strong random password
PROXY_PASSWORD=$(openssl rand -base64 16 | tr -d '/+=' | head -c 20)

echo "📦 Updating system..."
sudo apt update > /dev/null 2>&1 && echo "✅ System updated"

echo "📥 Installing packages..."
sudo apt install -y squid apache2-utils curl > /dev/null 2>&1 && echo "✅ Packages installed"

echo "💾 Configuring Squid..."
sudo tee /etc/squid/squid.conf > /dev/null <<'EOF'
http_port 8888
auth_param basic program /usr/lib/squid/basic_ncsa_auth /etc/squid/passwords
auth_param basic realm Proxy
auth_param basic credentialsttl 2 hours
acl authenticated proxy_auth REQUIRED
acl safe_ports port 80 443 8080
acl CONNECT method CONNECT
http_access deny !safe_ports
http_access deny CONNECT !safe_ports
http_access allow authenticated
http_access deny all
cache deny all
access_log /var/log/squid/access.log squid
EOF

echo "🔑 Creating authentication..."
sudo htpasswd -bc /etc/squid/passwords proxyuser "$PROXY_PASSWORD" > /dev/null
sudo chmod 640 /etc/squid/passwords
sudo chown proxy:proxy /etc/squid/passwords

echo "🔥 Configuring firewall..."
sudo ufw allow 22/tcp > /dev/null 2>&1
sudo ufw allow 8888/tcp > /dev/null 2>&1
echo "y" | sudo ufw enable > /dev/null 2>&1 || true

echo "🚀 Starting Squid..."
sudo systemctl restart squid
sudo systemctl enable squid > /dev/null 2>&1

# Get public IP
PUBLIC_IP=$(curl -s https://ifconfig.me || curl -s https://api.ipify.org)

# Test proxy
TEST_IP=$(curl -s -x "http://proxyuser:${PROXY_PASSWORD}@localhost:8888" https://ifconfig.me 2>/dev/null || echo "FAILED")

echo ""
echo "✅ Setup Complete!"
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "📋 PROXY DETAILS"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
echo "URL: http://proxyuser:${PROXY_PASSWORD}@${PUBLIC_IP}:8888"
echo ""
echo "Add this to your cryptobot VM:"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "echo 'http://proxyuser:${PROXY_PASSWORD}@${PUBLIC_IP}:8888' >> ~/Repositories/cryptobot/config/oracle_proxies.txt"
echo ""

if [ "$TEST_IP" == "$PUBLIC_IP" ]; then
    echo "✅ Proxy test: PASSED"
else
    echo "⚠️  Proxy test: Could not verify (may still work)"
fi

echo ""
echo "💾 SAVE THIS INFORMATION!"
echo "IP: $PUBLIC_IP"
echo "Password: $PROXY_PASSWORD"
echo ""
