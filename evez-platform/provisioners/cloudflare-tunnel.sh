#!/bin/bash
# EVEZ Cloudflare Tunnel — Expose platform to the internet for free
# Uses cloudflared (Cloudflare's free tunnel daemon)
# No port forwarding, no static IP, no cost

set -e

echo "⚡ EVEZ Cloudflare Tunnel Setup"

# Install cloudflared
if ! command -v cloudflared &>/dev/null; then
    echo "Installing cloudflared..."
    curl -fsSL https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64 -o /usr/local/bin/cloudflared
    chmod +x /usr/local/bin/cloudflared
fi

# Check for existing tunnel
TUNNEL_NAME="evez-platform"

echo ""
echo "To create a tunnel:"
echo "  1. cloudflared tunnel login"
echo "  2. cloudflared tunnel create $TUNNEL_NAME"
echo "  3. cloudflared tunnel route dns $TUNNEL_NAME evez.yourdomain.com"
echo ""
echo "Then run:"
echo "  cloudflared tunnel run --url http://localhost:8080 $TUNNEL_NAME"
echo ""
echo "Or use quick tunnel (no login, temporary URL):"
echo "  cloudflared tunnel --url http://localhost:8080"
echo ""
echo "Starting quick tunnel..."
cloudflared tunnel --url http://localhost:8080 2>&1 &
TUNNEL_PID=$!

echo "⚡ Tunnel started (PID: $TUNNEL_PID)"
echo "   Check cloudflared output for the .trycloudflare.com URL"
echo "   Press Ctrl+C to stop"

wait $TUNNEL_PID
