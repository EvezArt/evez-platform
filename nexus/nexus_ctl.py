#!/usr/bin/env python3
"""
Nexus Control — CLI for managing the nexus daemon.

Usage:
    python3 nexus_ctl.py start [--interval 300] [--serve] [--port 8877]
    python3 nexus_ctl.py stop
    python3 nexus_ctl.py status
    python3 nexus_ctl.py chat "message" [--provider auto|chatgpt|perplexity|openclaw]
    python3 nexus_ctl.py research "query"
    python3 nexus_ctl.py config set chatgpt_api_key "sk-..."
    python3 nexus_ctl.py config set perplexity_api_key "pplx-..."
    python3 nexus_ctl.py config show
    python3 nexus_ctl.py logs [--tail 20]
    python3 nexus_ctl.py once [--provider auto]
"""

from __future__ import annotations

import asyncio
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path


WORKSPACE = Path("/root/.openclaw/workspace")
NEXUS_DIR = WORKSPACE / "nexus"
PID_FILE = NEXUS_DIR / "daemon.pid"
CONFIG_FILE = NEXUS_DIR / "config.json"
CHAT_QUEUE = NEXUS_DIR / "chat_queue.jsonl"
CHAT_OUTPUT = NEXUS_DIR / "chat_output.jsonl"
LOG_FILE = NEXUS_DIR / "daemon.log"
STATE_FILE = NEXUS_DIR / "daemon_state.json"


def cmd_start(args):
    """Start the nexus daemon."""
    if PID_FILE.exists():
        pid = PID_FILE.read_text().strip()
        if pid and os.path.exists(f"/proc/{pid}"):
            print(f"Nexus already running (PID {pid})")
            return

    NEXUS_DIR.mkdir(parents=True, exist_ok=True)

    cmd_args = [
        "python3", str(WORKSPACE / "nexus" / "nexus_daemon.py"),
        "--interval", str(args.get("interval", 300)),
    ]
    if args.get("serve"):
        cmd_args.append("--serve")
        cmd_args.extend(["--port", str(args.get("port", 8877))])

    proc = subprocess.Popen(
        cmd_args,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        cwd=str(WORKSPACE),
    )

    import time
    time.sleep(2)

    if PID_FILE.exists():
        pid = PID_FILE.read_text().strip()
        print(f"⚡ Nexus started (PID {pid})")
    else:
        print(f"⚡ Nexus starting... (process {proc.pid})")


def cmd_stop():
    """Stop the nexus daemon."""
    if not PID_FILE.exists():
        print("Nexus is not running")
        return

    pid = PID_FILE.read_text().strip()
    try:
        os.kill(int(pid), 15)  # SIGTERM
        print(f"⚡ Nexus stopped (PID {pid})")
    except ProcessLookupError:
        print(f"Process {pid} not found, cleaning up")
    finally:
        try:
            PID_FILE.unlink()
        except FileNotFoundError:
            pass


def cmd_status():
    """Show nexus status."""
    print("⚡ NEXUS STATUS")
    print("=" * 40)

    # Daemon status
    if PID_FILE.exists():
        pid = PID_FILE.read_text().strip()
        if os.path.exists(f"/proc/{pid}"):
            print(f"  Daemon: RUNNING (PID {pid})")
        else:
            print(f"  Daemon: STALE (PID {pid} not found)")
    else:
        print("  Daemon: STOPPED")

    # State
    if STATE_FILE.exists():
        try:
            state = json.loads(STATE_FILE.read_text())
            print(f"  Cycles: {state.get('total_cycles', 0)}")
            print(f"  Chats: {state.get('total_chats', 0)}")
            print(f"  Errors: {state.get('errors', 0)}")
            if state.get("last_cycle"):
                print(f"  Last cycle: {state['last_cycle'][:19]}")
        except (json.JSONDecodeError, IOError):
            pass

    # Config
    if CONFIG_FILE.exists():
        try:
            config = json.loads(CONFIG_FILE.read_text())
            providers = []
            if config.get("chatgpt_api_key"):
                providers.append("ChatGPT ✓")
            if config.get("perplexity_api_key"):
                providers.append("Perplexity ✓")
            providers.append("OpenClaw ✓ (local)")
            print(f"  Providers: {', '.join(providers)}")
        except (json.JSONDecodeError, IOError):
            print("  Providers: OpenClaw only (no API keys configured)")

    # Memory
    index_file = NEXUS_DIR / "memory" / "index.json"
    if index_file.exists():
        try:
            data = json.loads(index_file.read_text())
            entries = len(data.get("entries", {}))
            convs = len(data.get("conversations", {}))
            print(f"  Memory: {entries} entries, {convs} conversations")
        except (json.JSONDecodeError, IOError):
            pass


