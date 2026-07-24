#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""自治体ページ用：住まい相場・駅乗降のHTML断片生成（reinfolib_tokyo.db 由来JSON）。"""
from __future__ import annotations

import html
import json
import os
import re
from typing import Optional

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
JSON_DIR = os.path.join(ROOT, "docs", "assets", "data", "area")


def esc(s):
    return html.escape(str(s or ""), quote=True)


def fmt_yen(v: Optional[int]) -> str:
    if not v:
        return "—"
    if v >= 100000000:
        return f"{v/100000000:.1f}".rstrip("0").rstrip(".") + "億円"
    if v >= 10000:
        return f"{v/10000:.0f}万円" if v % 10000 == 0 else f"{v/10000:.1f}".rstrip("0").rstrip(".") + "万円"
    return f"{v:,}円"


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


def _bar_chart(items, value_key, label_key, color="#1baf7a"):
    items = [x for x in items if x.get(value_key)]
    if not items:
        return ""
    max_v = max(x[value_key] for x in items)
    if max_v <= 0:
        return ""
    row_h = 28
    h = 16 + row_h * len(items)
    w = 420
    label_w = 108
    bars = []
    for i, it in enumerate(items):
        y = 8 + i * row_h
        bw = max(2, int((w - label_w - 80) * (it[value_key] / max_v)))
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


