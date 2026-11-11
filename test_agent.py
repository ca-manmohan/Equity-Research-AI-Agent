"""Verification suite for the 2026 AI Fundamental Research Analyst Agent + KDB-X Engine."""

from __future__ import annotations

from pathlib import Path
import pandas as pd

from agent import FundamentalAnalystAgent
from agent_tools import AgentWorkspace
from forensic_agent import run_forensic_audit
from indian_connectors import analyze_quarterly_earnings_india, clean_nse_symbol
from kdb_engine import KDBXEngine
from mcp_server import handle_request
from scoring_engine import (
    ARCHETYPE_WEIGHTS,
    recommend_archetype_from_goals,
    solve_reverse_dcf_growth,
)


def test_archetype_weights_sum_to_100() -> None:
    for name, w in ARCHETYPE_WEIGHTS.items():
        total = sum(w.values())
        assert abs(total - 100.0) < 1e-6, f"{name} weights summed to {total}"
    arch, cap = recommend_archetype_from_goals("5x_10x_plus", "high_45pct", 7)
    assert arch == "multibagger_hunter"
    assert cap == "small_mid"


def test_kdb_binary_roundtrip_and_ranking(tmp_path) -> None:
    kdb = KDBXEngine(cache_dir=tmp_path)
    df = pd.DataFrame(
        {
            "symbol": ["A.NS", "B.NS", "C.NS"],
            "sector": ["Technology", "Technology", "Technology"],
            "roic": [0.28, 0.14, 0.21],
            "cash_op_prof": [0.22, 0.08, 0.16],
            "fcf_yield": [0.04, 0.01, 0.03],
            "rev_cagr": [0.20, 0.06, 0.14],
        }
    )
    path = kdb.save_table("unit_test_tbl", df)
    assert path.exists()
    loaded = kdb.load_table("unit_test_tbl")
    assert loaded is not None and len(loaded) == 3

    ranked = kdb.cross_sectional_rank_and_zscore(
        loaded, ["roic", "cash_op_prof"], group_col="sector"
    )
    assert "roic_pct" in ranked.columns
    assert ranked.loc[ranked["symbol"] == "A.NS", "roic_pct"].iloc[0] > 90.0


def test_reverse_dcf_solver() -> None:
    g = solve_reverse_dcf_growth(ev=2000.0, base_fcf=80.0, wacc=0.11, years=7)
    assert g is not None
    assert 0.05 < g < 0.25


def test_forensic_vetoes_and_scoring() -> None:
    sample_text = (
        "Independent Auditor's Report: Based on our audit, we express an Adverse Opinion "
        "due to material uncertainty related to going concern and pending litigation "
        "involving contingent liabilities and consortium bank term loan restructuring."
    )
    audit = run_forensic_audit(
        symbol="TEST.NS",
        stock_summary={"sector": "Industrials", "industry": "Infrastructure"},
        raw_text=sample_text,
        external_inputs={
            "audit_status": "adverse_or_going_concern",
            "bank_loan_risk": "high",
            "govt_contract_pct": 65.0,
            "litigation_pct_networth": 30.0,
            "macro_war_exposure": "high_risk",
        },
    )
    assert len(audit["vetoes"]) >= 2
    assert audit["layer4_score_pct"] < 20.0
    assert audit["layer5_score_pct"] < 40.0
    assert len(audit["findings"]) >= 3


