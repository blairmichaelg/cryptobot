#!/bin/bash
# Automated Oracle Cloud Squid Proxy Setup
# Run this on each new Oracle Cloud ARM instance

set -e

echo "🚀 Oracle Cloud Squid Proxy Setup"
echo "=================================="
echo ""

# Prompt for password
read -sp "Enter proxy password: " PROXY_PASSWORD
echo ""
read -sp "Confirm password: " PROXY_PASSWORD_CONFIRM
echo ""

if [ "$PROXY_PASSWORD" != "$PROXY_PASSWORD_CONFIRM" ]; then
    echo "❌ Passwords don't match!"
    exit 1
fi

echo "📦 Updating system..."
sudo apt update && sudo apt upgrade -y

echo "📥 Installing Squid and Apache Utils..."
sudo apt install -y squid apache2-utils

echo "💾 Backing up original config..."
sudo cp /etc/squid/squid.conf /etc/squid/squid.conf.backup

echo "⚙️ Creating Squid configuration..."
sudo tee /etc/squid/squid.conf > /dev/null <<'EOF'
# Squid Proxy Configuration for Cryptobot
http_port 8888

# Authentication
auth_param basic program /usr/lib/squid/basic_ncsa_auth /etc/squid/passwords
auth_param basic realm Proxy Authentication
auth_param basic credentialsttl 2 hours

# ACLs
acl authenticated proxy_auth REQUIRED
acl safe_ports port 80          # http
acl safe_ports port 443         # https
acl safe_ports port 8080        # http-alt
acl CONNECT method CONNECT

# Access rules
http_access deny !safe_ports
http_access deny CONNECT !safe_ports
http_access allow authenticated
http_access deny all

# Disable caching (we're a forward proxy)
cache deny all

# Logging
access_log /var/log/squid/access.log squid
cache_log /var/log/squid/cache.log

# Performance tuning
dns_nameservers 8.8.8.8 8.8.4.4
EOF

echo "🔑 Creating proxy user..."
sudo htpasswd -bc /etc/squid/passwords proxyuser "$PROXY_PASSWORD"

echo "🔒 Setting permissions..."
sudo chmod 640 /etc/squid/passwords
sudo chown proxy:proxy /etc/squid/passwords

echo "🔥 Configuring firewall..."
sudo ufw allow 22/tcp    # SSH
sudo ufw allow 8888/tcp  # Proxy
sudo ufw --force enable

echo "🚀 Starting Squid..."
sudo systemctl restart squid
sudo systemctl enable squid

echo ""
echo "✅ Setup complete!"
echo ""
echo "📊 Squid Status:"
sudo systemctl status squid --no-pager | head -n 10
echo ""

# Get public IP
PUBLIC_IP=$(curl -s https://ifconfig.me || curl -s https://api.ipify.org)

echo "🌍 Testing proxy..."
PROXY_URL="http://proxyuser:${PROXY_PASSWORD}@localhost:8888"
TEST_IP=$(curl -s -x "$PROXY_URL" https://ifconfig.me || echo "FAILED")

if [ "$TEST_IP" == "$PUBLIC_IP" ]; then
    echo "✅ Proxy is working correctly!"
    echo ""
    echo "📋 Proxy Details:"
    echo "================="
    echo "URL: http://proxyuser:****@${PUBLIC_IP}:8888"
    echo ""
    echo "Add this to your config/oracle_proxies.txt:"
    echo "http://proxyuser:${PROXY_PASSWORD}@${PUBLIC_IP}:8888"
    echo ""
else
    echo "⚠️  Proxy test failed. Check configuration."
    echo "Expected IP: $PUBLIC_IP"
    echo "Test result: $TEST_IP"
fi

echo ""
echo "📝 Next Steps:"
echo "1. Add the proxy URL to config/oracle_proxies.txt on your main VM"
echo "2. Merge with existing proxies: cat config/oracle_proxies.txt >> config/azure_proxies.txt"
echo "3. Restart faucet_worker: sudo systemctl restart faucet_worker"
echo ""
echo "🔧 Useful Commands:"
echo "- Check status: sudo systemctl status squid"
echo "- View logs: sudo tail -f /var/log/squid/access.log"
echo "- Restart: sudo systemctl restart squid"
echo ""
