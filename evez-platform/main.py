"""
EVEZ Platform — Main API Server

FastAPI backend with SSE streaming, chat, search, agent, and stream endpoints.
"""

import asyncio
import json
import os
import sys
import logging
import time
from pathlib import Path
from datetime import datetime, timezone
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, StreamingResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional, List, Dict, Any
from sse_starlette.sse import EventSourceResponse

# Add parent to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from core import EveZCore
from agent import Agent, ModelProvider
from search import SearchEngine
from stream import AutonomousStream
from swarm import ComputeSwarm, SwarmProvisioner, ComputeTier
from cognition import CognitiveEngine
from access import EveZAccess
from replicate import Replicator
from metarom import MetaROMBridge
from finance import FinancialEngine
from income import IncomeEngine
from quantum import QuantumManifoldHub
from automator import IncomeAutomator
from trunk import Trunk, ChatGPTConnector, PerplexityConnector, N8NConnector
from emergent import EmergentCognition
from finance.wallet import EVEZWallet
from finance.debt_resolver import DebtResolver
from income.daily_engine import DailyIncomeEngine

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("evez.api")

# ---------------------------------------------------------------------------
# Global State
# ---------------------------------------------------------------------------

DATA_DIR = Path(os.environ.get("EVEZ_DATA", "/root/.openclaw/workspace/evez-platform/data"))
WORKSPACE = Path(os.environ.get("EVEZ_WORKSPACE", "/root/.openclaw/workspace"))

