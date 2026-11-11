# Fundamental Analysis Guide (Industry-Standard Indian Investor Edition)

> **Purpose:** A practical, **actual industry-standard** fundamental analysis framework modeled on the core equity research workflows of [`anthropics/financial-services`](https://github.com/anthropics/financial-services) (`goal-intake`, `idea-generation`, `/3-statement-model`, `/comps`, `/dcf`, `/earnings`, and `/audit` QC)—rebuilt for **self-directed Indian equity investors** using **100% free Indian data sources** and **KDB-X (PyKX)**.
>
> **Segregation Note:** This document covers **core, industry-standard fundamental analysis** (3-statement links, standard ratios, peer comps, standard FCFF DCF, quarterly earnings, and basic audit hygiene). For advanced 2026 academic/quantitative theory (6-layer 100-pt weighted scoring, Ball et al. cash-based profitability, Eisfeldt $HML_{INT}$, Gabaix–Koijen inelastic flows, Reverse-DCF bisection, and deep CARO/war/litigation/bank-loan forensics), see [**AdvancedFundamentalAnalysis.md**](AdvancedFundamentalAnalysis.md).

---

## Index

1. [Objective & Workflow Map](#1-objective--workflow-map)
2. [Stage 0: Investor Goal Intake (`goal-intake`)](#2-stage-0-investor-goal-intake-goal-intake)
3. [Three-Statement Analysis (`three-statement-india`)](#3-three-statement-analysis-three-statement-india)
4. [Core Industry-Standard Ratios & Indian Benchmarks](#4-core-industry-standard-ratios--indian-benchmarks)
5. [Idea Generation & Equity Screening (`idea-generation`)](#5-idea-generation--equity-screening-idea-generation)
6. [Comparable Company Analysis (`comps-india`)](#6-comparable-company-analysis-comps-india)
7. [Standard Intrinsic Valuation: FCFF DCF (`dcf-india`)](#7-standard-intrinsic-valuation-fcff-dcf-dcf-india)
8. [Quarterly Earnings Variance Review (`earnings-india`)](#8-quarterly-earnings-variance-review-earnings-india)
9. [Audit Hygiene QC & Portfolio Risk Rules (`audit-qc-india`)](#9-audit-hygiene-qc--portfolio-risk-rules-audit-qc-india)
10. [100% Free Indian Data Stack & KDB-X Engine](#10-100-free-indian-data-stack--kdb-x-engine)

---

## 1. Objective & Workflow Map

The goal is to give an individual Indian investor an institutional-quality, repeatable workflow—without advisor sales pitchbooks or expensive Bloomberg/FactSet/S&P subscriptions.

| Industry-Standard Workflow (`anthropics/financial-services`) | Indian Investor Skill (`indian-investor-plugin`) | Free Tool / Data Source |
| :--- | :--- | :--- |
| Goal & Mandate Discovery | `goal-intake` | `set_investor_mandate` |
| Idea Generation / Equity Screening | `idea-generation` | `scan_and_rank_kdb`, `screener_india` |
| 3-Statement Financial Analysis | `three-statement-india` | `inspect_stock_deeply`, Screener `.xlsx` |
| Comparable Company Analysis (`/comps`) | `comps-india` | `comps_india` (KDB-X peer table) |
| Discounted Cash Flow (`/dcf`) | `dcf-india` | Standard 5–10 yr FCFF + WACC Sensitivity |
| Quarterly Earnings Analysis (`/earnings`) | `earnings-india` | `earnings_india` (`yfinance` + NSE PDFs) |
| Model & Statement Hygiene QC (`/audit`) | `audit-qc-india` | `audit_filing_and_external_risks` |
| *Optional 2026 Quant/Forensic Layer* | `advanced-research-2026` | See `AdvancedFundamentalAnalysis.md` |

---

## 2. Stage 0: Investor Goal Intake (`goal-intake`)

Before screening stocks, define what the investor actually wants so valuation and risk match the mandate:

1. **Return Objective & Horizon:** Compounding steady wealth (`12–15%` CAGR over `5+` yrs), high-growth wealth creation (`18–25%+` CAGR / `3x–5x+` over `5–10` yrs), or dividend/capital preservation.
2. **Drawdown Tolerance:** Conservative (`≤15%`), Moderate (`≤30%`), or High (`≤45%` for small/mid-caps).
3. **Circle of Competence:** Preferred NSE sectors (IT, Pharma, Banking/NBFC, Capital Goods/Defense, Auto/Ancillaries, Consumer/FMCG, Chemicals) and personal exclusions (e.g., avoid tobacco, airlines, PSU, or high-debt companies).
4. **Capital & Liquidity Check:** Avoid illiquid micro-caps where daily traded value cannot easily absorb position entries or exits.

---

## 3. Three-Statement Analysis (`three-statement-india`)

Under **Ind-AS** (Indian Accounting Standards), always analyze all three statements together rather than looking at Net Profit alone:

### A. Income Statement (Statement of Profit & Loss)
- **Revenue from Operations (Top-Line):** Separate core operating revenue from **Other Income** (treasury interest, FX gains, one-off asset sales).
- **EBITDA & Operating Profit Margin (OPM %):** $(Revenue - RM - Employee - Other Expenses) / Revenue$. Watch gross margin stability (pricing power) vs. operating leverage.
- **Depreciation & Finance Cost:** Check if high capex is inflating D&A or if rising debt is consuming EBIT.
- **PAT & Exceptional Items:** Always strip out one-time gains/losses to compute **Normalized / Adjusted PAT**.

### B. Balance Sheet (Statement of Assets & Liabilities)
- **Equity & Reserves:** Track steady retained earnings growth vs. frequent equity dilution (QIPs, preferential allotments, warrants).
- **Borrowings (Long-Term + Short-Term) & Lease Liabilities (Ind-AS 116):** Compare Total Debt against Cash & Liquid Investments (`Net Debt = Total Debt - Cash`).
- **Working Capital Tie-Up:** Inspect Trade Receivables, Inventory, and Trade Payables—rising sales accompanied by exploding receivables often signals channel stuffing or delayed government/customer collections.
- **CWIP (Capital Work in Progress):** Indicates upcoming capacity expansion before revenue shows up on the P&L.

### C. Cash Flow Statement
- **CFO (Cash Flow from Operations):** The ultimate truth test of accounting profits. Over a 3–5 year cycle, cumulative `CFO` should closely track cumulative `PAT` or `EBITDA`.
- **CFI (Cash Flow from Investing):** Maintenance + Growth Capex (`Purchase of PPE / Intangibles`).
- **FCF (Free Cash Flow):** $FCF = CFO - Capex$. Positive or inflection-point FCF reduces dependence on external dilution or bank loans.
- **CFF (Cash Flow from Financing):** Track net debt issuance/repayment, interest paid, dividends, and buybacks.

---

## 4. Core Industry-Standard Ratios & Indian Benchmarks

| Category | Ratio | Formula | Healthy Indian Benchmark | Red Flag |
| :--- | :--- | :--- | :--- | :--- |
| **Return on Capital** | **ROCE %** | $EBIT / Capital Employed$ | `> 15%` (exceptional `> 20%`) | `< 10%` (below Indian cost of capital) |
| **Return on Equity** | **ROE %** | $PAT / Shareholders' Equity$ | `> 15%` without high leverage | High ROE driven solely by `D/E > 1.5x` |
| **Cash Quality** | **CFO / PAT (3Y–5Y)** | $\sum CFO / \sum PAT$ | `> 0.80x` (`CFO/EBITDA > 0.65x`) | `< 0.50x` repeatedly |
| **Solvency** | **Debt / Equity** | $Total Debt / Equity$ | `< 0.5x` (Non-financials) | `> 1.5x` or rising short-term debt |
| **Solvency** | **Net Debt / EBITDA** | $(Debt - Cash) / EBITDA$ | `< 1.5x` | `> 3.0x` |
| **Coverage** | **Interest Coverage** | $EBIT / Finance Cost$ | `> 4.0x` | `< 2.0x` |
| **Working Capital** | **Debtor Days** | $(Receivables / Revenue) \times 365$ | Stable or declining (`< 60–90` days) | Sudden spike (`> 120` days) |
| **Growth & Quality** | **5Y Sales & PAT CAGR** | $(X_t / X_{t-5})^{1/5} - 1$ | Sales `> 12%`, PAT `≥ Sales CAGR` | PAT growth from tax/other income only |
| **Valuation** | **P/E, EV/EBITDA, PEG** | Price/EPS, EV/EBITDA, (P/E)/CAGR | Reasonable vs. 5Y median & ROE/ROCE | High multiple with falling ROCE |

*(Note: For **Banks & NBFCs**, replace ROCE/Debt-to-Equity with **ROA (`> 1.2%`)**, **ROE (`> 14%`)**, **NIM (`> 3.5%`)**, **GNPA / NNPA**, **PCR (`> 70%`)**, **CASA %**, **Cost-to-Income**, and **Price-to-Book (P/B)**.)*

---

## 5. Idea Generation & Equity Screening (`idea-generation`)

Run clean, standard multi-filter screens across NSE/BSE (`NIFTY 50`, `NIFTY NEXT 50`, `NIFTY MIDCAP 150`, `NIFTY SMALLCAP 250`, or sector baskets):

- **Core Compounder Screen:** `ROCE > 18%` AND `ROE > 15%` AND `Debt/Equity < 0.5` AND `5Y Sales CAGR > 12%` AND `CFO/PAT (5Y) > 0.8` AND `Promoter Pledge = 0%`.
- **GARP (Growth at a Reasonable Price) Screen:** `ROCE > 15%` AND `3Y PAT CAGR > 18%` AND `PEG < 1.5` AND `Interest Coverage > 4x`.
- **Value / Cyclical Reversal Screen:** `EV/EBITDA < 5Y Median` OR `P/E < Peer Median` with `Net Debt/EBITDA < 1.5x` and stabilizing operating margins.

---

## 6. Comparable Company Analysis (`comps-india`)

Never value a stock in isolation. Compare `3–8` listed Indian peers within the exact same sub-industry:

1. **Standardize Metrics:** Compare Market Cap (INR Cr), Enterprise Value (`Market Cap + Total Debt - Cash`), LTM Revenue Growth %, EBITDA Margin %, ROCE %, Net Debt/EBITDA, P/E, EV/EBITDA, P/B, and FCF Yield %.
2. **Compute Peer Statistics:** Calculate Peer **Mean**, **Median**, and **Upper/Lower Quartiles**.
3. **Explain the Spread:** If Company A trades at `28x EV/EBITDA` while peers trade at `18x`, verify whether A genuinely earns superior `ROCE`, higher growth, and cleaner cash conversion—or is simply overvalued.

---

## 7. Standard Intrinsic Valuation: FCFF DCF (`dcf-india`)

Use an industry-standard **5-year or 10-year Unlevered Free Cash Flow (FCFF)** DCF in INR Crores:

1. **Project FCFF (Years $1..N$):**
   $$FCFF_t = EBIT_t \times (1 - \text{Effective Tax Rate}) + D\&A_t - Capex_t - \Delta Working Capital_t$$
   *(Default Indian corporate marginal tax assumption: ~`25.17%` under Section 115BAA unless exempt.)*
2. **Discount Rate (Indian WACC):**
   - Risk-Free Rate ($R_f$): 10Y Indian G-Sec yield (~`6.8%–7.2%`).
   - Equity Risk Premium ($ERP$): `5.0%–6.0%`.
   - Cost of Equity ($K_e = R_f + \beta \times ERP$): typically `11.5%–13.5%`.
   - After-tax Cost of Debt: $K_d \times (1 - t)$.
   - Typical unlevered Indian corporate WACC: **`11.0%–12.5%`** (use `12.5%–14.0%` for small-caps).
3. **Terminal Value ($TV$):**
   - **Perpetuity Growth Method:** $TV = \frac{FCFF_N \times (1 + g)}{WACC - g}$, where Indian long-term nominal GDP / terminal growth $g \in [4.0\%, 5.5\%]$ (must be $< WACC$).
   - **Exit Multiple Method (Cross-Check):** $TV = EBITDA_N \times \text{Conservative Peer Median EV/EBITDA}$.
4. **Enterprise Value to Equity Value per Share:**
   $$Equity Value = PV(FCFF_{1..N}) + PV(TV) - \text{Total Debt} - \text{Minority Interest} + \text{Cash \& Liquid Investments}$$
   $$\text{Intrinsic Value per Share} = \frac{Equity Value}{\text{Diluted Share Count}}$$
5. **Sensitivity Matrix & Margin of Safety:** Always build a 2D sensitivity table (`WACC` ± 1.0% vs. `Terminal Growth` ± 0.5% or `Operating Margin` ± 100 bps) and demand a **20–30% Margin of Safety** below base-case intrinsic value.

---

## 8. Quarterly Earnings Variance Review (`earnings-india`)

Every quarter after NSE/BSE results are filed (Ind-AS Reg 33):

1. **Revenue & Volume vs. Price:** Check YoY and QoQ revenue growth; separate volume growth from raw-material price inflation.
2. **Margin Bridge:** Track Gross Margin % and OPM % QoQ/YoY—was expansion sustainable or from temporary inventory gains?
3. **Below-the-Line Quality Check:** Flag spikes in Other Income, sharp drops in effective tax rate, or ballooning interest costs.
4. **Concall & Press Release Tone:** Track order book growth, capacity utilization, working capital commentary, and whether management met prior guidance.

---

## 9. Audit Hygiene QC & Portfolio Risk Rules (`audit-qc-india`)

Before investing capital, pass every candidate through a basic statement-hygiene checklist:

1. **Auditor Opinion & CARO Check:** Must be **Unmodified (Clean)**—reject Qualified, Adverse, Disclaimer of Opinion, or Going-Concern doubts.
2. **Promoter Skin-in-the-Game & Pledges:** Check Promoter Holding stability and **Pledged Shares %** (prefer `0%`; flag `> 10%`).
3. **Related-Party Transactions (RPTs) & Contingent Liabilities:** Flag excessive RPT loans/sales to promoter entities or contingent tax/legal claims `> 15%` of Net Worth.
4. **Basic Macro & Business Risk Check:** Assess sensitivity to interest rates, commodity/FX swings, customer concentration, and heavy debt-refinancing schedules.
5. **Portfolio Discipline:** Diversify across `12–20` stocks (max `8–10%` at cost per stock), scale in via tranches, and define **2–3 objective Thesis-Break Triggers** (e.g., 2 consecutive quarters of margin collapse or unexpected debt spike) rather than reacting to daily price noise.

---

## 10. 100% Free Indian Data Stack & KDB-X Engine

| Function | Free Resource / Python Package |
| :--- | :--- |
| **Market Prices, Statements & Quarterly Results** | `yfinance` (`.NS` / `.BO` NSE & BSE tickers) |
| **10-Year Historical P&L, Balance Sheet, ROCE, Peers** | **Screener.in** public company pages & free user-exported `.xlsx` |
| **Statutory Filings, Annual Reports, Concalls, Sh. Pattern** | **NSE India / BSE India** corporate announcements & XBRL/PDFs (`pymupdf`) |
| **High-Speed Columnar Screening & Caching** | **PyKX / KDB-X** binary `.kdb` columnar tables (`KDBXEngine`) |
| **AI Agent & MCP Integration** | `fundamental_analyst_app/` CLI & `indian-investor-mcp` (`mcp_server.py`) |

---

*For advanced 2026 empirical factor scoring, Reverse-DCF bisection, Gabaix–Koijen flow impact, and deep CARO/war/litigation/bank-loan forensics, proceed to [**AdvancedFundamentalAnalysis.md**](AdvancedFundamentalAnalysis.md).*
