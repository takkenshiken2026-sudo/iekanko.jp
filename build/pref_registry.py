#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""都道府県レジストリ（単一ソース）。

build_site.py（生成）と rebuild_db_from_docs.py（復元）の両方から import する。
DB に依存しないため、DB未作成の復元時でも安全に読み込める
（build_site は起動時に DB を読むため rebuild から import できない。その回避も兼ねる）。

対象エリアを広げるときは、ここに
  1) PREFECTURES へ (都道府県コード -> (URLスラッグ, 表示名)) を追加
  2) SLUGS_BY_PREF へ そのコードの {自治体名: スラッグ} を追加
するだけで、生成・復元の両パイプラインが追従する。
"""

# 都道府県コード（全国地方公共団体コードの上2桁・文字列）-> (URLスラッグ, 表示名)。
# 現状は関東1都6県を定義。実データは tokyo(13) のみ。他県は自治体スラッグ投入後に有効化。
PREFECTURES = {
    "08": ("ibaraki",  "茨城県"),
    "09": ("tochigi",  "栃木県"),
    "10": ("gunma",    "群馬県"),
    "11": ("saitama",  "埼玉県"),
    "12": ("chiba",    "千葉県"),
    "13": ("tokyo",    "東京都"),
    "14": ("kanagawa", "神奈川県"),
}

# 東京都62自治体のローマ字スラッグ（公式ドメインに整合。豊島区toshima/利島村toshimamuraを分離）。
# 他県を足すときは SLUGS_BY_PREF に同形式の dict を追加する。
_TOKYO_SLUGS = {
 "世田谷区":"setagaya","渋谷区":"shibuya","杉並区":"suginami","練馬区":"nerima","新宿区":"shinjuku",
 "港区":"minato","中央区":"chuo","江東区":"koto","大田区":"ota","千代田区":"chiyoda","文京区":"bunkyo",
 "台東区":"taito","墨田区":"sumida","品川区":"shinagawa","目黒区":"meguro","中野区":"nakano",
 "豊島区":"toshima","北区":"kita","荒川区":"arakawa","板橋区":"itabashi","足立区":"adachi",
 "葛飾区":"katsushika","江戸川区":"edogawa","八王子市":"hachioji","立川市":"tachikawa","武蔵野市":"musashino",
 "三鷹市":"mitaka","青梅市":"ome","府中市":"fuchu","昭島市":"akishima","調布市":"chofu","町田市":"machida",
 "小金井市":"koganei","小平市":"kodaira","日野市":"hino","東村山市":"higashimurayama","国分寺市":"kokubunji",
 "国立市":"kunitachi","福生市":"fussa","狛江市":"komae","東大和市":"higashiyamato","清瀬市":"kiyose",
 "東久留米市":"higashikurume","武蔵村山市":"musashimurayama","多摩市":"tama","稲城市":"inagi","羽村市":"hamura",
 "あきる野市":"akiruno","西東京市":"nishitokyo","瑞穂町":"mizuho","日の出町":"hinode","檜原村":"hinohara",
 "奥多摩町":"okutama","大島町":"oshima","利島村":"toshimamura","新島村":"niijima","神津島村":"kozushima",
 "三宅村":"miyake","御蔵島村":"mikurajima","八丈町":"hachijo","青ヶ島村":"aogashima","小笠原村":"ogasawara",
}

# 神奈川県（フェーズ2・第1弾。政令市→人口上位市へ順次拡大）。スラッグは公式ドメインに整合。
_KANAGAWA_SLUGS = {
    "横浜市": "yokohama", "川崎市": "kawasaki", "相模原市": "sagamihara",
    "藤沢市": "fujisawa", "横須賀市": "yokosuka",
    "平塚市": "hiratsuka", "茅ヶ崎市": "chigasaki", "大和市": "yamato",
}

# 都道府県コード -> {自治体名: スラッグ}
SLUGS_BY_PREF = {
    "13": _TOKYO_SLUGS,
    "14": _KANAGAWA_SLUGS,
}


def norm_code(code):
    """prefecture_code を2桁文字列に正規化（None/int/str を許容）。既定は東京(13)。"""
    if code is None or code == "":
        return "13"
    return str(code).zfill(2)


def pref_slug(code):
    """都道府県コード -> URLスラッグ（未知は 'tokyo' にフォールバック）。"""
    return PREFECTURES.get(norm_code(code), ("tokyo", "東京都"))[0]


def pref_name(code):
    """都道府県コード -> 表示名（未知は '東京都' にフォールバック）。"""
    return PREFECTURES.get(norm_code(code), ("tokyo", "東京都"))[1]


# URLスラッグ -> 都道府県コード（逆引き。復元時のパス解釈に使用）。
SLUG2CODE = {slug: code for code, (slug, _name) in PREFECTURES.items()}
