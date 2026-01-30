#!/bin/bash
# Optimize current VM for low-latency remote desktop

set -e

echo "🚀 Optimizing VM for remote desktop performance..."

# Check if running as root
if [ "$EUID" -ne 0 ]; then 
    echo "Please run with sudo"
    exit 1
fi

# Update system
echo "📦 Updating system packages..."
apt update
DEBIAN_FRONTEND=noninteractive apt upgrade -y

# Install desktop if not present (XFCE is lightweight)
if ! command -v xfce4-session &> /dev/null; then
    echo "🖥️  Installing XFCE desktop environment..."
    DEBIAN_FRONTEND=noninteractive apt install -y xfce4 xfce4-goodies
fi

# Install and optimize xRDP
echo "🔧 Installing and optimizing xRDP..."
DEBIAN_FRONTEND=noninteractive apt install -y xrdp
systemctl enable xrdp
adduser xrdp ssl-cert

# Optimize xRDP configuration for performance
cat > /etc/xrdp/xrdp.ini << 'EOF'
[Globals]
bitmap_cache=yes
bitmap_compression=yes
port=3389
crypt_level=low
channel_code=1
max_bpp=16
fork=yes
tcp_nodelay=yes

[xrdp1]
name=sesman-Xvnc
lib=libvnc.so
username=ask
password=ask
ip=127.0.0.1
port=-1
xserverbpp=16
EOF

# Set XFCE as default session
echo "xfce4-session" > /etc/skel/.xsession
for user in /home/*; do
    if [ -d "$user" ]; then
        username=$(basename "$user")
        echo "xfce4-session" > "$user/.xsession"
        chown $username:$username "$user/.xsession"
    fi
done

# Disable compositor for better performance
mkdir -p /etc/xdg/xfce4/xfconf/xfce-perchannel-xml
cat > /etc/xdg/xfce4/xfconf/xfce-perchannel-xml/xfwm4.xml << 'EOF'
<?xml version="1.0" encoding="UTF-8"?>
<channel name="xfwm4" version="1.0">
  <property name="general" type="empty">
    <property name="use_compositing" type="bool" value="false"/>
    <property name="frame_opacity" type="int" value="100"/>
  </property>
</channel>
EOF

# Install Parsec for better remote desktop performance
echo "🎮 Installing Parsec (gaming-grade remote desktop)..."
cd /tmp
wget -q https://builds.parsec.app/package/parsec-linux.deb
dpkg -i parsec-linux.deb || apt-get install -f -y
rm parsec-linux.deb

# Install essential tools
echo "🛠️  Installing development tools..."
DEBIAN_FRONTEND=noninteractive apt install -y \
    git \
    python3-pip \
    python3-venv \
    build-essential \
    curl \
    wget \
    htop \
    firefox \
    vim \
    net-tools

# Optimize network settings for low latency
echo "🌐 Optimizing network settings..."
cat >> /etc/sysctl.conf << 'EOF'

# Low-latency network optimizations
net.ipv4.tcp_fastopen=3
net.ipv4.tcp_low_latency=1
net.ipv4.tcp_timestamps=0
net.core.netdev_max_backlog=5000
net.ipv4.tcp_window_scaling=1
EOF

sysctl -p

# Restart xRDP with new settings
systemctl restart xrdp

echo ""
echo "✅ Optimization complete!"
echo ""
echo "📝 Next steps:"
echo "1. RDP Connection: Use the optimized .rdp file"
echo "2. Parsec Setup (recommended):"
echo "   - RDP in first"
echo "   - Open Firefox → parsec.app"
echo "   - Create free account"
echo "   - Install Parsec client on your laptop"
echo "   - Connect through Parsec (much faster than RDP)"
echo ""
