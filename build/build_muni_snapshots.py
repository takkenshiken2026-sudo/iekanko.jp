#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
自治体ハブ用スナップショット生成。
- 手当・助成の金額目安（hikaku から抽出）
- 住まい・交通（reinfolib JSON）
→ docs/assets/data/area/<slug>.snapshot.json
"""
from __future__ import annotations

import json
import math
import os
import re
import sqlite3
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT_DIR = os.path.join(ROOT, "docs", "assets", "data", "area")
HIKAKU = os.path.join(ROOT, "docs", "hikaku")
DB_PATH = os.path.join(ROOT, "data", "reinfolib_tokyo.db")

# (cid, 短いラベル, 単位表示, 抽出モード, グループ)
BENEFIT_SPECS = [
    ("child_hoiku_gen", "保育料補助", "月額上限", "hoiku_cap", "childcare"),
    ("child_iwai", "出産・入学祝金", "支給額", "child_gift", "childcare"),
    ("preg_shussanhi", "出産費用助成", "支給額", "birth_aid", "pregnancy_birth"),
    ("house_taishin", "耐震改修助成", "改修上限", "taishin_cap", "moving"),
    ("low_aircon", "エアコン設置助成", "助成上限", "aircon_cap", "retirement_unemployment"),
    ("eld_omutsu", "高齢者紙おむつ", "月額上限", "monthly_cap", "elderly_care"),
    ("eld_hochoki", "補聴器助成", "購入上限", "purchase_cap", "elderly_care"),
    ("dis_teate", "障害者福祉手当", "月額", "monthly", "elderly_care"),
]

GROUP_LABEL = {
    "childcare": "子育て",
    "pregnancy_birth": "出産",
    "moving": "住まい",
    "retirement_unemployment": "生活支援",
    "elderly_care": "シニア",
}

YOMI = {
 "千代田区":"ちよだ","中央区":"ちゅうおう","港区":"みなと","新宿区":"しんじゅく","文京区":"ぶんきょう",
 "台東区":"たいとう","墨田区":"すみだ","江東区":"こうとう","品川区":"しながわ","目黒区":"めぐろ",
 "大田区":"おおた","世田谷区":"せたがや","渋谷区":"しぶや","中野区":"なかの","杉並区":"すぎなみ",
 "豊島区":"としま","北区":"きた","荒川区":"あらかわ","板橋区":"いたばし","練馬区":"ねりま",
 "足立区":"あだち","葛飾区":"かつしか","江戸川区":"えどがわ",
 "八王子市":"はちおうじ","立川市":"たちかわ","武蔵野市":"むさしの","三鷹市":"みたか","青梅市":"おうめ",
 "府中市":"ふちゅう","昭島市":"あきしま","調布市":"ちょうふ","町田市":"まちだ","小金井市":"こがねい",
 "小平市":"こだいら","日野市":"ひの","東村山市":"ひがしむらやま","国分寺市":"こくぶんじ","国立市":"くにたち",
 "福生市":"ふっさ","狛江市":"こまえ","東大和市":"ひがしやまと","清瀬市":"きよせ","東久留米市":"ひがしくるめ",
 "武蔵村山市":"むさしむらやま","多摩市":"たま","稲城市":"いなぎ","羽村市":"はむら","あきる野市":"あきるの",
 "西東京市":"にしとうきょう","瑞穂町":"みずほ","日の出町":"ひので","檜原村":"ひのはら","奥多摩町":"おくたま",
 "大島町":"おおしま","利島村":"としま","新島村":"にいじま","神津島村":"こうづしま","三宅村":"みやけ",
 "御蔵島村":"みくらじま","八丈町":"はちじょう","青ヶ島村":"あおがしま","小笠原村":"おがさわら",
}


def _load_extract():
    path = os.path.join(ROOT, "build", "build_site.py")
    code = open(path, encoding="utf-8").read().split("\ncon = sqlite3.connect")[0]
    ns = {"__file__": path, "__name__": "build_site_partial"}
    exec(code, ns)
    return ns["extract_rank_yen"], ns["SLUGS"]


def parse_hikaku(cid, extract_rank_yen, mode):
    path = os.path.join(HIKAKU, cid, "index.html")
    if not os.path.isfile(path):
        return {}
    html = open(path, encoding="utf-8").read()
    out = {}
    for href, name, amt in re.findall(
        r'<tr><td class="mn"><a href="([^"]+)">([^<]+)</a></td><td>(.*?)</td>',
        html,
        re.S,
    ):
        plain = re.sub(r"<[^>]+>", "", amt).strip()
        yen = extract_rank_yen(plain, mode)
        if yen is None:
            continue
        m = re.search(r"/area/tokyo/([^/]+)/", href)
        if not m:
            continue
        slug = m.group(1)
        href_path = href if href.startswith("/") else "/" + href
        cur = out.get(slug)
        if cur is None or yen > cur["yen"]:
            out[slug] = {"yen": yen, "href": href_path, "raw": plain[:120]}
    return out


def rank_map(by_slug):
    """slug -> 1-based rank (higher yen = better rank)."""
    ordered = sorted(by_slug.items(), key=lambda x: (-x[1]["yen"], x[0]))
    return {slug: i for i, (slug, _) in enumerate(ordered, 1)}, len(ordered)


def load_centroids(code_to_slug):
    """municipality_code -> (lat, lon) from reinfolib DB."""
    if not os.path.isfile(DB_PATH):
        return {}
    con = sqlite3.connect(DB_PATH)
    out = {}
    for code, lat, lon in con.execute(
        "SELECT municipality_code, AVG(latitude), AVG(longitude) "
        "FROM land_price_points WHERE latitude IS NOT NULL AND longitude IS NOT NULL "
        "GROUP BY municipality_code"
    ):
        if code in code_to_slug and lat and lon:
            out[code] = (float(lat), float(lon))
    con.close()
    return out


def neighbor_slugs(slug, slug_to_code, code_to_slug, centroids, name_by_slug, n=3):
    """地理的に近い自治体。座標が無ければ五十音の前後。"""
    code = slug_to_code.get(slug)
    if code and code in centroids:
        lat, lon = centroids[code]
        dists = []
        for c, (la, lo) in centroids.items():
            if c == code:
                continue
            s = code_to_slug.get(c)
            if not s:
                continue
            dists.append((math.hypot(lat - la, lon - lo), s))
        dists.sort()
        return [s for _, s in dists[:n]]
    # fallback: yomi neighbors
    ordered = sorted(name_by_slug.keys(), key=lambda s: YOMI.get(name_by_slug[s], name_by_slug[s]))
    try:
        i = ordered.index(slug)
    except ValueError:
        return []
    near = []
    for j in range(1, 6):
        if i - j >= 0:
            near.append(ordered[i - j])
        if i + j < len(ordered):
            near.append(ordered[i + j])
        if len(near) >= n:
            break
    return near[:n]


def housing_metrics(housing):
    land = (housing or {}).get("land") or {}
    condo = (housing or {}).get("condo") or {}
    latest = condo.get("latest") or {}
    stations = (housing or {}).get("stations") or {}
    top = stations.get("top") or []
    top0 = top[0] if top else {}
    return {
        "condo_avg_price": latest.get("avg_price"),
        "land_median_yen_sqm": land.get("median_residential_yen_sqm"),
        "station_sum_top5": stations.get("sum_top5_passengers") or None,
        "station_top_passengers": top0.get("passengers"),
        "station_top_name": top0.get("name"),
    }


def median_int(vals):
    vals = sorted(v for v in vals if v)
    if not vals:
        return None
    n = len(vals)
    mid = n // 2
    if n % 2:
        return int(vals[mid])
    return int(round((vals[mid - 1] + vals[mid]) / 2))


def main():
    extract_rank_yen, slugs_by_name = _load_extract()
    name_by_slug = {v: k for k, v in slugs_by_name.items()}
    slug_to_code = {}
    code_to_slug = {}
    # codes from reinfolib json / municipalities via name match in area json
    for slug, name in name_by_slug.items():
        base_path = os.path.join(OUT_DIR, f"{slug}.json")
        if os.path.isfile(base_path):
            with open(base_path, encoding="utf-8") as f:
                h = json.load(f)
            code = h.get("city_code")
            if code:
                slug_to_code[slug] = code
                code_to_slug[code] = slug

    centroids = load_centroids(code_to_slug)

    # benefit matrices
    matrices = {}
    for cid, label, unit, mode, group in BENEFIT_SPECS:
        data = parse_hikaku(cid, extract_rank_yen, mode)
        ranks, n = rank_map(data)
        matrices[cid] = {
            "label": label,
            "unit": unit,
            "mode": mode,
            "group": group,
            "group_label": GROUP_LABEL[group],
            "n_ranked": n,
            "by_slug": data,
            "rank": ranks,
        }

    # preload all housing for neighbor charts
    housing_by_slug = {}
    for slug in name_by_slug:
        base_path = os.path.join(OUT_DIR, f"{slug}.json")
        if os.path.isfile(base_path):
            with open(base_path, encoding="utf-8") as f:
                housing_by_slug[slug] = json.load(f)

    tokyo_station = median_int(
        housing_metrics(h)["station_sum_top5"] for h in housing_by_slug.values()
    )

    os.makedirs(OUT_DIR, exist_ok=True)
    n_out = 0
    for slug, name in name_by_slug.items():
        housing = housing_by_slug.get(slug) or {}

        benefits = []
        for cid, label, unit, mode, group in BENEFIT_SPECS:
            mat = matrices[cid]
            row = mat["by_slug"].get(slug)
            if not row:
                continue
            benefits.append({
                "cid": cid,
                "label": label,
                "unit": unit,
                "group": group,
                "group_label": mat["group_label"],
                "yen": row["yen"],
                "href": row["href"],
                "rank": mat["rank"].get(slug),
                "n_ranked": mat["n_ranked"],
                "hikaku": f"/hikaku/{cid}/",
            })

        group_order = {g: i for i, g in enumerate(GROUP_LABEL)}
        benefits.sort(key=lambda b: (group_order.get(b["group"], 99), -b["yen"]))

        near = neighbor_slugs(slug, slug_to_code, code_to_slug, centroids, name_by_slug, n=3)
        neighbors = []
        for ns in near:
            h = housing_by_slug.get(ns) or {}
            m = housing_metrics(h)
            neighbors.append({
                "slug": ns,
                "name": name_by_slug.get(ns, ns),
                "condo_avg_price": m["condo_avg_price"],
                "land_median_yen_sqm": m["land_median_yen_sqm"],
                "station_sum_top5": m["station_sum_top5"],
            })

        self_m = housing_metrics(housing)
        tokyo_condo = housing.get("tokyo_median_condo_price")
        tokyo_land = housing.get("tokyo_median_residential_yen_sqm")

        def compare_series(value_key, self_val, tokyo_val):
            rows = []
            if self_val:
                rows.append({"key": "self", "slug": slug, "name": name, "value": self_val, "href": None})
            for nb in neighbors:
                v = nb.get(value_key)
                if v:
                    rows.append({
                        "key": "near",
                        "slug": nb["slug"],
                        "name": nb["name"],
                        "value": v,
                        "href": f"/area/tokyo/{nb['slug']}/",
                    })
            if tokyo_val:
                rows.append({"key": "tokyo", "slug": None, "name": "都内中央値", "value": tokyo_val, "href": None})
            return rows

        stations = dict(housing.get("stations") or {})
        if self_m["station_sum_top5"] and tokyo_station:
            stations["tokyo_median_sum_top5"] = tokyo_station
            stations["vs_tokyo_pct"] = round(100 * self_m["station_sum_top5"] / tokyo_station)

        snap = {
            "slug": slug,
            "name": name,
            "benefits": benefits,
            "housing": {
                "land": housing.get("land"),
                "condo": housing.get("condo"),
                "tokyo_median_residential_yen_sqm": tokyo_land,
                "tokyo_median_condo_price": tokyo_condo,
            },
            "neighbors": neighbors,
            "compare": {
                "condo": compare_series("condo_avg_price", self_m["condo_avg_price"], tokyo_condo),
                "land": compare_series("land_median_yen_sqm", self_m["land_median_yen_sqm"], tokyo_land),
                "stations": compare_series("station_sum_top5", self_m["station_sum_top5"], tokyo_station),
            },
            "stations": stations,
            "source": housing.get("source"),
        }
        with open(os.path.join(OUT_DIR, f"{slug}.snapshot.json"), "w", encoding="utf-8") as f:
            json.dump(snap, f, ensure_ascii=False, indent=2)
        n_out += 1

    print(f"wrote {n_out} snapshots")
    s = json.load(open(os.path.join(OUT_DIR, "shibuya.snapshot.json")))
    print("shibuya neighbors", [n["name"] for n in s["neighbors"]])
    print("condo compare", [(r["name"], r["value"]) for r in s["compare"]["condo"]])
    print("station compare", [(r["name"], r["value"]) for r in s["compare"]["stations"]])
    print("tokyo station median", s["stations"].get("tokyo_median_sum_top5"))


if __name__ == "__main__":
    main()
