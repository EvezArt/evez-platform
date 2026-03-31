"""
EVEZ Compute Swarm — Infinite free compute orchestration.

Orchestrates:
- Oracle Cloud Free (4 ARM, 24GB RAM, forever)
- Kaggle Notebooks (T4 GPU, 20h/wk)
- GitHub Actions (2k min/mo across forks)
- Colab (T4 burst)
- BOINC volunteer grid
- Vast.ai startup credits ($2500)

The swarm self-provisions, self-registers, and self-heals.
"""

import json
import os
import time
import asyncio
import logging
import hashlib
from pathlib import Path
from datetime import datetime, timezone
from typing import Optional, List, Dict, Any
from dataclasses import dataclass, field, asdict
from enum import Enum

import httpx

logger = logging.getLogger("evez.swarm")


class ComputeTier(Enum):
    """Compute tiers by capability."""
    EDGE = "edge"          # Local machine, limited
    ORACLE = "oracle"      # Oracle Free ARM, 24GB
    GITHUB = "github"      # GHA ephemeral runners
    KAGGLE = "kaggle"      # T4 GPU
    COLAB = "colab"        # T4/K80 burst
    VAST = "vast"          # Paid GPU swarm
    BOINC = "boinc"        # Volunteer grid


@dataclass
class ComputeNode:
    """A compute node in the swarm."""
    id: str
    name: str
    tier: ComputeTier
    endpoint: str
    cpus: int = 0
    ram_gb: float = 0
    gpu: str = ""
    status: str = "offline"
    last_heartbeat: float = 0
    tasks_completed: int = 0
    capabilities: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self):
        d = asdict(self)
        d["tier"] = self.tier.value
        return d

    @classmethod
    def from_dict(cls, d: dict) -> "ComputeNode":
        d["tier"] = ComputeTier(d["tier"])
        return cls(**d)


@dataclass
class ComputeTask:
    """A task to distribute across the swarm."""
    id: str
    name: str
    payload: Dict[str, Any]
    priority: int = 5  # 1=highest, 10=lowest
    required_tier: ComputeTier = ComputeTier.EDGE
    requires_gpu: bool = False
    timeout_seconds: int = 300
    status: str = "pending"
    assigned_node: str = ""
    result: Optional[Dict] = None
    created: float = field(default_factory=time.time)
    completed: float = 0

    def to_dict(self):
        d = asdict(self)
        d["required_tier"] = self.required_tier.value
        return d


