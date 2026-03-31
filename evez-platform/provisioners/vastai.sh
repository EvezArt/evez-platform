#!/bin/bash
set -e
echo "EVEZ Vast.ai GPU Provisioner"
cd /workspace
git clone https://github.com/EvezArt/evez-platform.git || true
cd evez-platform
pip install -r requirements.txt
curl -fsSL https://ollama.ai/install.sh | sh
ollama serve &
sleep 3 && ollama pull llama3.2
export EVEZ_PORT=8080
python3 main.py &
echo "EVEZ Vast.ai node online"