def cmd_chat(message: str, provider: str = "auto"):
    """Queue a chat message."""
    NEXUS_DIR.mkdir(parents=True, exist_ok=True)

    msg_data = {
        "message": message,
        "provider": provider,
        "conversation_id": "default",
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }

    with open(CHAT_QUEUE, "a") as f:
        f.write(json.dumps(msg_data) + "\n")

    print(f"📨 Queued: {message[:60]}...")
    print("   (will be processed on next daemon cycle)")

    # If daemon isn't running, process immediately
    if not PID_FILE.exists():
        print("   ⚡ Daemon not running — processing immediately...")
        subprocess.run(
            ["python3", str(WORKSPACE / "nexus" / "nexus_daemon.py"), "--once"],
            cwd=str(WORKSPACE),
        )

        # Show output
        if CHAT_OUTPUT.exists():
            lines = CHAT_OUTPUT.read_text().splitlines()
            if lines:
                last = json.loads(lines[-1])
                print(f"\n   Response [{last['provider']}]: {last['response']}")


def cmd_config(action: str, key: str = "", value: str = ""):
    """Manage nexus config."""
    config = {}
    if CONFIG_FILE.exists():
        try:
            config = json.loads(CONFIG_FILE.read_text())
        except (json.JSONDecodeError, IOError):
            pass

    if action == "set" and key:
        config[key] = value
        NEXUS_DIR.mkdir(parents=True, exist_ok=True)
        CONFIG_FILE.write_text(json.dumps(config, indent=2))
        print(f"✓ Set {key}")
    elif action == "show":
        print("⚡ NEXUS CONFIG")
        for k, v in config.items():
            if "key" in k.lower() and v:
                masked = v[:8] + "..." + v[-4:] if len(v) > 12 else "***"
                print(f"  {k}: {masked}")
            else:
                print(f"  {k}: {v}")


def cmd_logs(tail: int = 20):
    """Show daemon logs."""
    if LOG_FILE.exists():
        lines = LOG_FILE.read_text().splitlines()
        for line in lines[-tail:]:
            print(line)
    else:
        print("No logs found")


def cmd_once(provider: str = "auto"):
    """Run a single cycle."""
    subprocess.run(
        ["python3", str(WORKSPACE / "nexus" / "nexus_daemon.py"), "--once"],
        cwd=str(WORKSPACE),
    )


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        return

    cmd = sys.argv[1]

    if cmd == "start":
        args = {}
        i = 2
        while i < len(sys.argv):
            if sys.argv[i] == "--interval" and i + 1 < len(sys.argv):
                args["interval"] = int(sys.argv[i + 1])
                i += 2
            elif sys.argv[i] == "--serve":
                args["serve"] = True
                i += 1
            elif sys.argv[i] == "--port" and i + 1 < len(sys.argv):
                args["port"] = int(sys.argv[i + 1])
                i += 2
            else:
                i += 1
        cmd_start(args)

    elif cmd == "stop":
        cmd_stop()

    elif cmd == "status":
        cmd_status()

    elif cmd == "chat" and len(sys.argv) >= 3:
        provider = "auto"
        message_parts = []
        i = 2
        while i < len(sys.argv):
            if sys.argv[i] == "--provider" and i + 1 < len(sys.argv):
                provider = sys.argv[i + 1]
                i += 2
            else:
                message_parts.append(sys.argv[i])
                i += 1
        cmd_chat(" ".join(message_parts), provider)

    elif cmd == "research" and len(sys.argv) >= 3:
        cmd_chat(" ".join(sys.argv[2:]), "perplexity")

    elif cmd == "config":
        action = sys.argv[2] if len(sys.argv) > 2 else "show"
        key = sys.argv[3] if len(sys.argv) > 3 else ""
        value = sys.argv[4] if len(sys.argv) > 4 else ""
        cmd_config(action, key, value)

    elif cmd == "logs":
        tail = 20
        if "--tail" in sys.argv:
            idx = sys.argv.index("--tail")
            if idx + 1 < len(sys.argv):
                tail = int(sys.argv[idx + 1])
        cmd_logs(tail)

    elif cmd == "once":
        provider = "auto"
        if "--provider" in sys.argv:
            idx = sys.argv.index("--provider")
            if idx + 1 < len(sys.argv):
                provider = sys.argv[idx + 1]
        cmd_once(provider)

    else:
        print(f"Unknown command: {cmd}")
        print(__doc__)


if __name__ == "__main__":
    main()
