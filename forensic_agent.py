"""Stage 2 Forensic PDF/Text & External Risk Auditor (Layers 4, 5 & Final Memo).

Extracts cited evidence from Annual Reports, Independent Auditor's Reports,
Litigation/Contingency footnotes, and Earnings Calls, combined with external
macro/war/government-contract stress inputs to compute Layer 4 & Layer 5 scores,
Hard Vetoes, Sector-Specific Finalization checks, and the Investment Memo.
"""

from __future__ import annotations

import io
import os
import re
from typing import Any, Dict, List, Optional, Tuple

import pymupdf


FORENSIC_RULES: List[Dict[str, Any]] = [
    {
        "category": "Adverse / Disclaimer Audit Opinion",
        "severity": "VETO",
        "layer": "layer4",
        "penalty": 60,
        "patterns": [
            r"adverse opinion",
            r"disclaimer of opinion",
            r"material uncertainty.{0,60}going concern",
            r"do not give a true and fair view",
        ],
    },
    {
        "category": "Qualified Audit / Emphasis / ICFR Weakness",
        "severity": "HIGH",
        "layer": "layer4",
        "penalty": 22,
        "patterns": [
            r"qualified opinion",
            r"basis for qualified",
            r"emphasis of matter",
            r"resignation of.{0,30}auditor",
            r"internal financial controls.{0,50}weakness",
            r"caro.{0,40}default",
        ],
    },
    {
        "category": "Litigation Clause & Contingent Liabilities",
        "severity": "MEDIUM",
        "layer": "layer4",
        "penalty": 14,
        "patterns": [
            r"contingent liabilities",
            r"pending litigation",
            r"show cause notice",
            r"tax dispute",
            r"arbitration.{0,40}claim",
            r"penalty.{0,30}sebi|usfda|warning letter|import alert",
        ],
    },
    {
        "category": "Material / Exceptional Items & RPTs",
        "severity": "MEDIUM",
        "layer": "layer4",
        "penalty": 12,
        "patterns": [
            r"exceptional item",
            r"material.{0,25}(?:write[- ]?off|impairment|loss|misstatement)",
            r"related party transaction",
            r"change in accounting policy",
            r"restatement",
        ],
    },
    {
        "category": "Huge Bank Loans / Pledge / Rating Downgrade",
        "severity": "HIGH",
        "layer": "layer4",
        "penalty": 18,
        "patterns": [
            r"consortium.{0,30}bank",
            r"term loan.{0,40}(?:default|restructur|overdue|npa)",
            r"pledge[d]? shares",
            r"rating downgrade",
            r"debt covenant.{0,30}breach",
            r"working capital.{0,30}stress",
        ],
    },
    {
        "category": "Government Contract / Tender Dependency",
        "severity": "MEDIUM",
        "layer": "layer5",
        "penalty": 12,
        "patterns": [
            r"government contract",
            r"psu.{0,30}tender",
            r"delayed.{0,30}(?:receivable|milestone|payment)",
            r"ministry of defence|nhai|railways|state electricity",
            r"order book.{0,40}concentration",
        ],
    },
    {
        "category": "Economy / War / Geopolitical / Tariff Risk",
        "severity": "MEDIUM",
        "layer": "layer5",
        "penalty": 12,
        "patterns": [
            r"geopolitical|conflict|war|sanction",
            r"tariff|export control|import duty",
            r"supply chain disruption|red sea|chokepoint",
            r"foreign exchange.{0,30}(?:loss|volatility)",
            r"interest rate.{0,30}(?:hike|tightening)",
        ],
    },
]


def extract_text_from_pdf_bytes(pdf_bytes: bytes, max_pages: int = 120) -> List[Tuple[int, str]]:
    """Extract (page_number_1_based, text) tuples from an uploaded PDF."""
    pages: List[Tuple[int, str]] = []
    with pymupdf.open(stream=io.BytesIO(pdf_bytes), filetype="pdf") as doc:
        for idx, page in enumerate(doc):
            if idx >= max_pages:
                break
            pages.append((idx + 1, page.get_text("text")))
    return pages


