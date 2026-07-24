#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
不動産情報ライブラリ系の公開データから data/reinfolib_tokyo.db を構築する。

入力（デフォルトは /tmp/reinfolib の展開済みGeoJSON）:
  - 国土数値情報 地価公示 L01（東京都）
  - 国土数値情報 駅別乗降客数 S12（全国→東京都内にクリップ）
  - 国土数値情報 行政区域 N03（東京都）

出力:
  - data/reinfolib_tokyo.db
  - docs/assets/data/area/<slug>.json（各自治体サマリー）

出典: 国土交通省 国土数値情報（CC BY 4.0）
"""
from __future__ import annotations

import json
import os
import re
import sqlite3
import statistics
import sys
from collections import defaultdict

from shapely.geometry import Point, shape
from shapely.strtree import STRtree

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.environ.get("REINFOLIB_SRC", "/tmp/reinfolib")
DB_PATH = os.environ.get("REINFOLIB_DB", os.path.join(ROOT, "data", "reinfolib_tokyo.db"))
JSON_DIR = os.path.join(ROOT, "docs", "assets", "data", "area")

SLUGS = {
 "世田谷区":"setagaya","渋谷区":"shibuya","杉並区":"suginami","練馬区":"nerima","新宿区":"shinjuku",
 "港区":"minato","中央区":"chuo","江東区":"koto","大田区":"ota","千代田区":"chiyoda","文京区":"bunkyo",
 "台東区":"taito","墨田区":"sumida","品川区":"shinagawa","目黒区":"meguro","中野区":"nakano",
 "豊島区":"toshima","北区":"kita","荒川区":"arakawa","板橋区":"itabashi","足立区":"adachi",
 "葛飾区":"katsushika","江戸川区":"edogawa","八王子市":"hachioji","立川市":"tachikawa","武蔵野市":"musashino",
 "三鷹市":"mitaka","青梅市":"ome","府中市":"fuchu","昭島市":"akishima","調布市":"chofu","町田市":"machida",
 "小金井市":"koganei","小平市":"kodaira","日野市":"hino","東村山市":"higashimurayama","国分寺市":"kokubunji",
 "国立市":"kunitachi","福生市":"fussa","狛江市":"komae","東大和市":"higashiyamato","清瀬市":"kiyose",
 "東久留米市":"higashikurume","武蔵村山市":"musashimurayama","多摩市":"tama","稲城市":"inagi","羽村市":"hamura",
 "あきる野市":"akiruno","西東京市":"nishitokyo","瑞穂町":"mizuho","日の出町":"hinode","檜原村":"hinohara",
 "奥多摩町":"okutama","大島町":"oshima","利島村":"toshimamura","新島村":"niijima","神津島村":"kozushima",
 "三宅村":"miyake","御蔵島村":"mikurajima","八丈町":"hachijo","青ヶ島村":"aogashima","小笠原村":"ogasawara",
}

# 乗降客数フィールド（年 → 属性）
PASS_YEARS = {
 2011: "S12_009", 2012: "S12_013", 2013: "S12_017", 2014: "S12_021",
 2015: "S12_025", 2016: "S12_029", 2017: "S12_033", 2018: "S12_037",
 2019: "S12_041", 2020: "S12_045", 2021: "S12_049", 2022: "S12_053",
 2023: "S12_057", 2024: "S12_061",
}
PASS_AVAIL = {
 2011: "S12_007", 2012: "S12_011", 2013: "S12_015", 2014: "S12_019",
 2015: "S12_023", 2016: "S12_027", 2017: "S12_031", 2018: "S12_035",
 2019: "S12_039", 2020: "S12_043", 2021: "S12_047", 2022: "S12_051",
 2023: "S12_055", 2024: "S12_059",
}


def load_geojson(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def normalize_muni_name(name: str) -> str:
    name = (name or "").strip().replace("　", "")
    # N03 は「○○区」などそのまま
    if name in SLUGS:
        return name
    # 「二十三区」等は除外
    return name


def build_muni_index(n03_path):
    """行政区域ポリゴン → city_code / name / geometry"""
    gj = load_geojson(n03_path)
    polys = []
    meta = []
    code_to_name = {}
    for feat in gj["features"]:
        p = feat.get("properties") or {}
        code = str(p.get("N03_007") or p.get("N03_004") or "").strip()
        name = normalize_muni_name(p.get("N03_004") or p.get("N03_003") or "")
        # N03 schema: N03_001 pref, N03_002 subpref, N03_003 county, N03_004 city, N03_007 code
        if not code or len(code) < 5:
            continue
        # Prefer full municipality name field
        city = (p.get("N03_004") or "").strip()
        if not city:
            city = (p.get("N03_003") or "").strip()
        city = normalize_muni_name(city)
        if city not in SLUGS:
            # 島しょなど表記ゆれ
            for k in SLUGS:
                if k.startswith(city) or city.startswith(k.replace("区", "").replace("市", "")):
                    city = k
                    break
        if city not in SLUGS:
            continue
        geom = shape(feat["geometry"])
        if geom.is_empty:
            continue
        polys.append(geom)
        meta.append((code[:5], city, SLUGS[city]))
        code_to_name[code[:5]] = city
    tree = STRtree(polys)
    return tree, polys, meta, code_to_name


def centroid_lonlat(geom):
    if geom["type"] == "Point":
        return geom["coordinates"][0], geom["coordinates"][1]
    if geom["type"] == "LineString":
        coords = geom["coordinates"]
        mid = coords[len(coords) // 2]
        return mid[0], mid[1]
    if geom["type"] == "MultiLineString":
        coords = geom["coordinates"][0]
        mid = coords[len(coords) // 2]
        return mid[0], mid[1]
    g = shape(geom)
    c = g.centroid
    return c.x, c.y


def locate_muni(tree, polys, meta, lon, lat):
    pt = Point(lon, lat)
    hits = tree.query(pt)
    for idx in hits:
        poly = polys[int(idx)]
        if poly.covers(pt) or poly.intersects(pt):
            return meta[int(idx)]
    # ごく近傍のみ（境界の浮動小数誤差対策）。都外は捨てる
    nearest = tree.nearest(pt)
    if nearest is None:
        return None
    idx = int(nearest)
    if polys[idx].distance(pt) < 0.0003:  # ~30m
        return meta[idx]
    return None


def median(vals):
    vals = [v for v in vals if v is not None and v > 0]
    if not vals:
        return None
    return int(statistics.median(vals))


def main():
    l01 = os.path.join(SRC, "L01-25_13_GML", "L01-25_13.geojson")
    s12 = os.path.join(SRC, "S12-25_GML", "UTF-8", "S12-25_NumberOfPassengers.geojson")
    n03 = os.path.join(SRC, "N03-20240101_13.geojson")
    for p in (l01, s12, n03):
        if not os.path.isfile(p):
            sys.exit(f"missing input: {p}")

    print("loading municipalities…")
    tree, polys, meta, code_to_name = build_muni_index(n03)
    print(f"  polygons={len(polys)} codes={len(code_to_name)}")

    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    if os.path.exists(DB_PATH):
        os.remove(DB_PATH)
    con = sqlite3.connect(DB_PATH)
    c = con.cursor()
    c.executescript(
        """
        CREATE TABLE meta(key TEXT PRIMARY KEY, value TEXT);
        CREATE TABLE municipalities(
          city_code TEXT PRIMARY KEY,
          name TEXT NOT NULL,
          slug TEXT NOT NULL
        );
        CREATE TABLE land_prices(
          id INTEGER PRIMARY KEY,
          city_code TEXT,
          year INTEGER,
          price_per_sqm INTEGER,
          use_type TEXT,
          address TEXT,
          station_name TEXT,
          station_dist_m INTEGER,
          lon REAL, lat REAL
        );
        CREATE TABLE stations(
          id INTEGER PRIMARY KEY,
          station_code TEXT,
          group_code TEXT,
          name TEXT,
          company TEXT,
          line_name TEXT,
          city_code TEXT,
          lon REAL, lat REAL,
          passengers_2024 INTEGER,
          passengers_2023 INTEGER,
          passengers_2022 INTEGER,
          passengers_2019 INTEGER
        );
        CREATE TABLE station_passengers_yearly(
          station_id INTEGER,
          year INTEGER,
          passengers INTEGER,
          PRIMARY KEY(station_id, year)
        );
        CREATE TABLE muni_stats(
          city_code TEXT PRIMARY KEY,
          name TEXT,
          slug TEXT,
          median_residential_yen_sqm INTEGER,
          median_commercial_yen_sqm INTEGER,
          n_land_points INTEGER,
          n_stations INTEGER,
          top_station TEXT,
          top_station_passengers INTEGER,
          sum_top5_passengers INTEGER
        );
        CREATE INDEX idx_land_city ON land_prices(city_code);
        CREATE INDEX idx_st_city ON stations(city_code);
        """
    )
    c.execute("INSERT INTO meta VALUES(?,?)", ("source", "国土交通省 国土数値情報（地価公示L01・駅別乗降客数S12・行政区域N03）"))
    c.execute("INSERT INTO meta VALUES(?,?)", ("license", "CC BY 4.0"))
    c.execute("INSERT INTO meta VALUES(?,?)", ("land_year", "2025"))
    c.execute("INSERT INTO meta VALUES(?,?)", ("station_year", "2024"))
    c.execute("INSERT INTO meta VALUES(?,?)", ("note", "ローカルの reinfolib_tokyo.db がクラウド環境に未同梱のため、同系統の公開データから再構築"))

    # municipalities table
    seen = {}
    for code, name, slug in meta:
        if code not in seen:
            seen[code] = (name, slug)
            c.execute("INSERT OR IGNORE INTO municipalities VALUES(?,?,?)", (code, name, slug))
    # ensure all 62 slugs present even without polygon match
    name_to_code = {n: code for code, (n, _) in seen.items()}
    for name, slug in SLUGS.items():
        if name not in name_to_code:
            # synthesize from known JIS where possible later; skip empty
            pass

    print("loading land prices…")
    land = load_geojson(l01)
    land_rows = []
    for i, feat in enumerate(land["features"], 1):
        p = feat["properties"]
        code = str(p.get("L01_001") or "")[:5]
        price = p.get("L01_008")
        if not code or not price:
            continue
        lon, lat = centroid_lonlat(feat["geometry"])
        use = p.get("L01_028") or ""
        addr = (p.get("L01_025") or "").replace("　", " ")
        st = p.get("L01_048") or ""
        if st == "_":
            st = ""
        dist = p.get("L01_050")
        try:
            dist = int(dist) if dist not in (None, "_") else None
        except Exception:
            dist = None
        year = int(p.get("L01_007") or 2025)
        land_rows.append((i, code, year, int(price), use, addr, st, dist, lon, lat))
        if code not in seen:
            # derive name from address 「東京都　千代田区…」
            m = re.search(r"東京都\s*([^\s\d]+?[区市町村])", addr)
            nm = m.group(1) if m else code
            slug = SLUGS.get(nm, "")
            if slug:
                seen[code] = (nm, slug)
                c.execute("INSERT OR IGNORE INTO municipalities VALUES(?,?,?)", (code, nm, slug))
    c.executemany(
        "INSERT INTO land_prices VALUES(?,?,?,?,?,?,?,?,?,?)",
        land_rows,
    )
    print(f"  land_points={len(land_rows)}")

    print("loading stations (Tokyo clip)…")
    st_gj = load_geojson(s12)
    st_rows = []
    yearly = []
    sid = 0
    for feat in st_gj["features"]:
        p = feat["properties"]
        lon, lat = centroid_lonlat(feat["geometry"])
        # rough Tokyo bbox including islands
        if not (138.9 <= lon <= 140.0 and 24.0 <= lat <= 36.0):
            continue
        located = locate_muni(tree, polys, meta, lon, lat)
        if not located:
            continue
        city_code, city_name, slug = located
        sid += 1
        p24 = p.get("S12_061") or 0
        p23 = p.get("S12_057") or 0
        p22 = p.get("S12_053") or 0
        p19 = p.get("S12_041") or 0
        # availability code 1 = present
        def avail(y):
            code = str(p.get(PASS_AVAIL[y]) or "")
            return code == "1"
        if avail(2024) and not p24:
            p24 = 0
        st_rows.append((
            sid,
            str(p.get("S12_001c") or ""),
            str(p.get("S12_001g") or ""),
            p.get("S12_001") or "",
            p.get("S12_002") or "",
            p.get("S12_003") or "",
            city_code,
            lon, lat,
            int(p24 or 0) if avail(2024) else None,
            int(p23 or 0) if avail(2023) else None,
            int(p22 or 0) if avail(2022) else None,
            int(p19 or 0) if avail(2019) else None,
        ))
        for y, key in PASS_YEARS.items():
            if not avail(y):
                continue
            val = p.get(key)
            if val is None:
                continue
            yearly.append((sid, y, int(val)))
    c.executemany(
        "INSERT INTO stations VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)",
        st_rows,
    )
    c.executemany(
        "INSERT INTO station_passengers_yearly VALUES(?,?,?)",
        yearly,
    )
    print(f"  stations={len(st_rows)}")

    print("aggregating muni_stats…")
    # land by city
    land_by = defaultdict(lambda: {"res": [], "com": [], "n": 0})
    for row in land_rows:
        _, code, _y, price, use, *_ = row
        land_by[code]["n"] += 1
        if "住宅" in (use or ""):
            land_by[code]["res"].append(price)
        if any(k in (use or "") for k in ("店舗", "事務所", "商業")):
            land_by[code]["com"].append(price)
        if "住宅" not in (use or "") and not any(k in (use or "") for k in ("店舗", "事務所", "商業")):
            land_by[code]["res"].append(price)

    # stations: aggregate by group within city (same station name+group)
    st_by = defaultdict(list)
    for row in st_rows:
        (sid, scode, gcode, name, company, line, city_code, lon, lat, p24, p23, p22, p19) = row
        passengers = p24 or p23 or p22 or 0
        st_by[city_code].append({
            "name": name, "company": company, "line": line,
            "group": gcode, "passengers": passengers or 0,
        })

    stats_rows = []
    summaries = {}
    for code, (name, slug) in seen.items():
        lb = land_by.get(code, {"res": [], "com": [], "n": 0})
        med_res = median(lb["res"])
        med_com = median(lb["com"])
        # unique stations by group code, take max passengers
        groups = {}
        for s in st_by.get(code, []):
            g = s["group"] or s["name"]
            cur = groups.get(g)
            if cur is None or s["passengers"] > cur["passengers"]:
                groups[g] = s
        stations = sorted(groups.values(), key=lambda x: -x["passengers"])
        top = stations[0] if stations else None
        top5_sum = sum(s["passengers"] for s in stations[:5])
        stats_rows.append((
            code, name, slug, med_res, med_com, lb["n"],
            len(stations),
            top["name"] if top else None,
            top["passengers"] if top else None,
            top5_sum or None,
        ))
        summaries[slug] = {
            "city_code": code,
            "name": name,
            "slug": slug,
            "land": {
                "year": 2025,
                "median_residential_yen_sqm": med_res,
                "median_commercial_yen_sqm": med_com,
                "n_points": lb["n"],
                "unit": "円/㎡",
            },
            "stations": {
                "year": 2024,
                "n_stations": len(stations),
                "top": [
                    {
                        "name": s["name"],
                        "company": s["company"],
                        "line": s["line"],
                        "passengers": s["passengers"],
                    }
                    for s in stations[:8] if s["passengers"] > 0
                ],
                "sum_top5_passengers": top5_sum,
                "unit": "人/日（乗降）",
            },
            "source": {
                "land": "国土数値情報 地価公示（L01）2025年",
                "stations": "国土数値情報 駅別乗降客数（S12）2024年",
                "license": "CC BY 4.0（国土交通省）",
            },
        }

    c.executemany(
        "INSERT INTO muni_stats VALUES(?,?,?,?,?,?,?,?,?,?)",
        stats_rows,
    )
    con.commit()

    # Tokyo-wide medians for relative charts
    all_res = [r[3] for r in stats_rows if r[3]]
    tokyo_med = median(all_res)
    c.execute("INSERT INTO meta VALUES(?,?)", ("tokyo_median_residential_yen_sqm", str(tokyo_med or "")))
    con.commit()
    con.close()

    os.makedirs(JSON_DIR, exist_ok=True)
    for slug, data in summaries.items():
        data["tokyo_median_residential_yen_sqm"] = tokyo_med
        if data["land"]["median_residential_yen_sqm"] and tokyo_med:
            data["land"]["vs_tokyo_pct"] = round(
                100 * data["land"]["median_residential_yen_sqm"] / tokyo_med
            )
        path = os.path.join(JSON_DIR, f"{slug}.json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    # index
    with open(os.path.join(JSON_DIR, "index.json"), "w", encoding="utf-8") as f:
        json.dump(
            {
                "tokyo_median_residential_yen_sqm": tokyo_med,
                "municipalities": [
                    {
                        "slug": r[2],
                        "name": r[1],
                        "median_residential_yen_sqm": r[3],
                        "top_station": r[7],
                        "top_station_passengers": r[8],
                    }
                    for r in sorted(stats_rows, key=lambda x: -(x[3] or 0))
                ],
            },
            f,
            ensure_ascii=False,
            indent=2,
        )

    print(f"wrote {DB_PATH} ({os.path.getsize(DB_PATH)/1e6:.1f} MB)")
    print(f"wrote {len(summaries)} JSON files → {JSON_DIR}")
    print(f"tokyo median residential: {tokyo_med:,} 円/㎡" if tokyo_med else "no median")


if __name__ == "__main__":
    main()
