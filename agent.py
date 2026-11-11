"""Autonomous AI Fundamental Research Analyst Agent (Tool-Calling + Deterministic Fallback)."""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from agent_tools import OPENAI_TOOL_SCHEMAS, AgentWorkspace

SYSTEM_PROMPT = """You are an Educational Fundamental Financial Analysis Agent backed by KDB-X / PyKX columnar storage and deterministic quantitative engines.

Regulatory & Data Integrity Guardrails:
- SEBI RA 2014 / IA 2013 Compliance: Strictly provide objective, data-driven educational financial analysis and valuation modeling ONLY. NEVER issue Buy, Sell, Hold, Accumulate, Reduce, Target Price recommendations, "Buy on Dips", or portfolio allocation percentages.
- Strict Actual-Data Policy: Rely EXCLUSIVELY on live/cached exchange, regulatory filing, and tool outputs returned during execution. NEVER fabricate, estimate, extrapolate, or substitute synthetic/dummy financial figures; if a metric or source is unavailable, explicitly report it as unavailable and cite exact Data Sources.

Your workflow ALWAYS follows these stages:
1. Stage 0 (Analysis Scope): Confirm preferred market (IN, CA, US, GLOBAL), sectors, strategy lens, exclusions, and horizon. Call `set_investor_mandate`.
2. Stage 1 (KDB-X Scan): Call `scan_and_rank_kdb` (or `search_equities` first if company names need ticker resolution).
3. Stage 2 (Forensic & External Audit): For top candidates or user-specified stocks, call `audit_filing_and_external_risks` if PDFs, audit remarks, bank loans, government contracts, litigation, material items, or macro/war risks are provided or relevant.
4. Stage 3 (Finalization & Memo): Call `save_research_memo` to generate the standardized Markdown note and 8-block color-coded HTML dashboard (covering Section 0 Intro: Business Overview, Annual Report Outlook & Order Book; Section 1 Executive Summary w/ Audit Review & AI/Disclosure Briefings; Section 2 Price, 5Y Returns Scenario/IRR/MOIC Attribution & 5Y P/E Bands; Section 3 4-Quarter Earnings Surprise, Revisions & Source-Attributed Highlights BEFORE Financials; Section 4 4Y/4Q Financials & Conditional Ind-AS 108 Segment Mix/Margin Analysis; Section 5 5Y DCF & Sensitivity; Section 6 Shareholding, External Consensus & Competitive Peer Positioning/4-Pillar Moat Matrix; and Section 7 Key Drivers, Analytical Conclusion, Quantitative Quality Rating Grade/Stars, 6-Pillar Basis & 5-Tier Rating Guide):
   - Cite exact composite quality metrics, modeled 5Y IRR/MOIC attribution (EBITDA growth vs multiple shift vs cash/dividends), 4-quarter EPS beat/miss % and 30D estimate revisions, peer comparative standings (`●●●` tiering + 4-pillar moat), freshness date check, Reverse-DCF implied growth, ROIC-WACC spread, sequential quarter deltas (bps QoQ), and 4Y/4Q historical trends (NEVER invent numbers; cite only tool output with clickable sources).
   - Include risk flags and an objective Conclusion detailing the Quantitative Quality & Valuation Rating (`Grade A+`..`D` / Stars), 6-Pillar Basis, Scoring Formula, What the Rating Means, 5-Tier Guide, and SEBI educational disclaimer.
"""


@dataclass
class AgentStep:
    """Trace record of a single autonomous tool invocation."""

    step_index: int
    tool_name: str
    arguments: Dict[str, Any]
    summary: str


@dataclass
class AgentRunResult:
    """Final structured output of an autonomous research agent run."""

    mode: str
    final_response: str
    steps: List[AgentStep] = field(default_factory=list)
    ranked_results: List[Dict[str, Any]] = field(default_factory=list)
    memo_paths: List[str] = field(default_factory=list)
    dashboard_paths: List[str] = field(default_factory=list)
    kdb_telemetry: Dict[str, Any] = field(default_factory=dict)


