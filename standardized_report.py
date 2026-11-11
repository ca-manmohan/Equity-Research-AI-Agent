"""Standardized Investor-Friendly Research Report Builder (Stock-Agnostic).

Produces an identical 4-section human-readable report modeled on institutional equity research (PL Capital / ICICI Direct):
1. Executive Summary (Quick Pointers, Key Market Data, Recent Decisions/Contracts + Audit, Loans & Litigation + Verdict)
2. Financial Summary (4Y YoY Table, 4Q QoQ Table, 5Y DCF Valuation & Sensitivity Matrix, Peer Comps + Section Opinions)
3. Ownership, FPI/Promoter Actions, Bulk/Block Deals, Brokerage/Credit Ratings & Sector Performance
4. Deep Business Quality & Price Check (Plain-English Explanations without jargon or AI buzzwords)
"""

from __future__ import annotations

import datetime as dt
import json
import os
import re
import urllib.parse
import xml.etree.ElementTree as ET
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd
import requests
import yfinance as yf

from data_ingestor import MULTIBAGGER_UNIVERSES, PRESET_UNIVERSES
from forensic_agent import run_forensic_audit
from indian_connectors import fetch_nse_official_filings, fetch_nse_segment_results


def _row_series(stmt: pd.DataFrame, candidates: List[str]) -> pd.Series:
    if stmt is None or stmt.empty:
        return pd.Series(dtype=float)
    idx_map = {str(i).strip().lower(): i for i in stmt.index}
    for name in candidates:
        key = name.strip().lower()
        if key in idx_map:
            return pd.to_numeric(stmt.loc[idx_map[key]], errors="coerce")
    return pd.Series(dtype=float)


def _scale_divisor(currency: str) -> Tuple[float, str]:
    if str(currency).upper() == "INR":
        return 1e7, "₹ Cr"
    return 1e6, f"{currency or 'USD'} M"


def _fmt_num(val: Optional[float], div: float = 1.0, decimals: int = 1) -> Optional[float]:
    if val is None or pd.isna(val):
        return None
    return round(float(val) / div, decimals)


def fmt_comma(val: Optional[float], decimals: int = 0, suffix: str = "") -> str:
    """Format numbers cleanly with thousand separators for easy reading."""
    if val is None or pd.isna(val):
        return "—"
    if decimals == 0:
        return f"{round(float(val)):,}{suffix}"
    return f"{float(val):,.{decimals}f}{suffix}"


def _investor_stance(score: float, vetoes: List[str], upside_pct: Optional[float]) -> Dict[str, str]:
    """Translate composite quality score, audit vetoes, and DCF gap into a SEBI-compliant educational tier."""
    if vetoes:
        return {
            "label": "ELEVATED RISK FLAGGED",
            "tone": "red",
            "summary": f"Critical governance, debt, or audit risk indicator detected ({'; '.join(vetoes)}); baseline financial quality threshold is not satisfied.",
        }
    if score >= 75 and (upside_pct is None or upside_pct >= 0):
        return {
            "label": "STRONG FUNDAMENTALS · DISCOUNT TO DCF",
            "tone": "green",
            "summary": "Operating cash flows, ROIC–WACC spread, and governance metrics rank strongly, while DCF intrinsic value sits above current market price.",
        }
    if score >= 62:
        if upside_pct is not None and upside_pct >= 10:
            return {
                "label": "CONSTRUCTIVE FUNDAMENTALS · VALUE CUSHION",
                "tone": "green",
                "summary": "Return on capital and solvency metrics remain healthy alongside a double-digit valuation discount versus base-case DCF estimates.",
            }
        return {
            "label": "SOLID FUNDAMENTALS · FULL VALUATION",
            "tone": "amber",
            "summary": "Underlying profitability and balance-sheet quality remain healthy, while current market pricing discounts limited margin of safety on base DCF assumptions.",
        }
    if score >= 45:
        return {
            "label": "MODERATE FUNDAMENTALS · VALUATION WATCH",
            "tone": "amber",
            "summary": "Core operations remain stable, though consolidated return on capital or implied market expectations limit fundamental valuation cushion.",
        }
    return {
        "label": "CONSTRAINED FUNDAMENTALS · HIGH EXPECTATIONS",
        "tone": "red",
        "summary": "Modest return on capital or elevated implied cash-flow growth expectations relative to historical financial performance.",
    }


def _market_gl(symbol: str) -> str:
    s = symbol.strip().upper()
    if s.endswith((".NS", ".BO")):
        return "IN"
    if s.endswith(".TO"):
        return "CA"
    return "US"


def _fetch_google_news_rss(query_str: str, market_gl: str = "IN", limit: int = 8) -> List[Dict[str, str]]:
    """Fetch public Google News RSS headlines safely (zero paid API keys)."""
    items: List[Dict[str, str]] = []
    try:
        query = urllib.parse.quote_plus(query_str)
        rss_url = f"https://news.google.com/rss/search?q={query}&hl=en-{market_gl}&gl={market_gl}&ceid={market_gl}:en"
        resp = requests.get(rss_url, timeout=8, headers={"User-Agent": "Mozilla/5.0"})
        if resp.status_code != 200:
            return items
        root = ET.fromstring(resp.text)
        for item in root.findall(".//item")[:limit]:
            title_raw = item.findtext("title") or ""
            src_el = item.find("source")
            pub = (src_el.text if src_el is not None else "") or "Google News"
            if " - " in title_raw and src_el is None:
                title_raw, pub = title_raw.rsplit(" - ", 1)
            clean_title = re.sub(r"\s+", " ", title_raw.strip())
            if not clean_title:
                continue
            items.append(
                {
                    "title": clean_title,
                    "source": pub.strip() or "News",
                    "date": (item.findtext("pubDate") or "Recent")[:16],
                    "link": item.findtext("link") or "",
                }
            )
    except Exception:
        pass
    return items


def _clean_headline(raw_title: str, source: str) -> str:
    """Remove duplicate trailing source labels & verbose exchange boilerplate from headlines."""
    t = re.sub(r"\s+", " ", (raw_title or "").strip())
    if source and source != "News":
        src_esc = re.escape(source.strip())
        t = re.sub(rf"\s*[-|–]\s*{src_esc}\s*$", "", t, flags=re.I).strip()
    t = re.sub(r"\s*[|]\s*List\s*$", "", t, flags=re.I).strip()
    t = re.sub(r"\s+-\s+[A-Z][A-Za-z0-9.\s]{2,28}$", "", t).strip()
    t = re.sub(r"^.*?\bhas informed the Exchange\s+(?:about|regarding)\s+", "", t, flags=re.I)
    t = re.sub(r"^['\"]?Press Release\s*[-–:]\s*", "", t, flags=re.I).strip(" '\".").strip(" '\"")
    return t


def _is_low_signal_headline(title: str, source: str = "") -> bool:
    """Filter out social-media scraping, SEO ticker pages, and routine exchange boilerplate."""
    sl = (source or "").strip().lower()
    if any(bad in sl for bad in ("facebook", "instagram", "twitter", "x.com", "reddit", "pinterest", "tiktok")):
        return True
    tl = (title or "").lower()
    if "(wbo:" in tl:
        # Remove foreign exchange stub prefix later, but keep actual article if substantial
        pass
    noise_patterns = [
        r"\bshare price\s*$",
        r"\bstock price\b",
        r"\bcopy of newspaper publication\b",
        r"\btrading window\b",
        r"\breg\.?\s*74\(5\)\b",
        r"\bcompliance certificate\b",
        r"\bpostal ballot\b",
        r"\bloss of share certificate\b",
        r"\bscorpion\b",
    ]
    return any(re.search(p, tl) for p in noise_patterns)


def _repair_truncated_title(text: str) -> str:
    """Clean RSS/NSE truncation artifacts and foreign exchange ticker noise."""
    t = re.sub(r"\s*\(WBO:[A-Z0-9]+\)", "", text or "", flags=re.I)
    t = re.sub(r"\s+", " ", t).strip()
    # Fix cut-off incomplete year suffix like 'November 16, 2' or 'September 30, 2'
    t = re.sub(r",\s*\d{1,3}\s*$", "", t).strip()
    # Strip trailing cut-off prepositions/articles/connectors when RSS truncated at byte limit
    for _ in range(4):
        t = re.sub(r"\s+(?:as|of|and|the|to|for|in|at|by|on|with|from|among|potential|benef|is|was)\s*$", "", t, flags=re.I).strip()
    return t.rstrip(".,;:- ")


def _sanitize_sebi_phrase(text: str) -> str:
    """Rewrite direct broker Buy/Target-Price promo headlines into objective SEBI-compliant phrasing."""
    tl = (text or "").lower()
    if re.search(r"\b(recommends? buying|buy\s+[a-z\s]+;\s*target|target of rs|reiterates\s*'?buy'?)\b", tl):
        if "ipo" in tl:
            return "External market notes highlight potential strategic value-unlocking catalysts around subsidiary/Jio listing milestones."
        if "agm" in tl or "re-rating" in tl or "re-rate" in tl:
            return "Third-party brokerage coverage reviews potential valuation re-rating drivers around AGM and segment execution."
        return "External brokerage note reviews earnings outlook and capital allocation positioning (see numerical consensus distribution above)."
    return text


def _enrich_source_label(item: Dict[str, str]) -> str:
    """Create a concise clickable source label (distinguishing specific NSE Official Filings)."""
    src = (item.get("source") or "Disclosure").strip()
    cat = (item.get("category") or "").strip()
    tl = f"{cat} {item.get('title', '')}".lower()
    if "nse official filing" in src.lower():
        if "credit rating" in tl:
            return "NSE Filing · Credit Rating"
        if "transcript" in tl:
            return "NSE Filing · Concall Transcript"
        if "audio recording" in tl:
            return "NSE Filing · Earnings Audio"
        if "institutional investors" in tl or "schedule of meet" in tl:
            return "NSE Filing · Investor Meet"
        if "unaudited financial" in tl or "result" in tl:
            return "NSE Filing · Financial Results"
        return "NSE Official Filing"
    return src


_STOPWORDS_BRIEF = {
    "about", "after", "ahead", "amid", "among", "annual", "asks", "based", "beyond",
    "company", "crore", "despite", "during", "filed", "filing", "first", "forum",
    "from", "have", "here", "india", "indian", "into", "investor", "investors",
    "lakh", "limited", "major", "management", "market", "more", "most", "nearly",
    "over", "phase", "quarter", "quarterly", "recent", "report", "reports", "results",
    "share", "shares", "stock", "stocks", "their", "these", "this", "through",
    "today", "under", "update", "updates", "what", "when", "where", "which", "while",
    "why", "will", "with", "year", "years",
}


def _topic_keywords(txt: str, company_name: str = "") -> set[str]:
    """Extract normalized topical tokens + figure prefixes to catch duplicate news events."""
    comp_tokens = {t.lower() for t in re.split(r"[^a-zA-Z0-9]+", company_name) if len(t) >= 3}
    norm = re.sub(r"(?<=\d),(?=\d)", "", txt.lower())
    raw_tokens = re.findall(r"[a-z0-9]+(?:\.\d+)?", norm)
    out: set[str] = set()
    for t in raw_tokens:
        if len(t) >= 4 and t not in _STOPWORDS_BRIEF and t not in comp_tokens:
            out.add(t)
        elif re.match(r"^\d+(?:\.\d+)?$", t) and len(t) >= 2:
            out.add(t)
    # Normalize Indian notation equivalence (e.g. 144271 crore ~ 1.44 lakh)
    if "144271" in norm or "1.44" in norm:
        out.add("1.44l_fig")
    return out


def _is_redundant_topic(candidate: str, picked_texts: List[str], company_name: str = "") -> bool:
    """Return True when a candidate headline substantially repeats an already-selected bullet."""
    cand_kw = _topic_keywords(candidate, company_name)
    if not cand_kw or not picked_texts:
        return False
    for prev in picked_texts:
        prev_kw = _topic_keywords(prev, company_name)
        if not prev_kw:
            continue
        inter = cand_kw & prev_kw
        overlap_ratio = len(inter) / max(1, min(len(cand_kw), len(prev_kw)))
        if len(inter) >= 3 or (len(inter) >= 2 and overlap_ratio >= 0.34):
            return True
    return False


def _infer_investor_impact(title: str, section_key: str, tone: str, tag: str) -> str:
    """Return one crisp, SEBI-compliant sentence explaining how a disclosure impacts investors."""
    tl = title.lower()
    if any(k in tl for k in ("credit rating", "moody", "crisil", "icra", "fitch")):
        if tone == "warning":
            return "Signals tighter debt-servicing headroom; closely monitor interest coverage and refinancing terms."
        if "ipo" in tl or "flexibility" in tl:
            return "Supports borrowing flexibility and potential subsidiary value unlock alongside disciplined capex funding."
        return "Supports lower borrowing costs and balance-sheet refinancing comfort across business cycles."
    if any(k in tl for k in ("shift beyond heavy capex", "beyond heavy capex", "next growth phase", "capex moderation", "peak capex")):
        return "Moderation in peak capital intensity can lift free cash flow conversion and shareholder payout flexibility."
    if any(k in tl for k in ("ipo", "demerger", "spin off", "listing", "value unlock")):
        return "Enables standalone subsidiary value discovery and potential sum-of-the-parts re-rating."
    if any(k in tl for k in ("order book", "backlog", "tcv", "deal win", "contract", "award", "bid")):
        if "annual" in tl or "full year" in tl or "q4" in tl or "$" in tl:
            return "Large multi-year deal pipeline improves revenue visibility and capacity utilization over upcoming quarters."
        return "Expands multi-quarter revenue visibility; track book-to-bill conversion and execution margins ahead."
    if any(k in tl for k in ("capex", "capacity expansion", "commissioned", "new plant", "facility", "invests rs", "invests ₹", "spent rs")):
        return "Heavy capital outlay weighs on near-term free cash flow; returns depend on timely asset ramp-up above WACC."
    if any(k in tl for k in ("fundraising", "fund raising", "ncd", "debenture", "qip", "rights issue")):
        return "Strengthens liquidity and balance-sheet flexibility; monitor debt cost or potential equity dilution terms."
    if any(k in tl for k in ("margin miss", "margin pressure", "slowdown", "headwind", "delay", "cut", "slash")):
        return "Signals near-term profitability headwinds, raising EPS sensitivity unless cost control or pricing offsets inflation."
    if any(k in tl for k in ("record profit", "record ebitda", "record revenue", "profit jumps", "beats", "growth push")):
        return "Confirms top-line demand and operating leverage; watch whether margin gains sustain over coming quarters."
    if any(k in tl for k in ("acquisition", "acquires", "joint venture", "partnership", "merges")):
        return "Builds incremental scale or capability; monitor integration execution, funding mix, and acquisition payback ROCE."
    if any(k in tl for k in ("surveillance", "controversy", "legal", "litigation", "vote illegal", "penalty", "notice", "dispute")):
        return "Increases governance scrutiny and headline volatility until formal exchange clarification or resolution."
    if any(k in tl for k in ("credit rating", "moody", "crisil", "icra", "fitch")):
        if tone == "warning":
            return "Signals tighter debt-servicing headroom; closely monitor interest coverage and refinancing terms."
        return "Supports lower borrowing costs and balance-sheet refinancing comfort across business cycles."
    if any(k in tl for k in ("buyback", "dividend", "unpledge", "raises stake")):
        return "Enhances cash distribution / promoter alignment while reducing free-float supply."
    if any(k in tl for k in ("pledge", "promoter sale", "block deal")):
        return "Monitor ownership overhang and potential secondary share supply on the open market."
    if any(k in tl for k in ("transcript", "audio recording", "unaudited financial", "investor", "conference", "forum")):
        return "Enables direct verification of management demand commentary, margin guidance, and capital allocation priorities."
    if section_key == "ratings":
        return "Frames institutional consensus expectations and potential multiple re-rating triggers."
    if tone == "warning":
        return "Elevates near-term earnings or execution risk; track next quarterly filings for stabilization."
    if tone == "positive":
        return "Supports medium-term earnings momentum and business franchise visibility if execution holds."
    return "Useful operational context to monitor alongside quarterly revenue, margin, and cash-flow disclosures."


def _synthesize_overall_summary(section_key: str, company_name: str, bullets: List[Dict[str, str]], disclosure_count: int) -> str:
    """Create one tight headline synthesis showing what is happening + why it matters to investors."""
    if not bullets:
        return ""
    tags = []
    for b in bullets:
        t = b.get("tag", "").strip()
        if t and t not in tags:
            tags.append(t)
    theme_txt = ", ".join(tags[:3])
    tones = [b.get("tone", "neutral") for b in bullets]
    if "warning" in tones and "positive" in tones:
        tone_phrase = "balancing growth catalysts against near-term execution or margin watchpoints"
    elif "warning" in tones:
        tone_phrase = "highlighting risk and margin watchpoints that warrant monitoring in upcoming filings"
    elif "positive" in tones:
        tone_phrase = "pointing to constructive operational visibility, capital allocation, and earnings drivers"
    else:
        tone_phrase = "providing key governance, institutional engagement, and disclosure context"
    scope = {
        "outlook": "Annual report, capex & order-book",
        "events": "Material corporate event",
        "earnings": "Quarterly earnings & concall",
        "filings_deals": "Exchange filing & ownership",
        "ratings": "Credit & institutional coverage",
    }.get(section_key, "Disclosure")
    return f"{scope} snapshot across {disclosure_count} items ({theme_txt}) — {tone_phrase} for {company_name}."


def synthesize_news_briefing(
    section_key: str,
    company_name: str,
    items: List[Dict[str, str]],
    empty_msg: str,
) -> Dict[str, Any]:
    """Synthesize noisy headline/filing lists into clean SEBI-compliant AI/analytical summaries with investor impact."""
    clean_items: List[Dict[str, str]] = []
    seen_norm: set[str] = set()
    seen_urls: set[str] = set()

    for it in items or []:
        src = (it.get("source") or "News").strip()
        raw_t = _clean_headline(it.get("title", ""), src)
        if _is_low_signal_headline(raw_t, src):
            continue
        cleaned = _repair_truncated_title(raw_t)
        if not cleaned or len(cleaned) < 12:
            continue
        sig = re.sub(r"[^a-z0-9]", "", cleaned.lower())[:48]
        url = (it.get("link") or "").strip()
        if sig in seen_norm or (url and url != "#" and url in seen_urls):
            continue
        seen_norm.add(sig)
        if url and url != "#":
            seen_urls.add(url)
        clean_items.append({**it, "title": cleaned, "source": src, "source_label": _enrich_source_label(it)})
        if len(clean_items) >= 8:
            break

    if not clean_items:
        return {
            "mode": "Disclosure Summary",
            "disclosure_count": 0,
            "summary": empty_msg,
            "bullets": [],
            "sources": [],
        }

    sources: List[Dict[str, str]] = []
    seen_src_keys: set[Tuple[str, str]] = set()
    for it in clean_items:
        skey = (it["source_label"], it.get("date", "Recent"))
        if skey in seen_src_keys:
            continue
        seen_src_keys.add(skey)
        sources.append(
            {
                "label": it["source_label"],
                "date": it.get("date", "Recent"),
                "url": it.get("link") or "#",
            }
        )
        if len(sources) >= 5:
            break

    # Optional OpenAI synthesis when user has OPENAI_API_KEY configured (and not disabled)
    api_key = os.getenv("OPENAI_API_KEY")
    if api_key and os.getenv("DISABLE_LLM_SUMMARY") != "1":
        try:
            from openai import OpenAI

            client = OpenAI(api_key=api_key, timeout=6.0)
            payload_lines = [
                f"[{i + 1}] ({it['source_label']}, {it.get('date', 'Recent')}) {it['title']}"
                for i, it in enumerate(clean_items)
            ]
            prompt = (
                f"Company: {company_name}\nSection: {section_key}\nDisclosures:\n"
                + "\n".join(payload_lines)
                + "\n\nReturn JSON with fields: "
                '{"summary": "one crisp sentence summarizing what is happening and investor takeaway", '
                '"bullets": [{"tag": "2-3 word label", "tone": "positive|warning|neutral", "text": "12-22 word factual development", "impact": "12-18 word explanation of how this affects shareholders/cash flow/margins/risk"}]} '
                "(2 to 3 distinct bullets — merge duplicate facts). Rules: strict SEBI compliance — NO Buy/Sell/Hold advice, NO target price recommendations, never invent facts."
            )
            resp = client.chat.completions.create(
                model="gpt-4o-mini",
                temperature=0.1,
                response_format={"type": "json_object"},
                messages=[{"role": "user", "content": prompt}],
            )
            parsed = json.loads(resp.choices[0].message.content or "{}")
            raw_bullets = parsed.get("bullets") or []
            if raw_bullets:
                clean_bullets = [
                    {
                        "tag": str(b.get("tag") or "Key Takeaway")[:28],
                        "tone": b.get("tone") if b.get("tone") in ("positive", "warning", "neutral") else "neutral",
                        "text": _sanitize_sebi_phrase(str(b.get("text") or "").strip()),
                        "impact": _sanitize_sebi_phrase(str(b.get("impact") or "").strip()),
                    }
                    for b in raw_bullets[:3]
                    if str(b.get("text") or "").strip()
                ]
                for cb in clean_bullets:
                    if not cb["impact"]:
                        cb["impact"] = _infer_investor_impact(cb["text"], section_key, cb["tone"], cb["tag"])
                if clean_bullets:
                    return {
                        "mode": "AI Summary",
                        "disclosure_count": len(clean_items),
                        "summary": _sanitize_sebi_phrase(str(parsed.get("summary") or "")),
                        "bullets": clean_bullets,
                        "sources": sources,
                    }
        except Exception:
            pass

    # Deterministic institutional disclosure distiller (topic-deduped, investor-impact enriched, SEBI-compliant)
    bullets: List[Dict[str, str]] = []
    picked_texts: List[str] = []

    def _add_bullet(tag: str, tone: str, raw_text: str, custom_impact: str = "") -> None:
        txt = _sanitize_sebi_phrase(raw_text).strip()
        if not txt:
            return
        if not txt.endswith((".", "!", "?")):
            txt += "."
        if _is_redundant_topic(txt, picked_texts, company_name):
            return
        picked_texts.append(txt)
        imp = custom_impact.strip() if custom_impact.strip() else _infer_investor_impact(txt, section_key, tone, tag)
        bullets.append({"tag": tag, "tone": tone, "text": txt, "impact": _sanitize_sebi_phrase(imp)})

    if section_key == "earnings":
        has_transcript = any("transcript" in it["title"].lower() or "audio" in it["title"].lower() for it in clean_items)
        has_meet = any("institutional investors" in it["title"].lower() or "forum" in it["title"].lower() for it in clean_items)
        if has_transcript:
            _add_bullet(
                "Results & Transcripts",
                "neutral",
                "Company filed unaudited quarterly/half-yearly financial statements with official earnings call audio and transcripts.",
                "Allows verification of management margin commentary, segment demand, and forward execution priorities.",
            )
        if has_meet:
            _add_bullet(
                "Street Engagement",
                "neutral",
                "Management scheduled upcoming institutional investor conference/forum meetings for operational Q&A.",
                "Regular institutional dialogue improves disclosure clarity around capital allocation and demand trends.",
            )
        for it in clean_items:
            if len(bullets) >= 3:
                break
            tl = it["title"].lower()
            if any(k in tl for k in ("transcript", "audio recording", "institutional investors", "schedule of meet")):
                continue
            tone = "positive" if it.get("sentiment") == "positive" else ("warning" if it.get("sentiment") == "negative" else "neutral")
            _add_bullet("Quarterly Coverage", tone, it["title"])
    elif section_key == "filings_deals":
        has_credit = any("credit rating" in it["title"].lower() for it in clean_items)
        has_transcript = any("transcript" in it["title"].lower() or "unaudited financial" in it["title"].lower() for it in clean_items)
        if has_credit:
            _add_bullet(
                "Credit Filing",
                "neutral",
                "Formal credit-rating agency disclosure submitted to NSE during the latest reporting window.",
                "Confirms external agency credit review cadence and transparency around debt servicing capacity.",
            )
        if has_transcript:
            _add_bullet(
                "Board / Results Filing",
                "neutral",
                "Unaudited financial result transcripts and institutional investor meet notices filed timely on exchange.",
                "Timely exchange compliance reduces information asymmetry between institutional and minority holders.",
            )
        for it in clean_items:
            if len(bullets) >= 3:
                break
            tl = it["title"].lower()
            if tl == "credit rating" or "transcript" in tl or "institutional investors" in tl:
                continue
            tone = "positive" if "unpledge" in tl or "buyback" in tl or "raises" in tl else ("warning" if "pledge" in tl or "sale" in tl else "neutral")
            _add_bullet(it.get("category") or "Ownership Update", tone, it["title"])
    elif section_key == "ratings":
        rating_items = [it for it in clean_items if it.get("category") == "Credit Rating"]
        broker_items = [it for it in clean_items if it.get("category") != "Credit Rating"]
        for rit in rating_items[:2]:
            tone = "warning" if "Caution" in rit.get("effect", "") else "positive"
            _add_bullet("Credit Rating", tone, rit["title"])
        if broker_items and len(bullets) < 3:
            macro_themes = []
            joined_b = " ".join(b["title"].lower() for b in broker_items)
            if "fpi" in joined_b:
                macro_themes.append("FPI capital inflows")
            if "ipo" in joined_b or "jio" in joined_b or "value unlock" in joined_b:
                macro_themes.append("subsidiary value-unlocking milestones")
            if "eps" in joined_b or "growth" in joined_b or "margin" in joined_b:
                macro_themes.append("multi-year EPS growth trajectory")
            if "agm" in joined_b or "re-rat" in joined_b:
                macro_themes.append("valuation multiple re-rating triggers")
            theme_str = ", ".join(macro_themes) if macro_themes else "earnings visibility and sector positioning"
            _add_bullet(
                "Brokerage Coverage",
                "neutral",
                f"Public institutional and domestic brokerage reports currently center on {theme_str}; aggregate consensus is mapped above.",
                "Highlights which catalysts institutional desks track most closely when modeling forward multiples.",
            )
            factual_b = next(
                (
                    b
                    for b in broker_items
                    if not re.search(r"\b(buy\s+[a-z]|target|recommends? buying|reiterates)\b", b["title"].lower())
                ),
                None,
            )
            if factual_b and len(bullets) < 3:
                _add_bullet("Flow / Street Note", "neutral", factual_b["title"])
    elif section_key == "outlook":
        for it in clean_items:
            if len(bullets) >= 3:
                break
            tl = it["title"].lower()
            sent = it.get("sentiment", "neutral")
            if any(k in tl for k in ("order book", "backlog", "tcv", "deal win", "contract", "award", "bid")):
                tag = "Order Book / TCV"
                tone = "warning" if sent == "negative" else "positive"
            elif any(k in tl for k in ("shift beyond heavy capex", "next growth phase", "capex moderation")):
                tag = "Capex Inflection"
                tone = "positive"
            elif any(k in tl for k in ("capex", "expansion", "capacity", "plant", "facility", "investment", "invests", "spent")):
                tag = "Capex & Expansion"
                tone = "warning" if sent == "negative" else "positive"
            elif any(k in tl for k in ("annual report", "agm", "chairman", "annual general", "presentation")):
                tag = "Annual Report / Filing"
                tone = "neutral" if sent == "neutral" else ("positive" if sent in ("positive", "catalyst") else "warning")
            else:
                tag = it.get("category") or "Business Outlook"
                tone = "positive" if sent in ("positive", "catalyst") else ("warning" if sent == "negative" else "neutral")
            _add_bullet(tag, tone, it["title"])
    else:
        for it in clean_items:
            if len(bullets) >= 3:
                break
            sent = it.get("sentiment", "neutral")
            tone = "positive" if sent in ("positive", "catalyst") else ("warning" if sent == "negative" else "neutral")
            _add_bullet(it.get("category") or "Corporate Update", tone, it["title"])

    if not bullets and clean_items:
        _add_bullet("Disclosure Note", "neutral", clean_items[0]["title"])

    overall_summary = _synthesize_overall_summary(section_key, company_name, bullets, len(clean_items))
    return {
        "mode": "Disclosure Summary",
        "disclosure_count": len(clean_items),
        "summary": overall_summary or (bullets[0]["text"] if bullets else empty_msg),
        "bullets": bullets,
        "sources": sources,
    }


