#!/usr/bin/env python3
"""
Executable Economic Graph Prototype.

What it does:
- Runs a small local HTTP server for event ingestion.
- Routes events through a Kafka-like in-memory bus.
- Processes events with services: router, sales, marketing, ledger, learning, maps, inference.
- Maintains an economic ledger and graph state.
- Exposes /event, /health, /state, /graph endpoints.
- Supports a built-in simulation mode.

No external dependencies. Standard library only.
"""

from __future__ import annotations

import json
import queue
import threading
import time
import uuid
from dataclasses import dataclass, field, asdict
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Callable, Dict, List, Optional


# -----------------------------
# Core data model
# -----------------------------

def now_ms() -> int:
    return int(time.time() * 1000)


def uid(prefix: str = "") -> str:
    return f"{prefix}{uuid.uuid4().hex[:12]}"


@dataclass
class EconomicContext:
    trace_id: str
    tenant_id: str = "default"
    value_potential: float = 0.0
    cost_budget: float = 0.0
    probability_success: float = 0.0
    latency_budget_ms: int = 1000
    roi_target: float = 1.0
    route_history: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class Event:
    event_type: str
    payload: Dict[str, Any]
    trace_id: str = field(default_factory=lambda: uid("trace-"))
    tenant_id: str = "default"
    ts_ms: int = field(default_factory=now_ms)
    source: str = "api"
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


# -----------------------------
# Event bus
# -----------------------------

class EventBus:
    def __init__(self) -> None:
        self.topics: Dict[str, queue.Queue[Event]] = {}
        self.subscribers: Dict[str, List[Callable[[Event], None]]] = {}
        self.lock = threading.Lock()
        self.history: List[Dict[str, Any]] = []

    def ensure_topic(self, topic: str) -> queue.Queue[Event]:
        with self.lock:
            if topic not in self.topics:
                self.topics[topic] = queue.Queue()
                self.subscribers[topic] = []
            return self.topics[topic]

    def publish(self, topic: str, event: Event) -> None:
        self.ensure_topic(topic)
        self.history.append({
            "ts_ms": now_ms(),
            "topic": topic,
            "event": event.to_dict(),
        })
        self.topics[topic].put(event)

    def subscribe(self, topic: str, handler: Callable[[Event], None]) -> None:
        self.ensure_topic(topic)
        self.subscribers[topic].append(handler)

    def start_workers(self) -> None:
        for topic in list(self.topics.keys()):
            t = threading.Thread(target=self._worker, args=(topic,), daemon=True)
            t.start()

    def _worker(self, topic: str) -> None:
        q = self.ensure_topic(topic)
        while True:
            event = q.get()
            try:
                for handler in self.subscribers.get(topic, []):
                    handler(event)
            except Exception as exc:
                # System-level error capture
                err = Event(
                    event_type="system.error",
                    payload={
                        "topic": topic,
                        "error": repr(exc),
                        "failed_event": event.to_dict(),
                    },
                    tenant_id=event.tenant_id,
                    trace_id=event.trace_id,
                    source="bus",
                )
                self.publish("graph.errors", err)
            finally:
                q.task_done()


# -----------------------------
# Ledger
# -----------------------------

@dataclass
class LedgerRow:
    trace_id: str
    tenant_id: str
    agent: str
    revenue: float
    cost: float
    roi: float
    ts_ms: int
    payload: Dict[str, Any]


class Ledger:
    def __init__(self) -> None:
        self.rows: List[LedgerRow] = []
        self.lock = threading.Lock()

    def record(self, row: LedgerRow) -> None:
        with self.lock:
            self.rows.append(row)

    def summary(self) -> Dict[str, Any]:
        with self.lock:
            revenue = sum(r.revenue for r in self.rows)
            cost = sum(r.cost for r in self.rows)
            profit = revenue - cost
            by_agent: Dict[str, Dict[str, float]] = {}
            for r in self.rows:
                a = by_agent.setdefault(r.agent, {"revenue": 0.0, "cost": 0.0, "profit": 0.0, "count": 0})
                a["revenue"] += r.revenue
                a["cost"] += r.cost
                a["profit"] += r.revenue - r.cost
                a["count"] += 1
            return {
                "rows": len(self.rows),
                "revenue": revenue,
                "cost": cost,
                "profit": profit,
                "by_agent": by_agent,
            }


