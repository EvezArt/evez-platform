"""
EVEZ Search — AI-powered research engine with citations.

Replaces: Perplexity Pro ($20/mo)
Cost: Free (DuckDuckGo + local LLM synthesis)
"""

import json
import logging
from typing import List, Dict, Any, AsyncGenerator
from dataclasses import dataclass

import httpx

logger = logging.getLogger("evez.search")


@dataclass
class SearchResult:
    title: str
    url: str
    snippet: str
    source: str = "web"

    def to_dict(self):
        return {"title": self.title, "url": self.url, "snippet": self.snippet, "source": self.source}


class SearchEngine:
    """
    Multi-source search aggregation:
    1. DuckDuckGo (free, no API key)
    2. Direct URL fetch + extraction
    3. AI synthesis with citations
    """

    def __init__(self, model_provider=None):
        self.models = model_provider

    async def search(self, query: str, max_results: int = 8) -> List[SearchResult]:
        """Search across all sources."""
        results = []

        # DuckDuckGo
        ddg_results = await self._ddg_search(query, max_results)
        results.extend(ddg_results)

        return results

    async def _ddg_search(self, query: str, max_results: int) -> List[SearchResult]:
        try:
            from duckduckgo_search import DDGS
            raw = DDGS().text(query, max_results=max_results)
            return [
                SearchResult(
                    title=r["title"],
                    url=r["href"],
                    snippet=r["body"],
                    source="duckduckgo"
                )
                for r in raw
            ]
        except Exception as e:
            logger.error("DuckDuckGo search failed: %s", e)
            return []

    async def research(self, query: str, max_results: int = 8) -> Dict[str, Any]:
        """
        Full research pipeline:
        1. Search for sources
        2. Fetch top results for deeper content
        3. Synthesize answer with citations
        """
        # Step 1: Search
        results = await self.search(query, max_results)

        if not results:
            return {
                "query": query,
                "answer": "No results found. Try a different search query.",
                "sources": [],
                "citations": [],
            }

        # Step 2: Fetch top 3 for deeper content
        fetched = []
        for result in results[:3]:
            content = await self._fetch_page(result.url)
            if content:
                fetched.append({
                    "title": result.title,
                    "url": result.url,
                    "content": content[:3000],
                })

        # Step 3: Synthesize
        if self.models:
            answer = await self._synthesize(query, results, fetched)
        else:
            answer = self._format_results_only(query, results)

        return {
            "query": query,
            "answer": answer,
            "sources": [r.to_dict() for r in results],
            "citations": [{"title": r.title, "url": r.url} for r in results[:5]],
        }

    async def _fetch_page(self, url: str) -> str:
        try:
            from bs4 import BeautifulSoup
            async with httpx.AsyncClient(timeout=10, follow_redirects=True) as client:
                r = await client.get(url, headers={"User-Agent": "EVEZ-Search/1.0"})
                soup = BeautifulSoup(r.text, "html.parser")
                for tag in soup(["script", "style", "nav", "footer", "header"]):
                    tag.decompose()
                return soup.get_text(separator="\n", strip=True)[:3000]
        except Exception:
            return ""

    async def _synthesize(self, query: str, results: List[SearchResult],
                          fetched: list) -> str:
        """Use AI to synthesize a research answer with citations."""

        sources_text = ""
        for i, r in enumerate(results[:8], 1):
            sources_text += f"[{i}] {r.title}\n    {r.url}\n    {r.snippet}\n\n"

        # Add fetched content
        extra_context = ""
        for f in fetched:
            extra_context += f"\n--- {f['title']} ({f['url']}) ---\n{f['content'][:1500]}\n"

        prompt = f"""Research query: {query}

Sources found:
{sources_text}
Additional context from top pages:
{extra_context}

Synthesize a comprehensive answer to the query. Use inline citations like [1], [2] etc. to reference sources. Be accurate, cite claims, and note disagreements between sources. Format in markdown."""

        messages = [
            {"role": "system", "content": "You are a research assistant. Provide accurate, well-cited answers based on the provided sources. Always cite sources with [number] notation."},
            {"role": "user", "content": prompt}
        ]

        try:
            response = ""
            async for chunk in self.models.chat(messages, stream=False):
                response = chunk if chunk else response
                break
            return response or self._format_results_only(query, results)
        except Exception as e:
            logger.error("Synthesis failed: %s", e)
            return self._format_results_only(query, results)

    def _format_results_only(self, query: str, results: List[SearchResult]) -> str:
        """Fallback: format results without AI synthesis."""
        text = f"## Search Results for: {query}\n\n"
        for i, r in enumerate(results, 1):
            text += f"**[{i}] [{r.title}]({r.url})**\n{r.snippet}\n\n"
        return text
