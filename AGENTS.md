# AGENTS.md — Universal Cross-Agent Instructions

Works across **OpenAI Codex / ChatGPT Agents**, **Claude Code**, **Cursor**, **Antigravity**, **Windsurf**, **Gemini CLI**, and any **MCP-compatible client**.

## Core Mandates (Always On)

1. **Strict Actual-Data Only:** Never guess, invent, extrapolate, or use dummy/placeholder financial metrics. Invoke the MCP tools (`mcp_server.py`) or Python engine (`cli.py` / `agent_tools.py`) for every quantitative calculation. If an exchange feed, segment XBRL filing, or ratio is missing, explicitly report it as unavailable.
2. **SEBI RA 2014 / IA 2013 Educational Compliance:** Provide objective quantitative analysis, valuation sensitivity, and forensic risk checks **strictly for education**. Never issue Buy/Sell/Hold ratings, target price calls, or portfolio allocation advice.
3. **Standardized 4-Stage Pipeline:**
   - **Stage 0 (`set_investor_mandate`)**: Establish market (`IN`, `CA`, `US`, `GLOBAL`), sectors, horizon, drawdown tolerance, and strategy archetype.
   - **Stage 1 (`scan_and_rank_kdb`)**: Compute deterministic 6-layer scores in KDB-X / PyKX (`.kdb`).
   - **Stage 2 (`audit_filing_and_external_risks`)**: Parse Annual/Auditor PDFs or text for CARO qualifications, going-concern flags, litigation, bank loans, govt contract DSO, and macro risks.
   - **Stage 3 (`generate_stock_report_and_dashboard`)**: Emit standardized Markdown memo (`memos/<SYMBOL>_memo.md`) + interactive Chart.js HTML dashboard (`dashboards/<SYMBOL>_dashboard.html`) with full **Data Sources** provenance and **SEBI Disclaimer**.

## Portable Skills Registry (`skills/`)

Discover all workflow specifications in [`skills/registry.json`](skills/registry.json) or call the `list_skills` MCP tool:

| Skill | File | Primary Workflow |
| :--- | :--- | :--- |
| `fundamental-research-analyst` | [`skills/fundamental-research-analyst/SKILL.md`](skills/fundamental-research-analyst/SKILL.md) | Master 4-stage orchestrator & 8-section dashboard |
| `goal-intake` | [`skills/goal-intake/SKILL.md`](skills/goal-intake/SKILL.md) | Stage 0 Investor Goals & Archetype mapping |
| `idea-generation` | [`skills/idea-generation/SKILL.md`](skills/idea-generation/SKILL.md) | KDB-X cross-sectional screening |
| `three-statement-india` | [`skills/three-statement-india/SKILL.md`](skills/three-statement-india/SKILL.md) | Ind-AS P&L, Balance Sheet, Cash Flow & Screener |
| `comps-india` | [`skills/comps-india/SKILL.md`](skills/comps-india/SKILL.md) | Peer valuation comps & 4-pillar competitive moat |
| `dcf-india` | [`skills/dcf-india/SKILL.md`](skills/dcf-india/SKILL.md) | 5Y FCFF DCF, Reverse-DCF & 5Y IRR/MOIC returns |
| `earnings-india` | [`skills/earnings-india/SKILL.md`](skills/earnings-india/SKILL.md) | 4Q EPS beat/miss, revisions & Ind-AS 108 segments |
| `audit-qc-india` | [`skills/audit-qc-india/SKILL.md`](skills/audit-qc-india/SKILL.md) | Filing hygiene QC & solvency hard vetoes |
| `advanced-research-2026` | [`skills/advanced-research-2026/SKILL.md`](skills/advanced-research-2026/SKILL.md) | 6-layer quant overlay & PDF forensic risk audit |

## MCP Server Connection (`.mcp.json`)

Connect any MCP client using stdio transport from the repository root:
```bash
python mcp_server.py
```

## Reference Specifications
- Industry-Standard Framework: [`docs/FundamentalAnalysis.md`](docs/FundamentalAnalysis.md)
- Advanced Quantitative & Forensic Framework: [`docs/AdvancedFundamentalAnalysis.md`](docs/AdvancedFundamentalAnalysis.md)
