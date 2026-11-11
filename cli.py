"""Interactive Terminal CLI for the 2026 AI Fundamental Research Analyst Agent."""

from __future__ import annotations

from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.panel import Panel
from rich.prompt import Prompt
from rich.table import Table

from agent import AgentRunResult, FundamentalAnalystAgent
from agent_tools import AgentWorkspace
from scoring_engine import recommend_archetype_from_goals

cli = typer.Typer(
    name="fundamental-agent",
    help="2026 Institutional AI Fundamental Research Analyst Agent + KDB-X Engine",
)
console = Console()


def _render_result(result: AgentRunResult) -> None:
    console.print(
        Panel.fit(
            f"[bold cyan]Mode:[/] {result.mode}\n"
            f"[bold cyan]KDB-X:[/] {result.kdb_telemetry.get('mode')} "
            f"({result.kdb_telemetry.get('cached_tables', 0)} .kdb tables, "
            f"{result.kdb_telemetry.get('total_cache_kb', 0)} KB, "
            f"last op {result.kdb_telemetry.get('last_op_ms', 0)} ms)",
            title="AI Fundamental Research Analyst",
        )
    )

    if result.steps:
        step_tbl = Table(title="Autonomous Tool Execution Trace", show_lines=False)
        step_tbl.add_column("Step", justify="right", style="cyan")
        step_tbl.add_column("Tool", style="bold")
        step_tbl.add_column("Observation")
        for s in result.steps:
            step_tbl.add_row(str(s.step_index), s.tool_name, s.summary)
        console.print(step_tbl)

    if result.ranked_results:
        tbl = Table(title="6-Layer Weighted Multibagger Ranking")
        tbl.add_column("Symbol", style="bold")
        tbl.add_column("Score", justify="right")
        tbl.add_column("Verdict")
        tbl.add_column("ROIC %", justify="right")
        tbl.add_column("IncROIC %", justify="right")
        tbl.add_column("RevCAGR %", justify="right")
        tbl.add_column("RevDCF g%", justify="right")
        tbl.add_column("NetDebt/EB", justify="right")
        tbl.add_column("Vetoes / Flags")

        for r in result.ranked_results[:12]:
            m = r["metrics"]
            verdict_style = (
                "green"
                if r["verdict"] == "HIGH CONVICTION"
                else ("red" if r["verdict"] == "HARD VETO" else "yellow")
            )
            flags = "; ".join(r["vetoes"] or r["warnings"][:2]) or "Clean"
            tbl.add_row(
                r["symbol"],
                str(r["total_score"]),
                f"[{verdict_style}]{r['verdict']}[/{verdict_style}]",
                f"{m['roic_pct']}%" if m["roic_pct"] is not None else "—",
                f"{m['inc_roic_pct']}%" if m["inc_roic_pct"] is not None else "—",
                f"{m['rev_cagr_pct']}%" if m["rev_cagr_pct"] is not None else "—",
                f"{m['implied_fcf_g_pct']}%" if m["implied_fcf_g_pct"] is not None else "—",
                f"{m['net_debt_to_ebitda']}x" if m["net_debt_to_ebitda"] is not None else "—",
                flags,
            )
        console.print(tbl)

    console.print(Panel(result.final_response, title="Analyst Brief (Strict Actual Data · Educational Only)", border_style="green"))
    console.print(
        "[dim]SEBI Educational Disclaimer: Outputs are based strictly on verified public market/exchange filings for educational analysis only — not registered SEBI investment advice or a buy/sell/hold call.[/dim]"
    )


@cli.command()
def run(
    goal: str = typer.Argument(..., help="Natural-language research instruction or stock query."),
    pdf: Optional[Path] = typer.Option(None, "--pdf", help="Optional Annual Report / Audit Report PDF path."),
    audit_text: str = typer.Option("", "--audit-text", help="Optional Audit/Litigation/Concall text snippet."),
    offline: bool = typer.Option(False, "--offline", help="Force deterministic offline tool-loop (skip OpenAI)."),
    open_dashboard: bool = typer.Option(False, "--open", help="Open the generated interactive Web Dashboard in default browser."),
) -> None:
    """Run the autonomous AI Fundamental Research Analyst once for a goal."""
    import webbrowser

    agent = FundamentalAnalystAgent(force_offline=offline)
    res = agent.run(
        goal=goal,
        pdf_path=str(pdf) if pdf else None,
        audit_text=audit_text,
    )
    _render_result(res)
    if open_dashboard and res.dashboard_paths:
        webbrowser.open(Path(res.dashboard_paths[-1]).as_uri())


