# Advanced Fundamental Analysis Framework (2026 Institutional & Quantitative Edition)

> **Purpose:** The segregated **Advanced Quantitative & Forensic Research** blueprint for our End-to-End AI Fundamental Research Analyst—synthesizing 2024–2026 empirical asset-pricing, intangible-adjusted capital, Reverse-DCF, CARO/litigation/war forensics, and 100-point multibagger scoring. For the **Basic / Industry-Standard Fundamental Analysis Guide** modeled on `anthropics/financial-services` (3-Statement Analysis, Core Ratios, Comps, Standard DCF, Earnings Variance, Audit QC), see [FundamentalAnalysis.md](FundamentalAnalysis.md).

---

## Index

1. [Objective](#1-objective)
2. [Stage 0: Investor Profile & Interest Configuration (Flexibility Engine)](#2-stage-0-investor-profile--interest-configuration-flexibility-engine)
3. [Fundamental Weightage Architecture (100-Point Model)](#3-fundamental-weightage-architecture-100-point-model)
4. [The Six-Layer Institutional Framework (Updated with External & Audit Risk Controls)](#4-the-six-layer-institutional-framework-updated-with-external--audit-risk-controls)
   - [Layer 1: Forensic Cash, Accrual & Debt/Loan Dependency (20%)](#layer-1-forensic-cash-accrual--debtloan-dependency-20)
   - [Layer 2: Intangible-Adjusted Economic Capital, Reinvestment & ROIC–WACC Engine (25%)](#layer-2-intangible-adjusted-economic-capital-reinvestment--roicwacc-engine-25)
   - [Layer 3: Multi-Factor Quality × Adjusted Valuation & Reverse DCF (20%)](#layer-3-multi-factor-quality--adjusted-valuation--reverse-dcf-20)
   - [Layer 4: Audit Report, Litigation, Material Items & Governance Forensics (15%)](#layer-4-audit-report-litigation-material-items--governance-forensics-15)
   - [Layer 5: External Macro, Geopolitics (War/Tariffs), Govt Contracts & Flow Catalysts (10%)](#layer-5-external-macro-geopolitics-wartariffs-govt-contracts--flow-catalysts-10)
   - [Layer 6: Deployment Readiness, Sector Finalization & Risk Architecture (10% + Portfolio Rules)](#layer-6-deployment-readiness-sector-finalization--risk-architecture-10--portfolio-rules)
5. [Hard Veto & External Risk Matrix](#5-hard-veto--external-risk-matrix)
6. [Sector-Specific Finalization Playbook](#6-sector-specific-finalization-playbook)
7. [End-to-End AI Fundamental Research Analyst Workflow](#7-end-to-end-ai-fundamental-research-analyst-workflow)
8. [Free & Low-Friction Data Stack](#8-free--low-friction-data-stack)
9. [Core Research References](#9-core-research-references)

---

## 1. Objective

The primary objective of this framework is to **systematically scan, rank, and identify long-term multibagger stocks** using a disciplined, weighted fundamental architecture—customized to the investor's interests—rather than narrative hype or static valuation ratios.

Long-term multibaggers share a rare mathematical profile—two engines compounding together over 5–10+ years *without* blowing up from hidden leverage, audit fraud, or external shocks:
1. **High-ROIC Reinvestment Compounding:** A business earns sustained returns well above its cost of capital ($\text{ROIC} \gg \text{WACC}$) *and* possesses a long runway to reinvest incremental cash flows at high incremental returns.
2. **Valuation & Institutional Re-Rating:** That cash-compounding engine is acquired before market expectations and passive/institutional flows fully price in its terminal scale.
3. **External & Forensic Survivability:** The company is resilient against **huge bank-loan refinancing stress, concentrated government-contract payment delays, adverse audit remarks, material litigation, macro tightening, and geopolitical/war disruptions**.

---

## 2. Stage 0: Investor Profile & Interest Configuration (Flexibility Engine)

Before scanning a single stock, the **AI Fundamental Research Analyst** collects the investor's preferences so screening, sector rules, and weightage tilts match their exact mandate:

| Configuration Dimension | Investor Options / Inputs | How the Framework Adapts |
| :--- | :--- | :--- |
| **1. Financial Goal & Pain Budget** | Target Multiple (`2x–3x` \| `3x–5x` \| `5x–10x+`), Horizon (`3–10+ yrs`), Max Drawdown Tolerance (`15%` \| `30%` \| `45%`) | Auto-recommends Strategy Archetype (e.g., `multibagger_hunter`) & Market-Cap Runway (`small_mid` vs. `large`) |
| **2. Market & Universe** | India (`NSE/BSE`), Canada (`TSX/TSXV`), US, or Global; Market-cap focus (`small_mid`, `all`, `large`) | Selects regional accounting taxonomy (Ind-AS / IFRS / US GAAP), local filings (NSE/BSE, SEDAR+, SEC EDGAR), and liquidity thresholds |
| **3. Sector & Theme Interests** | e.g., Defense, Energy/Power, Specialty Chemicals, IT/AI, Financials, Pharma, Infra, or *Sector-Agnostic* | Restricts/prioritizes universe and activates **Sector-Specific Finalization Checks** (Section 6) |
| **4. Strategy Archetype** | *Multibagger Hunter* \| *Compounder Growth* \| *Deep Value / Turnaround* \| *Policy & Capex Beneficiary* \| *Conservative Income* | Applies bounded **$\pm 5\text{–}10\%$ weight tilts** across Layers 1–5 (e.g., Multibagger Hunter tilts toward Layer 2 ROIC/Reinvestment + Small/Mid Runway) |
| **5. Exclusion & Ethical Filters** | Custom exclusions (e.g., zero alcohol/tobacco/gambling, zero PSU/govt-contract reliance, zero net debt) | Converts user preferences into Stage-1 hard exclusion rules |

> **Non-Negotiable Guardrail:** Investor weight tilts can emphasize growth, value, or themes, **but cannot disable Hard Vetoes** (adverse audit opinions, distressed bank-loan traps, or fraud/litigation blowups).

---

## 3. Fundamental Weightage Architecture (100-Point Model)

Every candidate is scored out of **100 points** across six weighted layers (shown with the default institutional baseline weights):

| Layer | Core Domain | Baseline Weight | Primary Multibagger & Risk Role |
| :--- | :--- | :---: | :--- |
| **Layer 1** | **Forensic Cash, Accrual & Debt/Loan Dependency** | **20%** | Eliminates paper-profit illusions and **huge bank-loan / refinancing traps** |
| **Layer 2** | **Intangible-Adjusted Capital, Reinvestment & ROIC–WACC** | **25%** | Identifies the core compounding engine (high incremental ROIC + reinvestment runway) |
| **Layer 3** | **Multi-Factor Quality × Adjusted Valuation & Reverse DCF** | **20%** | Prevents overpaying for hype while capturing mispriced growth & intangible value ($HML_{INT}$) |
| **Layer 4** | **Audit Report, Litigation, Material Items & Governance** | **15%** | Audits **adverse auditor remarks, litigation clauses, material items, RPTs & concall drift** |
| **Layer 5** | **External Macro, Geopolitics, Govt Contracts & Flows** | **10%** | Stress-tests against **economy, interest rates, war/tariffs, govt-contract reliance & flows** |
| **Layer 6** | **Deployment Readiness, Sector Finalization & Liquidity** | **10%** | Enforces **sector-specific checks**, exit liquidity, and falsifiable thesis kill-switches |
| **Total** | **Composite Institutional Multibagger Score** | **100%** | **Action Threshold: `>= 75/100` (with zero Hard Vetoes triggered)** |

---

## 4. The Six-Layer Institutional Framework (Updated with External & Audit Risk Controls)

### Layer 1: Forensic Cash, Accrual & Debt/Loan Dependency (20%)
*Research Anchor: Ball, Gerakos, Linnainmaa & Nikolaev (2016, Journal of Financial Economics) — Cash-Based Operating Profitability.*

Accounting profits mean little if trapped in receivables or funded by dangerous debt. Under elevated cost-of-capital regimes, heavy reliance on **huge bank loans** turns a cyclical slowdown into permanent equity dilution or insolvency.

* **Sub-Weightage Breakdown (20 pts):**
  * **Cash-Based Operating Profitability (7 pts):** $(\text{Operating Profit} - \Delta \text{Working Capital Accruals}) / \text{Total Assets}$ ranked against sector peers.
  * **Multi-Year Cash Conversion (5 pts):** 3–5 year cumulative $\text{CFO} / \text{EBITDA} \ge 0.75\text{–}0.85$ and $\text{FCF} / \text{PAT}$ quality check.
  * **Working Capital & Receivable Hygiene (4 pts):** Receivable Days (DSO) and Inventory Days stable/improving vs. Revenue growth.
  * **Bank-Loan & Debt-Refinancing Resilience (4 pts):**
    * Track `Net Debt / EBITDA` ($< 1.5\text{x}$ preferred for non-financials), `Interest Coverage` ($> 4\text{–}5\text{x}$), and **short-term vs. long-term bank loan dependency**.
    * Audit **debt maturity wall** (next 12–24 months), **floating-rate exposure**, **credit rating trajectory** (upgrades vs. downgrades), and **promoter shares pledged to banks**.

---

### Layer 2: Intangible-Adjusted Economic Capital, Reinvestment & ROIC–WACC Engine (25%)
*Research Anchors: Eisfeldt, Kim & Papanikolaou (2022, Critical Finance Review — $HML_{INT}$); Arnott, Harvey, Kalesnik & Linnainmaa (2021); modern ROIC & capex discipline literature.*

Multibaggers come from companies with **wide economic moats**, **high incremental ROIC**, and **abundant reinvestment opportunities**—including asset-light compounders whose true investments sit inside expensed intangibles (R&D, software, brand equity, distribution).

* **Sub-Weightage Breakdown (25 pts):**
  * **Incremental ROIC & ROIC–WACC Spread (10 pts):**
    * $\text{Incremental ROIC} = \Delta \text{NOPAT} / \Delta \text{Invested Capital}$ over rolling 3–5 year windows.
    * Require persistent spread ($\text{ROIC} - \text{WACC} > +5\%$ to $+10\%$).
  * **Reinvestment Runway & Capex Efficiency (8 pts):**
    * High reinvestment rate ($\text{Reinvestment} / \text{NOPAT}$) paired with stable/rising asset turns and gross margins (confirming capex generates real cash returns, not empire building).
    * Market-share expansion within a growing or consolidating profit pool.
  * **Intangible-Adjusted Capital & Shareholder Yield (7 pts):**
    * Capitalize R&D and strategic SG&A (brand/software/customer acquisition) into Invested Capital & Book Value.
    * Evaluate **Total Shareholder Yield** (dividends + net buybacks + net debt reduction) when excess cash exceeds high-ROIC reinvestment needs.

---

### Layer 3: Multi-Factor Quality × Adjusted Valuation & Reverse DCF (20%)
*Research Anchors: Quality-Value factor integration (Asness/QMJ, updated Piotroski F-Score / Mohanram G-Score blends); $HML_{INT}$ valuation.*

Multibaggers sit at the intersection of **compounder quality** and **mispriced growth expectations**.

* **Sub-Weightage Breakdown (20 pts):**
  * **Composite Quality-Value Alignment (8 pts):** Rank simultaneously on Quality (ROIC stability, gross margin durability, low leverage) and Valuation ($\text{EV} / \text{NOPAT}$, FCF Yield, Intangible-Adjusted Price-to-Book $HML_{INT}$).
  * **Reverse DCF Implied Expectations Check (7 pts):** Invert current Enterprise Value to compute the **implied 5–7 year FCF/NOPAT growth rate** already priced in. Target businesses where current price implies modest growth while fundamentals support much faster compounding.
  * **Operating Leverage Asymmetry (5 pts):** Margin structure where incremental revenue drops disproportionately to EBIT and FCF.

---

### Layer 4: Audit Report, Litigation, Material Items & Governance Forensics (15%)
*Research Anchors: 2024–2026 Regulatory Filing & Earnings Call NLP research; Kim, Muhn & Nikolaev (2024; withdrawn Feb 2025).*

Because **Kim, Muhn & Nikolaev (2024)** was withdrawn in February 2025 over replication inconsistencies, an AI analyst in 2026 must never act as a black-box oracle. Instead, it uses structured NLP/LLM extraction as a **forensic audit engine** over statutory reports and concalls:

* **Sub-Weightage Breakdown (15 pts):**
  * **Independent Auditor's Report & Remarks Audit (5 pts):**
    * Scan for **Adverse Opinions, Disclaimers, Qualified Opinions, Going Concern warnings, Emphasis of Matter (EOM)**, internal financial control weaknesses (ICFR), and frequent auditor resignations/rotations.
  * **Litigation Clause & Contingent Liability Audit (4 pts):**
    * Extract **Pending Litigations** (tax disputes, regulatory penalties, environmental/IP/arbitration claims) and **Contingent Liabilities** from Audit Reports & Notes to Accounts.
    * Measure $\text{Contingent Liabilities} / \text{Net Worth}$ and assess probability of cash outflow.
  * **Material Items, RPTs & Concall Tone Drift (6 pts):**
    * Flag recurring **"Material / Exceptional Items"**, unexplained write-offs, aggressive revenue/depreciation policy shifts, and **Related-Party Transactions (RPTs)** with promoter entities.
    * Compare *Prepared Remarks* vs. *Unscripted Q&A* across 4 quarters for evasive answers or shifting KPI definitions; check promoter holding stability and zero dilution.

---

### Layer 5: External Macro, Geopolitics (War/Tariffs), Govt Contracts & Flow Catalysts (10%)
*Research Anchor: Gabaix & Koijen — The Inelastic Markets Hypothesis (IMH) + External Macro/Policy Stress Modeling.*

A company with clean internal ratios can still be derailed—or propelled—by external dependencies and inelastic institutional flows (~5x flow-to-market-cap multiplier).

* **Sub-Weightage Breakdown (10 pts):**
  * **Government Contract & Counterparty Dependency (3 pts):**
    * Measure `% of Revenue / Order Book` tied to government tenders, subsidies, or single customers.
    * Distinguish **high-visibility, escrow/milestone-backed strategic orders** (e.g., defense localization) from **low-margin, delayed-payment govt EPC contracts** (which spike working-capital debt and stall around elections/budget freezes).
  * **Macro Economy, War & Geopolitical Stress Exposure (4 pts):**
    * **Economy & Rates:** Cyclical demand sensitivity, pricing power under inflation, and FX mismatch (export revenues vs. imported raw materials/FX debt).
    * **War, Sanctions & Trade Shocks:** Exposure to conflict zones, maritime chokepoints, energy/commodity price spikes (crude, gas, metals), export bans, and tariff regimes—identifying whether the company is a **net beneficiary** (supply-chain reshoring, defense) or **vulnerable** (single-region sourcing/export).
  * **Institutional Discovery & Flow Catalysts (3 pts):**
    * Under-owned quality scaling toward institutional/index inclusion + identifiable 6–24 month catalysts (capacity ramp, deleveraging inflection, new export approvals).

---

### Layer 6: Deployment Readiness, Sector Finalization & Risk Architecture (10% + Portfolio Rules)

* **Sub-Weightage Breakdown (10 pts — Stock-Level Resilience & Finalization):**
  * **Sector-Specific Finalization Pass (4 pts):** Score against the tailored sector KPIs in Section 6.
  * **Balance-Sheet Downturn Stress Test (3 pts):** Can the firm survive 12–18 months of zero growth or delayed receivables without emergency bank loans or distressed dilution?
  * **Exit Liquidity Score (3 pts):** Position capacity relative to Average Daily Traded Value (ADTV).

* **Mandatory Portfolio Execution Rules:**
  1. **Staged Bayesian Deployment:**
     * *Starter Tranche (`25–30%` of target position):* Enter when composite score $\ge 75$, zero Hard Vetoes exist, and Reverse DCF is favorable.
     * *Confirmation Tranches (`70%`):* Add only as subsequent quarterly cash conversion, incremental ROIC, order-book execution, and audit/debt metrics validate the thesis.
  2. **Concentration with Guardrails:**
     * Target **12–20 stocks** across non-correlated themes/factors.
     * Cap initial cost at `5–8%` (core) / `2–4%` (emerging) and any single sector/macro theme (e.g., all govt-contract plays or all rate-sensitives) at `20–25%`.
  3. **Pre-Committed Thesis Kill-Switches (Written Before Entry):**
     * Define 3 falsifiable exit triggers upfront (e.g., *qualified audit remark / sudden auditor resignation*, *2-year CFO/EBITDA < 65%*, *bank-loan spike pushing Net Debt/EBITDA > 2.5x*, or *incremental ROIC < WACC*).

---

## 5. Hard Veto & External Risk Matrix

The AI Analyst automatically assigns a **HOLD / REJECT (Hard Veto)** or **Severity Penalty** whenever any critical risk triggers:

| Risk Factor | Trigger Condition | Action |
| :--- | :--- | :--- |
| **Adverse / Disclaimer Audit Opinion** | Auditor issues Adverse Opinion, Disclaimer, or Going Concern doubt | **HARD VETO (Reject)** |
| **Qualified Audit / Auditor Exit** | Unresolved Qualified Opinion on revenue/inventory/cash, or sudden mid-term auditor resignation | **HARD VETO / Deep Manual Review** |
| **Material Litigation / Contingencies** | Pending tax/regulatory/IP litigation or Contingent Liabilities $> 25\%$ of Net Worth with high outflow risk | **-10 pts to HARD VETO** |
| **Huge Bank Loan & Refinancing Trap** | `Net Debt / EBITDA > 3.0x` + `Interest Coverage < 2.0x` + near-term maturity wall or rating downgrade | **HARD VETO** |
| **Promoter Pledge & RPT Abuse** | Promoter pledge $> 20\%$ (non-operational) or material cash leakage via unapproved/opaque RPTs | **HARD VETO** |
| **Toxic Govt Contract Dependency** | $> 50\%$ revenue from govt tenders **AND** Receivable Days $> 150\text{–}180$ rising with rising bank overdrafts | **-8 pts Penalty + Stress Cap** |
| **Material Items / Accounting Churn** | Frequent "Exceptional Losses/Items" $> 15\%$ of PAT over 3+ years or repeated accounting policy changes | **-6 pts Penalty + Forensic Flag** |
| **War / Geopolitical Chokepoint Risk** | $> 30\%$ revenue or critical single-source input exposed to active conflict, sanction, or tariff-targeted corridor | **Scenario Haircut in Reverse DCF** |

---

## 6. Sector-Specific Finalization Playbook

Before finalizing any stock in Stage 6, the AI Analyst switches to the relevant **sector lens** (aligned with the investor's Stage 0 interests):

* **Defense / Infra / Capital Goods / Govt-Contractors:** Order Book-to-Bill (`2–4x`), milestone payment terms, Govt Receivable Days, Net Working Capital % of Sales, bank guarantee limits, and execution track record without cost overruns.
* **Banks / NBFCs / Financial Services:** Net Interest Margin (NIM), GNPA / NNPA trend, Provision Coverage Ratio (PCR), Return on Assets (RoA), Capital Adequacy (CAR), unsecured vs. secured book mix, and ALM liquidity mismatch.
* **Pharma / Specialty Chemicals:** USFDA / regulatory inspection history (OAI / Warning Letters), R&D % of Sales, molecule/product concentration, raw-material import dependency (e.g., China+1 / geopolitical tariff exposure), and backward integration.
* **IT / SaaS / Digital Platforms:** Net Dollar Retention (NDR), top-5/top-10 client concentration, attrition, intangible R&D productivity, and AI-automation pricing resilience.
* **Manufacturing / Consumer / Commodities:** Capacity utilization, gross-margin pass-through during raw-material inflation (crude/metal spikes), distribution moat, and normalized mid-cycle ROIC (avoiding peak-cycle low-P/E traps).

---

## 7. End-to-End AI Fundamental Research Analyst Workflow

To implement this as an **end-to-end AI system**, split responsibilities cleanly between **deterministic math** (zero hallucination) and **auditable LLM/NLP extraction** (cited directly to source pages):

```text
[Stage 0] Investor Intake Agent
    │     Captures: Market, Sector Interests, Strategy Archetype, Horizon, Exclusions
    ▼
[Stage 1] Deterministic Quantitative Scanner (Python)
    │     Pulls prices & statements -> Runs Hygiene Gates -> Scores Layers 1, 2, 3 & Liquidity (75 pts)
    ▼
[Stage 2] Forensic Document & External Risk Agent (RAG / NLP over Primary Filings)
    │     Reads: Independent Auditor's Report, Litigation & Contingent Notes, Material Items,
    │            Bank Loan / Credit Rating notes, Order Book / Govt Contract DSO, Concall Q&As
    │     Scans: Macro / Interest-Rate / War / Tariff / Supply-Chain news overlays
    │     Scores: Layers 4, 5 & Sector Finalization (25 pts) + checks Hard Vetoes
    ▼
[Stage 3] Finalization & Investment Memo Generator
          Outputs:
          1. 100-Point Weighted Scorecard (with Investor-Specific Tilts & Exact Citations)
          2. Hard-Veto & External Risk Audit Table (Bank Loans, Audit Remarks, Litigation, War/Macro)
          3. Reverse-DCF Expectations vs. Bull/Base/Bear Scenarios
          4. Staged Tranche Deployment Plan + 3 Falsifiable Thesis Kill-Switches
```

> **Design Principle:** Never ask an LLM to guess financial ratios from memory. All financial ratios (Layers 1–3) are computed deterministically in code from structured statements; the LLM/NLP layer strictly reads, extracts, cross-checks, and cites primary text disclosures (Layers 4–5).

---

## 8. Free & Low-Friction Data Stack

* **Quantitative Screening & Prototyping (Layers 1–3):**
  * **Python (`yfinance`):** Free programmatic access to US, Canadian (`.TO` / `.V`), and Indian (`.NS` / `.BO`) price history and ~4–5 years of Income Statement, Balance Sheet, and Cash Flow tables.
  * **India 10-Year Fundamentals:** **Screener.in** (free tier + Excel export) and official **BSE/NSE XBRL filings** for full 10-year cycle depth and promoter pledges.
  * **US Official 10-Year Fundamentals:** **SEC EDGAR API** (`data.sec.gov`, free and official).
* **Forensic Audit & External Risk Documents (Layers 4–6):**
  * **Annual Reports (Independent Auditor's Report, Notes to Accounts, Contingent Liabilities, Bank Borrowings), Credit Rating Rationales, Investor Presentations & Concall Transcripts** via **NSE/BSE Filings**, **SEDAR+** (Canada), or **SEC EDGAR** (US).
* **Macro & Geopolitical Feeds (Layer 5):**
  * Central bank policy/yield curves, commodity indices (Brent, metals), FX rates, and structured news/tariff/defense feeds.

---

## 9. Core Research References

1. **Ball, R., Gerakos, J., Linnainmaa, J. T., & Nikolaev, V. (2016).** *Accruals, Cash Flows, and Operating Profitability in the Cross Section of Stock Returns.* Journal of Financial Economics.
2. **Eisfeldt, A. L., Kim, E. T., & Papanikolaou, D. (2022).** *Intangible Value.* Critical Finance Review.
3. **Arnott, R. D., Harvey, C. R., Kalesnik, V., & Linnainmaa, J. T. (2021).** *Reports of Value's Death May Be Greatly Exaggerated.* Financial Analysts Journal.
4. **Gabaix, X., & Koijen, R. S. J. (2021/ongoing).** *In Search of the Origins of Financial Fluctuations: The Inelastic Markets Hypothesis.*
5. **Kim, A., Muhn, M., & Nikolaev, V. (2024; withdrawn Feb 2025).** *Financial Statement Analysis with Large Language Models.* (Key cautionary benchmark: LLMs must be used for cited forensic extraction, never as unverified black-box return predictors.)
6. **Regulatory Filing & Earnings Call NLP Literature (2024–2026).** *Extraction of durable management tone, capital allocation discipline, and guidance uncertainty signals from unstructured corporate disclosures.*
