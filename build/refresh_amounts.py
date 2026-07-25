#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""国の手当の月額を令和8年度（2026年4月改定）へ更新する（stale金額の是正）。

令和7→令和8で改定された国の手当額を、公式（東京都/厚労省/各市の告知）で確認し、
該当する program_facts の value を **fact_id 指定・完全一致** で置換する。
就学援助の学用品費など、数字が偶然一致する facts は対象外（fact_id で限定）。

確認済み令和8年度額（2026.4〜）:
  特別障害者手当   29,590 → 30,450
  障害児福祉手当   16,100 → 16,560
  特別児童扶養手当 1級56,800→58,450 / 2級37,830→38,930
出典: 東京都(koho.metro.tokyo.lg.jp 2026/06)・厚労省・各市改定告知
"""
import os
import sqlite3
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB = os.environ.get("SEIDO_DB", os.path.join(ROOT, "gov_life_support.sqlite3"))
VERIFIED = "2026-07-25"

# (fact_id, old_value, new_value) — 完全一致で置換
UPDATES = [
    # 特別児童扶養手当（1級/2級・令和7→令和8）
    (764, "1級 月56,800円／2級 月37,830円〈令和7年度・毎年度改定〉。所得制限あり",
          "1級 月58,450円／2級 月38,930円〈令和8年度・毎年度改定〉。所得制限あり"),
    (379, "1級 月56,800円／2級 月37,830円〈令和7年度・毎年度改定〉。所得制限あり",
          "1級 月58,450円／2級 月38,930円〈令和8年度・毎年度改定〉。所得制限あり"),
    (952, "1級 月56,800円／2級 月37,830円〈令和7年度・毎年度改定〉。所得制限あり",
          "1級 月58,450円／2級 月38,930円〈令和8年度・毎年度改定〉。所得制限あり"),
    (7694, "1級 月56,800円／2級 月37,830円〈令和7年度・毎年度改定〉。所得制限あり",
           "1級 月58,450円／2級 月38,930円〈令和8年度・毎年度改定〉。所得制限あり"),
    (9509, "1級 月56,800円／2級 月37,830円〈令和7年度・毎年度改定〉。所得制限あり",
           "1級 月58,450円／2級 月38,930円〈令和8年度・毎年度改定〉。所得制限あり"),
    (7126, "1級 月56,800円／2級 月37,830円〈令和7年度・毎年度改定〉。所得制限あり",
           "1級 月58,450円／2級 月38,930円〈令和8年度・毎年度改定〉。所得制限あり"),
    (3021, "1級56,800円、2級37,830円", "1級58,450円、2級38,930円"),
    # 障害児福祉手当（令和7→令和8）
    (2464, "月16,100円〈令和7年度・毎年度改定〉。20歳未満・常時介護・所得制限あり",
           "月16,560円〈令和8年度・毎年度改定〉。20歳未満・常時介護・所得制限あり"),
    (9674, "月16,100円〈令和7年度・毎年度改定〉。20歳未満・常時介護・所得制限あり",
           "月16,560円〈令和8年度・毎年度改定〉。20歳未満・常時介護・所得制限あり"),
    (9279, "月16,100円〈令和7年度・毎年度改定〉。20歳未満・常時介護・所得制限あり",
           "月16,560円〈令和8年度・毎年度改定〉。20歳未満・常時介護・所得制限あり"),
    (7687, "月16,100円〈令和7年度・毎年度改定〉。20歳未満・常時介護・所得制限あり",
           "月16,560円〈令和8年度・毎年度改定〉。20歳未満・常時介護・所得制限あり"),
    (9961, "月額16,100円", "月額16,560円"),
    (9620, "月額16,100円", "月額16,560円"),
    # 特別障害者手当（令和7→令和8）
    (9613, "月額29,590円", "月額30,450円"),
]


# 児童扶養手当は国の全国共通制度で自治体差がない。令和8年度額に正準化する。
# （DBには令和7額46,690/11,030・令和6額45,500・全部支給と一部支給上限を取り違えた
#  48,040表記などが混在。全国一律のため1つの正しい記述へ統一する。）
JIDO_FUYO_CANON = (
    "全部支給 本体 月48,050円／第2子以降 各 月11,350円加算"
    "（一部支給は所得に応じ逓減）〈令和8年度・国の全国共通額〉。所得制限あり"
)


def normalize_jido_fuyo(c):
    rows = c.execute(
        """SELECT pf.id, pf.value, pf.program_id FROM program_facts pf
           JOIN programs p ON p.id=pf.program_id
           WHERE p.title LIKE '%児童扶養手当%' AND p.title NOT LIKE '%特別児童扶養手当%'
             AND pf.fact_type='amount'"""
    ).fetchall()
    changed = 0
    for r in rows:
        if r["value"] == JIDO_FUYO_CANON:
            continue
        c.execute(
            "UPDATE program_facts SET value=?, confidence_score=88, "
            "reviewed_status='reviewed', updated_at=CURRENT_TIMESTAMP WHERE id=?",
            (JIDO_FUYO_CANON, r["id"]),
        )
        c.execute(
            "UPDATE programs SET last_verified_at=?, updated_at=CURRENT_TIMESTAMP WHERE id=?",
            (VERIFIED, r["program_id"]),
        )
        changed += 1
    print(f"児童扶養手当 正準化: {changed}/{len(rows)} facts 更新")
    return changed


def main():
    c = sqlite3.connect(DB)
    c.row_factory = sqlite3.Row
    ok = fail = 0
    for fid, old, new in UPDATES:
        row = c.execute("SELECT value, program_id FROM program_facts WHERE id=?", (fid,)).fetchone()
        if not row:
            print(f"  ! fact#{fid} 不在 — スキップ")
            fail += 1
            continue
        if row["value"] != old:
            print(f"  ! fact#{fid} 値が想定と不一致（既に更新済み or 別内容）— スキップ")
            print(f"      DB : {row['value'][:80]}")
            fail += 1
            continue
        c.execute(
            "UPDATE program_facts SET value=?, confidence_score=88, "
            "reviewed_status='reviewed', updated_at=CURRENT_TIMESTAMP WHERE id=?",
            (new, fid),
        )
        c.execute(
            "UPDATE programs SET last_verified_at=?, updated_at=CURRENT_TIMESTAMP WHERE id=?",
            (VERIFIED, row["program_id"]),
        )
        print(f"  ✓ fact#{fid} (pid={row['program_id']}) 更新")
        ok += 1
    print(f"\n国手当(特障/障児福祉/特児扶) 個別更新: {ok} / スキップ {fail}")
    normalize_jido_fuyo(c)
    c.commit()
    c.close()
    return fail


if __name__ == "__main__":
    sys.exit(1 if main() else 0)
