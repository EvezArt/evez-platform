# MINIMAL WORKING AGENT ECONOMY SIMULATOR
# Reference implementation - 2 services + Kafka-style bus + ledger

import asyncio
import json
import time
import random
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any
from enum import Enum
import uuid

# ============================================
# 1. EVENT BUS (Kafka-style)
# ============================================

class EventBus:
    """Simple in-memory Kafka-style event bus"""
    
    def __init__(self):
        self.topics: Dict[str, List[dict]] = {}
        
    def publish(self, topic: str, event: dict):
        if topic not in self.topics:
            self.topics[topic] = []
        event["_timestamp"] = time.time()
        event["_id"] = str(uuid.uuid4())
        self.topics[topic].append(event)
        
    def consume(self, topic: str) -> List[dict]:
        return self.topics.get(topic, [])


# ============================================
# 2. LEDGER (Economic Tracking)
# ============================================

@dataclass
class Transaction:
    from_agent: str
    to_agent: str
    amount: float
    reason: str
    timestamp: float

@dataclass
class AgentFinancials:
    agent_id: str
    balance: float = 0
    revenue: float = 0
    costs: float = 0
    
    @property
    def profit(self) -> float:
        return self.revenue - self.costs
    
    @property
    def roi(self) -> float:
        return self.revenue / max(self.costs, 0.01)

class Ledger:
    def __init__(self):
        self.transactions: List[Transaction] = []
        self.agents: Dict[str, AgentFinancials] = {}
        
    def register_agent(self, agent_id: str, initial_capital: float = 1000):
        self.agents[agent_id] = AgentFinancials(agent_id, initial_capital)
        
    def credit(self, agent_id: str, amount: float, source: str = "external"):
        if agent_id not in self.agents:
            self.register_agent(agent_id)
        self.agents[agent_id].revenue += amount
        self.agents[agent_id].balance += amount
        
    def debit(self, agent_id: str, amount: float, reason: str = "operation"):
        if agent_id not in self.agents:
            self.register_agent(agent_id)
        self.agents[agent_id].costs += amount
        self.agents[agent_id].balance -= amount
        
    def transfer(self, from_id: str, to_id: str, amount: float, reason: str):
        self.debit(from_id, amount, reason)
        self.credit(to_id, amount, reason)
        self.transactions.append(Transaction(from_id, to_id, amount, reason, time.time()))
        
    def get_agent(self, agent_id: str) -> AgentFinancials:
        if agent_id not in self.agents:
            self.register_agent(agent_id)
        return self.agents[agent_id]
    
    def get_ledger(self) -> Dict[str, Any]:
        return {
            agent_id: {
                "balance": a.balance,
                "revenue": a.revenue,
                "costs": a.costs,
                "profit": a.profit,
                "roi": a.roi
            }
            for agent_id, a in self.agents.items()
        }


# ============================================
# 3. MARKET SIMULATOR
# ============================================

class MarketSimulator:
    """Synthetic market that generates demand"""
    
    def __init__(self):
        self.demand = 0.5
        self.competition = 0.3
        self.trend = 0.0
        
    def step(self) -> dict:
        # Evolve market
        self.demand = max(0.1, min(0.9, self.demand + random.uniform(-0.1, 0.1)))
        self.competition = max(0.1, min(0.9, self.competition + random.uniform(-0.05, 0.05)))
        self.trend = random.uniform(-0.1, 0.1)
        
        return {
            "demand_level": self.demand,
            "competition_intensity": self.competition,
            "trend_shift": self.trend
        }


# ============================================
# 4. AGENT BASE CLASS
# ============================================

class AgentRole(Enum):
    SALES = "sales"
    MARKETING = "marketing" 
    OPERATIONS = "operations"
    FINANCE = "finance"

@dataclass
class Agent:
    agent_id: str
    role: AgentRole
    budget: float
    performance: float = 0.5
    state: str = "idle"
    active_strategies: List[str] = field(default_factory=list)
    
    def evaluate_opportunity(self, market: dict, price: float) -> float:
        base_probability = self.performance * market.get("demand_level", 0.5)
        competition_factor = 1 - market.get("competition_intensity", 0.3)
        return base_probability * competition_factor * (price / 1000)
    
    def execute(self, ledger: Ledger, market: dict) -> Optional[dict]:
        """Execute one action cycle - override in subclasses"""
        pass


