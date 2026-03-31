#!/bin/bash
# EVEZ Self-Boot — Paste this on any fresh Linux machine
set -e
echo "⚡ EVEZ Self-Boot"

# Install prerequisites
apt-get update -qq && apt-get install -y -qq python3 python3-pip python3-venv git curl

# Clone workspace
WORKSPACE="/root/.openclaw/workspace"
mkdir -p "$WORKSPACE"
cd "$WORKSPACE"

# If bundle exists, extract it
if [ -f /tmp/evez-bundle.tar.gz ]; then
    tar xzf /tmp/evez-bundle.tar.gz -C "$WORKSPACE"
    echo "Extracted from bundle"
fi

# Install platform dependencies
cd "$WORKSPACE/evez-platform"
pip3 install --break-system-packages -q -r requirements.txt 2>/dev/null

# Optional: Install Ollama
if ! command -v ollama &>/dev/null; then
    curl -fsSL https://ollama.ai/install.sh | sh
    ollama serve &
    sleep 3
    ollama pull llama3.2 2>/dev/null || true
fi

# Create systemd service
cat > /etc/systemd/system/evez.service << 'EOF'
[Unit]
Description=EVEZ Platform
After=network.target
[Service]
Type=simple
WorkingDirectory=/root/.openclaw/workspace/evez-platform
ExecStart=/usr/bin/python3 main.py
Restart=always
RestartSec=5
Environment=EVEZ_PORT=8080
Environment=EVEZ_DATA=/root/.openclaw/workspace/evez-platform/data
[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable --now evez

echo "⚡ EVEZ online at http://$(hostname -I | awk '{print $1}'):8080"
