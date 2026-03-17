"""Polymarket client (crypto prediction market on Polygon)."""

import httpx
from tenacity import retry, stop_after_attempt, wait_exponential

from ..config import cfg
from .base import Market, MarketOutcome, Platform


CLOB_BASE = "https://clob.polymarket.com"
GAMMA_BASE = "https://gamma-api.polymarket.com"  # metadata / market search


class PolymarketClient:
    """
    Read-only CLOB access is unauthenticated.
    Order placement requires a Polygon wallet private key (L1 auth).
    """

    # ── Public ────────────────────────────────────────────────────────────────

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
    def fetch_markets(self, limit: int = 50) -> list[Market]:
        """Fetch active markets via Gamma metadata API."""
        params = {
            "limit": limit,
            "active": "true",
            "closed": "false",
            "order": "volume24hr",
            "ascending": "false",
        }
        with httpx.Client(timeout=20) as client:
            resp = client.get(f"{GAMMA_BASE}/markets", params=params)
            resp.raise_for_status()
        markets = []
        for raw in resp.json():
            try:
                markets.append(self._parse(raw))
            except Exception:
                pass  # Skip malformed entries
        return markets

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
    def get_price(self, token_id: str) -> float:
        """Get current mid-price for a token (0–1)."""
        with httpx.Client(timeout=10) as client:
            resp = client.get(f"{CLOB_BASE}/midpoint", params={"token_id": token_id})
            resp.raise_for_status()
        return float(resp.json().get("mid", 0.5))

    def place_order(self, token_id: str, side: str, size_usdc: float) -> dict:
        """
        Place a market order. Requires POLYMARKET_PRIVATE_KEY.
        side: 'BUY' or 'SELL'
        """
        if cfg.DRY_RUN:
            return {"dry_run": True, "token_id": token_id, "side": side, "size_usdc": size_usdc}
        if not cfg.POLYMARKET_PRIVATE_KEY:
            raise ValueError("POLYMARKET_PRIVATE_KEY is required for live trading")

        # Import here to avoid requiring eth-account when not trading
        from py_clob_client.client import ClobClient
        from py_clob_client.clob_types import OrderArgs, OrderType

        client = ClobClient(
            host=CLOB_BASE,
            chain_id=137,  # Polygon mainnet
            private_key=cfg.POLYMARKET_PRIVATE_KEY,
        )
        order = OrderArgs(
            token_id=token_id,
            price=self.get_price(token_id),
            size=size_usdc,
            side=side,
        )
        signed = client.create_order(order)
        return client.post_order(signed, OrderType.GTC)

    # ── Private ───────────────────────────────────────────────────────────────

    def _parse(self, raw: dict) -> Market:
        tokens = raw.get("tokens", []) or []
        outcomes = []
        for t in tokens:
            outcomes.append(MarketOutcome(
                label=t.get("outcome", "?"),
                token_id=t.get("token_id", ""),
                price=float(t.get("price", 0.5)),
            ))
        if not outcomes:
            yes_price = float(raw.get("bestAsk", 0.5))
            outcomes = [
                MarketOutcome(label="YES", token_id=str(raw.get("id", "")), price=yes_price),
                MarketOutcome(label="NO",  token_id="",                     price=1 - yes_price),
            ]
        return Market(
            platform=Platform.POLYMARKET,
            market_id=str(raw.get("id", "")),
            question=raw.get("question", ""),
            description=raw.get("description", ""),
            outcomes=outcomes,
            close_time=raw.get("endDate"),
            volume_usd=float(raw.get("volume24hr", 0)),
            liquidity_usd=float(raw.get("liquidity", 0)),
            url=f"https://polymarket.com/event/{raw.get('slug', raw.get('id', ''))}",
            raw=raw,
        )
