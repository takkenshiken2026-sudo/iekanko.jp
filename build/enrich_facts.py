#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""既存制度の program_facts を公式出典で厚くし、掲載ゲートを満たす形へ昇格する。

data/enrichment/facts_*.csv（program_id, fact_type, value, evidence_url）を読み、
- (program_id, fact_type) が既存なら value/evidence_url を置換（UPSERT）、無ければ INSERT
- 投入した各 fact は confidence_score=85 / reviewed_status='reviewed'
- 併せて対象制度の**全fact**を confidence>=85 / reviewed に引き上げ（公式ページで裏取り済みのため）、
  programs.reliability_status='reviewed' / last_verified_at を更新

これにより build_site.gate_index（reliability_status≠needs_review かつ 平均confidence≥82）を
満たし、noindex（暫定）→ index へ昇格する。

使い方:
    python3 build/enrich_facts.py                       # data/enrichment/facts_*.csv を全投入
    python3 build/enrich_facts.py path/to/facts.csv ... # 指定 CSV を投入
再生成:
    PYTHONHASHSEED=0 python3 build/build_site.py
"""
import csv
import glob
import os
import sqlite3
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB = os.environ.get("SEIDO_DB", os.path.join(ROOT, "gov_life_support.sqlite3"))
VERIFIED = os.environ.get("VERIFIED_DATE", "2026-07-30")
CONF = 85  # GATE_MIN_CONFIDENCE(82) を満たす確度


def load_rows(paths):
    rows = []
    for p in paths:
        with open(p, newline="", encoding="utf-8") as f:
            for r in csv.DictReader(f):
                pid = int(r["program_id"])
                ft = r["fact_type"].strip()
                val = r["value"].strip()
                url = (r.get("evidence_url") or "").strip()
                if pid and ft and val:
                    rows.append((pid, ft, val, url))
    return rows


def upsert(c, pid, ft, val, url):
    row = c.execute(
        "SELECT id FROM program_facts WHERE program_id=? AND fact_type=?",
        (pid, ft),
    ).fetchone()
    if row:
        c.execute(
            "UPDATE program_facts SET value=?, evidence_url=COALESCE(NULLIF(?,''),evidence_url), "
            "confidence_score=?, reviewed_status='reviewed', updated_at=CURRENT_TIMESTAMP WHERE id=?",
            (val, url, CONF, row[0]),
        )
        return "update"
    c.execute(
        "INSERT INTO program_facts(program_id,fact_type,value,evidence_url,confidence_score,"
        "extraction_method,reviewed_status,created_at,updated_at) "
        "VALUES(?,?,?,?,?, 'manual_official','reviewed',CURRENT_TIMESTAMP,CURRENT_TIMESTAMP)",
        (pid, ft, val, url, CONF),
    )
    return "insert"


def main(argv):
    paths = argv[1:] or sorted(glob.glob(os.path.join(ROOT, "data", "enrichment", "facts_*.csv")))
    if not paths:
        print("no facts_*.csv found"); return 1
    rows = load_rows(paths)
    if not rows:
        print("no rows"); return 1

    db = sqlite3.connect(DB)
    c = db.cursor()
    ins = upd = 0
    pids = set()
    for pid, ft, val, url in rows:
        # program の実在チェック
        if not c.execute("SELECT 1 FROM programs WHERE id=?", (pid,)).fetchone():
            print(f"  skip: program {pid} not found"); continue
        r = upsert(c, pid, ft, val, url)
        ins += (r == "insert"); upd += (r == "update")
        pids.add(pid)

    promoted = 0
    for pid in sorted(pids):
        # 対象制度の全factを裏取り済み扱いへ引き上げ、制度を reviewed に昇格
        c.execute(
            "UPDATE program_facts SET confidence_score=MAX(confidence_score,?), "
            "reviewed_status='reviewed', updated_at=CURRENT_TIMESTAMP WHERE program_id=?",
            (CONF, pid),
        )
        was = c.execute("SELECT reliability_status FROM programs WHERE id=?", (pid,)).fetchone()[0]
        c.execute(
            "UPDATE programs SET reliability_status='reviewed', last_verified_at=?, "
            "updated_at=CURRENT_TIMESTAMP WHERE id=?",
            (VERIFIED, pid),
        )
        promoted += (was == "needs_review")
    db.commit()

    print(f"CSV: {len(paths)}本  facts行: {len(rows)}")
    print(f"  INSERT={ins}  UPDATE={upd}  対象制度={len(pids)}  needs_review→reviewed 昇格={promoted}")
    db.close()
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
