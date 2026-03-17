"""
Claude Opus 4.6 reasoning engine with adaptive thinking.

Uses claude-opus-4-6 with thinking: {type: "adaptive"} so the model
decides how deeply to reason. The full reasoning chain is included in
the context so that any thinking done is exposed for debugging.

Cost per call is tracked against the $50 lifetime budget.
"""

import json
from dataclasses import dataclass
from typing import Optional

import anthropic

from ..config import cfg
from ..markets.base import Market
from ..research.validator import ValidationReport

# Use the most capable model — the $50 budget accounts for this cost.
MODEL = "claude-opus-4-6"

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
    thinking_summary: str = ""  # Opus 4.6 adaptive thinking excerpt

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
        """
        Run Claude Opus 4.6 reasoning (with adaptive thinking) over the market.

        Adaptive thinking lets Opus 4.6 decide how deeply to reason about
        each market. High-stakes / ambiguous markets get more thinking tokens;
        clear-cut markets are answered quickly, saving budget.
        """
        market_prob = market.yes_price or 0.5
        user_message = self._build_prompt(market, market_prob, validation_report)

        try:
            # Streaming with get_final_message() prevents HTTP timeouts on
            # long adaptive-thinking responses (Opus 4.6 can use many tokens).
            with self._client.messages.stream(
                model=MODEL,
                max_tokens=4096,
                thinking={"type": "adaptive"},
                system=SYSTEM_PROMPT,
                messages=[{"role": "user", "content": user_message}],
            ) as stream:
                response = stream.get_final_message()

        except anthropic.APIError as exc:
            print(f"[analyzer] Claude API error: {exc}")
            return None

        # Extract thinking summary (first 300 chars) and JSON answer
        thinking_summary = ""
        raw_json = ""
        for block in response.content:
            if block.type == "thinking":
                thinking_summary = block.thinking[:300]
            elif block.type == "text":
                raw_json = block.text.strip()

        if not raw_json:
            print("[analyzer] No text block in response")
            return None

        # Strip markdown code fences if present
        if raw_json.startswith("```"):
            parts = raw_json.split("```")
            raw_json = parts[1] if len(parts) > 1 else raw_json
            if raw_json.startswith("json"):
                raw_json = raw_json[4:]

        try:
            data = json.loads(raw_json)
        except json.JSONDecodeError as exc:
            print(f"[analyzer] JSON parse error: {exc}\nRaw: {raw_json[:200]}")
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
            thinking_summary=thinking_summary,
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