# ============================================
# 5. SALES AGENT
# ============================================

class SalesAgent(Agent):
    def __init__(self, agent_id: str, budget: float = 1000):
        super().__init__(agent_id, AgentRole.SALES, budget)
        
    def execute(self, ledger: Ledger, market: dict) -> Optional[dict]:
        if self.budget < 10:
            return None
            
        # Simulate lead generation
        cost = random.uniform(5, 30)
        price = random.uniform(500, 2000)
        probability = self.evaluate_opportunity(market, price)
        
        if random.random() < probability:
            # Successful conversion
            ledger.credit(self.agent_id, price, "deal_closed")
            ledger.transfer(self.agent_id, "marketing", price * 0.15, "lead attribution")
            return {"outcome": "deal_closed", "value": price}
        else:
            # Failed attempt
            ledger.debit(self.agent_id, cost, "lead_attempt")
            return {"outcome": "attempt_failed", "cost": cost}


# ============================================
# 6. MARKETING AGENT
# ============================================

class MarketingAgent(Agent):
    def __init__(self, agent_id: str, budget: float = 500):
        super().__init__(agent_id, AgentRole.MARKETING, budget)
        
    def execute(self, ledger: Ledger, market: dict) -> Optional[dict]:
        if self.budget < 5:
            return None
            
        # Generate leads for sales
        cost = random.uniform(5, 20)
        leads_generated = int(market.get("demand_level", 0.5) * random.randint(1, 5))
        
        ledger.debit(self.agent_id, cost, "campaign")
        
        # Transfer leads to sales (conceptual)
        return {
            "outcome": "leads_generated", 
            "count": leads_generated,
            "cost": cost
        }


# ============================================
# 7. SIMULATION ENGINE
# ============================================

class EconomySimulator:
    def __init__(self):
        self.bus = EventBus()
        self.ledger = Ledger()
        self.market = MarketSimulator()
        self.agents: Dict[str, Agent] = {}
        
    def add_agent(self, agent: Agent):
        self.agents[agent.agent_id] = agent
        self.ledger.register_agent(agent.agent_id, agent.budget)
        
    async def run_cycle(self, cycle: int):
        # Step market
        market_state = self.market.step()
        self.bus.publish("market.step", market_state)
        
        # Run each agent
        results = []
        for agent_id, agent in self.agents.items():
            result = agent.execute(self.ledger, market_state)
            if result:
                results.append(result)
                self.bus.publish(f"agent.{agent_id}.result", result)
                
        # Publish ledger state
        self.bus.publish("ledger.state", self.ledger.get_ledger())
        
        return results
        
    async def run(self, cycles: int = 100, interval: float = 0.1):
        """Run simulation loop"""
        for cycle in range(cycles):
            results = await self.run_cycle(cycle)
            
            if cycle % 10 == 0:
                print(f"\n=== Cycle {cycle} ===")
                for agent_id, financials in self.ledger.get_ledger().items():
                    print(f"{agent_id}: ${financials['revenue']:.2f} revenue, "
                          f"${financials['costs']:.2f} costs, "
                          f"ROI: {financials['roi']:.2f}")
                    
            await asyncio.sleep(interval)


# ============================================
# 8. RUN IT
# ============================================

async def main():
    # Create economy
    economy = EconomySimulator()
    
    # Add agents
    economy.add_agent(SalesAgent("sales-1", budget=1000))
    economy.add_agent(SalesAgent("sales-2", budget=800))
    economy.add_agent(MarketingAgent("marketing-1", budget=500))
    economy.add_agent(MarketingAgent("marketing-2", budget=400))
    
    print("Starting Economy Simulation...")
    print(f"Initial agents: {list(economy.agents.keys())}")
    
    # Run 100 cycles
    await economy.run(cycles=100, interval=0.01)


if __name__ == "__main__":
    asyncio.run(main())

# ============================================
# USAGE
# ============================================
# Run: python economy_simulator.py
# 
# Watch agents:
# - Generate revenue (sales)
# - Spend on campaigns (marketing)  
# - Build ledger
# - Evolve based on ROI
#
# Extend with:
# - Real Kafka integration
# - External API connectors (Stripe, email)
# - Learning mutations
# - More agent types