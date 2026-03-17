"""
Kelly Criterion bet sizing.

Full Kelly can be extremely aggressive. We use fractional Kelly (default 0.25×)
which dramatically reduces variance while preserving most of the EV advantage.

Formula (binary market):
  f* = (p × b − q) / b
  where b = net odds (payout − 1), p = estimated win prob, q = 1 − p

For prediction markets that pay $1 per share:
  b = (1 / market_price) − 1
  f* = (p − market_price) / (1 − market_price)
"""

from ..config import cfg


def kelly_bet_size(
    estimated_prob: float,
    market_price: float,
    bankroll: float,
    fraction: float | None = None,
    max_bet: float | None = None,
) -> float:
    """
    Calculate the fractional Kelly bet size in the same currency as bankroll.

    Args:
        estimated_prob: Our true probability estimate (0–1).
        market_price:   Current market YES price (0–1).
        bankroll:       Total available funds.
        fraction:       Kelly fraction (defaults to cfg.KELLY_FRACTION).
        max_bet:        Hard cap on bet size (defaults to cfg.MAX_BET_USD).

    Returns:
        Recommended bet size (≥ 0). Returns 0 if no edge or negative Kelly.
    """
    fraction = fraction if fraction is not None else cfg.KELLY_FRACTION
    max_bet = max_bet if max_bet is not None else cfg.MAX_BET_USD

    # Avoid division by zero at price extremes
    if market_price <= 0 or market_price >= 1:
        return 0.0

    # Net odds: how much you win per $1 risked if you're right
    b = (1.0 / market_price) - 1.0

    # Full Kelly fraction of bankroll
    q = 1.0 - estimated_prob
    full_kelly = (estimated_prob * b - q) / b

    if full_kelly <= 0:
        return 0.0  # No edge in this direction

    fractional_kelly = full_kelly * fraction
    bet = bankroll * fractional_kelly

    # Apply hard cap
    return min(bet, max_bet)


def kelly_no_bet_size(
    estimated_prob: float,
    market_price: float,
    bankroll: float,
    fraction: float | None = None,
    max_bet: float | None = None,
) -> float:
    """
    Kelly size for betting NO (equivalent to betting YES at complementary price).
    """
    return kelly_bet_size(
        estimated_prob=1.0 - estimated_prob,
        market_price=1.0 - market_price,
        bankroll=bankroll,
        fraction=fraction,
        max_bet=max_bet,
    )
