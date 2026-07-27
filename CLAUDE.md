# iekanko.jp — くらしの制度ナビ（東京都62自治体の給付・手当・助成 比較サイト）

静的サイト。`docs/` を GitHub Pages で公開している。ページは SQLite DB から
`build/build_site.py` で生成する。

## ⚠️ 最重要: 「元データ（DB）が無い」と思ったときの復元手順

原本DB `gov_life_support.sqlite3` は **`.gitignore` 対象で、リポジトリには含まれていない**
（含まれていないのが正常）。各セッションはリポジトリをcloneするだけなのでDBは手元に無い。
**公開中の `docs/` が原本であり、そこからDBを完全復元できる**。

```bash
# 1) docs/ から DB を復元（これで gov_life_support.sqlite3 が生成される）
python3 build/rebuild_db_from_docs.py

# 2) DB を編集
#    - 新規制度の追加        : build/add_programs.py（data/enrichment/additions_*.csv を投入）
#    - 金額の鮮度是正・正準化 : build/refresh_amounts.py
#    - 個別編集は program_facts 等を直接 UPSERT

# 3) DB から docs を再生成（★ seed 固定を必ず付ける）
PYTHONHASHSEED=0 python3 build/build_site.py

# 4) docs をコミット → 公開元ブランチへマージで本番反映
```

「DBが無い」＝異常ではない。**手順1で必ず復元できる**。詳細は `build/MAINTENANCE.md`。

## 変更後は必ず `build/verify.sh` を通す（安全ゲート）
docs の**HTML構造**を変えると `rebuild_db_from_docs.py` の正規表現パーサが壊れ、
復元時に `program_facts` が激減する事故が起きうる（実際 11048→66 になった）。
再生成のあと **1コマンド** でラウンドトリップの冪等性を検証する:

```bash
bash build/verify.sh   # 復元→再生成→再復元し件数を突き合わせ、PASS/FAIL を出す
```

- CSS・文言・レイアウトだけの変更でも、最終確認としてこれ1本を通せば十分。
- 制度を意図的に増減したら期待値を上書き: `EXP_FACTS=... EXP_PROGRAMS=... bash build/verify.sh`
- 効率運用: 複数の変更は**まとめて再生成→verify→1回デプロイ**に束ねる（デプロイ待ちは1回で済む）。

## データ構成（build_site.py が参照する6テーブル）
`municipalities` / `programs` / `program_municipalities` /
`program_facts`（対象者・支給額・内容給付・申請方法・条件などの dt/dd はここ。
fact_type: target / amount / benefit / application / condition …）/
`program_life_events` / `life_events`

- 掲載可否ゲート: 制度の平均 confidence ≥ 82 かつ `reliability_status` ≠ `needs_review`
  → `index`。満たさなければ `noindex`（暫定データ表示）。
- `docs/` は DB の生成物。**手で docs を直接編集しても次回再生成で消える**ため、
  恒久変更は必ず DB 側（またはジェネレータ `build_site.py`）に入れる。

## 公開元ブランチ
`claude/seido-navi-db-publish-9t2kq4`（`main` は無い）。`docs/` をここへマージすると本番反映。
複数セッションが並行で `docs/` を触ることがあるため、作業前に必ず最新を fetch すること。

## 決定性（重要）
`build_site.py` は set の反復順が `PYTHONHASHSEED` に依存する。再生成は必ず
`PYTHONHASHSEED=0 python3 build/build_site.py` で実行する（seed固定で docs が完全再現＝
差分が「実際の変更」だけになる）。付け忘れると無関係な並べ替え差分が大量に出る。

## 補足
- 相場・駅データ（相場グラフ）は別DB `data/reinfolib_tokyo.db`（リポジトリ同梱）から生成。
- 復元DBは公開情報のみ。内部審査メモや `amount_min/max` 等のサイト非表示列は復元対象外。
- 追加調査の元ネタCSVと経緯は `data/enrichment/`、監査レポートは `audit/` に保存。
