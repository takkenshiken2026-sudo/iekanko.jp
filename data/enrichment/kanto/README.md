# 関東全域への拡大（フェーズ2）— 調査データと手順

対象エリアを東京都62自治体から関東1都6県（約316自治体）へ広げるための、
自治体別の調査データ（`additions_<県>_<自治体>.csv`）と運用手順を置く。

フェーズ1で生成・復元パイプラインは多県対応済み（`build/pref_registry.py` が単一ソース）。
ここから先は**データの調査・検証**が主作業。品質ゲート（reviewed のみ index／未検証は noindex 暫定）を
堅持し、検証済みの自治体・制度だけを段階的に公開する（広告安全性の床）。

## 新しい自治体を立ち上げる手順（ブートストラップ）

```bash
# 0) 自治体スラッグを登録（単一ソース）
#    build/pref_registry.py の SLUGS_BY_PREF に県コード単位で {自治体名: スラッグ} を追加
#    例: "14": {"横浜市":"yokohama", "川崎市":"kawasaki", ...}
#    スラッグは公式ドメインに合わせて一意にする（衝突すると build が停止して知らせる）

# 1) 公開中 docs から原本DBを復元（登録した自治体の空レコードが作られる）
python3 build/rebuild_db_from_docs.py

# 2) 調査データ CSV を投入（このディレクトリの additions_<県>_<自治体>.csv）
python3 build/add_programs.py data/enrichment/kanto/additions_kanagawa_yokohama.csv

# 3) 再生成（seed 固定）。/area/<県>/<自治体>/ 一式が生成される
PYTHONHASHSEED=0 python3 build/build_site.py

# 4) ラウンドトリップ検証（件数は投入ぶん増えるので期待値を上書き）
EXP_PROGRAMS=<新値> EXP_FACTS=<新値> bash build/verify.sh
```

> サンドボックス検証: `SEIDO_DB=<tmp.db>` と `SEIDO_OUT=<tmp/docs>` / `SEIDO_DOCS=<docs>` を
> 使えば、本番 docs を汚さずに生成・復元を試せる（フェーズ1で追加）。

## CSV フォーマット（1行＝1制度）

`municipality_slug,title,official_url,program_type,target,amount,benefit,application,condition,life_event,reliability,verified_date`

- `reliability`: `reviewed`（公式一次情報で金額・条件を確認済み＝公開/index）／`needs_review`（未確認＝noindex 暫定）
- `amount` は具体的な金額を公式の記載どおりに。`official_url` は必ず一次情報（市区町村公式）に。
- `life_event`: pregnancy_birth / childcare / moving / retirement_unemployment / elderly_care

## パイロット計測（2026-10-08・神奈川県横浜市）

`additions_kanagawa_yokohama.csv`（4制度）で end-to-end を実証：
- 小児医療費助成（18歳まで・所得制限なし・窓口負担なし）
- 産後母子ケア事業（訪問1,500円/デイ2,400円/泊6,000円・上限3回・非課税免除）
- 出産費用助成金（横浜独自・子1人最大9万円）
- 妊婦健康診査費用助成（補助券14枚82,700円＋助成金5万円）

いずれも横浜市公式サイトの一次情報から金額・条件を確認（各行の official_url が出典）。
生成→復元 round-trip 成功、4件とも index 化を確認。

**所感（工数の目安）**: 1制度あたり「対象検索→公式ページ精読→金額・条件の抜き出し」で、
横浜のように公式が整備された大規模市では比較的速い。全国・県共通（児童手当・国保・国民年金・
高額療養費・妊婦健診 等）はテンプレ＋パラメータで量産でき、真の調査は自治体独自の15〜25制度程度。

## 公開前に必要な共通UI整備（フェーズ1で予告・パイロットで確認済み）

複数県のデータを本番公開する前に、`build/build_site.py` の以下を都道府県対応にする必要がある
（東京のみの現状では顕在化しないが、2県目を入れると表示が崩れる）:

1. **比較ハブ(hikaku)の都道府県スコープ化** — 現状は全自治体を横断集計するため、
   「東京都の◯◯を比較」ページに他県の行が混入する。県別ハブ化、または 関東横断ハブ＋県ラベルへ。
2. **トップ/エリア索引の階層化** — 「62自治体」固定表示や単一グリッドを、
   「関東 → 都県 → 自治体」の階層と動的カウントに。
3. **`region_of`（地域別ランキング）** — 東京の 23区/多摩/島しょ 区分を各県に拡張。
