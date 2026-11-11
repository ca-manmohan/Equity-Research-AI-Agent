"""Free Indian Market & Fundamental Data Connectors (Zero Paid APIs).

Connectors:
1. Screener.in Public Company Summary Parser (respectful public HTML fetch).
2. Screener.in Exported Excel (.xlsx) 10-Year Financial Statement Reader.
3. Quarterly Earnings & Variance Analyzer via yfinance (.NS / .BO) + KDB-X cache.
"""

from __future__ import annotations

import datetime as dt
import re
import xml.etree.ElementTree as ET
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, List, Optional

import pandas as pd
import requests
import yfinance as yf
from bs4 import BeautifulSoup


def clean_nse_symbol(symbol: str) -> str:
    """Strip .NS / .BO suffix to get the base NSE/BSE ticker for Screener.in."""
    return re.sub(r"\.(NS|BO)$", "", symbol.strip().upper())


def _parse_num_cell(raw: str) -> Optional[float]:
    cleaned = re.sub(r"[,%\s]", "", raw or "")
    try:
        return float(cleaned)
    except ValueError:
        return None


def _parse_screener_table(soup: BeautifulSoup, selector: str) -> Dict[str, Any]:
    """Parse a Screener.in financial/shareholding HTML table into headers & row series."""
    table = soup.select_one(selector)
    if not table:
        return {"periods": [], "series": {}}
    headers = [re.sub(r"\s+", " ", th.get_text(" ", strip=True)) for th in table.select("thead th")]
    periods = [h for h in headers[1:] if h]
    series: Dict[str, List[Optional[float]]] = {}
    for tr in table.select("tbody tr"):
        cells = [re.sub(r"\s+", " ", td.get_text(" ", strip=True)) for td in tr.select("td")]
        if len(cells) < 2:
            continue
        label = re.sub(r"\s*\+\s*$", "", cells[0]).strip()
        vals = [_parse_num_cell(c) for c in cells[1 : 1 + len(periods)]]
        if label:
            series[label] = vals
    return {"periods": periods, "series": series}


def _parse_screener_shareholding(soup: BeautifulSoup) -> Dict[str, Any]:
    """Parse Screener.in #shareholding quarterly table into clean percentages & QoQ deltas."""
    parsed = _parse_screener_table(soup, "#shareholding table")
    quarters = parsed["periods"]
    series = parsed["series"]
    if not quarters:
        return {"quarters": [], "series": {}, "latest": {}, "qoq_change_pp": {}}

    latest: Dict[str, Any] = {"quarter": quarters[-1]}
    qoq_change_pp: Dict[str, Optional[float]] = {}
    for key in ("Promoters", "FIIs", "DIIs", "Government", "Public", "No. of Shareholders"):
        vals = series.get(key, [])
        if vals and vals[-1] is not None:
            latest[key] = vals[-1]
            if len(vals) >= 2 and vals[-2] is not None:
                qoq_change_pp[key] = round(vals[-1] - vals[-2], 2)
            else:
                qoq_change_pp[key] = None
    return {
        "quarters": quarters,
        "series": series,
        "latest": latest,
        "qoq_change_pp": qoq_change_pp,
    }


def _parse_screener_working_capital(soup: BeautifulSoup) -> Dict[str, Any]:
    """Extract Debtor Days, Inventory Days, Payable Days, Cash Conversion Cycle & ROCE trend."""
    parsed = _parse_screener_table(soup, "#ratios table")
    periods = parsed["periods"][-5:]
    series = {k: v[-5:] for k, v in parsed["series"].items()}
    latest: Dict[str, Any] = {"period": periods[-1] if periods else None}
    for key in ("Debtor Days", "Inventory Days", "Days Payable", "Cash Conversion Cycle", "Working Capital Days", "ROCE %"):
        vals = series.get(key, [])
        if vals and vals[-1] is not None:
            latest[key] = vals[-1]
    return {"periods": periods, "series": series, "latest": latest}


