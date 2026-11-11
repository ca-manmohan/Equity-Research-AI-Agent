"""Stage 0 Investor Mandate & Deterministic 6-Layer Quantitative Scoring Engine."""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

from kdb_engine import KDBXEngine

ARCHETYPE_WEIGHTS: Dict[str, Dict[str, float]] = {
    "balanced_institutional": {
        "layer1": 20.0,
        "layer2": 25.0,
        "layer3": 20.0,
        "layer4": 15.0,
        "layer5": 10.0,
        "layer6": 10.0,
    },
    "compounder_growth": {
        "layer1": 20.0,
        "layer2": 30.0,
        "layer3": 18.0,
        "layer4": 15.0,
        "layer5": 7.0,
        "layer6": 10.0,
    },
    "deep_value": {
        "layer1": 20.0,
        "layer2": 18.0,
        "layer3": 28.0,
        "layer4": 14.0,
        "layer5": 10.0,
        "layer6": 10.0,
    },
    "policy_capex": {
        "layer1": 18.0,
        "layer2": 23.0,
        "layer3": 17.0,
        "layer4": 14.0,
        "layer5": 18.0,
        "layer6": 10.0,
    },
    "conservative_income": {
        "layer1": 25.0,
        "layer2": 20.0,
        "layer3": 20.0,
        "layer4": 18.0,
        "layer5": 7.0,
        "layer6": 10.0,
    },
    "multibagger_hunter": {
        "layer1": 20.0,
        "layer2": 28.0,
        "layer3": 20.0,
        "layer4": 14.0,
        "layer5": 10.0,
        "layer6": 8.0,
    },
}


def recommend_archetype_from_goals(
    target_multiple: str = "3x_5x",
    drawdown_tolerance: str = "moderate_30pct",
    horizon_years: int = 5,
) -> Tuple[str, str]:
    """Map an investor's financial goals to the best-fit strategy archetype and cap focus."""
    if target_multiple == "5x_10x_plus" and drawdown_tolerance in ("moderate_30pct", "high_45pct") and horizon_years >= 5:
        return "multibagger_hunter", "small_mid"
    if drawdown_tolerance == "low_15pct" or target_multiple == "2x_3x":
        return "conservative_income", "large"
    if target_multiple == "3x_5x" and drawdown_tolerance == "high_45pct":
        return "compounder_growth", "small_mid"
    return "balanced_institutional", "all"


@dataclass
class InvestorProfile:
    """Stage 0 Investor Goals, Interests & Mandate Profile."""

    market: str = "IN"
    sectors: List[str] = field(default_factory=lambda: ["ALL"])
    archetype: str = "balanced_institutional"
    target_multiple: str = "3x_5x"  # 2x_3x | 3x_5x | 5x_10x_plus
    drawdown_tolerance: str = "moderate_30pct"  # low_15pct | moderate_30pct | high_45pct
    cap_focus: str = "all"  # all | small_mid | large
    horizon_years: int = 5
    exclude_high_debt: bool = True
    exclude_negative_cfo: bool = True
    min_adtv_usd_m: float = 0.25
    custom_tickers: List[str] = field(default_factory=list)

    def weights(self) -> Dict[str, float]:
        return ARCHETYPE_WEIGHTS.get(
            self.archetype, ARCHETYPE_WEIGHTS["balanced_institutional"]
        )


def _get_series(df: pd.DataFrame, candidates: List[str]) -> pd.Series:
    """Extract first matching metric row sorted oldest -> newest."""
    if df is None or df.empty:
        return pd.Series(dtype=float)
    index_lower = {str(idx).strip().lower(): idx for idx in df.index}
    for cand in candidates:
        key = cand.strip().lower()
        if key in index_lower:
            row = pd.to_numeric(df.loc[index_lower[key]], errors="coerce")
            # Sort columns chronologically (oldest first)
            try:
                row = row.reindex(sorted(row.index, key=lambda x: str(x)))
            except Exception:
                pass
            return row.dropna()
    return pd.Series(dtype=float)