def sector_finalization_checklist(sector: str, industry: str) -> List[str]:
    """Return Sector-Specific Finalization checks from Section 6 of FundamentalAnalysis.md."""
    combined = f"{sector} {industry}".lower()
    if any(k in combined for k in ["bank", "financial", "insurance", "credit"]):
        return [
            "Verify Net Interest Margin (NIM) stability across rate cycles",
            "Check GNPA / NNPA trend and Provision Coverage Ratio (PCR > 70%)",
            "Verify Return on Assets (RoA >= 1.5%) & Capital Adequacy (CAR)",
            "Audit unsecured retail/MFI loan share & Asset-Liability Maturity (ALM)",
        ]
    if any(k in combined for k in ["defense", "aerospace", "engineering", "construction", "infra", "industrial"]):
        return [
            "Verify Order Book-to-Bill (2x–4x healthy) & execution timeline",
            "Audit Govt/PSU Receivable Days (DSO) vs. milestone escrow backing",
            "Check bank guarantee / performance bond limits & working capital % of sales",
            "Confirm zero cost-overrun penalties or stalled tender exposure",
        ]
    if any(k in combined for k in ["health", "pharma", "biotech", "chemical"]):
        return [
            "Audit USFDA / regulatory inspection status (zero OAI / Warning Letters)",
            "Check R&D % of Sales and pipeline/molecule diversification",
            "Verify raw-material import dependency (China+1 / tariff / war chokepoints)",
            "Check backward integration and specialty mix expansion",
        ]
    if any(k in combined for k in ["tech", "software", "it ", "communication"]):
        return [
            "Check Net Dollar Retention (NDR) / repeat client revenue (>85–90%)",
            "Audit top-5 / top-10 client concentration & geographic FX mismatch",
            "Evaluate intangible R&D productivity and AI-automation moat vs. pricing pressure",
        ]
    return [
        "Verify capacity utilization & gross-margin pass-through during inflation",
        "Check raw-material / energy sensitivity (crude, metals, freight)",
        "Confirm normalized mid-cycle ROIC (avoiding peak-cycle low-P/E traps)",
    ]