def fetch_nse_official_filings(symbol: str, timeout: int = 6) -> Dict[str, Any]:
    """Best-effort fetch of official NSE corporate announcements & insider (PIT) filings."""
    sym = symbol.strip().upper()
    if not sym.endswith(".NS"):
        return {"status": "skipped", "announcements": [], "insider_pit": []}
    base = clean_nse_symbol(sym)
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
        "Accept": "application/json, text/plain, */*",
        "Referer": f"https://www.nseindia.com/get-quotes/equity?symbol={base}",
    }
    announcements: List[Dict[str, str]] = []
    insider_pit: List[Dict[str, str]] = []
    try:
        sess = requests.Session()
        sess.get("https://www.nseindia.com", headers=headers, timeout=timeout)
        r_ann = sess.get(
            f"https://www.nseindia.com/api/corporate-announcements?index=equities&symbol={base}",
            headers=headers,
            timeout=timeout,
        )
        if r_ann.status_code == 200 and isinstance(r_ann.json(), list):
            for row in r_ann.json()[:6]:
                announcements.append(
                    {
                        "date": str(row.get("an_dt") or "")[:11],
                        "category": str(row.get("desc") or "Exchange Filing")[:42],
                        "title": re.sub(r"\s+", " ", str(row.get("attchmntText") or row.get("desc") or "")).strip()[:160],
                        "source": "NSE Official Filing",
                        "link": str(row.get("attchmntFile") or ""),
                    }
                )
        r_pit = sess.get(
            f"https://www.nseindia.com/api/corporates-pit?index=equities&symbol={base}",
            headers=headers,
            timeout=timeout,
        )
        if r_pit.status_code == 200 and isinstance(r_pit.json(), dict):
            for row in (r_pit.json().get("data") or [])[:5]:
                insider_pit.append(
                    {
                        "date": str(row.get("date") or row.get("acqFromDt") or "")[:12],
                        "insider": str(row.get("acqName") or "Promoter / Insider")[:42],
                        "position": str(row.get("personCategory") or "")[:28],
                        "shares": _parse_num_cell(str(row.get("secAcq") or "")),
                        "transaction": f"{row.get('tdpTransactionType', 'Trade')} ({row.get('secType', 'Equity')})",
                    }
                )
    except Exception:
        pass
    return {
        "status": "ok" if (announcements or insider_pit) else "unavailable",
        "announcements": announcements,
        "insider_pit": insider_pit,
    }


def fetch_screener_public_snapshot(symbol: str, timeout: int = 10) -> Dict[str, Any]:
    """Fetch public top-level ratios, pros/cons, shareholding & working-capital cycles from Screener.in."""
    base = clean_nse_symbol(symbol)
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
    }
    for suffix in ("consolidated/", ""):
        url = f"https://www.screener.in/company/{base}/{suffix}"
        try:
            resp = requests.get(url, headers=headers, timeout=timeout)
            if resp.status_code != 200:
                continue
            soup = BeautifulSoup(resp.text, "lxml")
            ratios: Dict[str, str] = {}
            for li in soup.select("#top-ratios li"):
                name_el = li.select_one(".name")
                val_el = li.select_one(".number") or li.select_one(".value")
                if name_el and val_el:
                    k = re.sub(r"\s+", " ", name_el.get_text(strip=True))
                    v = re.sub(r"\s+", " ", val_el.get_text(strip=True))
                    ratios[k] = v

            pros = [li.get_text(" ", strip=True) for li in soup.select(".pros ul li")]
            cons = [li.get_text(" ", strip=True) for li in soup.select(".cons ul li")]
            shareholding = _parse_screener_shareholding(soup)
            working_capital = _parse_screener_working_capital(soup)

            if ratios or pros or cons or shareholding.get("quarters"):
                return {
                    "status": "ok",
                    "symbol": symbol,
                    "url": url,
                    "ratios": ratios,
                    "pros": pros,
                    "cons": cons,
                    "shareholding": shareholding,
                    "working_capital": working_capital,
                }
        except Exception as exc:
            last_err = str(exc)
            continue

    return {
        "status": "unavailable",
        "symbol": symbol,
        "message": "Could not fetch Screener.in public page (network/rate-limit); falling back to yfinance/KDB-X.",
    }


