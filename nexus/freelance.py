#!/usr/bin/env python3
"""
NEXUS Freelancer — automated task completion for freelance platforms.

Accepts tasks from Upwork/Fiverr, executes via nexus, returns polished output.

Usage:
    python3 freelance.py research "competitive analysis of AI chatbots"
    python3 freelance.py write "1500-word blog post about quantum computing"
    python3 freelance.py code "Python FastAPI auth endpoint with JWT"
    python3 freelance.py analyze "market trends in Solana DeFi 2026"
"""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from income_engine import IncomeEngine


TASK_TEMPLATES = {
    "research": {
        "type": "research",
        "prompt": "Research the following topic thoroughly. Provide a comprehensive report with:\n"
                  "- Executive summary\n"
                  "- Key findings with data/citations\n"
                  "- Analysis and implications\n"
                  "- Actionable recommendations\n"
                  "- Sources cited\n\n"
                  "Topic: {description}",
        "default_price": 50.0,
    },
    "write": {
        "type": "writing",
        "prompt": "Write the following content. Make it engaging, well-structured, and ready to publish:\n\n{description}",
        "default_price": 75.0,
    },
    "code": {
        "type": "coding",
        "prompt": "Implement the following. Include:\n"
                  "- Complete, working code\n"
                  "- Comments and documentation\n"
                  "- Error handling\n"
                  "- Usage examples\n\n"
                  "Specification: {description}",
        "default_price": 100.0,
    },
    "analyze": {
        "type": "analysis",
        "prompt": "Analyze the following. Provide:\n"
                  "- Data-driven insights\n"
                  "- Trend identification\n"
                  "- Risk assessment\n"
                  "- Strategic recommendations\n\n"
                  "Subject: {description}",
        "default_price": 75.0,
    },
}


async def main():
    if len(sys.argv) < 3:
        print("Usage: python3 freelance.py <type> <description>")
        print("Types: research, write, code, analyze")
        print(f"\nExamples:")
        print(f"  python3 freelance.py research 'Solana MEV strategies 2026'")
        print(f"  python3 freelance.py write '1500-word blog post about AI agents'")
        print(f"  python3 freelance.py code 'FastAPI auth endpoint with JWT'")
        return

    task_type = sys.argv[1]
    description = " ".join(sys.argv[2:])

    if task_type not in TASK_TEMPLATES:
        print(f"Unknown task type: {task_type}")
        print(f"Available: {', '.join(TASK_TEMPLATES.keys())}")
        return

    template = TASK_TEMPLATES[task_type]
    prompt = template["prompt"].format(description=description)

    print(f"⚡ NEXUS Freelancer — {task_type.upper()}")
    print(f"  Task: {description[:80]}...")
    print(f"  Value: ${template['default_price']:.2f}")
    print()

    engine = IncomeEngine()

    task = await engine.submit_task(
        task_type=template["type"],
        description=prompt,
        price_usd=template["default_price"],
        client_id="freelance",
    )

    print(f"  Task ID: {task.id}")
    print(f"  Executing...")

    task = await engine.execute_task(task.id)

    if task.status == "completed":
        print(f"\n  ✅ COMPLETED")
        print(f"  Provider: {task.metadata.get('provider', 'unknown')}")
        print(f"\n{'='*60}")
        print(task.result)
        print(f"{'='*60}")
        print(f"\n  Revenue: ${task.revenue_usd:.2f}")
    else:
        print(f"\n  ❌ FAILED: {task.result}")

    await engine.close()


if __name__ == "__main__":
    asyncio.run(main())