def _column_chart(items, value_key, label_key, color="#2a78d6"):
    items = [x for x in items if x.get(value_key)]
    if not items:
        return ""
    max_v = max(x[value_key] for x in items)
    if max_v <= 0:
        return ""
    w, h = 420, 150
    pad_l, pad_b, pad_t = 8, 28, 18
    usable_w = w - pad_l * 2
    usable_h = h - pad_b - pad_t
    gap = 8
    bw = max(12, (usable_w - gap * (len(items) - 1)) // len(items))
    bars = []
    for i, it in enumerate(items):
        x = pad_l + i * (bw + gap)
        bh = max(2, int(usable_h * (it[value_key] / max_v)))
        y = pad_t + usable_h - bh
        bars.append(
            f'<rect x="{x}" y="{y}" width="{bw}" height="{bh}" rx="3" fill="{color}" opacity="0.9"/>'
            f'<text x="{x+bw/2}" y="{y-4}" text-anchor="middle" class="lv-val">{esc(it.get("display") or "")}</text>'
            f'<text x="{x+bw/2}" y="{h-8}" text-anchor="middle" class="lv-lbl">{esc(it[label_key])}</text>'
        )
    return (
        f'<svg class="lv-chart" viewBox="0 0 {w} {h}" role="img" '
        f'aria-label="年次推移グラフ" preserveAspectRatio="xMinYMin meet">'
        f'<style>.lv-lbl{{font:600 11px sans-serif;fill:#222}}.lv-val{{font:10px sans-serif;fill:#444}}</style>'
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
    condo = data.get("condo") or {}
    st = data.get("stations") or {}
    tokyo_land = data.get("tokyo_median_residential_yen_sqm")
    tokyo_condo = data.get("tokyo_median_condo_price")
    med = land.get("median_residential_yen_sqm")
    med_com = land.get("median_commercial_yen_sqm")
    latest_condo = condo.get("latest")
    vs_land = land.get("vs_tokyo_pct")
    vs_condo = condo.get("vs_tokyo_pct")

    stats = []
    if latest_condo:
        cls = "成約" if latest_condo.get("price_classification") == "02" else "取引"
        area = latest_condo.get("avg_area")
        area_txt = f"・平均{area}㎡" if area else ""
        vs_txt = f"・都内中央値の約<strong>{vs_condo}%</strong>" if vs_condo else ""
        stats.append(
            f'<div class="lvstat"><span class="lvl">中古マンション平均（{latest_condo["year"]}・{cls}）</span>'
            f'<span class="lvv">{esc(fmt_yen(latest_condo["avg_price"]))}</span>'
            f'<span class="lvs">{latest_condo.get("n") or 0}件{area_txt}{vs_txt}</span></div>'
        )
    if med:
        stats.append(
            f'<div class="lvstat"><span class="lvl">住宅地価（中央値・{land.get("year","")}）</span>'
            f'<span class="lvv">{esc(fmt_yen_sqm(med))}</span>'
            f'{f"<span class=\"lvs\">都内中央値の約<strong>{vs_land}%</strong></span>" if vs_land else ""}</div>'
        )
    if med_com:
        stats.append(
            f'<div class="lvstat"><span class="lvl">商業地価（中央値）</span>'
            f'<span class="lvv">{esc(fmt_yen_sqm(med_com))}</span></div>'
        )
    top = st.get("top") or []
    if top:
        stats.append(
            f'<div class="lvstat"><span class="lvl">乗降が多い駅</span>'
            f'<span class="lvv">{esc(top[0]["name"])}</span>'
            f'<span class="lvs">{esc(fmt_passengers(top[0]["passengers"]))}</span></div>'
        )

    charts = []
    yearly = condo.get("yearly") or []
    if len(yearly) >= 2:
        col_items = [{
            "label": str(y["year"]),
            "value": y["avg_price"],
            "display": fmt_yen(y["avg_price"]).replace("万円", "万"),
        } for y in yearly[-5:]]
        charts.append(
            f'<div class="lvbox"><h3>中古マンション平均価格の推移</h3>'
            f'{_column_chart(col_items, "value", "label", color="#2a78d6")}</div>'
        )
    if med and tokyo_land:
        price_items = [
            {"label": name, "value": med, "display": fmt_yen_sqm(med)},
            {"label": "都内中央値", "value": tokyo_land, "display": fmt_yen_sqm(tokyo_land)},
        ]
        charts.append(
            f'<div class="lvbox"><h3>地価の目安（住宅）</h3>'
            f'{_bar_chart(price_items, "value", "label", color="#eb6834")}</div>'
        )

    if latest_condo and tokyo_condo and len(yearly) < 2:
        condo_items = [
            {"label": name, "value": latest_condo["avg_price"], "display": fmt_yen(latest_condo["avg_price"])},
            {"label": "都内中央値", "value": tokyo_condo, "display": fmt_yen(tokyo_condo)},
        ]
        charts.append(
            f'<div class="lvbox"><h3>中古マンション平均の比較</h3>'
            f'{_bar_chart(condo_items, "value", "label", color="#2a78d6")}</div>'
        )

    st_items = [{
        "label": t["name"],
        "value": t["passengers"],
        "display": fmt_passengers(t["passengers"]),
    } for t in top[:5]]
    if st_items:
        charts.append(
            f'<div class="lvbox"><h3>駅の乗降客数（上位）</h3>'
            f'{_bar_chart(st_items, "value", "label", color="#1baf7a")}</div>'
        )

    if not stats and not charts:
        return ""

    src = data.get("source") or {}
    note = (
        f'出典: {esc(src.get("trade","取引価格情報"))} ／ {esc(src.get("land","地価公示"))} ／ '
        f'{esc(src.get("stations","駅別乗降客数"))}（{esc(src.get("license","国土交通省系オープンデータ"))}）。'
        'マンション価格は件数加重平均、地価は公示等の中央値、乗降は1日あたりの目安です。'
    )

    return (
        '<section class="livability" id="sumai">'
        '<h2 class="fh">住まいの相場・交通の目安</h2>'
        f'<p class="lead2">{esc(name)}の中古マンション相場・地価・主な駅の乗降客数から、住み替えの参考指標を確認できます。</p>'
        f'<div class="lvstats">{"".join(stats)}</div>'
        f'<div class="lvcharts">{"".join(charts)}</div>'
        f'<p class="note">{note}</p>'
        '</section>'
    )


def inject_into_area_html(html_text: str, slug: str) -> str:
    sec = livability_section_html(slug)
    if not sec:
        return html_text
    if 'class="livability"' in html_text:
        return re.sub(
            r'<section class="livability"[^>]*>.*?</section>',
            sec,
            html_text,
            count=1,
            flags=re.S,
        )
    m = re.search(r'(<p class="lead">.*?</p>)', html_text, re.S)
    if not m:
        return html_text
    return html_text[: m.end()] + "\n" + sec + html_text[m.end() :]


if __name__ == "__main__":
    import sys
    slug = sys.argv[1] if len(sys.argv) > 1 else "shibuya"
    print(livability_section_html(slug)[:1200])