def test_autonomous_agent_end_to_end(tmp_path) -> None:
    ws = AgentWorkspace(base_dir=tmp_path)
    agent = FundamentalAnalystAgent(workspace=ws, force_offline=True)

    result = agent.run(
        goal=(
            "Find Indian defense multibaggers focusing on BEL.NS, "
            "check govt contract concentration and war beneficiary exposure, and save memo."
        ),
        audit_text=(
            "Clean unmodified audit opinion. Strong Ministry of Defence government contract "
            "order book with milestone advances and zero consortium loan defaults."
        ),
    )

    assert len(result.steps) >= 3
    assert any(s.tool_name == "set_investor_mandate" for s in result.steps)
    assert any(s.tool_name == "scan_and_rank_kdb" for s in result.steps)
    assert any(s.tool_name == "audit_filing_and_external_risks" for s in result.steps)
    assert any(s.tool_name == "save_research_memo" for s in result.steps)
    assert len(result.ranked_results) >= 1
    assert len(result.memo_paths) >= 1
    memo_file = tmp_path / "memos" / "BEL.NS_memo.md"
    assert memo_file.exists()
    memo_text = memo_file.read_text(encoding="utf-8")
    assert "Analytical Conclusion & Educational Synthesis" in memo_text
    assert "Monitorables & Thesis Invalidation Triggers" not in memo_text
    assert result.kdb_telemetry["cached_tables"] >= 1


def test_mcp_server_and_indian_connectors(tmp_path) -> None:
    import json
    from pathlib import Path

    assert clean_nse_symbol("eclerx.ns") == "ECLERX"

    ws = AgentWorkspace(base_dir=tmp_path)
    init_resp = handle_request(ws, {"jsonrpc": "2.0", "id": 1, "method": "initialize"})
    assert init_resp is not None and init_resp["result"]["serverInfo"]["name"] == "indian-investor-mcp"

    list_resp = handle_request(ws, {"jsonrpc": "2.0", "id": 2, "method": "tools/list"})
    tool_names = [t["name"] for t in list_resp["result"]["tools"]]
    for expected in ["comps_india", "screener_india", "earnings_india", "scan_and_rank_kdb"]:
        assert expected in tool_names

    call_resp = handle_request(
        ws,
        {
            "jsonrpc": "2.0",
            "id": 3,
            "method": "tools/call",
            "params": {
                "name": "comps_india",
                "arguments": {"tickers": ["ECLERX.NS", "NEWGEN.NS"]},
            },
        },
    )
    comps_payload = json.loads(call_resp["result"]["content"][0]["text"])
    assert comps_payload["status"] == "ok"
    assert len(comps_payload["peers"]) == 2

    q_earn = analyze_quarterly_earnings_india("ECLERX.NS")
    assert q_earn["status"] == "ok"
    assert q_earn["latest_quarter"] is not None

    plugin_dir = Path(__file__).resolve().parent.parent / "indian-investor-plugin"
    if plugin_dir.exists():
        plugin_json = json.loads((plugin_dir / "plugin.json").read_text(encoding="utf-8"))
        assert plugin_json["name"] == "indian-investor"
        assert (plugin_dir / "mcp_config.json").exists()
        skill_dirs = {p.parent.name for p in (plugin_dir / "skills").glob("*/SKILL.md")}
        expected_skills = {
            "goal-intake",
            "idea-generation",
            "three-statement-india",
            "comps-india",
            "dcf-india",
            "earnings-india",
            "audit-qc-india",
            "advanced-research-2026",
        }
        assert skill_dirs == expected_skills
        assert len(list((plugin_dir / "agents").glob("*.md"))) == 3


