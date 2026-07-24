#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
自治体ハブ用スナップショット生成。
- 手当・助成の金額目安（hikaku から抽出）
- 住まい・交通（reinfolib JSON）
→ docs/assets/data/area/<slug>.snapshot.json
"""
from __future__ import annotations

import importlib.util
import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT_DIR = os.path.join(ROOT, "docs", "assets", "data", "area")
HIKAKU = os.path.join(ROOT, "docs", "hikaku")

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


def main():
    extract_rank_yen, slugs_by_name = _load_extract()
    name_by_slug = {v: k for k, v in slugs_by_name.items()}

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

    os.makedirs(OUT_DIR, exist_ok=True)
    n_out = 0
    for slug, name in name_by_slug.items():
        base_path = os.path.join(OUT_DIR, f"{slug}.json")
        housing = {}
        if os.path.isfile(base_path):
            with open(base_path, encoding="utf-8") as f:
                housing = json.load(f)

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

        # sort: childcare first, then by yen desc within
        group_order = {g: i for i, g in enumerate(GROUP_LABEL)}
        benefits.sort(key=lambda b: (group_order.get(b["group"], 99), -b["yen"]))

        snap = {
            "slug": slug,
            "name": name,
            "benefits": benefits,
            "housing": {
                "land": housing.get("land"),
                "condo": housing.get("condo"),
                "tokyo_median_residential_yen_sqm": housing.get("tokyo_median_residential_yen_sqm"),
                "tokyo_median_condo_price": housing.get("tokyo_median_condo_price"),
            },
            "stations": housing.get("stations"),
            "source": housing.get("source"),
        }
        with open(os.path.join(OUT_DIR, f"{slug}.snapshot.json"), "w", encoding="utf-8") as f:
            json.dump(snap, f, ensure_ascii=False, indent=2)
        n_out += 1

    print(f"wrote {n_out} snapshots")
    # sample
    s = json.load(open(os.path.join(OUT_DIR, "shibuya.snapshot.json")))
    print("shibuya benefits", [(b["label"], b["yen"], b["rank"]) for b in s["benefits"]])


if __name__ == "__main__":
    main()
