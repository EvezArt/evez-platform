#!/usr/bin/env python3
from __future__ import annotations

import os
import re
import sys
import time
from typing import Any, Dict, Optional, Tuple

from bus import ActionBus
from executor import Executor
from gateway import GatewayClient
from orchestrator import Orchestrator
from producers import emit_error_pattern, emit_health_probe, emit_revenue_opportunity
from store import EventStore
from models import Event

GATEWAY_HOST = os.environ.get("GATEWAY_HOST", "localhost")
GATEWAY_PORT = int(os.environ.get("GATEWAY_PORT", "8888"))
AGENT_TOKEN = os.environ.get("AGENT_TOKEN", "devtoken")
DEFAULT_NODE = os.environ.get("AGENT_NODE", "")
DB_PATH = os.environ.get("AGENT_DB", os.path.join(os.path.dirname(__file__), ".openclaw_agent.db"))
BASE_URL = f"http://{GATEWAY_HOST}:{GATEWAY_PORT}"

_TTY = sys.stdout.isatty()

def _c(code: str, text: str) -> str:
    return f"\033[{code}m{text}\033[0m" if _TTY else text

def green(t): return _c("32", t)
def red(t): return _c("31", t)
def yellow(t): return _c("33", t)
def blue(t): return _c("34", t)
def cyan(t): return _c("36", t)
def bold(t): return _c("1", t)
def dim(t): return _c("2", t)


def _out_ok(title: str, data: Optional[Dict[str, Any]] = None) -> None:
    print(f"\n  {green('✓')}  {bold(title)}")
    if data:
        for k, v in data.items():
            print(f"  {dim(f'{k:<14}')} {v}")


def _out_error(msg: str) -> None:
    print(f"\n  {red('✗')}  {bold(msg)}")


def _out_info(msg: str) -> None:
    print(f"\n  {blue('·')}  {msg}")


_RULES = [
    (r"\b(photo|picture|camera|capture|snapshot)\b", "camera.capture", None),
    (r"\b(screenshot|screen\s*capture|screen)\b", "screen.capture", None),
    (r"\b(where\s+am\s+i|location|gps|coords?|position)\b", "location.get", None),
    (r"\b(say|speak|tts|voice|announce)\s+(.+)", "speaker.speak", 2),
    (r"\b(listen|mic|microphone|hear|record)\b.*?(\d+)\s*s", "microphone.listen_n", 2),
    (r"\b(listen|mic|microphone|hear|record)\b", "microphone.listen", None),
    (r"\b(notify|notification|alert|ping)\s*:?(.*)", "notifications.send", 2),
    (r"\b(sys|system\s*info|device\s*info|info)\b", "system.info", None),
    (r"\brun\s*:?(.*)", "shell", 1),
    (r"\bexec(ute)?\s*:?(.*)", "shell", 2),
    (r"\bbash\s*:?(.*)", "shell", 1),
    (r"\b(verify|check\s+chain|chain\s+ok|integrity)\b", "verify", None),
    (r"\b(manifest|sign|export\s+manifest)\b", "manifest", None),
    (r"\b(pending|confirm\w*\s+list|show\s+pending)\b", "pending_list", None),
    (r"\bconfirm\s+(\S+)", "confirm", 1),
    (r"\breject\s+(\S+)", "reject", 1),
    (r"\b(nodes?|list\s+nodes?|who.s\s+connected)\b", "nodes", None),
    (r"\b(health|status|ping\s+server)\b", "health", None),
    (r"\b(history|log|events?)\b", "history", None),
    (r"\bhelp\b", "help", None),
]


def parse_intent(prompt: str) -> Tuple[str, Optional[str]]:
    text = prompt.strip()
    for pattern, action, group in _RULES:
        m = re.search(pattern, text, re.IGNORECASE)
        if m:
            arg = None
            if group is not None and group <= len(m.groups()):
                arg = m.group(group)
                if arg is not None:
                    arg = arg.strip()
            return action, arg
    return "unknown", text


def build_event(action: str, arg: Optional[str], prompt: str) -> Event:
    payload: Dict[str, Any] = {"prompt": prompt}
    if action in {"speaker.speak", "notifications.send", "shell", "confirm", "reject"} and arg is not None:
        if action == "speaker.speak":
            payload["text"] = arg
        elif action == "notifications.send":
            payload["body"] = arg
        elif action == "shell":
            payload["cmd"] = arg
        elif action in {"confirm", "reject"}:
            payload["action_id"] = arg
    elif action == "microphone.listen_n" and arg:
        try:
            payload["timeoutMs"] = int(arg) * 1000
        except ValueError:
            payload["timeoutMs"] = 8000
    return Event(source="cli", type=action, confidence=1.0, payload=payload)