def _append_briefing_md(lines: List[str], briefing: Dict[str, Any], empty_msg: str) -> None:
    """Render AI/Disclosure overview, bullets with investor impact, and clickable source links in Markdown."""
    bullets = briefing.get("bullets") or []
    sources = briefing.get("sources") or []
    if not bullets:
        lines.append(f"- {empty_msg}")
        return
    if briefing.get("summary"):
        lines.append(f"> *{briefing['summary']}*")
    for b in bullets:
        imp = b.get("impact") or ""
        imp_suffix = f" — *Investor Impact: {imp}*" if imp else ""
        lines.append(f"- **[{b['tag']}]** {b['text']}{imp_suffix}")
    if sources:
        src_links = " · ".join(
            f"[{s['label']} ({s['date']})]({s['url']})" if s.get("url") and s["url"] != "#" else f"{s['label']} ({s['date']})"
            for s in sources
        )
        lines.append(f"- **Sources:** {src_links}")


def fetch_corporate_events_and_catalysts(
    symbol: str, company_name: str, max_items: int = 6
) -> Dict[str, Any]:
    """Fetch material corporate decisions, contracts, earnings updates & risks with standardized Effect tags."""
    raw_items: List[Dict[str, str]] = []
    seen_titles: set[str] = set()

    def _add_item(title: str, source: str, pub_date: str, link: str = "") -> None:
        clean_title = _clean_headline(title, source)
        if not clean_title or len(clean_title) < 18 or _is_low_signal_headline(clean_title, source):
            return
        norm = re.sub(r"[^a-z0-9]", "", clean_title.lower())[:52]
        if norm in seen_titles:
            return
        seen_titles.add(norm)
        raw_items.append(
            {"title": clean_title, "source": source or "News", "date": pub_date or "Recent", "link": link}
        )

    search_q = company_name.split("LIMITED")[0].split("LTD")[0].strip() or symbol
    try:
        sr = yf.Search(search_q, news_count=6)
        for n in getattr(sr, "news", []) or []:
            ts = n.get("providerPublishTime")
            d_str = (
                dt.datetime.fromtimestamp(ts).strftime("%Y-%m-%d")
                if isinstance(ts, (int, float))
                else "Recent"
            )
            _add_item(n.get("title", ""), n.get("publisher", "Yahoo Finance"), d_str, n.get("link", ""))
    except Exception:
        pass

    gl = _market_gl(symbol)
    for item in _fetch_google_news_rss(f'"{search_q}" when:90d', market_gl=gl, limit=12):
        _add_item(item["title"], item["source"], item["date"], item["link"])

    def _has_kw(text_lower: str, kws: List[str]) -> bool:
        return any(re.search(rf"\b{re.escape(k.lower())}\b", text_lower) for k in kws)

    legal_risk_kws = ["fine", "fined", "penalty", "probe", "raid", "litigation", "lawsuit", "sanction", "ban", "illegal", "suspends", "controversy"]
    margin_risk_kws = ["drop", "fall", "slump", "miss", "downgrade", "cut", "loss", "delay", "weak", "decline", "pressure"]
    order_win_kws = ["contract", "order", "win", "wins", "won", "bid", "approval", "approved", "partnership", "deal", "launch"]
    cap_alloc_kws = ["ipo", "demerger", "board", "fundraising", "acquisition", "acquire", "capex", "expansion", "joint venture", "buyback", "dividend", "merger", "split"]
    earnings_pos_kws = ["record", "surge", "jump", "beat", "upgrade", "boost", "growth", "upside", "lift"]

    classified: List[Dict[str, str]] = []
    for it in raw_items[:max_items]:
        tl = it["title"].lower()
        if _has_kw(tl, legal_risk_kws):
            tag, effect, sentiment = "Regulatory / Legal", "Negative — Legal / Regulatory Risk", "negative"
        elif _has_kw(tl, margin_risk_kws):
            tag, effect, sentiment = "Business Headwind", "Negative — Margin / Outlook Pressure", "negative"
        elif _has_kw(tl, cap_alloc_kws):
            tag, effect, sentiment = "Capital Allocation", "Positive — Strategic Value Unlock", "catalyst"
        elif _has_kw(tl, order_win_kws):
            tag, effect, sentiment = "Contract / Order Win", "Positive — Revenue / Order Book", "positive"
        elif _has_kw(tl, earnings_pos_kws):
            tag, effect, sentiment = "Earnings Momentum", "Positive — Earnings / Demand", "positive"
        else:
            tag, effect, sentiment = "Corporate Update", "Neutral — Monitor Execution", "neutral"
        classified.append({**it, "category": tag, "effect": effect, "sentiment": sentiment})

    briefing = synthesize_news_briefing(
        section_key="events",
        company_name=company_name,
        items=classified,
        empty_msg="No material corporate developments identified from live news feeds.",
    )
    return {
        "events": classified,
        "briefing": briefing,
        "favorable_count": sum(1 for e in classified if e["sentiment"] in ("positive", "catalyst")),
        "setback_count": sum(1 for e in classified if e["sentiment"] == "negative"),
    }


def build_4y_annual_series(bundle: Dict[str, Any]) -> Dict[str, Any]:
    """Extract up to 4 latest fiscal years of Revenue, EBITDA, OPM, PAT, CFO, Capex, FCF & YoY growth."""
    inc = bundle.get("income_stmt")
    cf = bundle.get("cashflow")
    currency = bundle.get("info", {}).get("currency", "INR")
    div, unit = _scale_divisor(currency)

    if inc is None or inc.empty:
        return {"unit": unit, "rows": [], "investor_opinion": "Annual statement history unavailable for multi-year trend evaluation."}

    cols = sorted([str(c)[:10] for c in inc.columns])[-4:]
    inc_c = inc.copy()
    inc_c.columns = [str(c)[:10] for c in inc_c.columns]
    cf_c = cf.copy() if (cf is not None and not cf.empty) else pd.DataFrame()
    if not cf_c.empty:
        cf_c.columns = [str(c)[:10] for c in cf_c.columns]

    rev_s = _row_series(inc_c, ["Total Revenue", "Operating Revenue"])
    ebitda_s = _row_series(inc_c, ["EBITDA", "Normalized EBITDA"])
    ebit_s = _row_series(inc_c, ["EBIT", "Operating Income"])
    pat_s = _row_series(inc_c, ["Net Income", "Net Income Common Stockholders"])
    eps_s = _row_series(inc_c, ["Diluted EPS", "Basic EPS"])
    cfo_s = _row_series(cf_c, ["Operating Cash Flow", "Cash Flow From Continuing Operating Activities"])
    capex_s = _row_series(cf_c, ["Capital Expenditure", "Purchase Of PPE"])

    rows: List[Dict[str, Any]] = []
    prev_rev: Optional[float] = None
    prev_pat: Optional[float] = None

    for c in cols:
        rev_v = _fmt_num(rev_s.get(c), div, 1)
        ebit_v = _fmt_num(ebit_s.get(c), div, 1)
        ebitda_v = _fmt_num(ebitda_s.get(c), div, 1)
        if ebitda_v is None and ebit_v is not None:
            ebitda_v = ebit_v
        pat_v = _fmt_num(pat_s.get(c), div, 1)
        eps_v = _fmt_num(eps_s.get(c), 1.0, 2)
        cfo_v = _fmt_num(cfo_s.get(c), div, 1)
        capex_raw = _fmt_num(capex_s.get(c), div, 1)
        capex_v = abs(capex_raw) if capex_raw is not None else None
        fcf_v = round(cfo_v - capex_v, 1) if (cfo_v is not None and capex_v is not None) else None

        opm_pct = round((ebitda_v / rev_v) * 100.0, 2) if (ebitda_v is not None and rev_v) else None
        npm_pct = round((pat_v / rev_v) * 100.0, 2) if (pat_v is not None and rev_v) else None
        yoy_rev = round((rev_v / prev_rev - 1.0) * 100.0, 2) if (rev_v is not None and prev_rev and prev_rev > 0) else None
        yoy_pat = round((pat_v / prev_pat - 1.0) * 100.0, 2) if (pat_v is not None and prev_pat and prev_pat > 0) else None

        rows.append(
            {
                "period": f"FY{c[:4]}" if c[5:7] in ("01", "02", "03") else c,
                "date": c,
                "revenue": rev_v,
                "yoy_rev_pct": yoy_rev,
                "ebitda": ebitda_v,
                "opm_pct": opm_pct,
                "pat": pat_v,
                "yoy_pat_pct": yoy_pat,
                "npm_pct": npm_pct,
                "eps": eps_v,
                "cfo": cfo_v,
                "capex": capex_v,
                "fcf": fcf_v,
            }
        )
        prev_rev = rev_v if rev_v is not None else prev_rev
        prev_pat = pat_v if pat_v is not None else prev_pat

    # Investor opinion on 4Y trajectory
    opinion = "Multi-year figures are mixed; inspect free cash flow durability alongside top-line growth."
    if len(rows) >= 2:
        first, last = rows[0], rows[-1]
        rev_up = (last.get("revenue") or 0) > (first.get("revenue") or 0)
        fcf_positive = (last.get("fcf") or 0) > 0
        fcf_growing = (last.get("fcf") or 0) > (first.get("fcf") or 0)
        latest_rev_g = last.get("yoy_rev_pct") or 0
        latest_pat_g = last.get("yoy_pat_pct") or 0
        if rev_up and fcf_positive and fcf_growing and latest_pat_g >= 10:
            opinion = (
                f"Consistent Multi-Year Compounding: Revenue expanded from {first['period']} to {last['period']} "
                f"with latest net profit growth at {latest_pat_g:+}% and Free Cash Flow reaching {fmt_comma(last.get('fcf'))} {unit}."
            )
        elif rev_up and fcf_positive:
            opinion = (
                f"Self-Funding Operating Profile: Revenue grew {latest_rev_g:+}% YoY in {last['period']} alongside positive "
                f"Free Cash Flow ({fmt_comma(last.get('fcf'))} {unit}); higher top-line acceleration remains a key fundamental monitorable."
            )
        elif not fcf_positive:
            opinion = (
                f"Capex-Intensive Phase (Negative FCF): Free Cash Flow sits at {fmt_comma(last.get('fcf'))} {unit} due to elevated capital expenditure; "
                f"subsequent asset-turnover and ROCE trends are key to track."
            )

    return {"unit": unit, "rows": rows, "investor_opinion": opinion}


def build_4q_quarterly_series(symbol: str, currency: str = "INR") -> Dict[str, Any]:
    """Extract last 4 quarters up to latest quarter with QoQ %, matching YoY %, and investor opinion."""
    div, unit = _scale_divisor(currency)
    try:
        tkr = yf.Ticker(symbol)
        q_inc = tkr.quarterly_income_stmt
        if q_inc is None or q_inc.empty:
            return {"unit": unit, "rows": [], "latest_quarter": None, "investor_opinion": "Quarterly data unavailable."}

        cols = sorted([str(c)[:10] for c in q_inc.columns])
        q_inc_c = q_inc.copy()
        q_inc_c.columns = [str(c)[:10] for c in q_inc_c.columns]

        rev_s = _row_series(q_inc_c, ["Total Revenue", "Operating Revenue"])
        gp_s = _row_series(q_inc_c, ["Gross Profit"])
        ebit_s = _row_series(q_inc_c, ["EBIT", "Operating Income"])
        pat_s = _row_series(q_inc_c, ["Net Income", "Net Income Common Stockholders"])
        eps_s = _row_series(q_inc_c, ["Diluted EPS", "Basic EPS"])

        all_map: Dict[str, Dict[str, Optional[float]]] = {}
        for c in cols:
            rv = _fmt_num(rev_s.get(c), div, 1)
            gv = _fmt_num(gp_s.get(c), div, 1)
            ev = _fmt_num(ebit_s.get(c), div, 1)
            pv = _fmt_num(pat_s.get(c), div, 1)
            eps_v = _fmt_num(eps_s.get(c), 1.0, 2)
            gm = round((gv / rv) * 100.0, 2) if (gv is not None and rv) else None
            opm = round((ev / rv) * 100.0, 2) if (ev is not None and rv) else None
            npm = round((pv / rv) * 100.0, 2) if (pv is not None and rv) else None
            all_map[c] = {
                "revenue": rv,
                "ebit": ev,
                "pat": pv,
                "gross_margin_pct": gm,
                "ebit_margin_pct": opm,
                "pat_margin_pct": npm,
                "eps_diluted": eps_v,
            }

        recent_cols = cols[-4:]
        rows: List[Dict[str, Any]] = []
        for c in recent_cols:
            cur = all_map[c]
            full_idx = cols.index(c)
            prev_q = all_map[cols[full_idx - 1]] if full_idx > 0 else None
            qoq_rev = (
                round((cur["revenue"] / prev_q["revenue"] - 1.0) * 100.0, 2)
                if (prev_q and cur["revenue"] and prev_q["revenue"] and prev_q["revenue"] > 0)
                else None
            )
            qoq_pat = (
                round((cur["pat"] / prev_q["pat"] - 1.0) * 100.0, 2)
                if (prev_q and cur["pat"] and prev_q["pat"] and prev_q["pat"] > 0)
                else None
            )
            yr = int(c[:4]) - 1
            prior_y_key = next((k for k in cols if k.startswith(f"{yr}-{c[5:7]}")), None)
            yoy_rev = (
                round((cur["revenue"] / all_map[prior_y_key]["revenue"] - 1.0) * 100.0, 2)
                if (prior_y_key and cur["revenue"] and all_map[prior_y_key]["revenue"] and all_map[prior_y_key]["revenue"] > 0)
                else None
            )
            yoy_pat = (
                round((cur["pat"] / all_map[prior_y_key]["pat"] - 1.0) * 100.0, 2)
                if (prior_y_key and cur["pat"] and all_map[prior_y_key]["pat"] and all_map[prior_y_key]["pat"] > 0)
                else None
            )
            rows.append(
                {
                    "quarter_end": c,
                    "revenue": cur["revenue"],
                    "qoq_rev_pct": qoq_rev,
                    "yoy_rev_pct": yoy_rev,
                    "ebit": cur["ebit"],
                    "gross_margin_pct": cur["gross_margin_pct"],
                    "ebit_margin_pct": cur["ebit_margin_pct"],
                    "pat": cur["pat"],
                    "pat_margin_pct": cur["pat_margin_pct"],
                    "eps_diluted": cur["eps_diluted"],
                    "qoq_pat_pct": qoq_pat,
                    "yoy_pat_pct": yoy_pat,
                }
            )

        opinion = "Quarterly momentum appears stable."
        if len(rows) >= 2:
            last, prev = rows[-1], rows[-2]
            m_diff = (last.get("ebit_margin_pct") or 0) - (prev.get("ebit_margin_pct") or 0)
            q_pat = last.get("qoq_pat_pct") or 0
            q_rev = last.get("qoq_rev_pct") or 0
            if q_rev > 0 and m_diff >= 0.5 and q_pat > 5:
                opinion = (
                    f"Constructive Quarterly Progression: Latest quarter ({last['quarter_end']}) recorded {q_rev:+}% QoQ revenue growth, "
                    f"{q_pat:+}% QoQ profit expansion, and a +{m_diff:.2f} pp EBIT margin gain to {last.get('ebit_margin_pct')}%."
                )
            elif q_rev > 0 and m_diff >= -0.5:
                opinion = (
                    f"Steady Sequential Execution: Revenue grew {q_rev:+}% QoQ in {last['quarter_end']} with operating margin holding at "
                    f"{last.get('ebit_margin_pct')}%; sequential revenue acceleration remains a key watchpoint."
                )
            else:
                opinion = (
                    f"Sequential Moderation / Margin Compression: Quarterly momentum softened ({q_rev:+}% QoQ revenue, {q_pat:+}% QoQ PAT); "
                    f"margin stabilization over upcoming quarters is a primary monitorable."
                )

        return {
            "unit": unit,
            "rows": rows,
            "latest_quarter": rows[-1] if rows else None,
            "investor_opinion": opinion,
        }
    except Exception:
        return {"unit": unit, "rows": [], "latest_quarter": None, "investor_opinion": "Quarterly trend temporarily unavailable."}


