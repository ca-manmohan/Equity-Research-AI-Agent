---
name: audit-qc-india
description: Standard Statement Hygiene, Audit QC & Portfolio Risk Rules (/audit-qc-india). Checks Auditor Opinion, Promoter Pledge, CFO vs PAT, Debt/Coverage, Contingent Liabilities, and Position Sizing.
---

# Audit Hygiene QC & Portfolio Risk (`/audit-qc-india`)

1. Pass NSE Annual Report PDFs (`pdf_path`) or filing text to `audit_filing_and_external_risks(ticker, sector, ...)` to check **Auditor Opinion** (Unmodified vs. Qualified/Adverse/Going Concern) and **Contingent Liabilities / RPTs**.
2. Verify core hygiene metrics from `inspect_stock_deeply` & `screener_india`: `CFO/PAT > 0.80x`, `Interest Coverage > 4x`, `Debt/Equity < 0.5x`, and **Promoter Pledge = 0%**.
3. Apply portfolio discipline for individual investors: max `8–10%` position size at cost, 12–20 stock diversification, staged buying, and 2–3 objective Thesis-Break rules.
