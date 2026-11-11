"""Modern Interactive Institutional Equity Research Web Dashboard Builder."""

from __future__ import annotations

import html
import json
from pathlib import Path
from typing import Any, Dict

from standardized_report import fmt_comma


def _esc(val: Any) -> str:
    return html.escape("" if val is None else str(val))


def _render_compact_table(items: list[dict[str, Any]], empty_msg: str, limit: int = 5) -> str:
    """Render news, exchange filings, block deals, and rating actions as a compact Headline | Effect | Source table."""
    if not items:
        return f'<div class="muted">{_esc(empty_msg)}</div>'
    rows = []
    for ev in items[:limit]:
        sent = ev.get("sentiment", "neutral")
        effect = str(ev.get("effect") or ev.get("category") or "Neutral")
        eff_low = effect.lower()
        if sent == "positive" or any(w in eff_low for w in ("positive", "affirmed", "buy ", "upgrade", "reduction", "accretive", "expansion")):
            pill_cls = "pill-green"
        elif sent == "negative" or any(w in eff_low for w in ("negative", "caution", "cut", "overhang", "headwind", "pressure", "setback")):
            pill_cls = "pill-red"
        elif sent == "catalyst" or any(w in eff_low for w in ("material", "strategic", "earnings", "value unlock", "track")):
            pill_cls = "pill-blue"
        else:
            pill_cls = "pill-slate"
        link = ev.get("link") or "#"
        src = ev.get("source") or "Disclosure"
        dt_str = ev.get("date") or "—"
        rows.append(
            f"""<tr>
          <td class="feed-hl"><a href="{_esc(link)}" target="_blank" rel="noopener">{_esc(ev.get('title'))}</a></td>
          <td class="feed-ef"><span class="pill {pill_cls}">{_esc(effect)}</span></td>
          <td class="feed-src"><strong>{_esc(src)}</strong><div class="sub">{_esc(dt_str)}</div></td>
        </tr>"""
        )
    return (
        '<div class="overflow-x"><table class="compact-feed-table">'
        "<thead><tr><th>Headline</th><th>Effect</th><th>Source</th></tr></thead>"
        f"<tbody>{''.join(rows)}</tbody></table></div>"
    )


def _render_summary_with_sources(
    briefing: Dict[str, Any] | None,
    empty_msg: str,
) -> str:
    """Render concise synthesized summary bullets with clickable sources directly underneath."""
    bf = briefing or {}
    bullets = bf.get("bullets") or []
    sources = bf.get("sources") or []
    if not bullets:
        return f'<div class="subcard muted">{_esc(bf.get("summary") or empty_msg)}</div>'

    mode = bf.get("mode") or "Disclosure Summary"
    cnt = int(bf.get("disclosure_count") or len(sources) or len(bullets))
    summary_line = (bf.get("summary") or "").strip()
    summary_html = (
        f'<div class="brief-lead">{_esc(summary_line)}</div>'
        if summary_line
        else ""
    )
    lis = []
    for b in bullets[:4]:
        tone = b.get("tone", "neutral")
        p_cls = "pill-green" if tone == "positive" else ("pill-red" if tone == "warning" else "pill-blue")
        imp = (b.get("impact") or "").strip()
        imp_html = (
            f'<div class="brief-impact"><strong>Investor Effect:</strong> {_esc(imp)}</div>'
            if imp
            else ""
        )
        lis.append(
            f'<li><span class="pill {p_cls}">{_esc(b.get("tag", "Takeaway"))}</span> '
            f'<div><div class="brief-text">{_esc(b.get("text", ""))}</div>{imp_html}</div></li>'
        )

    src_chips = []
    for sc in sources[:5]:
        lbl = f"{sc.get('label', 'Source')} ({sc.get('date', 'Recent')})"
        url = sc.get("url") or ""
        if url and url != "#":
            src_chips.append(
                f'<a class="source-chip" href="{_esc(url)}" target="_blank" rel="noopener">{_esc(lbl)} &nearr;</a>'
            )
        else:
            src_chips.append(f'<span class="source-chip">{_esc(lbl)}</span>')

    src_block = (
        f'<div class="source-strip"><span class="source-hdr">Sources:</span> {" ".join(src_chips)}</div>'
        if src_chips
        else ""
    )
    return (
        '<div class="subcard ai-brief-box">'
        '<div style="display:flex;justify-content:space-between;align-items:center;gap:8px;margin-bottom:7px;">'
        f'<span class="pill pill-blue">{_esc(mode)}</span>'
        f'<span class="sub">{cnt} disclosures synthesized</span>'
        "</div>"
        f"{summary_html}"
        f'<ul class="summary-bullets">{"".join(lis)}</ul>'
        f"{src_block}"
        "</div>"
    )


