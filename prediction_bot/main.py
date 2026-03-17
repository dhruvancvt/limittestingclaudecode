"""
Prediction Market Bot — main entry point.

The bot has a $50 lifetime budget covering:
  - Tavily web-search API calls  (~$0.004 / search × 4 searches = ~$0.016/market)
  - Claude Opus 4.6 reasoning   (~$0.025 / market analysis)
  - Real-money bets on Kalshi / Polymarket (Manifold is play-money, free)

Total API cost per market ≈ $0.041.  With $50 that's ≈ 1,200 market analyses,
but the safe split is roughly $20 API + $30 betting bankroll.

Flow per market:
  1. Budget check — skip if we can't afford the API call
  2. Fetch markets from enabled platforms
  3. Research each question with Tavily (multi-angle web search)
  4. Validate & cross-reference sources
  5. Reason with Claude Opus 4.6 (adaptive thinking) to estimate probability
  6. Size bet with fractional Kelly Criterion
  7. Budget check — cap real bets to remaining balance
  8. Execute (or dry-run) on the platform
  9. Charge API cost to budget

Usage:
  python -m prediction_bot.main --platforms manifold polymarket kalshi \\
      --limit 20 --max-bets 3
"""

import argparse
import sys
from typing import Optional

from rich.console import Console
from rich.table import Table
from rich import box

from .budget import budget as budget_mgr, API_COST_PER_MARKET, SAFETY_RESERVE_USD
from .config import cfg
from .markets.base import Market, Platform
from .markets.manifold import ManifoldClient
from .markets.kalshi import KalshiClient
from .markets.polymarket import PolymarketClient
from .research.searcher import SourceSearcher
from .research.validator import SourceValidator
from .reasoning.analyzer import MarketAnalyzer, AnalysisResult
from .betting.executor import BetExecutor, BetOrder

console = Console()


# ── Market fetching ───────────────────────────────────────────────────────────

def fetch_all_markets(
    platforms: list[str],
    limit: int,
    kalshi_demo: bool,
) -> tuple[list[Market], dict]:
    markets: list[Market] = []
    clients: dict = {}

    if "manifold" in platforms:
        try:
            client = ManifoldClient()
            fetched = client.fetch_markets(limit=limit)
            markets.extend(fetched)
            clients["manifold"] = client
            console.print(f"[green]✓[/] Manifold: {len(fetched)} markets fetched")
        except Exception as exc:
            console.print(f"[yellow]⚠[/] Manifold fetch failed: {exc}")

    if "kalshi" in platforms:
        try:
            client = KalshiClient(demo=kalshi_demo)
            if cfg.KALSHI_EMAIL and cfg.KALSHI_PASSWORD:
                client.login()
            fetched = client.fetch_markets(limit=limit)
            markets.extend(fetched)
            clients["kalshi"] = client
            console.print(f"[green]✓[/] Kalshi: {len(fetched)} markets fetched")
        except Exception as exc:
            console.print(f"[yellow]⚠[/] Kalshi fetch failed: {exc}")

    if "polymarket" in platforms:
        try:
            client = PolymarketClient()
            fetched = client.fetch_markets(limit=limit)
            markets.extend(fetched)
            clients["polymarket"] = client
            console.print(f"[green]✓[/] Polymarket: {len(fetched)} markets fetched")
        except Exception as exc:
            console.print(f"[yellow]⚠[/] Polymarket fetch failed: {exc}")

    return markets, clients


# ── Pipeline ──────────────────────────────────────────────────────────────────