def parse_screener_excel(xlsx_path: str) -> Dict[str, Any]:
    """Parse a user-downloaded Screener.in 10-year Excel (.xlsx) workbook."""
    path = Path(xlsx_path)
    if not path.exists():
        return {"status": "error", "message": f"Excel file not found: {xlsx_path}"}
    try:
        xl = pd.ExcelFile(path, engine="openpyxl")
        sheets_summary: Dict[str, Any] = {}
        if "Data Sheet" in xl.sheet_names:
            df = xl.parse("Data Sheet")
            sheets_summary["data_sheet_rows"] = len(df)
            sheets_summary["columns_preview"] = [str(c) for c in df.columns[:12]]
        return {
            "status": "ok",
            "file": str(path),
            "sheets": xl.sheet_names,
            "summary": sheets_summary,
        }
    except Exception as exc:
        return {"status": "error", "message": str(exc)}


def analyze_quarterly_earnings_india(symbol: str) -> Dict[str, Any]:
    """Analyze latest quarterly YoY/QoQ revenue, EBIT margin, and PAT trends via yfinance."""
    sym = symbol.strip().upper()
    if "." not in sym:
        sym = f"{sym}.NS"
    try:
        tkr = yf.Ticker(sym)
        q_inc = tkr.quarterly_income_stmt
        if q_inc is None or q_inc.empty:
            return {"status": "unavailable", "symbol": sym, "message": "No quarterly income statement returned."}

        cols = sorted(q_inc.columns)
        q_inc = q_inc[cols]

        def row_vals(names: List[str]) -> pd.Series:
            idx_map = {str(i).strip().lower(): i for i in q_inc.index}
            for n in names:
                if n.lower() in idx_map:
                    return pd.to_numeric(q_inc.loc[idx_map[n.lower()]], errors="coerce")
            return pd.Series(dtype=float)

        rev = row_vals(["Total Revenue", "Operating Revenue"])
        ebit = row_vals(["EBIT", "Operating Income"])
        pat = row_vals(["Net Income", "Net Income Common Stockholders"])

        quarters: List[Dict[str, Any]] = []
        for c in cols[-5:]:
            r_v = float(rev.get(c, float("nan"))) if c in rev else float("nan")
            e_v = float(ebit.get(c, float("nan"))) if c in ebit else float("nan")
            p_v = float(pat.get(c, float("nan"))) if c in pat else float("nan")
            opm = (e_v / r_v * 100.0) if (pd.notna(r_v) and r_v != 0 and pd.notna(e_v)) else None
            quarters.append(
                {
                    "quarter_end": str(c)[:10],
                    "revenue_cr_approx": None if pd.isna(r_v) else round(r_v / 1e7, 2),
                    "ebit_cr_approx": None if pd.isna(e_v) else round(e_v / 1e7, 2),
                    "pat_cr_approx": None if pd.isna(p_v) else round(p_v / 1e7, 2),
                    "ebit_margin_pct": None if opm is None else round(opm, 2),
                }
            )

        yoy_rev_growth = None
        yoy_pat_growth = None
        if len(quarters) >= 5:
            q_now, q_yoy = quarters[-1], quarters[-5]
            if q_now["revenue_cr_approx"] and q_yoy["revenue_cr_approx"] and q_yoy["revenue_cr_approx"] > 0:
                yoy_rev_growth = round((q_now["revenue_cr_approx"] / q_yoy["revenue_cr_approx"] - 1.0) * 100.0, 2)
            if q_now["pat_cr_approx"] and q_yoy["pat_cr_approx"] and q_yoy["pat_cr_approx"] > 0:
                yoy_pat_growth = round((q_now["pat_cr_approx"] / q_yoy["pat_cr_approx"] - 1.0) * 100.0, 2)

        return {
            "status": "ok",
            "symbol": sym,
            "latest_quarter": quarters[-1] if quarters else None,
            "yoy_revenue_growth_pct": yoy_rev_growth,
            "yoy_pat_growth_pct": yoy_pat_growth,
            "quarterly_history": quarters,
        }
    except Exception as exc:
        return {"status": "error", "symbol": sym, "message": str(exc)}


