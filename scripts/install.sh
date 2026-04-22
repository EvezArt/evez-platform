#!/bin/bash
set -e

echo "Installing EVEZ Platform..."

# Check Docker
if ! command -v docker &> /dev/null; then
    echo "Installing Docker..."
    curl -fsSL https://get.docker.com | sh
fi

# Start Redis
echo "Starting Redis..."
docker run -d --name evez-redis -p 6379:6379 redis:7-alpine

# Start API
echo "Starting API Gateway..."
cd "$(dirname "$0")"
python3 api/main.py &

# Start Control Plane
echo "Starting Control Plane..."
python3 control_plane/orchestrator.py &

# Start Worker
echo "Starting Worker..."
python3 workers/task_runner.py &

echo "EVEZ Platform deployed!"
echo "API: http://localhost:8000"
echo "Health: curl http://localhost:8000/health"