def run_pipeline(
    markets: list[Market],
    searcher: SourceSearcher,
    validator: SourceValidator,
    analyzer: MarketAnalyzer,
    executor: BetExecutor,
    max_bets: int,
) -> tuple[list[BetOrder], list[AnalysisResult]]:
    placed: list[BetOrder] = []
    analyses: list[AnalysisResult] = []

    for i, market in enumerate(markets, 1):
        # ── Budget gate ──────────────────────────────────────────────────────
        if not budget_mgr.can_analyse_market():
            console.print(
                f"\n[red bold]Budget exhausted![/] "
                f"Remaining: ${budget_mgr.state.balance:.2f} "
                f"(safety reserve: ${SAFETY_RESERVE_USD:.2f}). Stopping."
            )
            break

        console.rule(f"[bold cyan]Market {i}/{len(markets)}")
        console.print(f"[bold]{market.question}[/]")
        console.print(
            f"  Platform: {market.platform.value} | "
            f"Vol: ${market.volume_usd:,.0f} | "
            f"Market YES: {(market.yes_price or 0):.1%} | "
            f"[dim]{budget_mgr.state.status_line()}[/dim]"
        )

        # ── Research ─────────────────────────────────────────────────────────
        console.print("  [dim]Researching...[/dim]")
        try:
            raw_results = searcher.research_question(
                market.question, market.description[:200]
            )
        except Exception as exc:
            console.print(f"  [red]Research failed: {exc}[/]")
            budget_mgr.charge_api(0.016)  # Charge Tavily even on partial failure
            continue

        # ── Validate ─────────────────────────────────────────────────────────
        report = validator.validate(market.question, raw_results)
        console.print(
            f"  Evidence confidence: {report.confidence:.1%} | "
            f"Sources: {len(report.validated_sources)}"
        )

        # ── Reason (charges Opus 4.6 cost) ───────────────────────────────────
        console.print("  [dim]Reasoning with Claude Opus 4.6 (adaptive thinking)...[/dim]")
        analysis = analyzer.analyze(market, report)

        # Charge the full per-market API cost regardless of outcome
        budget_mgr.charge_api(API_COST_PER_MARKET)

        if analysis is None:
            console.print("  [red]Analysis failed, skipping[/]")
            continue
        analyses.append(analysis)

        console.print(
            f"  Est. prob: {analysis.estimated_probability:.1%} | "
            f"Edge: {analysis.edge:+.1%} | "
            f"Confidence: {analysis.confidence:.1%}"
        )
        if analysis.thinking_summary:
            console.print(f"  [dim italic]Thinking: {analysis.thinking_summary[:120]}...[/dim italic]")
        console.print(f"  [italic]{analysis.reasoning}[/italic]")

        # ── Execute ───────────────────────────────────────────────────────────
        if len(placed) >= max_bets:
            console.print("  [yellow]Max bets reached, skipping execution[/]")
            continue

        order = executor.execute(analysis)
        if order is None:
            console.print("  [dim]→ No edge or insufficient budget, skipping[/dim]")
        else:
            tag = "[yellow](DRY RUN)[/]" if order.dry_run else "[green bold](LIVE)[/]"
            currency_note = "(play-money)" if order.currency == "MANA" else "(real money)"
            console.print(
                f"  → BET [bold]{order.outcome}[/bold] "
                f"{order.size:.2f} {order.currency} {currency_note} {tag}"
            )
            placed.append(order)

    return placed, analyses


# ── Summary table ─────────────────────────────────────────────────────────────

def print_summary(
    analyses: list[AnalysisResult],
    placed: list[BetOrder],
) -> None:
    console.rule("[bold]Session Summary")

    # Budget status
    s = budget_mgr.state
    console.print(
        f"\n[bold cyan]Budget Status[/]\n"
        f"  Total budget:   [bold]${s.total_budget:.2f}[/]\n"
        f"  API spent:      [yellow]${s.api_spent:.2f}[/]\n"
        f"  Bets placed:    [yellow]${s.bets_placed_usd:.2f}[/]\n"
        f"  Winnings back:  [green]${s.bets_returned_usd:.2f}[/]\n"
        f"  Balance:        [bold {'green' if s.balance >= 40 else 'yellow' if s.balance >= 20 else 'red'}]"
        f"${s.balance:.2f}[/]\n"
        f"  Est. analyses remaining: [dim]~{int(s.usable_balance / API_COST_PER_MARKET)}[/]\n"
    )

    # Market table
    table = Table(box=box.SIMPLE_HEAVY, show_header=True)
    table.add_column("Platform", style="cyan", no_wrap=True)
    table.add_column("Question", max_width=45)
    table.add_column("Market %", justify="right")
    table.add_column("Est. %", justify="right")
    table.add_column("Edge", justify="right")
    table.add_column("Conf.", justify="right")
    table.add_column("Action", justify="center")

    for a in analyses:
        bet_placed = next(
            (b for b in placed if b.market.market_id == a.market.market_id), None
        )
        if bet_placed:
            tag = "(DRY)" if bet_placed.dry_run else ""
            action = (
                f"[green]BET {bet_placed.outcome} "
                f"{bet_placed.size:.1f} {bet_placed.currency} {tag}[/]"
            )
        elif a.recommended_outcome == "SKIP":
            action = "[dim]skip[/dim]"
        else:
            action = "[yellow]no edge[/yellow]"

        edge_style = "green" if a.edge > 0 else "red"
        table.add_row(
            a.market.platform.value,
            a.market.question[:45],
            f"{a.market_probability:.1%}",
            f"{a.estimated_probability:.1%}",
            f"[{edge_style}]{a.edge:+.1%}[/]",
            f"{a.confidence:.0%}",
            action,
        )

    console.print(table)
    console.print(f"Bets placed this session: [bold]{len(placed)}[/bold]")
    if cfg.DRY_RUN:
        console.print("[yellow bold]DRY RUN mode — no real money was wagered[/]")
    if not budget_mgr.state.is_alive:
        console.print(
            "[red bold]⚠ Budget is exhausted. "
            "Deposit more funds or the bot cannot continue.[/]"
        )


