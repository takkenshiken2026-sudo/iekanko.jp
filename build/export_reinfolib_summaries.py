#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
data/reinfolib_tokyo.db（不動産情報ライブラリ由来）から
docs/assets/data/area/<slug>.json を生成する。
"""
from __future__ import annotations

import json
import os
import sqlite3
import statistics
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_PATH = os.environ.get("REINFOLIB_DB", os.path.join(ROOT, "data", "reinfolib_tokyo.db"))
JSON_DIR = os.path.join(ROOT, "docs", "assets", "data", "area")
N03_PATH = os.environ.get(
    "REINFOLIB_N03",
    "/tmp/reinfolib/N03-20240101_13.geojson",
)

# サイト側スラッグ（DB側 slug は別表記のため name_ja で対応）
SITE_SLUGS = {
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


def median(vals):
    vals = [v for v in vals if v is not None and v > 0]
    if not vals:
        return None
    return int(statistics.median(vals))


def assign_stations(con):
    """駅に自治体コードを付与。N03があれば空間判定、なければ地価の最寄駅名から推定。"""
    stations = con.execute(
        "SELECT id, station_code, group_code, station_name, operator_name, line_name, "
        "latitude, longitude, latest_year, latest_passengers, passengers_json "
        "FROM station_passengers"
    ).fetchall()

    code_by_id = {}
    if os.path.isfile(N03_PATH):
        try:
            from shapely.geometry import Point, shape
            from shapely.strtree import STRtree
            with open(N03_PATH, encoding="utf-8") as f:
                gj = json.load(f)
            polys, meta = [], []
            for feat in gj["features"]:
                p = feat.get("properties") or {}
                code = str(p.get("N03_007") or "")[:5]
                name = (p.get("N03_004") or "").strip()
                if not code or name not in SITE_SLUGS:
                    continue
                geom = shape(feat["geometry"])
                if geom.is_empty:
                    continue
                polys.append(geom)
                meta.append(code)
            tree = STRtree(polys)
            for st in stations:
                lat, lon = st[6], st[7]
                if lat is None or lon is None:
                    continue
                pt = Point(lon, lat)
                hits = tree.query(pt)
                found = None
                for idx in hits:
                    idx = int(idx)
                    if polys[idx].covers(pt) or polys[idx].intersects(pt):
                        found = meta[idx]
                        break
                if not found:
                    nearest = tree.nearest(pt)
                    if nearest is not None:
                        idx = int(nearest)
                        if polys[idx].distance(pt) < 0.0003:
                            found = meta[idx]
                if found:
                    code_by_id[st[0]] = found
        except Exception as e:
            print("N03 assign failed:", e, file=sys.stderr)

    # fallback: nearest_station name → municipality from land prices (latest year)
    if len(code_by_id) < len(stations) // 2:
        name_votes = {}
        for muni, stname in con.execute(
            "SELECT municipality_code, nearest_station FROM land_price_points "
            "WHERE nearest_station IS NOT NULL AND nearest_station != '' "
            "AND survey_year = (SELECT MAX(survey_year) FROM land_price_points)"
        ):
            name_votes.setdefault(stname, {})
            name_votes[stname][muni] = name_votes[stname].get(muni, 0) + 1
        name_to_code = {
            n: max(votes.items(), key=lambda x: x[1])[0]
            for n, votes in name_votes.items() if votes
        }
        for st in stations:
            if st[0] in code_by_id:
                continue
            code = name_to_code.get(st[3])
            if code:
                code_by_id[st[0]] = code

    return stations, code_by_id


def condo_yearly(con, muni_code, prefer_class="02"):
    """年別の中古マンション平均価格（件数加重）。prefer_class が無ければ 01。"""
    rows = con.execute(
        """
        SELECT trade_year, price_classification,
               SUM(transaction_count) AS n,
               SUM(trade_price_avg * transaction_count) * 1.0 / SUM(transaction_count) AS avg_price,
               SUM(area_avg * transaction_count) * 1.0 / SUM(transaction_count) AS avg_area
        FROM municipality_trade_stats
        WHERE municipality_code=? AND property_type='中古マンション等'
          AND transaction_count > 0 AND trade_price_avg > 0
        GROUP BY trade_year, price_classification
        ORDER BY trade_year
        """,
        (muni_code,),
    ).fetchall()
    by_year = {}
    for y, cls, n, avg_p, avg_a in rows:
        by_year.setdefault(y, {})[cls] = {
            "n": int(n),
            "avg_price": int(avg_p),
            "avg_area": round(float(avg_a), 1) if avg_a else None,
            "price_classification": cls,
        }
    out = []
    for y in sorted(by_year):
        d = by_year[y]
        pick = d.get(prefer_class) or d.get("01") or next(iter(d.values()))
        out.append({"year": y, **pick})
    return out


def land_medians(con, muni_code, year):
    res, com = [], []
    for use, price in con.execute(
        "SELECT use_category_name, unit_price FROM land_price_points "
        "WHERE municipality_code=? AND survey_year=? AND unit_price > 0",
        (muni_code, year),
    ):
        if use == "住宅地":
            res.append(price)
        elif use == "商業地":
            com.append(price)
    return median(res), median(com), len(res) + len(com)


def main():
    if not os.path.isfile(DB_PATH):
        sys.exit(f"missing DB: {DB_PATH}")
    con = sqlite3.connect(DB_PATH)
    land_year = con.execute("SELECT MAX(survey_year) FROM land_price_points").fetchone()[0]
    stations, st_muni = assign_stations(con)

    # stations by muni (dedupe by group_code, max passengers)
    st_by_muni = {}
    for st in stations:
        mid = st[0]
        code = st_muni.get(mid)
        if not code:
            continue
        gcode = st[2] or st[1] or st[3]
        pax = st[9] or 0
        cur = st_by_muni.setdefault(code, {})
        prev = cur.get(gcode)
        if prev is None or pax > prev["passengers"]:
            # yearly from json
            yearly = []
            try:
                pj = json.loads(st[10] or "{}")
                yearly = [{"year": int(y), "passengers": int(v)} for y, v in sorted(pj.items()) if v]
            except Exception:
                yearly = []
            cur[gcode] = {
                "name": st[3],
                "company": st[4],
                "line": st[5],
                "passengers": int(pax),
                "year": st[8],
                "yearly": yearly[-6:],
            }

    munis = con.execute(
        "SELECT code, name_ja, slug FROM municipalities ORDER BY code"
    ).fetchall()

    # Tokyo-wide medians for residential land + condo
    all_res = []
    for use, price in con.execute(
        "SELECT use_category_name, unit_price FROM land_price_points "
        "WHERE survey_year=? AND use_category_name='住宅地' AND unit_price>0",
        (land_year,),
    ):
        all_res.append(price)
    tokyo_land_med = median(all_res)

    tokyo_condo = []
    for code, name, _ in munis:
        ys = condo_yearly(con, code)
        if ys:
            tokyo_condo.append(ys[-1]["avg_price"])
    tokyo_condo_med = median(tokyo_condo)

    os.makedirs(JSON_DIR, exist_ok=True)
    summaries = {}
    index_rows = []

    for code, name, db_slug in munis:
        site_slug = SITE_SLUGS.get(name)
        if not site_slug:
            print("skip unknown", name)
            continue
        med_res, med_com, n_land = land_medians(con, code, land_year)
        condo = condo_yearly(con, code)
        latest_condo = condo[-1] if condo else None
        meta = con.execute(
            "SELECT latest_year, latest_quarter, total_transactions, recent_avg_price "
            "FROM municipality_page_meta WHERE municipality_code=?",
            (code,),
        ).fetchone()

        stations_list = sorted(
            (st_by_muni.get(code) or {}).values(),
            key=lambda x: -x["passengers"],
        )
        top = [s for s in stations_list if s["passengers"] > 0][:8]

        vs_land = None
        if med_res and tokyo_land_med:
            vs_land = round(100 * med_res / tokyo_land_med)
        vs_condo = None
        if latest_condo and tokyo_condo_med:
            vs_condo = round(100 * latest_condo["avg_price"] / tokyo_condo_med)

        data = {
            "city_code": code,
            "name": name,
            "slug": site_slug,
            "db_slug": db_slug,
            "land": {
                "year": land_year,
                "median_residential_yen_sqm": med_res,
                "median_commercial_yen_sqm": med_com,
                "n_points": n_land,
                "unit": "円/㎡",
                "vs_tokyo_pct": vs_land,
            },
            "condo": {
                "label": "中古マンション等",
                "latest": latest_condo,
                "yearly": condo,
                "vs_tokyo_pct": vs_condo,
                "note": "成約価格（無い年は取引価格）。件数加重平均。",
            },
            "trade_meta": {
                "latest_year": meta[0] if meta else None,
                "latest_quarter": meta[1] if meta else None,
                "total_transactions": meta[2] if meta else None,
                "recent_avg_price": int(meta[3]) if meta and meta[3] else None,
            },
            "stations": {
                "year": top[0]["year"] if top else None,
                "n_stations": len(stations_list),
                "top": [
                    {
                        "name": s["name"],
                        "company": s["company"],
                        "line": s["line"],
                        "passengers": s["passengers"],
                        "yearly": s.get("yearly") or [],
                    }
                    for s in top
                ],
                "sum_top5_passengers": sum(s["passengers"] for s in top[:5]),
                "unit": "人/日（乗降）",
            },
            "tokyo_median_residential_yen_sqm": tokyo_land_med,
            "tokyo_median_condo_price": tokyo_condo_med,
            "source": {
                "land": f"地価公示・都道府県地価調査（{land_year}年）",
                "trade": "不動産情報ライブラリ 取引価格・成約価格",
                "stations": "国土数値情報 駅別乗降客数",
                "license": "国土交通省系オープンデータ",
            },
        }
        summaries[site_slug] = data
        index_rows.append({
            "slug": site_slug,
            "name": name,
            "median_residential_yen_sqm": med_res,
            "condo_avg_price": latest_condo["avg_price"] if latest_condo else None,
            "top_station": top[0]["name"] if top else None,
            "top_station_passengers": top[0]["passengers"] if top else None,
        })
        with open(os.path.join(JSON_DIR, f"{site_slug}.json"), "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    with open(os.path.join(JSON_DIR, "index.json"), "w", encoding="utf-8") as f:
        json.dump(
            {
                "tokyo_median_residential_yen_sqm": tokyo_land_med,
                "tokyo_median_condo_price": tokyo_condo_med,
                "municipalities": sorted(
                    index_rows,
                    key=lambda x: -(x["condo_avg_price"] or x["median_residential_yen_sqm"] or 0),
                ),
            },
            f,
            ensure_ascii=False,
            indent=2,
        )

    print(f"exported {len(summaries)} munis from {DB_PATH}")
    print(f"land_year={land_year} tokyo_land_med={tokyo_land_med} tokyo_condo_med={tokyo_condo_med}")
    print(f"stations assigned={len(st_muni)}/{len(stations)}")


if __name__ == "__main__":
    main()