def _parse_xbrl_segment_filing(xml_text: str) -> Dict[str, Any]:
    """Parse statutory Ind-AS 108 / Banking segment revenue, EBIT, assets & liabilities from NSE XBRL XML."""
    root = ET.fromstring(xml_text)
    ctxs: Dict[str, tuple[str, str, str, str]] = {}
    for el in root.iter():
        if el.tag.split("}")[-1] == "context":
            cid = el.attrib.get("id", "")
            start = end = inst = dim_val = ""
            for sub in el.iter():
                st = sub.tag.split("}")[-1]
                if st == "startDate":
                    start = (sub.text or "").strip()
                elif st == "endDate":
                    end = (sub.text or "").strip()
                elif st == "instant":
                    inst = (sub.text or "").strip()
                elif st in ("explicitMember", "typedMember"):
                    dim_val = (sub.text or "").strip() or "".join((c.text or "") for c in sub)
            ctxs[cid] = (start, end, inst, dim_val)

    multi_flag = ""
    by_dim: Dict[str, Dict[str, Any]] = defaultdict(dict)
    instant_vals: Dict[str, Dict[str, float]] = defaultdict(dict)
    period_label = ""
    fallback_by_dim: Dict[str, Dict[str, Any]] = defaultdict(dict)

    target_tags = {
        "DescriptionOfReportableSegment",
        "SegmentRevenue",
        "SegmentRevenueFromOperations",
        "SegmentProfitLossBeforeTaxAndFinanceCosts",
        "SegmentProfitBeforeTax",
        "SegmentAssets",
        "SegmentLiabilities",
    }

    for el in root:
        tag = el.tag.split("}")[-1]
        if tag == "IsCompanyReportingMultisegmentOrSingleSegment":
            multi_flag = (el.text or "").strip()
            continue
        if tag not in target_tags:
            continue
        cid = el.attrib.get("contextRef", "")
        if cid not in ctxs:
            continue
        start, end, inst, dim_val = ctxs[cid]
        if not dim_val:
            continue
        val_txt = (el.text or "").strip()
        if not val_txt:
            continue

        if tag == "DescriptionOfReportableSegment":
            by_dim[dim_val]["name"] = val_txt
            fallback_by_dim[dim_val]["name"] = val_txt
            continue

        num = _parse_num_cell(val_txt)
        if num is None:
            continue

        if inst and tag in ("SegmentAssets", "SegmentLiabilities"):
            instant_vals[dim_val][tag] = num
            continue

        if start and end:
            try:
                days = (dt.date.fromisoformat(end) - dt.date.fromisoformat(start)).days
            except ValueError:
                days = 90
            dest = by_dim[dim_val] if days <= 105 else fallback_by_dim[dim_val]
            if days <= 105 and not period_label:
                period_label = end
            if tag in ("SegmentRevenue", "SegmentRevenueFromOperations"):
                dest.setdefault("revenue_raw", num)
            elif tag == "SegmentProfitLossBeforeTaxAndFinanceCosts":
                dest["ebit_raw"] = num
            elif tag == "SegmentProfitBeforeTax" and "ebit_raw" not in dest:
                dest["ebit_raw"] = num

    chosen = by_dim if any("revenue_raw" in v or "ebit_raw" in v for v in by_dim.values()) else fallback_by_dim
    segments: Dict[str, Dict[str, Any]] = {}
    for dv, data in chosen.items():
        name = str(data.get("name") or dv.split(":")[-1]).strip()
        rev_raw = data.get("revenue_raw")
        ebit_raw = data.get("ebit_raw")
        if rev_raw is None and ebit_raw is None:
            continue
        assets_raw = instant_vals.get(dv, {}).get("SegmentAssets")
        liab_raw = instant_vals.get(dv, {}).get("SegmentLiabilities")
        key_norm = re.sub(r"\s+", " ", name.lower()).strip()
        segments[key_norm] = {
            "name": name,
            "revenue_cr": None if rev_raw is None else round(rev_raw / 1e7, 1),
            "ebit_cr": None if ebit_raw is None else round(ebit_raw / 1e7, 1),
            "assets_cr": None if assets_raw is None else round(assets_raw / 1e7, 1),
            "liabilities_cr": None if liab_raw is None else round(liab_raw / 1e7, 1),
        }

    return {
        "multi_flag": multi_flag,
        "period_end": period_label,
        "segments": segments,
    }


