---
name: idea-generation
description: Standard Indian Equity Screening & Idea Generation (/idea-generation). Runs Quality, GARP, Value, and Sector screens across NSE universes via KDB-X and Screener.in.
---

# Idea Generation (`/idea-generation`)

1. Confirm investor universe (`nifty50`, `it`, `pharma_chem`, `defense_infra`, `banking_fin`, `multibagger_india`, or `global_all`) and style (`Quality Compounder`, `GARP`, `Value`).
2. Call `scan_and_rank_kdb` via `indian-investor-mcp` to compute deterministic ROE/ROIC, OPM, Debt/Equity, CFO/PAT, and valuation multiples inside PyKX KDB-X without hallucinating ratios.
3. Cross-check top candidates with `screener_india(symbol)` for 10-year Sales/PAT CAGR and ROCE consistency, then shortlist 3–5 stocks for deeper 3-statement and DCF analysis.
