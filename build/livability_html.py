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

# 見出し用アイコン（build_site.py の .hi と同一様式のインラインSVG）
_HI_ICONS = {
    "yen": '<path d="M6 4l6 8 6-8"/><path d="M12 12v8"/><path d="M8 14h8"/><path d="M8 17.5h8"/>',
    "home": '<path d="M4 11l8-7 8 7M6 10v9h12v-9"/>',
    "bars": '<path d="M5 20V11M12 20V4M19 20v-6"/>',
}
def _hi(name):
    return ('<svg class="hi" viewBox="0 0 24 24" fill="none" stroke="currentColor" '
            'stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round" '
            f'aria-hidden="true">{_HI_ICONS[name]}</svg>')


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


def fmt_yen_parts(v: Optional[int]):
    """金額を数値部分と単位に分ける（カテゴリ合計行の数字強調用）。"""
    if not v:
        return "—", ""
    if v >= 100000000:
        s = f"{v/100000000:.2f}".rstrip("0").rstrip(".")
        return s, "億円"
    if v >= 10000:
        man = v / 10000
        if man >= 100:
            return f"{man:,.0f}", "万円"
        s = f"{man:.1f}".rstrip("0").rstrip(".")
        return s, "万円"
    return f"{v:,}", "円"


def fmt_yen_emphasis_html(v: Optional[int]) -> str:
    num, unit = fmt_yen_parts(v)
    if not unit:
        return esc(num)
    return (f'<span class="fig-bnum">{esc(num)}</span>'
            f'<span class="fig-bunit">{esc(unit)}</span>')


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


def _stats_db_path():
    return os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                        "data", "livability_stats.db")


_STATS_CACHE = {}


def _load_stats():
    """{muni_name: {indicator: value}} と 都平均 をキャッシュして返す。"""
    if _STATS_CACHE:
        return _STATS_CACHE
    import sqlite3
    p = _stats_db_path()
    data, meta = {}, {}
    if os.path.exists(p):
        c = sqlite3.connect(p).cursor()
        for nm, ind, val, unit, yr, src in c.execute(
                "SELECT municipality_name,indicator,value,unit,year,source_name FROM municipality_stats"):
            data.setdefault(nm, {})[ind] = val
            meta[ind] = (unit, yr, src)
    avg = {}
    inds = {i for d in data.values() for i in d}
    for i in inds:
        vals = [d[i] for d in data.values() if d.get(i) is not None]
        if vals:
            avg[i] = sum(vals) / len(vals)
    _STATS_CACHE["data"], _STATS_CACHE["avg"], _STATS_CACHE["meta"] = data, avg, meta
    return _STATS_CACHE


def stats_band_html(muni_name):
    """自治体ハブページ用「暮らしデータ」帯。制度データとは別の実態統計(人口・保育等)を、
    都平均との比較つきで表示。data/livability_stats.db が無ければ空文字。"""
    s = _load_stats()
    d = s["data"].get(muni_name)
    if not d:
        return ""
    avg, meta = s["avg"], s["meta"]

    def comma(v):
        return f"{int(round(v)):,}" if v is not None else "—"

    tiles = []
    if d.get("population") is not None:
        tiles.append(("人口", f'{comma(d["population"])}<span class="lu">人</span>', ""))
    if d.get("setai") is not None:
        tiles.append(("世帯数", f'{comma(d["setai"])}<span class="lu">世帯</span>', ""))
    if d.get("taikijido") is not None:
        note = "都平均 {:.1f}人".format(avg.get("taikijido", 0))
        tiles.append(("保育所 待機児童数", f'{comma(d["taikijido"])}<span class="lu">人</span>', note))
    if d.get("hoiku_riyou_rate") is not None:
        note = "都平均 {:.1f}%".format(avg.get("hoiku_riyou_rate", 0))
        tiles.append(("保育サービス利用率", f'{d["hoiku_riyou_rate"]:.1f}<span class="lu">%</span>', note))

    fact_parts = []
    for lbl, val, note in tiles:
        note_html = f'<span class="livnote">{esc(note)}</span>' if note else ""
        fact_parts.append(
            f'<div class="fact"><dt>{esc(lbl)}</dt>'
            f'<dd class="livnum">{val}{note_html}</dd></div>')
    facts = "".join(fact_parts)

    # 比較メーター（保育サービス利用率：この地域 vs 都平均）
    meter = ""
    if d.get("hoiku_riyou_rate") is not None and avg.get("hoiku_riyou_rate"):
        meter = ('<div class="livmeter"><span class="livmeter-cap">保育サービス利用率（都平均との比較）</span>'
                 + _compare_meter(d["hoiku_riyou_rate"], avg["hoiku_riyou_rate"], color="#2a9d6a") + "</div>")

    yr = (meta.get("taikijido") or meta.get("population") or ("", "", ""))[1]
    src_pop = (meta.get("population") or ("", "", "東京都 住民基本台帳"))[2]
    src_hoi = (meta.get("taikijido") or ("", "", "こども家庭庁/東京都"))[2]
    src = (f'<p class="livsrc">出典: {esc(src_pop)}／{esc(src_hoi)}'
           f'（基準時点 {esc(yr)}）。制度の実施状況とあわせて、暮らしの実態の目安としてご参照ください。'
           f' <a href="/kurashi-data/">東京都62自治体のランキングで比べる →</a></p>')

    return (f'<section class="band band-soft"><div class="bandin">'
            f'<h2>{_hi("bars")}暮らしデータ（{esc(muni_name)}）</h2>'
            f'<dl class="facts livgrid">{facts}</dl>{meter}{src}</div></section>')


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


