---
name: earnings-india
description: Indian Quarterly Results & Concall Review (/earnings-india). Tracks YoY/QoQ Revenue, EBIT Margin inflection, PAT, and management concall Q&A tone drift.
---

# Indian Quarterly Earnings Review (`/earnings-india`)

1. Call `earnings_india(symbol)` to extract the latest 5 quarterly Ind-AS periods (Revenue, EBIT, PAT, EBIT Margin %, YoY Revenue & PAT growth).
2. If the user provides a concall transcript or press release, pass it to `audit_filing_and_external_risks` to detect guidance softening, working-capital excuses, or capex delays.
3. Verify whether quarterly execution supports scaling from Starter Tranche (`25-30%`) to Confirmation Tranches (`70%`).
