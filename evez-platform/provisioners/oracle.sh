#!/bin/bash
set -e
echo "EVEZ Oracle Cloud Provisioner"
apt-get update && apt-get install -y python3 python3-pip git curl
cd /opt
git clone https://github.com/EvezArt/evez-platform.git 2>/dev/null || true
cd evez-platform
pip3 install --break-system-packages -r requirements.txt
cat > /etc/systemd/system/evez-platform.service << 'EOF'
[Unit]
Description=EVEZ Platform
After=network.target
[Service]
Type=simple
WorkingDirectory=/opt/evez-platform
ExecStart=/usr/bin/python3 main.py
Restart=always
Environment=EVEZ_PORT=8080
[Install]
WantedBy=multi-user.target
EOF
systemctl daemon-reload
systemctl enable --now evez-platform
echo "EVEZ Oracle node online"
