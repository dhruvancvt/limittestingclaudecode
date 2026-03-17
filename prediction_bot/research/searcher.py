"""
Multi-source web research using Tavily.

Tavily returns grounded, cited results — each result includes a URL, title,
content snippet, and a relevance score, making cross-referencing straightforward.
"""

from dataclasses import dataclass, field

import httpx
from tenacity import retry, stop_after_attempt, wait_exponential

from ..config import cfg

TAVILY_BASE = "https://api.tavily.com"


@dataclass
class SearchResult:
    url: str
    title: str
    content: str
    score: float          # Tavily relevance score (0–1)
    published_date: str = ""


@dataclass
class ResearchResult:
    query: str
    results: list[SearchResult] = field(default_factory=list)
    answer: str = ""      # Tavily's synthesized answer (when available)

    @property
    def top_sources(self) -> list[SearchResult]:
        return sorted(self.results, key=lambda r: r.score, reverse=True)[:5]

    def as_context_block(self) -> str:
        """Format for injection into a Claude prompt."""
        lines = [f"## Research: {self.query}\n"]
        if self.answer:
            lines.append(f"**Synthesized answer:** {self.answer}\n")
        lines.append("**Sources:**")
        for i, src in enumerate(self.top_sources, 1):
            lines.append(
                f"\n[{i}] {src.title}\n"
                f"    URL: {src.url}\n"
                f"    Score: {src.score:.2f}\n"
                f"    {src.content[:400]}..."
            )
        return "\n".join(lines)


class SourceSearcher:
    """Fetches information about a prediction market question from multiple angles."""

    def __init__(self) -> None:
        if not cfg.TAVILY_API_KEY:
            raise ValueError("TAVILY_API_KEY is required")
        self._key = cfg.TAVILY_API_KEY

    # ── Public ────────────────────────────────────────────────────────────────

    def research_question(self, question: str, context: str = "") -> list[ResearchResult]:
        """
        Run several targeted searches for a single market question.
        Returns multiple ResearchResult objects (one per search angle).
        """
        queries = self._build_queries(question, context)
        results = []
        for q in queries:
            try:
                results.append(self._search(q))
            except Exception as exc:
                # Log but continue — partial research is better than none
                print(f"[searcher] warning: query '{q}' failed: {exc}")
        return results

    # ── Private ───────────────────────────────────────────────────────────────

    def _build_queries(self, question: str, context: str) -> list[str]:
        """Generate diverse search angles to maximise coverage."""
        base = question.strip().rstrip("?")
        queries = [
            question,                              # Direct question
            f"{base} latest news",                 # Recent events
            f"{base} probability prediction",      # Expert forecasts
            f"{base} official statement",          # Primary sources
        ]
        if context:
            queries.append(f"{context} {base}")
        return queries

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
    def _search(self, query: str) -> ResearchResult:
        payload = {
            "api_key": self._key,
            "query": query,
            "search_depth": "advanced",    # Deeper crawl for more reliable facts
            "include_answer": True,        # Tavily's synthesized answer
            "include_raw_content": False,
            "max_results": 7,
            "include_domains": [           # Prioritise high-credibility domains
                "reuters.com", "apnews.com", "bbc.com", "nytimes.com",
                "theguardian.com", "wsj.com", "economist.com",
                "nature.com", "science.org", "pubmed.ncbi.nlm.nih.gov",
                "gov", "edu",
            ],
        }
        with httpx.Client(timeout=30) as client:
            resp = client.post(f"{TAVILY_BASE}/search", json=payload)
            resp.raise_for_status()
        data = resp.json()
        results = [
            SearchResult(
                url=r.get("url", ""),
                title=r.get("title", ""),
                content=r.get("content", ""),
                score=r.get("score", 0.0),
                published_date=r.get("published_date", ""),
            )
            for r in data.get("results", [])
        ]
        return ResearchResult(
            query=query,
            results=results,
            answer=data.get("answer", ""),
        )