def test_standardized_report_and_web_dashboard(tmp_path: Path) -> None:
    ws = AgentWorkspace(base_dir=tmp_path)
    out = ws.generate_stock_report_and_dashboard(
        symbol="RELIANCE.NS",
        audit_text="Deloitte issued Unmodified Clean Opinion. Net Debt/EBITDA 1.27x. Contingent liabilities 6.2% of Net Worth.",
    )
    assert out["status"] == "saved"
    rep = out["report"]

    # Section 1: Executive Summary (News/Catalysts + Quick Pointers + Key Data + Integrated Audit)
    assert "plain_english_verdict" in rep["executive_summary"]
    assert len(rep["executive_summary"]["quick_pointers"]) == 4
    assert rep["executive_summary"]["key_market_data"]["shares_outstanding"] is not None
    assert "forensic_audit_integrated" in rep["executive_summary"]

    # Section 2: Financial Summary (4Y YoY, 4Q QoQ, 5Y DCF & Peer Comps)
    fs = rep["financial_summary"]
    assert len(fs["annual_4y"]["rows"]) >= 3
    assert len(fs["quarterly_4q"]["rows"]) >= 3
    assert len(fs["dcf_valuation"]["forecast_5y"]) == 5
    assert fs["dcf_valuation"]["fair_value_per_share"] > 0
    assert fs["valuation_bands"]["current_pe"] is not None
    assert "sotp_bridge" in fs["dcf_valuation"]
    # Section 2 (Returns Analysis IRR/MOIC & Value Attribution in Price & Multiples section)
    assert "returns_analysis" in rep
    ret = rep["returns_analysis"]
    assert ret.get("available") is True
    assert ret["entry_mult"] > 0 and ret["base"]["moic"] > 0
    assert len(ret.get("scenarios", [])) == 3
    assert len(ret.get("sensitivity_matrix", [])) == 5
    rb = ret["base"]
    assert abs((1.0 + rb["attr_growth_moic"] + rb["attr_multiple_moic"] + rb["attr_cash_moic"]) - rb["moic"]) <= 0.05
    # Section 2 (Earnings Highlights & 4-Quarter Surprise Analysis before Financials)
    assert "earnings_highlights" in rep
    eh = rep["earnings_highlights"]
    assert len(eh.get("result_overview_rows", [])) >= 4
    assert len(eh.get("thematic_highlights", [])) >= 3
    assert len(eh.get("surprise_4q", [])) >= 3
    assert eh.get("freshness", {}).get("as_of_date")
    assert eh.get("sources_checklist")

    # Section 3 (now 4 in Dashboard): Financial Summary (4Y + 4Q + Conditional Segment Analysis + DCF)
    assert "working_capital" in fs
    assert "segment_analysis" in fs
    seg = fs["segment_analysis"]
    assert isinstance(seg, dict) and "available" in seg
    if seg["available"]:
        assert len(seg["segments"]) >= 2
        assert seg.get("opinion")

    # Section 3: Shareholding, Promoter/FPI Actions, Deals, Ratings & Benchmark Performance
    own = rep["ownership_and_market_context"]
    assert [r["horizon"] for r in own["performance_table"]] == ["1M", "3M", "6M", "12M"]
    assert own["analyst_recommendations"]["total"] > 0
    assert own["analyst_price_targets"]["mean"] > 0
    comp = own.get("competitive_analysis", {})
    assert comp.get("insight_headline")
    assert len(comp.get("dimensions", [])) >= 6
    assert len(comp.get("moat_pillars", [])) == 4
    assert len(comp.get("matrix_points", [])) >= 2
    assert all(
        own.get(k)
        for k in ("ownership_opinion", "deals_opinion", "ratings_opinion", "performance_opinion", "section_opinion")
    )

    # Section 0: Intro, Business Overview & Annual Report Outlook / Order Book
    intro = rep.get("intro_section", {})
    assert intro.get("overview")
    assert intro.get("outlook_briefing")

    # Section 4: Plain-English Advanced Analysis & Conclusion Rating Framework
    insights = rep["advanced_analysis_explained"]["insights"]
    assert len(insights) >= 3
    assert all(ins.get("what_it_is") and ins.get("what_it_means") for ins in insights)
    rf = (rep["advanced_analysis_explained"].get("conclusion") or {}).get("rating_framework", {})
    assert rf.get("grade", "").startswith("Grade ")
    assert (rf.get("stars") or 0) >= 1.0
    assert len(rf.get("layer_breakdown", [])) == 6
    assert len(rf.get("rating_scale_guide", [])) == 5
    assert rf.get("how_we_rated") and rf.get("meaning_of_rating")

    # Web Dashboard HTML & Memo files generated
    dash_path = Path(out["dashboard_path"])
    assert dash_path.exists() and dash_path.stat().st_size > 4000
    html_text = dash_path.read_text(encoding="utf-8")
    assert 'id="intro"' in html_text and "Annual Report Outlook, Capex &amp; Order Book" in html_text
    assert html_text.index('id="intro"') < html_text.index('id="exec"')
    assert "Executive Summary" in html_text
    assert "5-Year Public Equity Returns Analysis" in html_text
    assert "chartReturnsAttr" in html_text
    assert "Latest Earnings Highlights" in html_text
    assert "4-Quarter EPS Beat/Miss" in html_text
    assert "chartSurprise" in html_text
    assert "Primary Sources" in html_text
    assert "sec-cyan" in html_text and "sec-indigo" in html_text and "sec-cobalt" in html_text and "sec-amber" in html_text
    assert html_text.index("Latest Earnings Highlights") < html_text.index("Financial Track Record")
    assert "5-Year FCFF DCF Forecast" in html_text
    assert "What It Means For" in html_text
    assert "Shareholding, Promoter &amp; FPI Actions" in html_text
    assert "Competitive Positioning &amp; Structural Moat Analysis" in html_text
    assert "chartCompMatrix" in html_text
    assert "ai-brief-box" in html_text and "source-strip" in html_text
    assert "Investor Effect:" in html_text
    assert "<th>Headline</th>" not in html_text
    assert "events_briefing" in rep["executive_summary"]
    assert all(b.get("impact") for b in (intro.get("outlook_briefing") or {}).get("bullets", []))
    assert "media_briefing" in eh
    assert "filings_deals_briefing" in own and "ratings_briefing" in own
    assert "SEBI Educational Disclaimer" in html_text
    assert "Analytical Conclusion" in html_text
    assert "How Did We Rate This Company?" in html_text
    assert "What This Rating Means" in html_text
    assert "Our Educational Guide on the 5-Tier Rating Scale" in html_text
    assert "chartLayers" not in html_text
    assert "Monitorables &amp; Thesis Invalidation Triggers" not in html_text
    assert "Sector-Specific Diligence Checklist" not in html_text
    assert "BUY / ACCUMULATE" not in html_text
    assert "before increasing exposure" not in html_text
    assert "before allocating capital" not in html_text
    assert "Historical Multiple Decision" not in html_text
    assert any(p.get("symbol") == "ONGC.NS" for p in fs.get("peer_comps", []))
    memo_path = Path(out["memo_path"])
    assert memo_path.exists()
    memo_text = memo_path.read_text(encoding="utf-8")
    if seg.get("available"):
        assert "Operating Segment Analysis" in html_text
        assert "chartSegments" in html_text
        assert "### C. Operating Segment Analysis" in memo_text
    assert "## 0. Introduction: Business Overview, Annual Report Outlook & Order Book" in memo_text
    assert memo_text.index("## 0. Introduction:") < memo_text.index("## 1. Executive Summary")
    assert "5-Year Returns Scenario Model" in memo_text
    assert "## 2. Earnings Highlights" in memo_text
    assert "## 3. Financial Summary" in memo_text
    assert memo_text.index("## 2. Earnings Highlights") < memo_text.index("## 3. Financial Summary")
    assert "- **Sources:**" in memo_text
    assert "### Competitive Landscape & Structural Moat Analysis" in memo_text
    assert "| Headline | Effect | Source |" not in memo_text
    assert "Analytical Conclusion" in memo_text
    assert "#### Basis for Rating & How We Rated This Company" in memo_text
    assert "#### Educational Guide on Our Rating Scale" in memo_text
    assert "### Data Sources, Verification Status & Strict Actual-Data Policy" in memo_text
    assert "### SEBI Regulatory & Educational Disclaimer" in memo_text
    assert "Sources of Data &amp; Strict Actual-Data Verification" in html_text
    assert "SEBI Regulatory &amp; Educational Notice:" in html_text
    prov = rep.get("data_provenance", {})
    assert prov.get("strict_actual_data_enforced") is True
    assert prov.get("verified_sources_count", 0) >= 2


def test_strict_actual_data_blocks_phantom_tickers(tmp_path) -> None:
    ws = AgentWorkspace(base_dir=tmp_path)
    out = ws.generate_stock_report_and_dashboard(symbol="INVALID_NONEXISTENT_XYZ_999.NS")
    assert out.get("status") == "error"
