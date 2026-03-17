"""Kalshi client (US-regulated real-money prediction market)."""

import httpx
from tenacity import retry, stop_after_attempt, wait_exponential

from ..config import cfg
from .base import Market, MarketOutcome, Platform


BASE_URL = "https://api.elections.kalshi.com/trade-api/v2"
DEMO_URL = "https://demo-api.kalshi.co/trade-api/v2"


class KalshiClient:
    def __init__(self, demo: bool = False) -> None:
        self._base = DEMO_URL if demo else BASE_URL
        self._token: str | None = None

    # ── Auth ──────────────────────────────────────────────────────────────────

    def login(self) -> None:
        """Exchange email/password for a session token."""
        if not cfg.KALSHI_EMAIL or not cfg.KALSHI_PASSWORD:
            raise ValueError("KALSHI_EMAIL and KALSHI_PASSWORD are required")
        with httpx.Client(timeout=15) as client:
            resp = client.post(
                f"{self._base}/log_in",
                json={"email": cfg.KALSHI_EMAIL, "password": cfg.KALSHI_PASSWORD},
            )
            resp.raise_for_status()
        self._token = resp.json()["token"]

    @property
    def _auth_headers(self) -> dict:
        if not self._token:
            raise RuntimeError("Call .login() before making authenticated requests")
        return {"Authorization": f"Bearer {self._token}"}

    # ── Public ────────────────────────────────────────────────────────────────

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
    def fetch_markets(self, limit: int = 50) -> list[Market]:
        """Fetch open markets."""
        params = {"limit": limit, "status": "open"}
        with httpx.Client(timeout=15) as client:
            resp = client.get(f"{self._base}/markets", params=params)
            resp.raise_for_status()
        return [self._parse(m) for m in resp.json().get("markets", [])]

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
    def place_order(
        self,
        ticker: str,
        side: str,       # "yes" or "no"
        count: int,      # number of contracts
        yes_price: int,  # price in cents (1–99)
    ) -> dict:
        """Place a limit order. Respects DRY_RUN."""
        if cfg.DRY_RUN:
            return {"dry_run": True, "ticker": ticker, "side": side, "count": count}
        payload = {
            "ticker": ticker,
            "client_order_id": f"bot_{ticker}_{side}",
            "type": "limit",
            "action": "buy",
            "side": side,
            "count": count,
            "yes_price": yes_price,
        }
        with httpx.Client(timeout=15) as client:
            resp = client.post(
                f"{self._base}/orders",
                json=payload,
                headers=self._auth_headers,
            )
            resp.raise_for_status()
        return resp.json()

    # ── Private ───────────────────────────────────────────────────────────────

    def _parse(self, raw: dict) -> Market:
        yes_ask = raw.get("yes_ask", 50)  # cents
        no_ask = raw.get("no_ask", 50)
        yes_prob = yes_ask / 100.0
        outcomes = [
            MarketOutcome(label="YES", token_id=f"{raw['ticker']}:YES", price=yes_prob),
            MarketOutcome(label="NO",  token_id=f"{raw['ticker']}:NO",  price=no_ask / 100.0),
        ]
        return Market(
            platform=Platform.KALSHI,
            market_id=raw["ticker"],
            question=raw.get("title", ""),
            description=raw.get("rules_primary", ""),
            outcomes=outcomes,
            close_time=raw.get("close_time"),
            volume_usd=raw.get("volume", 0) / 100,  # cents → dollars
            liquidity_usd=raw.get("liquidity", 0) / 100,
            url=f"https://kalshi.com/markets/{raw['ticker']}",
            raw=raw,
        )
