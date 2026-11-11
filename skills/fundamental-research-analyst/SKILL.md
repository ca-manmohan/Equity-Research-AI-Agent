---
name: fundamental-research-analyst
description: >-
  2026 Institutional AI Fundamental Research Analyst Agent powered by KDB-X / PyKX, yfinance,
  NSE XBRL integrated filings, Screener.in, and PyMuPDF forensic PDF extraction. Trigger whenever the user
  asks to scan for multibagger stocks, run 6-layer fundamental analysis, audit Annual/Auditor reports
  (bank loans, govt contracts, adverse audit remarks, litigation, material items, war/macro risks),
  or generate an institutional research memo and interactive dashboard.
---

# Institutional AI Fundamental Research Analyst Skill (2026 Edition)

## Governing Specification & Engine (Portable Relative Paths)
- **Core Industry-Standard Spec:** `docs/FundamentalAnalysis.md` (3-Statement Analysis, Core Ratios, Comps, Standard FCFF DCF, Quarterly Earnings, 5Y IRR/MOIC Returns Attribution, Competitive Peer Matrix & 4-Pillar Moat, Audit Hygiene QC)
- **Advanced Quantitative & Forensic Spec (2026 Edition):** `docs/AdvancedFundamentalAnalysis.md` (6-Layer 100-pt Weighted Model, Ball et al. Cash Profitability, Eisfeldt HML_INT, Reverse-DCF, CARO/War/Litigation/Bank-Loan Forensics)
- **Autonomous Agent & Tools:** `agent.py`, `agent_tools.py`, `kdb_engine.py`, `scoring_engine.py`, `forensic_agent.py`, `standardized_report.py`, `dashboard_builder.py`
- **Terminal CLI:** `python cli.py` | **MCP Server:** `python mcp_server.py` (`.mcp.json`)

## Mandatory Execution Sequence

1. **Strict Actual-Data & SEBI Guardrails (Non-Negotiable):**
   - Rely **exclusively** on verified live/cached exchange, regulatory filing, and tool outputs. Never invent, extrapolate, or substitute synthetic/dummy financial figures.
   - Frame all analysis strictly for education under **SEBI (Research Analysts) Regulations, 2014** & **SEBI (Investment Advisers) Regulations, 2013** principles — zero Buy/Sell/Hold calls or target price recommendations.

2. **Stage 0 — Investor Mandate First (`set_investor_mandate`):**
   Confirm market (`IN` `.NS`, `CA` `.TO`/`.V`, `US`, `GLOBAL`), sectors, strategy archetype (`balanced_institutional`, `compounder_growth`, `deep_value`, `policy_capex`, `conservative_income`, `multibagger_hunter`), exclusions & custom tickers.

3. **Stage 1 — Deterministic KDB-X Quantitative Scan (`scan_and_rank_kdb`):**
   Run KDB-X columnar scoring across Layers 1, 2, 3, and 6 (cash-based operating profitability, `CFO/EBITDA`, `FCF/PAT`, Net Debt/EBITDA, ROIC vs WACC, 7-year Reverse-DCF, and ADTV liquidity).

4. **Stage 2 — Forensic Filing & External Risk Audit (`audit_filing_and_external_risks`):**
   Extract cited evidence from Annual/Auditor PDFs or footnotes (going concern, CARO qualifications, ICFR weaknesses, contingent liabilities, consortium bank loans, pledged shares, govt contract delays, and macro/war exposure).

5. **Stage 3 — Standardized Memo & Interactive Dashboard (`generate_stock_report_and_dashboard` / `save_research_memo`):**
   Produce the complete 8-section Markdown memo (`memos/<SYMBOL>_memo.md`) and interactive HTML dashboard (`dashboards/<SYMBOL>_dashboard.html`) complete with Data Sources & Verification Status and SEBI Educational Disclaimer.
