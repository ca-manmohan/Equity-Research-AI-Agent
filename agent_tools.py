"""Structured Toolset for the Autonomous AI Fundamental Research Analyst Agent."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional

from data_ingestor import (
    MULTIBAGGER_UNIVERSES,
    PRESET_UNIVERSES,
    MarketDataIngestor,
    get_universe_tickers,
    search_yahoo_tickers,
)
from forensic_agent import extract_text_from_pdf_bytes, run_forensic_audit
from indian_connectors import (
    analyze_quarterly_earnings_india,
    fetch_screener_public_snapshot,
    parse_screener_excel,
)
from kdb_engine import KDBXEngine
from scoring_engine import (
    ARCHETYPE_WEIGHTS,
    InvestorProfile,
    recommend_archetype_from_goals,
    score_universe,
)
from dashboard_builder import save_web_dashboard
from standardized_report import build_standardized_report, render_standardized_markdown


class AgentWorkspace:
    """Shared state and deterministic execution tools for the Fundamental Research Agent."""

    def __init__(self, base_dir: Optional[Path] = None) -> None:
        self.base_dir = base_dir or Path(__file__).resolve().parent
        self.kdb = KDBXEngine(cache_dir=self.base_dir / "kdb_store")
        self.ingestor = MarketDataIngestor(kdb=self.kdb)
        self.memos_dir = self.base_dir / "memos"
        self.memos_dir.mkdir(parents=True, exist_ok=True)
        self.dashboards_dir = self.base_dir / "dashboards"
        self.dashboards_dir.mkdir(parents=True, exist_ok=True)

        self.profile = InvestorProfile()
        self.forensic_overrides: Dict[str, Dict[str, Any]] = {}
        self.bundles: Dict[str, Dict[str, Any]] = {}
        self.results: List[Dict[str, Any]] = []
        self.last_snapshot: Dict[str, Any] = {}

    def set_investor_mandate(
        self,
        market: str = "IN",
        sectors: Optional[List[str]] = None,
        archetype: Optional[str] = None,
        target_multiple: str = "3x_5x",
        drawdown_tolerance: str = "moderate_30pct",
        cap_focus: Optional[str] = None,
        horizon_years: int = 5,
        exclude_high_debt: bool = True,
        exclude_negative_cfo: bool = True,
        min_adtv_usd_m: float = 0.25,
        custom_tickers: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """Stage 0: Configure investor financial goals, interests, market, and archetype weights."""
        mkt = market.upper() if market.upper() in ("IN", "CA", "US", "GLOBAL") else "IN"
        rec_arch, rec_cap = recommend_archetype_from_goals(
            target_multiple=target_multiple,
            drawdown_tolerance=drawdown_tolerance,
            horizon_years=horizon_years,
        )
        arch = archetype if (archetype and archetype in ARCHETYPE_WEIGHTS) else rec_arch
        resolved_cap = cap_focus or rec_cap
        self.profile = InvestorProfile(
            market=mkt,
            sectors=sectors or ["ALL"],
            archetype=arch,
            target_multiple=target_multiple,
            drawdown_tolerance=drawdown_tolerance,
            cap_focus=resolved_cap,
            horizon_years=horizon_years,
            exclude_high_debt=exclude_high_debt,
            exclude_negative_cfo=exclude_negative_cfo,
            min_adtv_usd_m=min_adtv_usd_m,
            custom_tickers=[t.strip().upper() for t in (custom_tickers or []) if t.strip()],
        )
        pool = MULTIBAGGER_UNIVERSES if resolved_cap == "small_mid" else PRESET_UNIVERSES
        return {
            "status": "configured",
            "market": self.profile.market,
            "sectors": self.profile.sectors,
            "target_multiple": self.profile.target_multiple,
            "drawdown_tolerance": self.profile.drawdown_tolerance,
            "cap_focus": self.profile.cap_focus,
            "horizon_years": self.profile.horizon_years,
            "archetype": self.profile.archetype,
            "weights": self.profile.weights(),
            "custom_tickers": self.profile.custom_tickers,
            "available_market_sectors": pool.get(self.profile.market, {}),
        }

    def search_equities(self, query: str, max_results: int = 8) -> Dict[str, Any]:
        """Search Yahoo Finance (including ca.finance.yahoo & NSE) for ticker symbols."""
        return {"query": query, "matches": search_yahoo_tickers(query, max_results=max_results)}

    def scan_and_rank_kdb(self, force_refresh: bool = False, max_symbols: int = 18) -> Dict[str, Any]:
        """Stage 1: Ingest market data, cache in KDB-X (.kdb), and rank across 6 weighted layers."""
        symbols = get_universe_tickers(
            market=self.profile.market,
            sectors=self.profile.sectors,
            custom_tickers=self.profile.custom_tickers,
            cap_focus=self.profile.cap_focus,
        )
        if not self.profile.custom_tickers and len(symbols) > max_symbols:
            symbols = symbols[:max_symbols]
        if not symbols:
            return {"status": "empty", "message": "No tickers resolved for current mandate."}

        bundles = self.ingestor.fetch_universe(symbols, force_refresh=force_refresh)
        self.bundles.update({b["symbol"]: b for b in bundles})

        scored, snap_info = score_universe(
            bundles=bundles,
            profile=self.profile,
            kdb=self.kdb,
            forensic_overrides=self.forensic_overrides,
        )
        for item in scored:
            if not item.get("forensic_audit"):
                item["forensic_audit"] = run_forensic_audit(item["symbol"], stock_summary=item)

        self.results = scored
        self.last_snapshot = snap_info
        return {
            "status": "ok",
            "count": len(scored),
            "weights": self.profile.weights(),
            "kdb_snapshot": snap_info,
            "kdb_status": self.kdb.status().__dict__,
            "ranked_summary": [
                {
                    "symbol": r["symbol"],
                    "name": r["name"],
                    "sector": r["sector"],
                    "total_score": r["total_score"],
                    "verdict": r["verdict"],
                    "roic_pct": r["metrics"]["roic_pct"],
                    "inc_roic_pct": r["metrics"]["inc_roic_pct"],
                    "rev_cagr_pct": r["metrics"]["rev_cagr_pct"],
                    "implied_fcf_g_pct": r["metrics"]["implied_fcf_g_pct"],
                    "cfo_to_ebitda": r["metrics"]["cfo_to_ebitda"],
                    "net_debt_to_ebitda": r["metrics"]["net_debt_to_ebitda"],
                    "vetoes": r["vetoes"],
                    "warnings": r["warnings"],
                    "multibagger_signals": r.get("multibagger_signals", []),
                }
                for r in scored
            ],
        }

    def inspect_stock_deeply(self, symbol: str) -> Dict[str, Any]:
        """Inspect full 6-layer metrics, Reverse-DCF expectations, and checklist for one ticker."""
        sym = symbol.strip().upper()
        stock = next((r for r in self.results if r["symbol"] == sym), None)
        if stock is None:
            bundle = self.ingestor.fetch_ticker_bundle(sym)
            self.bundles[sym] = bundle
            scored, snap = score_universe(
                bundles=list(self.bundles.values()),
                profile=self.profile,
                kdb=self.kdb,
                forensic_overrides=self.forensic_overrides,
            )
            self.results = scored
            self.last_snapshot = snap
            stock = next((r for r in self.results if r["symbol"] == sym), None)
        if stock is None:
            return {"status": "error", "message": f"Could not fetch or score {sym}."}
        if not stock.get("forensic_audit"):
            stock["forensic_audit"] = run_forensic_audit(sym, stock_summary=stock)
        return stock

    def audit_filing_and_external_risks(
        self,
        symbol: str,
        pdf_path: Optional[str] = None,
        raw_text: str = "",
        audit_status: str = "clean",
        bank_loan_risk: str = "low",
        govt_contract_pct: float = 0.0,
        litigation_pct_networth: float = 0.0,
        macro_war_exposure: str = "neutral",
        institutional_catalyst: str = "",
    ) -> Dict[str, Any]:
        """Stage 2: Audit PDF/text & external factors (bank loans, govt contracts, audit remarks, litigation, war/macro)."""
        sym = symbol.strip().upper()
        pdf_pages = None
        if pdf_path:
            p = Path(pdf_path)
            if not p.exists():
                return {"status": "error", "message": f"PDF file not found: {pdf_path}"}
            pdf_pages = extract_text_from_pdf_bytes(p.read_bytes())

        stock = self.inspect_stock_deeply(sym)
        if stock.get("status") == "error":
            return stock

        audit = run_forensic_audit(
            symbol=sym,
            stock_summary=stock,
            raw_text=raw_text,
            pdf_pages=pdf_pages,
            external_inputs={
                "audit_status": audit_status,
                "bank_loan_risk": bank_loan_risk,
                "govt_contract_pct": govt_contract_pct,
                "litigation_pct_networth": litigation_pct_networth,
                "macro_war_exposure": macro_war_exposure,
                "institutional_catalyst": institutional_catalyst,
            },
        )
        self.forensic_overrides[sym] = {
            "layer4_score_pct": audit["layer4_score_pct"],
            "layer5_score_pct": audit["layer5_score_pct"],
            "vetoes": audit["vetoes"],
            "warnings": audit["warnings"],
            "audit_summary": audit,
        }

        scored, snap = score_universe(
            bundles=list(self.bundles.values()),
            profile=self.profile,
            kdb=self.kdb,
            forensic_overrides=self.forensic_overrides,
        )
        self.results = scored
        self.last_snapshot = snap
        updated = next((r for r in scored if r["symbol"] == sym), stock)
        return {
            "status": "ok",
            "symbol": sym,
            "updated_score": updated["total_score"],
            "verdict": updated["verdict"],
            "audit": audit,
            "kdb_snapshot": snap,
        }

    def generate_stock_report_and_dashboard(
        self,
        symbol: str,
        pdf_path: Optional[str] = None,
        audit_text: str = "",
        sector_peers: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """Standardized 7-Section Institutional Report (with 5Y IRR/MOIC Returns Analysis) + Interactive Web Dashboard for any ticker."""
        report = build_standardized_report(
            workspace=self,
            symbol=symbol,
            pdf_path=pdf_path,
            audit_text=audit_text,
            sector_peers=sector_peers,
        )
        if report.get("status") != "ok":
            return report

        sym = report["symbol"]
        memo_md = render_standardized_markdown(report)
        memo_path = self.memos_dir / f"{sym}_memo.md"
        memo_path.write_text(memo_md, encoding="utf-8")

        dashboard_path = save_web_dashboard(report, self.dashboards_dir)
        return {
            "status": "saved",
            "symbol": sym,
            "memo_path": str(memo_path),
            "dashboard_path": dashboard_path,
            "verdict": report["verdict"],
            "score": report["score"],
            "report": report,
        }

    def save_research_memo(self, symbol: str) -> Dict[str, Any]:
        """Stage 3: Generate standardized Markdown Memo AND Interactive Web Dashboard."""
        res = self.generate_stock_report_and_dashboard(symbol=symbol)
        if res.get("status") != "saved":
            return res
        return {
            "status": "saved",
            "symbol": res["symbol"],
            "memo_path": res["memo_path"],
            "dashboard_path": res["dashboard_path"],
            "verdict": res["verdict"],
            "score": res["score"],
        }

    def get_kdb_telemetry(self) -> Dict[str, Any]:
        """Return active PyKX / KDB-X runtime status and storage telemetry."""
        return self.kdb.status().__dict__

    def comps_india(self, tickers: List[str]) -> Dict[str, Any]:
        """Run Indian peer comparison across ROIC, IncROIC, EV/NOPAT, FCF Yield, CFO/EBITDA & Rev-DCF via KDB-X."""
        clean = [t.strip().upper() if "." in t else f"{t.strip().upper()}.NS" for t in tickers if t.strip()]
        if not clean:
            return {"status": "error", "message": "Provide at least 2 tickers for peer comps."}
        bundles = self.ingestor.fetch_universe(clean)
        self.bundles.update({b["symbol"]: b for b in bundles})
        scored, snap = score_universe(
            bundles=bundles,
            profile=self.profile,
            kdb=self.kdb,
            forensic_overrides=self.forensic_overrides,
        )
        return {
            "status": "ok",
            "kdb_snapshot": snap,
            "peers": [
                {
                    "symbol": s["symbol"],
                    "name": s["name"],
                    "score": s["total_score"],
                    "verdict": s["verdict"],
                    "mcap_b": s["market_cap_b"],
                    **s["metrics"],
                }
                for s in scored
            ],
        }

    def screener_india(self, symbol: str, xlsx_path: Optional[str] = None) -> Dict[str, Any]:
        """Fetch free Screener.in public ratios/pros/cons or parse an exported Screener .xlsx file."""
        if xlsx_path:
            return parse_screener_excel(xlsx_path)
        return fetch_screener_public_snapshot(symbol)

    def earnings_india(self, symbol: str) -> Dict[str, Any]:
        """Analyze latest quarterly Indian earnings (YoY Revenue, EBIT Margin, PAT trend)."""
        return analyze_quarterly_earnings_india(symbol)

    def dispatch(self, tool_name: str, arguments_json: str) -> str:
        """Execute a named tool from JSON arguments for LLM function-calling loops."""
        args = json.loads(arguments_json) if arguments_json else {}
        mapping = {
            "set_investor_mandate": self.set_investor_mandate,
            "search_equities": self.search_equities,
            "scan_and_rank_kdb": self.scan_and_rank_kdb,
            "inspect_stock_deeply": self.inspect_stock_deeply,
            "audit_filing_and_external_risks": self.audit_filing_and_external_risks,
            "save_research_memo": self.save_research_memo,
            "generate_stock_report_and_dashboard": self.generate_stock_report_and_dashboard,
            "get_kdb_telemetry": self.get_kdb_telemetry,
            "comps_india": self.comps_india,
            "screener_india": self.screener_india,
            "earnings_india": self.earnings_india,
        }
        fn = mapping.get(tool_name)
        if fn is None:
            return json.dumps({"error": f"Unknown tool: {tool_name}"})
        result = fn(**args)
        return json.dumps(result, default=str)


OPENAI_TOOL_SCHEMAS: List[Dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "set_investor_mandate",
            "description": "Stage 0: Configure investor market (IN, CA, US, GLOBAL), preferred sectors, strategy archetype weights, debt/cash exclusions, and custom tickers.",
            "parameters": {
                "type": "object",
                "properties": {
                    "market": {"type": "string", "enum": ["IN", "CA", "US", "GLOBAL"]},
                    "sectors": {"type": "array", "items": {"type": "string"}},
                    "archetype": {
                        "type": "string",
                        "enum": [
                            "balanced_institutional",
                            "compounder_growth",
                            "deep_value",
                            "policy_capex",
                            "conservative_income",
                            "multibagger_hunter",
                        ],
                    },
                    "target_multiple": {"type": "string", "enum": ["2x_3x", "3x_5x", "5x_10x_plus"]},
                    "drawdown_tolerance": {"type": "string", "enum": ["low_15pct", "moderate_30pct", "high_45pct"]},
                    "cap_focus": {"type": "string", "enum": ["all", "small_mid", "large"]},
                    "horizon_years": {"type": "integer"},
                    "exclude_high_debt": {"type": "boolean"},
                    "exclude_negative_cfo": {"type": "boolean"},
                    "min_adtv_usd_m": {"type": "number"},
                    "custom_tickers": {"type": "array", "items": {"type": "string"}},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_equities",
            "description": "Search Yahoo Finance (including ca.finance.yahoo and NSE) to resolve company names to exact exchange ticker symbols.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string"},
                    "max_results": {"type": "integer"},
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "scan_and_rank_kdb",
            "description": "Stage 1: Fetch financial statements, cache into KDB-X (.kdb), and compute weighted 6-layer multibagger scores and Reverse-DCF implied growth.",
            "parameters": {
                "type": "object",
                "properties": {
                    "force_refresh": {"type": "boolean"},
                    "max_symbols": {"type": "integer"},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "inspect_stock_deeply",
            "description": "Inspect complete 6-layer fundamentals, Reverse DCF, debt structure, and sector checklist for a single ticker.",
            "parameters": {
                "type": "object",
                "properties": {"symbol": {"type": "string"}},
                "required": ["symbol"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "audit_filing_and_external_risks",
            "description": "Stage 2: Audit PDF/text reports and external factors (adverse audit remarks, litigation clauses, material items, huge bank loans, government contracts, economy/war shocks) and re-score the stock.",
            "parameters": {
                "type": "object",
                "properties": {
                    "symbol": {"type": "string"},
                    "pdf_path": {"type": "string"},
                    "raw_text": {"type": "string"},
                    "audit_status": {"type": "string", "enum": ["clean", "eom_or_qualified", "adverse_or_going_concern"]},
                    "bank_loan_risk": {"type": "string", "enum": ["low", "moderate", "high"]},
                    "govt_contract_pct": {"type": "number"},
                    "litigation_pct_networth": {"type": "number"},
                    "macro_war_exposure": {"type": "string", "enum": ["beneficiary", "neutral", "moderate_risk", "high_risk"]},
                    "institutional_catalyst": {"type": "string"},
                },
                "required": ["symbol"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "save_research_memo",
            "description": "Stage 3: Generate and save SEBI-compliant educational Markdown fundamental digest + interactive HTML dashboard with conclusion and monitorables.",
            "parameters": {
                "type": "object",
                "properties": {"symbol": {"type": "string"}},
                "required": ["symbol"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "generate_stock_report_and_dashboard",
            "description": "Run standardized educational 7-section analysis (Executive Summary w/ Filings & Audit Review, Price & 5Y P/E Bands, 4-Quarter Earnings Beat/Miss, Estimate Revisions & Source-Attributed Highlights BEFORE Financials, 4Y YoY & 4Q QoQ Financials + Conditional Segment Analysis, 5Y DCF & Sensitivity, Shareholding & External Consensus, Deep Drivers & Conclusion) and save color-coded HTML Dashboard.",
            "parameters": {
                "type": "object",
                "properties": {
                    "symbol": {"type": "string"},
                    "pdf_path": {"type": "string"},
                    "audit_text": {"type": "string"},
                    "sector_peers": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["symbol"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_kdb_telemetry",
            "description": "Check KDB-X / PyKX runtime mode, cached .kdb table count, storage size, and latency.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "comps_india",
            "description": "Compare Indian peers side-by-side (ROIC, IncROIC, EV/NOPAT, FCF Yield, CFO/EBITDA, NetDebt/EBITDA, Reverse-DCF g%) via KDB-X.",
            "parameters": {
                "type": "object",
                "properties": {"tickers": {"type": "array", "items": {"type": "string"}}},
                "required": ["tickers"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "screener_india",
            "description": "Fetch free Screener.in public ratios/pros/cons for an NSE/BSE symbol or parse a downloaded Screener .xlsx workbook.",
            "parameters": {
                "type": "object",
                "properties": {
                    "symbol": {"type": "string"},
                    "xlsx_path": {"type": "string"},
                },
                "required": ["symbol"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "earnings_india",
            "description": "Analyze quarterly Indian earnings trends (YoY Revenue, EBIT Margin %, PAT) via free yfinance data.",
            "parameters": {
                "type": "object",
                "properties": {"symbol": {"type": "string"}},
                "required": ["symbol"],
            },
        },
    },
]
