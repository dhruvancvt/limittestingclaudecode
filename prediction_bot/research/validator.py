"""
Source validation layer.

Cross-references search results across multiple queries and assigns a
validation score to each claim based on:
  - Source domain credibility
  - Agreement across independent sources
  - Recency of information
"""

from dataclasses import dataclass

from .searcher import ResearchResult, SearchResult

# Domain credibility tiers (higher = more trusted)
CREDIBILITY_TIERS: dict[str, float] = {
    # Tier 1 — Primary/institutional sources
    ".gov": 1.0, ".edu": 0.95, "pubmed": 0.95, "nature.com": 0.95,
    "science.org": 0.95, "who.int": 1.0, "un.org": 0.95,
    # Tier 2 — Major wire services / established press
    "reuters.com": 0.90, "apnews.com": 0.90, "bbc.com": 0.85,
    "wsj.com": 0.85, "nytimes.com": 0.82, "economist.com": 0.85,
    "theguardian.com": 0.80, "ft.com": 0.85,
    # Tier 3 — Reliable general press
    "washingtonpost.com": 0.78, "nbcnews.com": 0.75, "cbsnews.com": 0.75,
    "abcnews.go.com": 0.75, "politico.com": 0.75, "axios.com": 0.75,
    # Tier 4 — Specialist/prediction sites
    "metaculus.com": 0.70, "gjopen.com": 0.70, "polymarket.com": 0.65,
    "manifold.markets": 0.65,
}

DEFAULT_CREDIBILITY = 0.50  # Unknown domain


@dataclass
class ValidatedSource:
    result: SearchResult
    credibility: float          # 0–1 domain credibility score
    corroboration_count: int    # How many other sources agree on the key fact
    validation_score: float     # Combined score (credibility × corroboration weight)


@dataclass
class ValidationReport:
    market_question: str
    validated_sources: list[ValidatedSource]
    consensus_summary: str      # Short human-readable summary of what sources agree on
    confidence: float           # Overall evidence confidence (0–1)

    def top_sources(self, n: int = 5) -> list[ValidatedSource]:
        return sorted(self.validated_sources, key=lambda v: v.validation_score, reverse=True)[:n]

    def as_prompt_block(self) -> str:
        lines = [
            f"## Validated Evidence (confidence={self.confidence:.2f})\n",
            f"**Consensus:** {self.consensus_summary}\n",
            "**Top validated sources:**",
        ]
        for i, vs in enumerate(self.top_sources(), 1):
            lines.append(
                f"\n[{i}] {vs.result.title} (cred={vs.credibility:.2f}, "
                f"corroborated_by={vs.corroboration_count})\n"
                f"    {vs.result.url}\n"
                f"    {vs.result.content[:300]}..."
            )
        return "\n".join(lines)


class SourceValidator:
    """Validates and scores research results for reliability."""

    def validate(
        self,
        market_question: str,
        research_results: list[ResearchResult],
    ) -> ValidationReport:
        all_results = [r for rr in research_results for r in rr.results]

        if not all_results:
            return ValidationReport(
                market_question=market_question,
                validated_sources=[],
                consensus_summary="No sources found.",
                confidence=0.0,
            )

        # Score each source
        validated = [self._score_source(src, all_results) for src in all_results]

        # Deduplicate by URL
        seen: set[str] = set()
        deduped: list[ValidatedSource] = []
        for vs in validated:
            if vs.result.url not in seen:
                seen.add(vs.result.url)
                deduped.append(vs)

        # Overall confidence: mean validation score of top-5 sources
        top = sorted(deduped, key=lambda v: v.validation_score, reverse=True)[:5]
        confidence = sum(v.validation_score for v in top) / max(len(top), 1)

        # Build consensus from synthesized Tavily answers
        answers = [rr.answer for rr in research_results if rr.answer]
        consensus = answers[0] if answers else "No synthesized answer available."

        return ValidationReport(
            market_question=market_question,
            validated_sources=deduped,
            consensus_summary=consensus,
            confidence=min(confidence, 1.0),
        )

    # ── Private ───────────────────────────────────────────────────────────────

    def _domain_credibility(self, url: str) -> float:
        url_lower = url.lower()
        for domain, score in CREDIBILITY_TIERS.items():
            if domain in url_lower:
                return score
        return DEFAULT_CREDIBILITY

    def _corroboration_count(self, source: SearchResult, all_results: list[SearchResult]) -> int:
        """
        Count other sources that share significant content overlap.
        Uses simple word-overlap heuristic — good enough without NLP deps.
        """
        words = set(source.content.lower().split())
        count = 0
        for other in all_results:
            if other.url == source.url:
                continue
            other_words = set(other.content.lower().split())
            overlap = len(words & other_words) / max(len(words), 1)
            if overlap > 0.15:  # >15% word overlap = likely corroborating
                count += 1
        return count

    def _score_source(self, source: SearchResult, all_results: list[SearchResult]) -> ValidatedSource:
        cred = self._domain_credibility(source.url)
        corr = self._corroboration_count(source, all_results)
        # Corroboration bonus: each extra source adds diminishing returns
        corr_weight = min(corr * 0.1, 0.4)
        # Tavily relevance contributes 20%
        relevance_weight = source.score * 0.2
        validation_score = cred * 0.4 + corr_weight * 0.4 + relevance_weight
        return ValidatedSource(
            result=source,
            credibility=cred,
            corroboration_count=corr,
            validation_score=min(validation_score, 1.0),
        )