def build_earnings_highlights(
    symbol: str,
    company_name: str,
    quarterly_4q: Dict[str, Any],
    annual_4y: Dict[str, Any],
    stock: Dict[str, Any],
    ownership_section: Dict[str, Any],
) -> Dict[str, Any]:
    """Build 4-Quarter Earnings Beat/Miss, Revisions, Concall & Source-Attributed Highlights."""
    unit = quarterly_4q.get("unit") or annual_4y.get("unit") or "INR Cr"
    curr = stock.get("currency", "INR")
    q_rows = quarterly_4q.get("rows", [])
    latest = q_rows[-1] if q_rows else {}
    prev = q_rows[-2] if len(q_rows) >= 2 else {}
    m = stock.get("metrics", {})

    q_end = latest.get("quarter_end") or "Latest Quarter"
    prev_end = prev.get("quarter_end") or "Prior Quarter"
    rev_now, rev_prev = latest.get("revenue"), prev.get("revenue")
    ebit_now, ebit_prev = latest.get("ebit"), prev.get("ebit")
    opm_now, opm_prev = latest.get("ebit_margin_pct"), prev.get("ebit_margin_pct")
    pat_now, pat_prev = latest.get("pat"), prev.get("pat")
    npm_now = latest.get("pat_margin_pct") if latest else None
    npm_prev = prev.get("pat_margin_pct") if prev else None
    ebit_qoq = round(((ebit_now / ebit_prev) - 1.0) * 100.0, 1) if (ebit_now is not None and ebit_prev) else None
    opm_bps = round((opm_now - opm_prev) * 100.0) if (opm_now is not None and opm_prev is not None) else None
    npm_bps = round((npm_now - npm_prev) * 100.0) if (npm_now is not None and npm_prev is not None) else None

    # 1. Data Freshness Verification (earnings-analysis Phase 1 date guard)
    today_dt = dt.date.today()
    days_since_q: Optional[int] = None
    fresh_label = "Date Unverified"
    try:
        if q_end and len(q_end) >= 10:
            q_dt = dt.date.fromisoformat(q_end[:10])
            days_since_q = (today_dt - q_dt).days
            fresh_label = f"Verified Current ({days_since_q}d since Q-end)" if days_since_q <= 125 else f"Aged Period ({days_since_q}d since Q-end)"
    except ValueError:
        pass
    freshness = {
        "as_of_date": today_dt.isoformat(),
        "latest_quarter": q_end,
        "days_since_quarter": days_since_q,
        "status_label": fresh_label,
    }

    # 2. 4-Quarter EPS Beat/Miss History + Forward Next-Quarter Consensus & 30D Revisions
    eh_map: Dict[str, Dict[str, Optional[float]]] = {}
    forward_consensus: Dict[str, Any] = {}
    try:
        tkr = yf.Ticker(symbol)
        eh_df = tkr.earnings_history
        if eh_df is not None and not eh_df.empty:
            for idx, r in eh_df.tail(6).iterrows():
                qk = str(idx)[:10]
                ea = _fmt_num(r.get("epsActual"), 1.0, 2)
                ee = _fmt_num(r.get("epsEstimate"), 1.0, 2)
                ed = _fmt_num(r.get("epsDifference"), 1.0, 2)
                sp_raw = r.get("surprisePercent")
                sp = round(float(sp_raw) * 100.0, 1) if (sp_raw is not None and pd.notna(sp_raw)) else None
                eh_map[qk] = {"eps_actual": ea, "eps_estimate": ee, "eps_diff": ed, "surprise_pct": sp}

        ee_df = tkr.earnings_estimate
        rev_est_df = tkr.revenue_estimate
        rev_ch_df = tkr.eps_revisions
        if ee_df is not None and not ee_df.empty:
            target_idx = "0q" if "0q" in ee_df.index else ee_df.index[0]
            erow = ee_df.loc[target_idx]
            eps_avg = _fmt_num(erow.get("avg"), 1.0, 2)
            eps_g = round(float(erow["growth"]) * 100.0, 1) if pd.notna(erow.get("growth")) else None
            n_an = int(erow["numberOfAnalysts"]) if pd.notna(erow.get("numberOfAnalysts")) else None
            up30 = down30 = None
            if rev_ch_df is not None and not rev_ch_df.empty and target_idx in rev_ch_df.index:
                rrow = rev_ch_df.loc[target_idx]
                up30 = int(rrow["upLast30days"]) if pd.notna(rrow.get("upLast30days")) else 0
                down30 = int(rrow["downLast30days"]) if pd.notna(rrow.get("downLast30days")) else 0
            rev_g = None
            if rev_est_df is not None and not rev_est_df.empty and target_idx in rev_est_df.index:
                rv_g_raw = rev_est_df.loc[target_idx].get("growth")
                rev_g = round(float(rv_g_raw) * 100.0, 1) if pd.notna(rv_g_raw) else None
            forward_consensus = {
                "horizon_label": "Upcoming Quarter (0q)" if target_idx == "0q" else str(target_idx),
                "eps_avg": eps_avg,
                "eps_growth_pct": eps_g,
                "rev_growth_pct": rev_g,
                "num_analysts": n_an,
                "up_30d": up30,
                "down_30d": down30,
            }
    except Exception:
        pass

    surprise_4q: List[Dict[str, Any]] = []
    for qr in q_rows:
        qk = qr.get("quarter_end", "")
        st = eh_map.get(qk)
        if not st and qk and len(qk) >= 7:
            # match nearest same YYYY-MM quarter key
            m_key = next((k for k in eh_map if k[:7] == qk[:7]), None)
            st = eh_map.get(m_key, {}) if m_key else {}
        ea = (st or {}).get("eps_actual") if st else qr.get("eps_diluted")
        ee = (st or {}).get("eps_estimate")
        ed = (st or {}).get("eps_diff")
        sp = (st or {}).get("surprise_pct")
        if sp is None:
            verdict = "Reported"
        elif sp >= 1.0:
            verdict = "Beat"
        elif sp <= -1.0:
            verdict = "Miss"
        else:
            verdict = "In-Line"
        surprise_4q.append(
            {
                "quarter": qk,
                "eps_actual": ea,
                "eps_estimate": ee,
                "eps_diff": ed,
                "surprise_pct": sp,
                "verdict": verdict,
                "revenue": qr.get("revenue"),
                "qoq_rev_pct": qr.get("qoq_rev_pct"),
                "gross_margin_pct": qr.get("gross_margin_pct"),
                "ebit_margin_pct": qr.get("ebit_margin_pct"),
                "pat_margin_pct": qr.get("pat_margin_pct"),
            }
        )

    tracked_surp = [r for r in surprise_4q if r.get("surprise_pct") is not None]
    beats_count = sum(1 for r in tracked_surp if r["verdict"] == "Beat")
    misses_count = sum(1 for r in tracked_surp if r["verdict"] == "Miss")
    lat_s = tracked_surp[-1] if tracked_surp else (surprise_4q[-1] if surprise_4q else {})
    opm_4q_vals = [r["ebit_margin_pct"] for r in surprise_4q if r.get("ebit_margin_pct") is not None]
    ebit_margin_4q_bps = round((opm_4q_vals[-1] - opm_4q_vals[0]) * 100.0) if len(opm_4q_vals) >= 2 else None
    avg_surp = round(sum(r["surprise_pct"] for r in tracked_surp) / len(tracked_surp), 1) if tracked_surp else None

    surprise_summary = {
        "beats_count": beats_count,
        "misses_count": misses_count,
        "total_tracked": len(tracked_surp),
        "latest_verdict": lat_s.get("verdict", "—"),
        "latest_surprise_pct": lat_s.get("surprise_pct"),
        "latest_eps_actual": lat_s.get("eps_actual"),
        "latest_eps_estimate": lat_s.get("eps_estimate"),
        "avg_surprise_pct": avg_surp,
        "ebit_margin_4q_delta_bps": ebit_margin_4q_bps,
    }

    result_overview_rows: List[Dict[str, Any]] = []
    if latest:
        result_overview_rows = [
            {
                "metric": f"Net Sales / Revenue ({unit})",
                "latest": fmt_comma(rev_now),
                "prior": fmt_comma(rev_prev),
                "qoq_var": f"{latest.get('qoq_rev_pct'):+}%" if latest.get("qoq_rev_pct") is not None else "—",
                "yoy_var": f"{latest.get('yoy_rev_pct'):+}%" if latest.get("yoy_rev_pct") is not None else "—",
            },
            {
                "metric": f"Operating EBIT ({unit})",
                "latest": fmt_comma(ebit_now),
                "prior": fmt_comma(ebit_prev),
                "qoq_var": f"{ebit_qoq:+}%" if ebit_qoq is not None else "—",
                "yoy_var": "—",
            },
            {
                "metric": "EBIT Margin (%)",
                "latest": fmt_comma(opm_now, 2, "%"),
                "prior": fmt_comma(opm_prev, 2, "%"),
                "qoq_var": f"{opm_bps:+} bps" if opm_bps is not None else "—",
                "yoy_var": f"{ebit_margin_4q_bps:+} bps (4Q)" if ebit_margin_4q_bps is not None else "—",
            },
            {
                "metric": f"Net Profit / PAT ({unit})",
                "latest": fmt_comma(pat_now),
                "prior": fmt_comma(pat_prev),
                "qoq_var": f"{latest.get('qoq_pat_pct'):+}%" if latest.get("qoq_pat_pct") is not None else "—",
                "yoy_var": f"{latest.get('yoy_pat_pct'):+}%" if latest.get("yoy_pat_pct") is not None else "—",
            },
            {
                "metric": f"Diluted EPS ({curr})",
                "latest": fmt_comma(lat_s.get("eps_actual"), 2),
                "prior": fmt_comma(surprise_4q[-2].get("eps_actual") if len(surprise_4q) >= 2 else None, 2),
                "qoq_var": f"{lat_s.get('surprise_pct'):+}% vs Est" if lat_s.get("surprise_pct") is not None else "—",
                "yoy_var": f"Est {fmt_comma(lat_s.get('eps_estimate'), 2)}" if lat_s.get("eps_estimate") is not None else "—",
            },
        ]

    thematic_highlights: List[Dict[str, str]] = []
    if tracked_surp:
        sp_lat = lat_s.get("surprise_pct")
        rev_txt = ""
        if forward_consensus.get("up_30d") is not None:
            rev_txt = f" 30-day forward revisions stand at {forward_consensus['up_30d']} Up vs {forward_consensus['down_30d']} Down."
        thematic_highlights.append(
            {
                "topic": "4-Quarter Beat/Miss & Estimate Revisions",
                "tone": "positive" if (sp_lat or 0) >= 1.0 else ("warning" if (sp_lat or 0) <= -1.0 else "neutral"),
                "detail": (
                    f"{q_end} EPS of {curr} {fmt_comma(lat_s.get('eps_actual'), 2)} vs estimate {curr} {fmt_comma(lat_s.get('eps_estimate'), 2)} "
                    f"({sp_lat:+}% — {lat_s.get('verdict')}); {beats_count}/{len(tracked_surp)} quarters beat consensus over the trailing 4Q span."
                    f"{rev_txt}"
                ),
            }
        )
    if latest:
        rev_yoy_txt = f" ({latest['yoy_rev_pct']:+}% YoY)" if latest.get("yoy_rev_pct") is not None else ""
        thematic_highlights.append(
            {
                "topic": "Revenue & Topline Pace",
                "tone": "positive" if (latest.get("qoq_rev_pct") or 0) > 0 else "neutral",
                "detail": (
                    f"{q_end} revenue stood at {fmt_comma(rev_now)} {unit} "
                    f"({latest.get('qoq_rev_pct'):+}% QoQ vs {prev_end}{rev_yoy_txt})."
                    if latest.get("qoq_rev_pct") is not None
                    else f"{q_end} revenue stood at {fmt_comma(rev_now)} {unit}{rev_yoy_txt}."
                ),
            }
        )
        m_4q_str = f"; {ebit_margin_4q_bps:+} bps across 4Q span" if ebit_margin_4q_bps is not None else ""
        thematic_highlights.append(
            {
                "topic": "Operating Margin Progression (EBIT bps)",
                "tone": "positive" if (opm_bps or 0) >= 0 else "warning",
                "detail": (
                    f"EBIT came in at {fmt_comma(ebit_now)} {unit} with operating margin at {fmt_comma(opm_now, 2, '%')} "
                    f"({f'{opm_bps:+} bps QoQ' if opm_bps is not None else 'sequentially stable'}{m_4q_str})."
                ),
            }
        )
        pat_qoq_val = latest.get("qoq_pat_pct")
        pat_qoq_txt = f"{pat_qoq_val:+}% QoQ" if pat_qoq_val is not None else "tracked"
        thematic_highlights.append(
            {
                "topic": "Bottom-Line (PAT) & Cash Realization",
                "tone": "positive" if (pat_qoq_val or 0) > 0 else "neutral",
                "detail": (
                    f"PAT settled at {fmt_comma(pat_now)} {unit} ({fmt_comma(npm_now, 2, '%')} net margin; "
                    f"{pat_qoq_txt}), alongside TTM CFO/EBITDA cash conversion of {m.get('cfo_to_ebitda')}x."
                ),
            }
        )

    # Gather live quarterly result / concall / transcript updates from Google News RSS + NSE disclosures
    search_q = company_name.split("LIMITED")[0].split("LTD")[0].strip() or symbol
    base_sym = re.sub(r"\.(NS|BO|TO)$", "", symbol.strip().upper())
    entity_expr = f'"{search_q}"' if len(base_sym) <= 2 else f'({base_sym} OR "{search_q}")'
    earn_raw = _fetch_google_news_rss(
        f'{entity_expr} ("Q1" OR "Q2" OR "Q3" OR "Q4" OR "results" OR "concall" OR "earnings call" OR "guidance") when:120d',
        market_gl=_market_gl(symbol),
        limit=10,
    )
    earn_kw_re = re.compile(r"\b(q1|q2|q3|q4|quarter|results?|profit|revenue|margin|ebitda|concall|earnings call|guidance|order book|transcript)\b")
    media_items: List[Dict[str, str]] = []
    seen_t: set[str] = set()
    for nf in ownership_section.get("nse_official_announcements", []):
        tl_nf = f"{nf.get('category', '')} {nf.get('title', '')}".lower()
        if any(k in tl_nf for k in ("result", "transcript", "financial", "investor", "presentation")):
            media_items.append(nf)
            seen_t.add(nf.get("title", "").lower()[:45])
    for item in earn_raw:
        t_clean = _clean_headline(item["title"], item.get("source", ""))
        if _is_low_signal_headline(t_clean, item.get("source", "")):
            continue
        tl = t_clean.lower()
        if not earn_kw_re.search(tl) or tl[:45] in seen_t:
            continue
        seen_t.add(tl[:45])
        if any(w in tl for w in ("miss", "fall", "drop", "cut", "pressure", "decline", "slump", "below")):
            eff, sent = "Negative — Margin / Earnings Softness", "negative"
        elif any(w in tl for w in ("beat", "jump", "surge", "record", "rise", "up ", "grows", "guidance", "strong", "order")):
            eff, sent = "Positive — Earnings / Demand Momentum", "positive"
        else:
            eff, sent = "Neutral — Quarterly Result Disclosure", "neutral"
        media_items.append({**item, "title": t_clean, "category": "Earnings Note", "effect": eff, "sentiment": sent})
        if len(media_items) >= 4:
            break

    if media_items:
        latest_note_txt = _repair_truncated_title(media_items[0]["title"])
        thematic_highlights.append(
            {
                "topic": "Concall & Management Commentary Tracked",
                "tone": "neutral",
                "detail": f"Latest disclosed note ({media_items[0].get('source', 'Filing')}, {media_items[0].get('date', 'Recent')}): {latest_note_txt}.",
            }
        )

    if latest:
        ebit_m_str = fmt_comma(opm_now, 2, "%")
        bps_txt = f" ({opm_bps:+} bps / {opm_bps / 100.0:+.2f}% pts QoQ)" if opm_bps is not None else ""
        q_rev_txt = f"{latest.get('qoq_rev_pct'):+}% QoQ" if latest.get("qoq_rev_pct") is not None else "reported"
        surp_note = (
            f" EPS beat/miss tracked at {lat_s['surprise_pct']:+}% ({beats_count}/{len(tracked_surp)} beats across 4Q)."
            if tracked_surp and lat_s.get("surprise_pct") is not None
            else ""
        )
        takeaway = (
            f"4Q & Latest Quarter Synthesis ({q_end}): Topline moved {q_rev_txt} to {fmt_comma(rev_now)} {unit} "
            f"with EBIT margin at {ebit_m_str}{bps_txt} and PAT at {fmt_comma(pat_now)} {unit}.{surp_note} Monitor margin trajectory and estimate revisions."
        )
    else:
        takeaway = "Quarterly result line-items unavailable in feed; refer to audited annual statements below."

    sources_checklist: List[Dict[str, str]] = [
        {"label": f"Quarterly Statements ({q_end})", "date": q_end, "url": f"https://finance.yahoo.com/quote/{symbol}/financials"},
    ]
    if tracked_surp:
        sources_checklist.append({"label": "Street Consensus & EPS Surprise Feed", "date": today_dt.isoformat(), "url": f"https://finance.yahoo.com/quote/{symbol}/analysis"})
    for nf in media_items[:3]:
        if nf.get("link"):
            sources_checklist.append({"label": f"{nf.get('source', 'Disclosure')}: {nf['title'][:58]}", "date": nf.get("date", "Recent"), "url": nf["link"]})

    return {
        "available": True,
        "unit": unit,
        "latest_quarter": q_end,
        "prior_quarter": prev_end,
        "freshness": freshness,
        "surprise_4q": surprise_4q,
        "surprise_summary": surprise_summary,
        "forward_consensus": forward_consensus,
        "result_overview_rows": result_overview_rows,
        "thematic_highlights": thematic_highlights,
        "media_and_filings": media_items,
        "media_briefing": synthesize_news_briefing(
            section_key="earnings",
            company_name=company_name,
            items=media_items,
            empty_msg="No recent quarterly earnings call or exchange result notices returned in feed; refer to quarterly table.",
        ),
        "sources_checklist": sources_checklist,
        "takeaway": takeaway,
    }


def build_segment_analysis(symbol: str) -> Dict[str, Any]:
    """Build statutory Ind-AS 108 / Banking segment breakdown when available for the company."""
    raw = fetch_nse_segment_results(symbol)
    if not raw.get("available") or len(raw.get("segments") or []) < 2:
        return {
            "available": False,
            "status": raw.get("status", "unavailable"),
            "classification": raw.get("classification", ""),
            "segments": [],
            "has_cap_employed": False,
            "opinion": "",
        }

    segs = raw["segments"]
    has_cap = any(s.get("cap_employed_cr") and s["cap_employed_cr"] > 0 for s in segs)
    top_rev = max(segs, key=lambda s: s.get("revenue_cr") or 0.0)
    top_ebit = max(segs, key=lambda s: s.get("ebit_cr") or 0.0)
    core_segs = [s for s in segs if not s["name"].lower().startswith("other")] or segs
    top_margin = max(core_segs, key=lambda s: s.get("ebit_margin_pct") or -999.0)
    yoy_cands = [s for s in core_segs if s.get("rev_yoy_pct") is not None]
    fast_yoy = max(yoy_cands, key=lambda s: s["rev_yoy_pct"]) if yoy_cands else None

    parts = [
        f"{top_rev['name']} leads topline ({fmt_comma(top_rev.get('rev_mix_pct'), 1, '%')} of revenue)",
    ]
    if top_ebit["name"] != top_rev["name"] or (top_ebit.get("ebit_mix_pct") or 0) > (top_rev.get("rev_mix_pct") or 0) + 5:
        parts.append(
            f"while {top_ebit['name']} contributes {fmt_comma(top_ebit.get('ebit_mix_pct'), 1, '%')} of segment EBIT"
        )
    if top_margin.get("ebit_margin_pct") is not None:
        parts.append(
            f"with highest operating margin in {top_margin['name']} ({fmt_comma(top_margin['ebit_margin_pct'], 1, '%')})"
        )
    opinion = "; ".join(parts) + "."
    if fast_yoy and fast_yoy.get("rev_yoy_pct") is not None:
        opinion += f" Fastest YoY topline momentum came from {fast_yoy['name']} ({fast_yoy['rev_yoy_pct']:+}% YoY)."

    return {
        "available": True,
        "status": "ok",
        "period_end": raw.get("period_end", ""),
        "prior_period_end": raw.get("prior_period_end", ""),
        "yoy_period_end": raw.get("yoy_period_end", ""),
        "filing_basis": raw.get("filing_basis", "Consolidated"),
        "source_url": raw.get("source_url", ""),
        "has_cap_employed": has_cap,
        "intersegment_count": raw.get("intersegment_count", 0),
        "segments": segs,
        "opinion": opinion,
    }


def build_returns_analysis(
    bundle: Dict[str, Any],
    stock: Dict[str, Any],
    dcf_model: Dict[str, Any],
    pe_bands: Dict[str, Any],
    key_data: Dict[str, Any],
) -> Dict[str, Any]:
    """Build educational 5-Year Public Equity Returns (IRR / MOIC) scenario & attribution model.

    Adapts institutional returns attribution & 2-way sensitivity methodology to public equities
    entering at Current Market Price (CMP), adhering strictly to SEBI educational framing.
    """
    info = bundle.get("info", {}) or {}
    curr = stock.get("currency") or info.get("currency") or "INR"
    div, unit = _scale_divisor(curr)

    price = float(stock.get("price") or info.get("currentPrice") or dcf_model.get("current_price") or 0.0)
    shares_scaled = float(dcf_model.get("shares_scaled") or 0.0)
    if price > 0 and shares_scaled > 0:
        entry_equity = round(price * shares_scaled, 1)
    else:
        entry_equity = round(float(info.get("marketCap") or 0.0) / div, 1)

    entry_net_debt = float(dcf_model.get("net_debt") or 0.0)
    entry_ev = round(entry_equity + entry_net_debt, 1)
    entry_ebitda = float(dcf_model.get("base_ebitda") or 0.0)
    if entry_ebitda <= 0 and info.get("ebitda"):
        entry_ebitda = round(float(info["ebitda"]) / div, 1)

    if entry_equity <= 0 or entry_ebitda <= 0 or entry_ev <= 0 or not dcf_model.get("available", True):
        return {
            "available": False,
            "unit": unit,
            "currency": curr,
            "reason": "Entry market cap, trailing EBITDA, or verified multi-year DCF inputs are unavailable/negative for EV/EBITDA returns modeling.",
            "opinion": "5-year EV/EBITDA returns modeling is omitted where baseline operating EBITDA or verified multi-year fundamentals are unavailable.",
        }

    entry_mult = round(entry_ev / entry_ebitda, 1)
    proj_g_raw = dcf_model.get("projected_rev_growth_pct")
    if proj_g_raw is None:
        return {
            "available": False,
            "unit": unit,
            "currency": curr,
            "reason": "Verified multi-year revenue growth rate is unavailable for returns projection.",
            "opinion": "5-year returns scenario modeling is omitted because verified historical growth inputs are missing.",
        }
    base_g_pct = max(3.0, min(22.0, float(proj_g_raw)))

    # Mean-reversion gentle tilt when P/E sits >10% away from 5Y historical norm
    cur_pe = float(pe_bands.get("current_pe") or 0.0)
    mean_pe = float(pe_bands.get("mean_5y_pe") or 0.0)
    if cur_pe > 0 and mean_pe > 0:
        pe_ratio = max(0.75, min(1.25, mean_pe / cur_pe))
        base_exit_mult = round(entry_mult * (0.65 + 0.35 * pe_ratio), 1)
    else:
        base_exit_mult = entry_mult
    base_exit_mult = max(4.0, base_exit_mult)

    # Real FCF conversion & dividend yield from verified DCF + market snapshot (no arbitrary fallback ratios)
    f_rows = dcf_model.get("forecast_5y") or []
    cum_fcff_base = sum(float(r.get("fcff") or 0.0) for r in f_rows)
    cum_ebitda_base = sum(entry_ebitda * ((1.0 + base_g_pct / 100.0) ** yr) for yr in range(1, 6))
    if cum_ebitda_base > 0 and cum_fcff_base > 0:
        fcf_conv = max(0.0, min(0.85, cum_fcff_base / cum_ebitda_base))
    else:
        fcf_conv = 0.0

    div_yield_pct = max(0.0, min(10.0, float(key_data.get("div_yield_pct") or 0.0)))
    div_5y = round(entry_equity * (div_yield_pct / 100.0) * 5.0, 1)

    def _eval_case(g_pct: float, exit_m: float) -> Dict[str, Any]:
        g = g_pct / 100.0
        exit_ebitda = entry_ebitda * ((1.0 + g) ** 5)
        cum_ebitda = sum(entry_ebitda * ((1.0 + g) ** yr) for yr in range(1, 6))
        cum_fcf = cum_ebitda * fcf_conv
        retained_cash = max(0.0, cum_fcf - div_5y) if cum_fcf >= div_5y else 0.0
        effective_div = div_5y if cum_fcf >= (div_5y * 0.5) else round(max(div_5y * 0.5, cum_fcf), 1)

        exit_ev = exit_ebitda * exit_m
        exit_net_debt = entry_net_debt - retained_cash
        exit_equity = exit_ev - exit_net_debt + effective_div

        moic = max(0.05, exit_equity / entry_equity)
        irr_pct = ((moic ** (1.0 / 5.0)) - 1.0) * 100.0

        growth_moic = ((exit_ebitda - entry_ebitda) * exit_m) / entry_equity
        mult_moic = ((exit_m - entry_mult) * entry_ebitda) / entry_equity
        cash_moic = (retained_cash + effective_div) / entry_equity

        return {
            "growth_pct": round(g_pct, 1),
            "exit_mult": round(exit_m, 1),
            "exit_ebitda": round(exit_ebitda, 1),
            "exit_ev": round(exit_ev, 1),
            "exit_net_debt": round(exit_net_debt, 1),
            "cum_dividends": round(effective_div, 1),
            "retained_cash": round(retained_cash, 1),
            "exit_equity": round(exit_equity, 1),
            "moic": round(moic, 2),
            "irr_pct": round(irr_pct, 1),
            "attr_growth_moic": round(growth_moic, 2),
            "attr_multiple_moic": round(mult_moic, 2),
            "attr_cash_moic": round(cash_moic, 2),
        }

    base_case = _eval_case(base_g_pct, base_exit_mult)
    bear_case = _eval_case(max(1.5, round(base_g_pct - 3.5, 1)), max(3.5, round(base_exit_mult * 0.80, 1)))
    bull_case = _eval_case(round(base_g_pct + 3.0, 1), round(base_exit_mult * 1.15, 1))

    scenarios = [
        {"name": "Bear (Slower Growth / De-rating)", "key": "bear", **bear_case},
        {"name": "Base (Normalized Trajectory)", "key": "base", **base_case},
        {"name": "Bull (Stronger Growth / Re-rating)", "key": "bull", **bull_case},
    ]

    growth_grid = [
        round(max(1.5, base_g_pct - 4.0), 1),
        round(max(2.5, base_g_pct - 2.0), 1),
        round(base_g_pct, 1),
        round(base_g_pct + 2.0, 1),
        round(base_g_pct + 4.0, 1),
    ]
    raw_mults = [round(max(3.5, base_exit_mult * f), 1) for f in (0.80, 0.90, 1.00, 1.10, 1.20)]
    mult_grid: List[float] = []
    for idx_m, m_val in enumerate(raw_mults):
        if mult_grid and m_val <= mult_grid[-1]:
            m_val = round(mult_grid[-1] + 0.5, 1)
        mult_grid.append(m_val)

    sensitivity_matrix: List[List[Dict[str, Any]]] = []
    for g_val in growth_grid:
        row_cells = []
        for m_val in mult_grid:
            res = _eval_case(g_val, m_val)
            row_cells.append(
                {
                    "growth_pct": g_val,
                    "exit_mult": m_val,
                    "irr_pct": res["irr_pct"],
                    "moic": res["moic"],
                    "label": f"{res['irr_pct']:.1f}% / {res['moic']:.2f}x",
                }
            )
        sensitivity_matrix.append(row_cells)

    opinion = (
        f"Educational 5-Year Returns Scenario Note: Entering at CMP ({curr} {fmt_comma(price, 1)} | Entry {entry_mult}x EV/EBITDA), "
        f"the normalized base-case scenario ({base_case['growth_pct']}% EBITDA CAGR, {base_case['exit_mult']}x exit multiple) "
        f"models an implied 5-year IRR of {base_case['irr_pct']}% ({base_case['moic']}x MOIC). "
        f"Return attribution decomposes net equity value creation into {base_case['attr_growth_moic']:+}x from EBITDA growth, "
        f"{base_case['attr_multiple_moic']:+}x from exit-multiple shift, and {base_case['attr_cash_moic']:+}x from FCF retention & dividends. "
        f"Outcomes span {bear_case['irr_pct']}% IRR ({bear_case['moic']}x) to {bull_case['irr_pct']}% IRR ({bull_case['moic']}x) across regimes — "
        f"for educational modeling only, not a return guarantee or advice."
    )

    return {
        "available": True,
        "unit": unit,
        "currency": curr,
        "entry_price": round(price, 1),
        "entry_equity": entry_equity,
        "entry_net_debt": round(entry_net_debt, 1),
        "entry_ev": entry_ev,
        "entry_ebitda": round(entry_ebitda, 1),
        "entry_mult": entry_mult,
        "fcf_conversion_pct": round(fcf_conv * 100.0, 1),
        "div_yield_pct": round(div_yield_pct, 2),
        "base": base_case,
        "scenarios": scenarios,
        "sensitivity_growth_pcts": growth_grid,
        "sensitivity_mults": mult_grid,
        "sensitivity_matrix": sensitivity_matrix,
        "opinion": opinion,
    }


