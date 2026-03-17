"""Manifold Markets client (play-money + real-money sweepstakes)."""

import httpx
from tenacity import retry, stop_after_attempt, wait_exponential

from ..config import cfg
from .base import Market, MarketOutcome, Platform


BASE_URL = "https://api.manifold.markets"


class ManifoldClient:
    def __init__(self) -> None:
        self._headers = {"Authorization": f"Key {cfg.MANIFOLD_API_KEY}"}

    # ── Public ────────────────────────────────────────────────────────────────

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
    def fetch_markets(
        self,
        limit: int = 50,
        sort: str = "liquidity",
        filter_: str = "open",
    ) -> list[Market]:
        """Fetch open markets sorted by liquidity."""
        params = {
            "limit": limit,
            "sort": sort,
            "filter": filter_,
            "contractType": "BINARY",  # Focus on binary YES/NO markets
        }
        with httpx.Client(timeout=15) as client:
            resp = client.get(f"{BASE_URL}/markets", params=params)
            resp.raise_for_status()
        return [self._parse(m) for m in resp.json()]

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
    def place_bet(self, contract_id: str, outcome: str, amount: float) -> dict:
        """Place a bet. outcome='YES' or 'NO'. amount in Mana."""
        if cfg.DRY_RUN:
            return {"dry_run": True, "contract_id": contract_id, "outcome": outcome, "amount": amount}
        payload = {"contractId": contract_id, "outcome": outcome, "amount": int(amount)}
        with httpx.Client(timeout=15) as client:
            resp = client.post(
                f"{BASE_URL}/bet",
                json=payload,
                headers=self._headers,
            )
            resp.raise_for_status()
        return resp.json()

    # ── Private ───────────────────────────────────────────────────────────────

    def _parse(self, raw: dict) -> Market:
        prob = raw.get("probability", 0.5)
        outcomes = [
            MarketOutcome(label="YES", token_id=f"{raw['id']}:YES", price=prob),
            MarketOutcome(label="NO",  token_id=f"{raw['id']}:NO",  price=1 - prob),
        ]
        return Market(
            platform=Platform.MANIFOLD,
            market_id=raw["id"],
            question=raw.get("question", ""),
            description=raw.get("description", "") if isinstance(raw.get("description"), str) else "",
            outcomes=outcomes,
            close_time=raw.get("closeTime"),
            volume_usd=raw.get("volume", 0) / 100,  # Mana → rough USD equiv
            liquidity_usd=raw.get("totalLiquidity", 0) / 100,
            url=raw.get("url", f"https://manifold.markets/market/{raw['id']}"),
            raw=raw,
        )
