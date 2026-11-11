---
name: dcf-india
description: Standard Unlevered FCFF Discounted Cash Flow Valuation (/dcf-india). Builds 5-10 year INR FCFF projections, Indian WACC (11-12.5%), Terminal Value, and a WACC vs Terminal Growth sensitivity table.
---

# Standard FCFF DCF Valuation (`/dcf-india`)

1. Call `inspect_stock_deeply(ticker)` and `screener_india(symbol)` to obtain TTM/historical Revenue, EBIT Margin, Capex, Cash, Total Debt, Diluted Shares, and Market Cap in INR.
2. Project **5-year or 10-year Unlevered Free Cash Flow (FCFF)**:
   `FCFF = EBIT * (1 - 25.17% Tax) + D&A - Capex - Change in Working Capital`.
3. Discount using an Indian **WACC** (`11.0%–12.5%` large/mid-cap, `12.5%–14.0%` small-cap) and compute **Terminal Value** via Perpetuity Growth (`g = 4.0%–5.5%`) cross-checked against Conservative Exit `EV/EBITDA`.
4. Bridge `Enterprise Value -> Equity Value (= EV + Cash - Total Debt - Minority Interest) / Diluted Shares`, present a 2D `WACC vs. g` sensitivity matrix, and highlight the implied **Margin of Safety (%)** vs. current NSE price.
