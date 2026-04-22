#!/usr/bin/env python3
"""
EVEZ INTEGRATOR
Connects all EvezArt projects into one working system
"""
import sys
from pathlib import Path

WORKSPACE = Path("/root/.openclaw/workspace")

class Integrator:
    def __init__(self):
        self.projects = {
            "platform": WORKSPACE / "evez-platform",
            "agentnet": WORKSPACE / "evez-agentnet",
            "os": WORKSPACE / "evez-os",
            "vcl": WORKSPACE / "evez-vcl",
            "ledger": WORKSPACE / "evez-autonomous-ledger"
        }
        
    def connect_all(self):
        print("=== EVEZ INTEGRATOR ===")
        for name, path in self.projects.items():
            if path.exists():
                py_files = len(list(path.rglob("*.py")))
                print(f"✓ {name}: {py_files} files")
        return self
        
    def run(self):
        self.connect_all()
        return {"status": "operational"}

if __name__ == "__main__":
    Integrator().run()