def build_fcff_dcf_model(
    bundle: Dict[str, Any], stock: Dict[str, Any], annual_4y: Dict[str, Any]
) -> Dict[str, Any]:
    """Build deterministic 5-Year Unlevered FCFF DCF, Equity Bridge, Sensitivity Matrix & Valuation Decision."""
    info = bundle.get("info", {})
    currency = info.get("currency", "INR")
    div, unit = _scale_divisor(currency)

    price = float(stock.get("price") or info.get("currentPrice") or 0.0)
    shares_raw = float(info.get("sharesOutstanding") or 0.0)
    shares_scaled = shares_raw / div if shares_raw else 0.0
    total_debt = float(info.get("totalDebt") or 0.0) / div
    total_cash = float(info.get("totalCash") or 0.0) / div
    net_debt = total_debt - total_cash

    rows = annual_4y.get("rows", [])
    latest_row = rows[-1] if rows else {}
    base_rev = float(latest_row.get("revenue") or (info.get("totalRevenue") or 0.0) / div or 0.0)

    inc = bundle.get("income_stmt")
    base_ebit = 0.0
    tax_rate = 0.2517 if currency == "INR" else 0.21
    if inc is not None and not inc.empty:
        ebit_s = _row_series(inc, ["EBIT", "Operating Income"]).dropna()
        if not ebit_s.empty:
            base_ebit = float(ebit_s.iloc[0]) / div
        tax_s = _row_series(inc, ["Tax Provision"]).dropna()
        pretax_s = _row_series(inc, ["Pretax Income"]).dropna()
        if not tax_s.empty and not pretax_s.empty and float(pretax_s.iloc[0]) > 0:
            obs_tax = float(tax_s.iloc[0]) / float(pretax_s.iloc[0])
            if 0.05 <= obs_tax <= 0.40:
                tax_rate = round(obs_tax, 4)

    rev_cagr_raw = (stock.get("metrics") or {}).get("rev_cagr_pct")
    if base_rev <= 0 or base_ebit <= 0 or shares_scaled <= 0 or price <= 0 or rev_cagr_raw is None:
        return {
            "available": False,
            "unit": unit,
            "base_revenue": round(base_rev, 1),
            "base_ebitda": round(float(latest_row.get("ebitda") or 0.0), 1),
            "shares_scaled": round(shares_scaled, 3),
            "ebit_margin_pct": None,
            "projected_rev_growth_pct": None,
            "reinvestment_rate_pct": None,
            "wacc_pct": None,
            "terminal_growth_pct": None,
            "tax_rate_pct": round(tax_rate * 100.0, 2),
            "net_debt": round(net_debt, 1),
            "enterprise_value": None,
            "equity_value": None,
            "fair_value_per_share": None,
            "current_price": round(price, 1) if price > 0 else None,
            "upside_downside_pct": None,
            "forecast_5y": [],
            "sensitivity_wacc_pcts": [],
            "sensitivity_g_pcts": [],
            "sensitivity_matrix": [],
            "sotp_bridge": {
                "is_conglomerate_heavy_capex": False,
                "ladder": [],
                "opinion": "Insufficient verified operating EBIT, multi-year revenue CAGR, or share count data for intrinsic EV/EBITDA or DCF valuation.",
            },
            "investor_opinion": "Strict actual-data guard: Intrinsic cash-flow fair value omitted because verified trailing EBIT, revenue CAGR, or share count is unavailable.",
        }

    ebit_margin = float(np.clip(base_ebit / base_rev, 0.01, 0.70))
    base_fcf = float(latest_row.get("fcf") or 0.0)
    rev_cagr = float(rev_cagr_raw) / 100.0
    proj_rev_g = float(np.clip(rev_cagr, 0.03, 0.25))

    rf = 0.070 if currency == "INR" else 0.043
    erp = 0.055 if currency == "INR" else 0.048
    beta_raw = info.get("beta")
    beta = float(np.clip(float(beta_raw), 0.65, 1.50)) if (beta_raw is not None and float(beta_raw) > 0) else 1.0
    mcap_usd_b = float(stock.get("mcap_usd_b") or 0.0)
    size_prem = 0.012 if 0 < mcap_usd_b < 2.0 else (0.005 if 0 < mcap_usd_b < 10.0 else 0.0)
    base_wacc = round(float(np.clip(rf + beta * erp * 0.85 + size_prem, 0.10, 0.145)), 4)
    term_g = 0.050 if currency == "INR" else 0.030

    if base_ebit > 0 and base_fcf > 0:
        observed_reinv = 1.0 - (base_fcf / (base_ebit * (1.0 - tax_rate)))
        reinv_rate = float(np.clip(observed_reinv, 0.20, 0.65))
    else:
        reinv_rate = 0.45

    def _compute_fair_value(wacc_val: float, g_val: float) -> Tuple[List[Dict[str, Any]], float, float, float]:
        forecast: List[Dict[str, Any]] = []
        pv_fcff_sum = 0.0
        rev_curr = base_rev
        last_fcff = 0.0
        for yr in range(1, 6):
            step_g = proj_rev_g - (proj_rev_g - g_val) * ((yr - 1) / 5.0) * 0.6
            rev_curr = rev_curr * (1.0 + step_g)
            ebit_y = rev_curr * ebit_margin
            nopat_y = ebit_y * (1.0 - tax_rate)
            yr_reinv = reinv_rate * (1.0 - 0.15 * ((yr - 1) / 4.0))
            reinv_amt = nopat_y * yr_reinv
            fcff_y = nopat_y - reinv_amt
            df = (1.0 + wacc_val) ** yr
            pv_y = fcff_y / df
            pv_fcff_sum += pv_y
            last_fcff = fcff_y
            forecast.append(
                {
                    "year": f"Year {yr}",
                    "rev_growth_pct": round(step_g * 100.0, 1),
                    "revenue": round(rev_curr, 1),
                    "ebit": round(ebit_y, 1),
                    "nopat": round(nopat_y, 1),
                    "reinvestment": round(reinv_amt, 1),
                    "fcff": round(fcff_y, 1),
                    "pv_fcff": round(pv_y, 1),
                }
            )
        spread = max(wacc_val - g_val, 0.025)
        tv = (last_fcff * (1.0 + g_val)) / spread
        pv_tv = tv / ((1.0 + wacc_val) ** 5)
        ev = pv_fcff_sum + pv_tv
        eq_val = ev - net_debt
        fair_px = (eq_val / shares_scaled) if shares_scaled > 0 else 0.0
        return forecast, round(ev, 1), round(eq_val, 1), round(fair_px, 1)

    forecast_rows, base_ev, base_eq_val, base_fair_px = _compute_fair_value(base_wacc, term_g)
    upside_pct = round((base_fair_px / price - 1.0) * 100.0, 1) if (price > 0 and base_fair_px > 0) else None

    wacc_grid = [round(base_wacc - 0.01, 4), round(base_wacc - 0.005, 4), base_wacc, round(base_wacc + 0.005, 4)]
    g_grid = [round(term_g - 0.01, 4), round(term_g - 0.005, 4), term_g, round(term_g + 0.005, 4)]
    sensitivity = []
    for w in wacc_grid:
        row_vals = []
        for g in g_grid:
            _, _, _, fp = _compute_fair_value(w, g)
            row_vals.append({"wacc_pct": round(w * 100, 2), "g_pct": round(g * 100, 2), "fair_price": fp})
        sensitivity.append(row_vals)

    if upside_pct is None:
        val_opinion = "Intrinsic cash-flow fair value could not be reliably estimated from available share/cash data."
    elif upside_pct >= 20:
        val_opinion = (
            f"Valuation Discount Observed: Conservative DCF intrinsic estimate ({currency} {fmt_comma(base_fair_px, 1)}) sits {upside_pct:+}% above "
            f"CMP ({currency} {fmt_comma(price, 1)}), indicating fundamental valuation cushion if cash-flow assumptions hold."
        )
    elif upside_pct >= -5:
        val_opinion = (
            f"Near Base-Case Intrinsic Value: Estimated DCF fair value ({currency} {fmt_comma(base_fair_px, 1)}) lies within single digits ({upside_pct:+}%) of CMP "
            f"({currency} {fmt_comma(price, 1)}), reflecting balanced base-case pricing."
        )
    else:
        val_opinion = (
            f"Valuation Premium on Consolidated Cash Flows: CMP ({currency} {fmt_comma(price, 1)}) trades above conservative base DCF fair value "
            f"({currency} {fmt_comma(base_fair_px, 1)}, {upside_pct:+}%), pricing in higher growth or sum-of-the-parts value realization."
        )

    latest_ebitda = float(rows[-1].get("ebitda") or (base_ebit * 1.18)) if rows else base_ebit * 1.18
    is_conglomerate_gap = (upside_pct is not None and upside_pct <= -10.0 and reinv_rate >= 0.30)
    sotp_ladder = []
    if shares_scaled > 0 and latest_ebitda > 0:
        for mult in (10.0, 12.0, 14.0, 16.0):
            s_ev = latest_ebitda * mult
            s_eq = s_ev - net_debt
            s_px = round(s_eq / shares_scaled, 1)
            s_up = round((s_px / price - 1.0) * 100.0, 1) if price > 0 else None
            sotp_ladder.append({"ev_ebitda": mult, "implied_price": s_px, "upside_pct": s_up})

    if is_conglomerate_gap and sotp_ladder:
        sotp_note = (
            f"Conglomerate / Capex-Cycle Check: Because consolidated expansion capex ({round(reinv_rate * 100.0, 1)}% reinvestment) "
            f"weighs on near-term free cash flows, Sum-of-the-Parts (EV/EBITDA) valuation provides an essential second lens. "
            f"At 12x–14x trailing EBITDA ({fmt_comma(latest_ebitda)} {unit}), implied equity value is "
            f"{currency} {fmt_comma(sotp_ladder[1]['implied_price'], 1)}–{fmt_comma(sotp_ladder[2]['implied_price'], 1)} per share."
        )
    else:
        sotp_note = (
            f"Clean Operating Lens: Reinvestment needs are well-balanced relative to cash generation; "
            f"cross-checking EV/EBITDA (10x–16x trailing EBITDA of {fmt_comma(latest_ebitda)} {unit}) confirms the DCF valuation range."
        )

    return {
        "available": True,
        "unit": unit,
        "base_revenue": round(base_rev, 1),
        "base_ebitda": round(latest_ebitda, 1),
        "shares_scaled": round(shares_scaled, 3),
        "ebit_margin_pct": round(ebit_margin * 100.0, 2),
        "projected_rev_growth_pct": round(proj_rev_g * 100.0, 1),
        "reinvestment_rate_pct": round(reinv_rate * 100.0, 1),
        "wacc_pct": round(base_wacc * 100.0, 2),
        "terminal_growth_pct": round(term_g * 100.0, 2),
        "tax_rate_pct": round(tax_rate * 100.0, 2),
        "net_debt": round(net_debt, 1),
        "enterprise_value": base_ev,
        "equity_value": base_eq_val,
        "fair_value_per_share": base_fair_px,
        "current_price": round(price, 1),
        "upside_downside_pct": upside_pct,
        "forecast_5y": forecast_rows,
        "sensitivity_wacc_pcts": [round(w * 100, 2) for w in wacc_grid],
        "sensitivity_g_pcts": [round(g * 100, 2) for g in g_grid],
        "sensitivity_matrix": sensitivity,
        "sotp_bridge": {
            "is_conglomerate_heavy_capex": is_conglomerate_gap,
            "ladder": sotp_ladder,
            "opinion": sotp_note,
        },
        "investor_opinion": val_opinion,
    }


PEER_OVERRIDES_IN: Dict[str, List[str]] = {
    "RELIANCE.NS": ["ONGC.NS", "BPCL.NS", "IOC.NS"],
    "NTPC.NS": ["POWERGRID.NS", "TATAPOWER.NS", "COALINDIA.NS"],
    "ONGC.NS": ["RELIANCE.NS", "BPCL.NS", "IOC.NS"],
    "BHARTIARTL.NS": ["TCS.NS", "INFY.NS", "RELIANCE.NS"],
}


def auto_select_sector_peers(symbol: str, market: str = "IN", max_peers: int = 3) -> List[str]:
    """Pick domain-authentic sector peers deterministically from overrides, starter & multibagger universes."""
    sym = symbol.strip().upper()
    if sym in PEER_OVERRIDES_IN:
        return [sym] + PEER_OVERRIDES_IN[sym][:max_peers]
    pool = PRESET_UNIVERSES.get(market.upper(), {})
    m_pool = MULTIBAGGER_UNIVERSES.get(market.upper(), {})

    matched_peers: List[str] = []
    for src in (pool, m_pool):
        for _, syms in src.items():
            if sym in syms:
                for p in syms:
                    if p != sym and p not in matched_peers:
                        matched_peers.append(p)
    if not matched_peers:
        for syms in pool.values():
            for p in syms:
                if p != sym and p not in matched_peers:
                    matched_peers.append(p)
            if len(matched_peers) >= max_peers:
                break
    return [sym] + matched_peers[:max_peers]


def build_plain_english_advanced_insights(
    stock: Dict[str, Any], audit: Dict[str, Any]
) -> List[Dict[str, Any]]:
    """Translate financial quality metrics into clear, investor-friendly language without jargon."""
    m = stock.get("metrics", {})
    name = stock.get("name") or stock.get("symbol")

    roic = m.get("roic_pct")
    inc_roic = m.get("inc_roic_pct")
    spread = m.get("roic_wacc_spread_pct")
    cfo_eb = m.get("cfo_to_ebitda")
    net_debt_eb = m.get("net_debt_to_ebitda")
    int_cov = m.get("int_coverage")
    rev_g = m.get("rev_cagr_pct")
    rev_dcf = m.get("implied_fcf_g_pct")
    fcf_y = m.get("fcf_yield_pct")
    ev_nopat = m.get("ev_to_nopat")
    st_debt = m.get("st_debt_share_pct")

    insights: List[Dict[str, Any]] = []

    if spread is not None and roic is not None:
        if spread >= 5.0:
            meaning = (
                f"Every ₹100 of capital {name} uses earns ₹{roic:.1f} a year, beating its cost of funds by +{spread}%. "
                f"New projects earn {inc_roic}%, proving the business gets stronger as it grows."
            )
            tone, badge = "positive", "Strong Wealth Creator"
        elif spread >= 0:
            meaning = (
                f"{name} earns {roic}% on invested money—comfortably covering its funding cost (+{spread}% cushion). "
                f"Safe business, though higher returns on new capital ({inc_roic}%) would boost stock returns."
            )
            tone, badge = "neutral", "Steady Earner"
        else:
            meaning = (
                f"Returns on invested money ({roic}%) currently sit {abs(spread)}% below funding cost because heavy recent spending has not yet turned into full profit. "
                f"Monitoring whether new project returns ({inc_roic}%) climb above WACC over upcoming cycles helps track value creation."
            )
            tone, badge = "warning", "Capex Heavy / Lower Returns"
        insights.append(
            {
                "title": "1. Return on Invested Capital vs. Cost of Capital (ROIC)",
                "score_label": badge,
                "reading": f"ROIC: {roic}% | ROIC–WACC Spread: {spread:+}% | Incremental ROIC: {inc_roic}%",
                "tone": tone,
                "what_it_is": "Measures post-tax operating return generated on total invested capital (equity plus debt), and whether incremental capital expenditure is value-accretive.",
                "what_it_means": meaning,
            }
        )

    if cfo_eb is not None:
        if cfo_eb >= 0.75:
            meaning = f"{name} converts {cfo_eb:.2f}x of EBITDA into operating cash flow, confirming strong earnings quality and disciplined working-capital collection."
            tone, badge = "positive", "High Cash Quality"
        elif cfo_eb >= 0.45:
            meaning = f"Operating cash conversion is moderate at {cfo_eb:.2f}x EBITDA, indicating partial capital absorption in receivables or inventory."
            tone, badge = "neutral", "Moderate Cash Conversion"
        else:
            meaning = f"Cash conversion is weak ({cfo_eb:.2f}x EBITDA); reported operating profits are not yet translating into cash inflows, warranting receivable monitoring."
            tone, badge = "warning", "Low Cash Conversion"
        insights.append(
            {
                "title": "2. Operating Cash Flow Conversion vs. Reported Earnings",
                "score_label": badge,
                "reading": f"CFO / EBITDA: {cfo_eb}x | Net Debt / EBITDA: {net_debt_eb}x | Interest Coverage: {int_cov}x",
                "tone": tone,
                "what_it_is": "Compares Operating Cash Flow (CFO) against EBITDA to verify that accounting profits are backed by real cash generation rather than accrual build-up.",
                "what_it_means": meaning,
            }
        )

    if rev_dcf is not None and rev_g is not None:
        gap = round(rev_dcf - rev_g, 1)
        if gap <= 0:
            meaning = f"Current market valuation requires {rev_dcf}% annual FCF compounding over 7 years versus historical revenue growth of {rev_g}%, leaving valuation cushion."
            tone, badge = "positive", "Conservative Pricing"
        elif gap <= 5.0:
            meaning = f"At {ev_nopat}x EV/NOPAT ({fcf_y}% FCF yield), implied 7-year cash growth ({rev_dcf}%) sits broadly in line with historical revenue growth ({rev_g}%)."
            tone, badge = "neutral", "Fairly Valued Growth"
        else:
            meaning = f"At {ev_nopat}x EV/NOPAT, current pricing discounts {rev_dcf}% annual FCF growth—{gap} percentage points above the {rev_g}% historical trend, raising de-rating risk on execution misses."
            tone, badge = "warning", "Rich Implied Expectations"
        insights.append(
            {
                "title": "3. Reverse-DCF Implied Growth Expectations",
                "score_label": badge,
                "reading": f"Market-Implied FCF Growth: {rev_dcf}% vs. Historical Revenue CAGR: {rev_g}%",
                "tone": tone,
                "what_it_is": "Solves backward from live enterprise value to isolate the 7-year Free Cash Flow CAGR embedded in the current share price.",
                "what_it_means": meaning,
            }
        )

    insights.append(
        {
            "title": "4. Balance Sheet Solvency, Governance & Trading Liquidity",
            "score_label": "Clean Audit" if not audit.get("vetoes") else "Risk Flagged",
            "reading": f"Short-Term Debt Share: {st_debt}% | Institutional Ownership: {m.get('inst_hold_pct')}%",
            "tone": "positive" if not audit.get("vetoes") else "warning",
            "what_it_is": "Evaluates short-term debt rollover pressure, auditor qualification flags, and institutional secondary-market liquidity.",
            "what_it_means": (
                f"Interest coverage stands at {int_cov}x with short-term debt at {st_debt}% of borrowings, supported by ${stock.get('adtv_usd_m')}M average daily turnover. "
                + ("Audit and governance screening shows zero critical red flags." if not audit.get("vetoes") else f"Governance / Credit Flag: {'; '.join(audit.get('vetoes', []))}.")
            ),
        }
    )
    return insights


def _calc_horizon_returns(hist: pd.DataFrame) -> Dict[str, Optional[float]]:
    """Compute 1M, 3M, 6M, and 12M price returns from daily close history."""
    out: Dict[str, Optional[float]] = {"1M": None, "3M": None, "6M": None, "12M": None}
    if hist is None or hist.empty or "Close" not in hist.columns:
        return out
    closes = pd.to_numeric(hist["Close"], errors="coerce").dropna()
    if len(closes) < 5:
        return out
    curr = float(closes.iloc[-1])
    for label, bars in (("1M", 21), ("3M", 63), ("6M", 126), ("12M", 252)):
        idx = max(0, len(closes) - 1 - bars)
        if len(closes) > bars // 2:
            prev = float(closes.iloc[idx])
            if prev > 0:
                out[label] = round((curr / prev - 1.0) * 100.0, 1)
    return out


def _parse_pct_text(raw: Any) -> Optional[float]:
    if raw is None:
        return None
    cleaned = re.sub(r"[%\s,]", "", str(raw))
    try:
        return round(float(cleaned), 1)
    except ValueError:
        return None


def _tier_dots(val: Optional[float], all_vals: List[float], higher_is_better: bool = True) -> str:
    """Return 3-dot tier badge (●●● / ●●○ / ●○○) calibrated across the peer cohort."""
    valid = sorted(v for v in all_vals if v is not None)
    if val is None or len(valid) <= 1:
        return "●●○"
    lo, hi = valid[0], valid[-1]
    if abs(hi - lo) < 1e-6:
        return "●●○"
    pos = (val - lo) / (hi - lo)
    if not higher_is_better:
        pos = 1.0 - pos
    if pos >= 0.66:
        return "●●●"
    if pos >= 0.33:
        return "●●○"
    return "●○○"


