#!/bin/bash
# EVEZ Platform — Install & Run
set -e

echo "⚡ EVEZ Platform installer"
echo "========================="

cd "$(dirname "$0")"

# Install Python dependencies
echo "[1/3] Installing Python dependencies..."
pip install -q -r requirements.txt 2>&1 | tail -5

# Create data directory
echo "[2/3] Setting up data directory..."
mkdir -p data

# Check Ollama
echo "[3/3] Checking for Ollama..."
if command -v ollama &>/dev/null; then
    echo "  ✅ Ollama found — local models available"
    echo "  💡 Run 'ollama pull llama3.2' to get a free model"
else
    echo "  ⚠️  Ollama not found — will use cloud API"
    echo "  💡 Install with: curl -fsSL https://ollama.ai/install.sh | sh"
fi

echo ""
echo "⚡ Starting EVEZ Platform on http://localhost:8080"
echo "   Press Ctrl+C to stop"
echo ""

python3 main.py
