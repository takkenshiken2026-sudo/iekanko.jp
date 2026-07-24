# 不動産・交通データ（reinfolib_tokyo.db）

東京都の自治体ページに掲載する「住まいの相場・駅乗降」用のSQLiteです。

## ファイル

- `reinfolib_tokyo.db` … 不動産情報ライブラリ由来の東京都データ
- 公開用サマリーJSONは `docs/assets/data/area/<slug>.json`

## 主なテーブル

| テーブル | 内容 |
|---|---|
| `municipalities` | 62自治体 |
| `municipality_trade_stats` | 取引・成約価格の集計（マンション等） |
| `land_price_points` | 地価公示・都道府県地価調査ポイント |
| `station_passengers` | 駅別乗降客数 |
| `municipality_page_meta` | 自治体ページ用メタ |

## サマリー再生成

```bash
python3 build/export_reinfolib_summaries.py
```

駅の自治体割当には、展開済みの行政区域GeoJSON（`N03`）があると精度が上がります。