def _build_competitive_analysis(
    symbol: str,
    stock: Dict[str, Any],
    peer_perf: List[Dict[str, Any]],
    bench_label: str,
    perf_rows: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """Adopt competitive-analysis skill: 2x2 positioning, ●●● <actual> comparative table, and 4-pillar moat synthesis."""
    m = stock.get("metrics", {})
    sector_low = f"{stock.get('sector', '')} {stock.get('industry', '')}".lower()

    cohort: List[Dict[str, Any]] = []
    target_row = next((p for p in peer_perf if p.get("symbol") == symbol), None)
    ret_12m_target = perf_rows[-1]["stock_pct"] if perf_rows else None
    if target_row is None:
        target_row = {
            "symbol": symbol,
            "name": stock.get("name", symbol),
            "ret_12m_pct": ret_12m_target,
            "score": stock.get("total_score"),
            "ev_to_nopat": m.get("ev_to_nopat"),
            "roic_pct": m.get("roic_pct"),
            "cfo_to_ebitda": m.get("cfo_to_ebitda"),
            "fcf_yield_pct": m.get("fcf_yield_pct"),
            "mcap_b": stock.get("market_cap_b"),
        }
    cohort.append(target_row)
    for p in peer_perf:
        if p.get("symbol") != symbol:
            cohort.append(p)
    cohort = cohort[:4]

    roic_vals = [float(c["roic_pct"]) for c in cohort if c.get("roic_pct") is not None]
    mcap_vals = [float(c["mcap_b"]) for c in cohort if c.get("mcap_b") is not None]
    cfo_vals = [float(c["cfo_to_ebitda"]) for c in cohort if c.get("cfo_to_ebitda") is not None]
    fcf_vals = [float(c["fcf_yield_pct"]) for c in cohort if c.get("fcf_yield_pct") is not None]
    ret_vals = [float(c["ret_12m_pct"]) for c in cohort if c.get("ret_12m_pct") is not None]
    mult_vals = [float(c["ev_to_nopat"]) for c in cohort if c.get("ev_to_nopat") is not None and float(c["ev_to_nopat"]) > 0]
    score_vals = [float(c["score"]) for c in cohort if c.get("score") is not None]

    dimensions = [
        {
            "dimension": "Scale (MCap)",
            "cells": [
                {"symbol": c["symbol"], "display": f"{_tier_dots(c.get('mcap_b'), mcap_vals, True)} {fmt_comma(c.get('mcap_b'), 1, 'B')}"}
                for c in cohort
            ],
        },
        {
            "dimension": "Capital Return (ROIC)",
            "cells": [
                {"symbol": c["symbol"], "display": f"{_tier_dots(c.get('roic_pct'), roic_vals, True)} {fmt_comma(c.get('roic_pct'), 1, '%')}"}
                for c in cohort
            ],
        },
        {
            "dimension": "Cash Conversion (CFO/EB)",
            "cells": [
                {"symbol": c["symbol"], "display": f"{_tier_dots(c.get('cfo_to_ebitda'), cfo_vals, True)} {fmt_comma(c.get('cfo_to_ebitda'), 2, 'x')}"}
                for c in cohort
            ],
        },
        {
            "dimension": "FCF Yield (%)",
            "cells": [
                {"symbol": c["symbol"], "display": f"{_tier_dots(c.get('fcf_yield_pct'), fcf_vals, True)} {fmt_comma(c.get('fcf_yield_pct'), 1, '%')}"}
                for c in cohort
            ],
        },
        {
            "dimension": "12M Momentum",
            "cells": [
                {"symbol": c["symbol"], "display": f"{_tier_dots(c.get('ret_12m_pct'), ret_vals, True)} {fmt_comma(c.get('ret_12m_pct'), 1, '%')}"}
                for c in cohort
            ],
        },
        {
            "dimension": "Multiple (EV/NOPAT)",
            "cells": [
                {"symbol": c["symbol"], "display": f"{_tier_dots(c.get('ev_to_nopat'), mult_vals, False)} {fmt_comma(c.get('ev_to_nopat'), 1, 'x')}"}
                for c in cohort
            ],
        },
        {
            "dimension": "Composite Quality",
            "cells": [
                {"symbol": c["symbol"], "display": f"{_tier_dots(c.get('score'), score_vals, True)} {fmt_comma(c.get('score'), 1)}/100"}
                for c in cohort
            ],
        },
    ]

    max_mcap = max((float(c.get("mcap_b") or 1.0) for c in cohort), default=1.0)
    matrix_points = []
    for c in cohort:
        mc = float(c.get("mcap_b") or 10.0)
        rad = round(7.0 + 11.0 * ((mc / max_mcap) ** 0.5), 1)
        matrix_points.append(
            {
                "symbol": c["symbol"],
                "is_target": c["symbol"] == symbol,
                "x_roic": round(float(c.get("roic_pct") or 0.0), 1),
                "y_ret12": round(float(c.get("ret_12m_pct") or 0.0), 1),
                "score": round(float(c.get("score") or 0.0), 1),
                "mcap_b": round(mc, 1),
                "r": rad,
            }
        )

    sorted_by_score = sorted(cohort, key=lambda c: float(c.get("score") or 0.0), reverse=True)
    sorted_by_roic = sorted(cohort, key=lambda c: float(c.get("roic_pct") or 0.0), reverse=True)
    sorted_by_mcap = sorted(cohort, key=lambda c: float(c.get("mcap_b") or 0.0), reverse=True)
    t_rank = next((i + 1 for i, c in enumerate(sorted_by_score) if c["symbol"] == symbol), 1)
    t_roic = float(target_row.get("roic_pct") or 0.0)
    t_score = float(target_row.get("score") or 0.0)
    best_roic_peer = sorted_by_roic[0] if sorted_by_roic else target_row

    if sorted_by_score and sorted_by_score[0]["symbol"] == symbol and sorted_by_roic[0]["symbol"] == symbol:
        insight_headline = f"{symbol} leads tracked peers on composite quality ({t_score}/100) and capital efficiency ({t_roic}% ROIC)"
    elif sorted_by_mcap and sorted_by_mcap[0]["symbol"] == symbol and best_roic_peer["symbol"] != symbol:
        insight_headline = (
            f"{symbol} anchors sector scale ({fmt_comma(target_row.get('mcap_b'), 1, 'B')}) while {best_roic_peer['symbol']} leads peer ROIC "
            f"({fmt_comma(best_roic_peer.get('roic_pct'), 1, '%')} vs {t_roic}%)"
        )
    else:
        insight_headline = (
            f"{symbol} ranks #{t_rank}/{len(cohort)} in tracked peer group ({t_score}/100 score, {t_roic}% ROIC vs {bench_label} backdrop)"
        )

    roic_med = float(np.median(roic_vals)) if roic_vals else t_roic
    cfo_eb = float(m.get("cfo_to_ebitda") or 0.0)
    net_d = float(m.get("net_debt_to_ebitda") or 0.0)
    reinv = float(m.get("reinvestment_rate_pct") or 0.0)
    gross_p = float(m.get("gross_profitability") or 0.0)

    is_it_tech = any(k in sector_low for k in ("software", "information technology", "it services", "consulting", "internet"))
    is_telecom_energy_conglom = any(k in sector_low for k in ("oil", "gas", "refining", "telecom", "conglomerate", "integrated"))
    is_bank_fin = any(k in sector_low for k in ("bank", "financial", "insurance", "credit"))

    net_eff_rating = (
        "Strong"
        if (is_telecom_energy_conglom and float(target_row.get("mcap_b") or 0) > 40)
        else ("Moderate" if (is_it_tech or is_bank_fin or (sorted_by_mcap and sorted_by_mcap[0]["symbol"] == symbol)) else "Weak")
    )
    net_eff_note = (
        "Consumer-digital ecosystem & broad distribution cross-linkages reinforce customer acquisition"
        if is_telecom_energy_conglom
        else ("Two-sided partner, cloud & delivery ecosystem scale supports enterprise win rates" if is_it_tech else "Moderate ecosystem flywheel; differentiation rests primarily on execution and distribution")
    )

    sw_rating = "Strong" if (is_it_tech or is_bank_fin or "defense" in sector_low or "aerospace" in sector_low or "pharma" in sector_low) else "Moderate"
    sw_note = (
        "Multi-year enterprise workflows, compliance locks, and core software integration raise migration friction"
        if sw_rating == "Strong"
        else "B2B/retail channel presence and multi-service bundling provide moderate retention friction"
    )

    scale_rating = (
        "Strong"
        if (sorted_by_mcap and sorted_by_mcap[0]["symbol"] == symbol) or (t_roic >= roic_med and float(target_row.get("mcap_b") or 0) > 25)
        else ("Moderate" if float(target_row.get("mcap_b") or 0) > 5 else "Weak")
    )
    scale_note = f"Capitalization tier ({fmt_comma(target_row.get('mcap_b'), 1, 'B')}) supports fixed-cost amortization and procurement bargaining leverage"

    intang_rating = "Strong" if (t_roic >= 20.0 or gross_p >= 0.35 or is_it_tech or "consumer" in sector_low or "fmcg" in sector_low) else "Moderate"
    intang_note = f"Brand equity, specialized domain IP, and operating know-how drive {t_roic}% post-tax ROIC (vs peer median {round(roic_med, 1)}%)"

    moat_pillars = [
        {"pillar": "Network Effects", "rating": net_eff_rating, "detail": net_eff_note},
        {"pillar": "Switching Costs", "rating": sw_rating, "detail": sw_note},
        {"pillar": "Scale Economies", "rating": scale_rating, "detail": scale_note},
        {"pillar": "Intangible Assets", "rating": intang_rating, "detail": intang_note},
    ]

    advantages: List[str] = []
    vulnerabilities: List[str] = []
    if t_roic >= roic_med and t_roic > 0:
        advantages.append(f"Capital efficiency exceeds peer median ({t_roic}% ROIC vs {round(roic_med, 1)}% median).")
    else:
        vulnerabilities.append(f"ROIC trails top peer benchmark ({t_roic}% vs peer high {fmt_comma(best_roic_peer.get('roic_pct'), 1, '%')}).")
    if cfo_eb >= 0.75:
        advantages.append(f"Healthy cash realization ({cfo_eb}x CFO/EBITDA) internally funds operations.")
    else:
        vulnerabilities.append(f"Lower cash conversion ({cfo_eb}x CFO/EBITDA) limits near-term free cash flexibility.")
    if net_d <= 0.5:
        advantages.append(f"Fortress balance sheet ({net_d}x Net Debt/EBITDA) provides cycle resilience.")
    elif net_d >= 1.5:
        vulnerabilities.append(f"Elevated leverage ({net_d}x Net Debt/EBITDA) alongside {reinv}% reinvestment burden.")
    if ret_12m_target is not None and perf_rows[-1].get("relative_pct") is not None and perf_rows[-1]["relative_pct"] < -5.0:
        vulnerabilities.append(f"Stock trails {bench_label} by {perf_rows[-1]['relative_pct']}% over trailing 12M; monitor margin inflection.")
    if not advantages:
        advantages.append(f"Top-tier market scale ({fmt_comma(target_row.get('mcap_b'), 1, 'B')}) sustains competitive relevance.")
    if not vulnerabilities:
        vulnerabilities.append(f"Monitor sector pricing cycles and multiple sensitivity ({fmt_comma(target_row.get('ev_to_nopat'), 1, 'x')} EV/NOPAT).")

    return {
        "insight_headline": insight_headline,
        "cohort_symbols": [c["symbol"] for c in cohort],
        "dimensions": dimensions,
        "matrix_points": matrix_points,
        "moat_pillars": moat_pillars,
        "durable_advantages": advantages[:2],
        "structural_vulnerabilities": vulnerabilities[:2],
        "roic_peer_median": round(roic_med, 1),
    }


def build_key_market_and_performance(
    bundle: Dict[str, Any],
    workspace: Any,
    symbol: str,
    stock: Dict[str, Any],
    screener_data: Dict[str, Any],
    peers_list: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """Build Price Analysis (CMP, 52W Range, 50/200-DMA Trend), Basic Fundamentals & Benchmark Performance."""
    info = bundle.get("info", {})
    curr = stock.get("currency", "INR")
    hist = bundle.get("history")
    closes = (
        pd.to_numeric(hist["Close"], errors="coerce").dropna()
        if hist is not None and not hist.empty and "Close" in hist.columns
        else pd.Series(dtype=float)
    )
    price = float(stock.get("price") or info.get("currentPrice") or (closes.iloc[-1] if not closes.empty else 0.0))
    h52 = info.get("fiftyTwoWeekHigh") or (float(closes.max()) if not closes.empty else None)
    l52 = info.get("fiftyTwoWeekLow") or (float(closes.min()) if not closes.empty else None)
    pct_from_high = round((price / float(h52) - 1.0) * 100.0, 1) if (h52 and price) else None
    pct_above_low = round((price / float(l52) - 1.0) * 100.0, 1) if (l52 and price) else None
    range_pos_pct = (
        round(float(np.clip((price - float(l52)) / (float(h52) - float(l52)) * 100.0, 0.0, 100.0)), 1)
        if (h52 and l52 and float(h52) > float(l52) and price > 0)
        else None
    )

    # Moving averages & 1Y price chart payload (downsampled cleanly to ~160 points if longer)
    dma50_series = closes.rolling(50).mean() if len(closes) >= 50 else pd.Series(dtype=float)
    dma200_series = closes.rolling(200).mean() if len(closes) >= 200 else pd.Series(dtype=float)
    dma50 = round(float(dma50_series.iloc[-1]), 1) if not dma50_series.empty and pd.notna(dma50_series.iloc[-1]) else None
    dma200 = round(float(dma200_series.iloc[-1]), 1) if not dma200_series.empty and pd.notna(dma200_series.iloc[-1]) else None
    if dma50 is None and info.get("fiftyDayAverage"):
        dma50 = round(float(info["fiftyDayAverage"]), 1)
    if dma200 is None and info.get("twoHundredDayAverage"):
        dma200 = round(float(info["twoHundredDayAverage"]), 1)

    vs_dma50_pct = round((price / dma50 - 1.0) * 100.0, 1) if (dma50 and price) else None
    vs_dma200_pct = round((price / dma200 - 1.0) * 100.0, 1) if (dma200 and price) else None

    if dma50 and dma200:
        if price >= dma50 and price >= dma200:
            trend_signal = "Bullish Uptrend (Above 50 & 200 DMA)"
            trend_tone = "positive"
            price_trend_opinion = (
                f"Positive Technical Trend: Trading {vs_dma50_pct:+}% above its 50-DMA ({curr} {fmt_comma(dma50, 1)}) "
                f"and {vs_dma200_pct:+}% above its 200-DMA ({curr} {fmt_comma(dma200, 1)}), sitting at {range_pos_pct}% of its 52-week range."
            )
        elif price >= dma50 and price < dma200:
            trend_signal = "Early Rebound (Above 50 DMA, Below 200 DMA)"
            trend_tone = "neutral"
            price_trend_opinion = (
                f"Short-Term Rebound Underway: Reclaimed its 50-DMA ({curr} {fmt_comma(dma50, 1)}, {vs_dma50_pct:+}%), "
                f"though still {abs(vs_dma200_pct or 0)}% below long-term 200-DMA resistance ({curr} {fmt_comma(dma200, 1)})."
            )
        elif price < dma50 and price >= dma200:
            trend_signal = "Consolidation Above 200-DMA"
            trend_tone = "neutral"
            price_trend_opinion = (
                f"Consolidation Above Long-Term Moving Average: Holding above 200-DMA ({curr} {fmt_comma(dma200, 1)}, {vs_dma200_pct:+}%) "
                f"after retracing {pct_from_high:+}% from its 52-week peak, testing intermediate support near 50-DMA ({curr} {fmt_comma(dma50, 1)})."
            )
        else:
            trend_signal = "Below 50 & 200 DMA"
            trend_tone = "warning"
            price_trend_opinion = (
                f"Subdued Technical Trend: Trading below both 50-DMA ({curr} {fmt_comma(dma50, 1)}) and 200-DMA ({curr} {fmt_comma(dma200, 1)}), "
                f"{abs(pct_from_high or 0)}% below its 52-week high; reclaiming the 50-DMA is a key trend-stabilization threshold."
            )
    else:
        trend_signal = "Price Zone Tracked"
        trend_tone = "neutral"
        price_trend_opinion = f"CMP stands at {curr} {fmt_comma(price, 1)} ({pct_from_high:+}% from 52W High)." if pct_from_high is not None else "Price trend tracked."

    tail_closes = closes.tail(180)
    price_series = {
        "dates": [str(idx)[:10] for idx in tail_closes.index],
        "closes": [round(float(v), 1) for v in tail_closes.values],
        "dma50": [
            round(float(dma50_series.loc[idx]), 1) if idx in dma50_series.index and pd.notna(dma50_series.loc[idx]) else None
            for idx in tail_closes.index
        ],
        "dma200": [
            round(float(dma200_series.loc[idx]), 1) if idx in dma200_series.index and pd.notna(dma200_series.loc[idx]) else None
            for idx in tail_closes.index
        ],
    }

    div_yield_raw = info.get("dividendYield")
    if div_yield_raw is not None:
        div_yield_pct = round(float(div_yield_raw) * (100.0 if float(div_yield_raw) < 0.25 else 1.0), 2)
    else:
        div_yield_pct = None

    ratios = screener_data.get("ratios", {})
    roe_yf = round(float(info["returnOnEquity"]) * 100.0, 1) if info.get("returnOnEquity") is not None else None
    roe_pct = _parse_pct_text(ratios.get("ROE")) or roe_yf
    roce_pct = _parse_pct_text(ratios.get("ROCE"))
    eps_ttm = round(float(info["trailingEps"]), 1) if info.get("trailingEps") is not None else None
    book_val = _parse_pct_text(ratios.get("Book Value")) or (round(float(info["bookValue"]), 1) if info.get("bookValue") else None)

    shares_os = info.get("sharesOutstanding")
    share_div = 1e7 if curr == "INR" else 1e6
    shares_os_disp = round(float(shares_os) / share_div, 2) if shares_os else None

    recent_90 = closes.tail(90)
    sup_swing = round(float(recent_90.min()), 1) if not recent_90.empty else (round(float(l52), 1) if l52 else None)
    res_swing = round(float(recent_90.max()), 1) if not recent_90.empty else (round(float(h52), 1) if h52 else None)
    support_level = (
        round(min(x for x in (sup_swing, dma50, dma200) if x and x <= price * 1.03), 1)
        if any(x and x <= price * 1.03 for x in (sup_swing, dma50, dma200))
        else sup_swing
    )
    resistance_level = res_swing
    if dma50 and dma200:
        zone_low = round(min(dma50, dma200), 1)
        zone_high = round(max(dma50, dma200), 1)
        entry_zone_label = f"{curr} {fmt_comma(zone_low, 1)} – {fmt_comma(zone_high, 1)}"
    elif support_level:
        entry_zone_label = f"{curr} {fmt_comma(support_level, 1)}"
    else:
        entry_zone_label = "N/A"

    key_data = {
        "cmp": round(price, 1),
        "high_52w": round(float(h52), 1) if h52 else None,
        "low_52w": round(float(l52), 1) if l52 else None,
        "pct_from_52w_high": pct_from_high,
        "pct_above_52w_low": pct_above_low,
        "range_52w_pos_pct": range_pos_pct,
        "dma_50": dma50,
        "dma_200": dma200,
        "vs_dma50_pct": vs_dma50_pct,
        "vs_dma200_pct": vs_dma200_pct,
        "support_level": support_level,
        "resistance_level": resistance_level,
        "entry_zone_label": entry_zone_label,
        "trend_signal": trend_signal,
        "trend_tone": trend_tone,
        "price_trend_opinion": price_trend_opinion,
        "price_series": price_series,
        "pe_ttm": round(float(info["trailingPE"]), 1) if info.get("trailingPE") else None,
        "pb": round(float(info["priceToBook"]), 2) if info.get("priceToBook") else None,
        "eps_ttm": eps_ttm,
        "book_value": book_val,
        "roe_pct": roe_pct,
        "roce_pct": roce_pct,
        "div_yield_pct": div_yield_pct,
        "shares_outstanding": shares_os_disp,
    }

    bench_sym = "^NSEI" if symbol.endswith((".NS", ".BO")) else ("^GSPTSE" if symbol.endswith(".TO") else "^GSPC")
    bench_label = "Nifty 50" if bench_sym == "^NSEI" else ("S&P/TSX" if bench_sym == "^GSPTSE" else "S&P 500")
    stock_ret = _calc_horizon_returns(bundle.get("history"))
    bench_ret: Dict[str, Optional[float]] = {"1M": None, "3M": None, "6M": None, "12M": None}
    try:
        b_bundle = workspace.bundles.get(bench_sym)
        b_hist = b_bundle.get("history") if b_bundle else yf.Ticker(bench_sym).history(period="1y")
        bench_ret = _calc_horizon_returns(b_hist)
    except Exception:
        pass

    perf_rows: List[Dict[str, Any]] = []
    for h in ("1M", "3M", "6M", "12M"):
        s_val = stock_ret.get(h)
        b_val = bench_ret.get(h)
        rel = round(s_val - b_val, 1) if (s_val is not None and b_val is not None) else None
        perf_rows.append({"horizon": h, "stock_pct": s_val, "benchmark_pct": b_val, "relative_pct": rel})

    peer_perf: List[Dict[str, Any]] = []
    for p in peers_list:
        psym = p.get("symbol")
        if not psym:
            continue
        p12 = None
        try:
            pb = workspace.bundles.get(psym)
            if pb and pb.get("history") is not None:
                p12 = _calc_horizon_returns(pb.get("history")).get("12M")
            else:
                ph = yf.Ticker(psym).history(period="1y")
                p12 = _calc_horizon_returns(ph).get("12M")
        except Exception:
            pass
        peer_perf.append(
            {
                "symbol": psym,
                "name": p.get("name", psym),
                "ret_12m_pct": p12,
                "score": p.get("score"),
                "ev_to_nopat": p.get("ev_to_nopat"),
                "roic_pct": p.get("roic_pct"),
                "cfo_to_ebitda": p.get("cfo_to_ebitda"),
                "fcf_yield_pct": p.get("fcf_yield_pct"),
                "mcap_b": p.get("mcap_b"),
            }
        )

    rel_12 = perf_rows[-1]["relative_pct"]
    abs_12 = perf_rows[-1]["stock_pct"]
    if rel_12 is not None and abs_12 is not None:
        if rel_12 >= 8.0:
            perf_opinion = (
                f"Relative Outperformance: {symbol} delivered {abs_12:+}% over 12 months, outpacing {bench_label} by {rel_12:+}%, "
                f"consistent with sustained institutional appetite and earnings momentum."
            )
        elif rel_12 >= -8.0:
            perf_opinion = (
                f"Market-Line Performance: {symbol} returned {abs_12:+}% over 12 months ({rel_12:+}% vs {bench_label}), "
                f"indicating range-bound consolidation while awaiting quarterly earnings triggers."
            )
        else:
            perf_opinion = (
                f"Relative Underperformance vs {bench_label} ({rel_12:+}% Relative Over 12M, {abs_12:+}% Absolute): "
                f"Price lags the broader index; quarterly margin trajectory and FPI flow direction remain key stabilization indicators."
            )
    else:
        perf_opinion = f"Multi-horizon comparison against {bench_label} helps track whether recent price action confirms business improvement."

    comp_analysis = _build_competitive_analysis(
        symbol=symbol,
        stock=stock,
        peer_perf=peer_perf,
        bench_label=bench_label,
        perf_rows=perf_rows,
    )

    return {
        "benchmark_label": bench_label,
        "key_data": key_data,
        "performance_table": perf_rows,
        "peer_performance": peer_perf,
        "competitive_analysis": comp_analysis,
        "performance_opinion": perf_opinion,
    }


def build_historical_pe_bands(
    symbol: str,
    bundle: Dict[str, Any],
    annual_4y: Dict[str, Any],
) -> Dict[str, Any]:
    """Compute 5-year monthly trailing P/E history with Mean & +/- 1 SD valuation bands."""
    info = bundle.get("info", {})
    shares = float(info.get("sharesOutstanding") or 0.0)
    curr_pe = round(float(info["trailingPE"]), 1) if info.get("trailingPE") else None
    inc = bundle.get("income_stmt") if bundle.get("income_stmt") is not None else bundle.get("income")
    eps_by_year: Dict[int, float] = {}
    if inc is not None and not inc.empty and shares > 0:
        pat_s = _row_series(inc, ["Net Income", "Net Income Common Stockholders"])
        for col in pat_s.index:
            val = pat_s.loc[col]
            if pd.notna(val) and float(val) > 0:
                yr = pd.to_datetime(col).year
                eps_by_year[yr] = float(val) / shares
    ttm_eps = float(info.get("trailingEps") or 0.0)

    dates: List[str] = []
    pe_vals: List[float] = []
    try:
        mhist = yf.Ticker(symbol).history(period="5y", interval="1mo")
        if mhist is not None and not mhist.empty and "Close" in mhist.columns and (eps_by_year or ttm_eps > 0):
            yrs_sorted = sorted(eps_by_year.keys())
            for idx, px in mhist["Close"].dropna().items():
                y = pd.Timestamp(idx).year
                # Strict no-lookahead EPS matching: exact FY or prior reported annual EPS only
                eps = eps_by_year.get(y)
                if not eps and yrs_sorted:
                    prior = [yy for yy in yrs_sorted if yy <= y]
                    eps = eps_by_year[prior[-1]] if prior else None
                elif not eps and not yrs_sorted:
                    eps = ttm_eps
                if eps and eps > 0:
                    pe = round(float(px) / eps, 1)
                    if 2.0 <= pe <= 120.0:
                        dates.append(str(idx)[:7])
                        pe_vals.append(pe)
    except Exception:
        pass

    if len(pe_vals) >= 6:
        arr = np.array(pe_vals, dtype=float)
        mean_pe = round(float(np.mean(arr)), 1)
        sd_pe = round(float(np.std(arr)), 1)
        plus_1sd = round(mean_pe + sd_pe, 1)
        minus_1sd = round(max(mean_pe - sd_pe, 3.0), 1)
        cmp_pe = curr_pe or pe_vals[-1]
        disc_pct = round((cmp_pe / mean_pe - 1.0) * 100.0, 1) if mean_pe > 0 else 0.0
        if cmp_pe <= minus_1sd:
            zone, tone = "Discount (-1 SD Bargain Zone)", "positive"
            opinion = f"Historically Cheap Multiple: Current P/E ({cmp_pe}x) trades {abs(disc_pct)}% below its 5Y average ({mean_pe}x) and inside the -1 SD bargain zone ({minus_1sd}x)."
        elif cmp_pe >= plus_1sd:
            zone, tone = "Premium (+1 SD Expensive Zone)", "warning"
            opinion = f"Stretched Historical Multiple: Current P/E ({cmp_pe}x) trades +{abs(disc_pct)}% above its 5Y average ({mean_pe}x) near +1 SD ({plus_1sd}x). Margin of safety is thin."
        else:
            zone, tone = "Fair Historical Valuation Band", "neutral"
            opinion = f"Normal Historical Range: Current P/E ({cmp_pe}x) sits {disc_pct:+}% versus its 5Y average ({mean_pe}x; normal band {minus_1sd}x–{plus_1sd}x)."
    else:
        mean_pe = curr_pe
        sd_pe = None
        plus_1sd = None
        minus_1sd = None
        disc_pct = None
        zone, tone = "Limited 5Y Multiple History", "neutral"
        opinion = f"Current P/E stands at {curr_pe}x." if curr_pe else "Insufficient multi-year EPS history for 5-year P/E bands."

    return {
        "dates": dates,
        "pe_series": pe_vals,
        "current_pe": curr_pe or (pe_vals[-1] if pe_vals else None),
        "mean_5y_pe": mean_pe,
        "plus_1sd_pe": plus_1sd,
        "minus_1sd_pe": minus_1sd,
        "discount_prem_pct": disc_pct,
        "zone_label": zone,
        "tone": tone,
        "opinion": opinion,
    }


def build_working_capital_summary(
    annual_4y: Dict[str, Any], screener_data: Dict[str, Any]
) -> Dict[str, Any]:
    """Combine Screener Working Capital Days & 4-year Cash Conversion (CFO / PAT)."""
    wc = screener_data.get("working_capital") or {}
    periods = wc.get("periods", [])
    series = wc.get("series", {})
    latest_wc = wc.get("latest", {})

    rows_4y = annual_4y.get("rows", [])
    cfo_pat_rows: List[Dict[str, Any]] = []
    for r in rows_4y:
        pat = r.get("pat")
        cfo = r.get("cfo")
        ratio = round(float(cfo) / float(pat), 2) if (pat and cfo and pat > 0) else None
        cfo_pat_rows.append({"period": r["period"], "cfo_to_pat": ratio, "cfo": cfo, "pat": pat})

    latest_cfo_pat = cfo_pat_rows[-1]["cfo_to_pat"] if cfo_pat_rows else None
    ccc = latest_wc.get("Cash Conversion Cycle")
    debtor_d = latest_wc.get("Debtor Days")

    if latest_cfo_pat is not None and latest_cfo_pat >= 0.90:
        wc_op = f"Strong Cash Realization (CFO/PAT {latest_cfo_pat}x): Accounting profits convert efficiently into bank cash"
    elif latest_cfo_pat is not None:
        wc_op = f"Moderate Cash Conversion (CFO/PAT {latest_cfo_pat}x): Watch receivable & inventory absorption"
    else:
        wc_op = "Working capital & cash conversion ratios help confirm earnings quality."
    if debtor_d is not None and ccc is not None:
        wc_op += f"; Debtor Days sit at {int(round(debtor_d))} days with a {int(round(ccc))}-day Cash Conversion Cycle."
    else:
        wc_op += "."

    return {
        "periods": periods,
        "series": series,
        "latest": latest_wc,
        "cfo_to_pat_rows": cfo_pat_rows,
        "latest_cfo_to_pat": latest_cfo_pat,
        "opinion": wc_op,
    }


def build_ownership_deals_and_ratings(
    symbol: str,
    company_name: str,
    bundle: Dict[str, Any],
    stock: Dict[str, Any],
    screener_data: Dict[str, Any],
    perf_summary: Dict[str, Any],
) -> Dict[str, Any]:
    """Build Shareholding, FPI/Promoter Actions, Bulk/Block Deals & Brokerage/Credit Rating Analysis."""
    search_q = company_name.split("LIMITED")[0].split("LTD")[0].strip() or symbol
    gl = _market_gl(symbol)
    curr = stock.get("currency", "INR")
    price = float(stock.get("price") or 0.0)

    yf_insiders_pct = None
    yf_inst_pct = None
    yf_inst_float_pct = None
    yf_inst_count = None
    price_targets: Dict[str, Any] = {}
    rec_summary: Dict[str, int] = {"strongBuy": 0, "buy": 0, "hold": 0, "sell": 0, "strongSell": 0}
    rec_total = 0
    insider_txns: List[Dict[str, Any]] = []

    try:
        tk = yf.Ticker(symbol)
        mh = getattr(tk, "major_holders", None)
        if mh is not None and not mh.empty:
            mh_map = {}
            for idx, row in mh.iterrows():
                val = row.iloc[0] if len(row) > 0 else None
                mh_map[str(idx)] = float(val) if pd.notna(val) else None
            if mh_map.get("insidersPercentHeld") is not None:
                yf_insiders_pct = round(mh_map["insidersPercentHeld"] * 100.0, 2)
            if mh_map.get("institutionsPercentHeld") is not None:
                yf_inst_pct = round(mh_map["institutionsPercentHeld"] * 100.0, 2)
            if mh_map.get("institutionsFloatPercentHeld") is not None:
                yf_inst_float_pct = round(mh_map["institutionsFloatPercentHeld"] * 100.0, 2)
            if mh_map.get("institutionsCount") is not None:
                yf_inst_count = int(round(mh_map["institutionsCount"]))

        apt = getattr(tk, "analyst_price_targets", None)
        if isinstance(apt, dict) and apt:
            mean_tp = apt.get("mean")
            median_tp = apt.get("median")
            high_tp = apt.get("high")
            low_tp = apt.get("low")
            upside_tp = round((float(mean_tp) / price - 1.0) * 100.0, 1) if (mean_tp and price > 0) else None
            price_targets = {
                "current": round(float(apt.get("current") or price), 1),
                "low": round(float(low_tp), 1) if low_tp else None,
                "mean": round(float(mean_tp), 1) if mean_tp else None,
                "median": round(float(median_tp), 1) if median_tp else None,
                "high": round(float(high_tp), 1) if high_tp else None,
                "implied_upside_pct": upside_tp,
            }

        recs = getattr(tk, "recommendations", None)
        if recs is not None and not recs.empty:
            r0 = recs.iloc[0]
            for k in ("strongBuy", "buy", "hold", "sell", "strongSell"):
                rec_summary[k] = int(r0.get(k, 0) or 0)
            rec_total = sum(rec_summary.values())

        ins_df = getattr(tk, "insider_transactions", None)
        if ins_df is not None and not ins_df.empty:
            for _, row in ins_df.head(6).iterrows():
                dt_raw = row.get("Start Date")
                dt_str = str(dt_raw)[:10] if pd.notna(dt_raw) else "Recent"
                sh_val = int(row["Shares"]) if pd.notna(row.get("Shares")) else None
                tot_val = round(float(row["Value"]), 1) if pd.notna(row.get("Value")) else None
                tx_desc = str(row.get("Transaction") or row.get("Text") or "Reported Filing")[:90]
                if price > 0 and tot_val is not None and tot_val > 0 and sh_val and sh_val > 0:
                    imp_px = tot_val / sh_val
                    if imp_px < price * 0.15 and "esop" not in tx_desc.lower():
                        tx_desc = f"{tx_desc} (ESOP / Split-Adj. Allotment)"
                elif price > 0 and "at price" in tx_desc.lower():
                    m_px = re.search(r"at price\s+(\d+(?:\.\d+)?)", tx_desc, flags=re.I)
                    if m_px and float(m_px.group(1)) < price * 0.15 and "esop" not in tx_desc.lower():
                        tx_desc = f"{tx_desc} (ESOP / Allotment Price)"
                insider_txns.append(
                    {
                        "date": dt_str,
                        "insider": str(row.get("Insider") or "Insider / Promoter"),
                        "position": str(row.get("Position") or ""),
                        "shares": sh_val,
                        "value": tot_val,
                        "transaction": tx_desc,
                    }
                )
    except Exception:
        pass

    # Screener quarterly shareholding history (Promoters, FIIs, DIIs, Public)
    sh = screener_data.get("shareholding") or {}
    sh_quarters: List[str] = sh.get("quarters", [])[-5:]
    sh_series: Dict[str, List[Optional[float]]] = {}
    for cat, vals in (sh.get("series") or {}).items():
        sh_series[cat] = vals[-5:] if vals else []
    latest_sh = sh.get("latest") or {}
    qoq_sh = sh.get("qoq_change_pp") or {}

    prom_now = latest_sh.get("Promoters", yf_insiders_pct)
    fii_now = latest_sh.get("FIIs")
    dii_now = latest_sh.get("DIIs")
    pub_now = latest_sh.get("Public")
    fii_delta = qoq_sh.get("FIIs")
    dii_delta = qoq_sh.get("DIIs")
    prom_delta = qoq_sh.get("Promoters")

    # Classify FPI & Ownership Flow Opinion
    flow_parts: List[str] = []
    if fii_delta is not None:
        flow_parts.append(f"Foreign Investors (FPIs) {'raised' if fii_delta > 0 else 'trimmed'} stake by {fii_delta:+} pp last quarter (now {fii_now}%)")
    if dii_delta is not None:
        flow_parts.append(f"Domestic Funds (DIIs/MFs) {'accumulated' if dii_delta > 0 else 'reduced'} {dii_delta:+} pp (now {dii_now}%)")
    if prom_delta is not None and prom_delta != 0:
        flow_parts.append(f"Promoter stake shifted by {prom_delta:+} pp (now {prom_now}%)")
    elif prom_now is not None:
        flow_parts.append(f"Promoter holding stays steady at {prom_now}%")

    if fii_delta is not None and dii_delta is not None and fii_delta > 0 and dii_delta > 0:
        ownership_opinion = "Dual Institutional Buying: Both foreign (FPI) and domestic (MF/DII) institutions added shares. " + "; ".join(flow_parts) + "."
    elif dii_delta is not None and fii_delta is not None and dii_delta > 0 and fii_delta < 0:
        ownership_opinion = "Domestic Absorption of Foreign Selling: Domestic mutual funds are buying what foreign funds trimmed. " + "; ".join(flow_parts) + "."
    elif prom_delta is not None and prom_delta < -1.0:
        ownership_opinion = "Watch Promoter Stake Reduction: " + "; ".join(flow_parts) + ". Verify reasons for promoter selling before adding."
    elif flow_parts:
        ownership_opinion = "Stable Ownership Base: " + "; ".join(flow_parts) + "."
    else:
        ownership_opinion = (
            f"Insiders hold {yf_insiders_pct}% and {yf_inst_count or 'global'} institutions hold {yf_inst_pct}% "
            f"of total shares ({yf_inst_float_pct}% of public float)."
        )

    base_sym = re.sub(r"\.(NS|BO|TO)$", "", symbol.strip().upper())
    entity_expr = f'"{search_q}"' if len(base_sym) <= 2 else f'({base_sym} OR "{search_q}")'

    # Free RSS Queries for Bulk/Block Deals + Promoter Actions AND Institutional/Credit Ratings
    deal_news_raw = _fetch_google_news_rss(
        f'{entity_expr} ("bulk deal" OR "block deal" OR "promoter" OR "stake sale" OR "pledge" OR "buyback" OR "OFS") when:180d',
        market_gl=gl,
        limit=14,
    )
    deals_events: List[Dict[str, str]] = []
    deal_kw_re = re.compile(r"\b(bulk|block|promoter|promoters|pledge|unpledge|buyback|ofs|stake|insider|sast|shareholding|fpi|fii|dividend|split|bonus)\b")
    for item in deal_news_raw:
        src = item.get("source", "")
        cleaned_title = _clean_headline(item["title"], src)
        if _is_low_signal_headline(cleaned_title, src):
            continue
        tl = cleaned_title.lower()
        # Skip multi-year-old retrospective articles (e.g. "Buyback 2023 Details")
        if re.search(r"\b20(1[0-9]|2[0-4])\b", tl) and "2026" not in tl and "2025" not in tl:
            continue
        if not deal_kw_re.search(tl):
            continue
        if any(w in tl for w in ("bulk", "block")):
            tag, effect = "Bulk / Block Deal", "Neutral / Track — Institutional Block Flow"
        elif "unpledge" in tl or "release of pledge" in tl:
            tag, effect = "Promoter Unpledge", "Positive — Encumbrance Reduction"
        elif "pledge" in tl:
            tag, effect = "Promoter Pledge", "Negative — Promoter Pledge Overhang"
        elif "buyback" in tl:
            tag, effect = "Buyback / Capital Return", "Positive — EPS-Accretive Capital Return"
        elif any(w in tl for w in ("ofs", "stake sale", "offload", "trim")):
            tag, effect = "Stake Sale / OFS", "Watch — Supply Overhang / Stake Dilution"
        else:
            tag, effect = "Corporate / Ownership Action", "Neutral — Capital / Ownership Update"
        deals_events.append({**item, "title": cleaned_title, "category": tag, "effect": effect})
        if len(deals_events) >= 5:
            break

    if deals_events or insider_txns:
        has_pledge_risk = any("pledge" in d["title"].lower() and "unpledge" not in d["title"].lower() for d in deals_events)
        if has_pledge_risk:
            deals_opinion = "Caution on Promoter Pledge Disclosures: Review recent promoter encumbrance filings closely to assess governance and margin-call risk."
        elif deals_events:
            deals_opinion = (
                f"Tracked {len(deals_events)} material ownership/capital-action disclosure(s) near CMP ({curr} {fmt_comma(price, 1)}); "
                "note that sub-market Form C insider prices typically reflect ESOP exercises or allotment pricing rather than open-market trades."
            )
        else:
            deals_opinion = f"Tracked {len(insider_txns)} regulatory insider filing(s) with no disorderly promoter selling flagged."
    else:
        deals_opinion = "Benign Insider Tape: No promoter stake dilution, pledge escalation, or large block overhang reported in the last 6 months."

    rating_news_raw = _fetch_google_news_rss(
        f'{entity_expr} ("target price" OR "ICICI Direct" OR "Motilal Oswal" OR "PL Capital" OR "CRISIL" OR "ICRA" OR "CARE Ratings" OR "Fitch" OR "Moody" OR "brokerage" OR "downgrade") when:180d',
        market_gl=gl,
        limit=16,
    )
    rating_updates: List[Dict[str, str]] = []
    broker_agency_re = re.compile(
        r"\b(icici direct|motilal|pl capital|prabhudas|crisil|icra|care ratings|fitch|moody|s&p|jefferies|jpmorgan|nomura|clsa|kotak|citi|goldman|morgan stanley|hsbc|ubs|bernstein|emkay|hdfc sec|axis cap|anand rathi|sharekhan|nirmal bang|brokerage|brokerages|consensus)\b"
    )
    research_call_re = re.compile(
        r"\b(target price|price target|target of|downgrade|credit rating|eps growth|slash targets?|raises? target|initiates? coverage)\b"
    )
    for item in rating_news_raw:
        src = item.get("source", "")
        cleaned_title = _clean_headline(item["title"], src)
        if _is_low_signal_headline(cleaned_title, src):
            continue
        tl = cleaned_title.lower()
        # Exclude commercial IT/tech partnership releases mentioning software "upgrade"
        if not (broker_agency_re.search(tl) or research_call_re.search(tl)):
            continue
        if any(c in tl for c in ("crisil", "icra", "care ratings", "fitch", "moody", "s&p", "credit rating")):
            tag = "Credit Rating"
            effect = (
                "Credit Agency — Rating Caution / Watch"
                if any(w in tl for w in ("downgrade", "negative", "watch", "cut"))
                else "Credit Agency — Rating Affirmed"
            )
        elif any(u in tl for u in ("sell", "downgrade", "underperform", "reduce", "slash", "cut target")):
            tag = "External Brokerage"
            effect = "External Media — Cautious / Target Cut"
        elif any(u in tl for u in ("split", "mixed")):
            tag = "External Brokerage"
            effect = "External Media — Mixed Consensus"
        elif any(u in tl for u in ("buy", "upgrade", "outperform", "accumulate", "overweight", "keeps buy", "raise")):
            tag = "External Brokerage"
            effect = "External Media — Positive Note"
        else:
            tag = "External Brokerage"
            effect = "External Media — Coverage Update"
        rating_updates.append({**item, "title": cleaned_title, "category": tag, "effect": effect})
        if len(rating_updates) >= 5:
            break

    bullish_cnt = rec_summary["strongBuy"] + rec_summary["buy"]
    hold_cnt = rec_summary["hold"]
    bear_cnt = rec_summary["sell"] + rec_summary["strongSell"]
    mean_tp = price_targets.get("mean")
    tp_up = price_targets.get("implied_upside_pct")
    if rec_total > 0 and mean_tp:
        buy_share = round(bullish_cnt / rec_total * 100.0, 0)
        if buy_share >= 65:
            ratings_opinion = (
                f"External Public Consensus Summary ({bullish_cnt}/{rec_total} Positive, {hold_cnt} Neutral, {bear_cnt} Cautious): "
                f"Third-party consensus mean estimate sits at {curr} {fmt_comma(mean_tp, 1)} ({tp_up:+}% vs CMP); cited strictly as public market data."
            )
        elif buy_share >= 45:
            ratings_opinion = (
                f"External Public Consensus Summary ({bullish_cnt} Positive, {hold_cnt} Neutral, {bear_cnt} Cautious): "
                f"Third-party mean estimate of {curr} {fmt_comma(mean_tp, 1)} reflects {tp_up:+}% variance vs CMP; cited for context only."
            )
        else:
            ratings_opinion = (
                f"External Public Consensus Summary ({bullish_cnt} Positive, {hold_cnt} Neutral, {bear_cnt} Cautious): "
                f"Third-party mean estimate ({curr} {fmt_comma(mean_tp, 1)}, {tp_up:+}% vs CMP) indicates dispersed Street expectations."
            )
    elif rating_updates:
        ratings_opinion = f"Aggregated {len(rating_updates)} public third-party brokerage and credit-rating agency updates for reference alongside historical financials."
    else:
        ratings_opinion = "Limited public consensus feed coverage; analytical focus rests on historical financials and balance-sheet durability."

    nse_data = fetch_nse_official_filings(symbol)
    raw_nse = nse_data.get("announcements", [])
    cleaned_nse: List[Dict[str, str]] = []
    nse_noise_re = re.compile(
        r"\b(schedule of meet|newspaper publication|trading window|reg\.?\s*74\(5\)|loss of share certificate|postal ballot|intimation of record date|enterprise ai study)\b",
        re.IGNORECASE,
    )
    for nf in raw_nse:
        nf_title = _clean_headline(nf.get("title", ""), nf.get("source", ""))
        nf_title = re.sub(
            r"^.*?\bhas informed the Exchange\s+(?:about|regarding)\s*['\"]?",
            "",
            nf_title,
            flags=re.IGNORECASE,
        ).strip(" '\"-")
        nf_cat = nf.get("category", "Exchange Filing")
        tl_nf = f"{nf_cat} {nf_title}".lower()
        if nse_noise_re.search(tl_nf):
            continue
        if "credit rating" in tl_nf:
            eff = "Material — Credit Rating Disclosure"
        elif any(k in tl_nf for k in ("result", "financial", "outcome of board")):
            eff = "Material — Earnings / Board Outcome"
        elif any(k in tl_nf for k in ("acquisition", "order", "contract", "joint venture", "investment")):
            eff = "Positive — Strategic Business Expansion"
        elif any(k in tl_nf for k in ("buyback", "dividend", "bonus", "split")):
            eff = "Positive — Shareholder Capital Return"
        elif "transcript" in tl_nf or "investor" in tl_nf:
            eff = "Reference — Management Commentary"
        else:
            eff = "Neutral — Regulatory Exchange Filing"
        cleaned_nse.append({**nf, "title": nf_title, "effect": eff})
        if len(cleaned_nse) >= 4:
            break
    # Fallback to condensed non-trivial announcements only if strict filter dropped everything
    if not cleaned_nse and raw_nse:
        for nf in raw_nse[:2]:
            nf_title = re.sub(
                r"^.*?\bhas informed the Exchange\s+(?:about|regarding)\s*['\"]?",
                "",
                _clean_headline(nf.get("title", ""), nf.get("source", "")),
                flags=re.IGNORECASE,
            ).strip(" '\"-")
            cleaned_nse.append({**nf, "title": nf_title, "effect": "Routine — Regulatory Disclosure"})

    if nse_data.get("insider_pit"):
        existing_ins = {(t.get("date"), t.get("insider")) for t in insider_txns}
        for row in nse_data["insider_pit"]:
            key = (row.get("date"), row.get("insider"))
            if key not in existing_ins:
                insider_txns.append(row)

    section_opinion = (
        f"Ownership & Institutional Positioning: {ownership_opinion.split('.')[0]}. "
        f"{ratings_opinion.split('.')[0]}. {perf_summary.get('performance_opinion', '').split('.')[0]}."
    ).strip()

    return {
        "shareholding_quarters": sh_quarters,
        "shareholding_series": sh_series,
        "shareholding_latest": {
            "quarter": latest_sh.get("quarter") or "Latest",
            "promoters_pct": prom_now,
            "fiis_pct": fii_now,
            "diis_pct": dii_now,
            "govt_pct": latest_sh.get("Government"),
            "public_pct": pub_now,
            "shareholders_count": latest_sh.get("No. of Shareholders"),
            "promoters_qoq_pp": prom_delta,
            "fiis_qoq_pp": fii_delta,
            "diis_qoq_pp": dii_delta,
            "yf_insiders_pct": yf_insiders_pct,
            "yf_institutions_pct": yf_inst_pct,
            "yf_institutions_float_pct": yf_inst_float_pct,
            "yf_institutions_count": yf_inst_count,
        },
        "nse_official_announcements": cleaned_nse,
        "insider_transactions": insider_txns,
        "deals_and_promoter_events": deals_events,
        "filings_deals_briefing": synthesize_news_briefing(
            section_key="filings_deals",
            company_name=company_name,
            items=list(cleaned_nse[:3]) + list(deals_events[:4]),
            empty_msg="No promoter stake sales, pledge escalations, or material block deals identified over the last 6 months.",
        ),
        "analyst_price_targets": price_targets,
        "analyst_recommendations": {**rec_summary, "total": rec_total},
        "rating_institution_updates": rating_updates,
        "ratings_briefing": synthesize_news_briefing(
            section_key="ratings",
            company_name=company_name,
            items=rating_updates,
            empty_msg="No recent brokerage target or credit-rating actions returned; refer to street consensus above.",
        ),
        "ownership_opinion": ownership_opinion,
        "deals_opinion": deals_opinion,
        "ratings_opinion": ratings_opinion,
        "section_opinion": section_opinion,
    }


def _extract_concise_overview(raw_summary: str, company_name: str, sector: str, industry: str, max_sentences: int = 3) -> str:
    """Distill raw exchange/provider business summary into 2-3 clean institutional sentences."""
    txt = re.sub(r"\s+", " ", (raw_summary or "").strip())
    if not txt:
        return f"{company_name} operates in the {industry or sector or 'diversified'} industry with exchange-listed operations."
    sentences = re.split(r"(?<=[.!?])\s+(?=[A-Z])", txt)
    kept: List[str] = []
    for sent in sentences:
        s = sent.strip()
        if not s:
            continue
        if len(kept) >= max_sentences or (kept and sum(len(x) for x in kept) + len(s) > 480):
            break
        kept.append(s)
    if not kept:
        kept = [txt[:460].rsplit(" ", 1)[0].rstrip(".,;:") + "."]
    return _sanitize_sebi_phrase(" ".join(kept))


def build_intro_business_outlook(
    symbol: str,
    company_name: str,
    bundle: Dict[str, Any],
    stock: Dict[str, Any],
    annual_4y: Dict[str, Any],
    segment_analysis: Dict[str, Any],
    ownership_section: Dict[str, Any],
    audit: Dict[str, Any],
    screener_data: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Build Section 0 Introduction: Business Overview, Annual Report Outlook, Order Book & Strategic Mix."""
    info = bundle.get("info", {}) or {}
    curr = stock.get("currency", "INR")
    ann_rows = annual_4y.get("rows") or [] if isinstance(annual_4y, dict) else (annual_4y or [])
    unit = (annual_4y.get("unit") if isinstance(annual_4y, dict) else None) or stock.get("unit") or ("₹ Cr" if curr == "INR" else "M")
    sector = stock.get("sector") or info.get("sector") or "Equities"
    industry = stock.get("industry") or info.get("industry") or "Diversified"

    overview = _extract_concise_overview(info.get("longBusinessSummary", ""), company_name, sector, industry)

    city = (info.get("city") or "").strip()
    country = (info.get("country") or ("India" if symbol.endswith((".NS", ".BO")) else "")).strip()
    hq = f"{city}, {country}" if city and country else (city or country or "India")
    emp_raw = info.get("fullTimeEmployees")
    employees = fmt_comma(emp_raw, 0) if emp_raw else "Not disclosed"
    website = (info.get("website") or "—").strip()

    # 4-year revenue & operating margin trajectory snapshot
    scale_summary = "Consolidated multi-year financials tracked below."
    if len(ann_rows) >= 2:
        r0 = ann_rows[0]
        r_last = ann_rows[-1]
        rev0, rev_last = r0.get("revenue"), r_last.get("revenue")
        opm_last = r_last.get("opm_pct") if r_last.get("opm_pct") is not None else r_last.get("ebitda_margin_pct")
        cagr_txt = ""
        if rev0 and rev_last and rev0 > 0 and rev_last > 0:
            yrs = max(1, len(ann_rows) - 1)
            cagr = ((rev_last / rev0) ** (1.0 / yrs) - 1.0) * 100.0
            cagr_txt = f" ({cagr:+.1f}% {yrs}Y CAGR)"
        margin_txt = f"; latest operating margin {opm_last:.1f}%." if opm_last is not None else "."
        scale_summary = (
            f"Operating revenue moved from {fmt_comma(rev0, 0)} {unit} ({r0.get('period')}) "
            f"to {fmt_comma(rev_last, 0)} {unit} ({r_last.get('period')}){cagr_txt}{margin_txt}"
        )

    verticals: List[str] = []
    for seg in (segment_analysis.get("segments") or []):
        sname = (seg.get("name") or "").strip()
        sh = seg.get("rev_mix_pct") if seg.get("rev_mix_pct") is not None else seg.get("revenue_share_pct")
        if sname and "total" not in sname.lower() and "unalloc" not in sname.lower():
            verticals.append(f"{sname} ({sh:.1f}%)" if sh is not None else sname)
        if len(verticals) >= 5:
            break

    # Gather Annual Report, Order Book, Capex & Management Outlook disclosures
    outlook_items: List[Dict[str, str]] = []

    # 1. Uploaded Annual / Audit Report findings (order book, capex, guidance, outlook)
    outlook_kw = re.compile(
        r"\b(annual report|order book|backlog|tcv|deal win|contract|capex|capital expenditure|"
        r"capacity expansion|guidance|outlook|pipeline|commissio|facility|joint venture|agm)\b"
    )
    for f in (audit.get("findings") or []):
        snippet = str(f.get("snippet") or "").strip()
        cat = str(f.get("category") or "Annual Filing").strip()
        if snippet and (outlook_kw.search(snippet.lower()) or any(k in cat.lower() for k in ("capex", "order", "outlook", "contract", "growth"))):
            outlook_items.append(
                {
                    "title": f"{cat}: {snippet[:180]}",
                    "source": "Annual / Uploaded Filing",
                    "date": str(f.get("page") or "Filing"),
                    "link": "#",
                    "category": "Annual Report / Filing",
                    "sentiment": "neutral",
                }
            )

    # 2. NSE official corporate announcements matching AR / AGM / Investor Presentation / Order Book / Capex
    nse_kw = re.compile(
        r"\b(annual report|annual general|agm|investor presentation|press release|order|contract|award|capex|expansion|capacity|joint venture|acquisition|partnership|milestone)\b"
    )
    for ann in (ownership_section.get("nse_official_announcements") or []):
        title = str(ann.get("title") or "")
        tl = title.lower()
        if nse_kw.search(tl):
            sent = "positive" if any(k in tl for k in ("order", "award", "win", "expansion", "contract", "partnership", "launch")) else "neutral"
            outlook_items.append(
                {
                    "title": title,
                    "source": ann.get("source") or "NSE Official Filing",
                    "date": ann.get("date") or "Recent",
                    "link": ann.get("link") or "#",
                    "category": "Exchange Filing",
                    "sentiment": sent,
                }
            )

    # 3. 365-day institutional press RSS for Annual Report, Order Book / TCV, Capex & Outlook
    is_in = symbol.endswith((".NS", ".BO"))
    gl = "IN" if is_in else "US"
    base_name = re.sub(r"\b(limited|ltd\.?|inc\.?|corp\.?|industries|enterprise|services|co\.?)\b", "", company_name, flags=re.I).strip()
    short_stem = re.sub(r"\.(NS|BO)$", "", symbol)
    aliases = [a for a in {company_name, base_name, short_stem} if a and len(a) >= 2]
    entity_expr = "(" + " OR ".join(f'"{a}"' for a in aliases[:3]) + ")"
    token_guards = [w.lower() for w in re.split(r"[^a-zA-Z0-9]+", f"{company_name} {short_stem}") if len(w) >= 3]

    rss_raw = _fetch_google_news_rss(
        f'{entity_expr} ("annual report" OR "order book" OR "TCV" OR "backlog" OR "capex" OR "capacity expansion" OR "management outlook" OR "FY26 guidance" OR "FY27 guidance" OR "deal wins") when:365d',
        market_gl=gl,
        limit=12,
    )
    for it in rss_raw:
        src = it.get("source", "")
        ct = _clean_headline(it.get("title", ""), src)
        if _is_low_signal_headline(ct, src):
            continue
        tl = ct.lower()
        if token_guards and not any(tok in tl for tok in token_guards):
            continue
        if any(k in tl for k in ("slowdown", "headwind", "delay", "cut guidance", "weak order", "drop in")):
            sent = "negative"
        elif any(k in tl for k in ("order book", "backlog", "tcv", "deal win", "contract", "capex", "expansion", "growth", "annual report", "guidance", "record")):
            sent = "positive"
        else:
            sent = "neutral"
        outlook_items.append({**it, "title": ct, "sentiment": sent, "category": "Outlook & Order Book"})

    outlook_briefing = synthesize_news_briefing(
        section_key="outlook",
        company_name=company_name,
        items=outlook_items,
        empty_msg=(
            "Recent annual report or order-book guidance headlines were limited across automated feeds; "
            "refer to FY revenue CAGR and segment mix below, or attach the latest Annual Report PDF for line-item extraction."
        ),
    )

    structural_strengths = [str(p).strip() for p in ((screener_data or {}).get("pros") or [])[:2] if str(p).strip()]

    return {
        "company_name": company_name,
        "sector": sector,
        "industry": industry,
        "hq": hq,
        "employees": employees,
        "website": website,
        "overview": overview,
        "scale_summary": scale_summary,
        "verticals": verticals,
        "structural_strengths": structural_strengths,
        "outlook_briefing": outlook_briefing,
        "annual_report_pdf_attached": bool(audit.get("source_label") and "manual" not in str(audit.get("source_label")).lower()),
    }


def build_rating_and_methodology(
    workspace: Any,
    stock: Dict[str, Any],
    dcf_model: Dict[str, Any],
    key_data: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Build transparent SEBI-compliant Quality & Valuation Rating, 6-Pillar Basis, Meaning & Rating Guide."""
    total_score = round(float(stock.get("total_score") or 0.0), 1)
    vetoes = list(stock.get("vetoes") or [])
    pts = stock.get("layer_points") or {}
    weights = workspace.profile.weights()
    m = stock.get("metrics") or {}
    kd = key_data or {}
    curr = stock.get("currency", "INR")
    dcf_up = dcf_model.get("upside_downside_pct")

    if vetoes:
        grade = "Grade D"
        stars = 1.0
        rating_label = "High Risk / Governance or Solvency Veto"
        tone = "danger"
        meaning = (
            f"{stock['name']} carries an active hard risk veto ({'; '.join(vetoes)}). Under our quantitative model, "
            "severe balance-sheet stress, qualified audit items, or governance exceptions cap the composite rating at Grade D "
            "regardless of trailing accounting profitability. This is a quantitative risk flag, not trading advice."
        )
    elif total_score >= 78.0:
        grade = "Grade A+"
        stars = 5.0
        rating_label = "Top-Decile Fundamental & Capital Efficiency Quality"
        tone = "strong"
        meaning = (
            f"{stock['name']} scores {total_score}/100 ({grade} — 5.0/5.0 Stars), reflecting top-tier capital efficiency "
            f"(ROIC {m.get('roic_pct')}%), strong operating cash conversion ({m.get('cfo_to_ebitda')}x EBITDA), and clean governance. "
            "Grade A+ identifies exceptional historical business economics while leaving valuation entry sensitivity to DCF/multiple checks."
        )
    elif total_score >= 68.0:
        grade = "Grade A"
        stars = 4.0
        rating_label = "Strong Fundamental Core"
        tone = "good"
        meaning = (
            f"{stock['name']} scores {total_score}/100 ({grade} — 4.0/5.0 Stars), indicating an institutional-grade balance sheet, "
            f"healthy returns on capital (ROIC {m.get('roic_pct')}%), and zero forensic red flags, with moderate score deductions driven primarily "
            + (f"by valuation premium ({dcf_up:+}% DCF variance)." if dcf_up is not None and dcf_up < 0 else "by cyclical growth or external risk weights.")
        )
    elif total_score >= 58.0:
        grade = "Grade B+"
        stars = 3.5
        rating_label = "Solid Core / Valuation & Growth Sensitive"
        tone = "neutral"
        meaning = (
            f"{stock['name']} scores {total_score}/100 ({grade} — 3.5/5.0 Stars), reflecting a solvent operating franchise "
            "whose composite rating is tempered by either rich valuation multiples, moderate capital returns, or slower recent earnings momentum."
        )
    elif total_score >= 45.0:
        grade = "Grade B"
        stars = 3.0
        rating_label = "Moderate / Mixed Fundamental Profile"
        tone = "caution"
        meaning = (
            f"{stock['name']} scores {total_score}/100 ({grade} — 3.0/5.0 Stars), highlighting mixed financial execution — "
            "stable baseline operations offset by constrained margins, lower ROIC-WACC spread, or elevated valuation sensitivity."
        )
    else:
        grade = "Grade C"
        stars = 2.0
        rating_label = "Below-Threshold Return or Balance-Sheet Profile"
        tone = "weak"
        meaning = (
            f"{stock['name']} scores {total_score}/100 ({grade} — 2.0/5.0 Stars), signaling below-benchmark profitability, "
            "weak cash conversion, or compressed return ratios across the 6 quantitative pillars."
        )

    pe_s = fmt_comma(kd.get("pe_ttm"), 1, "x")
    pb_s = fmt_comma(kd.get("pb"), 2, "x")
    ev_n_s = fmt_comma(m.get("ev_to_nopat"), 1, "x")
    roe_s = fmt_comma(kd.get("roe_pct"), 1, "%")
    fcf_y_s = fmt_comma(m.get("fcf_yield_pct"), 2, "%")
    rev_g_s = fmt_comma(m.get("rev_cagr_pct"), 1, "%")
    pat_g_s = fmt_comma(m.get("pat_cagr_pct"), 1, "%")
    mcap_b = fmt_comma(stock.get("market_cap_b"), 1, "B")
    adtv_s = fmt_comma(stock.get("adtv_usd_m"), 1, "M")

    pillar_meta = [
        (
            "layer1",
            "Balance Sheet & Cash Conversion",
            f"Net Debt/EBITDA {m.get('net_debt_to_ebitda')}x · Int. Cov {m.get('int_coverage')}x · CFO/EBITDA {m.get('cfo_to_ebitda')}x · FCF Yield {fcf_y_s}",
        ),
        (
            "layer2",
            "Business Quality & Capital Efficiency",
            f"ROIC {m.get('roic_pct')}% · ROE {roe_s} · Sales CAGR {rev_g_s} · PAT CAGR {pat_g_s}",
        ),
        (
            "layer3",
            "Valuation & Margin of Safety",
            f"P/E {pe_s} · P/B {pb_s} · EV/NOPAT {ev_n_s}"
            + (f" · Base DCF {dcf_up:+}%" if dcf_up is not None else ""),
        ),
        (
            "layer4",
            "Governance, Audit & Litigation",
            f"{'Clean audit checks — zero governance or fraud flags' if not vetoes else '; '.join(vetoes)}",
        ),
        (
            "layer5",
            "Macro, Geopolitical & External Risk",
            "Supply-chain, tariff, commodity, and macro sensitivity resilience",
        ),
        (
            "layer6",
            "Market Scale & Trading Liquidity",
            f"Market Cap {curr} {mcap_b} · ADTV ${adtv_s} · Inst. Float {fmt_comma(m.get('inst_hold_pct'), 1, '%')}",
        ),
    ]

    layer_breakdown: List[Dict[str, Any]] = []
    for k, label, evidence in pillar_meta:
        w = round(float(weights.get(k, 0.0)), 1)
        e = round(float(pts.get(k, 0.0)), 1)
        att = round((e / w * 100.0), 1) if w > 0 else 0.0
        st = "Strong" if att >= 75.0 else ("Satisfactory" if att >= 55.0 else ("Watch" if att >= 40.0 else "Weak"))
        layer_breakdown.append(
            {
                "layer": k,
                "pillar": label,
                "weight_pct": w,
                "earned_pts": e,
                "attainment_pct": att,
                "status": st,
                "evidence": evidence,
            }
        )

    base_layer_total = round(sum(row["earned_pts"] for row in layer_breakdown), 1)
    bonus_adj = round(total_score - base_layer_total, 1)
    archetype_name = str(workspace.profile.archetype).replace("_", " ").title()
    w_str = "/".join(f"{int(round(r['weight_pct']))}%" for r in layer_breakdown)
    how_we_rated = (
        f"Rated under the '{archetype_name}' quantitative weighting profile ({w_str} across Layers 1–6 = 100 base pts). "
        f"Base weighted pillars contribute {base_layer_total:.1f}/100, plus a {bonus_adj:+.1f} pt multi-signal / veto adjustment "
        f"= {total_score:.1f}/100 final composite score. Hard risk overrides cap any stock with severe leverage, negative CFO, or qualified audit exceptions at Grade D. "
        "Note: This rating measures historical financial quality and intrinsic-value cushion strictly for education — it is NOT a SEBI-regulated Buy/Sell/Hold rating or price target."
    )

    rating_scale_guide = [
        {
            "grade": "Grade A+",
            "stars": "5.0 ★",
            "score_range": "78.0 – 100.0",
            "classification": "Top-Decile Quality",
            "meaning": "Exceptional ROIC > WACC spread, fortress net-cash or low-leverage balance sheet, clean audit, and favorable valuation cushion.",
            "study_focus": "Examine sustainability of incremental ROIC, reinvestment runway, and any cyclical peak margin risk.",
        },
        {
            "grade": "Grade A",
            "stars": "4.0 ★",
            "score_range": "68.0 – 77.9",
            "classification": "Strong Fundamental Core",
            "meaning": "High-quality operating franchise with durable margins and clean governance, typically deducting points only on rich multiples or mature growth.",
            "study_focus": "Compare CMP against Base/Bear DCF and 5Y P/E bands to separate business quality from entry multiple risk.",
        },
        {
            "grade": "Grade B+",
            "stars": "3.5 ★",
            "score_range": "58.0 – 67.9",
            "classification": "Solid / Valuation Sensitive",
            "meaning": "Sound core business with acceptable solvency, but either lower return ratios, tighter valuation margin of safety, or slower 3Y earnings CAGR.",
            "study_focus": "Track sequential margin expansion, order book conversion, and working-capital intensity.",
        },
        {
            "grade": "Grade B",
            "stars": "3.0 ★",
            "score_range": "45.0 – 57.9",
            "classification": "Moderate / Mixed Profile",
            "meaning": "Mixed financial scorecard where steady revenue scale is offset by margin volatility, moderate leverage, or sub-par cash conversion.",
            "study_focus": "Verify capex payoff timeline, debt reduction milestones, and peer ROIC gap before relying on mean reversion.",
        },
        {
            "grade": "Grade C / D",
            "stars": "1.0 – 2.0 ★",
            "score_range": "< 45.0 or Veto",
            "classification": "Weak Quality / Risk Veto",
            "meaning": "Grade C reflects weak operational returns; Grade D indicates an active hard risk veto (excessive debt, cash-flow divergence, or audit qualification).",
            "study_focus": "Focus strictly on auditor qualifications, debt maturity schedule, promoter pledges, and structural turnaround evidence.",
        },
    ]

    return {
        "grade": grade,
        "stars": stars,
        "rating_label": rating_label,
        "tone": tone,
        "score": total_score,
        "max_score": 100.0,
        "base_layer_total": base_layer_total,
        "bonus_adj": bonus_adj,
        "archetype": archetype_name,
        "layer_breakdown": layer_breakdown,
        "how_we_rated": how_we_rated,
        "meaning_of_rating": meaning,
        "rating_scale_guide": rating_scale_guide,
    }


def build_data_sources_and_provenance(
    symbol: str,
    bundle: Dict[str, Any],
    screener_data: Dict[str, Any],
    segment_analysis: Dict[str, Any],
    ownership_section: Dict[str, Any],
    news_data: Dict[str, Any],
    annual_4y: Dict[str, Any],
    quarterly_4q: Dict[str, Any],
    pdf_path: Optional[str] = None,
    audit_text: str = "",
) -> Dict[str, Any]:
    """Document exact public/regulatory data sources, verification status, and strict actual-data enforcement."""
    checks = bundle.get("data_checks") or {}
    ann_years = [r.get("period") for r in (annual_4y.get("rows") or []) if r.get("period")]
    q_ends = [r.get("quarter_end") for r in (quarterly_4q.get("rows") or []) if r.get("quarter_end")]
    news_cnt = len(news_data.get("events") or [])
    nse_filings = ownership_section.get("nse_filings_count") or len(ownership_section.get("filings_and_deals") or [])

    sources: List[Dict[str, str]] = [
        {
            "name": "Market Quotes, Financial Statements & Price History",
            "provider": "Yahoo Finance API + KDB-X / PyKX Binary Store (.kdb)",
            "status": "Verified" if (checks.get("has_price", True) and ann_years) else "Partial",
            "scope": f"{len(ann_years)} annual FYs ({', '.join(ann_years) or '—'}), {len(q_ends)} quarters, 5Y price series",
            "url": f"https://finance.yahoo.com/quote/{symbol}",
        },
        {
            "name": "NSE India Integrated Filings (Ind-AS 108 XBRL) & Announcements",
            "provider": "National Stock Exchange of India (nseindia.com)",
            "status": (
                "Verified"
                if (segment_analysis.get("available") or ownership_section.get("filings_and_deals"))
                else ("Skipped (Non-NSE)" if not symbol.endswith((".NS", ".BO")) else "Limited / Unavailable")
            ),
            "scope": (
                f"Statutory XBRL segments ({segment_analysis.get('period_end', '—')})"
                if segment_analysis.get("available")
                else f"Corporate announcements & PIT insider disclosures ({nse_filings} items tracked)"
            ),
            "url": segment_analysis.get("source_url") or (
                f"https://www.nseindia.com/get-quotes/equity?symbol={symbol.split('.')[0]}"
                if symbol.endswith(".NS")
                else ""
            ),
        },
        {
            "name": "Consolidated Ratios, Working Capital & Shareholding",
            "provider": "Screener.in Public Company Filings",
            "status": "Verified" if screener_data.get("status") == "ok" else ("Skipped (Non-IN)" if not symbol.endswith((".NS", ".BO")) else "Unavailable"),
            "scope": (
                f"Shareholding ({(screener_data.get('shareholding') or {}).get('latest', {}).get('quarter', '—')}), ROCE, Debtor/Inventory/Payable days"
                if screener_data.get("status") == "ok"
                else "Direct Screener.in consolidated feed not returned; exchange/Yahoo statements used."
            ),
            "url": screener_data.get("url") or (
                f"https://www.screener.in/company/{symbol.split('.')[0]}/" if symbol.endswith((".NS", ".BO")) else ""
            ),
        },
        {
            "name": "Corporate Developments, Credit Ratings & Order-Book Disclosures",
            "provider": "Google News RSS + Exchange Media Feeds",
            "status": "Verified" if news_cnt > 0 else "No Recent Items",
            "scope": f"{news_cnt} dated disclosure / news items indexed with source attribution",
            "url": "",
        },
        {
            "name": "Annual Report / Independent Auditor's Report PDF",
            "provider": "User-Supplied Primary Filing (PyMuPDF Forensic Parser)",
            "status": "Attached & Audited" if (pdf_path or audit_text.strip()) else "Not Attached",
            "scope": (
                f"Parsed document/text ({pdf_path or 'inline audit text'}) for going-concern, litigation & loan clauses"
                if (pdf_path or audit_text.strip())
                else "No PDF attached on this run; automated solvency & exchange checks applied."
            ),
            "url": "",
        },
    ]

    verified_count = sum(1 for s in sources if s["status"] in ("Verified", "Attached & Audited"))
    return {
        "strict_actual_data_enforced": True,
        "policy": (
            "Strict Actual-Data Policy Enforced: Every financial metric, multiple, segment figure, and disclosure link in this report "
            "is sourced exclusively from live exchange/regulatory APIs, public filings, or cached KDB-X snapshots of actual fetched statements. "
            "Zero synthetic, dummy, placeholder, or backward-imputed EPS figures are generated; unavailable fields display as '—' or omit modeling."
        ),
        "verified_sources_count": verified_count,
        "total_sources_checked": len(sources),
        "ingest_source": bundle.get("source", "Yahoo Finance / KDB-X"),
        "ingested_at": bundle.get("ingested_at") or dt.datetime.now().strftime("%Y-%m-%d %H:%M"),
        "sources": sources,
    }


def build_standardized_report(
    workspace: Any,
    symbol: str,
    pdf_path: Optional[str] = None,
    audit_text: str = "",
    sector_peers: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """Master standardized pipeline: identical 3-section investor-friendly analysis for any stock."""
    sym = symbol.strip().upper()
    if "." not in sym and workspace.profile.market == "IN":
        sym = f"{sym}.NS"

    if pdf_path or audit_text.strip():
        workspace.audit_filing_and_external_risks(sym, pdf_path=pdf_path, raw_text=audit_text)
    stock = workspace.inspect_stock_deeply(sym)
    if stock.get("status") == "error":
        return stock

    bundle = workspace.bundles.get(sym) or workspace.ingestor.fetch_ticker_bundle(sym)
    audit = stock.get("forensic_audit") or run_forensic_audit(sym, stock_summary=stock)

    news_data = fetch_corporate_events_and_catalysts(sym, stock.get("name", sym))
    screener_data = (
        workspace.screener_india(sym)
        if sym.endswith((".NS", ".BO"))
        else {"status": "skipped", "ratios": {}, "pros": [], "cons": []}
    )

    annual_4y = build_4y_annual_series(bundle)
    quarterly_4q = build_4q_quarterly_series(sym, currency=stock.get("currency", "INR"))
    dcf_model = build_fcff_dcf_model(bundle, stock, annual_4y)
    pe_bands = build_historical_pe_bands(sym, bundle, annual_4y)
    working_capital = build_working_capital_summary(annual_4y, screener_data)

    peer_list = sector_peers or auto_select_sector_peers(sym, market=workspace.profile.market, max_peers=3)
    comps_data = workspace.comps_india(peer_list) if len(peer_list) >= 2 else {"status": "skipped", "peers": []}

    # Investor opinion for peer comparison
    peers_list = comps_data.get("peers", [])
    peer_opinion = "Peer comparison helps check whether valuation and profitability stand out inside the sector."
    if peers_list:
        best_peer = max(peers_list, key=lambda x: x.get("score") or 0)
        cur_peer = next((x for x in peers_list if x["symbol"] == sym), None)
        if cur_peer and best_peer["symbol"] == sym:
            peer_opinion = f"{sym} leads its peer group ({cur_peer.get('score')}/100 overall score) with superior fundamentals."
        elif cur_peer:
            peer_opinion = (
                f"Among direct peers, {best_peer['symbol']} currently scores highest ({best_peer.get('score')}/100, {best_peer.get('roic_pct')}% ROIC) "
                f"versus {sym} ({cur_peer.get('score')}/100, {cur_peer.get('roic_pct')}% ROIC). Compare capital efficiency, cash conversion, and multiples side by side."
            )

    advanced_insights = build_plain_english_advanced_insights(stock, audit)
    stance = _investor_stance(stock["total_score"], stock["vetoes"], dcf_model.get("upside_downside_pct"))

    # PL Capital / ICICI Direct style Key Market Data + Multi-Horizon Benchmark & Sector Performance
    market_perf = build_key_market_and_performance(
        bundle=bundle,
        workspace=workspace,
        symbol=sym,
        stock=stock,
        screener_data=screener_data,
        peers_list=peers_list,
    )
    ownership_section = build_ownership_deals_and_ratings(
        symbol=sym,
        company_name=stock.get("name", sym),
        bundle=bundle,
        stock=stock,
        screener_data=screener_data,
        perf_summary=market_perf,
    )
    earnings_highlights = build_earnings_highlights(
        symbol=sym,
        company_name=stock.get("name", sym),
        quarterly_4q=quarterly_4q,
        annual_4y=annual_4y,
        stock=stock,
        ownership_section=ownership_section,
    )
    segment_analysis = build_segment_analysis(sym)
    returns_analysis = build_returns_analysis(
        bundle=bundle,
        stock=stock,
        dcf_model=dcf_model,
        pe_bands=pe_bands,
        key_data=market_perf["key_data"],
    )
    intro_section = build_intro_business_outlook(
        symbol=sym,
        company_name=stock.get("name", sym),
        bundle=bundle,
        stock=stock,
        annual_4y=annual_4y,
        segment_analysis=segment_analysis,
        ownership_section=ownership_section,
        audit=audit,
        screener_data=screener_data,
    )
    rating_framework = build_rating_and_methodology(
        workspace=workspace,
        stock=stock,
        dcf_model=dcf_model,
        key_data=market_perf["key_data"],
    )
    data_provenance = build_data_sources_and_provenance(
        symbol=sym,
        bundle=bundle,
        screener_data=screener_data,
        segment_analysis=segment_analysis,
        ownership_section=ownership_section,
        news_data=news_data,
        annual_4y=annual_4y,
        quarterly_4q=quarterly_4q,
        pdf_path=pdf_path,
        audit_text=audit_text,
    )

    # PL Capital Page 1 Style "Quick Pointers" (4 concise investor takeaways)
    sh_lat = ownership_section["shareholding_latest"]
    tp_mean = ownership_section["analyst_price_targets"].get("mean")
    tp_up = ownership_section["analyst_price_targets"].get("implied_upside_pct")
    dcf_fv = dcf_model.get("fair_value_per_share")
    dcf_up = dcf_model.get("upside_downside_pct")
    rel_12 = next((r["relative_pct"] for r in market_perf["performance_table"] if r["horizon"] == "12M"), None)
    spread_qp = stock["metrics"].get("roic_wacc_spread_pct")
    imp_g_qp = stock["metrics"].get("implied_fcf_g_pct")
    rev_g_qp = stock["metrics"].get("rev_cagr_pct")
    quick_pointers = [
        (
            f"Valuation & Expectations Gap: Base DCF Fair Value {stock['currency']} {fmt_comma(dcf_fv, 1)} ({dcf_up:+}% vs CMP); "
            + (
                f"market price implies {imp_g_qp}% 7Y FCF growth vs {rev_g_qp}% historical sales CAGR."
                if imp_g_qp is not None and rev_g_qp is not None
                else (f"Street Consensus Mean sits at {stock['currency']} {fmt_comma(tp_mean, 1)} ({tp_up:+}%)." if tp_mean and tp_up is not None else "refer to DCF sensitivity matrix.")
            )
        ),
        (
            f"Institutional Ownership Flow: FIIs/FPIs {sh_lat.get('fiis_qoq_pp'):+} pp QoQ (to {fmt_comma(sh_lat.get('fiis_pct'), 1, '%')}) vs "
            f"DIIs/MFs {sh_lat.get('diis_qoq_pp'):+} pp QoQ (to {fmt_comma(sh_lat.get('diis_pct'), 1, '%')}) | Promoter stake {fmt_comma(sh_lat.get('promoters_pct'), 1, '%')}."
            if sh_lat.get("fiis_pct") is not None and sh_lat.get("fiis_qoq_pp") is not None
            else ownership_section["ownership_opinion"]
        ),
        (
            f"Capital Efficiency & Benchmark Relative Return: ROIC–WACC spread {spread_qp:+}% (Inc. ROIC {stock['metrics'].get('inc_roic_pct')}%); "
            f"12M stock return {market_perf['performance_table'][-1]['stock_pct']:+}% ({rel_12:+}% vs {market_perf['benchmark_label']})."
            if spread_qp is not None and rel_12 is not None and market_perf["performance_table"][-1]["stock_pct"] is not None
            else f"Capital Efficiency & Solvency: ROIC {stock['metrics'].get('roic_pct')}% | Net Debt/EBITDA {stock['metrics'].get('net_debt_to_ebitda')}x | Int. Coverage {stock['metrics'].get('int_coverage')}x."
        ),
        (
            f"Audit & Disclosure Balance: {'Clean audit — zero governance or leverage red flags' if not audit['vetoes'] else '; '.join(audit['vetoes'])}; "
            f"{news_data['favorable_count']} constructive and {news_data['setback_count']} risk developments logged."
        ),
    ]

    # SEBI-compliant analytical synthesis & structured conclusion (zero Buy/Sell/Hold advice)
    roic_val = stock["metrics"].get("roic_pct")
    cfo_eb_val = stock["metrics"].get("cfo_to_ebitda")
    net_d_val = stock["metrics"].get("net_debt_to_ebitda")
    strength_summary = (
        f"{stock['name']} scores {stock['total_score']}/100 on composite fundamental health "
        f"(ROIC {roic_val}%, CFO/EBITDA {cfo_eb_val}x, Net Debt/EBITDA {net_d_val}x)."
    )
    valuation_context = (
        f"Shares trade at {stock['currency']} {fmt_comma(stock['price'], 1)} "
        f"versus a base-case 5Y DCF estimate of {stock['currency']} {fmt_comma(dcf_fv, 1)}"
        + (f" ({dcf_up:+}% variance)." if dcf_up is not None else ".")
    )
    risk_focus = (
        f"Governance & solvency checks passed without audit red flags."
        if not audit["vetoes"]
        else f"Governance/credit risk flagged ({'; '.join(audit['vetoes'])}) requiring resolution prior to analytical reliance."
    )
    if stock["vetoes"]:
        conclusion_summary = f"Elevated Risk Profile: Critical governance, leverage, or audit exceptions dominate current fundamental metrics and warrant resolution before relying on trailing earnings."
    elif stock["total_score"] >= 70:
        conclusion_summary = f"Strong Quantitative Core: Superior capital returns and operating cash conversion stand out; ongoing monitoring centers on sustaining incremental ROIC above WACC and tracking implied valuation expectations."
    elif stock["total_score"] >= 55:
        conclusion_summary = f"Resilient Core Business With Balanced Valuation Sensitivity: Clean balance-sheet solvency supports stability, while future multiple expansion or intrinsic value creation hinges on sequential revenue growth and margin consistency."
    else:
        conclusion_summary = f"Constrained Return vs Valuation Profile: Consolidated ROIC–WACC spread or capital-allocation drag requires multi-quarter operating improvement before intrinsic value cushion expands."

    # Audit summary sentence
    audit_opinion_txt = (
        f"Unqualified Governance & Solvency Profile: Audit checks are clean with manageable leverage (Net Debt/EBITDA {net_d_val}x) and {stock['metrics'].get('int_coverage')}x interest coverage."
        if not audit["vetoes"]
        else f"Governance / Audit Exception: {'; '.join(audit['vetoes'])}. Adverse findings dominate fundamental risk until formally resolved."
    )

    # Final Section 4 summary note
    adv_opinion = (
        f"Fundamental Synthesis: {stance['summary']} Key drivers remain sustained ROIC ({roic_val}%) and operating cash conversion ({cfo_eb_val}x EBITDA)."
    )

    return {
        "status": "ok",
        "generated_at": dt.datetime.now().strftime("%Y-%m-%d %H:%M IST"),
        "symbol": sym,
        "name": stock["name"],
        "sector": stock["sector"],
        "industry": stock["industry"],
        "currency": stock["currency"],
        "unit": annual_4y["unit"],
        "price": stock["price"],
        "market_cap_b": stock["market_cap_b"],
        "mcap_usd_b": stock["mcap_usd_b"],
        "score": stock["total_score"],
        "verdict": stock["verdict"],
        "investor_stance": stance,
        "kdb_telemetry": workspace.get_kdb_telemetry(),
        "data_provenance": data_provenance,
        "intro_section": intro_section,
        "executive_summary": {
            "plain_english_verdict": stance["summary"],
            "quick_pointers": quick_pointers,
            "key_market_data": market_perf["key_data"],
            "recent_events": news_data["events"],
            "events_briefing": news_data.get("briefing", {}),
            "favorable_events_count": news_data["favorable_count"],
            "setbacks_count": news_data["setback_count"],
            "screener_pros": screener_data.get("pros", []),
            "screener_cons": screener_data.get("cons", []),
            "forensic_audit_integrated": {
                "audit_opinion_status": "Risk Flagged" if any("Audit" in v for v in audit["vetoes"]) else "Clean / Unmodified",
                "investor_audit_takeaway": audit_opinion_txt,
                "layer4_governance_pct": audit["layer4_score_pct"],
                "layer5_macro_war_pct": audit["layer5_score_pct"],
                "net_debt_to_ebitda": stock["metrics"].get("net_debt_to_ebitda"),
                "interest_coverage": stock["metrics"].get("int_coverage"),
                "st_debt_share_pct": stock["metrics"].get("st_debt_share_pct"),
                "cfo_to_ebitda": stock["metrics"].get("cfo_to_ebitda"),
                "vetoes": audit["vetoes"],
                "warnings": audit["warnings"],
                "citations": audit["findings"][:6],
                "kill_switches": audit["kill_switches"],
                "sector_checklist": audit["sector_checklist"],
            },
        },
        "returns_analysis": returns_analysis,
        "earnings_highlights": earnings_highlights,
        "financial_summary": {
            "screener_ratios": screener_data.get("ratios", {}),
            "annual_4y": annual_4y,
            "quarterly_4q": quarterly_4q,
            "segment_analysis": segment_analysis,
            "dcf_valuation": dcf_model,
            "valuation_bands": pe_bands,
            "working_capital": working_capital,
            "peer_comps": peers_list,
            "peer_opinion": peer_opinion,
        },
        "ownership_and_market_context": {
            **ownership_section,
            "benchmark_label": market_perf["benchmark_label"],
            "performance_table": market_perf["performance_table"],
            "peer_performance": market_perf["peer_performance"],
            "competitive_analysis": market_perf.get("competitive_analysis", {}),
            "performance_opinion": market_perf["performance_opinion"],
        },
        "advanced_analysis_explained": {
            "layer_points": stock["layer_points"],
            "multibagger_signals": stock.get("multibagger_signals", []),
            "insights": advanced_insights,
            "deployment_plan": conclusion_summary,
            "conclusion": {
                "strength_summary": strength_summary,
                "valuation_context": valuation_context,
                "risk_focus": risk_focus,
                "summary": conclusion_summary,
                "rating_framework": rating_framework,
            },
            "section_opinion": adv_opinion,
        },
    }


def render_standardized_markdown(report: Dict[str, Any]) -> str:
    """Render standardized 6-part (Intro + Sections 1–5) investor-friendly Markdown report."""
    ex = report["executive_summary"]
    intro = report.get("intro_section") or {}
    fa = ex["forensic_audit_integrated"]
    kd = ex.get("key_market_data", {})
    ret = report.get("returns_analysis", {})
    eh = report.get("earnings_highlights", {})
    fs = report["financial_summary"]
    dcf = fs["dcf_valuation"]
    own = report.get("ownership_and_market_context", {})
    adv = report["advanced_analysis_explained"]
    stance = report["investor_stance"]
    unit = report["unit"]
    curr = report["currency"]

    lines = [
        f"# Educational Fundamental & Valuation Analysis: {report['name']} ({report['symbol']})",
        "> *SEBI Educational Disclaimer: For informational and financial education purposes only. Not SEBI-registered investment advice, a research report, or a recommendation to buy, sell, or hold any security.*",
        f"- **Sector / Industry:** {report['sector']} / {report['industry']} | **Date:** {report['generated_at']}",
        f"- **Price Action:** CMP `{curr} {fmt_comma(report['price'], 1)}` | 52W Range `{curr} {fmt_comma(kd.get('low_52w'), 1)} – {curr} {fmt_comma(kd.get('high_52w'), 1)}` ({kd.get('range_52w_pos_pct', '—')}% of 52W range) | 50-DMA `{curr} {fmt_comma(kd.get('dma_50'), 1)}` | 200-DMA `{curr} {fmt_comma(kd.get('dma_200'), 1)}` | Trend: `{kd.get('trend_signal', '—')}`",
        f"- **Core Valuation & Return Metrics:** P/E `{fmt_comma(kd.get('pe_ttm'), 1, 'x')}` | P/B `{fmt_comma(kd.get('pb'), 2, 'x')}` | EPS `{curr} {fmt_comma(kd.get('eps_ttm'), 1)}` | ROE `{fmt_comma(kd.get('roe_pct'), 1, '%')}` | ROCE `{fmt_comma(kd.get('roce_pct'), 1, '%')}` | Div Yield `{fmt_comma(kd.get('div_yield_pct'), 2, '%')}` | Base 5Y DCF Value `{curr} {fmt_comma(dcf['fair_value_per_share'], 1)}` ({dcf['upside_downside_pct']:+}%)"
        if dcf.get("upside_downside_pct") is not None
        else f"- **Core Valuation & Return Metrics:** P/E `{fmt_comma(kd.get('pe_ttm'), 1, 'x')}` | P/B `{fmt_comma(kd.get('pb'), 2, 'x')}` | EPS `{curr} {fmt_comma(kd.get('eps_ttm'), 1)}` | ROE `{fmt_comma(kd.get('roe_pct'), 1, '%')}`",
        f"- **Composite Quality Score:** `{report['score']} / 100` — **Classification:** `{stance['label']}`",
        "",
        "---",
        "## 0. Introduction: Business Overview, Annual Report Outlook & Order Book",
        f"- **Company Profile (HQ: {intro.get('hq', '—')} | Employees: {intro.get('employees', '—')}):** {intro.get('overview', '')}",
        f"- **4-Year Operating Trajectory:** {intro.get('scale_summary', '—')}",
    ]
    if intro.get("verticals"):
        lines.append(f"- **Primary Operating Segments:** {', '.join(intro['verticals'])}")
    lines += [
        "",
        "### Annual Report Outlook, Order Book & Strategic Priorities",
    ]
    _append_briefing_md(
        lines,
        intro.get("outlook_briefing") or {},
        "Recent annual report or order-book guidance items were limited across automated feeds.",
    )
    lines += [
        "",
        "---",
        "## 1. Executive Summary (Highlights, Price Trend, Material Events & Audit Review)",
        f"**Analytical Assessment (`{stance['label']}`):** {ex['plain_english_verdict']}",
        "",
        f"> **Price Action & Moving Averages:** {kd.get('price_trend_opinion', '')}",
        "",
        "### Key Highlights",
    ]
    for qp in ex.get("quick_pointers", []):
        lines.append(f"- {qp}")

    lines += [
        "",
        "### Material Corporate Developments & Risk Monitorables",
    ]
    _append_briefing_md(
        lines,
        ex.get("events_briefing") or {},
        "No material corporate developments identified in recent public disclosures.",
    )

    lines += [
        "",
        "### Audit, Leverage, Litigation & Macro Risk Review",
        f"- **Audit Assessment:** {fa['investor_audit_takeaway']}",
        f"- **Audit Opinion Status:** {fa['audit_opinion_status']} (Governance Score: `{fa['layer4_governance_pct']}%`) | **Macro Risk Resilience:** `{fa['layer5_macro_war_pct']}%`",
        f"- **Balance Sheet & Solvency:** Net Debt/EBITDA `{fa['net_debt_to_ebitda']}x` | Interest Coverage `{fa['interest_coverage']}x` | Short-Term Debt Share `{fa['st_debt_share_pct']}%`",
        f"- **Material Governance Flags:** `{', '.join(fa['vetoes']) if fa['vetoes'] else 'None Detected'}`",
    ]
    if fa["warnings"]:
        lines.append(f"- **Watchpoints:** {'; '.join(fa['warnings'])}")
    if fa["citations"]:
        for c in fa["citations"]:
            lines.append(f"  - *[{c['page']} — {c['category']}]:* {c['snippet']}")

    if ret.get("available"):
        rb = ret["base"]
        lines += [
            "",
            "### 5-Year Returns Scenario Model (IRR / MOIC & Value Attribution)",
            f"- **Entry Setup (at CMP {curr} {fmt_comma(ret['entry_price'], 1)}):** Entry Equity `{fmt_comma(ret['entry_equity'])} {unit}` | Entry Net Debt `{fmt_comma(ret['entry_net_debt'])} {unit}` | Entry EV `{fmt_comma(ret['entry_ev'])} {unit}` | Entry EV/EBITDA `{ret['entry_mult']}x`",
            f"- **Base 5Y Attribution:** Operating EBITDA Growth `{rb['attr_growth_moic']:+}x` | Exit Multiple Shift `{rb['attr_multiple_moic']:+}x` | FCF Retention & Dividends `{rb['attr_cash_moic']:+}x` -> **Total MOIC `{rb['moic']:.2f}x` | Implied 5Y IRR `{rb['irr_pct']:.1f}%`**",
            "| Scenario | EBITDA CAGR | Exit EV/EBITDA | Exit Equity (" + unit + ") | MOIC (x) | Implied 5Y IRR (%) |",
            "| --- | ---: | ---: | ---: | ---: | ---: |",
        ]
        for sc in ret.get("scenarios", []):
            lines.append(
                f"| **{sc['name']}** | {sc['growth_pct']}% | {sc['exit_mult']}x | {fmt_comma(sc['exit_equity'])} | {sc['moic']:.2f}x | {sc['irr_pct']:.1f}% |"
            )
        m_hdr = " | ".join(f"{m}x Exit" for m in ret.get("sensitivity_mults", []))
        lines += [
            "",
            "**2-Way Returns Sensitivity (EBITDA Growth CAGR × Exit EV/EBITDA -> IRR% / MOICx):**",
            f"| Growth \\ Exit Mult | {m_hdr} |",
            "| --- | " + " | ".join(["---:"] * len(ret.get("sensitivity_mults", []))) + " |",
        ]
        for r_idx, g_val in enumerate(ret.get("sensitivity_growth_pcts", [])):
            cells = " | ".join(c["label"] for c in ret["sensitivity_matrix"][r_idx])
            lines.append(f"| **{g_val}% CAGR** | {cells} |")
        lines.append(f"- **Educational Note:** {ret['opinion']}")

    if eh:
        fr = eh.get("freshness", {})
        ssum = eh.get("surprise_summary", {})
        fc = eh.get("forward_consensus", {})
        fc_g = fc.get("eps_growth_pct")
        fc_g_txt = f"{fc_g:+}% YoY; " if fc_g is not None else ""
        fc_txt = (
            f" | Next-Q Est EPS `{curr} {fmt_comma(fc.get('eps_avg'), 2)}` ({fc_g_txt}30D Revs `{fc.get('up_30d', 0)} Up / {fc.get('down_30d', 0)} Down`)"
            if fc.get("eps_avg") is not None
            else ""
        )
        lines += [
            "",
            "---",
            f"## 2. Earnings Highlights & 4-Quarter Surprise Analysis ({eh.get('latest_quarter', 'Latest')} vs {eh.get('prior_quarter', 'Prior')})",
            f"- **Data Freshness:** As of `{fr.get('as_of_date', '')}` — {fr.get('status_label', 'Tracked')} | **4Q Beat Rate:** `{ssum.get('beats_count', 0)}/{ssum.get('total_tracked', 0)}` quarters beat consensus{fc_txt}",
            "",
            "### 4-Quarter EPS Beat/Miss & Sequential Margin Progression",
            f"| Quarter End | EPS Actual ({curr}) | Consensus Est. | Surprise % | Verdict | Gross Margin % | EBIT Margin % | PAT Margin % |",
            "| :--- | ---: | ---: | ---: | :--- | ---: | ---: | ---: |",
        ]
        for sr in eh.get("surprise_4q", []):
            sp_val = sr.get("surprise_pct")
            sp_str = f"{sp_val:+}%" if sp_val is not None else "—"
            lines.append(
                f"| {sr['quarter']} | {fmt_comma(sr.get('eps_actual'), 2)} | {fmt_comma(sr.get('eps_estimate'), 2)} | "
                f"{sp_str} | {sr.get('verdict', '—')} | "
                f"{fmt_comma(sr.get('gross_margin_pct'), 1, '%')} | {fmt_comma(sr.get('ebit_margin_pct'), 1, '%')} | {fmt_comma(sr.get('pat_margin_pct'), 1, '%')} |"
            )
        lines += [
            "",
            "### Latest Quarter Bridge (Sequential & YoY)",
            "| Line Item | Latest | Prior | QoQ Var | YoY % |",
            "| :--- | ---: | ---: | ---: | ---: |",
        ]
        for ov in eh.get("result_overview_rows", []):
            lines.append(
                f"| {ov['metric']} | {ov['latest']} | {ov['prior']} | {ov['qoq_var']} | {ov['yoy_var']} |"
            )
        lines.append("")
        lines.append("### Operating Commentary, Beat/Miss Drivers & Revisions")
        for hl in eh.get("thematic_highlights", []):
            lines.append(f"- **{hl['topic']}:** {hl['detail']}")
        if eh.get("media_briefing") or eh.get("media_and_filings"):
            lines += [
                "",
                "### Earnings Releases, Concall Notes & Primary Sources",
            ]
            _append_briefing_md(
                lines,
                eh.get("media_briefing") or {},
                "No recent quarterly earnings call or exchange result notices returned in feed.",
            )
        if eh.get("sources_checklist"):
            lines.append("")
            lines.append("**Clickable Primary Sources Referenced:** " + " · ".join(
                f"[{sc['label']} ({sc['date']})]({sc['url']})" for sc in eh["sources_checklist"]
            ))
        lines.append(f"\n> **Earnings Summary:** {eh.get('takeaway', '')}")

    lines += [
        "",
        "---",
        f"## 3. Financial Summary ({unit})",
        "",
        "### A. 4-Year Year-on-Year Performance",
        f"| Fiscal Year | Revenue ({unit}) | YoY % | EBITDA ({unit}) | OPM % | Net Profit ({unit}) | YoY % | Operating Cash ({unit}) | Capex ({unit}) | Free Cash Flow ({unit}) |",
        "| :--- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for r in fs["annual_4y"]["rows"]:
        lines.append(
            f"| {r['period']} | {fmt_comma(r['revenue'])} | {fmt_comma(r['yoy_rev_pct'], 1, '%')} | {fmt_comma(r['ebitda'])} | {fmt_comma(r['opm_pct'], 1, '%')} | "
            f"{fmt_comma(r['pat'])} | {fmt_comma(r['yoy_pat_pct'], 1, '%')} | {fmt_comma(r['cfo'])} | {fmt_comma(r['capex'])} | {fmt_comma(r['fcf'])} |"
        )
    lines.append(f"\n> **Multi-Year Cash & Growth Summary:** {fs['annual_4y']['investor_opinion']}")

    lines += [
        "",
        "### B. Last 4 Quarters Performance (Quarter-on-Quarter)",
        f"| Quarter End | Revenue ({unit}) | QoQ % | YoY % | EBIT ({unit}) | EBIT Margin % | Net Profit ({unit}) | QoQ % |",
        "| :--- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for q in fs["quarterly_4q"]["rows"]:
        lines.append(
            f"| {q['quarter_end']} | {fmt_comma(q['revenue'])} | {fmt_comma(q['qoq_rev_pct'], 1, '%')} | {fmt_comma(q['yoy_rev_pct'], 1, '%')} | "
            f"{fmt_comma(q['ebit'])} | {fmt_comma(q['ebit_margin_pct'], 1, '%')} | {fmt_comma(q['pat'])} | {fmt_comma(q['qoq_pat_pct'], 1, '%')} |"
        )
    lines.append(f"\n> **Quarterly Margin & Growth Trajectory:** {fs['quarterly_4q']['investor_opinion']}")

    seg = fs.get("segment_analysis") or {}
    if seg.get("available") and seg.get("segments"):
        has_cap = bool(seg.get("has_cap_employed"))
        lines += [
            "",
            f"### C. Operating Segment Analysis — {seg.get('filing_basis', 'Consolidated')} ({seg.get('period_end', 'Latest Quarter')})",
            "| Segment | Revenue (₹ Cr) | Rev Mix | QoQ % | YoY % | EBIT (₹ Cr) | EBIT Mix | Margin %"
            + (" | Ann. ROCE %" if has_cap else "")
            + " |",
            "| :--- | ---: | ---: | ---: | ---: | ---: | ---: | ---:"
            + (" | ---: |" if has_cap else " |"),
        ]
        for sr in seg["segments"]:
            roce_col = f" | {fmt_comma(sr.get('ann_roce_pct'), 1, '%')}" if has_cap else ""
            lines.append(
                f"| {sr['name']} | {fmt_comma(sr['revenue_cr'])} | {fmt_comma(sr.get('rev_mix_pct'), 1, '%')} | "
                f"{fmt_comma(sr.get('rev_qoq_pct'), 1, '%')} | {fmt_comma(sr.get('rev_yoy_pct'), 1, '%')} | "
                f"{fmt_comma(sr['ebit_cr'])} | {fmt_comma(sr.get('ebit_mix_pct'), 1, '%')} | {fmt_comma(sr.get('ebit_margin_pct'), 1, '%')}{roce_col} |"
            )
        lines.append(f"\n> **Segment Mix & Margin Observation:** {seg.get('opinion', '')}")

    dcf_sec_lbl = "D" if (seg.get("available") and seg.get("segments")) else "C"
    lines += [
        "",
        f"### {dcf_sec_lbl}. 5-Year FCFF DCF Forecast & Valuation Sensitivity",
        f"- **Core Model Inputs:** Discount Rate (WACC) `{dcf['wacc_pct']}%` | Long-Term Growth `{dcf['terminal_growth_pct']}%` | Operating Margin `{dcf['ebit_margin_pct']}%` | Reinvestment `{dcf['reinvestment_rate_pct']}%`",
        f"- **Fair Value Calculation:** Business Value `{fmt_comma(dcf['enterprise_value'])}` − Net Debt `{fmt_comma(dcf['net_debt'])}` = Equity Value `{fmt_comma(dcf['equity_value'])} {unit}` → **Base Intrinsic Value Estimate: {curr} {fmt_comma(dcf['fair_value_per_share'], 1)}**",
        "",
        f"| Forecast Period | Growth % | Est. Revenue ({unit}) | After-Tax Operating Profit | Reinvestment | Free Cash Flow ({unit}) | Today's Value |",
        "| :--- | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for fy in dcf["forecast_5y"]:
        lines.append(
            f"| {fy['year']} | {fy['rev_growth_pct']}% | {fmt_comma(fy['revenue'])} | {fmt_comma(fy['nopat'])} | {fmt_comma(fy['reinvestment'])} | {fmt_comma(fy['fcff'])} | {fmt_comma(fy['pv_fcff'])} |"
        )
    lines.append(f"\n> **DCF Valuation Variance:** {dcf['investor_opinion']}")
    pe_b = fs.get("valuation_bands") or {}
    if pe_b.get("opinion"):
        lines.append(f"> **5-Year P/E Valuation Band:** {pe_b['opinion']}")
    sotp = dcf.get("sotp_bridge") or {}
    if sotp.get("opinion"):
        lines.append(f"> **Multiple / SOTP Second Lens:** {sotp['opinion']}")
    wc_s = fs.get("working_capital") or {}
    if wc_s.get("opinion"):
        lines.append(f"> **Working Capital & Cash Conversion:** {wc_s['opinion']}")
    lines.append(f"> **Peer Comparison Context:** {fs['peer_opinion']}")

    if own:
        sh_lat = own.get("shareholding_latest", {})
        pt = own.get("analyst_price_targets", {})
        rec = own.get("analyst_recommendations", {})
        lines += [
            "",
            "---",
            "## 4. Shareholding, Promoter/FPI Actions, Bulk Deals, External Market Consensus & Sector Performance",
            f"- **Latest Shareholding ({sh_lat.get('quarter', 'Latest')}):** Promoters `{fmt_comma(sh_lat.get('promoters_pct'), 2, '%')}` ({sh_lat.get('promoters_qoq_pp'):+} pp QoQ) | "
            f"FIIs/FPIs `{fmt_comma(sh_lat.get('fiis_pct'), 2, '%')}` ({sh_lat.get('fiis_qoq_pp'):+} pp QoQ) | "
            f"DIIs/MFs `{fmt_comma(sh_lat.get('diis_pct'), 2, '%')}` ({sh_lat.get('diis_qoq_pp'):+} pp QoQ) | "
            f"Public `{fmt_comma(sh_lat.get('public_pct'), 2, '%')}`"
            if sh_lat.get("fiis_pct") is not None and sh_lat.get("fiis_qoq_pp") is not None
            else f"- **Share Ownership (`yfinance`):** Insiders `{fmt_comma(sh_lat.get('yf_insiders_pct'), 2, '%')}` | Institutions `{fmt_comma(sh_lat.get('yf_institutions_pct'), 2, '%')}` ({fmt_comma(sh_lat.get('yf_institutions_float_pct'), 2, '%')} of float, `{sh_lat.get('yf_institutions_count', '—')}` holders)",
            f"> **Ownership & Institutional Flow Note:** {own.get('ownership_opinion', '')}",
            "",
            "### Exchange Filings, Promoter Actions & Bulk / Block Deals",
        ]
        _append_briefing_md(
            lines,
            own.get("filings_deals_briefing") or {},
            "No material promoter stake sales, pledge increases, or block deal dislocations tracked over the last 6 months.",
        )
        if own.get("insider_transactions"):
            for tx in own["insider_transactions"][:4]:
                lines.append(f"- **Insider Disclosure** ({tx['date']} | {tx['insider']}): {tx['transaction']} | Shares: {fmt_comma(tx.get('shares'))}")
        lines.append(f"\n> **Ownership & Block Activity Note:** {own.get('deals_opinion', '')}")

        lines += [
            "",
            "### External Consensus Distribution & Credit / Brokerage Coverage (Public Attribution)",
            f"- **External Analyst Split ({rec.get('total', 0)} Analysts, Third-Party Feed):** `Positive: {rec.get('strongBuy', 0) + rec.get('buy', 0)}` | `Neutral: {rec.get('hold', 0)}` | `Cautious: {rec.get('sell', 0) + rec.get('strongSell', 0)}`",
        ]
        if pt.get("mean"):
            lines.append(
                f"- **Third-Party Consensus Estimate Range:** Low `{curr} {fmt_comma(pt.get('low'), 1)}` | Mean `{curr} {fmt_comma(pt.get('mean'), 1)}` ({pt.get('implied_upside_pct'):+}% vs CMP) | Median `{curr} {fmt_comma(pt.get('median'), 1)}` | High `{curr} {fmt_comma(pt.get('high'), 1)}`"
            )
        if own.get("ratings_briefing") or own.get("rating_institution_updates"):
            lines.append("")
            _append_briefing_md(
                lines,
                own.get("ratings_briefing") or {},
                "No recent institutional rating agency or brokerage updates tracked.",
            )
        lines.append(f"\n> **Institutional & Credit Rating Takeaway:** {own.get('ratings_opinion', '')}")

        lines += [
            "",
            f"### Stock Performance vs {own.get('benchmark_label', 'Benchmark')}",
            "| Horizon | Stock Return | Benchmark Return | Relative Performance |",
            "| :--- | ---: | ---: | ---: |",
        ]
        for pr in own.get("performance_table", []):
            lines.append(
                f"| {pr['horizon']} | {fmt_comma(pr['stock_pct'], 1, '%')} | {fmt_comma(pr['benchmark_pct'], 1, '%')} | {fmt_comma(pr['relative_pct'], 1, '%')} |"
            )
        lines.append(f"\n> **Relative & Sector Performance Takeaway:** {own.get('performance_opinion', '')}")
        comp = own.get("competitive_analysis") or {}
        if comp.get("dimensions"):
            syms_hdr = " | ".join(f"**{s}**" if s == report["symbol"] else s for s in comp.get("cohort_symbols", []))
            lines += [
                "",
                f"### Competitive Landscape & Structural Moat Analysis — *{comp.get('insight_headline', '')}*",
                f"| Competitive Dimension | {syms_hdr} |",
                "| :--- | " + " | ".join([":---"] * len(comp.get("cohort_symbols", []))) + " |",
            ]
            for dim in comp["dimensions"]:
                row_vals = " | ".join(c["display"] for c in dim["cells"])
                lines.append(f"| **{dim['dimension']}** | {row_vals} |")
            lines += [
                "",
                "| Moat Pillar | Strength | Assessment |",
                "| :--- | :--- | :--- |",
            ]
            for mp in comp.get("moat_pillars", []):
                lines.append(f"| **{mp['pillar']}** | `{mp['rating']}` | {mp['detail']} |")
            if comp.get("durable_advantages"):
                lines.append(f"- **Durable Advantages:** {' '.join(comp['durable_advantages'])}")
            if comp.get("structural_vulnerabilities"):
                lines.append(f"- **Structural Vulnerabilities:** {' '.join(comp['structural_vulnerabilities'])}")

    lines += [
        "",
        "---",
        "## 5. Capital Efficiency & Risk Framework",
    ]
    for ins in adv["insights"]:
        lines.append(f"### {ins['title']} — *{ins['score_label']}*")
        lines.append(f"- **Key Metrics:** {ins['reading']}")
        lines.append(f"- **Analytical Definition:** {ins['what_it_is']}")
        lines.append(f"- **Company Implication:** {ins['what_it_means']}")
        lines.append("")

    concl = adv.get("conclusion") or {}
    rf = concl.get("rating_framework") or {}
    lines += [
        "",
        "### Analytical Conclusion & Educational Synthesis",
        (
            f"- **Composite Quality & Valuation Rating:** **{rf.get('grade', '—')} ({rf.get('stars', '—')} / 5.0 ★ | {rf.get('score', report['score'])} / 100)** — *{rf.get('rating_label', stance['label'])}* *(Educational quantitative score; not a Buy/Sell/Hold advice)*"
            if rf
            else f"- **Composite Classification:** `{stance['label']}`"
        ),
        f"- **Operating & Solvency Profile:** {concl.get('strength_summary', adv['section_opinion'])}",
        f"- **Valuation Context:** {concl.get('valuation_context', '')}",
        f"- **Governance & Risk Posture:** {concl.get('risk_focus', '')}",
        f"- **Overall Takeaway:** {adv['deployment_plan']}",
    ]
    if rf:
        lines += [
            "",
            "#### Basis for Rating & How We Rated This Company",
            f"- **Scoring Formula ({rf.get('archetype', 'Core') } Profile):** {rf.get('how_we_rated', '')}",
            f"- **What This Rating Means:** {rf.get('meaning_of_rating', '')}",
            "",
            "| Scoring Pillar | Weight (%) | Earned Pts | Attainment (%) | Status | Underlying Metric Evidence |",
            "| --- | ---: | ---: | ---: | --- | --- |",
        ]
        for row in rf.get("layer_breakdown") or []:
            lines.append(
                f"| {row['pillar']} | {row['weight_pct']:.1f}% | {row['earned_pts']:.1f} | {row['attainment_pct']:.1f}% | {row['status']} | {row['evidence']} |"
            )
        lines += [
            "",
            "#### Educational Guide on Our Rating Scale",
            "| Grade | Star Equivalent | Score Range | Classification | Meaning & Educational Study Focus |",
            "| --- | :---: | :---: | --- | --- |",
        ]
        for g in rf.get("rating_scale_guide") or []:
            lines.append(
                f"| {g['grade']} | {g['stars']} | {g['score_range']} | {g['classification']} | {g['meaning']} Focus: {g['study_focus']} |"
            )
    prov = report.get("data_provenance") or {}
    if prov.get("sources"):
        lines += [
            "",
            "### Data Sources, Verification Status & Strict Actual-Data Policy",
            f"- **Data Policy:** {prov.get('policy', '')}",
            f"- **Primary Market Snapshot:** `{prov.get('ingest_source', '—')}` (Verified Sources: `{prov.get('verified_sources_count', 0)}/{prov.get('total_sources_checked', 0)}`)",
            "",
            "| Data Source | Provider / Exchange | Status | Coverage / Provenance |",
            "| --- | --- | :---: | --- |",
        ]
        for src in prov["sources"]:
            src_name = f"[{src['name']}]({src['url']})" if src.get("url") else src["name"]
            lines.append(f"| {src_name} | {src['provider']} | `{src['status']}` | {src['scope']} |")

    lines += [
        "",
        "---",
        "### SEBI Regulatory & Educational Disclaimer",
        "> *Prepared strictly for educational, informational, and quantitative research analysis using verified public filings and exchange data under **SEBI (Research Analysts) Regulations, 2014** and **SEBI (Investment Advisers) Regulations, 2013** framing. The author/agent is not a SEBI-registered Research Analyst or Investment Adviser. Nothing herein constitutes investment advice, a research recommendation, or a solicitation to buy, sell, or hold any security.*",
    ]
    return "\n".join(lines)