def _latest(s: pd.Series, default: float = np.nan) -> float:
    return float(s.iloc[-1]) if len(s) >= 1 else default


def _safe_div(a: float, b: float, default: float = np.nan) -> float:
    if pd.isna(a) or pd.isna(b) or abs(b) < 1e-12:
        return default
    return float(a / b)


def _cagr(s: pd.Series) -> float:
    if len(s) < 2:
        return np.nan
    start, end = float(s.iloc[0]), float(s.iloc[-1])
    periods = len(s) - 1
    if start <= 0 or end <= 0 or periods <= 0:
        return np.nan
    return float((end / start) ** (1.0 / periods) - 1.0)


def solve_reverse_dcf_growth(
    ev: float,
    base_fcf: float,
    wacc: float = 0.11,
    years: int = 7,
    terminal_g: float = 0.035,
) -> Optional[float]:
    """Solve for the 7-year FCF CAGR implied by current Enterprise Value via bisection."""
    if pd.isna(ev) or pd.isna(base_fcf) or ev <= 0 or base_fcf <= 0:
        return None
    if wacc <= terminal_g + 0.01:
        wacc = terminal_g + 0.03

    def dcf_value(g: float) -> float:
        pv = 0.0
        fcf_t = base_fcf
        for t in range(1, years + 1):
            fcf_t *= 1.0 + g
            pv += fcf_t / ((1.0 + wacc) ** t)
        tv = (fcf_t * (1.0 + terminal_g)) / (wacc - terminal_g)
        pv += tv / ((1.0 + wacc) ** years)
        return pv

    lo, hi = -0.20, 0.65
    for _ in range(50):
        mid = 0.5 * (lo + hi)
        if dcf_value(mid) < ev:
            lo = mid
        else:
            hi = mid
    return float(0.5 * (lo + hi))


def _clamp(val: float, lo: float = 0.0, hi: float = 100.0) -> float:
    if pd.isna(val) or math.isnan(val):
        return 0.0
    return float(max(lo, min(hi, val)))