# -----------------------------
# Services
# -----------------------------

class Service:
    name = "service"

    def __init__(self, bus: EventBus, state: Dict[str, Any]) -> None:
        self.bus = bus
        self.state = state

    def start(self) -> None:
        raise NotImplementedError


class IntakeService(Service):
    name = "intake"

    def start(self) -> None:
        self.bus.subscribe("graph.intake", self.handle)

    def handle(self, event: Event) -> None:
        ctx = EconomicContext(
            trace_id=event.trace_id,
            tenant_id=event.tenant_id,
            value_potential=float(event.payload.get("value", 0.0)),
            cost_budget=float(event.payload.get("cost_budget", 100.0)),
            probability_success=float(event.payload.get("probability_success", 0.5)),
            latency_budget_ms=int(event.payload.get("latency_budget_ms", 1000)),
            roi_target=float(event.payload.get("roi_target", 1.0)),
            route_history=event.metadata.get("route_history", []) + [self.name],
            metadata=event.payload,
        )
        routed = Event(
            event_type="graph.route.request",
            payload={"context": ctx.to_dict(), "original": event.to_dict()},
            tenant_id=event.tenant_id,
            trace_id=event.trace_id,
            source=self.name,
        )
        self.bus.publish("graph.router", routed)


class RouterService(Service):
    name = "router"

    def start(self) -> None:
        self.bus.subscribe("graph.router", self.handle)

    def handle(self, event: Event) -> None:
        ctx = event.payload["context"]
        value = float(ctx.get("value_potential", 0.0))
        probability = float(ctx.get("probability_success", 0.0))
        cost_budget = float(ctx.get("cost_budget", 0.0))
        roi_estimate = (value * max(probability, 0.01)) / max(cost_budget, 1.0)

        if roi_estimate >= 1.5 and value >= 500:
            target = "graph.sales"
            agent = "sales"
        elif roi_estimate >= 0.8:
            target = "graph.marketing"
            agent = "marketing"
        else:
            target = "graph.learning"
            agent = "learning"

        next_event = Event(
            event_type="graph.route.decision",
            payload={
                "context": ctx,
                "route": target,
                "agent": agent,
                "roi_estimate": roi_estimate,
            },
            tenant_id=event.tenant_id,
            trace_id=event.trace_id,
            source=self.name,
        )
        self.state.setdefault("routes", []).append(next_event.to_dict())
        self.bus.publish(target, next_event)


class SalesAgent(Service):
    name = "sales"

    def start(self) -> None:
        self.bus.subscribe("graph.sales", self.handle)

    def handle(self, event: Event) -> None:
        ctx = event.payload["context"]
        value = float(ctx.get("value_potential", 0.0))
        revenue = value * 1.3
        cost = max(value * 0.2, 1.0)
        roi = revenue / max(cost, 1.0)

        ledger_event = Event(
            event_type="graph.ledger.record",
            payload={
                "agent": self.name,
                "revenue": revenue,
                "cost": cost,
                "roi": roi,
                "source_event": event.to_dict(),
            },
            tenant_id=event.tenant_id,
            trace_id=event.trace_id,
            source=self.name,
        )
        self.bus.publish("graph.ledger", ledger_event)


class MarketingAgent(Service):
    name = "marketing"

    def start(self) -> None:
        self.bus.subscribe("graph.marketing", self.handle)

    def handle(self, event: Event) -> None:
        ctx = event.payload["context"]
        value = float(ctx.get("value_potential", 0.0))
        lift = 1.15
        revenue = value * lift
        cost = max(value * 0.1, 1.0)
        roi = revenue / max(cost, 1.0)

        ledger_event = Event(
            event_type="graph.ledger.record",
            payload={
                "agent": self.name,
                "revenue": revenue,
                "cost": cost,
                "roi": roi,
                "source_event": event.to_dict(),
            },
            tenant_id=event.tenant_id,
            trace_id=event.trace_id,
            source=self.name,
        )
        self.bus.publish("graph.ledger", ledger_event)