def render_web_dashboard_html(report: Dict[str, Any]) -> str:
    """Build a crisp, gap-free interactive HTML5 + Chart.js Equity Research Web Dashboard."""
    sym = report["symbol"]
    name = report["name"]
    unit = report["unit"]
    curr = report["currency"]
    ex = report["executive_summary"]
    ret = report.get("returns_analysis") or {}
    kd = ex.get("key_market_data", {})
    fa = ex["forensic_audit_integrated"]
    eh = report.get("earnings_highlights", {})
    fs = report["financial_summary"]
    annual_rows = fs["annual_4y"]["rows"]
    q_rows = fs["quarterly_4q"]["rows"]
    seg = fs.get("segment_analysis") or {}
    dcf = fs["dcf_valuation"]
    pe_bands = fs.get("valuation_bands") or {}
    wc = fs.get("working_capital") or {}
    peers = fs["peer_comps"]
    own = report.get("ownership_and_market_context", {})
    adv = report["advanced_analysis_explained"]
    concl = adv.get("conclusion") or {}
    intro = report.get("intro_section") or {}
    rating_fw = concl.get("rating_framework") or {}
    stance = report["investor_stance"]

    tone_badge = (
        "badge-green" if stance["tone"] == "green" else ("badge-red" if stance["tone"] == "red" else "badge-amber")
    )
    tone_border = (
        "decision-green"
        if stance["tone"] == "green"
        else ("decision-red" if stance["tone"] == "red" else "decision-amber")
    )

    upside = dcf.get("upside_downside_pct")
    upside_str = f"{upside:+}% variance vs CMP" if upside is not None else "N/A"
    upside_cls = "text-green" if (upside or 0) > 10 else ("text-red" if (upside or 0) < -5 else "text-amber")

    quick_pointers_html = "".join(f"<li>{_esc(qp)}</li>" for qp in ex.get("quick_pointers", []))
    events_html = _render_summary_with_sources(
        ex.get("events_briefing"),
        "No material corporate developments identified from live news feeds.",
    )

    eh_overview_trs = "".join(
        f"""<tr>
          <td><strong>{_esc(ov['metric'])}</strong></td>
          <td class="num"><strong>{_esc(ov['latest'])}</strong></td>
          <td class="num">{_esc(ov['prior'])}</td>
          <td class="num {'text-green' if str(ov.get('qoq_var', '')).startswith('+') else ('text-red' if str(ov.get('qoq_var', '')).startswith('-') else '')}">{_esc(ov['qoq_var'])}</td>
          <td class="num {'text-green' if str(ov.get('yoy_var', '')).startswith('+') else ('text-red' if str(ov.get('yoy_var', '')).startswith('-') else '')}">{_esc(ov['yoy_var'])}</td>
        </tr>"""
        for ov in eh.get("result_overview_rows", [])
    )
    eh_thematic_html = "".join(
        f"""<div class="subcard" style="margin-bottom:8px;border-left:3px solid {'var(--green)' if hl.get('tone') == 'positive' else ('var(--red)' if hl.get('tone') == 'warning' else 'var(--accent)')};">
          <strong>{_esc(hl['topic'])}</strong>
          <div class="explain-block" style="margin-top:3px;">{_esc(hl['detail'])}</div>
        </div>"""
        for hl in eh.get("thematic_highlights", [])
    ) or '<div class="muted">Quarterly operating commentary will populate once sequential statements are available.</div>'
    eh_feed_html = _render_summary_with_sources(
        eh.get("media_briefing"),
        "No recent quarterly earnings call or exchange result notices returned in feed; see quarterly table.",
    )
    eh_fresh = eh.get("freshness") or {}
    eh_ssum = eh.get("surprise_summary") or {}
    eh_fc = eh.get("forward_consensus") or {}
    eh_surp_rows = eh.get("surprise_4q") or []
    eh_surp_trs = "".join(
        f"""<tr>
          <td><strong>{_esc(sr['quarter'])}</strong></td>
          <td class="num"><strong>{fmt_comma(sr.get('eps_actual'), 2)}</strong></td>
          <td class="num">{fmt_comma(sr.get('eps_estimate'), 2)}</td>
          <td class="num {'text-green' if (sr.get('surprise_pct') or 0) >= 1.0 else ('text-red' if (sr.get('surprise_pct') or 0) <= -1.0 else '')}">{f"{sr['surprise_pct']:+}%" if sr.get('surprise_pct') is not None else '—'}</td>
          <td><span class="pill {'pill-green' if sr.get('verdict') == 'Beat' else ('pill-red' if sr.get('verdict') == 'Miss' else 'pill-slate')}">{_esc(sr.get('verdict', '—'))}</span></td>
          <td class="num">{fmt_comma(sr.get('gross_margin_pct'), 1, '%')}</td>
          <td class="num">{fmt_comma(sr.get('ebit_margin_pct'), 1, '%')}</td>
          <td class="num">{fmt_comma(sr.get('pat_margin_pct'), 1, '%')}</td>
        </tr>"""
        for sr in eh_surp_rows
    )
    eh_sources_html = " &middot; ".join(
        f'<a href="{_esc(sc["url"])}" target="_blank" rel="noopener" style="color:var(--accent);font-weight:600;text-decoration:none;">{_esc(sc["label"])} ({_esc(sc["date"])})</a>'
        for sc in eh.get("sources_checklist", [])
    )

    seg_available = bool(seg.get("available") and seg.get("segments"))
    seg_rows = seg.get("segments", []) if seg_available else []
    seg_has_cap = bool(seg.get("has_cap_employed"))
    seg_card_html = ""
    if seg_available:
        seg_trs = "".join(
            f"""<tr>
              <td><strong>{_esc(sr['name'])}</strong></td>
              <td class="num">{fmt_comma(sr.get('revenue_cr'))}</td>
              <td class="num">{fmt_comma(sr.get('rev_mix_pct'), 1, '%')}</td>
              <td class="num {'text-green' if (sr.get('rev_qoq_pct') or 0) > 0 else ('text-red' if (sr.get('rev_qoq_pct') or 0) < 0 else '')}">{fmt_comma(sr.get('rev_qoq_pct'), 1, '%')}</td>
              <td class="num {'text-green' if (sr.get('rev_yoy_pct') or 0) > 0 else ('text-red' if (sr.get('rev_yoy_pct') or 0) < 0 else '')}">{fmt_comma(sr.get('rev_yoy_pct'), 1, '%')}</td>
              <td class="num">{fmt_comma(sr.get('ebit_cr'))}</td>
              <td class="num">{fmt_comma(sr.get('ebit_mix_pct'), 1, '%')}</td>
              <td class="num"><strong>{fmt_comma(sr.get('ebit_margin_pct'), 1, '%')}</strong></td>
              {f'<td class="num">{fmt_comma(sr.get("ann_roce_pct"), 1, "%")}</td>' if seg_has_cap else ''}
            </tr>"""
            for sr in seg_rows
        )
        cap_th = '<th class="num">Ann. ROCE</th>' if seg_has_cap else ''
        seg_src_badge = (
            f'<a href="{_esc(seg.get("source_url"))}" target="_blank" rel="noopener" class="pill pill-blue" style="text-decoration:none;">Ind-AS 108 XBRL</a>'
            if seg.get("source_url")
            else '<span class="pill pill-blue">Ind-AS 108</span>'
        )
        seg_card_html = f"""
  <div class="card">
    <div style="display:flex;justify-content:space-between;align-items:center;gap:8px;flex-wrap:wrap;margin-bottom:10px;">
      <h3 style="margin:0">C. Operating Segment Analysis — {_esc(seg.get('filing_basis', 'Consolidated'))} ({_esc(seg.get('period_end', 'Latest'))})</h3>
      {seg_src_badge}
    </div>
    <div class="split-40-60">
      <div class="chart-box" style="height:240px"><canvas id="chartSegments"></canvas></div>
      <div class="overflow-x">
        <table>
          <thead><tr><th>Segment</th><th class="num">Revenue</th><th class="num">Rev Mix</th><th class="num">QoQ%</th><th class="num">YoY%</th><th class="num">EBIT</th><th class="num">EBIT Mix</th><th class="num">Margin%</th>{cap_th}</tr></thead>
          <tbody>{seg_trs}</tbody>
        </table>
      </div>
    </div>
    <div class="decision-box decision-blue">
      <span class="decision-tag">Segment Mix &amp; Margin Observation</span>
      {_esc(seg.get('opinion', ''))}
    </div>
  </div>"""
    wc_lbl = "D" if seg_available else "C"
    peer_lbl = "E" if seg_available else "D"

    ret_available = bool(ret.get("available"))
    returns_card_html = ""
    ret_attr_labels: list[str] = []
    ret_attr_vals: list[float] = []
    if ret_available:
        rb = ret["base"]
        ret_attr_labels = ["Entry Capital", "EBITDA Growth", "Multiple Shift", "Cash & Divs", "Base Exit MOIC"]
        ret_attr_vals = [1.0, rb["attr_growth_moic"], rb["attr_multiple_moic"], rb["attr_cash_moic"], rb["moic"]]

        scen_trs = "".join(
            f"""<tr class="{'highlight-row' if sc.get('key') == 'base' else ''}">
              <td><strong>{_esc(sc['name'])}</strong></td>
              <td class="num">{sc['growth_pct']}%</td>
              <td class="num">{sc['exit_mult']}x</td>
              <td class="num">{fmt_comma(sc['exit_equity'])}</td>
              <td class="num"><strong>{sc['moic']:.2f}x</strong></td>
              <td class="num {'text-green' if sc['irr_pct'] >= 15.0 else ('text-amber' if sc['irr_pct'] >= 10.0 else 'text-red')}"><strong>{sc['irr_pct']:.1f}%</strong></td>
            </tr>"""
            for sc in ret.get("scenarios", [])
        )
        m_cols = "".join(f"<th class='num'>{m}x</th>" for m in ret.get("sensitivity_mults", []))
        ret_sens_trs = ""
        mid_r = len(ret.get("sensitivity_growth_pcts", [])) // 2
        mid_c = len(ret.get("sensitivity_mults", [])) // 2
        for r_i, g_val in enumerate(ret.get("sensitivity_growth_pcts", [])):
            row_tds = f"<td><strong>{g_val}%</strong></td>"
            for c_i, cell in enumerate(ret["sensitivity_matrix"][r_i]):
                irr_v = float(cell["irr_pct"])
                cls = "cell-upside" if irr_v >= 15.0 else ("cell-fair" if irr_v >= 10.0 else "cell-downside")
                base_mark = "border:2px solid var(--accent);" if (r_i == mid_r and c_i == mid_c) else ""
                row_tds += f'<td class="num {cls}" style="{base_mark}white-space:nowrap;">{_esc(cell["label"])}</td>'
            ret_sens_trs += f"<tr>{row_tds}</tr>"

        returns_card_html = f"""
  <div class="card" style="margin-bottom:0;">
    <div style="display:flex;justify-content:space-between;align-items:center;gap:8px;flex-wrap:wrap;margin-bottom:8px;">
      <h3 style="margin:0">5-Year Public Equity Returns Analysis (Annualized IRR / Total Multiple MOIC)</h3>
      <span class="pill {'pill-green' if rb['irr_pct'] >= 15.0 else ('pill-blue' if rb['irr_pct'] >= 10.0 else 'pill-slate')}">Base Model: {rb['irr_pct']:.1f}% IRR &middot; {rb['moic']:.2f}x MOIC</span>
    </div>
    <div class="audit-kpis">
      <div class="mini-stat"><div class="lbl">Entry MCap / EV</div><div class="v">{fmt_comma(ret['entry_equity'])} / {fmt_comma(ret['entry_ev'])}</div><div class="sub">{_esc(unit)} at CMP {_esc(curr)} {fmt_comma(ret['entry_price'], 1)}</div></div>
      <div class="mini-stat"><div class="lbl">Entry EV / EBITDA</div><div class="v">{ret['entry_mult']}x</div><div class="sub">LTM EBITDA {fmt_comma(ret['entry_ebitda'])} {_esc(unit)}</div></div>
      <div class="mini-stat"><div class="lbl">Base 5Y IRR / MOIC</div><div class="v {'text-green' if rb['irr_pct'] >= 15.0 else ''}">{rb['irr_pct']:.1f}% / {rb['moic']:.2f}x</div><div class="sub">Annual return / Capital multiple</div></div>
      <div class="mini-stat"><div class="lbl">Return Drivers</div><div class="v">{rb['attr_growth_moic']:+}x / {rb['attr_multiple_moic']:+}x / {rb['attr_cash_moic']:+}x</div><div class="sub">Profit Growth / Multiple / Cash+Div</div></div>
    </div>
    <div class="grid-2" style="margin-bottom:0;">
      <div>
        <div class="overflow-x">
          <table>
            <thead><tr><th>Scenario</th><th class="num">EBITDA CAGR</th><th class="num">Exit Mult <span class="sub">(EV/EB)</span></th><th class="num">Exit Equity</th><th class="num">MOIC <span class="sub">(x Cap)</span></th><th class="num">5Y IRR <span class="sub">(CAGR)</span></th></tr></thead>
            <tbody>{scen_trs}</tbody>
          </table>
        </div>
        <div class="chart-box" style="height:190px;margin-top:10px;"><canvas id="chartReturnsAttr"></canvas></div>
      </div>
      <div>
        <div class="sub" style="margin-bottom:4px;"><strong>2-Way Returns Sensitivity (EBITDA Growth CAGR &times; Exit EV/EBITDA &rarr; IRR% / MOICx)</strong> &middot; Green &ge;15% | Amber 10–15% | Red &lt;10%</div>
        <div class="overflow-x">
          <table>
            <thead><tr><th>CAGR / Exit</th>{m_cols}</tr></thead>
            <tbody>{ret_sens_trs}</tbody>
          </table>
        </div>
      </div>
    </div>
    <div class="decision-box decision-blue">
      <span class="decision-tag">Educational 5-Year Returns &amp; Sensitivity Model</span>
      {_esc(ret.get('opinion', ''))}
    </div>
  </div>"""

    deals_html = _render_summary_with_sources(
        own.get("filings_deals_briefing"),
        "No promoter stake sales, pledge escalations, or material block deals identified over the last 6 months.",
    )
    ratings_news_html = _render_summary_with_sources(
        own.get("ratings_briefing"),
        "No recent brokerage target or credit-rating actions returned; refer to street consensus above.",
    )

    pros_cons_html = ""
    if ex.get("screener_pros") or ex.get("screener_cons"):
        pros_li = "".join(f"<li>{_esc(p)}</li>" for p in ex.get("screener_pros", [])[:3])
        cons_li = "".join(f"<li>{_esc(c)}</li>" for c in ex.get("screener_cons", [])[:3])
        pros_cons_html = f"""
        <div class="grid-2-tight mt-12">
          <div class="subcard"><strong class="text-green">Key Strengths</strong><ul class="compact-list">{pros_li or '<li>None listed</li>'}</ul></div>
          <div class="subcard"><strong class="text-red">Key Watchpoints</strong><ul class="compact-list">{cons_li or '<li>None listed</li>'}</ul></div>
        </div>"""

    citations_html = "".join(
        f'<li><span class="pill pill-slate">{_esc(c.get("category"))}</span> {_esc(c.get("snippet"))}</li>'
        for c in fa.get("citations", [])[:4]
    ) or "<li>Baseline financial, cash-flow &amp; solvency checks passed cleanly.</li>"

    warnings_html = "".join(f'<span class="warn-chip">{_esc(w)}</span>' for w in fa.get("warnings", [])) or '<span class="pill pill-green">Zero Audit Warnings</span>'
    vetoes_html = "".join(f'<span class="veto-chip">{_esc(v)}</span>' for v in fa.get("vetoes", [])) or '<span class="pill pill-green">Zero Major Red Flags</span>'

    annual_trs = "".join(
        f"""<tr>
          <td><strong>{_esc(r['period'])}</strong></td>
          <td class="num">{fmt_comma(r['revenue'])}</td>
          <td class="num">{fmt_comma(r['yoy_rev_pct'], 1, '%')}</td>
          <td class="num">{fmt_comma(r['ebitda'])}</td>
          <td class="num">{fmt_comma(r['opm_pct'], 1, '%')}</td>
          <td class="num">{fmt_comma(r['pat'])}</td>
          <td class="num">{fmt_comma(r['yoy_pat_pct'], 1, '%')}</td>
          <td class="num">{fmt_comma(r['cfo'])}</td>
          <td class="num">{fmt_comma(r['capex'])}</td>
          <td class="num"><strong>{fmt_comma(r['fcf'])}</strong></td>
        </tr>"""
        for r in annual_rows
    )

    quarterly_trs = "".join(
        f"""<tr>
          <td><strong>{_esc(q['quarter_end'])}</strong></td>
          <td class="num">{fmt_comma(q['revenue'])}</td>
          <td class="num">{fmt_comma(q['qoq_rev_pct'], 1, '%')}</td>
          <td class="num">{fmt_comma(q['yoy_rev_pct'], 1, '%')}</td>
          <td class="num">{fmt_comma(q['ebit'])}</td>
          <td class="num">{fmt_comma(q['ebit_margin_pct'], 1, '%')}</td>
          <td class="num">{fmt_comma(q['pat'])}</td>
          <td class="num">{fmt_comma(q['qoq_pat_pct'], 1, '%')}</td>
        </tr>"""
        for q in q_rows
    )

    # Working capital & cash conversion table
    wc_periods = wc.get("periods", [])
    wc_series = wc.get("series", {})
    wc_headers = "".join(f"<th class='num'>{_esc(p)}</th>" for p in wc_periods)
    wc_rows_html = ""
    for metric_lbl in ("Debtor Days", "Inventory Days", "Days Payable", "Cash Conversion Cycle", "ROCE %"):
        vals = wc_series.get(metric_lbl, [])
        if vals:
            tds = "".join(f"<td class='num'>{fmt_comma(v, 0 if 'Days' in metric_lbl or 'Cycle' in metric_lbl else 1, '%' if '%' in metric_lbl else '')}</td>" for v in vals)
            wc_rows_html += f"<tr><td><strong>{_esc(metric_lbl)}</strong></td>{tds}</tr>"
    cfo_pat_rows = wc.get("cfo_to_pat_rows", [])
    if cfo_pat_rows:
        cfo_pat_pills = " · ".join(
            f"<strong>{_esc(r['period'])}:</strong> {fmt_comma(r['cfo_to_pat'], 2, 'x')}" for r in cfo_pat_rows if r.get("cfo_to_pat") is not None
        )
    else:
        cfo_pat_pills = "—"

    dcf_trs = "".join(
        f"""<tr>
          <td><strong>{_esc(f['year'])}</strong></td>
          <td class="num">{fmt_comma(f['rev_growth_pct'], 1, '%')}</td>
          <td class="num">{fmt_comma(f['revenue'])}</td>
          <td class="num">{fmt_comma(f['nopat'])}</td>
          <td class="num">{fmt_comma(f['reinvestment'])}</td>
          <td class="num"><strong>{fmt_comma(f['fcff'])}</strong></td>
          <td class="num">{fmt_comma(f['pv_fcff'])}</td>
        </tr>"""
        for f in dcf.get("forecast_5y", [])
    )

    cmp_px = float(report.get("price") or 0.0)
    g_headers = "".join(f"<th class='num'>Growth = {g}%</th>" for g in dcf.get("sensitivity_g_pcts", []))
    sens_trs = ""
    for row in dcf.get("sensitivity_matrix", []):
        w_lbl = row[0]["wacc_pct"]
        cells = ""
        for cell in row:
            fp = cell["fair_price"]
            if cmp_px > 0 and fp >= cmp_px * 1.15:
                c_cls = "cell-upside"
            elif cmp_px > 0 and fp <= cmp_px * 0.90:
                c_cls = "cell-downside"
            else:
                c_cls = "cell-fair"
            cells += f"<td class='num {c_cls}'>{_esc(curr)} {fmt_comma(fp, 1)}</td>"
        sens_trs += f"<tr><td><strong>Discount {w_lbl}%</strong></td>{cells}</tr>"

    sotp = dcf.get("sotp_bridge") or {}
    sotp_trs = "".join(
        f"""<tr>
          <td><strong>{row['ev_ebitda']:.0f}x EV/EBITDA</strong></td>
          <td class="num">{_esc(curr)} {fmt_comma(row['implied_price'], 1)}</td>
          <td class="num {'text-green' if (row.get('upside_pct') or 0) >= 0 else 'text-red'}">{fmt_comma(row.get('upside_pct'), 1, '%')}</td>
        </tr>"""
        for row in sotp.get("ladder", [])
    )

    peer_trs = "".join(
        f"""<tr class="{'highlight-row' if p['symbol'] == sym else ''}">
          <td><strong>{_esc(p['symbol'])}</strong><div class="sub">{_esc(p['name'][:22])}</div></td>
          <td class="num">{fmt_comma(p.get('score'), 1)}</td>
          <td class="num">{fmt_comma(p.get('roic_pct'), 1, '%')}</td>
          <td class="num">{fmt_comma(p.get('inc_roic_pct'), 1, '%')}</td>
          <td class="num">{fmt_comma(p.get('cfo_to_ebitda'), 2, 'x')}</td>
          <td class="num">{fmt_comma(p.get('ev_to_nopat'), 1, 'x')}</td>
          <td class="num">{fmt_comma(p.get('fcf_yield_pct'), 2, '%')}</td>
        </tr>"""
        for p in peers
    )

    insights_html = ""
    for ins in adv.get("insights", []):
        tone = ins.get("tone", "neutral")
        border_cls = "border-green" if tone == "positive" else ("border-amber" if tone == "warning" else "border-blue")
        pill_t = "pill-green" if tone == "positive" else ("pill-red" if tone == "warning" else "pill-blue")
        insights_html += f"""
        <div class="insight-card {border_cls}">
          <div class="insight-head">
            <h4>{_esc(ins['title'])}</h4>
            <span class="pill {pill_t}">{_esc(ins['score_label'])}</span>
          </div>
          <div class="insight-reading">{_esc(ins['reading'])}</div>
          <p class="explain-block"><strong>Analytical Definition:</strong> {_esc(ins['what_it_is'])}</p>
          <p class="explain-block"><strong>What It Means For {_esc(name)}:</strong> {_esc(ins['what_it_means'])}</p>
        </div>"""

    sh_quarters = own.get("shareholding_quarters", [])
    sh_series = own.get("shareholding_series", {})
    sh_lat = own.get("shareholding_latest", {})
    sh_header = "".join(f"<th class='num'>{_esc(q)}</th>" for q in sh_quarters)
    sh_rows_html = ""
    for cat_key, display_lbl in (("Promoters", "Promoters (%)"), ("FIIs", "Foreign / FPIs (%)"), ("DIIs", "Domestic / MFs (%)"), ("Public", "Public (%)")):
        vals = sh_series.get(cat_key, [])
        if vals:
            tds = "".join(f"<td class='num'>{fmt_comma(v, 2, '%')}</td>" for v in vals)
            sh_rows_html += f"<tr><td><strong>{display_lbl}</strong></td>{tds}</tr>"

    insider_trs = "".join(
        f"""<tr>
          <td>{_esc(tx.get('date'))}</td>
          <td><strong>{_esc(tx.get('insider'))}</strong></td>
          <td>{_esc(tx.get('transaction'))}</td>
          <td class="num">{fmt_comma(tx.get('shares'))}</td>
        </tr>"""
        for tx in own.get("insider_transactions", [])[:4]
    )

    perf_rows = own.get("performance_table", [])
    perf_trs = "".join(
        f"""<tr>
          <td><strong>{_esc(pr['horizon'])}</strong></td>
          <td class="num {'text-green' if (pr.get('stock_pct') or 0) > 0 else 'text-red'}"><strong>{fmt_comma(pr.get('stock_pct'), 1, '%')}</strong></td>
          <td class="num">{fmt_comma(pr.get('benchmark_pct'), 1, '%')}</td>
          <td class="num {'text-green' if (pr.get('relative_pct') or 0) >= 0 else 'text-red'}"><strong>{fmt_comma(pr.get('relative_pct'), 1, '%')}</strong></td>
        </tr>"""
        for pr in perf_rows
    )

    peer_perf_trs = "".join(
        f"""<tr class="{'highlight-row' if pp['symbol'] == sym else ''}">
          <td><strong>{_esc(pp['symbol'])}</strong></td>
          <td class="num {'text-green' if (pp.get('ret_12m_pct') or 0) >= 0 else 'text-red'}"><strong>{fmt_comma(pp.get('ret_12m_pct'), 1, '%')}</strong></td>
          <td class="num">{fmt_comma(pp.get('roic_pct'), 1, '%')}</td>
          <td class="num">{fmt_comma(pp.get('score'), 1)}</td>
        </tr>"""
        for pp in own.get("peer_performance", [])
    )

    comp = own.get("competitive_analysis") or {}
    comp_card_html = ""
    if comp.get("dimensions"):
        comp_sym_ths = "".join(
            f'<th class="num">{"<strong>" + _esc(cs) + "</strong>" if cs == sym else _esc(cs)}</th>'
            for cs in comp.get("cohort_symbols", [])
        )
        comp_dim_trs = ""
        for dim in comp["dimensions"]:
            tds = ""
            for cell in dim["cells"]:
                hl_style = 'style="font-weight:700;background:var(--accent-soft);"' if cell["symbol"] == sym else ""
                tds += f'<td class="num" {hl_style}>{_esc(cell["display"])}</td>'
            comp_dim_trs += f"<tr><td><strong>{_esc(dim['dimension'])}</strong></td>{tds}</tr>"

        moat_trs = ""
        for mp in comp.get("moat_pillars", []):
            r_txt = mp.get("rating", "Moderate")
            r_cls = "pill-green" if r_txt == "Strong" else ("pill-red" if r_txt == "Weak" else "pill-blue")
            moat_trs += (
                f'<tr><td><strong>{_esc(mp["pillar"])}</strong></td>'
                f'<td><span class="pill {r_cls}">{_esc(r_txt)}</span></td>'
                f'<td>{_esc(mp["detail"])}</td></tr>'
            )

        adv_li = "".join(f"<li>{_esc(a)}</li>" for a in comp.get("durable_advantages", []))
        vuln_li = "".join(f"<li>{_esc(v)}</li>" for v in comp.get("structural_vulnerabilities", []))
        comp_card_html = f"""
  <div class="card" style="margin-bottom:0;">
    <div style="display:flex;justify-content:space-between;align-items:center;gap:8px;flex-wrap:wrap;margin-bottom:8px;">
      <h3 style="margin:0">Competitive Positioning &amp; Structural Moat Analysis</h3>
      <span class="pill pill-blue">{_esc(comp.get('insight_headline', 'Peer Landscape'))}</span>
    </div>
    <div class="grid-2" style="margin-bottom:0;">
      <div>
        <div class="sub" style="margin-bottom:4px;"><strong>2&times;2 Competitive Positioning Matrix</strong> (X: ROIC % &middot; Y: 12M Return % &middot; Size: Market Cap)</div>
        <div class="chart-box" style="height:225px;"><canvas id="chartCompMatrix"></canvas></div>
        <h4 style="margin:12px 0 6px;font-size:0.86rem;">4-Pillar Structural Moat Scorecard</h4>
        <div class="overflow-x">
          <table>
            <thead><tr><th>Moat Pillar</th><th>Rating</th><th>Assessment</th></tr></thead>
            <tbody>{moat_trs}</tbody>
          </table>
        </div>
      </div>
      <div>
        <div class="sub" style="margin-bottom:4px;"><strong>Comparative Peer Scorecard</strong> (&#9679;&#9679;&#9679; Top Tier &middot; &#9679;&#9679;&#9675; Mid &middot; &#9679;&#9675;&#9675; Lagging across cohort)</div>
        <div class="overflow-x">
          <table>
            <thead><tr><th>Dimension</th>{comp_sym_ths}</tr></thead>
            <tbody>{comp_dim_trs}</tbody>
          </table>
        </div>
        <div class="grid-2-tight mt-12">
          <div class="subcard"><strong class="text-green">Durable Advantages</strong><ul class="compact-list">{adv_li}</ul></div>
          <div class="subcard"><strong class="text-red">Structural Vulnerabilities</strong><ul class="compact-list">{vuln_li}</ul></div>
        </div>
      </div>
    </div>
  </div>"""

    pt = own.get("analyst_price_targets", {})
    rec = own.get("analyst_recommendations", {})
    rec_tot = max(rec.get("total", 0), 1)
    buy_pct_bar = round((rec.get("strongBuy", 0) + rec.get("buy", 0)) / rec_tot * 100.0, 1) if rec.get("total") else 0
    hold_pct_bar = round(rec.get("hold", 0) / rec_tot * 100.0, 1) if rec.get("total") else 0
    sell_pct_bar = round((rec.get("sell", 0) + rec.get("strongSell", 0)) / rec_tot * 100.0, 1) if rec.get("total") else 0

    intro_outlook_html = _render_summary_with_sources(
        intro.get("outlook_briefing"),
        "Recent annual report or order-book guidance items were limited across automated feeds.",
    )
    intro_verticals = ", ".join(intro.get("verticals") or []) or "Diversified Core Operations"
    intro_strengths_html = "".join(
        f'<span class="pill pill-green" style="margin:2px 4px 2px 0;">{_esc(s)}</span>'
        for s in (intro.get("structural_strengths") or [])
    )
    intro_website = intro.get("website") or "—"
    intro_website_link = (
        f'<a href="{_esc(intro_website)}" target="_blank" rel="noopener noreferrer">{_esc(intro_website)}</a>'
        if str(intro_website).startswith("http")
        else _esc(intro_website)
    )
    intro_section_html = f"""
  <!-- SECTION 0: INTRODUCTION, BUSINESS OUTLOOK & ORDER BOOK -->
  <div class="sec-wrap sec-cyan">
  <div id="intro" class="section-hdr"><span class="section-num">0</span> Introduction: Business Overview, Annual Report Outlook &amp; Order Book</div>
  <div class="card">
    <div class="grid-2" style="margin-bottom:0;">
      <div>
        <h3 style="margin:0 0 8px">Company Business Profile</h3>
        <p class="explain-block" style="line-height:1.52;">{_esc(intro.get('overview') or '')}</p>
        <div class="audit-kpis" style="margin-top:10px;">
          <div class="mini-stat"><div class="lbl">Headquarters</div><div class="v" style="font-size:0.86rem;">{_esc(intro.get('hq') or '—')}</div></div>
          <div class="mini-stat"><div class="lbl">Workforce</div><div class="v" style="font-size:0.86rem;">{_esc(intro.get('employees') or 'Not disclosed')}</div></div>
          <div class="mini-stat"><div class="lbl">Corporate Site</div><div class="v" style="font-size:0.82rem;word-break:break-word;">{intro_website_link}</div></div>
        </div>
        <div class="subcard" style="margin-top:8px;">
          <strong>Multi-Year Scale &amp; Segments:</strong>
          <div class="explain-block" style="margin-top:3px;">{_esc(intro.get('scale_summary') or '')}</div>
          <div class="muted" style="margin-top:4px;"><strong>Key Verticals:</strong> {_esc(intro_verticals)}</div>
          {f'<div style="margin-top:6px;">{intro_strengths_html}</div>' if intro_strengths_html else ''}
        </div>
      </div>
      <div>
        <h3 style="margin:0 0 6px">Annual Report Outlook, Capex &amp; Order Book</h3>
        <div class="muted" style="margin-bottom:6px;">Synthesized from recent Annual Report filings, exchange announcements, capex plans, and order-book / TCV disclosures.</div>
        {intro_outlook_html}
      </div>
    </div>
  </div>
  </div>"""

    if rating_fw:
        rf_tone = rating_fw.get("tone", "neutral")
        rf_badge_cls = (
            "badge-green" if rf_tone in ("strong", "good") else ("badge-red" if rf_tone == "danger" else "badge-amber")
        )
        rf_trs = "".join(
            f"""<tr>
              <td><strong>{_esc(row['pillar'])}</strong><div class="muted" style="font-size:0.73rem;">{_esc(row['evidence'])}</div></td>
              <td class="num">{row['weight_pct']:.1f}%</td>
              <td class="num"><strong>{row['earned_pts']:.1f}</strong></td>
              <td class="num">{row['attainment_pct']:.1f}%</td>
              <td><span class="pill {'pill-green' if row['status'] == 'Strong' else ('pill-blue' if row['status'] == 'Satisfactory' else 'pill-red' if row['status'] == 'Weak' else 'pill-slate')}">{_esc(row['status'])}</span></td>
            </tr>"""
            for row in (rating_fw.get("layer_breakdown") or [])
        )
        rf_guide_trs = "".join(
            f"""<tr class="{'highlight-row' if g['grade'] == rating_fw.get('grade') else ''}">
              <td><strong>{_esc(g['grade'])}</strong></td>
              <td>{_esc(g['stars'])}</td>
              <td class="num">{_esc(g['score_range'])}</td>
              <td><strong>{_esc(g['classification'])}</strong></td>
              <td>{_esc(g['meaning'])} <span class="muted">Focus: {_esc(g['study_focus'])}</span></td>
            </tr>"""
            for g in (rating_fw.get("rating_scale_guide") or [])
        )
        rating_framework_html = f"""
    <div class="subcard" style="margin-bottom:12px;border-left:4px solid var(--accent);">
      <div style="display:flex;flex-wrap:wrap;justify-content:space-between;align-items:center;gap:10px;margin-bottom:8px;">
        <div>
          <span class="decision-tag" style="margin-bottom:3px;">Quantitative Fundamental &amp; Valuation Rating (Educational)</span>
          <strong style="font-size:1.05rem;">{_esc(rating_fw.get('rating_label', ''))}</strong>
        </div>
        <div style="display:flex;align-items:center;gap:8px;flex-wrap:wrap;">
          <span class="badge {rf_badge_cls}" style="font-size:0.9rem;">{_esc(rating_fw.get('grade', '—'))} &bull; {rating_fw.get('stars', '—')} / 5.0 &#9733;</span>
          <span class="pill pill-slate">Composite Score: {rating_fw.get('score', report['score'])} / 100</span>
        </div>
      </div>
      <div class="grid-2" style="margin-bottom:10px;">
        <div class="subcard" style="background:var(--surface);">
          <strong>How Did We Rate This Company? ({_esc(rating_fw.get('archetype', 'Core'))} Profile)</strong>
          <p class="explain-block">{_esc(rating_fw.get('how_we_rated', ''))}</p>
        </div>
        <div class="subcard" style="background:var(--surface);">
          <strong>What This Rating Means</strong>
          <p class="explain-block">{_esc(rating_fw.get('meaning_of_rating', ''))}</p>
        </div>
      </div>
      <h4 style="margin:8px 0 4px;font-size:0.86rem;">Basis for Rating: 6-Pillar Scorecard Reconciliation (Base {rating_fw.get('base_layer_total', 0):.1f} + Multi-Signal/Veto {rating_fw.get('bonus_adj', 0):+.1f} = {rating_fw.get('score', 0):.1f}/100)</h4>
      <div class="overflow-x">
        <table>
          <thead><tr><th>Scoring Pillar &amp; Underlying Evidence</th><th class="num">Weight</th><th class="num">Earned Pts</th><th class="num">Attainment</th><th>Rating Tier</th></tr></thead>
          <tbody>{rf_trs}</tbody>
        </table>
      </div>
      <h4 style="margin:12px 0 4px;font-size:0.86rem;">Our Educational Guide on the 5-Tier Rating Scale</h4>
      <div class="overflow-x">
        <table>
          <thead><tr><th>Grade</th><th>Stars</th><th class="num">Score Range</th><th>Classification</th><th>Meaning &amp; Analytical Study Focus</th></tr></thead>
          <tbody>{rf_guide_trs}</tbody>
        </table>
      </div>
    </div>"""
    else:
        rating_framework_html = ""

    prov = report.get("data_provenance") or {}
    if prov.get("sources"):
        prov_trs = "".join(
            f"""<tr>
              <td><strong>{_esc(s['name'])}</strong>{f' &nbsp;<a href="{_esc(s["url"])}" target="_blank" rel="noopener noreferrer" style="font-size:0.74rem;">Source &#8599;</a>' if s.get('url') else ''}</td>
              <td>{_esc(s['provider'])}</td>
              <td><span class="pill {'pill-green' if s['status'] in ('Verified', 'Attached & Audited') else 'pill-slate'}">{_esc(s['status'])}</span></td>
              <td class="muted">{_esc(s['scope'])}</td>
            </tr>"""
            for s in prov["sources"]
        )
        data_sources_html = f"""
    <div class="subcard" style="margin-bottom:12px;">
      <div style="display:flex;flex-wrap:wrap;justify-content:space-between;align-items:center;gap:8px;margin-bottom:6px;">
        <strong style="font-size:0.95rem;">Sources of Data &amp; Strict Actual-Data Verification</strong>
        <span class="pill pill-green">Actual Data Only &bull; {prov.get('verified_sources_count', 0)}/{prov.get('total_sources_checked', 0)} Feeds Verified</span>
      </div>
      <div class="explain-block" style="margin-bottom:8px;">{_esc(prov.get('policy', ''))}</div>
      <div class="overflow-x">
        <table>
          <thead><tr><th>Data Stream</th><th>Provider / Regulatory Source</th><th>Status</th><th>Coverage &amp; Provenance</th></tr></thead>
          <tbody>{prov_trs}</tbody>
        </table>
      </div>
    </div>"""
    else:
        data_sources_html = ""

    chart_payload = json.dumps(
        {
            "annual_labels": [r["period"] for r in annual_rows],
            "annual_rev": [r["revenue"] for r in annual_rows],
            "annual_pat": [r["pat"] for r in annual_rows],
            "annual_fcf": [r["fcf"] for r in annual_rows],
            "annual_opm": [r["opm_pct"] for r in annual_rows],
            "q_labels": [q["quarter_end"] for q in q_rows],
            "q_rev": [q["revenue"] for q in q_rows],
            "q_pat": [q["pat"] for q in q_rows],
            "q_opm": [q["ebit_margin_pct"] for q in q_rows],
            "surp_labels": [sr["quarter"] for sr in eh_surp_rows],
            "surp_actual": [sr.get("eps_actual") for sr in eh_surp_rows],
            "surp_est": [sr.get("eps_estimate") for sr in eh_surp_rows],
            "surp_pct": [sr.get("surprise_pct") for sr in eh_surp_rows],
            "ret_attr_labels": ret_attr_labels,
            "ret_attr_vals": ret_attr_vals,
            "seg_labels": [s["name"][:28] for s in seg_rows],
            "seg_rev_mix": [s.get("rev_mix_pct") or 0 for s in seg_rows],
            "seg_ebit_mix": [s.get("ebit_mix_pct") or 0 for s in seg_rows],
            "seg_margins": [s.get("ebit_margin_pct") or 0 for s in seg_rows],
            "dcf_labels": [f["year"] for f in dcf.get("forecast_5y", [])],
            "dcf_fcff": [f["fcff"] for f in dcf.get("forecast_5y", [])],
            "dcf_pv": [f["pv_fcff"] for f in dcf.get("forecast_5y", [])],
            "dcf_sim": {
                "base_rev": dcf.get("base_revenue", 0),
                "reinv_pct": dcf.get("reinvestment_rate_pct", 30.0),
                "tax_pct": dcf.get("tax_rate_pct", 25.17),
                "term_g_pct": dcf.get("terminal_growth_pct", 5.0),
                "net_debt": dcf.get("net_debt", 0.0),
                "shares_scaled": dcf.get("shares_scaled", 1.0),
                "cmp": cmp_px,
                "curr": curr,
            },
            "peer_labels": [p["symbol"] for p in peers],
            "peer_roic": [p.get("roic_pct") or 0 for p in peers],
            "peer_score": [p.get("score") or 0 for p in peers],
            "comp_points": comp.get("matrix_points", []),
            "sh_labels": sh_quarters,
            "sh_prom": sh_series.get("Promoters", []),
            "sh_fii": sh_series.get("FIIs", []),
            "sh_dii": sh_series.get("DIIs", []),
            "perf_labels": [p["horizon"] for p in perf_rows],
            "perf_stock": [p.get("stock_pct") or 0 for p in perf_rows],
            "perf_bench": [p.get("benchmark_pct") or 0 for p in perf_rows],
            "price_dates": (kd.get("price_series") or {}).get("dates", []),
            "price_closes": (kd.get("price_series") or {}).get("closes", []),
            "price_dma50": (kd.get("price_series") or {}).get("dma50", []),
            "price_dma200": (kd.get("price_series") or {}).get("dma200", []),
            "pe_dates": pe_bands.get("dates", []),
            "pe_series": pe_bands.get("pe_series", []),
            "pe_mean": pe_bands.get("mean_5y_pe"),
            "pe_plus": pe_bands.get("plus_1sd_pe"),
            "pe_minus": pe_bands.get("minus_1sd_pe"),
            "bench_label": own.get("benchmark_label", "Nifty 50"),
            "sym": sym,
            "unit": unit,
        }
    )

    meta_desc = (
        f"{name} ({sym}) fundamental analysis and Indian equity research digest covering {report.get('sector', 'Equity')} "
        f"({report.get('industry', '')}): 4-quarter earnings surprise, Ind-AS 108 segment mix, ROIC vs WACC capital efficiency, "
        f"5-year FCFF DCF & IRR/MOIC valuation, Nifty/benchmark comparison, peer moat scorecard, and SEBI-compliant educational synthesis."
    )
    meta_keywords = (
        f"{name}, {sym}, fundamental analysis, Indian stock analysis, Nifty 50 stock analysis, NSE stock research, "
        f"how to do stock research, DCF valuation, ROIC WACC, quarterly earnings analysis, {report.get('sector', '')}"
    )
    schema_json_ld = json.dumps(
        {
            "@context": "https://schema.org",
            "@type": "AnalysisNewsArticle",
            "headline": f"{name} ({sym}) Fundamental Analysis, Valuation & Financial Research Digest",
            "description": meta_desc,
            "keywords": meta_keywords,
            "datePublished": str(report.get("generated_at", ""))[:10],
            "about": {
                "@type": "Corporation",
                "name": name,
                "tickerSymbol": sym,
            },
            "author": {
                "@type": "SoftwareApplication",
                "name": "Equity Research AI Agent",
            },
            "isAccessibleForFree": True,
            "educationalUse": "Quantitative Financial Education (Non-Advisory under SEBI RA 2014 / IA 2013)",
        },
        ensure_ascii=False,
    )

    return f"""<!DOCTYPE html>
<html lang="en" data-theme="light">
<head>
<meta charset="UTF-8" />
<meta name="viewport" content="width=device-width, initial-scale=1.0" />
<title>{_esc(name)} ({_esc(sym)}) — Fundamental Analysis, Valuation &amp; Stock Research Digest</title>
<meta name="description" content="{_esc(meta_desc)}" />
<meta name="keywords" content="{_esc(meta_keywords)}" />
<meta name="robots" content="index, follow" />
<meta property="og:type" content="article" />
<meta property="og:title" content="{_esc(name)} ({_esc(sym)}) — Fundamental Analysis &amp; Valuation Digest" />
<meta property="og:description" content="{_esc(meta_desc)}" />
<meta name="twitter:card" content="summary_large_image" />
<meta name="twitter:title" content="{_esc(name)} ({_esc(sym)}) — Equity Research AI Agent" />
<meta name="twitter:description" content="{_esc(meta_desc)}" />
<script type="application/ld+json">{schema_json_ld}</script>
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.3/dist/chart.umd.min.js"></script>
<style>
  :root {{
    --bg: #f3f6fb; --surface: #ffffff; --surface-2: #f8fafc; --border: #e2e8f0;
    --text: #0f172a; --muted: #64748b; --accent: #0284c7; --accent-soft: rgba(2, 132, 199, 0.10);
    --green: #059669; --amber: #d97706; --red: #dc2626;
    --shadow: 0 3px 14px rgba(15, 23, 42, 0.05);
  }}
  [data-theme="dark"] {{
    --bg: #090d16; --surface: #111827; --surface-2: #182234; --border: #263244;
    --text: #f1f5f9; --muted: #94a3b8; --accent: #38bdf8; --accent-soft: rgba(56, 189, 248, 0.14);
    --green: #22c55e; --amber: #f59e0b; --red: #f87171;
    --shadow: 0 4px 18px rgba(0, 0, 0, 0.35);
  }}
  * {{ box-sizing: border-box; scroll-behavior: smooth; }}
  body {{ margin: 0; font-family: "Plus Jakarta Sans", Inter, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; background: var(--bg); color: var(--text); line-height: 1.5; }}
  .nav-bar {{ position: sticky; top: 0; z-index: 50; background: var(--surface); border-bottom: 1px solid var(--border); padding: 9px 22px; display: flex; justify-content: space-between; align-items: center; gap: 12px; flex-wrap: wrap; }}
  .nav-links {{ display: flex; gap: 6px; flex-wrap: wrap; }}
  .nav-links a {{ text-decoration: none; color: var(--muted); font-size: 0.82rem; font-weight: 600; padding: 5px 11px; border-radius: 999px; transition: all .15s; }}
  .nav-links a:hover {{ background: var(--accent-soft); color: var(--accent); }}
  .container {{ max-width: 1360px; margin: 0 auto; padding: 18px 22px 48px; }}
  .hero {{ background: var(--surface); border: 1px solid var(--border); border-radius: 14px; padding: 18px 22px; box-shadow: var(--shadow); display: flex; flex-wrap: wrap; justify-content: space-between; align-items: center; gap: 14px; margin-bottom: 14px; }}
  .hero h1 {{ margin: 0; font-size: 1.55rem; letter-spacing: -0.025em; }}
  .subtitle {{ color: var(--muted); font-size: 0.84rem; margin-top: 3px; }}
  .btn {{ background: var(--surface-2); color: var(--text); border: 1px solid var(--border); border-radius: 999px; padding: 7px 14px; cursor: pointer; font-size: 0.81rem; font-weight: 600; }}
  .key-strip {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(125px, 1fr)); gap: 10px; margin-bottom: 14px; background: var(--surface); border: 1px solid var(--border); border-radius: 12px; padding: 11px 16px; box-shadow: var(--shadow); }}
  .key-cell .lbl {{ font-size: 0.7rem; color: var(--muted); text-transform: uppercase; letter-spacing: 0.04em; font-weight: 700; }}
  .key-cell .val {{ font-size: 0.96rem; font-weight: 700; margin-top: 2px; }}
  .kpi-grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(210px, 1fr)); gap: 12px; margin-bottom: 18px; }}
  .kpi-card {{ background: var(--surface); border: 1px solid var(--border); border-radius: 12px; padding: 14px 16px; box-shadow: var(--shadow); }}
  .kpi-label {{ color: var(--muted); font-size: 0.73rem; font-weight: 700; text-transform: uppercase; letter-spacing: 0.04em; }}
  .kpi-val {{ font-size: 1.38rem; font-weight: 800; margin-top: 4px; letter-spacing: -0.02em; }}
  .kpi-sub {{ font-size: 0.8rem; color: var(--muted); margin-top: 2px; }}
  .section-hdr {{ font-size: 1.13rem; font-weight: 800; margin: 24px 0 12px; display: flex; align-items: center; gap: 10px; padding: 9px 14px; background: var(--sec-soft, var(--accent-soft)); border-left: 4px solid var(--sec-accent, var(--accent)); border-radius: 10px; }}
  .section-num {{ background: var(--sec-accent, var(--accent)); color: #ffffff; width: 26px; height: 26px; display: inline-flex; align-items: center; justify-content: center; border-radius: 7px; font-size: 0.84rem; flex-shrink: 0; }}
  .sec-wrap {{ margin-bottom: 10px; }}
  .sec-wrap .card {{ border-top: 3px solid var(--sec-accent, var(--accent)); }}
  .sec-navy {{ --sec-accent: #1e40af; --sec-soft: rgba(30, 64, 175, 0.09); --accent: #1e40af; --accent-soft: rgba(30, 64, 175, 0.09); }}
  .sec-emerald {{ --sec-accent: #047857; --sec-soft: rgba(4, 120, 87, 0.09); --accent: #047857; --accent-soft: rgba(4, 120, 87, 0.09); }}
  .sec-indigo {{ --sec-accent: #6d28d9; --sec-soft: rgba(109, 40, 217, 0.09); --accent: #6d28d9; --accent-soft: rgba(109, 40, 217, 0.09); }}
  .sec-cobalt {{ --sec-accent: #0369a1; --sec-soft: rgba(3, 105, 161, 0.09); --accent: #0369a1; --accent-soft: rgba(3, 105, 161, 0.09); }}
  .sec-amber {{ --sec-accent: #b45309; --sec-soft: rgba(180, 83, 9, 0.10); --accent: #b45309; --accent-soft: rgba(180, 83, 9, 0.10); }}
  .sec-teal {{ --sec-accent: #0f766e; --sec-soft: rgba(15, 118, 110, 0.09); --accent: #0f766e; --accent-soft: rgba(15, 118, 110, 0.09); }}
  .sec-jade {{ --sec-accent: #334155; --sec-soft: rgba(51, 65, 85, 0.09); --accent: #334155; --accent-soft: rgba(51, 65, 85, 0.09); }}
  .sec-cyan {{ --sec-accent: #0891b2; --sec-soft: rgba(8, 145, 178, 0.09); --accent: #0891b2; --accent-soft: rgba(8, 145, 178, 0.09); }}
  [data-theme="dark"] .sec-navy {{ --sec-accent: #60a5fa; --sec-soft: rgba(96, 165, 250, 0.14); --accent: #60a5fa; --accent-soft: rgba(96, 165, 250, 0.14); }}
  [data-theme="dark"] .sec-emerald {{ --sec-accent: #34d399; --sec-soft: rgba(52, 211, 153, 0.14); --accent: #34d399; --accent-soft: rgba(52, 211, 153, 0.14); }}
  [data-theme="dark"] .sec-indigo {{ --sec-accent: #a78bfa; --sec-soft: rgba(167, 139, 250, 0.14); --accent: #a78bfa; --accent-soft: rgba(167, 139, 250, 0.14); }}
  [data-theme="dark"] .sec-cobalt {{ --sec-accent: #38bdf8; --sec-soft: rgba(56, 189, 248, 0.14); --accent: #38bdf8; --accent-soft: rgba(56, 189, 248, 0.14); }}
  [data-theme="dark"] .sec-amber {{ --sec-accent: #fbbf24; --sec-soft: rgba(251, 191, 36, 0.14); --accent: #fbbf24; --accent-soft: rgba(251, 191, 36, 0.14); }}
  [data-theme="dark"] .sec-teal {{ --sec-accent: #2dd4bf; --sec-soft: rgba(45, 212, 191, 0.14); --accent: #2dd4bf; --accent-soft: rgba(45, 212, 191, 0.14); }}
  [data-theme="dark"] .sec-jade {{ --sec-accent: #94a3b8; --sec-soft: rgba(148, 163, 184, 0.15); --accent: #94a3b8; --accent-soft: rgba(148, 163, 184, 0.15); }}
  [data-theme="dark"] .sec-cyan {{ --sec-accent: #22d3ee; --sec-soft: rgba(34, 211, 238, 0.14); --accent: #22d3ee; --accent-soft: rgba(34, 211, 238, 0.14); }}
  .card {{ background: var(--surface); border: 1px solid var(--border); border-radius: 14px; padding: 16px 18px; box-shadow: var(--shadow); margin-bottom: 14px; }}
  .subcard {{ background: var(--surface-2); border: 1px solid var(--border); border-radius: 10px; padding: 11px 13px; }}
  .grid-2 {{ display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 14px; align-items: start; margin-bottom: 14px; }}
  .grid-2 > .card {{ margin-bottom: 0; }}
  .grid-2-tight {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); gap: 10px; align-items: start; }}
  .split-40-60 {{ display: grid; grid-template-columns: 5fr 7fr; gap: 18px; align-items: center; }}
  .mt-12 {{ margin-top: 12px; }}
  .qp-box {{ background: var(--accent-soft); border: 1px solid rgba(2,132,199,0.22); border-radius: 10px; padding: 11px 15px; margin-bottom: 12px; }}
  .qp-box h4 {{ margin: 0 0 5px; font-size: 0.82rem; text-transform: uppercase; letter-spacing: 0.05em; color: var(--accent); }}
  .qp-box ul {{ margin: 0; padding-left: 18px; font-size: 0.85rem; }}
  .badge {{ display: inline-block; padding: 6px 13px; border-radius: 999px; font-size: 0.8rem; font-weight: 700; }}
  .badge-green {{ background: rgba(5,150,105,0.13); color: var(--green); border: 1px solid rgba(5,150,105,0.3); }}
  .badge-amber {{ background: rgba(217,119,6,0.13); color: var(--amber); border: 1px solid rgba(217,119,6,0.3); }}
  .badge-red {{ background: rgba(220,38,38,0.13); color: var(--red); border: 1px solid rgba(220,38,38,0.3); }}
  .decision-box {{ border-radius: 10px; padding: 11px 14px; margin-top: 12px; font-size: 0.87rem; border: 1px solid var(--border); border-left-width: 4px; background: var(--surface-2); }}
  .decision-green {{ border-left-color: var(--green); }} .decision-amber {{ border-left-color: var(--amber); }} .decision-red {{ border-left-color: var(--red); }} .decision-blue {{ border-left-color: var(--accent); }}
  .decision-tag {{ font-size: 0.7rem; text-transform: uppercase; letter-spacing: 0.06em; font-weight: 800; color: var(--accent); display: block; margin-bottom: 2px; }}
  .pill {{ display: inline-block; padding: 2px 8px; border-radius: 999px; font-size: 0.71rem; font-weight: 600; white-space: nowrap; }}
  .pill-green {{ background: rgba(5,150,105,0.13); color: var(--green); }} .pill-blue {{ background: var(--accent-soft); color: var(--accent); }}
  .pill-red {{ background: rgba(220,38,38,0.13); color: var(--red); }} .pill-slate {{ background: var(--surface-2); color: var(--muted); border: 1px solid var(--border); }}
  .text-green {{ color: var(--green); }} .text-amber {{ color: var(--amber); }} .text-red {{ color: var(--red); }}
  .compact-feed-table {{ width: 100%; border-collapse: collapse; font-size: 0.81rem; margin-top: 4px; }}
  .compact-feed-table th, .compact-feed-table td {{ padding: 6px 8px; border-bottom: 1px solid var(--border); vertical-align: top; }}
  .compact-feed-table td.feed-hl {{ width: 54%; line-height: 1.38; }}
  .compact-feed-table td.feed-hl a {{ color: var(--text); text-decoration: none; font-weight: 600; }}
  .compact-feed-table td.feed-hl a:hover {{ color: var(--accent); text-decoration: underline; }}
  .compact-feed-table td.feed-ef {{ width: 26%; }}
  .compact-feed-table td.feed-src {{ width: 20%; white-space: nowrap; font-size: 0.77rem; }}
  .ai-brief-box {{ border-left: 3px solid var(--accent); margin-top: 6px; }}
  .brief-lead {{ font-size: 0.82rem; font-weight: 600; color: var(--text); margin-bottom: 8px; padding-bottom: 6px; border-bottom: 1px dashed var(--border); line-height: 1.4; }}
  .summary-bullets {{ list-style: none; margin: 0; padding: 0; display: grid; gap: 8px; font-size: 0.83rem; line-height: 1.42; }}
  .summary-bullets li {{ display: flex; align-items: flex-start; gap: 8px; }}
  .summary-bullets li .pill {{ margin-top: 2px; flex-shrink: 0; }}
  .brief-text {{ color: var(--text); }}
  .brief-impact {{ font-size: 0.77rem; color: var(--muted); margin-top: 2px; line-height: 1.38; }}
  .brief-impact strong {{ color: var(--accent); font-weight: 700; }}
  .source-strip {{ margin-top: 9px; padding-top: 7px; border-top: 1px dashed var(--border); display: flex; flex-wrap: wrap; align-items: center; gap: 5px; font-size: 0.74rem; }}
  .source-hdr {{ font-weight: 700; color: var(--muted); text-transform: uppercase; letter-spacing: 0.04em; font-size: 0.69rem; margin-right: 2px; }}
  .source-chip {{ display: inline-block; padding: 2px 8px; border-radius: 6px; background: var(--surface); border: 1px solid var(--border); color: var(--accent); text-decoration: none; font-weight: 600; }}
  .source-chip:hover {{ border-color: var(--accent); text-decoration: underline; }}
  .audit-kpis {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(125px, 1fr)); gap: 8px; margin: 10px 0; }}
  .mini-stat {{ background: var(--surface-2); padding: 9px 11px; border-radius: 9px; border: 1px solid var(--border); }}
  .mini-stat .lbl {{ font-size: 0.7rem; color: var(--muted); font-weight: 600; }}
  .mini-stat .v {{ font-size: 1.0rem; font-weight: 800; margin-top: 2px; }}
  table {{ width: 100%; border-collapse: collapse; font-size: 0.82rem; margin-top: 6px; }}
  th, td {{ padding: 7px 9px; border-bottom: 1px solid var(--border); text-align: left; }}
  th {{ color: var(--muted); font-weight: 700; font-size: 0.72rem; text-transform: uppercase; letter-spacing: 0.04em; }}
  th.num, td.num {{ text-align: right; font-variant-numeric: tabular-nums; }}
  .highlight-row {{ background: var(--accent-soft); }}
  .cell-upside {{ background: rgba(5,150,105,0.16); color: var(--green); font-weight: 700; }}
  .cell-fair {{ background: rgba(217,119,6,0.12); color: var(--amber); font-weight: 600; }}
  .cell-downside {{ background: rgba(220,38,38,0.12); color: var(--red); }}
  .chart-box {{ position: relative; height: 225px; width: 100%; }}
  .insight-card {{ background: var(--surface); border: 1px solid var(--border); border-left-width: 4px; border-radius: 12px; padding: 13px 15px; box-shadow: var(--shadow); }}
  .border-green {{ border-left-color: var(--green); }} .border-blue {{ border-left-color: var(--accent); }} .border-amber {{ border-left-color: var(--amber); }}
  .insight-head {{ display: flex; justify-content: space-between; align-items: center; gap: 8px; margin-bottom: 3px; }}
  .insight-head h4 {{ margin: 0; font-size: 0.94rem; }}
  .insight-reading {{ font-size: 0.8rem; font-weight: 700; color: var(--accent); margin-bottom: 5px; }}
  .explain-block {{ margin: 4px 0; font-size: 0.84rem; }}
  .compact-list {{ margin: 5px 0 0; padding-left: 17px; font-size: 0.82rem; color: var(--muted); }}
  .sub, .muted {{ font-size: 0.74rem; color: var(--muted); }}
  .warn-chip {{ display: inline-block; background: rgba(217,119,6,0.15); color: var(--amber); padding: 3px 9px; border-radius: 999px; font-size: 0.74rem; margin: 2px 4px 2px 0; font-weight: 600; }}
  .veto-chip {{ display: inline-block; background: rgba(220,38,38,0.16); color: var(--red); padding: 3px 9px; border-radius: 999px; font-size: 0.74rem; margin: 2px 4px 2px 0; font-weight: 700; }}
  .overflow-x {{ overflow-x: auto; }}
  .range-track {{ position: relative; height: 9px; border-radius: 999px; background: var(--surface-2); border: 1px solid var(--border); margin: 8px 0 5px; }}
  .range-fill {{ height: 100%; border-radius: 999px; background: linear-gradient(90deg, var(--accent), var(--green)); }}
  .range-dot {{ position: absolute; top: 50%; width: 14px; height: 14px; border-radius: 50%; background: var(--text); border: 2.5px solid var(--surface); transform: translate(-50%, -50%); box-shadow: 0 2px 5px rgba(0,0,0,0.28); }}
  .consensus-bar {{ display: flex; height: 10px; border-radius: 999px; overflow: hidden; margin: 8px 0 5px; background: var(--surface-2); border: 1px solid var(--border); }}
  .cbar-buy {{ background: var(--green); }} .cbar-hold {{ background: var(--amber); }} .cbar-sell {{ background: var(--red); }}
  .sim-panel {{ background: var(--surface-2); border: 1px solid var(--border); border-radius: 10px; padding: 12px 14px; margin: 10px 0; }}
  .sim-row {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(160px, 1fr)); gap: 12px; margin-top: 8px; }}
  .sim-row label {{ display: block; font-size: 0.76rem; font-weight: 700; color: var(--muted); }}
  .sim-row input[type=range] {{ width: 100%; accent-color: var(--accent); margin-top: 3px; }}
  .sim-out {{ display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 10px; padding-bottom: 8px; border-bottom: 1px solid var(--border); }}
  @media (max-width: 900px) {{ .grid-2, .split-40-60 {{ grid-template-columns: 1fr; }} }}
</style>
</head>
<body>
<div class="nav-bar">
  <div style="font-weight:800;font-size:0.93rem;">{_esc(sym)} Financial Data Digest</div>
  <div class="nav-links">
    <a href="#intro">0. Intro &amp; Outlook</a>
    <a href="#exec">1. Summary</a>
    <a href="#price-bands">2. Price, Returns &amp; P/E</a>
    <a href="#earnings">3. Earnings Highlights</a>
    <a href="#financials">4. Financials &amp; Cash Flow</a>
    <a href="#valuation">5. Intrinsic DCF</a>
    <a href="#ownership">6. Ownership &amp; Flows</a>
    <a href="#conclusion">7. Key Drivers &amp; Conclusion</a>
  </div>
  <button class="btn" onclick="toggleTheme()">Light / Dark</button>
</div>

<div class="container">
  <div class="hero">
    <div>
      <h1>{_esc(name)} ({_esc(sym)})</h1>
      <div class="subtitle">{_esc(report['sector'])} · {_esc(report['industry'])} · As of {_esc(report['generated_at'])} · Public Exchange &amp; Regulatory Data</div>
    </div>
    <div>
      <span class="badge {tone_badge}">{_esc(stance['label'])} · Quality Index {_esc(report['score'])}/100</span>
    </div>
  </div>

  <div class="decision-box decision-blue" style="margin-top:0;margin-bottom:14px;padding:8px 14px;font-size:0.79rem;">
    <strong>SEBI Educational Disclaimer:</strong> Strictly for quantitative financial education and data analysis using public filings. Not SEBI-registered investment advice, a research report, or a buy/sell/hold recommendation.
  </div>

  <!-- CORE FUNDAMENTAL STRIP -->
  <div class="key-strip">
    <div class="key-cell"><div class="lbl">P/E (TTM)</div><div class="val">{fmt_comma(kd.get('pe_ttm'), 1, 'x')}</div></div>
    <div class="key-cell"><div class="lbl">Price / Book (P/B)</div><div class="val">{fmt_comma(kd.get('pb'), 2, 'x')}</div></div>
    <div class="key-cell"><div class="lbl">EPS (TTM)</div><div class="val">{_esc(curr)} {fmt_comma(kd.get('eps_ttm'), 1)}</div></div>
    <div class="key-cell"><div class="lbl">Book Value / Share</div><div class="val">{_esc(curr)} {fmt_comma(kd.get('book_value'), 1)}</div></div>
    <div class="key-cell"><div class="lbl">ROE</div><div class="val">{fmt_comma(kd.get('roe_pct'), 1, '%')}</div></div>
    <div class="key-cell"><div class="lbl">ROCE</div><div class="val">{fmt_comma(kd.get('roce_pct'), 1, '%')}</div></div>
    <div class="key-cell"><div class="lbl">Dividend Yield</div><div class="val">{fmt_comma(kd.get('div_yield_pct'), 2, '%')}</div></div>
  </div>

  <!-- 4 NON-REDUNDANT HEADLINE METRIC CARDS -->
  <div class="kpi-grid">
    <div class="kpi-card">
      <div class="kpi-label">Current Market Price (CMP)</div>
      <div class="kpi-val">{_esc(curr)} {fmt_comma(report['price'], 1)}</div>
      <div class="kpi-sub">Market Cap: {_esc(curr)} {fmt_comma(report['market_cap_b'], 1)}B · {fmt_comma(kd.get('pct_from_52w_high'), 1, '%')} vs 52W High</div>
    </div>
    <div class="kpi-card">
      <div class="kpi-label">Base 5Y DCF Value (Model)</div>
      <div class="kpi-val">{_esc(curr)} {fmt_comma(dcf['fair_value_per_share'], 1)}</div>
      <div class="kpi-sub {upside_cls}"><strong>{_esc(upside_str)}</strong> (WACC {dcf['wacc_pct']}%)</div>
    </div>
    <div class="kpi-card">
      <div class="kpi-label">External Consensus Mean (Public Feed)</div>
      <div class="kpi-val">{_esc(curr)} {fmt_comma(pt.get('mean'), 1)}</div>
      <div class="kpi-sub">Third-Party Range: {_esc(curr)} {fmt_comma(pt.get('low'), 0)} – {fmt_comma(pt.get('high'), 0)} ({fmt_comma(pt.get('implied_upside_pct'), 1, '%')})</div>
    </div>
    <div class="kpi-card">
      <div class="kpi-label">Solvency &amp; Cash Conversion</div>
      <div class="kpi-val">{fmt_comma(fa['net_debt_to_ebitda'], 2, 'x')} <span style="font-size:0.78rem;font-weight:600;color:var(--muted);">Net Debt/EBITDA</span></div>
      <div class="kpi-sub">Cash Conv. (CFO/EBITDA): {fmt_comma(fa['cfo_to_ebitda'], 2, 'x')} &middot; {_esc(ex['favorable_events_count'])} Pos / {_esc(ex['setbacks_count'])} Risk</div>
    </div>
  </div>

  {intro_section_html}

  <!-- SECTION 1: EXECUTIVE SUMMARY -->
  <div class="sec-wrap sec-navy">
  <div id="exec" class="section-hdr"><span class="section-num">1</span> Executive Summary — Key Takeaways, Material Events &amp; Audit Review</div>
  <div class="card">
    <div class="qp-box">
      <h4>Key Quantitative Highlights</h4>
      <ul>{quick_pointers_html}</ul>
    </div>
    <div class="decision-box {tone_border}" style="margin-top:0;margin-bottom:14px;">
      <span class="decision-tag">Composite Quantitative Tier — {_esc(stance['label'])}</span>
      {_esc(ex['plain_english_verdict'])}
    </div>
    <div class="grid-2" style="margin-bottom:0;">
      <div>
        <h3 style="margin:0 0 6px">Material Corporate Developments &amp; Risk Monitorables</h3>
        {events_html}
        {pros_cons_html}
      </div>
      <div>
        <h3 style="margin:0 0 6px">Audit Opinion, Leverage, Litigation &amp; Macro Risk Review</h3>
        <div style="margin-bottom:8px">{vetoes_html} {warnings_html}</div>
        <div class="audit-kpis">
          <div class="mini-stat"><div class="lbl">Audit Opinion</div><div class="v">{_esc(fa['audit_opinion_status'])}</div></div>
          <div class="mini-stat"><div class="lbl">Net Debt / EBITDA</div><div class="v">{fmt_comma(fa['net_debt_to_ebitda'], 2, 'x')}</div></div>
          <div class="mini-stat"><div class="lbl">Interest Coverage</div><div class="v">{fmt_comma(fa['interest_coverage'], 1, 'x')}</div></div>
          <div class="mini-stat"><div class="lbl">Short-Term Debt %</div><div class="v">{fmt_comma(fa['st_debt_share_pct'], 1, '%')}</div></div>
        </div>
        <ul class="compact-list">{citations_html}</ul>
        <div class="decision-box decision-blue">
          <span class="decision-tag">Credit &amp; Solvency Observation</span>
          {_esc(fa['investor_audit_takeaway'])}
        </div>
      </div>
    </div>
  </div>
  </div>

  <!-- SECTION 2: PRICE ACTION, 5Y RETURNS (IRR/MOIC) & 5Y P/E VALUATION BANDS -->
  <div class="sec-wrap sec-emerald">
  <div id="price-bands" class="section-hdr"><span class="section-num">2</span> Price Action, 5-Year Returns Analysis (IRR/MOIC) &amp; Historical P/E Bands</div>
  <div class="grid-2">
    <div class="card">
      <div style="display:flex;justify-content:space-between;align-items:center;gap:8px;flex-wrap:wrap;margin-bottom:6px;">
        <h3 style="margin:0">CMP, 52-Week Range &amp; Moving Averages</h3>
        <span class="pill {'pill-green' if kd.get('trend_tone') == 'positive' else ('pill-red' if kd.get('trend_tone') == 'warning' else 'pill-blue')}">{_esc(kd.get('trend_signal', 'Tracked'))}</span>
      </div>
      <div style="display:flex;justify-content:space-between;font-size:0.78rem;font-weight:700;">
        <span>52W Low: {_esc(curr)} {fmt_comma(kd.get('low_52w'), 1)} ({fmt_comma(kd.get('pct_above_52w_low'), 1, '%')})</span>
        <span>Range Pos: {kd.get('range_52w_pos_pct', '—')}%</span>
        <span>52W High: {_esc(curr)} {fmt_comma(kd.get('high_52w'), 1)} ({fmt_comma(kd.get('pct_from_52w_high'), 1, '%')})</span>
      </div>
      <div class="range-track">
        <div class="range-fill" style="width:{kd.get('range_52w_pos_pct') or 50}%"></div>
        <div class="range-dot" style="left:{kd.get('range_52w_pos_pct') or 50}%"></div>
      </div>
      <div class="audit-kpis">
        <div class="mini-stat"><div class="lbl">50-DMA</div><div class="v">{_esc(curr)} {fmt_comma(kd.get('dma_50'), 1)}</div><div class="sub">{fmt_comma(kd.get('vs_dma50_pct'), 1, '%')} vs CMP</div></div>
        <div class="mini-stat"><div class="lbl">200-DMA</div><div class="v">{_esc(curr)} {fmt_comma(kd.get('dma_200'), 1)}</div><div class="sub">{fmt_comma(kd.get('vs_dma200_pct'), 1, '%')} vs CMP</div></div>
        <div class="mini-stat"><div class="lbl">90D Technical Support</div><div class="v">{_esc(curr)} {fmt_comma(kd.get('support_level'), 1)}</div><div class="sub">Posture: {_esc(kd.get('entry_zone_label', '—'))}</div></div>
        <div class="mini-stat"><div class="lbl">90D Resistance</div><div class="v">{_esc(curr)} {fmt_comma(kd.get('resistance_level'), 1)}</div><div class="sub">Trailing 90D high</div></div>
      </div>
      <div class="chart-box"><canvas id="chartPrice"></canvas></div>
      <div class="decision-box decision-blue">
        <span class="decision-tag">Technical Trend Observation</span>
        {_esc(kd.get('price_trend_opinion', ''))}
      </div>
    </div>

    <div class="card">
      <div style="display:flex;justify-content:space-between;align-items:center;gap:8px;flex-wrap:wrap;margin-bottom:6px;">
        <h3 style="margin:0">5-Year Historical P/E Band (Mean &plusmn; 1 SD)</h3>
        <span class="pill {'pill-green' if pe_bands.get('tone') == 'positive' else ('pill-red' if pe_bands.get('tone') == 'warning' else 'pill-blue')}">{_esc(pe_bands.get('zone_label', 'Tracked'))}</span>
      </div>
      <div class="audit-kpis">
        <div class="mini-stat"><div class="lbl">Current P/E</div><div class="v">{fmt_comma(pe_bands.get('current_pe'), 1, 'x')}</div><div class="sub">{fmt_comma(pe_bands.get('discount_prem_pct'), 1, '%')} vs 5Y Avg</div></div>
        <div class="mini-stat"><div class="lbl">5Y Avg P/E</div><div class="v">{fmt_comma(pe_bands.get('mean_5y_pe'), 1, 'x')}</div><div class="sub">Historical median norm</div></div>
        <div class="mini-stat"><div class="lbl">-1 SD Bargain</div><div class="v text-green">{fmt_comma(pe_bands.get('minus_1sd_pe'), 1, 'x')}</div><div class="sub">Value comfort floor</div></div>
        <div class="mini-stat"><div class="lbl">+1 SD Expensive</div><div class="v text-red">{fmt_comma(pe_bands.get('plus_1sd_pe'), 1, 'x')}</div><div class="sub">Rich multiple zone</div></div>
      </div>
      <div class="chart-box" style="height:268px"><canvas id="chartPE"></canvas></div>
      <div class="decision-box decision-blue">
        <span class="decision-tag">Historical Valuation Context</span>
        {_esc(pe_bands.get('opinion', ''))}
      </div>
    </div>
  </div>
  {returns_card_html}
  </div>

  <!-- SECTION 3: LATEST EARNINGS HIGHLIGHTS & 4Q SURPRISE ANALYSIS (BEFORE FINANCIALS) -->
  <div class="sec-wrap sec-indigo">
  <div id="earnings" class="section-hdr" style="justify-content:space-between;flex-wrap:wrap;">
    <span style="display:flex;align-items:center;gap:10px;"><span class="section-num">3</span> Latest Earnings Highlights &amp; 4-Quarter Surprise Analysis ({_esc(eh.get('latest_quarter', 'Latest'))} vs {_esc(eh.get('prior_quarter', 'Prior'))})</span>
    <span class="pill {'pill-green' if 'Verified Current' in str(eh_fresh.get('status_label', '')) else 'pill-blue'}">{_esc(eh_fresh.get('status_label', 'Tracked'))}</span>
  </div>
  <div class="card" style="margin-bottom:14px;padding:12px 16px;">
    <div class="audit-kpis" style="margin:0;">
      <div class="mini-stat"><div class="lbl">Latest EPS Beat / Miss</div><div class="v {'text-green' if (eh_ssum.get('latest_surprise_pct') or 0) >= 1.0 else ('text-red' if (eh_ssum.get('latest_surprise_pct') or 0) <= -1.0 else '')}">{f"{eh_ssum['latest_surprise_pct']:+}%" if eh_ssum.get('latest_surprise_pct') is not None else '—'} ({_esc(eh_ssum.get('latest_verdict', '—'))})</div><div class="sub">Act {_esc(curr)} {fmt_comma(eh_ssum.get('latest_eps_actual'), 2)} vs Est {fmt_comma(eh_ssum.get('latest_eps_estimate'), 2)}</div></div>
      <div class="mini-stat"><div class="lbl">4-Quarter Beat Rate</div><div class="v">{eh_ssum.get('beats_count', 0)} / {eh_ssum.get('total_tracked', 0)} Quarters</div><div class="sub">Avg surprise: {f"{eh_ssum['avg_surprise_pct']:+}%" if eh_ssum.get('avg_surprise_pct') is not None else '—'} · 4Q EBIT: {f"{eh_ssum['ebit_margin_4q_delta_bps']:+} bps" if eh_ssum.get('ebit_margin_4q_delta_bps') is not None else '—'}</div></div>
      <div class="mini-stat"><div class="lbl">Next-Q Consensus EPS</div><div class="v">{_esc(curr)} {fmt_comma(eh_fc.get('eps_avg'), 2)}</div><div class="sub">{f"{eh_fc['eps_growth_pct']:+}% YoY expected" if eh_fc.get('eps_growth_pct') is not None else 'Consensus estimate'} ({eh_fc.get('num_analysts') or '—'} analysts)</div></div>
      <div class="mini-stat"><div class="lbl">30D Estimate Revisions</div><div class="v">{f"{eh_fc.get('up_30d', 0)} Up / {eh_fc.get('down_30d', 0)} Down" if eh_fc.get('up_30d') is not None else '—'}</div><div class="sub">Street estimate breadth (last 30d)</div></div>
    </div>
  </div>
  <div class="grid-2">
    <div class="card">
      <h3 style="margin:0 0 8px">A. 4-Quarter EPS Beat/Miss &amp; Margin Progression</h3>
      <div class="chart-box" style="height:205px"><canvas id="chartSurprise"></canvas></div>
      {f'<div class="overflow-x mt-12"><table><thead><tr><th>Quarter End</th><th class="num">Actual EPS</th><th class="num">Est. EPS</th><th class="num">Surprise%</th><th>Verdict</th><th class="num">Gross%</th><th class="num">EBIT%</th><th class="num">PAT%</th></tr></thead><tbody>{eh_surp_trs}</tbody></table></div>' if eh_surp_trs else '<div class="muted">4-quarter EPS surprise history unavailable.</div>'}
      <h4 style="margin:12px 0 6px;font-size:0.86rem;">Key Operating Drivers, Beat/Miss &amp; Revisions</h4>
      {eh_thematic_html}
    </div>
    <div class="card">
      <h3 style="margin:0 0 8px">B. Latest Quarter Bridge &amp; Primary Sources</h3>
      {f'<div class="overflow-x"><table><thead><tr><th>Line Item</th><th class="num">{_esc(eh.get("latest_quarter", "Latest"))}</th><th class="num">{_esc(eh.get("prior_quarter", "Prior"))}</th><th class="num">QoQ Var</th><th class="num">4Q / YoY</th></tr></thead><tbody>{eh_overview_trs}</tbody></table></div>' if eh_overview_trs else '<div class="muted">Quarterly line-item comparison unavailable in feed; refer to Section 4 financial tables.</div>'}
      <h4 style="margin:12px 0 6px;font-size:0.86rem;">Earnings Releases, Concall Transcripts &amp; Quarterly Disclosures</h4>
      {eh_feed_html}
      {f'<div class="subcard mt-12" style="font-size:0.78rem;"><strong>Primary Sources &amp; Attribution:</strong> {eh_sources_html}</div>' if eh_sources_html else ''}
      <div class="decision-box decision-blue">
        <span class="decision-tag">Quarterly Result Takeaway</span>
        {_esc(eh.get('takeaway', ''))}
      </div>
    </div>
  </div>
  </div>

  <!-- SECTION 4: FINANCIAL SUMMARY (FULL-WIDTH CHART + TABLE PAIRS, ZERO CRAMPING) -->
  <div class="sec-wrap sec-cobalt">
  <div id="financials" class="section-hdr"><span class="section-num">4</span> Financial Track Record &amp; Cash Conversion ({_esc(unit)})</div>
  <div class="card">
    <h3 style="margin:0 0 10px">A. 4-Year Year-on-Year Financial Growth &amp; Free Cash Flow</h3>
    <div class="split-40-60">
      <div class="chart-box"><canvas id="chartAnnual"></canvas></div>
      <div class="overflow-x">
        <table>
          <thead><tr><th>Year</th><th class="num">Revenue</th><th class="num">YoY%</th><th class="num">EBITDA</th><th class="num">OPM%</th><th class="num">Profit</th><th class="num">YoY%</th><th class="num">Op. Cash</th><th class="num">Capex</th><th class="num">Free Cash</th></tr></thead>
          <tbody>{annual_trs}</tbody>
        </table>
      </div>
    </div>
    <div class="decision-box decision-blue">
      <span class="decision-tag">Multi-Year Operating &amp; Cash Summary</span>
      {_esc(fs['annual_4y']['investor_opinion'])}
    </div>
  </div>

  <div class="card">
    <h3 style="margin:0 0 10px">B. Last 4 Quarters Trajectory (Quarter-on-Quarter)</h3>
    <div class="split-40-60">
      <div class="chart-box"><canvas id="chartQuarterly"></canvas></div>
      <div class="overflow-x">
        <table>
          <thead><tr><th>Quarter End</th><th class="num">Revenue</th><th class="num">QoQ%</th><th class="num">YoY%</th><th class="num">EBIT</th><th class="num">Margin%</th><th class="num">Profit</th><th class="num">QoQ%</th></tr></thead>
          <tbody>{quarterly_trs}</tbody>
        </table>
      </div>
    </div>
    <div class="decision-box decision-blue">
      <span class="decision-tag">Quarterly Margin &amp; Growth Summary</span>
      {_esc(fs['quarterly_4q']['investor_opinion'])}
    </div>
  </div>
{seg_card_html}
  <div class="grid-2">
    <div class="card">
      <h3 style="margin:0 0 6px">{wc_lbl}. Working Capital &amp; Cash Conversion Cycle</h3>
      <div class="subcard" style="margin-bottom:8px;"><strong>Annual CFO / Net Profit Conversion:</strong> <span class="sub">{cfo_pat_pills}</span></div>
      {f'<div class="overflow-x"><table><thead><tr><th>Efficiency Metric</th>{wc_headers}</tr></thead><tbody>{wc_rows_html}</tbody></table></div>' if wc_rows_html else '<div class="muted">Consolidated working-capital cycle metrics tracked via annual CFO/EBITDA conversion above.</div>'}
      <div class="decision-box decision-blue">
        <span class="decision-tag">Working Capital Efficiency</span>
        {_esc(wc.get('opinion', ''))}
      </div>
    </div>

    <div class="card">
      <h3 style="margin:0 0 6px">{peer_lbl}. Sector Peer Valuation Multiples &amp; Quality Snapshot</h3>
      <div class="chart-box" style="height:175px"><canvas id="chartPeers"></canvas></div>
      <div class="overflow-x">
        <table>
          <thead><tr><th>Company</th><th class="num">Score</th><th class="num">ROIC</th><th class="num">Inc.ROIC</th><th class="num">Cash Conv.</th><th class="num">EV/NOPAT</th><th class="num">FCF Yld</th></tr></thead>
          <tbody>{peer_trs}</tbody>
        </table>
      </div>
      <div class="decision-box decision-blue">
        <span class="decision-tag">Peer Comparison Context</span>
        {_esc(fs['peer_opinion'])}
      </div>
    </div>
  </div>

  </div>

  <!-- SECTION 5: INTRINSIC VALUATION (DCF + SOTP + SENSITIVITY) -->
  <div class="sec-wrap sec-amber">
  <div id="valuation" class="section-hdr"><span class="section-num">5</span> Intrinsic Valuation (Interactive DCF &amp; SOTP Multiples)</div>
  <div class="grid-2">
    <div class="card">
      <h3 style="margin:0 0 8px">5-Year FCFF DCF Forecast &amp; Sensitivity Simulator ({_esc(unit)})</h3>
      <div class="sim-panel">
        <div class="sim-out">
          <div><div class="lbl sub">SIMULATED MODEL VALUE (SENSITIVITY OUTPUT)</div><strong id="simFairPrice" style="font-size:1.32rem;">{_esc(curr)} {fmt_comma(dcf['fair_value_per_share'], 1)}</strong></div>
          <div><div class="lbl sub">IMPLIED VARIANCE VS CMP</div><strong id="simUpside" style="font-size:1.15rem;">{f"{dcf['upside_downside_pct']:+}%" if dcf.get('upside_downside_pct') is not None else '—'}</strong></div>
          <button class="btn" onclick="resetSim()">Reset Base Case</button>
        </div>
        <div class="sim-row">
          <div><label>Yr1 Revenue Growth: <span id="lblG">{dcf['projected_rev_growth_pct']}%</span></label><input id="slG" type="range" min="2" max="22" step="0.5" value="{dcf['projected_rev_growth_pct']}" oninput="runDcfSim()" /></div>
          <div><label>EBIT Operating Margin: <span id="lblM">{dcf['ebit_margin_pct']}%</span></label><input id="slM" type="range" min="5" max="40" step="0.5" value="{dcf['ebit_margin_pct']}" oninput="runDcfSim()" /></div>
          <div><label>Discount Rate (WACC): <span id="lblW">{dcf['wacc_pct']}%</span></label><input id="slW" type="range" min="8.5" max="15.5" step="0.25" value="{dcf['wacc_pct']}" oninput="runDcfSim()" /></div>
        </div>
      </div>
      <div class="chart-box" style="height:200px"><canvas id="chartDCF"></canvas></div>
      <div class="overflow-x">
        <table>
          <thead><tr><th>Forecast</th><th class="num">Growth%</th><th class="num">Est. Rev</th><th class="num">Op. Profit <span class="sub">(NOPAT)</span></th><th class="num">Capex+WC <span class="sub">(Reinv.)</span></th><th class="num">Free Cash</th><th class="num">Today's PV</th></tr></thead>
          <tbody>{dcf_trs}</tbody>
        </table>
      </div>
      <div class="decision-box {tone_border}">
        <span class="decision-tag">DCF Fair Value Assessment</span>
        {_esc(dcf['investor_opinion'])}
      </div>
    </div>

    <div class="card">
      <h3 style="margin:0 0 8px">DCF Fair Price Sensitivity Matrix (vs CMP {_esc(curr)} {fmt_comma(report['price'], 1)})</h3>
      <div class="overflow-x">
        <table>
          <thead><tr><th>Discount \\ Growth</th>{g_headers}</tr></thead>
          <tbody>{sens_trs}</tbody>
        </table>
      </div>
      <h3 style="margin:16px 0 6px">EV / EBITDA &amp; Conglomerate SOTP Valuation Ladder</h3>
      {f'<div class="overflow-x"><table><thead><tr><th>Blended Multiple</th><th class="num">Implied Fair Price</th><th class="num">vs CMP</th></tr></thead><tbody>{sotp_trs}</tbody></table></div>' if sotp_trs else ''}
      <div class="decision-box decision-blue">
        <span class="decision-tag">Multiple &amp; SOTP Assessment</span>
        {_esc(sotp.get('opinion', ''))}
      </div>
    </div>
  </div>

  </div>

  <!-- SECTION 6: SHAREHOLDING, PROMOTER/FPI ACTIONS, NSE FILINGS, RATINGS & BENCHMARK PERFORMANCE -->
  <div class="sec-wrap sec-teal">
  <div id="ownership" class="section-hdr"><span class="section-num">6</span> Shareholding, Promoter &amp; FPI Actions, Deals, Ratings &amp; Benchmark Performance</div>
  <div class="grid-2">
    <div class="card">
      <h3 style="margin:0 0 8px">Shareholding Trend &amp; Institutional Flows ({_esc(sh_lat.get('quarter', 'Latest'))})</h3>
      <div class="audit-kpis">
        <div class="mini-stat"><div class="lbl">Promoters</div><div class="v">{fmt_comma(sh_lat.get('promoters_pct'), 2, '%')}</div><div class="sub">QoQ: {f"{sh_lat.get('promoters_qoq_pp'):+} pp" if sh_lat.get('promoters_qoq_pp') is not None else '—'}</div></div>
        <div class="mini-stat"><div class="lbl">Foreign (FPIs)</div><div class="v">{fmt_comma(sh_lat.get('fiis_pct'), 2, '%')}</div><div class="sub">QoQ: {f"{sh_lat.get('fiis_qoq_pp'):+} pp" if sh_lat.get('fiis_qoq_pp') is not None else '—'}</div></div>
        <div class="mini-stat"><div class="lbl">Domestic (MFs/DII)</div><div class="v">{fmt_comma(sh_lat.get('diis_pct'), 2, '%')}</div><div class="sub">QoQ: {f"{sh_lat.get('diis_qoq_pp'):+} pp" if sh_lat.get('diis_qoq_pp') is not None else '—'}</div></div>
        <div class="mini-stat"><div class="lbl">Public / Inst.</div><div class="v">{fmt_comma(sh_lat.get('public_pct') if sh_lat.get('public_pct') is not None else sh_lat.get('yf_institutions_pct'), 2, '%')}</div><div class="sub">Holders: {fmt_comma(sh_lat.get('shareholders_count') or sh_lat.get('yf_institutions_count'))}</div></div>
      </div>
      {f'<div class="chart-box" style="height:190px"><canvas id="chartShareholding"></canvas></div>' if sh_quarters else ''}
      {f'<div class="overflow-x"><table><thead><tr><th>Holder Category</th>{sh_header}</tr></thead><tbody>{sh_rows_html}</tbody></table></div>' if sh_rows_html else ''}
      <div class="decision-box decision-blue">
        <span class="decision-tag">Ownership &amp; FPI Flow Assessment</span>
        {_esc(own.get('ownership_opinion', ''))}
      </div>
    </div>

    <div class="card">
      <h3 style="margin:0 0 8px">Exchange Filings, Promoter Activity &amp; Bulk / Block Deals</h3>
      {deals_html}
      {f'<div class="overflow-x mt-12"><strong>Regulatory Insider Disclosures (Form C / SE):</strong><table><thead><tr><th>Date</th><th>Insider</th><th>Action</th><th class="num">Shares</th></tr></thead><tbody>{insider_trs}</tbody></table></div>' if insider_trs else ''}
      <div class="decision-box decision-blue">
        <span class="decision-tag">Ownership &amp; Block Activity Takeaway</span>
        {_esc(own.get('deals_opinion', ''))}
      </div>
    </div>
  </div>

  <div class="grid-2">
    <div class="card">
      <h3 style="margin:0 0 8px">External Consensus Distribution &amp; Credit / Brokerage Coverage</h3>
      <div class="audit-kpis">
        <div class="mini-stat"><div class="lbl">Third-Party Analysts</div><div class="v">{_esc(rec.get('total', 0))}</div><div class="sub">Positive {rec.get('strongBuy', 0) + rec.get('buy', 0)} · Neutral {rec.get('hold', 0)} · Cautious {rec.get('sell', 0) + rec.get('strongSell', 0)}</div></div>
        <div class="mini-stat"><div class="lbl">Consensus Mean Est.</div><div class="v">{_esc(curr)} {fmt_comma(pt.get('mean'), 1)}</div><div class="sub">{f"{pt.get('implied_upside_pct'):+}% vs CMP" if pt.get('implied_upside_pct') is not None else '—'}</div></div>
        <div class="mini-stat"><div class="lbl">Low / Median Est.</div><div class="v">{fmt_comma(pt.get('low'), 0)} / {fmt_comma(pt.get('median'), 0)}</div></div>
        <div class="mini-stat"><div class="lbl">High Est.</div><div class="v">{_esc(curr)} {fmt_comma(pt.get('high'), 1)}</div></div>
      </div>
      {f'<div class="consensus-bar"><div class="cbar-buy" style="width:{buy_pct_bar}%"></div><div class="cbar-hold" style="width:{hold_pct_bar}%"></div><div class="cbar-sell" style="width:{sell_pct_bar}%"></div></div><div class="sub" style="margin-bottom:8px">External Feed Split (Not Our Opinion): {buy_pct_bar}% Positive · {hold_pct_bar}% Neutral · {sell_pct_bar}% Cautious</div>' if rec.get('total') else ''}
      {ratings_news_html}
      <div class="decision-box decision-blue">
        <span class="decision-tag">External Market Consensus Note</span>
        {_esc(own.get('ratings_opinion', ''))}
      </div>
    </div>

    <div class="card">
      <h3 style="margin:0 0 8px">Relative Performance vs {_esc(own.get('benchmark_label', 'Nifty 50'))} &amp; Sector Peers</h3>
      <div class="chart-box" style="height:190px"><canvas id="chartPerf"></canvas></div>
      <div class="overflow-x">
        <table>
          <thead><tr><th>Horizon</th><th class="num">{_esc(sym)}</th><th class="num">{_esc(own.get('benchmark_label', 'Nifty 50'))}</th><th class="num">Relative Alpha</th></tr></thead>
          <tbody>{perf_trs}</tbody>
        </table>
      </div>
      {f'<div class="overflow-x mt-12"><strong>12-Month Peer Return &amp; ROIC Leaderboard:</strong><table><thead><tr><th>Peer</th><th class="num">12M Return</th><th class="num">ROIC</th><th class="num">Score</th></tr></thead><tbody>{peer_perf_trs}</tbody></table></div>' if peer_perf_trs else ''}
      <div class="decision-box decision-blue">
        <span class="decision-tag">Relative &amp; Sector Performance Observation</span>
        {_esc(own.get('performance_opinion', ''))}
      </div>
    </div>
  </div>
  {comp_card_html}
  </div>

  <!-- SECTION 7: KEY ANALYTICAL DRIVERS & CONCLUSION -->
  <div class="sec-wrap sec-jade">
  <div id="conclusion" class="section-hdr"><span class="section-num">7</span> Key Analytical Drivers &amp; Conclusion</div>
  <div class="grid-2">
    {insights_html}
  </div>

  <div class="card">
    <h3 style="margin:0 0 10px">Analytical Conclusion &amp; Educational Synthesis</h3>
    <div class="grid-2-tight" style="margin-bottom:12px;">
      <div class="subcard">
        <strong>1. Operating &amp; Solvency Profile</strong>
        <p class="explain-block">{_esc(concl.get('strength_summary') or adv['section_opinion'])}</p>
      </div>
      <div class="subcard">
        <strong>2. Valuation Context vs Base DCF</strong>
        <p class="explain-block">{_esc(concl.get('valuation_context') or dcf['investor_opinion'])}</p>
      </div>
      <div class="subcard">
        <strong>3. Governance &amp; Credit Posture</strong>
        <p class="explain-block">{_esc(concl.get('risk_focus') or fa['investor_audit_takeaway'])}</p>
      </div>
    </div>
    <div class="decision-box {tone_border}" style="margin-top:0;margin-bottom:12px;">
      <span class="decision-tag">Concluding Educational Synthesis</span>
      {_esc(adv['deployment_plan'])}
    </div>
    {rating_framework_html}
    {data_sources_html}
    <div class="muted mt-12" style="border-top:1px solid var(--border);padding-top:10px;">
      <strong>SEBI Regulatory &amp; Educational Notice:</strong> Prepared strictly for educational, informational, and quantitative financial analysis using verified public exchange filings and market data in accordance with <strong>SEBI (Research Analysts) Regulations, 2014</strong> and <strong>SEBI (Investment Advisers) Regulations, 2013</strong> framing. Neither this automated agent nor its output constitutes registered investment advice, portfolio management, or a recommendation to buy, sell, or hold any security.
    </div>
  </div>
  </div>
</div>

<script>
const D = {chart_payload};
const gridColor = 'rgba(148, 163, 184, 0.16)';
const tickColor = '#64748b';

function toggleTheme() {{
  const root = document.documentElement;
  root.setAttribute('data-theme', root.getAttribute('data-theme') === 'dark' ? 'light' : 'dark');
}}

if (document.getElementById('chartPrice') && D.price_dates && D.price_dates.length) {{
  new Chart(document.getElementById('chartPrice'), {{
    type: 'line',
    data: {{
      labels: D.price_dates,
      datasets: [
        {{ label: 'Close Price', data: D.price_closes, borderColor: '#0284c7', backgroundColor: 'rgba(2,132,199,0.08)', fill: true, pointRadius: 0, tension: 0.15, borderWidth: 2.2 }},
        {{ label: '50-DMA', data: D.price_dma50, borderColor: '#059669', pointRadius: 0, borderDash: [4,4], tension: 0.15, borderWidth: 1.7 }},
        {{ label: '200-DMA', data: D.price_dma200, borderColor: '#d97706', pointRadius: 0, borderDash: [6,4], tension: 0.15, borderWidth: 1.7 }}
      ]
    }},
    options: {{ responsive: true, maintainAspectRatio: false, scales: {{ x: {{ ticks: {{ color: tickColor, maxTicksLimit: 6 }}, grid: {{ display: false }} }}, y: {{ ticks: {{ color: tickColor }}, grid: {{ color: gridColor }} }} }}, plugins: {{ legend: {{ labels: {{ color: tickColor }} }} }} }}
  }});
}}

if (document.getElementById('chartPE') && D.pe_dates && D.pe_dates.length) {{
  const peMeanArr = D.pe_dates.map(() => D.pe_mean);
  const pePlusArr = D.pe_dates.map(() => D.pe_plus);
  const peMinusArr = D.pe_dates.map(() => D.pe_minus);
  new Chart(document.getElementById('chartPE'), {{
    type: 'line',
    data: {{
      labels: D.pe_dates,
      datasets: [
        {{ label: 'Trailing P/E (x)', data: D.pe_series, borderColor: '#0284c7', backgroundColor: 'rgba(2,132,199,0.08)', fill: false, pointRadius: 0, tension: 0.2, borderWidth: 2.2 }},
        {{ label: '5Y Avg (' + D.pe_mean + 'x)', data: peMeanArr, borderColor: '#64748b', pointRadius: 0, borderDash: [4,4], borderWidth: 1.6 }},
        {{ label: '+1 SD (' + D.pe_plus + 'x)', data: pePlusArr, borderColor: '#dc2626', pointRadius: 0, borderDash: [6,4], borderWidth: 1.4 }},
        {{ label: '-1 SD (' + D.pe_minus + 'x)', data: peMinusArr, borderColor: '#059669', pointRadius: 0, borderDash: [6,4], borderWidth: 1.4 }}
      ]
    }},
    options: {{ responsive: true, maintainAspectRatio: false, scales: {{ x: {{ ticks: {{ color: tickColor, maxTicksLimit: 6 }}, grid: {{ display: false }} }}, y: {{ ticks: {{ color: tickColor }}, grid: {{ color: gridColor }} }} }}, plugins: {{ legend: {{ labels: {{ color: tickColor }} }} }} }}
  }});
}}

if (document.getElementById('chartReturnsAttr') && D.ret_attr_labels && D.ret_attr_labels.length) {{
  const retColors = D.ret_attr_vals.map((v, idx) => {{
    if (idx === 0) return 'rgba(100,116,139,0.75)';
    if (idx === D.ret_attr_vals.length - 1) return 'rgba(5,150,105,0.85)';
    return v >= 0 ? 'rgba(2,132,199,0.78)' : 'rgba(220,38,38,0.78)';
  }});
  new Chart(document.getElementById('chartReturnsAttr'), {{
    type: 'bar',
    data: {{
      labels: D.ret_attr_labels,
      datasets: [{{ label: 'MOIC Attribution (x)', data: D.ret_attr_vals, backgroundColor: retColors, borderRadius: 6 }}]
    }},
    options: {{
      responsive: true,
      maintainAspectRatio: false,
      scales: {{ x: {{ ticks: {{ color: tickColor }}, grid: {{ display: false }} }}, y: {{ ticks: {{ color: tickColor }}, grid: {{ color: gridColor }} }} }},
      plugins: {{ legend: {{ display: false }}, tooltip: {{ callbacks: {{ label: (ctx) => ctx.parsed.y.toFixed(2) + 'x MOIC' }} }} }}
    }}
  }});
}}

if (document.getElementById('chartSurprise') && D.surp_labels && D.surp_labels.length) {{
  new Chart(document.getElementById('chartSurprise'), {{
    type: 'bar',
    data: {{
      labels: D.surp_labels,
      datasets: [
        {{ label: 'Actual EPS', data: D.surp_actual, backgroundColor: 'rgba(109,40,217,0.82)', borderRadius: 5, yAxisID: 'y' }},
        {{ label: 'Street Estimate', data: D.surp_est, backgroundColor: 'rgba(148,163,184,0.52)', borderRadius: 5, yAxisID: 'y' }},
        {{ label: 'Surprise %', data: D.surp_pct, type: 'line', borderColor: '#059669', backgroundColor: '#059669', tension: 0.25, borderWidth: 2.2, yAxisID: 'y1' }}
      ]
    }},
    options: {{ responsive: true, maintainAspectRatio: false, scales: {{ x: {{ ticks: {{ color: tickColor }}, grid: {{ color: gridColor }} }}, y: {{ ticks: {{ color: tickColor }}, grid: {{ color: gridColor }} }}, y1: {{ position: 'right', ticks: {{ color: '#059669' }}, grid: {{ drawOnChartArea: false }} }} }}, plugins: {{ legend: {{ labels: {{ color: tickColor }} }} }} }}
  }});
}}

new Chart(document.getElementById('chartAnnual'), {{
  type: 'bar',
  data: {{
    labels: D.annual_labels,
    datasets: [
      {{ label: 'Revenue', data: D.annual_rev, backgroundColor: 'rgba(2,132,199,0.72)', borderRadius: 5, yAxisID: 'y' }},
      {{ label: 'Net Profit', data: D.annual_pat, backgroundColor: 'rgba(5,150,105,0.78)', borderRadius: 5, yAxisID: 'y' }},
      {{ label: 'Free Cash', data: D.annual_fcf, backgroundColor: 'rgba(217,119,6,0.78)', borderRadius: 5, yAxisID: 'y' }},
      {{ label: 'OPM %', data: D.annual_opm, type: 'line', borderColor: '#9333ea', backgroundColor: '#9333ea', tension: 0.3, borderWidth: 2.2, yAxisID: 'y1' }}
    ]
  }},
  options: {{ responsive: true, maintainAspectRatio: false, scales: {{ x: {{ ticks: {{ color: tickColor }}, grid: {{ color: gridColor }} }}, y: {{ ticks: {{ color: tickColor }}, grid: {{ color: gridColor }} }}, y1: {{ position: 'right', ticks: {{ color: '#9333ea' }}, grid: {{ drawOnChartArea: false }} }} }}, plugins: {{ legend: {{ labels: {{ color: tickColor }} }} }} }}
}});

new Chart(document.getElementById('chartQuarterly'), {{
  type: 'bar',
  data: {{
    labels: D.q_labels,
    datasets: [
      {{ label: 'Revenue', data: D.q_rev, backgroundColor: 'rgba(2,132,199,0.72)', borderRadius: 5, yAxisID: 'y' }},
      {{ label: 'Net Profit', data: D.q_pat, backgroundColor: 'rgba(5,150,105,0.78)', borderRadius: 5, yAxisID: 'y' }},
      {{ label: 'EBIT Margin %', data: D.q_opm, type: 'line', borderColor: '#d97706', backgroundColor: '#d97706', tension: 0.3, borderWidth: 2.2, yAxisID: 'y1' }}
    ]
  }},
  options: {{ responsive: true, maintainAspectRatio: false, scales: {{ x: {{ ticks: {{ color: tickColor }}, grid: {{ color: gridColor }} }}, y: {{ ticks: {{ color: tickColor }}, grid: {{ color: gridColor }} }}, y1: {{ position: 'right', ticks: {{ color: '#d97706' }}, grid: {{ drawOnChartArea: false }} }} }}, plugins: {{ legend: {{ labels: {{ color: tickColor }} }} }} }}
}});

if (document.getElementById('chartSegments') && D.seg_labels && D.seg_labels.length) {{
  new Chart(document.getElementById('chartSegments'), {{
    type: 'bar',
    data: {{
      labels: D.seg_labels,
      datasets: [
        {{ label: 'Revenue Mix (%)', data: D.seg_rev_mix, backgroundColor: 'rgba(3,105,161,0.76)', borderRadius: 5 }},
        {{ label: 'EBIT Mix (%)', data: D.seg_ebit_mix, backgroundColor: 'rgba(5,150,105,0.80)', borderRadius: 5 }},
        {{ label: 'EBIT Margin (%)', data: D.seg_margins, backgroundColor: 'rgba(217,119,6,0.76)', borderRadius: 5 }}
      ]
    }},
    options: {{ indexAxis: 'y', responsive: true, maintainAspectRatio: false, scales: {{ x: {{ ticks: {{ color: tickColor }}, grid: {{ color: gridColor }} }}, y: {{ ticks: {{ color: tickColor }}, grid: {{ display: false }} }} }}, plugins: {{ legend: {{ labels: {{ color: tickColor }} }} }} }}
  }});
}}

const dcfChart = new Chart(document.getElementById('chartDCF'), {{
  type: 'bar',
  data: {{
    labels: D.dcf_labels,
    datasets: [
      {{ label: 'Projected Free Cash (' + D.unit + ')', data: D.dcf_fcff, backgroundColor: 'rgba(2,132,199,0.72)', borderRadius: 5 }},
      {{ label: 'Present Value Today', data: D.dcf_pv, backgroundColor: 'rgba(5,150,105,0.82)', borderRadius: 5 }}
    ]
  }},
  options: {{ responsive: true, maintainAspectRatio: false, scales: {{ x: {{ ticks: {{ color: tickColor }}, grid: {{ color: gridColor }} }}, y: {{ ticks: {{ color: tickColor }}, grid: {{ color: gridColor }} }} }}, plugins: {{ legend: {{ labels: {{ color: tickColor }} }} }} }}
}});

const baseSlG = document.getElementById('slG').value;
const baseSlM = document.getElementById('slM').value;
const baseSlW = document.getElementById('slW').value;
function resetSim() {{
  document.getElementById('slG').value = baseSlG;
  document.getElementById('slM').value = baseSlM;
  document.getElementById('slW').value = baseSlW;
  runDcfSim();
}}
function runDcfSim() {{
  const g0 = parseFloat(document.getElementById('slG').value) / 100.0;
  const m = parseFloat(document.getElementById('slM').value) / 100.0;
  const w = parseFloat(document.getElementById('slW').value) / 100.0;
  document.getElementById('lblG').textContent = (g0 * 100).toFixed(1) + '%';
  document.getElementById('lblM').textContent = (m * 100).toFixed(1) + '%';
  document.getElementById('lblW').textContent = (w * 100).toFixed(2) + '%';
  const s = D.dcf_sim;
  const tg = s.term_g_pct / 100.0;
  const tax = s.tax_pct / 100.0;
  const reinv0 = s.reinv_pct / 100.0;
  let rev = s.base_rev, pvSum = 0, lastFcff = 0;
  const newFcff = [], newPv = [];
  for (let yr = 1; yr <= 5; yr++) {{
    const sg = g0 - (g0 - tg) * ((yr - 1) / 5.0) * 0.6;
    rev *= (1.0 + sg);
    const nopat = rev * m * (1.0 - tax);
    const fcff = nopat * (1.0 - reinv0 * (1.0 - 0.15 * ((yr - 1) / 4.0)));
    const pv = fcff / Math.pow(1.0 + w, yr);
    pvSum += pv;
    lastFcff = fcff;
    newFcff.push(Math.round(fcff * 10) / 10);
    newPv.push(Math.round(pv * 10) / 10);
  }}
  const tv = (lastFcff * (1.0 + tg)) / Math.max(w - tg, 0.025);
  const eq = pvSum + tv / Math.pow(1.0 + w, 5) - s.net_debt;
  const px = s.shares_scaled > 0 ? eq / s.shares_scaled : 0;
  const up = s.cmp > 0 ? (px / s.cmp - 1.0) * 100.0 : 0;
  document.getElementById('simFairPrice').textContent = s.curr + ' ' + px.toLocaleString(undefined, {{maximumFractionDigits:1, minimumFractionDigits:1}});
  const upEl = document.getElementById('simUpside');
  upEl.textContent = (up >= 0 ? '+' : '') + up.toFixed(1) + '%';
  upEl.style.color = up >= 10 ? 'var(--green)' : (up < -5 ? 'var(--red)' : 'var(--amber)');
  dcfChart.data.datasets[0].data = newFcff;
  dcfChart.data.datasets[1].data = newPv;
  dcfChart.update('none');
}}

new Chart(document.getElementById('chartPeers'), {{
  type: 'bar',
  data: {{
    labels: D.peer_labels,
    datasets: [
      {{ label: 'Quality Score (/100)', data: D.peer_score, backgroundColor: 'rgba(2,132,199,0.75)', borderRadius: 5 }},
      {{ label: 'ROIC (%)', data: D.peer_roic, backgroundColor: 'rgba(5,150,105,0.78)', borderRadius: 5 }}
    ]
  }},
  options: {{ responsive: true, maintainAspectRatio: false, scales: {{ x: {{ ticks: {{ color: tickColor }}, grid: {{ color: gridColor }} }}, y: {{ ticks: {{ color: tickColor }}, grid: {{ color: gridColor }} }} }}, plugins: {{ legend: {{ labels: {{ color: tickColor }} }} }} }}
}});

if (document.getElementById('chartShareholding') && D.sh_labels && D.sh_labels.length) {{
  new Chart(document.getElementById('chartShareholding'), {{
    type: 'line',
    data: {{
      labels: D.sh_labels,
      datasets: [
        {{ label: 'Promoters %', data: D.sh_prom, borderColor: '#0284c7', backgroundColor: '#0284c7', tension: 0.25, borderWidth: 2.2 }},
        {{ label: 'Foreign Inv. (FPIs) %', data: D.sh_fii, borderColor: '#059669', backgroundColor: '#059669', tension: 0.25, borderWidth: 2.2 }},
        {{ label: 'Domestic Funds (DIIs) %', data: D.sh_dii, borderColor: '#d97706', backgroundColor: '#d97706', tension: 0.25, borderWidth: 2.2 }}
      ]
    }},
    options: {{ responsive: true, maintainAspectRatio: false, scales: {{ x: {{ ticks: {{ color: tickColor }}, grid: {{ color: gridColor }} }}, y: {{ ticks: {{ color: tickColor }}, grid: {{ color: gridColor }} }} }}, plugins: {{ legend: {{ labels: {{ color: tickColor }} }} }} }}
  }});
}}

if (document.getElementById('chartPerf') && D.perf_labels && D.perf_labels.length) {{
  new Chart(document.getElementById('chartPerf'), {{
    type: 'bar',
    data: {{
      labels: D.perf_labels,
      datasets: [
        {{ label: D.sym + ' (%)', data: D.perf_stock, backgroundColor: 'rgba(2,132,199,0.78)', borderRadius: 5 }},
        {{ label: D.bench_label + ' (%)', data: D.perf_bench, backgroundColor: 'rgba(100,116,139,0.55)', borderRadius: 5 }}
      ]
    }},
    options: {{ responsive: true, maintainAspectRatio: false, scales: {{ x: {{ ticks: {{ color: tickColor }}, grid: {{ color: gridColor }} }}, y: {{ ticks: {{ color: tickColor }}, grid: {{ color: gridColor }} }} }}, plugins: {{ legend: {{ labels: {{ color: tickColor }} }} }} }}
  }});
}}

if (document.getElementById('chartCompMatrix') && D.comp_points && D.comp_points.length) {{
  const dsComp = D.comp_points.map((pt) => ({{
    label: pt.symbol,
    data: [{{ x: pt.x_roic, y: pt.y_ret12, r: pt.r }}],
    backgroundColor: pt.is_target ? 'rgba(5,150,105,0.72)' : 'rgba(2,132,199,0.52)',
    borderColor: pt.is_target ? '#059669' : '#0284c7',
    borderWidth: pt.is_target ? 2.5 : 1.5
  }}));
  new Chart(document.getElementById('chartCompMatrix'), {{
    type: 'bubble',
    data: {{ datasets: dsComp }},
    options: {{
      responsive: true,
      maintainAspectRatio: false,
      scales: {{
        x: {{ title: {{ display: true, text: 'Capital Efficiency — ROIC (%)', color: tickColor }}, ticks: {{ color: tickColor }}, grid: {{ color: gridColor }} }},
        y: {{ title: {{ display: true, text: '12M Total Return (%)', color: tickColor }}, ticks: {{ color: tickColor }}, grid: {{ color: gridColor }} }}
      }},
      plugins: {{
        legend: {{ labels: {{ color: tickColor }} }},
        tooltip: {{
          callbacks: {{
            label: (ctx) => {{
              const p = D.comp_points[ctx.datasetIndex];
              return p.symbol + ': ROIC ' + p.x_roic + '% | 12M ' + p.y_ret12 + '% | Score ' + p.score + '/100 | MCap $' + p.mcap_b + 'B';
            }}
          }}
        }}
      }}
    }}
  }});
}}
</script>
</body>
</html>"""


def save_web_dashboard(
    report: Dict[str, Any], dashboards_dir: Path
) -> str:
    """Write self-contained interactive HTML dashboard for any analyzed stock."""
    dashboards_dir.mkdir(parents=True, exist_ok=True)
    sym = report["symbol"].replace("/", "_")
    out_path = dashboards_dir / f"{sym}_dashboard.html"
    out_path.write_text(render_web_dashboard_html(report), encoding="utf-8")
    return str(out_path)
