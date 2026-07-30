#!/usr/bin/env python3
"""自治体別の OG 画像（1200×630 PNG）を docs/assets/og/<slug>.png に生成する。

共有リンク（X・Facebook・LINE 等）に、共通の og.png ではなく
「東京都 ○○区」の名前入り画像が出るようにして CTR を上げる目的。
per-page（制度ごと3000+枚）はリポジトリを肥大化させ検索順位にも効かないため、
このサイトの核である 62自治体ごと（≒62枚）の粒度で生成する。

- ブランドの実ロゴ（docs/assets/icon-512.png）と配色をそのまま使い、共通og.pngと統一。
- slug→自治体名 の対応は build_site.py の SLUGS を単一の出所として再利用。
- 決定性: 乱数・時刻を使わないので何度実行しても同じ出力（差分は実変更のみ）。

使い方:
    python3 build/rebuild_db_from_docs.py   # 先にDB復元（SLUGS取得のため build_site が読む）
    python3 build/build_og_images.py
"""
import os
import sys
from PIL import Image, ImageDraw, ImageFont

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "build"))
from build_site import SLUGS  # slug の単一の出所（import 時にDBを開くので事前復元が必要）

ASSETS = os.path.join(ROOT, "docs", "assets")
OUT_DIR = os.path.join(ASSETS, "og")
LOGO = os.path.join(ASSETS, "icon-512.png")
FONT_PATH = "/usr/share/fonts/truetype/fonts-japanese-gothic.ttf"

W, H = 1200, 630
BG = (244, 246, 251)        # og.png と同じ薄いグレー背景
NAVY = (27, 36, 64)         # 見出しの濃紺
BLUE = (21, 88, 214)        # ブランドの青（theme-color #1558d6）
MUTED = (90, 100, 120)      # 補助テキスト


def _font(size):
    return ImageFont.truetype(FONT_PATH, size)


def _text_w(draw, text, font, stroke=0):
    l, t, r, b = draw.textbbox((0, 0), text, font=font, stroke_width=stroke)
    return r - l


def _fit_font(draw, text, max_w, start, stroke=0, floor=48):
    """max_w に収まる最大のフォントサイズを返す（長い自治体名対策）。"""
    size = start
    while size > floor and _text_w(draw, text, _font(size), stroke) > max_w:
        size -= 4
    return _font(size)


def build_one(name, slug, logo_img):
    img = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(img)

    # 左上: ロゴ + サイト名（共通og.pngと同じブランド表示）
    mark = logo_img.resize((104, 104), Image.LANCZOS)
    img.paste(mark, (72, 60), mark)
    d.text((196, 78), "くらしの制度ナビ", font=_font(40), fill=NAVY)
    d.text((198, 128), "iekanko.jp", font=_font(26), fill=BLUE)

    # ヒーロー: 東京都 + 自治体名（自治体名を主役に）
    d.text((76, 268), "東京都", font=_font(46), fill=BLUE)
    hero_font = _fit_font(d, name, W - 150, start=132, stroke=1)
    d.text((72, 318), name, font=hero_font, fill=NAVY, stroke_width=1, stroke_fill=NAVY)

    # 下部: サブコピー
    d.text((76, 548), "給付・手当・助成をまるわかり比較 ｜ 出典・最終確認日つき",
           font=_font(30), fill=MUTED)

    os.makedirs(OUT_DIR, exist_ok=True)
    img.save(os.path.join(OUT_DIR, f"{slug}.png"), optimize=True)


def main():
    if not os.path.exists(LOGO):
        sys.exit(f"ロゴが見つかりません: {LOGO}")
    logo_img = Image.open(LOGO).convert("RGBA")
    n = 0
    for name, slug in sorted(SLUGS.items(), key=lambda kv: kv[1]):
        build_one(name, slug, logo_img)
        n += 1
    print(f"OG画像 生成完了: {n}枚 -> {OUT_DIR}")


if __name__ == "__main__":
    main()