class LedgerService(Service):
    name = "ledger"

    def __init__(self, bus: EventBus, state: Dict[str, Any], ledger: Ledger) -> None:
        super().__init__(bus, state)
        self.ledger = ledger

    def start(self) -> None:
        self.bus.subscribe("graph.ledger", self.handle)

    def handle(self, event: Event) -> None:
        payload = event.payload
        revenue = float(payload.get("revenue", 0.0))
        cost = float(payload.get("cost", 0.0))
        roi = float(payload.get("roi", revenue / max(cost, 1.0)))
        row = LedgerRow(
            trace_id=event.trace_id,
            tenant_id=event.tenant_id,
            agent=payload.get("agent", "unknown"),
            revenue=revenue,
            cost=cost,
            roi=roi,
            ts_ms=event.ts_ms,
            payload=payload,
        )
        self.ledger.record(row)
        self.state.setdefault("ledger_events", []).append({
            "trace_id": row.trace_id,
            "agent": row.agent,
            "revenue": row.revenue,
            "cost": row.cost,
            "roi": row.roi,
        })
        # forward to learning
        self.bus.publish(
            "graph.learning",
            Event(
                event_type="graph.learning.signal",
                payload={"ledger_row": asdict(row)},
                tenant_id=event.tenant_id,
                trace_id=event.trace_id,
                source=self.name,
            )
        )


class LearningService(Service):
    name = "learning"

    def start(self) -> None:
        self.bus.subscribe("graph.learning", self.handle)

    def handle(self, event: Event) -> None:
        row = event.payload["ledger_row"]
        agent = row["agent"]
        profit = row["revenue"] - row["cost"]
        agent_stats = self.state.setdefault("agent_stats", {})
        stats = agent_stats.setdefault(agent, {"profit": 0.0, "count": 0, "avg_roi": 0.0})
        stats["profit"] += profit
        stats["count"] += 1
        stats["avg_roi"] = ((stats["avg_roi"] * (stats["count"] - 1)) + row["roi"]) / stats["count"]

        # simple adaptive adjustment
        routing = self.state.setdefault("routing_policy", {"sales_threshold": 1.5, "marketing_threshold": 0.8})
        if stats["avg_roi"] > 2.0:
            routing["sales_threshold"] = max(1.0, routing["sales_threshold"] - 0.05)
        elif stats["avg_roi"] < 1.2:
            routing["sales_threshold"] = min(3.0, routing["sales_threshold"] + 0.05)

        self.state.setdefault("learning_events", []).append({
            "trace_id": event.trace_id,
            "agent": agent,
            "profit": profit,
            "avg_roi": stats["avg_roi"],
            "policy": routing.copy(),
        })


class InferenceService(Service):
    name = "inference"

    def start(self) -> None:
        self.bus.subscribe("graph.inference", self.handle)

    def handle(self, event: Event) -> None:
        ctx = event.payload.get("context", {})
        task = ctx.get("task", "generic")
        complexity = float(ctx.get("complexity", 0.5))
        model = "phi-mini" if complexity < 0.4 else ("gpt-mid" if complexity < 0.8 else "llama-70b")
        self.state.setdefault("inference", []).append({
            "trace_id": event.trace_id,
            "task": task,
            "model": model,
            "tenant_id": event.tenant_id,
        })


class MapEngine(Service):
    name = "maps"

    def start(self) -> None:
        self.bus.subscribe("graph.maps", self.handle)

    def handle(self, event: Event) -> None:
        payload = event.payload
        self.state.setdefault("map_graph", []).append({
            "trace_id": event.trace_id,
            "node": payload.get("node", "unknown"),
            "kind": payload.get("kind", "concept"),
            "links": payload.get("links", []),
        })


# -----------------------------
# System bootstrap
# -----------------------------

