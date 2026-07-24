# 網羅性向上のための調査データ（2026-07-24）

役所PDF・公式サイトの精読／横断チェックで判明した「サイト未掲載の制度」「金額・条件の追補」
「出典リンクの修正」を、元DB（`gov_life_support.sqlite3`）へ投入しやすい形で整理したもの。

恒久反映は DB の `programs`（および `program_municipalities`）を更新 →
`build/build_site.py` で `docs/` を再生成する。**このディレクトリのCSVは中間成果物**。

## ファイル

| ファイル | 内容 | 件数 | 確度 |
|---|---|---|---|
| `maruao_additions.csv` | 高校生等医療費助成(マル青)の欠落自治体への追加 | 13 | 11=公式確定 / 2=金額要確認 |
| `postpartum_and_maternal.csv` | 産後ケア掲載漏れ＋島しょ妊婦支援 | 6 | 5=公式確定 / 1=金額要確認 |
| `new_programs_candidates.csv` | PDF精読で発見した未掲載の独自制度候補 | 33 | candidate（多くは旧PDF由来・要現在確認） |
| `source_link_corrections.csv` | 出典リンク切れの差し替え/削除 | 6 | 八丈3=確定 / 品川・奥多摩=削除候補 |

## status 列の意味
- `verified` … 公式ドメインのページで対象・金額・URLを確認済み。そのまま追加可。
- `needs_amount_check` … 実施は確実だが金額/負担の数値が未取得。追加時に原課/要綱で要確認。
- `candidate` … 主に旧PDF（小笠原2008・青ヶ島2018等）由来。制度の存在発見が主眼、数値は要現在確認。

## 関連レポート（`audit/`）
- `municipal-pdf-source-audit.md` … PDF出典15ページの本文突合＋リンク死活
- `cross-municipality-gap-check.md` … 全62自治体の共通制度 横断カバレッジ
- `pdf-enrichment-findings.md` … 5村のPDF全文精読による制度・金額抽出

## 優先度
1. **マル青13**（都統一制度・確定欠落）→ 最優先追加
2. **産後ケア3（港区・檜原・御蔵島）**＋**リンク切れ八丈3件の差し替え**
3. 品川配食・奥多摩敬老祝い金の**現存確認 → 削除 or 修正**
4. 島しょ妊婦支援3・PDF独自制度33 → 現在額を確認しつつ順次追加
