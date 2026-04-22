# ASYNC EVENT-DRIVEN ORCHESTRATION
# Microsoft Agent Framework Pattern (AutoGen + Semantic Kernel)

from asyncio import Queue, create_task, gather
from dataclasses import dataclass
from typing import Dict, List, Optional, Callable
from enum import Enum
import time

class AgentState(Enum):
    IDLE = "idle"
    THINKING = "thinking"
    ACTING = "acting"
    WAITING = "waiting"
    DONE = "done"
    ERROR = "error"

@dataclass
class AgentMessage:
    id: str
    sender: str
    receiver: str
    content: dict
    conversation_id: str
    timestamp: float

class AsyncAgent:
    """Async agent that can negotiate and delegate"""
    
    def __init__(self, name: str):
        self.name = name
        self.state = AgentState.IDLE
        self.inbox = Queue()
        self.capabilities: List[str] = []
        self.memory: List[dict] = []
        
    async def receive(self, msg: AgentMessage):
        await self.inbox.put(msg)
        
    async def process(self) -> Optional[AgentMessage]:
        msg = await self.inbox.get()
        self.state = AgentState.THINKING
        
        # Process message
        response = await self.think(msg)
        
        self.state = AgentState.DONE
        return response
    
    async def think(self, msg: AgentMessage) -> AgentMessage:
        # LLM reasoning here
        return AgentMessage(
            id=f"resp-{msg.id}",
            sender=self.name,
            receiver=msg.sender,
            content={"response": "thought process complete"},
            conversation_id=msg.conversation_id,
            timestamp=time.time()
        )
        
class Orchestrator:
    """Multi-agent async orchestration"""
    
    def __init__(self):
        self.agents: Dict[str, AsyncAgent] = {}
        self.conversations: Dict[str, List[AgentMessage]] = {}
        
    def register(self, agent: AsyncAgent):
        self.agents[agent.name] = agent
        
    async def broadcast(self, msg: AgentMessage):
        """Send to all agents"""
        tasks = [agent.receive(msg) for agent in self.agents.values()]
        await gather(*tasks)
        
    async def delegate(self, from_agent: str, to_agent: str, msg: dict):
        """Delegate to specific agent"""
        if to_agent in self.agents:
            message = AgentMessage(
                id=msg.get("id", "delegate-1"),
                sender=from_agent,
                receiver=to_agent,
                content=msg,
                conversation_id=msg.get("conversation_id", "default"),
                timestamp=time.time()
            )
            await self.agents[to_agent].receive(message)
            
    async def negotiate(self, topic: str, agents: List[str]):
        """Multi-agent negotiation"""
        msg = AgentMessage(
            id=f"nego-{topic}",
            sender="orchestrator",
            receiver="all",
            content={"topic": topic, "type": "negotiation"},
            conversation_id=topic,
            timestamp=time.time()
        )
        
        # All agents respond
        tasks = [self.agents[a].process() for a in agents]
        responses = await gather(*tasks, return_exceptions=True)
        
        return [r for r in responses if not isinstance(r, Exception)]

# Usage
async def main():
    orch = Orchestrator()
    
    # Register agents
    sales = AsyncAgent("sales")
    marketing = AsyncAgent("marketing")
    closer = AsyncAgent("closer")
    
    orch.register(sales)
    orch.register(marketing)
    orch.register(closer)
    
    # Negotiation
    result = await orch.negotiate("pricing-strategy", ["sales", "marketing", "closer"])
    
    print(f"Negotiation result: {result}")

# The key difference from sync:
# - Agents don't block each other
# - Real concurrent execution
# - Human can interject mid-conversation
# - Conversations are stateful