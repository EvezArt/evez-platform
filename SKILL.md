---
name: openclaw-evezos-agent
version: 2.0.0
description: Persistent Action Bus + Orchestrator for OpenClaw + EVEZOS. Supports device commands, chain operations, quarantine and confirmation, durable event storage, idempotent execution, optional bridge access, and a synchronous request/reply path for one-shot commands.
---

# OpenClaw + EVEZOS Agent

This version replaces the single-regex dispatcher with a persistent event system.

## Architecture

- Producers emit typed events.
- The Action Bus persists events and routes them to subscribers.
- The Orchestrator resolves rules, enforces risk gating, executes actions, verifies outcomes, and records learning data.
- The Event Store uses SQLite for durability and idempotency.
- The Gateway Client signs requests and talks to the OpenClaw API.
- The Local File Bridge is optional and restricted to a configured root directory.

## Usage

Interactive:

```bash
python3 agent.py
```

One-shot:

```bash
python3 agent.py "take a photo"
python3 agent.py "verify"
python3 agent.py "show pending"
```

## Environment

- `GATEWAY_HOST` — gateway host, default `localhost`
- `GATEWAY_PORT` — gateway port, default `8888`
- `AGENT_TOKEN` — controller token, default `devtoken`
- `AGENT_NODE` — default target node ID, empty means auto-pick
- `AGENT_DB` — SQLite database path, default `.openclaw_agent.db`
- `ACTION_BUS_BACKEND` — `memory` or `sqlite`
- `FILE_BRIDGE_ROOT` — root directory for the optional file bridge
- `FILE_BRIDGE_WRITE` — `1` to allow writes on the bridge, default `0`

## Runtime Notes

- High-risk shell commands remain quarantined until confirmed.
- The bus is synchronous for request/reply, but durable state is still recorded in SQLite.
- The bridge is read-restricted to the configured root and is disabled unless started explicitly.
