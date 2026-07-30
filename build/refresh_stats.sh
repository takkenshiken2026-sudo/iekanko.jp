#!/usr/bin/env bash
# 暮らしデータ（実態統計 data/livability_stats.db）の年次リフレッシュ。
#
# ingest_livability_stats.py が参照する公開オープンデータを再取得し、
# 統計DBを作り直してからサイトを再生成・検証する。
#
# 使い方:
#   bash build/refresh_stats.sh
#
# ★ 年に一度、出典が新年度版に更新されたら、先に
#   build/ingest_livability_stats.py 内の URL / year を新しい版に差し替えること。
#   （待機児童: こども家庭庁「保育所等関連状況取りまとめ」表4 / 東京都掲載分の d/tosei 番号、
#     人口・世帯: 東京都「住民基本台帳による世帯と人口」第5表の年度フォルダ jyXXqv0500.csv）
#   URL を替えずに実行すると前年と同じ数値で再取得されるだけなので注意。
set -euo pipefail
cd "$(dirname "$0")/.."

# 1) 統計DBの前提となる制度DBが無ければ docs から復元（自治体名→コードの突合に使う）
if [ ! -f gov_life_support.sqlite3 ]; then
  echo "[refresh_stats] gov_life_support.sqlite3 が無いので docs から復元します"
  python3 build/rebuild_db_from_docs.py
fi

# 2) オープンデータを再取得し livability_stats.db を作り直す
echo "[refresh_stats] オープンデータを再取得して統計DBを再構築します"
python3 build/ingest_livability_stats.py

# 3) サイト再生成（seed固定で決定的に）
echo "[refresh_stats] docs を再生成します（PYTHONHASHSEED=0）"
PYTHONHASHSEED=0 python3 build/build_site.py

# 4) ラウンドトリップ検証（制度データの件数が不変であることを確認）
echo "[refresh_stats] verify.sh でラウンドトリップ検証します"
bash build/verify.sh

echo "[refresh_stats] 完了。git diff で docs の差分（統計の更新分）を確認し、"
echo "                問題なければ commit → 公開元ブランチへマージで本番反映してください。"
