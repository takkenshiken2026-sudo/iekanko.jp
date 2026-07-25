#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""新規制度を原本DBへ投入する（網羅の底上げ）。

data/enrichment/additions_*.csv を読み、programs / program_municipalities /
program_facts / program_life_events へ INSERT する。
- 重複ガード: 同一自治体に official_url 一致、または title に既存制度の
  代表キーワードが含まれる制度が既にある場合はスキップ。
- reliability=reviewed の facts は confidence 85（GATE>=82 を満たし index 化）、
  needs_review は 60（noindex 暫定データ扱い）。

使い方:
    python3 build/add_programs.py                 # 既定 CSV を全投入
    python3 build/add_programs.py path/to.csv ... # 指定 CSV を投入
再生成:
    PYTHONHASHSEED=0 python3 build/build_site.py
"""
import csv
import os
import sqlite3
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB = os.environ.get("SEIDO_DB", os.path.join(ROOT, "gov_life_support.sqlite3"))

# 名称 -> slug（build_site.SLUGS と同一）。ここでは逆引き slug -> 自治体名 を使う。
sys.path.insert(0, os.path.join(ROOT, "build"))
from build_site import SLUGS  # noqa: E402

SLUG2NAME = {v: k for k, v in SLUGS.items()}

# CSV の列 -> program_facts.fact_type（表示順は build_site.FACT_LABELS が決める）
FACT_COLS = [
    ("target", "target"),
    ("amount", "amount"),
    ("benefit", "benefit"),
    ("application", "application"),
    ("condition", "condition"),
]

# 重複判定に使う、既存制度タイトルのキーワード（title 内の語）
DUP_KEYWORDS = {
    "高校生等医療費助成（マル青）": ["マル青", "高校生等医療", "高校生医療"],
    "産後ケア事業（通所型）": ["産後ケア", "産後母子ケア"],
    "産後ケア費用助成事業": ["産後ケア", "産後母子ケア"],
}

DEFAULT_CSVS = [
    os.path.join(ROOT, "data", "enrichment", "additions_maruao.csv"),
]


def muni_id(c, slug):
    name = SLUG2NAME.get(slug)
    if not name:
        return None
    row = c.execute(
        "SELECT id FROM municipalities WHERE municipality_name=?", (name,)
    ).fetchone()
    return row[0] if row else None


def life_event_id(c, slug):
    row = c.execute("SELECT id FROM life_events WHERE slug=?", (slug,)).fetchone()
    return row[0] if row else None


def already_has(c, mid, title, official_url):
    """同一自治体に同種制度が既にあるか（重複ガード）。"""
    rows = c.execute(
        """SELECT p.title, p.official_url FROM programs p
           JOIN program_municipalities pm ON pm.program_id=p.id
           WHERE pm.municipality_id=?""",
        (mid,),
    ).fetchall()
    # 同種制度のキーワードでのみ重複判定する。official_url は共有ランディング
    # ページ（例: 利島村の welfare.html）で他制度と衝突しうるため使わない。
    # 再実行時は投入済みタイトルがキーワードを含むため冪等に skip される。
    kws = DUP_KEYWORDS.get(title, [title])
    for t, _url in rows:
        if any(kw and kw in (t or "") for kw in kws):
            return True
    return False


def next_id(c, table):
    return (c.execute(f"SELECT COALESCE(MAX(id),0) FROM {table}").fetchone()[0]) + 1


def main(csv_paths):
    c = sqlite3.connect(DB)
    pid = next_id(c, "programs")
    pm_id = next_id(c, "program_municipalities")
    pf_id = next_id(c, "program_facts")
    ple_id = next_id(c, "program_life_events")

    added = skipped = 0
    for path in csv_paths:
        with open(path, encoding="utf-8") as f:
            for row in csv.DictReader(f):
                slug = row["municipality_slug"].strip()
                title = row["title"].strip()
                official = row["official_url"].strip()
                mid = muni_id(c, slug)
                if mid is None:
                    print(f"  ! 自治体slug不明: {slug} — スキップ")
                    skipped += 1
                    continue
                if already_has(c, mid, title, official):
                    print(f"  = 既存につきスキップ: {slug} / {title}")
                    skipped += 1
                    continue

                reliable = row.get("reliability", "").strip() == "reviewed"
                rel_status = "reviewed" if reliable else "needs_review"
                conf = 85 if reliable else 60
                verified = row.get("verified_date", "").strip() or None
                summary = (row.get("benefit") or "").strip()

                c.execute(
                    """INSERT INTO programs
                       (id,title,program_type,summary,plain_summary,official_url,
                        status,reliability_status,last_verified_at)
                       VALUES (?,?,?,?,?,?, 'active', ?, ?)""",
                    (pid, title, row["program_type"].strip(), summary, summary,
                     official, rel_status, verified),
                )
                c.execute(
                    """INSERT INTO program_municipalities
                       (id,program_id,municipality_id,area_scope)
                       VALUES (?,?,?, 'municipal')""",
                    (pm_id, pid, mid),
                )
                pm_id += 1

                for col, ft in FACT_COLS:
                    val = (row.get(col) or "").strip()
                    if not val:
                        continue
                    c.execute(
                        """INSERT INTO program_facts
                           (id,program_id,fact_type,value,evidence_url,
                            confidence_score,extraction_method,reviewed_status)
                           VALUES (?,?,?,?,?,?, 'manual_research', ?)""",
                        (pf_id, pid, ft, val, official, conf, rel_status),
                    )
                    pf_id += 1

                le = life_event_id(c, row.get("life_event", "").strip())
                if le:
                    c.execute(
                        """INSERT INTO program_life_events
                           (id,program_id,life_event_id,relevance_score,display_reason)
                           VALUES (?,?,?, 80, ?)""",
                        (ple_id, pid, le, title),
                    )
                    ple_id += 1

                print(f"  + 追加 id={pid}: {slug} / {title} [{rel_status}]")
                pid += 1
                added += 1

    c.commit()
    c.close()
    print(f"\n完了: 追加 {added} / スキップ {skipped}")


if __name__ == "__main__":
    paths = sys.argv[1:] or DEFAULT_CSVS
    main(paths)