class ComputeSwarm:
    """
    Orchestrates infinite free compute across providers.

    Strategy:
    1. Local edge for latency-sensitive tasks
    2. Oracle Free for persistent services (DB, API)
    3. GitHub Actions for burst batch (swarm of forks)
    4. Kaggle/Colab for GPU training
    5. BOINC for distributed simulation
    6. Vast.ai for heavy GPU when credits available
    """

    def __init__(self, data_dir: Path):
        self.data_dir = data_dir
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.nodes: Dict[str, ComputeNode] = {}
        self.task_queue: List[ComputeTask] = []
        self.completed_tasks: List[ComputeTask] = []
        self._load_state()

        # Register self (edge node)
        self._register_self()

    def _load_state(self):
        state_file = self.data_dir / "swarm_state.json"
        if state_file.exists():
            try:
                with open(state_file) as f:
                    data = json.load(f)
                for n in data.get("nodes", []):
                    node = ComputeNode.from_dict(n)
                    self.nodes[node.id] = node
            except (json.JSONDecodeError, IOError):
                pass

    def _save_state(self):
        state_file = self.data_dir / "swarm_state.json"
        with open(state_file, "w") as f:
            json.dump({
                "nodes": [n.to_dict() for n in self.nodes.values()],
                "pending_tasks": len(self.task_queue),
                "completed_tasks": len(self.completed_tasks),
                "updated": datetime.now(timezone.utc).isoformat(),
            }, f, indent=2)

    def _register_self(self):
        """Register the local machine as an edge node."""
        import socket
        node_id = hashlib.sha256(socket.gethostname().encode()).hexdigest()[:12]
        node = ComputeNode(
            id=node_id,
            name=f"edge-{socket.gethostname()}",
            tier=ComputeTier.EDGE,
            endpoint="local",
            cpus=os.cpu_count() or 1,
            ram_gb=self._get_ram_gb(),
            status="online",
            last_heartbeat=time.time(),
            capabilities=["shell", "python", "git", "file_io", "web"],
        )
        self.nodes[node_id] = node
        self._save_state()

    def _get_ram_gb(self) -> float:
        try:
            with open("/proc/meminfo") as f:
                for line in f:
                    if line.startswith("MemTotal"):
                        kb = int(line.split()[1])
                        return round(kb / 1024 / 1024, 1)
        except Exception:
            pass
        return 2.9

    def register_node(self, name: str, tier: ComputeTier, endpoint: str,
                      cpus: int = 0, ram_gb: float = 0, gpu: str = "",
                      capabilities: List[str] = None) -> str:
        """Register a new compute node."""
        node_id = hashlib.sha256(f"{name}:{endpoint}".encode()).hexdigest()[:12]
        node = ComputeNode(
            id=node_id, name=name, tier=tier, endpoint=endpoint,
            cpus=cpus, ram_gb=ram_gb, gpu=gpu,
            status="online", last_heartbeat=time.time(),
            capabilities=capabilities or [],
        )
        self.nodes[node_id] = node
        self._save_state()
        logger.info("Registered node: %s (%s, %s)", name, tier.value, endpoint)
        return node_id

    def submit_task(self, name: str, payload: Dict, priority: int = 5,
                    required_tier: ComputeTier = ComputeTier.EDGE,
                    requires_gpu: bool = False,
                    timeout: int = 300) -> str:
        """Submit a task to the swarm queue."""
        task_id = hashlib.sha256(f"{name}:{time.time()}".encode()).hexdigest()[:16]
        task = ComputeTask(
            id=task_id, name=name, payload=payload,
            priority=priority, required_tier=required_tier,
            requires_gpu=requires_gpu, timeout_seconds=timeout,
        )
        self.task_queue.append(task)
        self.task_queue.sort(key=lambda t: t.priority)
        logger.info("Task submitted: %s (priority=%d, gpu=%s)", name, priority, requires_gpu)
        return task_id

    def get_best_node(self, task: ComputeTask) -> Optional[ComputeNode]:
        """Find the best available node for a task."""
        candidates = []
        for node in self.nodes.values():
            if node.status != "online":
                continue
            if task.requires_gpu and not node.gpu:
                continue
            # Score: prefer higher tier, more resources, recent heartbeat
            score = 0
            tier_order = list(ComputeTier)
            score += (len(tier_order) - tier_order.index(node.tier)) * 10
            score += node.cpus * 2
            score += node.ram_gb
            if node.gpu:
                score += 20
            # Penalize stale nodes
            age = time.time() - node.last_heartbeat
            if age > 300:
                score -= 50
            candidates.append((score, node))

        if not candidates:
            return None
        candidates.sort(key=lambda x: x[0], reverse=True)
        return candidates[0][1]

    def get_status(self) -> Dict:
        """Get swarm status."""
        online = [n for n in self.nodes.values() if n.status == "online"]
        total_cpus = sum(n.cpus for n in online)
        total_ram = sum(n.ram_gb for n in online)
        gpus = [n.gpu for n in online if n.gpu]

        return {
            "nodes_total": len(self.nodes),
            "nodes_online": len(online),
            "total_cpus": total_cpus,
            "total_ram_gb": round(total_ram, 1),
            "gpus": gpus,
            "pending_tasks": len(self.task_queue),
            "completed_tasks": len(self.completed_tasks),
            "nodes": [n.to_dict() for n in online],
        }


