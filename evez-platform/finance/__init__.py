"""
EVEZ Financial Engine — Autonomous DeFi observation + execution.

Provides:
- Multi-chain price feeds (free public APIs)
- Portfolio tracking
- MEV pattern detection
- Risk assessment via Invariance Battery
- Trade signal generation (requires explicit user approval)

Steven's requirement: "abilities to make money and trade online in crypto
or currency based transactions. They must verify internally eternally before
external verification sensory is attempted."
"""

import json
import time
import hashlib
import logging
from pathlib import Path
from datetime import datetime, timezone
from typing import Optional, Dict, Any, List, Tuple
from dataclasses import dataclass, field

import httpx

logger = logging.getLogger("evez.finance")


@dataclass
class PricePoint:
    asset: str
    price_usd: float
    volume_24h: float
    change_24h: float
    timestamp: float = field(default_factory=time.time)
    source: str = ""

    def to_dict(self):
        return {
            "asset": self.asset, "price_usd": self.price_usd,
            "volume_24h": self.volume_24h, "change_24h": self.change_24h,
            "ts": self.timestamp, "source": self.source,
        }


@dataclass
class TradeSignal:
    action: str       # "buy", "sell", "hold"
    asset: str
    confidence: float
    reasoning: str
    price_target: float = 0
    stop_loss: float = 0
    verified: bool = False   # Must pass Invariance Battery
    battery_passed: int = 0
    battery_failed: int = 0
    created: float = field(default_factory=time.time)

    def to_dict(self):
        return {
            "action": self.action, "asset": self.asset,
            "confidence": self.confidence, "reasoning": self.reasoning,
            "price_target": self.price_target, "stop_loss": self.stop_loss,
            "verified": self.verified,
            "battery_passed": self.battery_passed,
            "battery_failed": self.battery_failed,
        }


class PriceFeed:
    """Free price feeds from public APIs."""

    COINGECKO_BASE = "https://api.coingecko.com/api/v3"

    async def get_price(self, asset_id: str) -> Optional[PricePoint]:
        """Get current price from CoinGecko (free, no key)."""
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                r = await client.get(
                    f"{self.COINGECKO_BASE}/simple/price",
                    params={
                        "ids": asset_id,
                        "vs_currencies": "usd",
                        "include_24hr_vol": "true",
                        "include_24hr_change": "true",
                    }
                )
                data = r.json()
                if asset_id in data:
                    d = data[asset_id]
                    return PricePoint(
                        asset=asset_id,
                        price_usd=d.get("usd", 0),
                        volume_24h=d.get("usd_24h_vol", 0),
                        change_24h=d.get("usd_24h_change", 0),
                        source="coingecko",
                    )
        except Exception as e:
            logger.error("Price fetch failed: %s", e)
        return None

    async def get_prices(self, asset_ids: List[str]) -> List[PricePoint]:
        """Get prices for multiple assets."""
        results = []
        for aid in asset_ids:
            price = await self.get_price(aid)
            if price:
                results.append(price)
            time.sleep(0.5)  # Rate limit
        return results

    async def get_market_overview(self) -> Dict:
        """Global market overview."""
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                r = await client.get(f"{self.COINGECKO_BASE}/global")
                data = r.json().get("data", {})
                return {
                    "total_market_cap_usd": data.get("total_market_cap", {}).get("usd", 0),
                    "total_volume_24h": data.get("total_volume", {}).get("usd", 0),
                    "btc_dominance": data.get("market_cap_percentage", {}).get("btc", 0),
                    "active_cryptos": data.get("active_cryptocurrencies", 0),
                }
        except Exception:
            return {"error": "Market data unavailable"}


