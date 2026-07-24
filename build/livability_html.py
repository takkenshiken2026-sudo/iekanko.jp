#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""自治体ページ用：住まい相場・駅乗降のHTML断片生成。"""
from __future__ import annotations

import html
import json
import os
from typing import Any, Optional

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
JSON_DIR = os.path.join(ROOT, "docs", "assets", "data", "area")


def esc(s):
    return html.escape(str(s or ""), quote=True)


def fmt_yen_sqm(v: Optional[int]) -> str:
    if not v:
        return "—"
    if v >= 10000:
        return f"{v/10000:.1f}".rstrip("0").rstrip(".") + "万円/㎡"
    return f"{v:,}円/㎡"


def fmt_passengers(v: Optional[int]) -> str:
    if not v:
        return "—"
    if v >= 10000:
        return f"{v/10000:.1f}".rstrip("0").rstrip(".") + "万人/日"
    return f"{v:,}人/日"


def _bar_chart(items, value_key, label_key, max_v=None, color="#1baf7a"):
    """Horizontal SVG bar chart. items: list of dicts."""
    items = [x for x in items if x.get(value_key)]
    if not items:
        return ""
    max_v = max_v or max(x[value_key] for x in items)
    if max_v <= 0:
        return ""
    row_h = 28
    h = 16 + row_h * len(items)
    w = 420
    label_w = 108
    bars = []
    for i, it in enumerate(items):
        y = 8 + i * row_h
        bw = int((w - label_w - 70) * (it[value_key] / max_v))
        bars.append(
            f'<text x="0" y="{y+14}" class="lv-lbl">{esc(it[label_key])}</text>'
            f'<rect x="{label_w}" y="{y+2}" width="{bw}" height="16" rx="3" fill="{color}" opacity="0.9"/>'
            f'<text x="{label_w+bw+6}" y="{y+14}" class="lv-val">{esc(it.get("display") or it[value_key])}</text>'
        )
    return (
        f'<svg class="lv-chart" viewBox="0 0 {w} {h}" role="img" '
        f'aria-label="比較グラフ" preserveAspectRatio="xMinYMin meet">'
        f'<style>.lv-lbl{{font:600 11px sans-serif;fill:#222}}.lv-val{{font:11px sans-serif;fill:#444}}</style>'
        f'{"".join(bars)}</svg>'
    )


def load_summary(slug: str) -> Optional[dict]:
    path = os.path.join(JSON_DIR, f"{slug}.json")
    if not os.path.isfile(path):
        return None
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def livability_section_html(slug: str, data: Optional[dict] = None) -> str:
    data = data or load_summary(slug)
    if not data:
        return ""
    name = data.get("name") or slug
    land = data.get("land") or {}
    st = data.get("stations") or {}
    tokyo_med = data.get("tokyo_median_residential_yen_sqm")
    med = land.get("median_residential_yen_sqm")
    med_com = land.get("median_commercial_yen_sqm")
    vs = land.get("vs_tokyo_pct")

    # price compare bars
    price_items = []
    if med:
        price_items.append({
            "label": name,
            "value": med,
            "display": fmt_yen_sqm(med),
        })
    if tokyo_med:
        price_items.append({
            "label": "都内中央値",
            "value": tokyo_med,
            "display": fmt_yen_sqm(tokyo_med),
        })
    price_svg = _bar_chart(price_items, "value", "label", color="#2a78d6")

    top = st.get("top") or []
    st_items = [{
        "label": t["name"],
        "value": t["passengers"],
        "display": fmt_passengers(t["passengers"]),
    } for t in top[:5]]
    st_svg = _bar_chart(st_items, "value", "label", color="#1baf7a")

    vs_txt = ""
    if vs:
        if vs >= 100:
            vs_txt = f'都内中央値の約<strong>{vs}%</strong>'
        else:
            vs_txt = f'都内中央値の約<strong>{vs}%</strong>'

    stats = []
    if med:
        stats.append(
            f'<div class="lvstat"><span class="lvl">住宅地価（中央値）</span>'
            f'<span class="lvv">{esc(fmt_yen_sqm(med))}</span>'
            f'{f"<span class=\"lvs\">{vs_txt}</span>" if vs_txt else ""}</div>'
        )
    if med_com:
        stats.append(
            f'<div class="lvstat"><span class="lvl">商業地価（中央値）</span>'
            f'<span class="lvv">{esc(fmt_yen_sqm(med_com))}</span></div>'
        )
    if top:
        stats.append(
            f'<div class="lvstat"><span class="lvl">乗降が多い駅</span>'
            f'<span class="lvv">{esc(top[0]["name"])}</span>'
            f'<span class="lvs">{esc(fmt_passengers(top[0]["passengers"]))}</span></div>'
        )
    n_st = st.get("n_stations") or 0
    if n_st:
        stats.append(
            f'<div class="lvstat"><span class="lvl">駅数（目安）</span>'
            f'<span class="lvv">{n_st}駅</span></div>'
        )

    charts = []
    if price_svg:
        charts.append(
            f'<div class="lvbox"><h3>地価の目安（住宅）</h3>{price_svg}</div>'
        )
    if st_svg:
        charts.append(
            f'<div class="lvbox"><h3>駅の乗降客数（上位）</h3>{st_svg}</div>'
        )

    if not stats and not charts:
        return ""

    src = data.get("source") or {}
    note = (
        f'出典: {esc(src.get("land","地価公示"))} ／ {esc(src.get("stations","駅別乗降客数"))}'
        f'（{esc(src.get("license","CC BY 4.0"))}）。'
        '地価は公示価格の中央値、乗降は1日あたりの目安です。実際の売買・家賃とは異なります。'
    )

    return (
        '<section class="livability" id="sumai">'
        '<h2 class="fh">住まいの相場・交通の目安</h2>'
        f'<p class="lead2">{esc(name)}の地価と主な駅の乗降客数から、住み替えの参考指標を確認できます。</p>'
        f'<div class="lvstats">{"".join(stats)}</div>'
        f'<div class="lvcharts">{"".join(charts)}</div>'
        f'<p class="note">{note}</p>'
        '</section>'
    )


def inject_into_area_html(html_text: str, slug: str) -> str:
    """自治体ハブHTMLの lead の直後に livability セクションを挿入（既存なら置換）。"""
    import re
    sec = livability_section_html(slug)
    if not sec:
        return html_text
    # replace existing
    if 'class="livability"' in html_text:
        return re.sub(
            r'<section class="livability"[^>]*>.*?</section>',
            sec,
            html_text,
            count=1,
            flags=re.S,
        )
    # insert after first lead paragraph
    m = re.search(r'(<p class="lead">.*?</p>)', html_text, re.S)
    if not m:
        return html_text
    pos = m.end()
    return html_text[:pos] + "\n" + sec + html_text[pos:]


if __name__ == "__main__":
    import sys
    slug = sys.argv[1] if len(sys.argv) > 1 else "shibuya"
    print(livability_section_html(slug)[:800])
