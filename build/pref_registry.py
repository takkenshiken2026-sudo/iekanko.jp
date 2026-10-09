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
    "厚木市": "atsugi", "小田原市": "odawara", "鎌倉市": "kamakura",
    "秦野市": "hadano", "海老名市": "ebina", "座間市": "zama",
    "伊勢原市": "isehara", "綾瀬市": "ayase", "逗子市": "zushi",
    "三浦市": "miura", "南足柄市": "minamiashigara",
    "葉山町": "hayama", "寒川町": "samukawa", "大磯町": "oiso",
    "二宮町": "ninomiya", "大井町": "oi", "松田町": "matsuda",
    "開成町": "kaisei", "愛川町": "aikawa",
    "中井町": "nakai", "山北町": "yamakita", "箱根町": "hakone",
    "真鶴町": "manazuru", "湯河原町": "yugawara", "清川村": "kiyokawa",
}

# 埼玉県（フェーズ2・第2県。政令市・中核市から順次拡大）。スラッグは公式ドメインに整合。
_SAITAMA_SLUGS = {
    "さいたま市": "saitama", "川口市": "kawaguchi", "川越市": "kawagoe",
    "越谷市": "koshigaya", "所沢市": "tokorozawa", "草加市": "soka",
    "春日部市": "kasukabe", "上尾市": "ageo", "熊谷市": "kumagaya",
    "新座市": "niiza", "戸田市": "toda", "朝霞市": "asaka",
    "三郷市": "misato", "入間市": "iruma", "深谷市": "fukaya",
    "久喜市": "kuki", "鴻巣市": "kounosu", "ふじみ野市": "fujimino",
    "狭山市": "sayama", "東松山市": "higashimatsuyama", "本庄市": "honjo",
    "坂戸市": "sakado", "和光市": "wako", "八潮市": "yashio",
    "行田市": "gyoda", "秩父市": "chichibu", "飯能市": "hanno",
    "加須市": "kazo", "羽生市": "hanyu", "富士見市": "fujimi",
    "蕨市": "warabi", "志木市": "shiki", "桶川市": "okegawa",
    "北本市": "kitamoto", "蓮田市": "hasuda", "幸手市": "satte",
    "鶴ヶ島市": "tsurugashima", "日高市": "hidaka", "吉川市": "yoshikawa",
    "白岡市": "shiraoka", "三芳町": "miyoshi",
    "伊奈町": "ina", "宮代町": "miyashiro", "杉戸町": "sugito",
    "松伏町": "matsubushi", "寄居町": "yorii", "上里町": "kamisato",
    "毛呂山町": "moroyama", "越生町": "ogose", "滑川町": "namegawa",
    "嵐山町": "ranzan", "小川町": "ogawa", "川島町": "kawajima",
    "吉見町": "yoshimi", "鳩山町": "hatoyama", "皆野町": "minano",
    "長瀞町": "nagatoro",
    "ときがわ町": "tokigawa", "横瀬町": "yokoze", "小鹿野町": "ogano",
    "東秩父村": "higashichichibu", "美里町": "saitama-misato", "神川町": "kamikawa",
}

# 千葉県（フェーズ2・第3県。政令市・中核市・人口上位市から順次拡大）。スラッグは公式ドメインに整合。
_CHIBA_SLUGS = {
    "千葉市": "chiba", "船橋市": "funabashi", "松戸市": "matsudo",
    "市川市": "ichikawa", "柏市": "kashiwa",
    "流山市": "nagareyama", "八千代市": "yachiyo", "習志野市": "narashino",
    "浦安市": "urayasu", "佐倉市": "sakura", "成田市": "narita",
    "市原市": "ichihara", "野田市": "noda", "木更津市": "kisarazu",
    "我孫子市": "abiko", "鎌ケ谷市": "kamagaya", "印西市": "inzai",
    "四街道市": "yotsukaido", "八街市": "yachimata", "白井市": "shiroi",
    "富里市": "tomisato", "茂原市": "mobara", "東金市": "togane",
    "君津市": "kimitsu", "袖ケ浦市": "sodegaura", "旭市": "asahi",
    "銚子市": "choshi", "館山市": "tateyama", "大網白里市": "oamishirasato",
}

# 茨城県（フェーズ2・第4県。マル福制度。県庁所在地・研究学園都市・人口上位市から順次拡大）。
_IBARAKI_SLUGS = {
    "水戸市": "mito", "つくば市": "tsukuba", "日立市": "hitachi",
    "ひたちなか市": "hitachinaka", "土浦市": "tsuchiura", "古河市": "koga",
    "取手市": "toride", "牛久市": "ushiku", "守谷市": "moriya",
    "神栖市": "kamisu", "筑西市": "chikusei", "龍ケ崎市": "ryugasaki",
    "常総市": "joso", "笠間市": "kasama", "鹿嶋市": "kashima",
    "坂東市": "bando", "石岡市": "ishioka", "那珂市": "naka",
    "つくばみらい市": "tsukubamirai", "下妻市": "shimotsuma", "結城市": "yuki",
    "常陸大宮市": "hitachiomiya", "常陸太田市": "hitachiota", "北茨城市": "kitaibaraki",
}

# 栃木県（フェーズ2・第5県。県内現物給付で窓口無料。県庁所在地・人口上位市から順次拡大）。
# さくら市は千葉・佐倉市（sakura）とスラッグが衝突するため sakura-tochigi で分離。
_TOCHIGI_SLUGS = {
    "宇都宮市": "utsunomiya", "小山市": "oyama", "栃木市": "tochigi",
    "足利市": "ashikaga", "佐野市": "sano", "那須塩原市": "nasushiobara",
    "鹿沼市": "kanuma", "日光市": "nikko", "真岡市": "moka",
    "大田原市": "ohtawara", "下野市": "shimotsuke", "さくら市": "sakura-tochigi",
}

# 群馬県（フェーズ2・第6県。福祉医療で現物給付・原則無料。県庁所在地・人口上位市から順次拡大）。
# 太田市は東京・大田区（ota）とスラッグが衝突するため ota-gunma で分離。
_GUNMA_SLUGS = {
    "前橋市": "maebashi", "高崎市": "takasaki", "太田市": "ota-gunma",
    "伊勢崎市": "isesaki", "桐生市": "kiryu", "渋川市": "shibukawa",
    "館林市": "tatebayashi", "藤岡市": "fujioka", "安中市": "annaka",
    "みどり市": "midori", "富岡市": "tomioka", "沼田市": "numata",
}

# 都道府県コード -> {自治体名: スラッグ}
SLUGS_BY_PREF = {
    "13": _TOKYO_SLUGS,
    "14": _KANAGAWA_SLUGS,
    "11": _SAITAMA_SLUGS,
    "12": _CHIBA_SLUGS,
    "08": _IBARAKI_SLUGS,
    "09": _TOCHIGI_SLUGS,
    "10": _GUNMA_SLUGS,
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
