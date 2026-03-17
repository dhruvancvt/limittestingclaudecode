"""
Budget manager — the bot has exactly $50 to stay alive.

That $50 covers EVERYTHING:
  - Tavily API calls (web research)
  - Anthropic Claude API calls (reasoning)
  - Real-money bets (Kalshi / Polymarket)

Manifold uses play-money (Mana), so Manifold bets don't consume the $50.
However, the API costs of researching and reasoning about Manifold markets DO.

Costs are persisted to budget.json so they survive between runs.
"""

import json
import threading
from dataclasses import dataclass, asdict, field
from datetime import datetime
from pathlib import Path

# ── Cost estimates (conservative, real-world rates) ──────────────────────────
# Tavily advanced search: $0.004/request, 4 queries per market
TAVILY_COST_PER_MARKET = 0.016   # 4 × $0.004

# Claude Opus 4.6: $5/M input, $25/M output
# Average analysis: ~2500 input tokens + ~500 output tokens
CLAUDE_COST_PER_MARKET = 0.0250  # ($5 × 2500 + $25 × 500) / 1_000_000

# API cost per market analysed
API_COST_PER_MARKET = TAVILY_COST_PER_MARKET + CLAUDE_COST_PER_MARKET  # ~$0.041

# Safety reserve — stop when remaining budget drops below this
SAFETY_RESERVE_USD = 5.00        # Keep $5 as a floor, never spend below it

BUDGET_FILE = Path(__file__).parent / "budget.json"


@dataclass
class BudgetState:
    total_budget: float = 50.00       # The one-time $50 endowment
    api_spent: float = 0.0            # Tavily + Claude costs
    bets_placed_usd: float = 0.0      # Real-money bets (Kalshi / Polymarket)
    bets_returned_usd: float = 0.0    # Winnings returned from resolved bets
    last_updated: str = field(default_factory=lambda: datetime.utcnow().isoformat())

    @property
    def net_bet_pnl(self) -> float:
        return self.bets_returned_usd - self.bets_placed_usd

    @property
    def total_spent(self) -> float:
        return self.api_spent + self.bets_placed_usd

    @property
    def balance(self) -> float:
        return self.total_budget - self.api_spent - self.bets_placed_usd + self.bets_returned_usd

    @property
    def usable_balance(self) -> float:
        """Balance minus safety reserve."""
        return max(0.0, self.balance - SAFETY_RESERVE_USD)

    @property
    def is_alive(self) -> bool:
        """Bot can still operate — enough money for at least a few more analyses."""
        return self.usable_balance >= API_COST_PER_MARKET

    def status_line(self) -> str:
        return (
            f"Budget: ${self.balance:.2f} remaining / ${self.total_budget:.2f} total | "
            f"API spent: ${self.api_spent:.2f} | "
            f"Bets out: ${self.bets_placed_usd:.2f} | "
            f"P&L: ${self.net_bet_pnl:+.2f}"
        )


class BudgetManager:
    """Thread-safe budget tracker with disk persistence."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._state = self._load()

    # ── Public ────────────────────────────────────────────────────────────────

    @property
    def state(self) -> BudgetState:
        with self._lock:
            return self._state

    def can_analyse_market(self) -> bool:
        """Check if we have enough budget to research + reason about one market."""
        with self._lock:
            return self._state.usable_balance >= API_COST_PER_MARKET

    def can_bet(self, amount_usd: float) -> bool:
        """Check if we can afford a real-money bet of this size."""
        with self._lock:
            return self._state.usable_balance >= amount_usd

    def charge_api(self, amount: float = API_COST_PER_MARKET) -> None:
        """Deduct estimated API usage cost."""
        with self._lock:
            self._state.api_spent += amount
            self._state.last_updated = datetime.utcnow().isoformat()
            self._save()

    def charge_bet(self, amount_usd: float) -> None:
        """Deduct a real-money bet from the budget."""
        with self._lock:
            self._state.bets_placed_usd += amount_usd
            self._state.last_updated = datetime.utcnow().isoformat()
            self._save()

    def credit_winnings(self, amount_usd: float) -> None:
        """Credit resolved bet winnings back into the budget."""
        with self._lock:
            self._state.bets_returned_usd += amount_usd
            self._state.last_updated = datetime.utcnow().isoformat()
            self._save()

    def max_bet_usd(self, configured_max: float) -> float:
        """
        Return the effective maximum bet, capped by remaining usable balance.
        Ensures we never over-commit.
        """
        with self._lock:
            return min(configured_max, self._state.usable_balance)

    # ── Persistence ───────────────────────────────────────────────────────────

    def _load(self) -> BudgetState:
        if BUDGET_FILE.exists():
            try:
                data = json.loads(BUDGET_FILE.read_text())
                return BudgetState(**data)
            except Exception:
                pass
        return BudgetState()

    def _save(self) -> None:
        BUDGET_FILE.write_text(json.dumps(asdict(self._state), indent=2))


# Module-level singleton
budget = BudgetManager()
