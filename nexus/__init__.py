"""
NEXUS — Unified 24/7 Chatbot Core

Connects ChatGPT, Perplexity, and OpenClaw into one continuous consciousness.
Memory is shared across all providers. The nexus never sleeps.

Architecture:
  User ↔ Nexus Core ↔ Provider Router
                      ├── ChatGPT (conversation, reasoning)
                      ├── Perplexity (search, research)
                      └── OpenClaw (tools, spine, daemon)
  
  All providers write to → Unified Memory (spine + vector + daily logs)
  All providers read from ← Unified Memory (context injection)

The nexus outdoes any single provider by:
1. Routing queries to the best provider for each task
2. Maintaining continuous memory across all providers
3. Operating 24/7 as a daemon, not session-bound
4. Self-improving through pattern detection (local cognition)
"""

__version__ = "0.1.0"