def make_system() -> tuple[ActionBus, Orchestrator, EventStore]:
    store = EventStore(DB_PATH)
    bus = ActionBus(store)
    gateway = GatewayClient(GATEWAY_HOST, GATEWAY_PORT, AGENT_TOKEN)
    executor = Executor(gateway, store, default_node=DEFAULT_NODE)
    orchestrator = Orchestrator(bus, executor, store)
    bus.subscribe(orchestrator.handle)
    bus.start()
    return bus, orchestrator, store


def show_help() -> None:
    print(f"""
  {bold('OpenClaw + EVEZOS Agent')}
  {dim(f'Gateway: {BASE_URL}')}  {dim(f'DB: {DB_PATH}')}

  {cyan('Device commands')}
    take a photo
    where am i
    say hello world
    listen for 10 seconds
    screenshot
    send a notification: meeting in 5
    system info
    run: ls ~/Downloads

  {cyan('Chain / control')}
    verify
    manifest
    show pending
    confirm <action_id>
    reject <action_id>
    history
    nodes
    health

  {cyan('Special')}
    emit probe
    emit revenue
    emit error
    bridge
    help
    exit
""")


def run_command(bus: ActionBus, orchestrator: Orchestrator, store: EventStore, prompt: str) -> None:
    raw = prompt.strip()
    if not raw:
        return
    if raw.lower() == "help":
        show_help()
        return
    if raw.lower() == "emit probe":
        result = bus.request(emit_health_probe())
        _out_ok("Probe completed", result)
        return
    if raw.lower() == "emit revenue":
        result = bus.request(emit_revenue_opportunity())
        _out_ok("Revenue event handled", result)
        return
    if raw.lower() == "emit error":
        result = bus.request(emit_error_pattern())
        _out_ok("Error event handled", result)
        return

    action, arg = parse_intent(raw)
    event = build_event(action, arg, raw)

    if action == "help":
        show_help()
        return
    if action == "unknown":
        _out_info(f"Didn't understand: {raw!r}")
        print(dim("  Try: help"))
        return

    result = bus.request(event)

    if action == "health":
        if result.get("_unreachable"):
            _out_error(f"Gateway unreachable at {BASE_URL}")
        else:
            _out_ok("Gateway status", result)
        return
    if action == "nodes":
        _out_ok("Nodes / chain", result)
        return
    if action == "history":
        _out_ok("Recent chain events", {"count": len(result.get('last_50', []))})
        for rec in result.get("last_50", [])[:10]:
            print(f"  {dim(rec.get('type','?')):<22} {dim(rec.get('id','')[:10]+'…')}")
        return
    if action == "pending_list":
        pending = result.get("pending", [])
        if not pending:
            _out_info("No pending confirmations.")
            return
        _out_ok(f"{len(pending)} pending action(s)")
        for item in pending:
            print(f"  {bold(item.get('action_id','?'))}  {dim(item.get('payload',{}).get('action',{}).get('name','?'))}")
        return
    if action in {"verify", "manifest"}:
        _out_ok(action, result)
        return
    if action in {"confirm", "reject"}:
        _out_ok(action, result)
        return

    if result.get("status") == "quarantined":
        _out_info(f"Queued for confirmation: {result.get('action_id')}")
        return

    if result.get("ok") is False and result.get("error"):
        _out_error(result["error"])
        return

    _out_ok(f"Dispatched — {action}", result)


def repl() -> None:
    bus, orchestrator, store = make_system()
    print(f"\n  {bold('OpenClaw + EVEZOS Agent')}  {dim(f'→ {BASE_URL}')}")
    print(f"  {dim('Type help for commands. Ctrl-C or exit to stop.')}\n")
    while True:
        try:
            raw = input(f"  {cyan('agent')} {dim('›')} ").strip()
        except (EOFError, KeyboardInterrupt):
            print(f"\n  {dim('bye.')}\n")
            break
        if not raw:
            continue
        if raw.lower() in {"exit", "quit", "q"}:
            print(f"\n  {dim('bye.')}\n")
            break
        run_command(bus, orchestrator, store, raw)
        print()


def main() -> None:
    bus, orchestrator, store = make_system()
    if len(sys.argv) > 1:
        prompt = " ".join(sys.argv[1:])
        run_command(bus, orchestrator, store, prompt)
        print()
        return
    repl()


if __name__ == "__main__":
    main()