core: EveZCore = None
models: ModelProvider = None
agent: Agent = None
search_engine: SearchEngine = None
streamer: AutonomousStream = None
swarm: ComputeSwarm = None
provisioner: SwarmProvisioner = None
cognition: CognitiveEngine = None
access_layer: EveZAccess = None
replicator: Replicator = None
metarom: MetaROMBridge = None
finance: FinancialEngine = None
income: IncomeEngine = None
quantum: QuantumManifoldHub = None
automator: IncomeAutomator = None
trunk: Trunk = None
emergent: EmergentCognition = None
wallet: EVEZWallet = None
debt: DebtResolver = None
daily_income: DailyIncomeEngine = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup/shutdown lifecycle."""
    global core, models, agent, search_engine, streamer, swarm, provisioner, cognition, access_layer, replicator, metarom, finance, income, quantum, automator, trunk, emergent, income, wallet, debt, daily_income

    logger.info("⚡ EVEZ Platform starting...")
    core = EveZCore(DATA_DIR)
    models = ModelProvider()
    agent = Agent(core, models)
    search_engine = SearchEngine(models)
    streamer = AutonomousStream(core, models, search_engine)
    swarm = ComputeSwarm(DATA_DIR / "swarm")
    provisioner = SwarmProvisioner()
    cognition = CognitiveEngine(core.spine)
    access_layer = EveZAccess(core.spine, core.memory, cognition)
    replicator = Replicator(WORKSPACE, DATA_DIR)
    metarom = MetaROMBridge(core.spine, WORKSPACE)
    finance = FinancialEngine(core.spine, cognition, DATA_DIR)
    income = IncomeEngine(core.spine, cognition, DATA_DIR)
    quantum = QuantumManifoldHub(core.spine, DATA_DIR / "quantum")
    automator = IncomeAutomator(DATA_DIR / "income")
    automator.generate_immediate_tasks()

    # Initialize trunk with surfaces
    trunk = Trunk(core.spine, DATA_DIR / "trunk")
    # Register surfaces (API keys from environment)
    import os
    if os.environ.get("OPENAI_API_KEY"):
        trunk.register_surface("chatgpt", ChatGPTConnector(os.environ["OPENAI_API_KEY"]))
    if os.environ.get("PERPLEXITY_API_KEY"):
        trunk.register_surface("perplexity", PerplexityConnector(os.environ["PERPLEXITY_API_KEY"]))
    if os.environ.get("N8N_WEBHOOK_URL"):
        trunk.register_surface("n8n", N8NConnector(os.environ["N8N_WEBHOOK_URL"]))

    # Initialize emergent cognition
    emergent = EmergentCognition(core.spine)
    income = IncomeEngine(core.spine, cognition, DATA_DIR / "income")

    # Initialize wallet and debt resolver
    wallet = EVEZWallet(DATA_DIR / "wallet")
    debt = DebtResolver(DATA_DIR / "debt")
    daily_income = DailyIncomeEngine(DATA_DIR / "income")

    # Store startup in spine
    core.spine.write("platform.start", {
        "version": "0.1.0",
        "data_dir": str(DATA_DIR),
    }, tags=["platform", "boot"])

    logger.info("⚡ EVEZ Platform ready — http://localhost:8080")
    yield

    # Shutdown
    if streamer and streamer.running:
        await streamer.stop()
    core.spine.write("platform.stop", {}, tags=["platform", "shutdown"])
    logger.info("⚡ EVEZ Platform stopped")


# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------

app = FastAPI(title="EVEZ Platform", version="0.1.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Serve static files — resolve relative to main.py's parent (evez-platform/)
BASE_DIR = Path(__file__).parent
STATIC_DIR = BASE_DIR / "static"
TEMPLATES_DIR = BASE_DIR / "templates"
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


# ---------------------------------------------------------------------------
# Request Models
# ---------------------------------------------------------------------------

class ChatRequest(BaseModel):
    message: str
    model: Optional[str] = None
    conversation_id: Optional[str] = None
    stream: bool = True

class SearchRequest(BaseModel):
    query: str
    max_results: int = 8

class NewConversationRequest(BaseModel):
    title: Optional[str] = "New Chat"


# ---------------------------------------------------------------------------
# Routes — Pages
# ---------------------------------------------------------------------------

@app.get("/", response_class=HTMLResponse)
async def index():
    """Serve main UI."""
    template = TEMPLATES_DIR / "index.html"
    if template.exists():
        return HTMLResponse(template.read_text())
    return HTMLResponse("<h1>EVEZ Platform</h1><p>Templates not found.</p>")


# ---------------------------------------------------------------------------
# Routes — API
# ---------------------------------------------------------------------------

@app.get("/api/health")
async def health():
    return {"status": "ok", "time": datetime.now(timezone.utc).isoformat()}


@app.get("/api/models")
async def list_models():
    """List available models (free first)."""
    m = await models.list_models()
    return {"models": m}


@app.post("/api/chat")
async def chat(req: ChatRequest):
    """Chat with agent (supports streaming via SSE)."""

    # Create conversation if needed
    conv_id = req.conversation_id
    if not conv_id:
        conv_id = core.conversations.create_conversation(
            title=req.message[:50] + "..." if len(req.message) > 50 else req.message
        )

    if req.stream:
        async def generate():
            yield f"data: {json.dumps({'type': 'conversation_id', 'id': conv_id})}\n\n"

            try:
                async for chunk in agent.run_stream(req.message, model=req.model,
                                                    conversation_id=conv_id):
                    if chunk:
                        yield f"data: {json.dumps({'type': 'content', 'content': chunk})}\n\n"
                yield f"data: {json.dumps({'type': 'done'})}\n\n"
            except Exception as e:
                yield f"data: {json.dumps({'type': 'error', 'error': str(e)})}\n\n"

        return StreamingResponse(generate(), media_type="text/event-stream")
    else:
        result = await agent.run(req.message, model=req.model,
                                 conversation_id=conv_id)
        return {"conversation_id": conv_id, "response": result}


@app.post("/api/search")
async def search(req: SearchRequest):
    """AI-powered search with citations."""
    result = await search_engine.research(req.query, req.max_results)
    return result


@app.get("/api/conversations")
async def list_conversations():
    """List all conversations."""
    convs = core.conversations.list_conversations()
    return {"conversations": convs}


@app.get("/api/conversations/{conv_id}")
async def get_conversation(conv_id: str):
    """Get conversation messages."""
    messages = core.conversations.get_messages(conv_id)
    return {"conversation_id": conv_id, "messages": messages}


@app.post("/api/conversations/new")
async def new_conversation(req: NewConversationRequest):
    """Create new conversation."""
    conv_id = core.conversations.create_conversation(req.title)
    return {"conversation_id": conv_id}


@app.get("/api/conversations/{conv_id}/search")
async def search_conversation(conv_id: str, q: str = ""):
    """Search within conversation history."""
    results = core.conversations.search_messages(q)
    return {"results": results}


# ---------------------------------------------------------------------------
# Routes — Stream
# ---------------------------------------------------------------------------

@app.post("/api/stream/start")
async def start_stream():
    """Start autonomous broadcast."""
    if streamer.running:
        return {"status": "already_running", **streamer.get_status()}
    asyncio.create_task(streamer.start())
    return {"status": "starting"}


@app.post("/api/stream/stop")
async def stop_stream():
    """Stop autonomous broadcast."""
    await streamer.stop()
    return {"status": "stopped"}


@app.get("/api/stream/status")
async def stream_status():
    """Get stream status."""
    return streamer.get_status()


@app.get("/api/stream/events")
async def stream_events(n: int = 20):
    """Get recent stream events."""
    return {"events": streamer.get_recent_events(n)}


@app.get("/api/stream/live")
async def stream_live():
    """SSE endpoint for live stream events."""
    async def generate():
        last_count = 0
        while True:
            if len(streamer.events) > last_count:
                for event in streamer.events[last_count:]:
                    yield f"data: {json.dumps(event.to_dict())}\n\n"
                last_count = len(streamer.events)
            await asyncio.sleep(1)

    return EventSourceResponse(generate())


# ---------------------------------------------------------------------------
# Routes — Spine & Memory
# ---------------------------------------------------------------------------

@app.get("/api/spine")
async def get_spine(n: int = 50):
    """Get recent spine events."""
    return {"events": core.spine.read_recent(n)}


@app.get("/api/spine/search")
async def search_spine(q: str = "", n: int = 20):
    """Search spine events."""
    return {"events": core.spine.search(q, n)}


@app.get("/api/memory")
async def get_memory():
    """Get current memories."""
    memories = core.memory.strongest(20)
    return {"memories": [
        {"key": m.key, "content": m.content[:200], "strength": m.strength,
         "tags": m.tags, "source": m.source}
        for m in memories
    ]}


# ---------------------------------------------------------------------------
# Routes — System
# ---------------------------------------------------------------------------

@app.get("/api/system/status")
async def system_status():
    """Full system status."""
    model_list = await models.list_models()
    return {
        "platform": "EVEZ",
        "version": "0.5.1",
        "models": model_list,
        "ollama": await models.is_ollama_up(),
        "stream": streamer.get_status(),
        "swarm": swarm.get_status(),
        "cognition": cognition.get_state(),
        "spine_events": core.spine._event_count,
        "conversations": len(core.conversations.list_conversations()),
        "memories": len(core.memory.memories),
    }


# ---------------------------------------------------------------------------
# Routes — Compute Swarm
# ---------------------------------------------------------------------------

@app.get("/api/swarm/status")
async def swarm_status():
    return swarm.get_status()

@app.post("/api/swarm/register")
async def swarm_register(request: Request):
    body = await request.json()
    node_id = swarm.register_node(
        name=body.get("name", "unnoded"),
        tier=ComputeTier(body.get("tier", "edge")),
        endpoint=body.get("endpoint", "unknown"),
        cpus=body.get("cpus", 0),
        ram_gb=body.get("ram_gb", 0),
        gpu=body.get("gpu", ""),
        capabilities=body.get("capabilities", []),
    )
    return {"node_id": node_id, "status": "registered"}

@app.post("/api/swarm/submit")
async def swarm_submit(request: Request):
    body = await request.json()
    task_id = swarm.submit_task(
        name=body.get("name", "unnamed"),
        payload=body.get("payload", {}),
        priority=body.get("priority", 5),
        required_tier=ComputeTier(body.get("tier", "edge")),
        requires_gpu=body.get("requires_gpu", False),
        timeout=body.get("timeout", 300),
    )
    return {"task_id": task_id, "status": "queued"}

@app.get("/api/swarm/provision/{provider}")
async def swarm_provision(provider: str):
    scripts = {
        "github": provisioner.generate_gha_swarm("EvezArt/evez-platform"),
        "oracle": provisioner.generate_oracle_init(),
        "kaggle": provisioner.generate_kaggle_notebook(),
        "boinc": provisioner.generate_boinc_config(),
        "vastai": provisioner.generate_vastai_script(),
    }
    if provider not in scripts:
        raise HTTPException(404, f"Unknown provider: {provider}")
    return {"provider": provider, "script": scripts[provider]}

@app.get("/api/swarm/provisioners")
async def swarm_provisioners():
    return {"provisioners": [
        {"id": "oracle", "name": "Oracle Cloud Free", "cpus": 4, "ram_gb": 24, "cost": "free forever"},
        {"id": "github", "name": "GitHub Actions Swarm", "cpus": "Nx2", "cost": "2k min/mo x N forks"},
        {"id": "kaggle", "name": "Kaggle GPU Notebooks", "gpu": "T4 16GB", "cost": "20h/wk free"},
        {"id": "boinc", "name": "BOINC Volunteer Grid", "cpus": "inf", "cost": "volunteer opt-in"},
        {"id": "vastai", "name": "Vast.ai Startup", "gpu": "swarm", "cost": "$2500 credits"},
    ]}


# ---------------------------------------------------------------------------
# Routes — Cognitive Sensory Engine
# ---------------------------------------------------------------------------

@app.get("/api/cognition/status")
async def cognition_status():
    return cognition.get_state()

@app.post("/api/cognition/perceive")
async def cognition_perceive(request: Request):
    body = await request.json()
    result = await cognition.perceive(
        body.get("modality", "text"),
        body.get("input", ""),
        body.get("context"),
    )
    return result

@app.get("/api/cognition/focus")
async def cognition_focus():
    return cognition.get_focus()

@app.post("/api/cognition/focus")
async def set_cognition_focus(request: Request):
    body = await request.json()
    cognition.set_focus(body.get("target", ""), body.get("reason", ""))
    return {"status": "ok"}


# ---------------------------------------------------------------------------
# Routes — Access Layer (read-only façade)
# ---------------------------------------------------------------------------

@app.get("/api/access/status")
async def access_status():
    return access_layer.get_status()

@app.get("/api/access/snapshot")
async def access_snapshot(n: int = 100):
    return {"events": access_layer.snapshot(n)}

@app.get("/api/access/spine")
async def access_spine_snapshot(n: int = 50):
    return {"events": access_layer.snapshot_spine(n)}

@app.get("/api/access/memory")
async def access_memory_snapshot():
    return {"memories": access_layer.snapshot_memory()}

@app.get("/api/access/fire")
async def access_fire(n: int = 1):
    """Pure FIRE score accessor — no state mutation."""
    return {
        "n": n,
        "tau": EveZAccess.tau(n),
        "omega": EveZAccess.omega(n),
        "fire": EveZAccess.fire(n),
    }

@app.get("/api/access/fire/window")
async def access_fire_window(start: int = 1, end: int = 100):
    return {"results": access_layer.fire_window(start, end)}

@app.get("/api/access/search/spine")
async def access_search_spine(q: str = "", n: int = 20):
    return {"results": access_layer.spine_search(q, n)}

@app.get("/api/access/search/memory")
async def access_search_memory(q: str = "", n: int = 5):
    return {"results": access_layer.memory_search(q, n)}


# ---------------------------------------------------------------------------
# Routes — Replication
# ---------------------------------------------------------------------------

@app.get("/api/replicate/status")
async def replicate_status():
    return replicator.get_status()

@app.get("/api/replicate/manifest")
async def replicate_manifest():
    return replicator.generate_manifest()

@app.get("/api/replicate/boot-script")
async def replicate_boot_script():
    from fastapi.responses import PlainTextResponse
    return PlainTextResponse(replicator.generate_boot_script())

@app.get("/api/replicate/dockerfile")
async def replicate_dockerfile():
    from fastapi.responses import PlainTextResponse
    return PlainTextResponse(replicator.generate_dockerfile())

@app.get("/api/replicate/docker-compose")
async def replicate_docker_compose():
    from fastapi.responses import PlainTextResponse
    return PlainTextResponse(replicator.generate_docker_compose())

@app.post("/api/replicate/bundle")
async def replicate_bundle():
    path = replicator.create_bundle()
    return {"bundle": str(path), "size_mb": round(path.stat().st_size / 1e6, 2)}


# ---------------------------------------------------------------------------
# Routes — MetaROM Bridge
# ---------------------------------------------------------------------------

@app.get("/api/metarom/stats")
async def metarom_stats():
    return metarom.get_stats()


# ---------------------------------------------------------------------------
# Routes — Income Engine
# ---------------------------------------------------------------------------

@app.get("/api/income/status")
async def income_status():
    return income.get_status()

@app.post("/api/income/scan")
async def income_scan():
    opps = await income.scan_all()
    return {"opportunities": [o.to_dict() for o in opps], "total": len(opps)}

@app.get("/api/income/opportunities")
async def income_opportunities(n: int = 10, verified: bool = False):
    return {"opportunities": income.get_top_opportunities(n, verified)}

@app.get("/api/income/portfolio")
async def income_portfolio():
    return income.get_portfolio()

@app.post("/api/income/wallet")
async def add_income_wallet(request: Request):
    body = await request.json()
    income.add_wallet(body.get("chain", ""), body.get("address", ""), body.get("label", ""))
    return {"status": "added"}


# ---------------------------------------------------------------------------
# Routes — Financial Engine
# ---------------------------------------------------------------------------

@app.get("/api/finance/status")
async def finance_status():
    return finance.get_status()

@app.post("/api/finance/observe")
async def finance_observe():
    result = await finance.observe()
    return result

@app.post("/api/finance/analyze")
async def finance_analyze(request: Request):
    body = await request.json()
    asset = body.get("asset", "bitcoin")
    signal = await finance.analyze(asset)
    return signal.to_dict() if signal else {"error": "Insufficient data"}

@app.get("/api/finance/signals")
async def finance_signals(n: int = 20):
    return {"signals": finance.get_signals(n)}

@app.get("/api/finance/portfolio")
async def finance_portfolio():
    return finance.get_portfolio_status()


# ---------------------------------------------------------------------------
# Routes — HD Wallet
# ---------------------------------------------------------------------------

@app.get("/api/wallet/status")
async def wallet_status():
    return wallet.get_status()

@app.get("/api/wallet/info")
async def wallet_info():
    """Public-safe wallet info (no private keys)."""
    return wallet.get_public_info()

@app.post("/api/wallet/create")
async def wallet_create(request: Request):
    """Create new HD wallet. Returns mnemonic ONCE."""
    body = await request.json() if request.headers.get("content-length") else {}
    result = wallet.create_wallet(label=body.get("label", "evez"))
    return result

@app.post("/api/wallet/derive")
async def wallet_derive(request: Request):
    """Derive new account from HD wallet."""
    body = await request.json()
    return wallet.derive_account(
        index=body.get("index"),
        label=body.get("label", ""),
    )

@app.get("/api/wallet/accounts")
async def wallet_accounts():
    return {"accounts": wallet.list_accounts()}


# ---------------------------------------------------------------------------
# Routes — Debt Resolver
# ---------------------------------------------------------------------------

@app.get("/api/debt/status")
async def debt_status():
    return debt.get_status()

@app.post("/api/debt/add")
async def debt_add(request: Request):
    """Add a debt to the portfolio."""
    body = await request.json()
    return debt.add_debt(
        name=body["name"],
        balance=body["balance"],
        interest_rate=body["interest_rate"],
        minimum_payment=body["minimum_payment"],
        type=body.get("type", "revolving"),
        is_collections=body.get("is_collections", False),
    )

@app.post("/api/debt/income")
async def debt_set_income(request: Request):
    """Set monthly income for debt calculations."""
    body = await request.json()
    debt.set_income(body["mean"], body.get("std", 0))
    return {"status": "updated", "mean": body["mean"]}

@app.post("/api/debt/expenses")
async def debt_set_expenses(request: Request):
    """Set monthly non-debt expenses."""
    body = await request.json()
    debt.set_expenses(body["monthly"])
    return {"status": "updated", "monthly": body["monthly"]}

@app.post("/api/debt/cash")
async def debt_set_cash(request: Request):
    """Set current liquid cash available."""
    body = await request.json()
    debt.set_cash(body["available"])
    return {"status": "updated", "available": body["available"]}

@app.post("/api/debt/analyze")
async def debt_analyze():
    """Full probabilistic debt analysis."""
    return debt.full_analysis()

@app.get("/api/debt/strategies")
async def debt_strategies():
    """Compare all payoff strategies."""
    strats = debt.compute_all_strategies()
    return {"strategies": [s.to_dict() for s in strats]}

@app.get("/api/debt/negotiate")
async def debt_negotiate():
    """Score negotiation opportunities."""
    return {"opportunities": debt.score_negotiation_opportunities()}

@app.post("/api/debt/kelly")
async def debt_kelly(request: Request):
    """Kelly Criterion optimal allocation."""
    body = await request.json() if request.headers.get("content-length") else {}
    return debt.kelly_allocation(investment_return=body.get("investment_return", 0.08))

@app.post("/api/debt/monte-carlo")
async def debt_monte_carlo(request: Request):
    """Monte Carlo cashflow simulation."""
    body = await request.json() if request.headers.get("content-length") else {}
    return debt.monte_carlo_cashflow(
        n_simulations=body.get("simulations", 1000),
        months=body.get("months", 60),
    )

@app.post("/api/debt/bayesian")
async def debt_bayesian(request: Request):
    """Bayesian income update from observed data."""
    body = await request.json()
    return debt.bayesian_income_update(body.get("incomes", []))


# ---------------------------------------------------------------------------
# Routes — Daily Income Engine ($100/day)
# ---------------------------------------------------------------------------

@app.get("/api/daily/status")
async def daily_status():
    return daily_income.get_status()

@app.get("/api/daily/runbook")
async def daily_runbook():
    """Today's execution plan to hit $100."""
    return daily_income.get_daily_runbook()

