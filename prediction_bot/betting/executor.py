"""
Bet executor — translates AnalysisResult + Kelly size into platform-specific orders.
"""

from dataclasses import dataclass
from typing import Optional

from ..config import cfg
from ..markets.base import Market, Platform
from ..markets.manifold import ManifoldClient
from ..markets.kalshi import KalshiClient
from ..markets.polymarket import PolymarketClient
from ..reasoning.analyzer import AnalysisResult
from .kelly import kelly_bet_size, kelly_no_bet_size


@dataclass
class BetOrder:
    market: Market
    outcome: str            # "YES" or "NO"
    size: float             # Amount in native currency
    currency: str           # "USD", "MANA", "USDC"
    estimated_prob: float
    market_prob: float
    edge: float
    dry_run: bool
    result: Optional[dict] = None


class BetExecutor:
    def __init__(
        self,
        manifold: Optional[ManifoldClient] = None,
        kalshi: Optional[KalshiClient] = None,
        polymarket: Optional[PolymarketClient] = None,
        bankroll_usd: float = 100.0,
        bankroll_mana: float = 1000.0,
    ) -> None:
        self._manifold = manifold
        self._kalshi = kalshi
        self._polymarket = polymarket
        self._bankroll_usd = bankroll_usd
        self._bankroll_mana = bankroll_mana

    def execute(self, analysis: AnalysisResult) -> Optional[BetOrder]:
        """Size and place a bet based on the analysis. Returns None if skipped."""
        if not analysis.has_edge:
            return None

        market = analysis.market
        outcome = analysis.recommended_outcome  # "YES" or "NO"

        if outcome == "YES":
            size_usd = kelly_bet_size(
                analysis.estimated_probability,
                analysis.market_probability,
                self._bankroll_usd,
            )
            size_mana = kelly_bet_size(
                analysis.estimated_probability,
                analysis.market_probability,
                self._bankroll_mana,
                max_bet=cfg.MAX_BET_MANA,
            )
        else:
            size_usd = kelly_no_bet_size(
                analysis.estimated_probability,
                analysis.market_probability,
                self._bankroll_usd,
            )
            size_mana = kelly_no_bet_size(
                analysis.estimated_probability,
                analysis.market_probability,
                self._bankroll_mana,
                max_bet=cfg.MAX_BET_MANA,
            )

        order = self._route_order(market, outcome, size_usd, size_mana, analysis)
        return order

    # ── Routing ───────────────────────────────────────────────────────────────

    def _route_order(
        self,
        market: Market,
        outcome: str,
        size_usd: float,
        size_mana: float,
        analysis: AnalysisResult,
    ) -> BetOrder:
        if market.platform == Platform.MANIFOLD:
            return self._bet_manifold(market, outcome, size_mana, analysis)
        elif market.platform == Platform.KALSHI:
            return self._bet_kalshi(market, outcome, size_usd, analysis)
        elif market.platform == Platform.POLYMARKET:
            return self._bet_polymarket(market, outcome, size_usd, analysis)
        else:
            raise ValueError(f"Unknown platform: {market.platform}")

    def _bet_manifold(
        self, market: Market, outcome: str, size: float, analysis: AnalysisResult
    ) -> BetOrder:
        size = max(size, 1.0)  # Manifold minimum
        result = None
        if self._manifold:
            result = self._manifold.place_bet(market.market_id, outcome, size)
        return BetOrder(
            market=market, outcome=outcome, size=size, currency="MANA",
            estimated_prob=analysis.estimated_probability,
            market_prob=analysis.market_probability,
            edge=analysis.edge, dry_run=cfg.DRY_RUN, result=result,
        )

    def _bet_kalshi(
        self, market: Market, outcome: str, size_usd: float, analysis: AnalysisResult
    ) -> BetOrder:
        # Kalshi trades in $0.01 contracts; round to nearest cent
        contracts = max(int(size_usd * 100), 1)
        yes_price_cents = int(analysis.market_probability * 100)
        result = None
        if self._kalshi:
            side = "yes" if outcome == "YES" else "no"
            result = self._kalshi.place_order(
                market.market_id, side, contracts, yes_price_cents
            )
        return BetOrder(
            market=market, outcome=outcome, size=contracts / 100, currency="USD",
            estimated_prob=analysis.estimated_probability,
            market_prob=analysis.market_probability,
            edge=analysis.edge, dry_run=cfg.DRY_RUN, result=result,
        )

    def _bet_polymarket(
        self, market: Market, outcome: str, size_usdc: float, analysis: AnalysisResult
    ) -> BetOrder:
        # Find the token ID for this outcome
        token_id = ""
        for o in market.outcomes:
            if o.label.upper() == outcome:
                token_id = o.token_id
                break
        result = None
        if self._polymarket and token_id:
            side = "BUY"
            result = self._polymarket.place_order(token_id, side, size_usdc)
        return BetOrder(
            market=market, outcome=outcome, size=size_usdc, currency="USDC",
            estimated_prob=analysis.estimated_probability,
            market_prob=analysis.market_probability,
            edge=analysis.edge, dry_run=cfg.DRY_RUN, result=result,
        )
