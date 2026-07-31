#!/usr/bin/env bash
# docs の構造変更が「復元パーサ（rebuild_db_from_docs.py の正規表現）」を壊していないかを
# 1コマンドで検証する安全ゲート。過去に fact ラベルへ <svg> を入れて FACT_RE が壊れ、
# program_facts が 11048 -> 66 に激減した事故があった。その再発をここで必ず捕まえる。
#
# 仕組み（ラウンドトリップの冪等性を確認）:
#   1) 現行 docs -> DB を復元し、件数が期待値どおりか検証
#   2) DB -> docs を PYTHONHASHSEED=0 で決定的に再生成
#   3) 再生成後の docs -> DB をもう一度復元し、件数が期待値どおりか検証
#   すべて一致 = 構造変更後もパーサ健在。1つでも欠けると FAIL で止まる。
#
# 使い方:  bash build/verify.sh
# 件数を意図的に増減した（制度を追加した等）ときは環境変数で期待値を上書き:
#   EXP_FACTS=11200 EXP_PROGRAMS=3120 bash build/verify.sh
set -euo pipefail
cd "$(dirname "$0")/.."

EXP_MUNI=${EXP_MUNI:-62}
EXP_EVENTS=${EXP_EVENTS:-5}
# 既定値は現行baseline（路線A: 標準制度の欠落埋め 2026-07-30 反映後）。
# 制度を増減したら都度この既定値も更新するか、環境変数で上書きすること。
EXP_PROGRAMS=${EXP_PROGRAMS:-3130}
EXP_FACTS=${EXP_FACTS:-13465}

counts() {  # DB の主要件数を "muni events programs facts" として出力
  python3 - "$1" <<'PY'
import sqlite3, sys
c = sqlite3.connect(sys.argv[1])
q = lambda t: c.execute(f"select count(*) from {t}").fetchone()[0]
print(q("municipalities"), q("life_events"), q("programs"), q("program_facts"))
PY
}

check() {  # ラベル 期待(muni events programs facts) 実測... を突き合わせる
  local label="$1"; shift
  local got="$*"
  local want="$EXP_MUNI $EXP_EVENTS $EXP_PROGRAMS $EXP_FACTS"
  if [ "$got" != "$want" ]; then
    echo "  ✗ FAIL [$label]  got: $got  want: $want"
    echo ""
    echo "復元パーサが構造変更で壊れた可能性が高い。build/rebuild_db_from_docs.py の"
    echo "正規表現（FACT_RE / OFFICIAL0_RE / TITLE_RE / BADGE_RE 等）を確認すること。"
    echo "件数を意図的に変えた場合は EXP_FACTS 等の環境変数で期待値を更新。"
    exit 1
  fi
  echo "  ✓ ok   [$label]  $got"
}

echo "[1/3] docs -> DB を復元して件数検証 ..."
python3 build/rebuild_db_from_docs.py >/dev/null
check "restore-before" $(counts gov_life_support.sqlite3)

echo "[2/3] DB -> docs を決定的に再生成 (PYTHONHASHSEED=0) ..."
PYTHONHASHSEED=0 python3 build/build_site.py >/dev/null
echo "  ✓ built"

echo "[3/3] 再生成後の docs -> DB を復元して件数検証 ..."
python3 build/rebuild_db_from_docs.py >/dev/null
check "restore-after " $(counts gov_life_support.sqlite3)

echo ""
echo "PASS  (muni=$EXP_MUNI events=$EXP_EVENTS programs=$EXP_PROGRAMS facts=$EXP_FACTS)"
echo "docs の差分は git diff で確認できます。"