@app.get("/api/daily/projection")
async def daily_projection():
    """30-day income projection."""
    return daily_income.get_projection()

@app.post("/api/daily/log")
async def daily_log(request: Request):
    """Log earnings from a source."""
    body = await request.json()
    daily_income.log_earnings(
        source_name=body["source"],
        amount=body["amount"],
        hours=body.get("hours", 0),
    )
    return {"status": "logged", "source": body["source"], "amount": body["amount"]}

@app.post("/api/daily/signup")
async def daily_signup(request: Request):
    """Update signup status for a source."""
    body = await request.json()
    daily_income.update_signup_status(body["source"], body["status"])
    return {"status": "updated"}


# ---------------------------------------------------------------------------
# Routes — Income Engine
# ---------------------------------------------------------------------------

@app.get("/api/income/status")
async def income_status():
    return income.get_status()

@app.post("/api/income/scan")
async def income_scan():
    opps = await income.scan_all()
    return {"opportunities": [o.to_dict() for o in opps], "total": len(opps)}

@app.get("/api/income/opportunities")
async def income_opportunities(n: int = 10, verified: bool = False):
    return {"opportunities": income.get_top_opportunities(n, verified)}

@app.get("/api/income/portfolio")
async def income_portfolio():
    return income.get_portfolio()

