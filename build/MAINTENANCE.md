# 原本DBの更新・再生成フロー（メンテナンス手順）

このリポジトリには元DB `gov_life_support.sqlite3` を**含めていません**（`.gitignore` で
`*.sqlite3` を除外＝内部データは非公開の方針）。一方で公開中の `docs/` には、サイト生成に
必要な全データ（制度・自治体・出典・対象/金額/内容などの facts・ライフイベント割当）が
含まれているため、**docs から原本DBを復元できます**。

これにより「DBが手元に無くても、原本を編集して再生成する」運用が可能です。

## テーブル構成（build_site.py が参照する6テーブル）
`municipalities` / `programs` / `program_municipalities` / `program_facts`
（対象者・支給額・内容給付・申請方法・条件＝各 dt/dd はここ） / `program_life_events` / `life_events`

## 更新フロー（3ステップ）

```bash
# 1) 公開中の docs から原本DBを復元
python3 build/rebuild_db_from_docs.py         # -> gov_life_support.sqlite3 を生成

# 2) 原本DBを編集（例：金額や内容の更新、新規制度の追加）
#    - 既存の項目更新/追加は program_facts を UPSERT（fact_type: target/amount/benefit/application/condition ...）
#    - 新規制度は programs + program_municipalities + program_facts を INSERT
#    - 既に docs に反映済みの加筆は、手順1の復元時点でDBに取り込まれている
#      （data/enrichment/*.csv は追加調査の元ネタとして保持）

# 3) DB から docs を再生成（CNAME/.nojekyll は保持される）
python3 build/build_site.py                    # SEIDO_DB 既定 = gov_life_support.sqlite3
```

`docs/` を commit → 公開元ブランチ（現状 `claude/seido-navi-db-publish-9t2kq4`）へマージで本番反映。

## 復元の忠実性（検証済み・2026-07-24）
`rebuild_db_from_docs.py` → `build_site.py`（**`PYTHONHASHSEED=0` 固定**）の往復再生成で：
- **掲載（index）1,869ページは現行docsとバイト完全一致**。
- **全3,058ページで facts（対象/金額/内容/出典）の内容喪失はゼロ**（機械検証済み）。
- noindex（暫定データ）1,189ページの差分は次の2点のみ＝**制度データ自体は不変**：
  1. facts の表示順が build_site の正準順（対象→金額→内容…）に整列
  2. 比較(hikaku)カテゴリの自動リンクが `classify()` で再計算（隠し列
     `benefit_description`/`target_description` を facts から近似するため一部ズレる）
→ 次回の再生成で docs は「DBの出力」に正規化され、以後は安定（fixpoint）。

> **決定性**: build_site は set 反復順が `PYTHONHASHSEED` に依存するため、
> 再生成時は `PYTHONHASHSEED=0 python3 build/build_site.py` を推奨（seed固定で完全再現）。
>
> **注意**: 元DB本体は入手できないため「元DBそのものとのバイナリ差分」は比較不可。
> 検証しているのは「復元DB→再生成した**サイト**が現行docsと一致し、内容が失われないこと」。
> 元DBにのみ在るサイト非表示の列（内部審査メモ・amount_min/max 等）は復元対象外。

## 補足
- `build/build_site.py` 末尾に `if __name__ == "__main__": main()` を追加済み（実行部の補完）。
- 相場・駅データ（相場グラフ等）は別DB `data/reinfolib_tokyo.db`（リポジトリ同梱）から生成。
- 復元DBは公開情報のみで構成されるため内部の審査用データは含まない。恒久的に手元DBを
  正としたい場合は、`.gitignore` に `!gov_life_support.sqlite3` の例外を足してコミットも可能。