@cli.command()
def dashboard(
    symbol: str = typer.Argument(..., help="Ticker symbol (e.g., RELIANCE.NS, BEL.NS, TCS.NS)."),
    pdf: Optional[Path] = typer.Option(None, "--pdf", help="Optional Annual Report / Audit PDF path."),
    open_browser: bool = typer.Option(True, "--open/--no-open", help="Launch dashboard in default browser."),
) -> None:
    """Generate standardized 3-section Memo + Interactive Web Dashboard for any stock."""
    import webbrowser

    ws = AgentWorkspace()
    res = ws.generate_stock_report_and_dashboard(
        symbol=symbol,
        pdf_path=str(pdf) if pdf else None,
    )
    if res.get("status") != "saved":
        console.print(f"[red]Error:[/red] {res.get('message')}")
        raise typer.Exit(code=1)
    console.print(f"[green]Standardized Memo:[/green] {res['memo_path']}")
    console.print(f"[green]Web Dashboard HTML:[/green] {res['dashboard_path']}")
    if open_browser:
        webbrowser.open(Path(res["dashboard_path"]).as_uri())


@cli.command()
def chat(
    offline: bool = typer.Option(False, "--offline", help="Force deterministic offline tool-loop."),
) -> None:
    """Interactive Stage 0 -> Stage 3 AI Fundamental Research Analyst conversation."""
    ws = AgentWorkspace()
    agent = FundamentalAnalystAgent(workspace=ws, force_offline=offline)

    console.print(
        Panel.fit(
            "[bold]Stage 0 — Investor Financial Goal & Mandate Interview[/bold]\n"
            "First let's uncover your return goal, horizon, drawdown tolerance, and interests.",
            border_style="cyan",
        )
    )

    target_multiple = Prompt.ask(
        "1. Target Return Multiple",
        choices=["2x_3x", "3x_5x", "5x_10x_plus"],
        default="5x_10x_plus",
    )
    horizon_years = int(Prompt.ask("2. Investment Horizon (years)", choices=["3", "5", "7", "10"], default="7"))
    drawdown_tolerance = Prompt.ask(
        "3. Max Drawdown Pain Tolerance",
        choices=["low_15pct", "moderate_30pct", "high_45pct"],
        default="high_45pct" if target_multiple == "5x_10x_plus" else "moderate_30pct",
    )
    rec_arch, rec_cap = recommend_archetype_from_goals(
        target_multiple=target_multiple,
        drawdown_tolerance=drawdown_tolerance,
        horizon_years=horizon_years,
    )
    console.print(
        f"[cyan]Recommended Strategy:[/cyan] archetype=[bold]{rec_arch}[/bold], cap_focus=[bold]{rec_cap}[/bold]"
    )

    market = Prompt.ask("4. Market Universe", choices=["IN", "CA", "US", "GLOBAL"], default="IN")
    cap_focus = Prompt.ask("5. Market-Cap Runway Zone", choices=["small_mid", "all", "large"], default=rec_cap)
    sectors_raw = Prompt.ask("6. Preferred Sectors (comma-separated or ALL)", default="ALL")
    archetype = Prompt.ask(
        "7. Strategy Archetype",
        choices=[
            "multibagger_hunter",
            "balanced_institutional",
            "compounder_growth",
            "deep_value",
            "policy_capex",
            "conservative_income",
        ],
        default=rec_arch,
    )
    custom_raw = Prompt.ask("8. Specific Tickers to include (optional, comma-separated)", default="")

    sectors = [s.strip() for s in sectors_raw.split(",") if s.strip()] or ["ALL"]
    custom_tickers = [t.strip().upper() for t in custom_raw.split(",") if t.strip()]
    ws.set_investor_mandate(
        market=market,
        sectors=sectors,
        archetype=archetype,
        target_multiple=target_multiple,
        drawdown_tolerance=drawdown_tolerance,
        cap_focus=cap_focus,
        horizon_years=horizon_years,
        custom_tickers=custom_tickers,
    )

    console.print("\n[bold green]Investor goals & mandate locked.[/bold green] Running KDB-X multibagger scan...\n")
    init_res = agent.run(
        goal=(
            f"Scan market={market}, cap_focus={cap_focus}, target={target_multiple}, "
            f"sectors={','.join(sectors)}, archetype={archetype}, tickers={','.join(custom_tickers)}"
        )
    )
    _render_result(init_res)

    console.print(
        "\n[bold]Interactive commands:[/bold] Ask any follow-up (e.g. "
        "'Audit BEL.NS for 65% govt contracts and war beneficiary', "
        "'Inspect SHOP.TO', 'audit_pdf <SYMBOL> <PATH>', or 'exit').\n"
    )

    while True:
        user_msg = Prompt.ask("[bold cyan]Investor[/bold cyan]").strip()
        if not user_msg:
            continue
        if user_msg.lower() in {"exit", "quit", "q"}:
            console.print("Session ended. Memos & .kdb tables preserved.")
            break

        if user_msg.lower().startswith("audit_pdf "):
            parts = user_msg.split(maxsplit=2)
            if len(parts) < 3:
                console.print("[yellow]Usage: audit_pdf <SYMBOL> <PDF_PATH>[/yellow]")
                continue
            sym, pdf_p = parts[1], parts[2]
            res = agent.run(goal=f"Audit {sym} using attached PDF and save memo", pdf_path=pdf_p)
            _render_result(res)
            continue

        res = agent.run(goal=user_msg)
        _render_result(res)


if __name__ == "__main__":
    cli()