@app.post("/api/income/wallet")
async def income_add_wallet(request: Request):
    body = await request.json()
    income.add_wallet(
        chain=body.get("chain", "ETH"),
        address=body.get("address", ""),
        label=body.get("label", ""),
    )
    return {"status": "added"}


# ---------------------------------------------------------------------------
# Routes — Quantum Manifold Hub
# ---------------------------------------------------------------------------

@app.get("/api/quantum/status")
async def quantum_status():
    return quantum.get_state()

@app.post("/api/quantum/step")
async def quantum_step(steps: int = 1):
    results = []
    for _ in range(min(steps, 100)):
        q = quantum.step()
        results.append(q.to_dict())
    return {"steps": len(results), "qualia": results[-5:], "state": quantum.get_state()}

@app.post("/api/quantum/action")
async def quantum_register_action(request: Request):
    body = await request.json()
    quantum.grover.register_action(body)
    return {"status": "registered", "total_actions": len(quantum.grover.actions)}

@app.get("/api/quantum/probabilities")
async def quantum_probabilities():
    import numpy as np
    probs = quantum.grover.get_probabilities().tolist()
    actions = quantum.grover.actions
    return {
        "probabilities": probs[:len(actions)] if actions else [],
        "actions": actions,
        "top_action": int(np.argmax(probs)) if probs else -1,
    }