# ── CLI ───────────────────────────────────────────────────────────────────────

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Prediction Market Reasoning Bot ($50 lifetime budget)"
    )
    parser.add_argument(
        "--platforms", nargs="+",
        choices=["manifold", "kalshi", "polymarket"],
        default=["manifold"],
        help="Platforms to trade on (default: manifold = play-money, costs no budget)",
    )
    parser.add_argument("--limit", type=int, default=10, help="Markets per platform")
    parser.add_argument("--max-bets", type=int, default=3, help="Max bets per run")
    parser.add_argument(
        "--bankroll-usd", type=float, default=30.0,
        help="Real-money bankroll portion (default $30 of the $50 budget)"
    )
    parser.add_argument("--bankroll-mana", type=float, default=1000.0)
    parser.add_argument("--kalshi-demo", action="store_true")
    parser.add_argument("--dry-run", action="store_true", help="Force dry-run mode")
    parser.add_argument(
        "--budget-status", action="store_true",
        help="Print budget status and exit"
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    if args.dry_run:
        cfg.DRY_RUN = True

    # Budget status shortcut
    if args.budget_status:
        s = budget_mgr.state
        console.print(f"\n[bold cyan]Budget Status[/]")
        console.print(s.status_line())
        console.print(
            f"  Est. analyses remaining: ~{int(s.usable_balance / API_COST_PER_MARKET)}"
        )
        return

    console.rule("[bold blue]Prediction Market Bot")
    console.print(
        f"Mode: {'[yellow]DRY RUN[/]' if cfg.DRY_RUN else '[red bold]LIVE BETTING[/]'}"
    )
    console.print(f"Model: [cyan]claude-opus-4-6[/] with adaptive thinking")
    console.print(f"Platforms: {args.platforms}")
    console.print(f"[bold]{budget_mgr.state.status_line()}[/bold]\n")

    if not budget_mgr.state.is_alive:
        console.print(
            "[red bold]Budget exhausted — cannot afford even one market analysis. "
            "Top up the budget or the bot cannot run.[/]"
        )
        sys.exit(1)

    try:
        cfg.validate()
    except ValueError as exc:
        console.print(f"[red]Config error: {exc}[/]")
        sys.exit(1)

    searcher = SourceSearcher()
    validator = SourceValidator()
    analyzer = MarketAnalyzer()

    markets, clients = fetch_all_markets(args.platforms, args.limit, args.kalshi_demo)
    if not markets:
        console.print("[red]No markets fetched. Check API keys and network.[/]")
        sys.exit(1)

    # Sort by volume — busier markets have better information environments
    markets.sort(key=lambda m: m.volume_usd, reverse=True)

    executor = BetExecutor(
        manifold=clients.get("manifold"),
        kalshi=clients.get("kalshi"),
        polymarket=clients.get("polymarket"),
        bankroll_usd=args.bankroll_usd,
        bankroll_mana=args.bankroll_mana,
    )

    placed, analyses = run_pipeline(
        markets, searcher, validator, analyzer, executor, args.max_bets
    )
    print_summary(analyses, placed)


if __name__ == "__main__":
    main()