def run_forensic_audit(
    symbol: str,
    stock_summary: Optional[Dict[str, Any]] = None,
    raw_text: str = "",
    pdf_pages: Optional[List[Tuple[int, str]]] = None,
    external_inputs: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Run forensic NLP & external risk assessment over text/PDF + external sliders.

    `external_inputs` supports explicit analyst overrides:
      - bank_loan_risk: 'low' | 'moderate' | 'high'
      - govt_contract_pct: float (0-100)
      - audit_status: 'clean' | 'eom_or_qualified' | 'adverse_or_going_concern'
      - litigation_pct_networth: float (0-100)
      - macro_war_exposure: 'beneficiary' | 'neutral' | 'moderate_risk' | 'high_risk'
      - institutional_catalyst: str
    """
    ext = external_inputs or {}
    corpus_pages: List[Tuple[int, str]] = []
    if pdf_pages:
        corpus_pages.extend(pdf_pages)
    if raw_text.strip():
        corpus_pages.append((0, raw_text))

    findings: List[Dict[str, Any]] = []
    vetoes: List[str] = []
    warnings: List[str] = []
    l4_penalty = 0.0
    l5_penalty = 0.0

    # 1. Pattern-based forensic scan with exact page/snippet citations
    for rule in FORENSIC_RULES:
        hits_for_rule = 0
        for page_num, text in corpus_pages:
            if not text:
                continue
            for pat in rule["patterns"]:
                for match in re.finditer(pat, text, flags=re.IGNORECASE):
                    start = max(0, match.start() - 90)
                    end = min(len(text), match.end() + 130)
                    snippet = re.sub(r"\s+", " ", text[start:end]).strip()
                    findings.append(
                        {
                            "category": rule["category"],
                            "severity": rule["severity"],
                            "page": "Pasted Text" if page_num == 0 else f"Page {page_num}",
                            "matched_term": match.group(0),
                            "snippet": snippet,
                        }
                    )
                    hits_for_rule += 1
                    if hits_for_rule >= 3:
                        break
                if hits_for_rule >= 3:
                    break
            if hits_for_rule >= 3:
                break

        if hits_for_rule > 0:
            if rule["severity"] == "VETO":
                vetoes.append(f"AUDIT TEXT VETO: {rule['category']}")
            else:
                warnings.append(f"Forensic Match: {rule['category']} ({hits_for_rule} citation(s))")
            if rule["layer"] == "layer4":
                l4_penalty += rule["penalty"]
            else:
                l5_penalty += rule["penalty"]

    # 2. Explicit External & Audit Inputs
    audit_status = str(ext.get("audit_status", "clean")).lower()
    if audit_status == "adverse_or_going_concern":
        vetoes.append("AUDITOR ADVERSE / GOING CONCERN REMARK")
        l4_penalty += 60
    elif audit_status == "eom_or_qualified":
        warnings.append("Auditor Qualified / Emphasis of Matter flagged")
        l4_penalty += 22

    lit_pct = float(ext.get("litigation_pct_networth") or 0.0)
    if lit_pct >= 25.0:
        vetoes.append(f"MATERIAL LITIGATION / CONTINGENCIES ({lit_pct:.0f}% of Net Worth)")
        l4_penalty += 30
    elif lit_pct >= 10.0:
        warnings.append(f"Elevated Contingent Liabilities ({lit_pct:.0f}% of Net Worth)")
        l4_penalty += 12

    bank_loan_risk = str(ext.get("bank_loan_risk", "low")).lower()
    if bank_loan_risk == "high":
        warnings.append("High Bank-Loan / Refinancing Dependency flagged")
        l4_penalty += 15
        l5_penalty += 8
    elif bank_loan_risk == "moderate":
        l4_penalty += 6

    govt_pct = float(ext.get("govt_contract_pct") or 0.0)
    if govt_pct >= 50.0:
        warnings.append(f"High Government Contract Concentration ({govt_pct:.0f}% of Revenue)")
        l5_penalty += 16
    elif govt_pct >= 25.0:
        l5_penalty += 6

    macro_war = str(ext.get("macro_war_exposure", "neutral")).lower()
    l5_bonus = 0.0
    if macro_war == "beneficiary":
        l5_bonus += 14.0
    elif macro_war == "high_risk":
        warnings.append("High Macro / War / Geopolitical Chokepoint Vulnerability")
        l5_penalty += 22.0
    elif macro_war == "moderate_risk":
        l5_penalty += 10.0

    catalyst = str(ext.get("institutional_catalyst") or "").strip()
    if catalyst:
        l5_bonus += 8.0

    # Base scores adjusted by forensic findings
    l4_score_pct = max(5.0, min(100.0, 82.0 - l4_penalty))
    l5_score_pct = max(5.0, min(100.0, 72.0 + l5_bonus - l5_penalty))

    # Optional LLM Synthesis if OPENAI_API_KEY is present
    llm_note = _optional_llm_forensic_note(symbol, findings, ext)

    sector = (stock_summary or {}).get("sector", "Unknown")
    industry = (stock_summary or {}).get("industry", "Unknown")
    checklist = sector_finalization_checklist(sector, industry)

    # Pre-committed Thesis Kill-Switches
    kill_switches = [
        "Auditors issue a Qualified/Adverse remark, Going Concern note, or resign mid-term.",
        "2-year cumulative CFO/EBITDA drops below 0.65x or Net Debt/EBITDA rises above 2.5x from bank loans.",
        "Incremental ROIC falls below WACC for 2 consecutive annual cycles or Contingent Liabilities cross 25% of Net Worth.",
    ]
    if govt_pct >= 25.0:
        kill_switches.append("Government contract Receivable Days (DSO) expand >160 days while short-term bank borrowings surge.")

    # Educational Risk & Operational Synthesis (SEBI-compliant, zero investment advice)
    if vetoes:
        deployment_plan = "Elevated Governance / Credit Flag: Material audit, leverage, or litigation findings require formal resolution before relying on trailing earnings."
    else:
        deployment_plan = (
            "Analytical Synthesis (Educational Use Only): Baseline audit and solvency screening passed cleanly; "
            "monitor quarterly CFO/PAT cash conversion, working-capital cycle (DSO), and return on capital versus funding cost."
        )

    return {
        "symbol": symbol,
        "layer4_score_pct": round(l4_score_pct, 1),
        "layer5_score_pct": round(l5_score_pct, 1),
        "vetoes": vetoes,
        "warnings": warnings,
        "findings": findings[:25],
        "sector_checklist": checklist,
        "kill_switches": kill_switches,
        "deployment_plan": deployment_plan,
        "catalyst": catalyst or "None specified",
        "llm_note": llm_note,
    }


def _optional_llm_forensic_note(
    symbol: str,
    findings: List[Dict[str, Any]],
    ext: Dict[str, Any],
) -> str:
    """Use OpenAI if configured, otherwise return clean deterministic analyst summary."""
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key or not findings:
        return (
            f"Deterministic Forensic Audit completed for {symbol}: "
            f"{len(findings)} document citation(s) extracted across audit, litigation, "
            f"material items, bank loans, government contracts, and macro/war factors."
        )
    try:
        from openai import OpenAI

        client = OpenAI(api_key=api_key)
        snippets = "\n".join(
            f"- [{f['page']}] {f['category']}: {f['snippet']}"
            for f in findings[:10]
        )
        prompt = (
            f"You are an institutional equity forensic analyst reviewing {symbol}.\n"
            f"External inputs: {ext}\n"
            f"Extracted filing citations:\n{snippets}\n\n"
            "Write a concise 4-bullet forensic risk assessment citing only the facts above."
        )
        resp = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=260,
            temperature=0.1,
        )
        return resp.choices[0].message.content or ""
    except Exception:
        return (
            f"Deterministic Forensic Audit completed for {symbol}: "
            f"{len(findings)} citation(s) extracted."
        )