class FinancialEngine:
    """
    Autonomous financial observation and signal generation.

    Pipeline:
    1. Observe: Multi-source price feeds
    2. Analyze: Pattern detection, trend analysis
    3. Think: Generate TradeSignal (CognitiveEvent)
    4. Verify: Invariance Battery (MUST pass before any action)
    5. Act: Only with explicit user approval
    """

    def __init__(self, spine=None, cognition=None, data_dir: Path = None):
        self.spine = spine
        self.cognition = cognition
        self.data_dir = data_dir or Path("/root/.openclaw/workspace/evez-platform/data")
        self.feed = PriceFeed()
        self.price_history: Dict[str, List[PricePoint]] = {}
        self.signals: List[TradeSignal] = []
        self.watchlist: List[str] = ["bitcoin", "ethereum", "solana"]
        self.auto_trade_enabled = False  # NEVER auto-trade without explicit opt-in

    async def observe(self) -> Dict:
        """Observe current market state."""
        prices = await self.feed.get_prices(self.watchlist)
        market = await self.feed.get_market_overview()

        # Store in history
        for p in prices:
            if p.asset not in self.price_history:
                self.price_history[p.asset] = []
            self.price_history[p.asset].append(p)
            # Keep last 1000 points
            self.price_history[p.asset] = self.price_history[p.asset][-1000:]

        # Write to spine
        if self.spine:
            self.spine.write("finance.observe", {
                "assets": [p.to_dict() for p in prices],
                "market_cap": market.get("total_market_cap_usd", 0),
            }, tags=["finance", "observation"])

        return {
            "prices": [p.to_dict() for p in prices],
            "market": market,
            "watchlist": self.watchlist,
        }

    async def analyze(self, asset: str) -> Optional[TradeSignal]:
        """Analyze an asset and generate a trade signal."""
        history = self.price_history.get(asset, [])
        if len(history) < 2:
            return None

        prices = [h.price_usd for h in history[-20:]]
        current = prices[-1]
        avg = sum(prices) / len(prices)
        change = (current - prices[0]) / prices[0] * 100 if prices[0] > 0 else 0

        # Simple trend analysis
        if change > 5:
            action = "buy"
            confidence = min(0.8, change / 20)
            reasoning = f"{asset} up {change:.1f}% over recent period — bullish trend"
        elif change < -5:
            action = "sell"
            confidence = min(0.8, abs(change) / 20)
            reasoning = f"{asset} down {change:.1f}% over recent period — bearish trend"
        else:
            action = "hold"
            confidence = 0.5
            reasoning = f"{asset} stable ({change:.1f}%) — no clear direction"

        signal = TradeSignal(
            action=action, asset=asset, confidence=confidence,
            reasoning=reasoning,
            price_target=current * 1.1 if action == "buy" else current * 0.9,
            stop_loss=current * 0.95 if action == "buy" else current * 1.05,
        )

        # CRITICAL: Run through Invariance Battery before marking verified
        if self.cognition:
            result = await self.cognition.perceive("market", reasoning, {
                "asset": asset,
                "price": current,
                "change": change,
                "volatility": abs(change) / 10,
            })
            ce = result.get("ce", {})
            signal.battery_passed = ce.get("rotations_passed", 0)
            signal.battery_failed = ce.get("rotations_failed", 0)
            signal.verified = ce.get("confidence") == "validated"

        self.signals.append(signal)
        return signal

    def get_signals(self, limit: int = 20) -> List[Dict]:
        """Get recent trade signals."""
        return [s.to_dict() for s in self.signals[-limit:]]

    def get_portfolio_status(self) -> Dict:
        """Get current portfolio observation (no execution)."""
        latest_prices = {}
        for asset, history in self.price_history.items():
            if history:
                latest_prices[asset] = history[-1].to_dict()

        return {
            "watchlist": self.watchlist,
            "latest_prices": latest_prices,
            "signals_generated": len(self.signals),
            "verified_signals": sum(1 for s in self.signals if s.verified),
            "auto_trade": self.auto_trade_enabled,
        }

    def get_status(self) -> Dict:
        return {
            "watchlist": self.watchlist,
            "price_history_points": sum(len(v) for v in self.price_history.values()),
            "signals_generated": len(self.signals),
            "verified_signals": sum(1 for s in self.signals if s.verified),
            "auto_trade": self.auto_trade_enabled,
        }
