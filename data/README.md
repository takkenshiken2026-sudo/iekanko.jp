# 不動産・交通データ（reinfolib_tokyo.db）

東京都の自治体ページに掲載する「住まいの相場・駅乗降」用のSQLiteです。

## ファイル

- `reinfolib_tokyo.db` … 集計済みDB（地価公示・駅別乗降客数・自治体統計）
- 公開用サマリーJSONは `docs/assets/data/area/<slug>.json`

## 出典

国土交通省「国土数値情報」（CC BY 4.0）

- 地価公示（L01）2025年・東京都
- 駅別乗降客数（S12）2024年
- 行政区域（N03）2024年・東京都

## 再構築

```bash
# GeoJSON を /tmp/reinfolib に展開したうえで
python3 build/build_reinfolib_db.py
```

ローカルの `reinfolib_tokyo.db`（不動産情報ライブラリ由来）を使う場合は、
同パスに配置してスキーマを合わせるか、取り込みスクリプトを追加してください。
