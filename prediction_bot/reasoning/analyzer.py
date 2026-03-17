"""
Claude-powered reasoning engine.

Takes a market question + validated evidence and returns:
  - An estimated true probability
  - A recommended bet direction
  - A confidence level
  - A structured reasoning chain
"""

import json
from dataclasses import dataclass
from typing import Optional

import anthropic

from ..config import cfg
from ..markets.base import Market
from ..research.validator import ValidationReport

MODEL = "claude-sonnet-4-6"

SYSTEM_PROMPT = """You are an expert prediction market analyst and probabilistic reasoner.

Your job:
1. Read the market question and validated evidence provided.
2. Reason carefully about the true probability of the event occurring.
3. Compare your estimated probability to the current market price.
4. Identify whether a betting edge exists.

Output ONLY valid JSON matching this schema (no prose outside the JSON):
{
  "estimated_probability": <float 0.0–1.0>,
  "market_probability": <float 0.0–1.0>,
  "edge": <float, positive = YES has edge, negative = NO has edge>,
  "recommended_outcome": "YES" | "NO" | "SKIP",
  "confidence": <float 0.0–1.0>,
  "reasoning": "<2–4 sentence explanation>",
  "key_uncertainties": ["<uncertainty 1>", "<uncertainty 2>"],
  "evidence_quality": "high" | "medium" | "low"
}

Rules:
- If evidence is low quality or contradictory, set confidence ≤ 0.4 and recommended_outcome = "SKIP".
- Be calibrated: do not push probabilities to extremes without strong evidence.
- Edge = estimated_probability − market_probability.
- Only recommend betting when |edge| > 0.05 AND confidence ≥ 0.5.
"""


@dataclass
class AnalysisResult:
    market: Market
    estimated_probability: float
    market_probability: float
    edge: float
    recommended_outcome: str    # "YES", "NO", or "SKIP"
    confidence: float
    reasoning: str
    key_uncertainties: list[str]
    evidence_quality: str       # "high", "medium", "low"

    @property
    def has_edge(self) -> bool:
        return (
            self.recommended_outcome != "SKIP"
            and abs(self.edge) > cfg.MIN_EDGE
            and self.confidence >= 0.5
        )

    def summary(self) -> str:
        return (
            f"[{self.market.platform.value.upper()}] {self.market.question}\n"
            f"  Market prob: {self.market_probability:.1%} | "
            f"Est. prob: {self.estimated_probability:.1%} | "
            f"Edge: {self.edge:+.1%} | "
            f"Confidence: {self.confidence:.1%}\n"
            f"  → {self.recommended_outcome}  ({self.evidence_quality} quality evidence)\n"
            f"  {self.reasoning}"
        )


class MarketAnalyzer:
    def __init__(self) -> None:
        self._client = anthropic.Anthropic(api_key=cfg.ANTHROPIC_API_KEY)

    def analyze(
        self,
        market: Market,
        validation_report: ValidationReport,
    ) -> Optional[AnalysisResult]:
        """Run Claude reasoning over the market and its validated evidence."""
        market_prob = market.yes_price or 0.5
        user_message = self._build_prompt(market, market_prob, validation_report)

        try:
            response = self._client.messages.create(
                model=MODEL,
                max_tokens=1024,
                system=SYSTEM_PROMPT,
                messages=[{"role": "user", "content": user_message}],
            )
            raw_json = response.content[0].text.strip()
            # Strip markdown code fences if present
            if raw_json.startswith("```"):
                raw_json = raw_json.split("```")[1]
                if raw_json.startswith("json"):
                    raw_json = raw_json[4:]
            data = json.loads(raw_json)
        except (json.JSONDecodeError, IndexError, anthropic.APIError) as exc:
            print(f"[analyzer] error parsing Claude response: {exc}")
            return None

        return AnalysisResult(
            market=market,
            estimated_probability=float(data.get("estimated_probability", market_prob)),
            market_probability=float(data.get("market_probability", market_prob)),
            edge=float(data.get("edge", 0.0)),
            recommended_outcome=data.get("recommended_outcome", "SKIP"),
            confidence=float(data.get("confidence", 0.0)),
            reasoning=data.get("reasoning", ""),
            key_uncertainties=data.get("key_uncertainties", []),
            evidence_quality=data.get("evidence_quality", "low"),
        )

    # ── Private ───────────────────────────────────────────────────────────────

    def _build_prompt(
        self,
        market: Market,
        market_prob: float,
        report: ValidationReport,
    ) -> str:
        outcomes_block = "\n".join(
            f"  - {o.label}: {o.price:.1%}" for o in market.outcomes
        )
        return f"""## Market
Question: {market.question}
Description: {market.description[:500] if market.description else "(none)"}
Platform: {market.platform.value}
Current prices:
{outcomes_block}
Current YES probability: {market_prob:.1%}
Volume: ${market.volume_usd:,.0f}  Liquidity: ${market.liquidity_usd:,.0f}
Closes: {market.close_time or "unknown"}

{report.as_prompt_block()}

Analyze this market and return JSON only."""
