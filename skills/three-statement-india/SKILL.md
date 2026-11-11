---
name: three-statement-india
description: Standard Ind-AS Three-Statement Analysis (/3-statement-india). Links Income Statement, Balance Sheet, and Cash Flow Statement using yfinance, Screener.in public/Excel data, and KDB-X.
---

# Three-Statement Analysis (`/three-statement-india`)

1. Call `inspect_stock_deeply(ticker)` and `screener_india(symbol, xlsx_path=...)` to extract multi-year Ind-AS P&L, Balance Sheet, Cash Flow, and 10-year ROCE/OPM series.
2. Analyze the **Income Statement**: core revenue CAGR vs. Other Income, Gross Margin & OPM % trend, Depreciation, Finance Cost, and Normalized PAT.
3. Analyze the **Balance Sheet**: equity dilution, Long-Term vs. Short-Term Borrowings, Cash, Net Debt, Trade Receivables/Inventory working capital tie-up, and CWIP.
4. Analyze the **Cash Flow Statement**: `CFO / PAT` (3Y–5Y > 0.80x benchmark), Capex intensity, Free Cash Flow (`CFO - Capex`), and Net Borrowing/Dividend flows.
