"""Shared data models for prediction markets."""

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class Platform(str, Enum):
    MANIFOLD = "manifold"
    KALSHI = "kalshi"
    POLYMARKET = "polymarket"


@dataclass
class MarketOutcome:
    """A single binary or multi-outcome option within a market."""
    label: str          # e.g. "Yes", "No", "Candidate X"
    token_id: str       # Platform-specific ID for placing orders
    price: float        # Current market probability (0–1)


@dataclass
class Market:
    """Unified market representation across all platforms."""
    platform: Platform
    market_id: str
    question: str
    description: str
    outcomes: list[MarketOutcome]
    close_time: Optional[str]       # ISO-8601 or None
    volume_usd: float               # Traded volume in USD equivalent
    liquidity_usd: float            # Available liquidity
    url: str
    raw: dict = field(default_factory=dict, repr=False)

    @property
    def is_binary(self) -> bool:
        return len(self.outcomes) == 2

    @property
    def yes_price(self) -> Optional[float]:
        """For binary markets, return the YES probability."""
        for o in self.outcomes:
            if o.label.lower() in ("yes", "true", "1"):
                return o.price
        return self.outcomes[0].price if self.outcomes else None
