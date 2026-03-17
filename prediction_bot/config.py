"""Central configuration loaded from environment variables."""

import os
from dotenv import load_dotenv

load_dotenv()


class Config:
    # Anthropic
    ANTHROPIC_API_KEY: str = os.getenv("ANTHROPIC_API_KEY", "")

    # Tavily
    TAVILY_API_KEY: str = os.getenv("TAVILY_API_KEY", "")

    # Polymarket
    POLYMARKET_PRIVATE_KEY: str = os.getenv("POLYMARKET_PRIVATE_KEY", "")

    # Kalshi
    KALSHI_API_KEY: str = os.getenv("KALSHI_API_KEY", "")
    KALSHI_EMAIL: str = os.getenv("KALSHI_EMAIL", "")
    KALSHI_PASSWORD: str = os.getenv("KALSHI_PASSWORD", "")

    # Manifold
    MANIFOLD_API_KEY: str = os.getenv("MANIFOLD_API_KEY", "")

    # ── Budget ─────────────────────────────────────────────────────────────────
    # The bot has exactly $50 to survive. This covers API costs AND real bets.
    # Manifold uses play-money (Mana), so Manifold bets are free.
    # Kalshi / Polymarket bets come out of the same $50 as API costs.
    TOTAL_BUDGET_USD: float = float(os.getenv("TOTAL_BUDGET_USD", "50"))

    # ── Bot behaviour ──────────────────────────────────────────────────────────
    DRY_RUN: bool = os.getenv("DRY_RUN", "true").lower() == "true"
    MAX_BET_USD: float = float(os.getenv("MAX_BET_USD", "5"))       # Lowered: preserve budget
    MAX_BET_MANA: float = float(os.getenv("MAX_BET_MANA", "100"))
    KELLY_FRACTION: float = float(os.getenv("KELLY_FRACTION", "0.25"))
    MIN_EDGE: float = float(os.getenv("MIN_EDGE", "0.05"))

    @classmethod
    def validate(cls) -> None:
        if not cls.ANTHROPIC_API_KEY:
            raise ValueError("ANTHROPIC_API_KEY is required")
        if not cls.TAVILY_API_KEY:
            raise ValueError("TAVILY_API_KEY is required for source validation")


cfg = Config()