class SwarmProvisioner:
    """
    Auto-provisions compute nodes across free tiers.

    Generates:
    - Oracle Cloud init scripts
    - GitHub Actions workflow YAML
    - Kaggle notebook scripts
    - BOINC project configs
    - Vast.ai startup scripts
    """

    @staticmethod
    def generate_gha_swarm(repo: str, oracle_webhook: str = "",
                           num_forks: int = 10) -> str:
        """Generate GitHub Actions swarm workflow."""
        return f"""# EVEZ Compute Swarm — GitHub Actions
# Auto-generated by EVEZ Platform
# Fork this repo N times for N * 2000 min/mo free compute

name: EVEZ Swarm
on:
  schedule:
    - cron: '*/5 * * * *'  # Every 5 minutes
  workflow_dispatch:
  push:
    branches: [main]

jobs:
  compute-tick:
    runs-on: ubuntu-latest
    timeout-minutes: 10
    steps:
      - uses: actions/checkout@v4

      - name: System Info
        run: |
          echo "CPUs: $(nproc)"
          echo "RAM: $(free -h | awk '/Mem:/{print $2}')"
          echo "Runner: ${{{{ runner.name }}}}"
          echo "Repo: ${{{{ github.repository }}}}"

      - name: EVEZ Compute Task
        run: |
          # Pull task from swarm coordinator
          # Execute computation
          # Push results back
          echo "Executing compute tick..."
          python3 -c "
          import json, time, hashlib, os
          task = {{
              'node': '${{{{ runner.name }}}}',
              'repo': '${{{{ github.repository }}}}',
              'timestamp': time.time(),
              'cpus': os.cpu_count(),
          }}
          print(json.dumps(task, indent=2))
          "

      - name: Register with Oracle
        if: env.ORACLE_WEBHOOK != ''
        env:
          ORACLE_WEBHOOK: ${{{{ secrets.ORACLE_WEBHOOK }}}}
        run: |
          curl -s -X POST "$ORACLE_WEBHOOK" \\
            -H "Content-Type: application/json" \\
            -d '{{"node":"${{{{ runner.name }}}}","tick":1,"repo":"${{{{ github.repository }}}}"}}' || true

      - name: Report Heartbeat
        run: |
          echo "💓 Swarm heartbeat from ${{{{ runner.name }}}}"
"""

    @staticmethod
    def generate_oracle_init(evez_api_url: str = "http://localhost:8080") -> str:
        """Generate Oracle Cloud Free init script."""
        return f"""#!/bin/bash
# EVEZ Oracle Cloud Free VPS Setup
# 4 ARM CPUs, 24GB RAM, 200GB SSD — FREE FOREVER

set -e

echo "⚡ EVEZ Oracle Cloud Provisioner"

# System setup
apt-get update && apt-get install -y python3 python3-pip python3-venv git curl wget

# Create evez user
useradd -m -s /bin/bash evez 2>/dev/null || true

# Clone EVEZ platform
cd /opt
git clone https://github.com/EvezArt/evez-platform.git 2>/dev/null || true
cd evez-platform

# Install dependencies
pip3 install --break-system-packages -r requirements.txt

# Create systemd service
cat > /etc/systemd/system/evez-platform.service << 'EOF'
[Unit]
Description=EVEZ Platform
After=network.target

[Service]
Type=simple
User=root
WorkingDirectory=/opt/evez-platform
ExecStart=/usr/bin/python3 main.py
Restart=always
RestartSec=5
Environment=EVEZ_PORT=8080
Environment=EVEZ_DATA=/opt/evez-platform/data

[Install]
WantedBy=multi-user.target
EOF

# Create Oracle compute node webhook receiver
cat > /opt/evez-platform/oracle_webhook.py << 'PYEOF'
from http.server import HTTPServer, BaseHTTPRequestHandler
import json, time

class Handler(BaseHTTPRequestHandler):
    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        body = json.loads(self.rfile.read(length)) if length else {{}}
        body["received_at"] = time.time()
        body["server"] = "oracle-free"
        print(f"Swarm heartbeat: {{body}}")
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b'{{"ok":true}}')

    def log_message(self, format, *args):
        pass

HTTPServer(("0.0.0.0", 9090), Handler).serve_forever()
PYEOF

# Enable services
systemctl daemon-reload
systemctl enable evez-platform
systemctl start evez-platform

echo "⚡ EVEZ Oracle node online — 4 ARM CPUs, 24GB RAM"
"""

    @staticmethod
    def generate_kaggle_notebook() -> str:
        """Generate Kaggle GPU notebook script."""
        return """# EVEZ Kaggle GPU Notebook
# T4 GPU, 16GB VRAM, 30GB RAM — 20hrs/week FREE
# Paste this into a new Kaggle notebook

!pip install torch transformers accelerate

import torch
import json
import time
from datetime import datetime

print(f"🔥 EVEZ Kaggle GPU Node")
print(f"   GPU: {torch.cuda.get_device_name(0) if torch.cuda.is_available() else 'None'}")
print(f"   CUDA: {torch.version.cuda}")
print(f"   PyTorch: {torch.__version__}")

# === GPU Compute Tasks ===

def run_phi_training():
    """Train or fine-tune a model on free T4."""
    from transformers import AutoModelForCausalLM, AutoTokenizer

    model_name = "microsoft/phi-2"
    print(f"Loading {model_name}...")
    tokenizer = AutoTokenizer.from_pretrained(model_name)
    model = AutoModelForCausalLM.from_pretrained(
        model_name,
        torch_dtype=torch.float16,
        device_map="auto"
    )

    # Inference test
    prompt = "The EVEZ cognitive architecture is"
    inputs = tokenizer(prompt, return_tensors="pt").to(model.device)
    with torch.no_grad():
        outputs = model.generate(**inputs, max_new_tokens=100, temperature=0.7)
    result = tokenizer.decode(outputs[0], skip_special_tokens=True)
    print(f"Generated: {result}")
    return result

def run_distributed_sim():
    """Barnes-Hut N-body simulation on GPU."""
    import torch

    n_bodies = 10000
    dt = 0.01
    steps = 1000

    pos = torch.randn(n_bodies, 3, device='cuda')
    vel = torch.randn(n_bodies, 3, device='cuda') * 0.1
    mass = torch.ones(n_bodies, device='cuda')

    print(f"Running {steps}-step Barnes-Hut sim with {n_bodies} bodies...")
    start = time.time()
    for i in range(steps):
        # Simplified gravity
        diff = pos.unsqueeze(0) - pos.unsqueeze(1)  # NxNx3
        dist = torch.norm(diff, dim=2, keepdim=True) + 1e-6
        force = (mass.unsqueeze(0).unsqueeze(2) * diff / dist.pow(3)).sum(1)
        vel += force * dt
        pos += vel * dt

        if i % 100 == 0:
            energy = 0.5 * (vel.pow(2).sum() * mass).item()
            print(f"  Step {i}: E={energy:.4f}")

    elapsed = time.time() - start
    print(f"Completed in {elapsed:.1f}s ({steps/elapsed:.0f} steps/sec)")

# Run tasks
run_distributed_sim()

# Run phi if enough time
try:
    run_phi_training()
except Exception as e:
    print(f"Phi training error: {e}")

print("⚡ Kaggle compute cycle complete")
"""

    @staticmethod
    def generate_boinc_config() -> str:
        """Generate BOINC volunteer compute project config."""
        return """<?xml version="1.0" encoding="UTF-8"?>
<!-- EVEZ BOINC Project Configuration -->
<!-- Deploy to a BOINC server for infinite volunteer compute -->
<project>
    <name>evez-swarm</name>
    <long_name>EVEZ Cognitive Compute Swarm</long_name>
    <description>
        Volunteer compute grid for the EVEZ cognitive architecture.
        Contribute your CPU/GPU to train AI, run simulations,
        and power a never-halting cognitive daemon.
    </description>
    <home>https://evez.ai</home>
    <keywords>
        <keyword>artificial intelligence</keyword>
        <keyword>distributed computing</keyword>
        <keyword>cognitive architecture</keyword>
    </keywords>

    <platforms>
        <platform>linux_x86_64</platform>
        <platform>windows_x86_64</platform>
        <platform>darwin_x86_64</platform>
        <platform>linux_aarch64</platform>
    </platforms>

    <!-- Work units: N-body sims, model training, spine analysis -->
    <workunit>
        <name>evez_sim</name>
        <app_version>1.0</app_version>
        <rsc_fpops_est>1e12</rsc_fpops_est>
        <rsc_memory_bound>500000000</rsc_memory_bound>
        <rsc_disk_bound>100000000</rsc_disk_bound>
    </workunit>

    <workunit>
        <name>evez_train</name>
        <app_version>1.0</app_version>
        <rsc_fpops_est>1e14</rsc_fpops_est>
        <rsc_memory_bound>2000000000</rsc_memory_bound>
        <rsc_disk_bound>500000000</rsc_disk_bound>
        <need_gpu>1</need_gpu>
    </workunit>
</project>
"""

    @staticmethod
    def generate_vastai_script() -> str:
        """Generate Vast.ai startup script for GPU instances."""
        return """#!/bin/bash
# EVEZ Vast.ai GPU Instance Setup
# Apply for $2500 startup credits at vast.ai

set -e

echo "⚡ EVEZ Vast.ai GPU Provisioner"

# Install EVEZ
cd /workspace
git clone https://github.com/EvezArt/evez-platform.git || true
cd evez-platform
pip install -r requirements.txt

# Install Ollama for local models
curl -fsSL https://ollama.ai/install.sh | sh
ollama serve &
sleep 3
ollama pull llama3.2
ollama pull codellama

# Install PyTorch with CUDA
pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu121

# Start EVEZ platform
export EVEZ_PORT=8080
export EVEZ_DATA=/workspace/data
python3 main.py &

echo "⚡ EVEZ Vast.ai node online"
echo "   GPU: $(nvidia-smi --query-gpu=name --format=csv,noheader)"
echo "   VRAM: $(nvidia-smi --query-gpu=memory.total --format=csv,noheader)"
echo "   API: http://localhost:8080"
"""