class FundamentalAnalystAgent:
    """End-to-end AI Fundamental Research Analyst operating over AgentWorkspace tools."""

    def __init__(
        self,
        workspace: Optional[AgentWorkspace] = None,
        model: str = "gpt-4o-mini",
        force_offline: bool = False,
    ) -> None:
        self.workspace = workspace or AgentWorkspace()
        self.model = model
        self.force_offline = force_offline
        self.history: List[Dict[str, Any]] = [{"role": "system", "content": SYSTEM_PROMPT}]

    @property
    def has_llm(self) -> bool:
        return (not self.force_offline) and bool(os.getenv("OPENAI_API_KEY"))

    def run(
        self,
        goal: str,
        pdf_path: Optional[str] = None,
        audit_text: str = "",
        max_steps: int = 8,
    ) -> AgentRunResult:
        """Execute an autonomous multi-step fundamental research workflow."""
        if self.has_llm:
            try:
                return self._run_llm_loop(
                    goal=goal, pdf_path=pdf_path, audit_text=audit_text, max_steps=max_steps
                )
            except Exception:
                pass
        return self._run_deterministic_agent(
            goal=goal, pdf_path=pdf_path, audit_text=audit_text
        )

    def _run_llm_loop(
        self,
        goal: str,
        pdf_path: Optional[str],
        audit_text: str,
        max_steps: int,
    ) -> AgentRunResult:
        from openai import OpenAI

        client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
        user_msg = goal
        if pdf_path:
            user_msg += f"\nAttached Annual/Audit PDF path: {pdf_path}"
        if audit_text:
            user_msg += f"\nAttached Audit/External Risk Text:\n{audit_text[:3000]}"

        self.history.append({"role": "user", "content": user_msg})
        steps: List[AgentStep] = []
        memo_paths: List[str] = []
        dashboard_paths: List[str] = []

        for idx in range(1, max_steps + 1):
            resp = client.chat.completions.create(
                model=self.model,
                messages=self.history,
                tools=OPENAI_TOOL_SCHEMAS,
                temperature=0.1,
            )
            msg = resp.choices[0].message
            tool_calls = msg.tool_calls or []
            self.history.append(msg.model_dump(exclude_none=True))

            if not tool_calls:
                return AgentRunResult(
                    mode=f"LLM Tool-Calling Agent ({self.model})",
                    final_response=msg.content or "",
                    steps=steps,
                    ranked_results=self.workspace.results,
                    memo_paths=memo_paths,
                    dashboard_paths=dashboard_paths,
                    kdb_telemetry=self.workspace.get_kdb_telemetry(),
                )

            for tc in tool_calls:
                name = tc.function.name
                raw_args = tc.function.arguments or "{}"
                obs_json = self.workspace.dispatch(name, raw_args)
                steps.append(
                    AgentStep(
                        step_index=idx,
                        tool_name=name,
                        arguments={"raw": raw_args[:160]},
                        summary=obs_json[:180],
                    )
                )
                if name in ("save_research_memo", "generate_stock_report_and_dashboard") and '"memo_path"' in obs_json:
                    import json

                    parsed = json.loads(obs_json)
                    if parsed.get("memo_path"):
                        memo_paths.append(parsed["memo_path"])
                    if parsed.get("dashboard_path"):
                        dashboard_paths.append(parsed["dashboard_path"])

                self.history.append(
                    {
                        "role": "tool",
                        "tool_call_id": tc.id,
                        "content": obs_json,
                    }
                )

        return AgentRunResult(
            mode=f"LLM Tool-Calling Agent ({self.model})",
            final_response="Reached maximum reasoning steps; partial research saved.",
            steps=steps,
            ranked_results=self.workspace.results,
            memo_paths=memo_paths,
            dashboard_paths=dashboard_paths,
            kdb_telemetry=self.workspace.get_kdb_telemetry(),
        )

    @staticmethod
    def _parse_goal_mandate(goal: str) -> Dict[str, Any]:
        """Extract market, sectors, archetype, explicit tickers, and risk flags from goal."""
        g = goal.lower()

        market = "IN"
        if any(k in g for k in ["canada", "tsx", ".to", "ca.finance", "canadian"]):
            market = "CA"
        elif any(k in g for k in ["us ", "usa", "nasdaq", "nyse", "america"]):
            market = "US"
        elif "global" in g:
            market = "GLOBAL"

        sectors: List[str] = []
        sector_keywords = {
            "Defense & Infra": ["defense", "defence", "infra", "railway", "capital goods"],
            "IT & Digital": ["it ", "software", "tech", "saas", "ai ", "digital"],
            "Pharma & Chemicals": ["pharma", "chemical", "health", "biotech"],
            "Consumer & Retail": ["consumer", "retail", "fmcg"],
            "Banking & Financials": ["bank", "nbfc", "financial"],
            "Energy & Manufacturing": ["energy", "power", "manufacturing", "industrial"],
        }
        for sec, kws in sector_keywords.items():
            if any(k in g for k in kws):
                sectors.append(sec)
        if not sectors:
            sectors = ["ALL"]

        archetype = "balanced_institutional"
        target_multiple = "3x_5x"
        drawdown_tolerance = "moderate_30pct"
        cap_focus = "all"

        if any(k in g for k in ["multibagger", "10x", "5x", "small cap", "small-cap", "small_mid", "emerging"]):
            archetype = "multibagger_hunter"
            target_multiple = "5x_10x_plus"
            drawdown_tolerance = "high_45pct"
            cap_focus = "small_mid"
        elif any(k in g for k in ["growth", "compounder", "high roic"]):
            archetype = "compounder_growth"
        elif any(k in g for k in ["value", "cheap", "turnaround", "contrarian"]):
            archetype = "deep_value"
        elif any(k in g for k in ["policy", "govt", "government", "capex", "defense", "defence"]):
            archetype = "policy_capex"
        elif any(k in g for k in ["conservative", "safe", "dividend", "income"]):
            archetype = "conservative_income"
            target_multiple = "2x_3x"
            drawdown_tolerance = "low_15pct"
            cap_focus = "large"

        # Detect explicit tickers like BEL.NS, RY.TO, MSFT (ignore common English caps)
        raw_tickers = re.findall(r"\b[A-Z]{2,12}(?:-[A-Z])?\.(?:NS|BO|TO|V|NE)\b", goal)
        if not raw_tickers and market == "US":
            us_cands = re.findall(r"\b[A-Z]{2,5}\b", goal)
            ignore = {"US", "USA", "AI", "KDB", "DCF", "ROIC", "WACC", "API", "PDF", "NSE", "TSX", "ALL"}
            raw_tickers = [t for t in us_cands if t not in ignore]

        # Detect external risk hints
        macro_war = "neutral"
        if any(k in g for k in ["war beneficiary", "defense tailwind"]):
            macro_war = "beneficiary"
        elif any(k in g for k in ["war", "geopolitical", "tariff", "sanction"]):
            macro_war = "moderate_risk"

        bank_risk = "high" if any(k in g for k in ["huge bank loan", "high debt", "debt stress"]) else "low"
        govt_pct = 45.0 if any(k in g for k in ["govt contract", "government contract", "psu tender"]) else 0.0

        return {
            "market": market,
            "sectors": sectors,
            "archetype": archetype,
            "target_multiple": target_multiple,
            "drawdown_tolerance": drawdown_tolerance,
            "cap_focus": cap_focus,
            "custom_tickers": raw_tickers,
            "macro_war_exposure": macro_war,
            "bank_loan_risk": bank_risk,
            "govt_contract_pct": govt_pct,
            "save_memo": "memo" in g or "report" in g or "save" in g or True,
        }

    def _run_deterministic_agent(
        self,
        goal: str,
        pdf_path: Optional[str],
        audit_text: str,
    ) -> AgentRunResult:
        parsed = self._parse_goal_mandate(goal)
        steps: List[AgentStep] = []
        memo_paths: List[str] = []

        # Step 0b: Resolve company name via search_equities if single-stock prompt lacks exchange suffix
        if not parsed["custom_tickers"]:
            m_name = re.search(
                r"(?:analyze|analyse|inspect|audit|evaluate|dashboard\s+for|report\s+on)\s+([A-Za-z0-9&\.\-\s]{2,30}?)(?:\s+(?:using|for|with|and|on|stock|shares|ltd|limited|$))",
                goal,
                re.IGNORECASE,
            )
            if m_name:
                cand = m_name.group(1).strip()
                generic_skip = {"all", "indian", "nse", "multibagger", "top", "best", "stocks", "sector", "growth", "value"}
                if cand.lower() not in generic_skip and len(cand.split()) <= 3:
                    srch = self.workspace.search_equities(cand, max_results=5)
                    matches = srch.get("matches", [])
                    preferred_suffix = ".NS" if parsed["market"] == "IN" else (".TO" if parsed["market"] == "CA" else "")
                    chosen = next(
                        (x["symbol"] for x in matches if preferred_suffix and x["symbol"].endswith(preferred_suffix)),
                        matches[0]["symbol"] if matches else None,
                    )
                    if chosen:
                        parsed["custom_tickers"] = [chosen]

        # Step 1: Stage 0 Mandate
        mandate_res = self.workspace.set_investor_mandate(
            market=parsed["market"],
            sectors=parsed["sectors"],
            archetype=parsed["archetype"],
            target_multiple=parsed["target_multiple"],
            drawdown_tolerance=parsed["drawdown_tolerance"],
            cap_focus=parsed["cap_focus"],
            custom_tickers=parsed["custom_tickers"],
        )
        steps.append(
            AgentStep(
                step_index=1,
                tool_name="set_investor_mandate",
                arguments={
                    "market": mandate_res["market"],
                    "sectors": mandate_res["sectors"],
                    "archetype": mandate_res["archetype"],
                    "custom_tickers": mandate_res["custom_tickers"],
                },
                summary=f"Weights configured for {mandate_res['archetype']} on {mandate_res['market']}",
            )
        )

        # Step 2: Stage 1 KDB-X Scan
        scan_res = self.workspace.scan_and_rank_kdb()
        ranked = self.workspace.results
        snap = scan_res.get("kdb_snapshot", {})
        steps.append(
            AgentStep(
                step_index=2,
                tool_name="scan_and_rank_kdb",
                arguments={"market": parsed["market"], "sectors": parsed["sectors"]},
                summary=f"Scanned {scan_res.get('count', 0)} stocks via {snap.get('mode', 'KDB-X')} ({snap.get('latency_ms', 0)} ms)",
            )
        )

        # Step 3: Stage 2 Forensic & External Audit on top candidate (or explicit ticker)
        target_sym = (
            parsed["custom_tickers"][0]
            if parsed["custom_tickers"]
            else (ranked[0]["symbol"] if ranked else None)
        )
        if target_sym and (
            pdf_path
            or audit_text.strip()
            or parsed["govt_contract_pct"] > 0
            or parsed["bank_loan_risk"] != "low"
            or parsed["macro_war_exposure"] != "neutral"
        ):
            audit_res = self.workspace.audit_filing_and_external_risks(
                symbol=target_sym,
                pdf_path=pdf_path,
                raw_text=audit_text,
                bank_loan_risk=parsed["bank_loan_risk"],
                govt_contract_pct=parsed["govt_contract_pct"],
                macro_war_exposure=parsed["macro_war_exposure"],
            )
            steps.append(
                AgentStep(
                    step_index=3,
                    tool_name="audit_filing_and_external_risks",
                    arguments={"symbol": target_sym, "pdf_path": pdf_path},
                    summary=f"Forensic audit -> Score {audit_res.get('updated_score')}, Verdict {audit_res.get('verdict')}",
                )
            )
            ranked = self.workspace.results

        dashboard_paths: List[str] = []

        # Step 4: Save Stage 3 Standardized Report + Web Dashboard for Top Non-Veto Pick and requested ticker
        if ranked:
            top_pick = next((r for r in ranked if r["verdict"] != "HARD VETO"), ranked[0])
            memo_targets = [top_pick["symbol"]]
            if target_sym and target_sym not in memo_targets and any(r["symbol"] == target_sym for r in ranked):
                memo_targets.append(target_sym)
            for sym_to_save in memo_targets:
                memo_res = self.workspace.save_research_memo(sym_to_save)
                if memo_res.get("memo_path"):
                    memo_paths.append(memo_res["memo_path"])
                if memo_res.get("dashboard_path"):
                    dashboard_paths.append(memo_res["dashboard_path"])
                steps.append(
                    AgentStep(
                        step_index=len(steps) + 1,
                        tool_name="save_research_memo",
                        arguments={"symbol": sym_to_save},
                        summary=f"Saved standardized memo & web dashboard -> {memo_res.get('dashboard_path')}",
                    )
                )

        # Synthesize clean executive report
        telemetry = self.workspace.get_kdb_telemetry()
        lines = [
            f"Completed standardized multi-section fundamental analysis (with Intro Outlook & Order Book, dedicated Earnings Highlights before Financials, and Conclusion Rating/Guide) for market={parsed['market']}, sectors={parsed['sectors']}, archetype={parsed['archetype']}.",
            f"KDB-X Runtime: {telemetry['mode']} | {telemetry['cached_tables']} .kdb tables ({telemetry['total_cache_kb']} KB).",
            "",
            "Top Ranked Candidates:",
        ]
        for r in ranked[:5]:
            m = r["metrics"]
            sigs = ", ".join(r.get("multibagger_signals", [])[:3]) or "None"
            lines.append(
                f"  - {r['symbol']} ({r['name']}): Score {r['total_score']}/100 [{r['verdict']}] | "
                f"ROIC={m['roic_pct']}% | IncROIC={m['inc_roic_pct']}% | RevCAGR={m['rev_cagr_pct']}% | "
                f"RevDCF={m['implied_fcf_g_pct']}% | Vetoes={len(r['vetoes'])} | Signals=[{sigs}]"
            )
        if memo_paths:
            lines.append(f"\nStandardized Research Memo: {memo_paths[-1]}")
        if dashboard_paths:
            lines.append(f"Interactive Web Dashboard (HTML): {dashboard_paths[-1]}")
        lines += [
            "\nData Sources & Integrity: Yahoo Finance API, NSE India XBRL/Filings, Screener.in, Google News RSS & PyKX/KDB-X binary store (Strict Actual-Data Only).",
            "SEBI Educational Disclaimer: Strictly for educational financial analysis using public data under SEBI RA 2014 / IA 2013 guidelines; not investment advice or a buy/sell/hold recommendation.",
        ]

        return AgentRunResult(
            mode="Autonomous Deterministic Research Agent (Offline Tool Loop)",
            final_response="\n".join(lines),
            steps=steps,
            ranked_results=ranked,
            memo_paths=memo_paths,
            dashboard_paths=dashboard_paths,
            kdb_telemetry=telemetry,
        )
