"""
Prediction Market Bot — main entry point.

Flow per market:
  1. Fetch markets from enabled platforms
  2. Research each question with Tavily (multi-angle web search)
  3. Validate & cross-reference sources
  4. Reason with Claude to estimate true probability
  5. Size bet with fractional Kelly Criterion
  6. Execute (or dry-run) on the platform

Usage:
  python -m prediction_bot.main --platforms manifold polymarket kalshi \\
      --limit 20 --bankroll-usd 500 --bankroll-mana 5000
"""

import argparse
import sys
from typing import Optional

from rich.console import Console
from rich.table import Table
from rich import box

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
    """Fetch markets from all requested platforms. Returns (markets, clients)."""
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
) -> list[BetOrder]:
    """Process each market through the full research → reason → bet pipeline."""
    placed: list[BetOrder] = []
    analyses: list[AnalysisResult] = []

    for i, market in enumerate(markets, 1):
        console.rule(f"[bold cyan]Market {i}/{len(markets)}")
        console.print(f"[bold]{market.question}[/]")
        console.print(f"  Platform: {market.platform.value} | "
                      f"Vol: ${market.volume_usd:,.0f} | "
                      f"Market YES: {market.yes_price:.1%}")

        # 1. Research
        console.print("  [dim]Researching...[/dim]")
        try:
            raw_results = searcher.research_question(market.question, market.description[:200])
        except Exception as exc:
            console.print(f"  [red]Research failed: {exc}[/]")
            continue

        # 2. Validate
        report = validator.validate(market.question, raw_results)
        console.print(f"  Evidence confidence: {report.confidence:.1%} | "
                      f"Sources: {len(report.validated_sources)}")

        # 3. Reason
        console.print("  [dim]Reasoning with Claude...[/dim]")
        analysis = analyzer.analyze(market, report)
        if analysis is None:
            console.print("  [red]Analysis failed, skipping[/]")
            continue
        analyses.append(analysis)

        console.print(f"  Est. prob: {analysis.estimated_probability:.1%} | "
                      f"Edge: {analysis.edge:+.1%} | "
                      f"Confidence: {analysis.confidence:.1%}")
        console.print(f"  [italic]{analysis.reasoning}[/italic]")

        # 4. Execute
        if len(placed) >= max_bets:
            console.print("  [yellow]Max bets reached, skipping execution[/]")
            continue

        order = executor.execute(analysis)
        if order is None:
            console.print("  [dim]→ No edge, skipping[/dim]")
        else:
            tag = "[yellow](DRY RUN)[/]" if order.dry_run else "[green](LIVE)[/]"
            console.print(
                f"  → BET {order.outcome} {order.size:.2f} {order.currency} {tag}"
            )
            placed.append(order)

    return placed, analyses


# ── Summary table ─────────────────────────────────────────────────────────────

def print_summary(analyses: list[AnalysisResult], placed: list[BetOrder]) -> None:
    console.rule("[bold]Summary")

    table = Table(box=box.SIMPLE_HEAVY, show_header=True)
    table.add_column("Platform", style="cyan", no_wrap=True)
    table.add_column("Question", max_width=50)
    table.add_column("Market %", justify="right")
    table.add_column("Est. %", justify="right")
    table.add_column("Edge", justify="right")
    table.add_column("Action", justify="center")

    for a in analyses:
        bet_placed = next((b for b in placed if b.market.market_id == a.market.market_id), None)
        if bet_placed:
            action = f"[green]BET {bet_placed.outcome} {bet_placed.size:.1f} {bet_placed.currency}[/]"
        elif a.recommended_outcome == "SKIP":
            action = "[dim]skip[/dim]"
        else:
            action = "[yellow]no edge[/yellow]"

        edge_style = "green" if a.edge > 0 else "red"
        table.add_row(
            a.market.platform.value,
            a.market.question[:50],
            f"{a.market_probability:.1%}",
            f"{a.estimated_probability:.1%}",
            f"[{edge_style}]{a.edge:+.1%}[/]",
            action,
        )

    console.print(table)
    console.print(f"\nTotal bets placed: [bold]{len(placed)}[/bold]")
    if cfg.DRY_RUN:
        console.print("[yellow bold]DRY RUN mode — no real money was wagered[/]")


# ── CLI ───────────────────────────────────────────────────────────────────────

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Prediction Market Reasoning Bot")
    parser.add_argument(
        "--platforms", nargs="+",
        choices=["manifold", "kalshi", "polymarket"],
        default=["manifold"],
        help="Which platforms to trade on (default: manifold)",
    )
    parser.add_argument("--limit", type=int, default=10, help="Markets to fetch per platform")
    parser.add_argument("--max-bets", type=int, default=3, help="Max bets per run")
    parser.add_argument("--bankroll-usd", type=float, default=100.0, help="USD bankroll")
    parser.add_argument("--bankroll-mana", type=float, default=1000.0, help="Mana bankroll")
    parser.add_argument("--kalshi-demo", action="store_true", help="Use Kalshi demo environment")
    parser.add_argument("--dry-run", action="store_true", help="Force dry-run (override .env)")
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    if args.dry_run:
        cfg.DRY_RUN = True

    console.rule("[bold blue]Prediction Market Bot")
    console.print(f"Mode: {'[yellow]DRY RUN[/]' if cfg.DRY_RUN else '[red bold]LIVE BETTING[/]'}")
    console.print(f"Platforms: {args.platforms}")
    console.print(f"Markets per platform: {args.limit} | Max bets: {args.max_bets}\n")

    try:
        cfg.validate()
    except ValueError as exc:
        console.print(f"[red]Config error: {exc}[/]")
        sys.exit(1)

    # Initialise components
    searcher = SourceSearcher()
    validator = SourceValidator()
    analyzer = MarketAnalyzer()

    markets, clients = fetch_all_markets(args.platforms, args.limit, args.kalshi_demo)
    if not markets:
        console.print("[red]No markets fetched. Check API keys and network.[/]")
        sys.exit(1)

    # Sort by volume (higher = more efficient, better info environment)
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