def extract_stock_metrics(bundle: Dict[str, Any]) -> Dict[str, Any]:
    """Compute raw deterministic financial metrics for Layers 1, 2, 3, and 6."""
    sym = bundle["symbol"]
    info = bundle.get("info") or {}
    inc = bundle.get("income_stmt")
    bal = bundle.get("balance_sheet")
    cf = bundle.get("cashflow")
    hist = bundle.get("history")

    sector = str(info.get("sector") or "Unknown")
    industry = str(info.get("industry") or "Unknown")
    name = str(info.get("shortName") or info.get("longName") or sym)
    currency = str(info.get("currency") or "")
    is_financial = "financial" in sector.lower() or "bank" in industry.lower()

    mcap = float(info.get("marketCap") or np.nan)
    ev = float(info.get("enterpriseValue") or np.nan)
    price = float(info.get("currentPrice") or info.get("regularMarketPrice") or np.nan)
    inst_hold = float(info.get("heldPercentInstitutions") or np.nan)
    insider_hold = float(info.get("heldPercentInsiders") or np.nan)
    beta_raw = info.get("beta")
    beta = float(beta_raw) if (beta_raw is not None and not pd.isna(beta_raw) and float(beta_raw) > 0) else 1.0

    # Liquidity (Average Daily Traded Value)
    adtv_local = np.nan
    if hist is not None and not hist.empty and "Close" in hist.columns and "Volume" in hist.columns:
        tail = hist.tail(30)
        adtv_local = float((pd.to_numeric(tail["Close"], errors="coerce") * pd.to_numeric(tail["Volume"], errors="coerce")).mean())
    elif not pd.isna(price) and info.get("averageVolume"):
        adtv_local = float(price * float(info["averageVolume"]))

    # Approximate USD equivalent for cross-market ADTV filter
    fx_to_usd = 1.0
    if currency == "INR":
        fx_to_usd = 1.0 / 84.0
    elif currency == "CAD":
        fx_to_usd = 1.0 / 1.38
    adtv_usd_m = (adtv_local * fx_to_usd) / 1e6 if not pd.isna(adtv_local) else np.nan
    mcap_usd_b = (mcap * fx_to_usd) / 1e9 if not pd.isna(mcap) else np.nan

    # Statements
    rev = _get_series(inc, ["Total Revenue", "Operating Revenue"])
    ebit = _get_series(inc, ["EBIT", "Operating Income"])
    ebitda = _get_series(inc, ["EBITDA", "Normalized EBITDA"])
    pat = _get_series(inc, ["Net Income", "Net Income Common Stockholders"])
    int_exp = _get_series(inc, ["Interest Expense", "Interest Expense Non Operating"]).abs()
    tax = _get_series(inc, ["Tax Provision"])
    pretax = _get_series(inc, ["Pretax Income"])
    rnd = _get_series(inc, ["Research And Development"])
    sga = _get_series(inc, ["Selling General And Administration"])

    tot_assets = _get_series(bal, ["Total Assets"])
    tot_debt = _get_series(bal, ["Total Debt"])
    cur_debt = _get_series(bal, ["Current Debt", "Current Debt And Capital Lease Obligation"])
    cash = _get_series(bal, ["Cash And Cash Equivalents", "Cash Cash Equivalents And Short Term Investments"])
    equity = _get_series(bal, ["Stockholders Equity", "Common Stock Equity", "Total Equity Gross Minority Interest"])
    inv_cap_reported = _get_series(bal, ["Invested Capital"])
    ar = _get_series(bal, ["Accounts Receivable", "Receivables"])
    inv = _get_series(bal, ["Inventory"])
    ap = _get_series(bal, ["Accounts Payable", "Payables"])

    cfo = _get_series(cf, ["Operating Cash Flow", "Cash Flow From Continuing Operating Activities"])
    capex = _get_series(cf, ["Capital Expenditure"]).abs()
    fcf_series = _get_series(cf, ["Free Cash Flow"])
    dividends = _get_series(cf, ["Cash Dividends Paid", "Common Stock Dividend Paid"]).abs()
    buybacks = _get_series(cf, ["Repurchase Of Capital Stock", "Common Stock Payments"]).abs()
    issuance = _get_series(cf, ["Issuance Of Capital Stock"]).abs()

    has_bal = bal is not None and not bal.empty
    has_inc = inc is not None and not inc.empty
    has_cf = cf is not None and not cf.empty

    # Layer 1: Cash-based profitability & Debt/Loan checks (strictly from reported balance sheet)
    rev_latest = _latest(rev)
    ebit_latest = _latest(ebit)
    ebitda_latest = _latest(ebitda)
    pat_latest = _latest(pat)
    assets_latest = _latest(tot_assets)
    debt_latest = _latest(tot_debt, 0.0) if has_bal else np.nan
    cur_debt_latest = _latest(cur_debt, 0.0) if has_bal else np.nan
    cash_latest = _latest(cash, 0.0) if has_bal else np.nan
    equity_latest = _latest(equity)
    net_debt = (debt_latest - cash_latest) if (has_bal and not pd.isna(debt_latest) and not pd.isna(cash_latest)) else np.nan

    # Working capital accrual delta (Ball et al. 2016)
    d_ar = float(ar.iloc[-1] - ar.iloc[-2]) if len(ar) >= 2 else 0.0
    d_inv = float(inv.iloc[-1] - inv.iloc[-2]) if len(inv) >= 2 else 0.0
    d_ap = float(ap.iloc[-1] - ap.iloc[-2]) if len(ap) >= 2 else 0.0
    wc_accrual = d_ar + d_inv - d_ap
    cash_op_prof = _safe_div(ebit_latest - wc_accrual, assets_latest)

    # Multi-year CFO/EBITDA and FCF/PAT
    cfo_sum = float(cfo.sum()) if len(cfo) else np.nan
    ebitda_sum = float(ebitda.sum()) if len(ebitda) else np.nan
    pat_sum = float(pat.sum()) if len(pat) else np.nan
    cfo_to_ebitda = _safe_div(cfo_sum, ebitda_sum)

    if len(fcf_series):
        fcf_latest = _latest(fcf_series)
        fcf_sum = float(fcf_series.sum())
    elif len(cfo) and len(capex):
        fcf_latest = _latest(cfo) - _latest(capex, 0.0)
        fcf_sum = float(cfo.sum() - capex.sum())
    else:
        fcf_latest = np.nan
        fcf_sum = np.nan

    fcf_to_pat = _safe_div(fcf_sum, pat_sum)
    net_debt_to_ebitda = _safe_div(net_debt, ebitda_latest) if (not is_financial and not pd.isna(net_debt)) else np.nan
    int_coverage = _safe_div(ebit_latest, _latest(int_exp)) if not is_financial else np.nan
    st_debt_share = (
        (_safe_div(cur_debt_latest, debt_latest, 0.0) if debt_latest > 0 else 0.0)
        if has_bal and not pd.isna(debt_latest)
        else np.nan
    )
    dso = _safe_div(_latest(ar), rev_latest) * 365.0 if not pd.isna(_latest(ar)) else np.nan

    # Layer 2: Intangible Capital, ROIC & WACC
    eff_tax = _clamp(_safe_div(_latest(tax), _latest(pretax), 0.25), 0.10, 0.35)
    nopat_latest = ebit_latest * (1.0 - eff_tax) if not pd.isna(ebit_latest) else pat_latest

    # Intangible capitalization proxy: capitalized 3-yr R&D + 30% SG&A where available
    rnd_cap = float(rnd.tail(3).sum()) * 0.7 if len(rnd) else 0.0
    sga_cap = float(sga.tail(3).sum()) * 0.15 if len(sga) else 0.0
    intangibles_proxy = rnd_cap + sga_cap

    if len(inv_cap_reported):
        ic_latest = _latest(inv_cap_reported)
        ic_earliest = float(inv_cap_reported.iloc[0])
    else:
        ic_latest = (equity_latest + net_debt) if not pd.isna(equity_latest) else np.nan
        ic_earliest = float(equity.iloc[0] + (tot_debt.iloc[0] if len(tot_debt) else 0) - (cash.iloc[0] if len(cash) else 0)) if len(equity) else np.nan

    adj_ic_latest = (ic_latest + intangibles_proxy) if not pd.isna(ic_latest) else np.nan
    roic = _safe_div(nopat_latest, ic_latest)
    if is_financial:
        roic = float(info.get("returnOnEquity") or _safe_div(pat_latest, equity_latest))

    # Incremental ROIC over multi-year window
    if len(ebit) >= 2 and not pd.isna(ic_latest) and not pd.isna(ic_earliest):
        nopat_earliest = float(ebit.iloc[0]) * (1.0 - eff_tax)
        d_nopat = nopat_latest - nopat_earliest
        d_ic = ic_latest - ic_earliest
        inc_roic = _safe_div(d_nopat, d_ic) if d_ic > 0 else (roic if d_nopat > 0 else -0.1)
    else:
        inc_roic = roic

    # Risk-free & WACC approximation by market currency
    rf = 0.068 if currency == "INR" else (0.036 if currency == "CAD" else 0.042)
    wacc = rf + min(max(beta, 0.7), 1.6) * 0.055
    roic_wacc_spread = (roic - wacc) if not pd.isna(roic) else np.nan

    rev_cagr = _cagr(rev)
    pat_cagr = _cagr(pat)

    # Reinvestment & Shareholder Yield
    capex_latest = _latest(capex, 0.0)
    reinvest_rate = _safe_div(capex_latest + _latest(rnd, 0.0), nopat_latest) if not pd.isna(nopat_latest) else np.nan
    net_buyback = _latest(buybacks, 0.0) - _latest(issuance, 0.0)
    sh_yield = _safe_div(_latest(dividends, 0.0) + net_buyback, mcap, 0.0)

    # Layer 3: Valuation & Reverse DCF
    if pd.isna(ev) and not pd.isna(mcap):
        ev = mcap + net_debt
    ev_to_nopat = _safe_div(ev, nopat_latest)
    fcf_yield = _safe_div(fcf_latest, mcap)
    adj_pb = _safe_div(mcap, (equity_latest + intangibles_proxy)) if not pd.isna(equity_latest) else np.nan
    implied_fcf_g = solve_reverse_dcf_growth(ev=ev, base_fcf=fcf_latest, wacc=wacc)

    # Operating Margin & Expansion
    op_margin = _safe_div(ebit_latest, rev_latest)
    op_margin_prev = _safe_div(float(ebit.iloc[0]), float(rev.iloc[0])) if len(ebit) >= 2 and len(rev) >= 2 else op_margin
    margin_expansion = (op_margin - op_margin_prev) if not pd.isna(op_margin) and not pd.isna(op_margin_prev) else 0.0

    # Layer 6: Survival cash runway (strictly from balance sheet when available)
    if not has_bal:
        cash_to_st_debt = np.nan
    elif not pd.isna(cur_debt_latest) and cur_debt_latest > 0:
        cash_to_st_debt = _safe_div(cash_latest, cur_debt_latest)
    else:
        cash_to_st_debt = 5.0 if not pd.isna(cash_latest) else np.nan

    return {
        "symbol": sym,
        "name": name,
        "sector": sector,
        "industry": industry,
        "currency": currency,
        "is_financial": is_financial,
        "source": bundle.get("source", ""),
        "error": bundle.get("error"),
        "price": price,
        "market_cap": mcap,
        "mcap_usd_b": mcap_usd_b,
        "ev": ev,
        "adtv_usd_m": adtv_usd_m,
        "inst_hold": inst_hold,
        "insider_hold": insider_hold,
        # Layer 1
        "cash_op_prof": cash_op_prof,
        "cfo_to_ebitda": cfo_to_ebitda,
        "fcf_to_pat": fcf_to_pat,
        "net_debt_to_ebitda": net_debt_to_ebitda,
        "int_coverage": int_coverage,
        "st_debt_share": st_debt_share,
        "dso_days": dso,
        # Layer 2
        "roic": roic,
        "inc_roic": inc_roic,
        "wacc": wacc,
        "roic_wacc_spread": roic_wacc_spread,
        "rev_cagr": rev_cagr,
        "pat_cagr": pat_cagr,
        "reinvest_rate": reinvest_rate,
        "sh_yield": sh_yield,
        "intangibles_proxy": intangibles_proxy,
        # Layer 3
        "ev_to_nopat": ev_to_nopat,
        "fcf_yield": fcf_yield,
        "adj_pb": adj_pb,
        "implied_fcf_g": implied_fcf_g,
        "op_margin": op_margin,
        "margin_expansion": margin_expansion,
        # Layer 6
        "cash_to_st_debt": cash_to_st_debt,
    }


