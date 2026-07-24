#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
自治体ハブ「数字でみる」ダッシュボード HTML。
方針: 数字優先 / 3層（もらえる・かかる・まち）/ グラフは都内比較に絞る。
"""
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


def fmt_yen(v: Optional[int], kind="absolute") -> str:
    if not v:
        return "—"
    if kind == "sqm":
        if v >= 10000:
            s = f"{v/10000:.1f}".rstrip("0").rstrip(".")
            return f"{s}万円/㎡"
        return f"{v:,}円/㎡"
    if v >= 100000000:
        s = f"{v/100000000:.2f}".rstrip("0").rstrip(".")
        return f"{s}億円"
    if v >= 10000:
        man = v / 10000
        if man >= 100:
            return f"{man:,.0f}万円"
        s = f"{man:.1f}".rstrip("0").rstrip(".")
        return f"{s}万円"
    return f"{v:,}円"


def fmt_pax(v: Optional[int]) -> str:
    if not v:
        return "—"
    if v >= 10000:
        s = f"{v/10000:.1f}".rstrip("0").rstrip(".")
        return f"{s}万人"
    return f"{v:,}人"


def load_snapshot(slug: str) -> Optional[dict]:
    path = os.path.join(JSON_DIR, f"{slug}.snapshot.json")
    if not os.path.isfile(path):
        # fallback to reinfolib json only
        base = os.path.join(JSON_DIR, f"{slug}.json")
        if not os.path.isfile(base):
            return None
        with open(base, encoding="utf-8") as f:
            h = json.load(f)
        return {
            "slug": slug,
            "name": h.get("name") or slug,
            "benefits": [],
            "housing": {
                "land": h.get("land"),
                "condo": h.get("condo"),
                "tokyo_median_residential_yen_sqm": h.get("tokyo_median_residential_yen_sqm"),
                "tokyo_median_condo_price": h.get("tokyo_median_condo_price"),
            },
            "stations": h.get("stations"),
            "source": h.get("source"),
        }
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _compare_meter(value, ref, color="#2a78d6"):
    """この地域 vs 都内中央値。value/ref を1本のメーターで示す。"""
    if not value or not ref:
        return ""
    top = max(value, ref)
    pct_v = max(4, min(100, round(100 * value / top)))
    pct_r = max(4, min(100, round(100 * ref / top)))
    return (
        f'<div class="fig-meter" style="--c:{color}">'
        f'<div class="fig-meter-row"><span>この地域</span>'
        f'<div class="fig-meter-track"><i style="width:{pct_v}%"></i></div></div>'
        f'<div class="fig-meter-row muted"><span>都内中央値</span>'
        f'<div class="fig-meter-track"><i class="ref" style="width:{pct_r}%"></i></div></div>'
        f"</div>"
    )


def _compare_bars(rows, kind="absolute", color="#2a78d6"):
    """近隣＋都内中央値の横棒比較。rows: [{key,name,value,href}]"""
    rows = [r for r in (rows or []) if r.get("value")]
    if len(rows) < 2:
        return ""
    mx = max(r["value"] for r in rows)
    items = []
    for r in rows:
        pct = max(3, round(100 * r["value"] / mx))
        cls = f' fig-{r.get("key","")}'
        label = esc(r["name"])
        if r.get("key") == "self":
            label = f'{label}<em>この地域</em>'
        if kind == "pax":
            val = esc(fmt_pax(r["value"])) + "/日"
        else:
            val = esc(fmt_yen(r["value"], "sqm" if kind == "sqm" else "absolute"))
        inner = (
            f'<span class="fig-cmp-name">{label}</span>'
            f'<span class="fig-cmp-bar"><i style="--w:{pct}%"></i></span>'
            f'<span class="fig-cmp-n">{val}</span>'
        )
        if r.get("href"):
            items.append(f'<li class="{cls.strip()}"><a href="{esc(r["href"])}">{inner}</a></li>')
        else:
            items.append(f'<li class="{cls.strip()}"><div>{inner}</div></li>')
    return (
        f'<ul class="fig-cmp" style="--c:{color}">{"".join(items)}</ul>'
    )


def _station_bars(top):
    items = [t for t in (top or []) if t.get("passengers")]
    if not items:
        return ""
    mx = max(t["passengers"] for t in items)
    rows = []
    for t in items[:5]:
        pct = max(3, round(100 * t["passengers"] / mx))
        rows.append(
            f'<li><span class="fig-st-name">{esc(t["name"])}</span>'
            f'<span class="fig-st-bar"><i style="--w:{pct}%"></i></span>'
            f'<span class="fig-st-n">{esc(fmt_pax(t["passengers"]))}/日</span></li>'
        )
    return f'<ul class="fig-st-list">{"".join(rows)}</ul>'


def figures_section_html(slug: str, data: Optional[dict] = None) -> str:
    data = data or load_snapshot(slug)
    if not data:
        return ""
    name = data.get("name") or slug
    benefits = data.get("benefits") or []
    housing = data.get("housing") or {}
    land = housing.get("land") or {}
    condo = housing.get("condo") or {}
    stations = data.get("stations") or {}
    latest = condo.get("latest")
    compare = data.get("compare") or {}

    # ── もらえるお金 ──
    tag_class = {
        "childcare": "g-child",
        "pregnancy_birth": "g-birth",
        "moving": "g-house",
        "retirement_unemployment": "g-life",
        "elderly_care": "g-senior",
    }
    benefit_rows = []
    for b in benefits:
        rank_txt = ""
        if b.get("rank") and b.get("n_ranked"):
            rank_txt = f'<span class="fig-rank">都内{b["rank"]}/{b["n_ranked"]}</span>'
        tc = tag_class.get(b.get("group"), "")
        benefit_rows.append(
            f'<a class="fig-brow" href="{esc(b["href"])}">'
            f'<span class="fig-btag {tc}">{esc(b["group_label"])}</span>'
            f'<span class="fig-blabel">{esc(b["label"])}</span>'
            f'<span class="fig-bunit">{esc(b["unit"])}</span>'
            f'<span class="fig-bval">{esc(fmt_yen(b["yen"]))}</span>'
            f"{rank_txt}</a>"
        )
    benefit_block = ""
    if benefit_rows:
        benefit_block = (
            '<div class="fig-panel" data-fig="benefit">'
            '<header class="fig-head">'
            "<h3>もらえるお金の目安</h3>"
            "<p>自治体で差が出やすい手当・助成（金額が分かるもの）</p>"
            "</header>"
            f'<div class="fig-brows">{"".join(benefit_rows)}</div>'
            f'<p class="fig-more"><a href="/hikaku/">制度ごとの自治体比較を見る</a></p>'
            "</div>"
        )

    # ── 住まい・交通（3列） ──
    near_names = [n["name"] for n in (data.get("neighbors") or [])]
    near_note = f'近隣は{"・".join(near_names)}と比較。' if near_names else ""
    place_cards = []

    if latest:
        cls = "成約" if latest.get("price_classification") == "02" else "取引"
        vs = condo.get("vs_tokyo_pct")
        vs_html = f'<span class="fig-vs">都内中央値の <strong>{vs}%</strong></span>' if vs else ""
        area = latest.get("avg_area")
        sub = f'{latest.get("n") or 0}件'
        if area:
            sub += f" · 平均{area}㎡"
        bars = _compare_bars(compare.get("condo"), kind="absolute", color="#2a78d6")
        place_cards.append(
            f'<div class="fig-card" data-card="condo">'
            f'<span class="fig-kicker">中古マンション平均 · {latest["year"]}年（{cls}）</span>'
            f'<span class="fig-big">{esc(fmt_yen(latest["avg_price"]))}</span>'
            f'<span class="fig-sub">{esc(sub)}</span>'
            f"{vs_html}"
            f'<div class="fig-cost-chart">'
            f'<span class="fig-side-label">近隣・都内中央値</span>'
            f"{bars}</div>"
            f"</div>"
        )

    med = land.get("median_residential_yen_sqm")
    if med:
        vs = land.get("vs_tokyo_pct")
        vs_html = f'<span class="fig-vs">都内中央値の <strong>{vs}%</strong></span>' if vs else ""
        bars = _compare_bars(compare.get("land"), kind="sqm", color="#c45c26")
        place_cards.append(
            f'<div class="fig-card" data-card="land">'
            f'<span class="fig-kicker">住宅地価の中央値 · {land.get("year","")}年</span>'
            f'<span class="fig-big">{esc(fmt_yen(med, "sqm"))}</span>'
            f'<span class="fig-sub">公示地価ポイントの中央値</span>'
            f"{vs_html}"
            f'<div class="fig-cost-chart">'
            f'<span class="fig-side-label">近隣・都内中央値</span>'
            f"{bars}</div>"
            f"</div>"
        )

    top = stations.get("top") or []
    sum5 = stations.get("sum_top5_passengers")
    st_list = _station_bars(top)
    if sum5:
        vs = stations.get("vs_tokyo_pct")
        vs_html = f'<span class="fig-vs">都内中央値の <strong>{vs}%</strong></span>' if vs else ""
        year = stations.get("year") or "最新"
        top_name = (top[0].get("name") if top else None) or ""
        sub = "上位5駅の合計"
        if top_name:
            sub += f" · 最大は{top_name}"
        bars = _compare_bars(compare.get("stations"), kind="pax", color="#1baf7a")
        place_cards.append(
            f'<div class="fig-card" data-card="station">'
            f'<span class="fig-kicker">駅の利用者数 · {esc(str(year))}年</span>'
            f'<span class="fig-big">{esc(fmt_pax(sum5))}/日</span>'
            f'<span class="fig-sub">{esc(sub)}</span>'
            f"{vs_html}"
            f'<div class="fig-cost-chart">'
            f'<span class="fig-side-label">近隣・都内中央値</span>'
            f"{bars}</div>"
            f"</div>"
        )

    place_block = ""
    if place_cards:
        extras = []
        med_com = land.get("median_commercial_yen_sqm")
        if med_com:
            extras.append(
                f'<div class="fig-cost slim">'
                f'<span class="fig-kicker">商業地価の中央値</span>'
                f'<span class="fig-mid">{esc(fmt_yen(med_com, "sqm"))}</span>'
                f"</div>"
            )
        if st_list:
            extras.append(
                f'<div class="fig-st-wrap">'
                f'<span class="fig-side-label">この地域の主な駅</span>'
                f"{st_list}</div>"
            )
        place_block = (
            '<div class="fig-panel" data-fig="place">'
            '<header class="fig-head">'
            "<h3>住まい・交通のかかる数字</h3>"
            f"<p>中古マンション・住宅地価・駅利用者を、近隣エリアと都内中央値と並べて比較します。"
            f"{esc(near_note)}</p>"
            "</header>"
            f'<div class="fig-tri">{"".join(place_cards)}</div>'
            f'{"".join(extras)}'
            "</div>"
        )

    if not (benefit_block or place_block):
        return ""

    src = data.get("source") or {}
    note = (
        "手当は各制度の公式情報から抽出した上限・月額の目安です。"
        f"住宅は{esc(src.get('trade','取引・成約価格'))}と{esc(src.get('land','地価公示等'))}、"
        f"駅は{esc(src.get('stations','駅別乗降客数'))}に基づきます。"
        "条件・時点により実際の金額は異なります。"
    )

    return (
        '<section class="figures" id="figures">'
        '<div class="figures-intro">'
        '<h2>数字でみるこの地域</h2>'
        f"<p>{esc(name)}で受けられる手当の目安と、住まい・交通にかかる数字を一覧にしました。</p>"
        "</div>"
        f'<div class="figures-grid">'
        f"{benefit_block}{place_block}"
        "</div>"
        f'<p class="figures-note">{note}</p>'
        '<script>(function(){var r=document.querySelector(".figures");if(!r)return;'
        'if(window.matchMedia("(prefers-reduced-motion:reduce)").matches){r.classList.add("on");return;}'
        'var io=new IntersectionObserver(function(es){es.forEach(function(e){'
        'if(e.isIntersecting){r.classList.add("on");io.disconnect();}});},{threshold:.15});'
        "io.observe(r);})();</script>"
        "</section>"
    )


# 互換: 旧 livability 呼び出し名
def livability_section_html(slug: str, data: Optional[dict] = None) -> str:
    return figures_section_html(slug, data)


def inject_into_area_html(html_text: str, slug: str) -> str:
    sec = figures_section_html(slug)
    if not sec:
        return html_text
    # replace old livability OR figures
    if 'class="figures"' in html_text or 'class="livability"' in html_text:
        html_text = re.sub(
            r'<section class="(?:figures|livability)"[^>]*>.*?</section>',
            sec,
            html_text,
            count=1,
            flags=re.S,
        )
        return html_text
    m = re.search(r'(<p class="lead">.*?</p>)', html_text, re.S)
    if not m:
        return html_text
    return html_text[: m.end()] + "\n" + sec + html_text[m.end() :]


if __name__ == "__main__":
    import sys
    slug = sys.argv[1] if len(sys.argv) > 1 else "shibuya"
    print(figures_section_html(slug)[:1500])
