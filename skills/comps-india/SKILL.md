---
name: comps-india
description: Standard Indian Comparable Company Analysis (/comps-india). Compares NSE peers side-by-side via KDB-X across EV/EBITDA, P/E, P/B, ROCE, Operating Margins, Net Debt/EBITDA, FCF Yield, and Peer Medians.
---

# Indian Peer Comps (`/comps-india`)

1. Collect 3–8 listed NSE peer tickers (appending `.NS` if omitted; resolve names via `search_equities` if needed).
2. Call `comps_india(tickers=[...])` to evaluate all peers uniformly in PyKX KDB-X.
3. Optionally call `screener_india(symbol=...)` for 10-year ROCE/OPM context, compute peer **Mean/Median**, explain premium/discount spreads via ROCE & Growth differentials, and flag Hard Vetoes.