def fetch_nse_segment_results(symbol: str, timeout: int = 8) -> Dict[str, Any]:
    """Fetch official Ind-AS 108 / Banking segment breakdown (Q latest, QoQ, YoY) from NSE SEBI Integrated Filings."""
    sym = symbol.strip().upper()
    if not sym.endswith((".NS", ".BO")):
        return {"status": "skipped", "available": False, "reason": "Non-Indian ticker"}
    base = clean_nse_symbol(sym)
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
        "Accept": "application/json, text/plain, */*",
        "Referer": f"https://www.nseindia.com/get-quotes/equity?symbol={base}",
    }
    try:
        sess = requests.Session()
        sess.get("https://www.nseindia.com", headers=headers, timeout=timeout)
        r = sess.get(
            f"https://www.nseindia.com/api/integrated-filing-results?index=equities&symbol={base}",
            headers=headers,
            timeout=timeout,
        )
        if r.status_code != 200:
            return {"status": "unavailable", "available": False}
        payload = r.json()
        raw_rows = payload.get("data", payload) if isinstance(payload, dict) else payload
        if not isinstance(raw_rows, list):
            return {"status": "unavailable", "available": False}

        def _parse_qe(row: Dict[str, Any]) -> dt.date:
            s = str(row.get("qe_Date") or "").strip()
            for fmt in ("%d-%b-%Y", "%d-%m-%Y", "%Y-%m-%d"):
                try:
                    return dt.datetime.strptime(s.title(), fmt).date()
                except ValueError:
                    continue
            return dt.date.min

        cons = [
            x
            for x in raw_rows
            if (x.get("consolidated") or "").lower() == "consolidated"
            and x.get("xbrl")
            and "GOVERNANCE" not in str(x.get("xbrl", "")).upper()
        ]
        if not cons:
            cons = [
                x
                for x in raw_rows
                if (x.get("consolidated") or "").lower() == "standalone"
                and x.get("xbrl")
                and "GOVERNANCE" not in str(x.get("xbrl", "")).upper()
            ]
        if not cons:
            return {"status": "unavailable", "available": False}

        cons.sort(key=_parse_qe, reverse=True)
        latest_row = cons[0]
        latest_dt = _parse_qe(latest_row)
        prev_row = cons[1] if len(cons) > 1 else None
        yoy_row = None
        if latest_dt != dt.date.min:
            target_yoy = latest_dt.replace(year=latest_dt.year - 1)
            for cand in cons[1:]:
                cdt = _parse_qe(cand)
                if cdt != dt.date.min and abs((cdt - target_yoy).days) <= 7:
                    yoy_row = cand
                    break

        xr_latest = sess.get(latest_row["xbrl"], headers=headers, timeout=timeout)
        if xr_latest.status_code != 200:
            return {"status": "unavailable", "available": False}
        parsed_now = _parse_xbrl_segment_filing(xr_latest.text)
        segs_now = parsed_now["segments"]
        if "single" in parsed_now["multi_flag"].lower() and len(segs_now) < 2:
            return {
                "status": "single_segment",
                "available": False,
                "classification": parsed_now["multi_flag"],
                "period_end": latest_row.get("qe_Date"),
            }

        prev_segs: Dict[str, Dict[str, Any]] = {}
        if prev_row:
            try:
                xr_prev = sess.get(prev_row["xbrl"], headers=headers, timeout=timeout)
                if xr_prev.status_code == 200:
                    prev_segs = _parse_xbrl_segment_filing(xr_prev.text)["segments"]
            except Exception:
                pass

        yoy_segs: Dict[str, Dict[str, Any]] = {}
        if yoy_row:
            try:
                xr_yoy = sess.get(yoy_row["xbrl"], headers=headers, timeout=timeout)
                if xr_yoy.status_code == 200:
                    yoy_segs = _parse_xbrl_segment_filing(xr_yoy.text)["segments"]
            except Exception:
                pass

        def _is_elim(k: str) -> bool:
            return any(tok in k for tok in ("intersegment", "inter segment", "inter-segment", "elimination", "unallocated"))

        reportable_rows: List[Dict[str, Any]] = []
        elim_rows: List[Dict[str, Any]] = []
        for k, cur in segs_now.items():
            if _is_elim(k):
                elim_rows.append(cur)
                continue
            rev = cur.get("revenue_cr")
            ebit = cur.get("ebit_cr")
            assets = cur.get("assets_cr")
            liab = cur.get("liabilities_cr")
            cap_emp = round(assets - liab, 1) if (assets is not None and liab is not None and assets > liab) else None
            ann_roce = round((ebit * 4.0) / cap_emp * 100.0, 1) if (ebit is not None and cap_emp and cap_emp > 0) else None
            margin = round(ebit / rev * 100.0, 1) if (ebit is not None and rev and rev > 0) else None

            p_cur = prev_segs.get(k, {})
            y_cur = yoy_segs.get(k, {})
            prev_rev, prev_ebit = p_cur.get("revenue_cr"), p_cur.get("ebit_cr")
            yoy_rev, yoy_ebit = y_cur.get("revenue_cr"), y_cur.get("ebit_cr")
            rev_qoq = round((rev - prev_rev) / abs(prev_rev) * 100.0, 1) if (rev is not None and prev_rev and abs(prev_rev) > 0) else None
            rev_yoy = round((rev - yoy_rev) / abs(yoy_rev) * 100.0, 1) if (rev is not None and yoy_rev and abs(yoy_rev) > 0) else None
            ebit_qoq = round((ebit - prev_ebit) / abs(prev_ebit) * 100.0, 1) if (ebit is not None and prev_ebit and abs(prev_ebit) > 0) else None
            ebit_yoy = round((ebit - yoy_ebit) / abs(yoy_ebit) * 100.0, 1) if (ebit is not None and yoy_ebit and abs(yoy_ebit) > 0) else None

            reportable_rows.append(
                {
                    "name": cur["name"],
                    "revenue_cr": rev,
                    "ebit_cr": ebit,
                    "ebit_margin_pct": margin,
                    "rev_qoq_pct": rev_qoq,
                    "rev_yoy_pct": rev_yoy,
                    "ebit_qoq_pct": ebit_qoq,
                    "ebit_yoy_pct": ebit_yoy,
                    "assets_cr": assets,
                    "liabilities_cr": liab,
                    "cap_employed_cr": cap_emp,
                    "ann_roce_pct": ann_roce,
                }
            )

        if len(reportable_rows) < 2:
            return {"status": "single_segment", "available": False, "classification": parsed_now["multi_flag"]}

        reportable_rows.sort(
            key=lambda r: (1 if r["name"].lower().startswith("other") else 0, -(r["revenue_cr"] or 0.0))
        )
        tot_rev = sum(r["revenue_cr"] for r in reportable_rows if r["revenue_cr"] and r["revenue_cr"] > 0)
        tot_ebit = sum(r["ebit_cr"] for r in reportable_rows if r["ebit_cr"] and r["ebit_cr"] > 0)
        for r in reportable_rows:
            r["rev_mix_pct"] = round(r["revenue_cr"] / tot_rev * 100.0, 1) if (r["revenue_cr"] and tot_rev > 0) else None
            r["ebit_mix_pct"] = round(r["ebit_cr"] / tot_ebit * 100.0, 1) if (r["ebit_cr"] and r["ebit_cr"] > 0 and tot_ebit > 0) else None

        return {
            "status": "ok",
            "available": True,
            "period_end": parsed_now["period_end"] or str(latest_row.get("qe_Date") or ""),
            "prior_period_end": str(prev_row.get("qe_Date") or "") if prev_row else "",
            "yoy_period_end": str(yoy_row.get("qe_Date") or "") if yoy_row else "",
            "filing_basis": str(latest_row.get("consolidated") or "Consolidated"),
            "source_url": str(latest_row.get("xbrl") or ""),
            "segments": reportable_rows,
            "intersegment_count": len(elim_rows),
        }
    except Exception as exc:
        return {"status": "unavailable", "available": False, "message": str(exc)}