def figures_section_html(slug: str, data: Optional[dict] = None, part: str = "all",
                         benefit_totals: Optional[list] = None) -> str:
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
    if benefit_totals:
        for t in benefit_totals:
            tc = tag_class.get(t.get("ev"), "")
            pc = t.get("color") or ""
            style = f' style="--pc-ev:{esc(pc)}"' if pc else ""
            benefit_rows.append(
                f'<a class="fig-brow fig-cat-total" href="{esc(t["href"])}"{style}>'
                f'<span class="fig-btag {tc}">{esc(t["label"])}</span>'
                f'<span class="fig-blabel">{t["n_amt"]}件 / {t["n_prog"]}制度</span>'
                f'<span class="fig-bval">{fmt_yen_emphasis_html(t["yen_sum"])}</span></a>'
            )
    else:
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

    anim = ('<script>(function(){var r=document.currentScript.closest(".figures");if(!r)return;'
            'if(window.matchMedia("(prefers-reduced-motion:reduce)").matches){r.classList.add("on");return;}'
            'var io=new IntersectionObserver(function(es){es.forEach(function(e){'
            'if(e.isIntersecting){r.classList.add("on");io.disconnect();}});},{threshold:.15});'
            'io.observe(r);})();</script>')

    if part == "benefit":
        if not benefit_block:
            return ""
        return (
            '<section class="figures" id="figures-benefit">'
            f'<div class="figures-intro"><h2>{_hi("yen")}もらえるお金の目安</h2>'
            f'<p>{esc(name)}で受けられる手当・助成を、目的・年代カテゴリごとの合計目安で示しています（金額が分かる制度の上限・月額などを合算）。</p></div>'
            f'<div class="figures-grid">{benefit_block}</div>'
            f'{anim}</section>'
        )
    if part == "place":
        if not place_block:
            return ""
        return (
            '<section class="figures" id="figures">'
            f'<div class="figures-intro"><h2>{_hi("home")}住まい・交通のかかる数字</h2>'
            f'<p>{esc(name)}の中古マンション・住宅地価・駅利用者を、近隣エリアや都内中央値と並べて比較します。{esc(near_note)}</p></div>'
            f'<div class="figures-grid">{place_block}</div>'
            f'<p class="figures-note">{note}</p>{anim}</section>'
        )
    return (
        '<section class="figures" id="figures">'
        '<div class="figures-intro">'
        f'<h2>{_hi("bars")}数字でみるこの地域</h2>'
        f"<p>{esc(name)}で受けられる手当の目安と、住まい・交通にかかる数字を一覧にしました。</p>"
        "</div>"
        f'<div class="figures-grid">'
        f"{benefit_block}{place_block}"
        "</div>"
        f'<p class="figures-note">{note}</p>{anim}</section>'
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