def _score_band(val: float, low: float, high: float, invert: bool = False) -> float:
    """Linearly map a metric into [0, 100] across [low, high]."""
    if pd.isna(val) or math.isnan(val):
        return 45.0
    ratio = (val - low) / (high - low) if abs(high - low) > 1e-12 else 0.5
    if invert:
        ratio = 1.0 - ratio
    return _clamp(ratio * 100.0)


def score_universe(
    bundles: List[Dict[str, Any]],
    profile: InvestorProfile,
    kdb: KDBXEngine,
    forensic_overrides: Optional[Dict[str, Dict[str, Any]]] = None,
) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    """Score a universe across Layers 1–6 using KDB-X cross-sectional ranking."""
    raw_rows = [extract_stock_metrics(b) for b in bundles]
    valid_rows = [r for r in raw_rows if not r.get("error") and not pd.isna(r.get("market_cap"))]
    if not valid_rows:
        return [], {"kdb_mode": kdb.mode_label, "ranked_rows": 0}

    df = pd.DataFrame(valid_rows)
    df = kdb.cross_sectional_rank_and_zscore(
        df,
        metric_cols=["cash_op_prof", "roic", "fcf_yield", "rev_cagr"],
        group_col="sector",
    )

    weights = profile.weights()
    overrides = forensic_overrides or {}
    scored: List[Dict[str, Any]] = []

    for _, row in df.iterrows():
        sym = row["symbol"]
        is_fin = bool(row["is_financial"])

        # --- Layer 1 (0–100 raw, scaled by layer1 weight) ---
        l1_cash_prof = float(row.get("cash_op_prof_pct", 50.0)) if not pd.isna(row.get("cash_op_prof_pct")) else 45.0
        l1_cfo = _score_band(row["cfo_to_ebitda"], 0.35, 1.05) if not is_fin else 65.0
        l1_fcf_pat = _score_band(row["fcf_to_pat"], 0.25, 1.05) if not is_fin else 65.0
        if is_fin:
            l1_debt = 70.0
        else:
            nd_eb = row["net_debt_to_ebitda"]
            nd_score = _score_band(nd_eb, 0.0, 3.2, invert=True) if not pd.isna(nd_eb) else 60.0
            ic_score = _score_band(row["int_coverage"], 2.0, 12.0) if not pd.isna(row["int_coverage"]) else 65.0
            st_pen = _score_band(row["st_debt_share"], 0.15, 0.70, invert=True)
            l1_debt = 0.45 * nd_score + 0.35 * ic_score + 0.20 * st_pen
        l1_pct = 0.35 * l1_cash_prof + 0.25 * l1_cfo + 0.20 * l1_fcf_pat + 0.20 * l1_debt

        # --- Layer 2 (0–100 raw) ---
        spread_score = _score_band(row["roic_wacc_spread"], -0.02, 0.20)
        inc_roic_score = _score_band(row["inc_roic"], 0.05, 0.30)
        growth_score = 0.55 * _score_band(row["rev_cagr"], 0.03, 0.26) + 0.45 * _score_band(row["pat_cagr"], 0.05, 0.30)
        sh_score = _score_band(row["sh_yield"], 0.0, 0.05)
        l2_pct = 0.40 * (0.55 * spread_score + 0.45 * inc_roic_score) + 0.40 * growth_score + 0.20 * sh_score

        # --- Layer 3 (0–100 raw) ---
        fcf_y_score = _score_band(row["fcf_yield"], 0.005, 0.065)
        ev_nopat_score = _score_band(row["ev_to_nopat"], 10.0, 42.0, invert=True)
        pb_int_score = _score_band(row["adj_pb"], 1.5, 12.0, invert=True)
        imp_g = row["implied_fcf_g"]
        rev_cagr_val = row["rev_cagr"]
        if imp_g is not None and not pd.isna(imp_g) and not pd.isna(rev_cagr_val):
            # Best score when fundamentals growth exceeds Reverse-DCF implied growth
            expectation_gap = rev_cagr_val - imp_g
            rdcf_score = _score_band(expectation_gap, -0.10, 0.10)
        else:
            rdcf_score = 45.0
        margin_score = _score_band(row["margin_expansion"], -0.04, 0.06)
        l3_pct = 0.30 * (0.5 * fcf_y_score + 0.5 * ev_nopat_score) + 0.20 * pb_int_score + 0.35 * rdcf_score + 0.15 * margin_score

        # --- Layer 4 & Layer 5 (Baseline proxy + Forensic Audit overrides) ---
        ov = overrides.get(sym, {})
        insider = row["insider_hold"]
        inst = row["inst_hold"]

        # Default quantitative governance & institutional runway proxy before PDF forensic audit
        l4_default = 70.0 if (not pd.isna(insider) and insider >= 0.20) else 62.0
        l4_pct = float(ov.get("layer4_score_pct", l4_default))

        # Layer 5: Institutional under-ownership runway + operating momentum
        inst_runway = _score_band(inst, 0.10, 0.70, invert=True) if not pd.isna(inst) else 60.0
        l5_default = 0.55 * inst_runway + 0.45 * growth_score
        l5_pct = float(ov.get("layer5_score_pct", l5_default))

        # --- Layer 6 (Survival & Exit Liquidity) ---
        adtv_m = row["adtv_usd_m"]
        liq_score = _score_band(adtv_m, 0.15, 5.0) if not pd.isna(adtv_m) else 50.0
        runway_score = _score_band(row["cash_to_st_debt"], 0.4, 3.0)
        l6_pct = 0.50 * liq_score + 0.50 * runway_score

        # Weighted points
        pts_l1 = l1_pct * (weights["layer1"] / 100.0)
        pts_l2 = l2_pct * (weights["layer2"] / 100.0)
        pts_l3 = l3_pct * (weights["layer3"] / 100.0)
        pts_l4 = l4_pct * (weights["layer4"] / 100.0)
        pts_l5 = l5_pct * (weights["layer5"] / 100.0)
        pts_l6 = l6_pct * (weights["layer6"] / 100.0)
        total_score = pts_l1 + pts_l2 + pts_l3 + pts_l4 + pts_l5 + pts_l6

        # Multibagger Runway & Inflection Signals
        mcap_usd_b = row["mcap_usd_b"]
        mb_signals: List[str] = []
        mb_bonus = 0.0

        if not pd.isna(mcap_usd_b):
            if 0.05 <= mcap_usd_b <= 4.0:
                mb_signals.append(f"Small/Mid-Cap 10x Runway (${mcap_usd_b:.2f}B)")
                if profile.archetype == "multibagger_hunter" or profile.cap_focus == "small_mid":
                    mb_bonus += 4.5
            elif mcap_usd_b > 20.0 and (profile.archetype == "multibagger_hunter" or profile.target_multiple == "5x_10x_plus"):
                mb_signals.append(f"Mega-Cap Size Headwind for 10x (${mcap_usd_b:.1f}B)")
                mb_bonus -= 6.0

        if not pd.isna(row["inc_roic"]) and row["inc_roic"] >= 0.20:
            mb_signals.append(f"High Incremental ROIC ({row['inc_roic']*100:.1f}%)")
            if profile.archetype == "multibagger_hunter":
                mb_bonus += 2.5

        if imp_g is not None and not pd.isna(imp_g) and not pd.isna(row["rev_cagr"]):
            if imp_g <= 0.18 and row["rev_cagr"] >= 0.14:
                mb_signals.append(f"Mispriced Runway (RevCAGR {row['rev_cagr']*100:.1f}% vs RevDCF {imp_g*100:.1f}%)")
                mb_bonus += 4.0

        if not pd.isna(inst) and inst <= 0.25:
            mb_signals.append(f"Under-Owned Institutional Discovery ({inst*100:.1f}%)")
            if profile.archetype == "multibagger_hunter":
                mb_bonus += 2.5

        if not pd.isna(row["margin_expansion"]) and row["margin_expansion"] >= 0.015:
            mb_signals.append(f"Operating Margin Inflection (+{row['margin_expansion']*100:.1f}pp)")
            mb_bonus += 2.0

        total_score = _clamp(total_score + mb_bonus, 0.0, 100.0)

        # Hard Veto & Stage 0 Exclusion Checks
        vetoes: List[str] = list(ov.get("vetoes", []))
        warnings: List[str] = list(ov.get("warnings", []))

        if not is_fin and not pd.isna(row["net_debt_to_ebitda"]) and row["net_debt_to_ebitda"] > 3.0:
            if not pd.isna(row["int_coverage"]) and row["int_coverage"] < 2.2:
                vetoes.append("HUGE BANK LOAN / REFINANCING RISK (NetDebt/EBITDA > 3x & Low Coverage)")
            else:
                warnings.append("Elevated Leverage (NetDebt/EBITDA > 3.0x)")
        if profile.exclude_high_debt and not is_fin and not pd.isna(row["net_debt_to_ebitda"]) and row["net_debt_to_ebitda"] > 2.5:
            warnings.append("Exceeds Investor Debt Threshold (>2.5x)")
        if not is_fin and not pd.isna(row["cfo_to_ebitda"]) and row["cfo_to_ebitda"] < 0.25:
            if profile.exclude_negative_cfo:
                vetoes.append("WEAK CASH CONVERSION (CFO/EBITDA < 0.25)")
            else:
                warnings.append("Low Cash Conversion")
        if not pd.isna(adtv_m) and adtv_m < profile.min_adtv_usd_m:
            warnings.append(f"Low Exit Liquidity (${adtv_m:.2f}M/day)")

        if vetoes:
            verdict = "HARD VETO"
        elif total_score >= 75.0:
            verdict = "HIGH CONVICTION"
        elif total_score >= 62.0:
            verdict = "WATCHLIST"
        else:
            verdict = "PASS / WEAK"

        scored.append(
            {
                "symbol": sym,
                "name": row["name"],
                "sector": row["sector"],
                "industry": row["industry"],
                "currency": row["currency"],
                "is_financial": is_fin,
                "source": row["source"],
                "price": None if pd.isna(row["price"]) else round(float(row["price"]), 2),
                "market_cap_b": round(float(row["market_cap"]) / 1e9, 2),
                "mcap_usd_b": None if pd.isna(mcap_usd_b) else round(float(mcap_usd_b), 2),
                "adtv_usd_m": None if pd.isna(adtv_m) else round(float(adtv_m), 2),
                "total_score": round(total_score, 1),
                "verdict": verdict,
                "vetoes": vetoes,
                "warnings": warnings,
                "multibagger_signals": mb_signals,
                "layer_points": {
                    "layer1": round(pts_l1, 1),
                    "layer2": round(pts_l2, 1),
                    "layer3": round(pts_l3, 1),
                    "layer4": round(pts_l4, 1),
                    "layer5": round(pts_l5, 1),
                    "layer6": round(pts_l6, 1),
                },
                "metrics": {
                    "roic_pct": None if pd.isna(row["roic"]) else round(float(row["roic"]) * 100, 1),
                    "inc_roic_pct": None if pd.isna(row["inc_roic"]) else round(float(row["inc_roic"]) * 100, 1),
                    "roic_wacc_spread_pct": None if pd.isna(row["roic_wacc_spread"]) else round(float(row["roic_wacc_spread"]) * 100, 1),
                    "rev_cagr_pct": None if pd.isna(row["rev_cagr"]) else round(float(row["rev_cagr"]) * 100, 1),
                    "pat_cagr_pct": None if pd.isna(row["pat_cagr"]) else round(float(row["pat_cagr"]) * 100, 1),
                    "cfo_to_ebitda": None if pd.isna(row["cfo_to_ebitda"]) else round(float(row["cfo_to_ebitda"]), 2),
                    "fcf_yield_pct": None if pd.isna(row["fcf_yield"]) else round(float(row["fcf_yield"]) * 100, 2),
                    "ev_to_nopat": None if pd.isna(row["ev_to_nopat"]) else round(float(row["ev_to_nopat"]), 1),
                    "net_debt_to_ebitda": None if pd.isna(row["net_debt_to_ebitda"]) else round(float(row["net_debt_to_ebitda"]), 2),
                    "int_coverage": None if pd.isna(row["int_coverage"]) else round(float(row["int_coverage"]), 1),
                    "st_debt_share_pct": None if pd.isna(row["st_debt_share"]) else round(float(row["st_debt_share"]) * 100, 1),
                    "implied_fcf_g_pct": None if imp_g is None else round(float(imp_g) * 100, 1),
                    "inst_hold_pct": None if pd.isna(inst) else round(float(inst) * 100, 1),
                    "insider_hold_pct": None if pd.isna(insider) else round(float(insider) * 100, 1),
                },
                "forensic_audit": ov.get("audit_summary"),
            }
        )

    scored.sort(key=lambda x: (0 if x["verdict"] != "HARD VETO" else 1, -x["total_score"]))

    # Save ranked table snapshot in KDB-X
    flat_records = [
        {
            "symbol": s["symbol"],
            "sector": s["sector"],
            "total_score": s["total_score"],
            "verdict": s["verdict"],
            "roic_pct": s["metrics"]["roic_pct"] or 0.0,
            "implied_fcf_g_pct": s["metrics"]["implied_fcf_g_pct"] or 0.0,
        }
        for s in scored
    ]
    snap_info = kdb.persist_universe_snapshot(f"ranked_{profile.market.lower()}", flat_records)
    return scored, snap_info