# ---------------------------------------------------------------------------
# Routes — Income Automator (actual executable tasks)
# ---------------------------------------------------------------------------

@app.get("/api/automator/tasks")
async def automator_tasks():
    return {"tasks": automator.get_prioritized()}

@app.get("/api/automator/status")
async def automator_status():
    return automator.get_status()

@app.post("/api/automator/earn")
async def automator_record_earning(request: Request):
    body = await request.json()
    automator.record_earning(
        source=body.get("source", "manual"),
        amount=float(body.get("amount", 0)),
        description=body.get("description", ""),
    )
    return automator.get_status()


# ---------------------------------------------------------------------------
# Routes — Trunk (master integration bus)
# ---------------------------------------------------------------------------

@app.get("/api/trunk/status")
async def trunk_status():
    return trunk.get_state()

@app.post("/api/trunk/advance")
async def trunk_advance(request: Request):
    body = await request.json()
    objective = body.get("objective", "")
    if not objective:
        return {"error": "No objective provided"}
    result = await trunk.advance(objective)
    return result


# ---------------------------------------------------------------------------
# Routes — Emergent Cognition (quantum interference states)
# ---------------------------------------------------------------------------

@app.get("/api/emergent/status")
async def emergent_status():
    return emergent.get_state()

@app.post("/api/emergent/process")
async def emergent_process(request: Request):
    body = await request.json()
    result = emergent.process(
        context=body.get("context", "general"),
        action=body.get("action", "default"),
        options=body.get("options", []),
        raw_signal=body.get("signal"),
    )
    return result

