# iekanko.jp ｜ くらしの制度ナビ（東京都の給付・手当・助成 比較）

東京都62自治体（23区・26市・5町・8村）の給付金・手当・助成・減免制度を、
**出典URL・最終確認日つき**で自治体ごと／制度カテゴリごとに比較できる静的サイトです。

- 公開URL: https://iekanko.jp
- 配信: GitHub Pages（`docs/` を公開ディレクトリとして配信）

## リポジトリ構成

```
docs/            公開する静的サイト本体（GitHub Pages の公開ディレクトリ）
  index.html     トップ（自治体一覧）
  area/tokyo/…   自治体ハブ / ライフイベント別 / 制度詳細ページ
  hikaku/…       制度カテゴリ別の自治体横断比較
  assets/        CSS
  sitemap.xml    サイトマップ
  robots.txt
  CNAME          カスタムドメイン設定（iekanko.jp）
  .nojekyll      Jekyll 変換を無効化
build/
  build_site.py  DB から docs/ を再生成する静的サイトジェネレータ
  schema.sql     元データDBのスキーマ（参考）
```

> 注: 元データDB（`gov_life_support.sqlite3`）と収集した生テキスト・レビュー用CSVは、
> 内部作業用のためこのリポジトリには含めていません。サイトの再生成には別途DBが必要です。

## サイトの再生成

`docs/` は `build/build_site.py` が DB から生成した成果物です。データを更新して
作り直す場合は、リポジトリ直下に DB（`gov_life_support.sqlite3`）を置いて実行します。

```bash
# 本番ドメインは既定で https://iekanko.jp。必要なら SEIDO_BASE_URL で上書き可。
python3 build/build_site.py
```

- 出力先は `docs/`。`CNAME` と `.nojekyll` は上書きされず保持されます。
- 別のDBパスを使う場合は `SEIDO_DB=/path/to.sqlite3 python3 build/build_site.py`。

## GitHub Pages の公開手順

1. このブランチを `main`（デフォルトブランチ）へマージする。
2. リポジトリの **Settings → Pages** を開く。
3. **Source** を `Deploy from a branch`、**Branch** を `main` / `/docs` に設定して保存。
4. **Custom domain** に `iekanko.jp` を入力して保存（`docs/CNAME` があるので自動入力されます）。
5. DNS 側で `iekanko.jp` を GitHub Pages に向ける:
   - Apex ドメイン用 A レコード:
     `185.199.108.153` / `185.199.109.153` / `185.199.110.153` / `185.199.111.153`
     （AAAA を使う場合: `2606:50c0:8000::153` 〜 `8003::153`）
   - `www` を使う場合は `www.iekanko.jp` を `takkenshiken2026-sudo.github.io` に CNAME。
6. DNS 反映後、Pages 設定の **Enforce HTTPS** を有効化する。

## データについての注意

各自治体・公的機関の公表情報をもとに整理した比較・案内サービスです。
金額・対象・期限などは変更されることがあります。最新かつ正確な内容は、
各制度の公式ページ（各ページに出典リンクを掲載）で必ずご確認ください。