def build_system() -> Dict[str, Any]:
    bus = EventBus()
    state: Dict[str, Any] = {
        "started_at_ms": now_ms(),
        "routes": [],
        "ledger_events": [],
        "learning_events": [],
        "agent_stats": {},
        "routing_policy": {"sales_threshold": 1.5, "marketing_threshold": 0.8},
        "inference": [],
        "map_graph": [],
    }
    ledger = Ledger()

    services: List[Service] = [
        IntakeService(bus, state),
        RouterService(bus, state),
        SalesAgent(bus, state),
        MarketingAgent(bus, state),
        LedgerService(bus, state, ledger),
        LearningService(bus, state),
        InferenceService(bus, state),
        MapEngine(bus, state),
    ]

    for s in services:
        s.start()

    # ensure topic workers exist
    for topic in [
        "graph.intake",
        "graph.router",
        "graph.sales",
        "graph.marketing",
        "graph.ledger",
        "graph.learning",
        "graph.inference",
        "graph.maps",
        "graph.errors",
    ]:
        bus.ensure_topic(topic)

    bus.start_workers()

    return {
        "bus": bus,
        "state": state,
        "ledger": ledger,
        "services": services,
    }


SYSTEM = build_system()


# -----------------------------
# HTTP API
# -----------------------------

class Handler(BaseHTTPRequestHandler):
    def _send(self, code: int, obj: Any) -> None:
        data = json.dumps(obj, indent=2, sort_keys=True).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self) -> None:
        if self.path == "/health":
            self._send(200, {"ok": True, "ts_ms": now_ms()})
            return
        if self.path == "/state":
            ledger_summary = SYSTEM["ledger"].summary()
            self._send(200, {
                "ok": True,
                "state": SYSTEM["state"],
                "ledger_summary": ledger_summary,
            })
            return
        if self.path == "/graph":
            self._send(200, {
                "ok": True,
                "map_graph": SYSTEM["state"].get("map_graph", []),
                "routes": SYSTEM["state"].get("routes", []),
                "inference": SYSTEM["state"].get("inference", []),
            })
            return
        self._send(404, {"error": "not_found"})

    def do_POST(self) -> None:
        if self.path != "/event":
            self._send(404, {"error": "not_found"})
            return

        length = int(self.headers.get("Content-Length", "0"))
        raw = self.rfile.read(length).decode() if length else "{}"
        try:
            body = json.loads(raw)
        except json.JSONDecodeError:
            self._send(400, {"error": "invalid_json"})
            return

        event_type = body.get("event_type", "graph.intake")
        payload = body.get("payload", body)
        trace_id = body.get("trace_id", uid("trace-"))
        tenant_id = body.get("tenant_id", "default")

        event = Event(
            event_type=event_type,
            payload=payload,
            trace_id=trace_id,
            tenant_id=tenant_id,
            source="http",
        )

        # direct entry into the graph
        SYSTEM["bus"].publish("graph.intake", event)

        self._send(202, {"queued": True, "trace_id": trace_id})


# -----------------------------
# Simulation
# -----------------------------

def simulate() -> None:
    samples = [
        {"value": 1000, "cost_budget": 200, "probability_success": 0.82, "roi_target": 1.5},
        {"value": 220, "cost_budget": 120, "probability_success": 0.55, "roi_target": 1.0},
        {"value": 5200, "cost_budget": 700, "probability_success": 0.91, "roi_target": 2.0},
        {"value": 80, "cost_budget": 30, "probability_success": 0.25, "roi_target": 0.8},
    ]
    for i, payload in enumerate(samples, start=1):
        event = Event(
            event_type="graph.intake",
            payload=payload,
            trace_id=f"sim-{i}",
            tenant_id="simulation",
            source="simulation",
        )
        SYSTEM["bus"].publish("graph.intake", event)
    time.sleep(1.0)


def main() -> None:
    import argparse
    parser = argparse.ArgumentParser(description="Executable Economic Graph Prototype")
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--simulate", action="store_true")
    args = parser.parse_args()

    if args.simulate:
        simulate()
        print(json.dumps({
            "ledger": SYSTEM["ledger"].summary(),
            "state": SYSTEM["state"],
        }, indent=2))
        return

    server = ThreadingHTTPServer((args.host, args.port), Handler)
    print(f"Serving on http://{args.host}:{args.port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down.")


if __name__ == "__main__":
    main()