@app.get("/api/emergent/diagnostic")
async def emergent_diagnostic():
    return emergent.meta.get_self_diagnostic()

@app.get("/api/emergent/next-actions")
async def emergent_next_actions():
    return {"actions": emergent.temporal.get_next_actions()}

@app.get("/api/emergent/project")
async def emergent_project(hours: int = 24):
    return {"projected": emergent.temporal.project_future(hours)}


# ---------------------------------------------------------------------------
# Routes — Full System Graph
# ---------------------------------------------------------------------------

@app.get("/api/system/graph")
async def system_graph():
    """Expose current system topology — all modules, all connections."""
    return {
        "platform": "EVEZ",
        "version": "0.5.1",
        "modules": {
            "core": {"status": "online", "description": "Spine, Memory, Conversations"},
            "agent": {"status": "online", "description": "KiloCode API, tool-calling"},
            "search": {"status": "online", "description": "Web search + AI synthesis"},
            "stream": {"status": "online", "description": "24/7 autonomous broadcast"},
            "cognition": {"status": "online", "description": "Invariance Battery"},
            "access": {"status": "online", "description": "Read-only façade"},
            "swarm": {"status": "online", "description": "Compute swarm"},
            "replicate": {"status": "online", "description": "Self-replication"},
            "metarom": {"status": "online", "description": "ROM cognition bridge"},
            "finance": {"status": "online", "description": "Market analysis"},
            "income": {"status": "online", "description": "Income automation"},
            "quantum": {"status": "online", "description": "TDSE + Grover routing"},
            "automator": {"status": "online", "description": "Executable income tasks"},
            "trunk": {"status": "online", "description": "Cross-surface bus"},
            "emergent": {"status": "online", "description": "Meta-cognition + learning + temporal"},
        },
        "surfaces": {
            "chatgpt": {"role": "skeptic", "status": "ready"},
            "claude": {"role": "architect", "status": "ready"},
            "perplexity": {"role": "recon", "status": "ready"},
            "n8n": {"role": "executor", "status": "ready"},
            "android": {"role": "mobile", "status": "ready"},
        },
        "cron": {
            "watchdog": "every 5 min",
            "income_scan": "every 6 hours",
            "auto_commit": "every 30 min",
        },
        "spine_events": core.spine._event_count,
    }


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("EVEZ_PORT", "8080"))
    uvicorn.run(app, host="0.0.0.0", port=port, log_level="info")
