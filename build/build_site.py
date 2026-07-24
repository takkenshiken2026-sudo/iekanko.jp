#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
くらしの制度ナビ 静的サイトジェネレータ (SSG)
DB(gov_life_support.sqlite3) から SEO最適化済みの静的HTMLを生成する。

生成物 -> docs/  (GitHub Pages 公開ディレクトリ)
  /                                  トップ
  /area/tokyo/<muni>/                自治体ハブ
  /area/tokyo/<muni>/<event>/        自治体 × ライフイベント
  /area/tokyo/<muni>/seido/<id>/     制度詳細（本命ロングテール）
  /sitemap.xml  /robots.txt  /assets/style.css

各ページ: <title>/meta description/canonical/OGP/robots(品質ゲート)/JSON-LD
(BreadcrumbList, GovernmentService, FAQPage) / 出典リンク / 最終更新日 を出力。
"""
import sqlite3, os, html, json, re, sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB   = os.environ.get("SEIDO_DB", os.path.join(ROOT, "gov_life_support.sqlite3"))
OUT  = os.path.join(ROOT, "docs")

# ▼ 本番ドメイン（canonical / sitemap / OGP に使用）。環境変数 SEIDO_BASE_URL で上書き可。
BASE_URL = os.environ.get("SEIDO_BASE_URL", "https://iekanko.jp").rstrip("/")
SITE_NAME = "くらしの制度ナビ｜東京都の給付・手当・助成 まるわかり比較"
SITE_SHORT = "くらしの制度ナビ"

# ── 運営者情報（E-E-A-T用。★実名・連絡先を記入すると信頼性ページが完成します）──────
OPERATOR_NAME  = os.environ.get("SEIDO_OPERATOR",  "【要記入：運営者名または屋号】")
CONTACT_EMAIL  = os.environ.get("SEIDO_CONTACT",   "【要記入：連絡先メールアドレス】")
ESTABLISHED    = os.environ.get("SEIDO_ESTABLISHED", "2026")
# Google Analytics 4 測定ID（全ページの <head> に gtag を出力）。空文字で無効化可。
GA_MEASUREMENT_ID = os.environ.get("SEIDO_GA_ID", "G-9TB0TXT8X0").strip()
# プライバシーポリシーのアクセス解析表記。未設定なら記載を省略。
ANALYTICS_NOTE = os.environ.get(
    "SEIDO_ANALYTICS",
    "Google Analytics 4（測定ID: %s）" % GA_MEASUREMENT_ID if GA_MEASUREMENT_ID else "",
)

# ── 品質ゲート（YMYL: 未検証の薄いページをインデックスさせない）────────────
GATE_MIN_CONFIDENCE = 82   # 制度の平均confidenceがこれ未満なら noindex

# ── 62自治体のローマ字スラッグ（公式ドメインに整合。豊島区toshima/利島村toshimamuraを分離）─
SLUGS = {
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

# ── 62自治体の読み（五十音順の並べ替え用。区/市/町村を対等に一覧するため）──────────
YOMI = {
 "千代田区":"ちよだ","中央区":"ちゅうおう","港区":"みなと","新宿区":"しんじゅく","文京区":"ぶんきょう",
 "台東区":"たいとう","墨田区":"すみだ","江東区":"こうとう","品川区":"しながわ","目黒区":"めぐろ",
 "大田区":"おおた","世田谷区":"せたがや","渋谷区":"しぶや","中野区":"なかの","杉並区":"すぎなみ",
 "豊島区":"としま","北区":"きた","荒川区":"あらかわ","板橋区":"いたばし","練馬区":"ねりま",
 "足立区":"あだち","葛飾区":"かつしか","江戸川区":"えどがわ",
 "八王子市":"はちおうじ","立川市":"たちかわ","武蔵野市":"むさしの","三鷹市":"みたか","青梅市":"おうめ",
 "府中市":"ふちゅう","昭島市":"あきしま","調布市":"ちょうふ","町田市":"まちだ","小金井市":"こがねい",
 "小平市":"こだいら","日野市":"ひの","東村山市":"ひがしむらやま","国分寺市":"こくぶんじ","国立市":"くにたち",
 "福生市":"ふっさ","狛江市":"こまえ","東大和市":"ひがしやまと","清瀬市":"きよせ","東久留米市":"ひがしくるめ",
 "武蔵村山市":"むさしむらやま","多摩市":"たま","稲城市":"いなぎ","羽村市":"はむら","あきる野市":"あきるの",
 "西東京市":"にしとうきょう","瑞穂町":"みずほ","日の出町":"ひので","檜原村":"ひのはら","奥多摩町":"おくたま",
 "大島町":"おおしま","利島村":"としま","新島村":"にいじま","神津島村":"こうづしま","三宅村":"みやけ",
 "御蔵島村":"みくらじま","八丈町":"はちじょう","青ヶ島村":"あおがしま","小笠原村":"おがさわら",
}

EVENTS = {  # slug -> (表示名, 導入文)
 "pregnancy_birth":("妊娠・出産","妊娠がわかってから出産までにもらえる給付金・助成と、必要な手続きをまとめています。"),
 "childcare":("子育て","児童手当・医療費助成・保育料軽減など、子育て世帯が受けられる支援をまとめています。"),
 "moving":("引っ越し","転入・転出の手続きと、引っ越しに関わる助成・支援をまとめています。"),
 "retirement_unemployment":("退職・失業","退職・失業時の保険料軽減・給付・支援制度をまとめています。"),
 "elderly_care":("高齢・介護","高齢者・介護が必要な方が受けられる助成・サービスをまとめています。"),
}

# ライフイベント別メタ（目的・年代の発見導線／カラー＝検証済みパレット slot1-5／アイコン）
EV_META = {
 "pregnancy_birth":("これから出産する方","妊娠・出産期","#e87ba4",
   '<path d="M12 21C7 17 4 14 4 10.5 4 8 6 6 8.5 6c1.6 0 2.9 1 3.5 2C12.6 7 13.9 6 15.5 6 18 6 20 8 20 10.5 20 14 17 17 12 21Z"/>'),
 "childcare":("子育て世帯","子育て世代","#2a78d6",
   '<circle cx="12" cy="8" r="3.2"/><path d="M6 20c0-3.3 2.7-6 6-6s6 2.7 6 6"/>'),
 "moving":("引っ越し・住まい探し","住み替え・全世代","#1baf7a",
   '<path d="M4 11 12 4l8 7"/><path d="M6 10v9h12v-9"/>'),
 "retirement_unemployment":("退職・失業した方","現役〜シニア","#eda100",
   '<rect x="4" y="8" width="16" height="11" rx="2"/><path d="M9 8V6a2 2 0 0 1 2-2h2a2 2 0 0 1 2 2v2"/>'),
 "elderly_care":("シニア・介護","シニア世代","#eb6834",
   '<circle cx="12" cy="12" r="8"/><path d="M12 8v8M8 12h8"/>'),
}
def icon_svg(ev):
    paths = EV_META[ev][3]
    return ('<svg class="ev-ic" viewBox="0 0 24 24" fill="none" stroke="currentColor" '
            'stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">'+paths+'</svg>')

# モノクロのシェブロン・アイコン（三角記号{CHEV_R}{CHEV_L}▲の代替。currentColorで文字色に追従）
_CHV='<svg class="chev" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="%s"/></svg>'
CHEV_R=_CHV % "M9 5l7 7-7 7"
CHEV_L=_CHV % "M15 5l-7 7 7 7"
CHEV_U=_CHV % "M5 15l7-7 7 7"

# fact_type -> (表示ラベル, 表示順)。未定義は末尾に。
FACT_LABELS = {
 "target":("対象者",10),"target_detail":("対象の詳細",11),"amount":("支給額・助成額",20),
 "benefit":("内容・給付",30),"support":("支援内容",31),"service":("サービス内容",32),
 "coverage":("対象範囲",33),"condition":("条件",40),"limit":("上限",41),
 "application":("申請方法",50),"application_method":("申請方法",50),
 "document":("必要書類",55),"documents":("必要書類",55),"required_document":("必要書類",55),
 "required_documents":("必要書類",55),"deadline":("申請期限",60),"schedule":("日程",61),
 "duration":("期間",62),"payment":("支給時期",70),"payment_timing":("支給時期",70),
 "online":("オンライン手続き",75),"office":("窓口",80),"purpose":("目的",85),
 "repayment":("返済",86),"capacity":("定員",87),"start":("開始",88),
 "related_procedures":("関連手続き",89),"move_value":("引っ越し関連",90),
}
def fact_label(ft): return FACT_LABELS.get(ft, (ft, 99))

# ── 標準給付タクソノミ（比較ページ用。coverage_matrix.py と同一定義）─────────────
# (カテゴリID, ラベル, 生活イベントslug, 必須kw(any), 除外kw(any))
TAXONOMY = [
 ("preg_kenshin","妊婦健診・産婦健診助成","pregnancy_birth",["妊婦健診","妊婦健康診査","産婦健診","妊産婦健"],[]),
 ("preg_gift","出産・子育て応援給付(伴走)","pregnancy_birth",["出産応援","子育て応援","伴走型","出産・子育て応援","応援ギフト","妊娠届出時"],[]),
 ("preg_shussanhi","出産費用助成・出産一時金上乗せ","pregnancy_birth",["出産費助成","出産費用","出産助成","ハッピーマザー","出産育児一時金"],[]),
 ("preg_sango_care","産後ケア事業","pregnancy_birth",["産後ケア","産後母子","産後デイ","産後ショート","産婦ケア"],[]),
 ("preg_funin","不妊・不育治療助成","pregnancy_birth",["不妊","不育","妊活"],[]),
 ("preg_tamondo","多胎児支援","pregnancy_birth",["多胎","双子","ふたご","三つ子"],[]),
 ("child_teate","児童手当","childcare",["児童手当"],["調査委託","プロポーザル"]),
 ("child_fuyou","児童扶養手当(ひとり親)","childcare",["児童扶養手当"],[]),
 ("child_iryo","子ども・乳幼児医療費助成","childcare",["子ども医療費","乳幼児医療","子育て医療","義務教育就学児医療","高校生等医療","マル子","マル乳","こども医療費","子供医療費","子どもの医療費","子ども等医療","児童医療費","すこやか医療費","乳幼児の医療"],[]),
 ("child_hitorioya","ひとり親家庭医療費助成(マル親)","childcare",["ひとり親家庭医療","母子家庭医療","ひとり親医療","マル親","ひとり親家庭.{0,3}医療","ひとり親家庭.{0,4}医療費"],[]),
 ("child_shugaku","就学援助","childcare",["就学援助","就学奨励","学用品費"],[]),
 ("child_hoiku_gen","保育料軽減・多子軽減","childcare",["保育料","副食費","給食費無償","第二子","多子"],["就学援助"]),
 ("child_ninkagai","認可外保育料補助","childcare",["認可外","ベビーシッター","一時預かり","病児保育","産休明け"],[]),
 ("child_iwai","出産・入学祝金/子育てクーポン","childcare",["出産祝","誕生祝","入学祝","入学準備","子育てクーポン","誕生記念","バースデー","子育て応援券","子育て利用券","出産祝金","誕生お祝い","1歳プレゼント","サポートクーポン"],[]),
 ("child_shogakukin","奨学金・進学支援","childcare",["奨学金","奨学資金","奨学","育英","進学支援","高校生等奨学","入学支度金","入学支度","入学資金","入学一時金","修学資金","就学資金","就学支援金","修学給付","受験生"],[]),
 ("child_omutsu_baby","乳児おむつ・ミルク支援","childcare",["おむつ定期便","乳児用おむつ","おむつ配送","ミルク","液体ミルク","0歳児"],["高齢"]),
 ("house_juukyo","住居確保給付金","moving",["住居確保給付"],[]),
 ("house_yachin","家賃補助(若年・子育て・勤労者)","moving",["家賃助成","家賃補助","住み替え家賃","居住支援","家賃債務","礼金","転居費用"],["住居確保給付"]),
 ("house_sansedai","三世代同居・近居支援","moving",["三世代","近居","親元近居"],[]),
 ("house_reform","住宅リフォーム・バリアフリー改修助成","moving",["リフォーム","住宅改修","バリアフリー","住宅設備改修","増改築","改修助成"],["高齢者住宅改修"]),
 ("house_taishin","耐震・ブロック塀・空き家助成","moving",["耐震","ブロック塀","空き家","除却"],[]),
 ("house_eco","住宅省エネ・創エネ・雨水助成","moving",["太陽光","蓄電池","省エネ","創エネ","再エネ","雨水","高断熱","ゼロエミ"],[]),
 ("job_kokuho","国民健康保険料軽減・減免","retirement_unemployment",["国民健康保険料","国民健康保険税","国保料","保険料軽減","保険税軽減","国保税","国保料軽減","国保税軽減"],[]),
 ("job_nenkin","国民年金保険料免除","retirement_unemployment",["国民年金","年金保険料免除","年金免除","付加年金"],[]),
 ("job_shurou","就労支援・職業訓練","retirement_unemployment",["就労支援","職業訓練","再就職","求職","就職支援","マザーズ"],[]),
 ("job_kashitsuke","生活福祉資金・緊急小口貸付","retirement_unemployment",["生活福祉資金","緊急小口","貸付","応急小口"],["奨学","育英","入学資金","入学支度","入学一時金","修学資金"]),
 ("job_konkyu","生活困窮者自立支援・家計相談","retirement_unemployment",["生活困窮","自立支援","家計改善","家計相談","くらしとしごと"],[]),
 ("job_shobyo","傷病手当金","retirement_unemployment",["傷病手当"],[]),
 ("eld_omutsu","高齢者紙おむつ支給・助成","elderly_care",["紙おむつ","おむつ支給","おむつ代","おむつ給付","おむつ助成","おむつ費用","おむつ等","日常生活用品.*おむつ","介護用品.*おむつ"],["乳児","0歳児","乳幼児"]),
 ("eld_kaigo_gen","介護保険料減免","elderly_care",["介護保険料","保険料減免"],[]),
 ("eld_hochoki","補聴器購入助成","elderly_care",["補聴器"],[]),
 ("eld_jutaku","高齢者住宅改修・設備改修助成","elderly_care",["高齢者住宅改修","高齢者住宅設備","高齢者リフォーム","住宅改修給付","段差解消"],[]),
 ("eld_vaccine","高齢者ワクチン助成(肺炎球菌/帯状疱疹等)","elderly_care",["肺炎球菌","帯状疱疹","高齢者インフル","高齢者予防接種"],[]),
 ("eld_kinkyu","緊急通報システム・見守り","elderly_care",["緊急通報","救急通報","安否通報","非常通報","代理通報","見守り","徘徊","位置探索","認知症高齢者位置","声かけ","自動通話録音","通話録音装置","シルバーホン"],[]),
 ("eld_haishoku","配食・栄養・食事サービス","elderly_care",["配食","食事サービス","給食サービス","栄養改善"],[]),
 ("eld_iwai","敬老祝い金・長寿祝品","elderly_care",["敬老","長寿","米寿","高齢者祝","祝い金"],[]),
 ("eld_yougu","介護用具・福祉用具・寝具乾燥","elderly_care",["福祉用具","介護用具","寝具乾燥","日常生活用具","用具受領","レンタル"],["障害"]),
 ("dis_iryo","重度心身障害者医療費助成(マル障)","elderly_care",["障害者医療","心身障害者医療","マル障","重度障害者医療"],[]),
 ("dis_yougu","障害者日常生活用具・補装具","elderly_care",["障害.*日常生活用具","補装具","障害者用具","障害児用具"],[]),
 ("low_aircon","エアコン設置助成(低所得/熱中症)","elderly_care",["エアコン","冷房","熱中症"],[]),
 ("low_taxi","タクシー・移送・交通費助成","elderly_care",["タクシー","移送","福祉交通","交通費助成","バス.*助成","リフト付"],[]),
 # ── 既存の検証済みデータで頻出だが未分類だった制度を新カテゴリ化（網羅性向上）──
 ("child_ikusei","児童育成手当","childcare",["児童育成手当"],[]),
 ("dis_teate","心身障害者・特別障害者手当","elderly_care",["心身障害者福祉手当","障害児福祉手当","特別障害者手当","重度心身障害者手当","重度心身障害者福祉手当"],[]),
 ("med_kogaku","高額療養費・限度額認定","retirement_unemployment",["高額療養費","限度額適用認定","限度額適用","高額介護合算","高額医療・高額介護"],[]),
 ("med_sosai","葬祭費（国保・後期高齢）","retirement_unemployment",["葬祭費"],[]),
]
CAT_BY_ID = {c[0]:c for c in TAXONOMY}

# トップ掲載：目的カテゴリ別の金額ランキング（各カテゴリ2制度以上）
# (event_slug, [(cid, 見出し, 単位ラベル, 抽出モード), ...])
AMOUNT_RANK_BY_EVENT = [
 ("childcare", [
   ("child_hoiku_gen", "認可外・認証保育の補助", "月額上限の目安", "hoiku_cap"),
   ("child_iwai", "出産・入学祝金・クーポン", "支給額の目安", "child_gift"),
 ]),
 ("pregnancy_birth", [
   ("child_iwai", "自治体の出産祝金・クーポン", "支給額の目安", "birth_gift"),
   ("preg_shussanhi", "出産費用の自治体助成", "支給額の目安", "birth_aid"),
   ("preg_funin", "不妊・不育治療助成", "助成上限の目安", "funin_cap"),
 ]),
 ("moving", [
   ("house_yachin", "家賃補助", "月額の目安", "rent_monthly"),
   ("house_taishin", "耐震改修の助成", "改修上限の目安", "taishin_cap"),
 ]),
 ("retirement_unemployment", [
   ("low_aircon", "エアコン設置助成", "助成上限の目安", "aircon_cap"),
   ("job_kashitsuke", "緊急小口・生活福祉資金", "貸付上限の目安", "loan_cap"),
 ]),
 ("elderly_care", [
   ("eld_omutsu", "高齢者の紙おむつ助成", "月額上限の目安", "monthly_cap"),
   ("eld_hochoki", "補聴器の購入助成", "助成上限の目安", "purchase_cap"),
   ("dis_teate", "心身障害者福祉手当", "月額の目安", "monthly"),
 ]),
]

def _yen_int(s):
    return int(str(s).replace(",", "").replace("，", ""))

def extract_rank_yen(text, mode):
    """比較可能な円額を抽出。抽出できない／比較不向きなら None。"""
    t = re.sub(r"<[^>]+>", "", text or "")
    t = t.replace("，", ",")
    if not t or "記載を確認中" in t:
        return None
    if mode == "monthly_cap":
        if re.search(r"(利用者負担|自己負担|1割負担)", t) and not re.search(r"(助成|上限|限度|支給)", t):
            return None
        for pat in (
            r"月額\s*上限\s*([0-9,]+)\s*円",
            r"月額\s*([0-9,]+)\s*円を上限",
            r"助成限度額は月額\s*([0-9,]+)\s*円",
            r"月額\s*([0-9,]+)\s*円を限度",
            r"1(?:か|ヶ)?月(?:につき)?\s*([0-9,]+)\s*円上限",
            r"おむつ代助成\s*月\s*([0-9,]+)\s*円",
            r"助成\s*月\s*([0-9,]+)\s*円",
            r"上限\s*([0-9,]+)\s*円",
            r"月額\s*([0-9,]+)\s*円",
            r"月\s*([0-9,]+)\s*円",
        ):
            m = re.search(pat, t)
            if not m:
                continue
            window = t[max(0, m.start()-5): m.end()+12]
            if re.search(r"以内は|負担", window) and "助成" not in window:
                continue
            return _yen_int(m.group(1))
        return None
    if mode == "purchase_cap":
        vals = []
        for m in re.finditer(r"(?:上限|限度額?|助成上限額?|助成額|助成限度額)[^。\d]{0,6}([0-9,]+)\s*円", t):
            vals.append(_yen_int(m.group(1)))
        for m in re.finditer(r"([0-9,]+)\s*円[^。]{0,4}(?:上限|以内)", t):
            vals.append(_yen_int(m.group(1)))
        for m in re.finditer(r"([0-9,]+)\s*円", t):
            v = _yen_int(m.group(1))
            if 10000 <= v <= 300000:
                vals.append(v)
        return max(vals) if vals else None
    if mode == "monthly":
        vals = []
        for m in re.finditer(r"月額\s*([0-9,]+)\s*円", t):
            vals.append(_yen_int(m.group(1)))
        for m in re.finditer(r"([0-9,]+)\s*円", t):
            v = _yen_int(m.group(1))
            if 3000 <= v <= 200000:
                vals.append(v)
        return max(vals) if vals else None
    if mode in ("child_gift", "birth_gift"):
        # 国の伴走型給付（ほぼ全市共通）は除外し、自治体独自のみ
        if any(k in t for k in ("出産・子育て応援給付", "妊婦のための支援給付", "妊婦給付認定後")):
            return None
        if mode == "birth_gift" and re.search(r"入学|学用品", t) and not re.search(r"出生|出産|新生児|妊娠|クーポン", t):
            return None
        vals = []
        for m in re.finditer(r"(\d+(?:\.\d+)?)\s*万円", t):
            vals.append(int(float(m.group(1)) * 10000))
        for m in re.finditer(r"([0-9,]+)\s*円", t):
            v = _yen_int(m.group(1))
            if 5000 <= v <= 300000:
                vals.append(v)
        return max(vals) if vals else None
    if mode == "hoiku_cap":
        if re.search(r"(商品券|タクシー|第[3-9]子|第\d子)", t):
            return None
        vals = []
        for m in re.finditer(r"(?:月額)?(?:補助)?(?:上限額?|限度額)?[^。\d]{0,6}(\d+(?:\.\d+)?)\s*万円", t):
            vals.append(int(float(m.group(1)) * 10000))
        for m in re.finditer(r"(?:月額)?(?:補助)?上限額?\s*([0-9,]+)\s*円", t):
            vals.append(_yen_int(m.group(1)))
        for m in re.finditer(r"月額\s*([0-9,]+)\s*円", t):
            vals.append(_yen_int(m.group(1)))
        for m in re.finditer(r"上限\s*([0-9,]+)\s*円", t):
            vals.append(_yen_int(m.group(1)))
        vals = [v for v in vals if 20000 <= v <= 150000]
        return max(vals) if vals else None
    if mode == "rent_monthly":
        # 所得月額などの閾値は除外し、家賃補助の上限・月額を優先
        if re.search(r"所得月額", t):
            m = re.search(r"(?:家賃|補助)?(?:月額)?\s*([0-9,]+)\s*円(?:を)?限度", t)
            if m:
                return _yen_int(m.group(1))
            m = re.search(r"限度\s*([0-9,]+)\s*円", t)
            if m:
                return _yen_int(m.group(1))
            return None
        m = re.search(r"月額\s*(\d+(?:\.\d+)?)\s*万円", t)
        if m:
            return int(float(m.group(1)) * 10000)
        m = re.search(r"月額\s*([0-9,]+)\s*円限度", t)
        if m:
            return _yen_int(m.group(1))
        m = re.search(r"([0-9,]+)\s*円限度", t)
        if m:
            return _yen_int(m.group(1))
        m = re.search(r"月額\s*([0-9,]+)\s*円", t)
        if m:
            return _yen_int(m.group(1))
        return None
    if mode == "aircon_cap":
        if any(k in t for k in ("児童扶養", "児童手当", "全部支給：本体")):
            return None
        m = re.search(r"上限\s*(\d+)\s*万円", t)
        if m:
            return int(m.group(1)) * 10000
        m = re.search(r"(\d+)\s*万円を上限", t)
        if m:
            return int(m.group(1)) * 10000
        m = re.search(r"上限\s*([0-9,]+)\s*円", t)
        if m:
            return _yen_int(m.group(1))
        m = re.search(r"([0-9,]+)\s*円を上限", t)
        if m:
            return _yen_int(m.group(1))
        return None
    if mode == "birth_aid":
        # 国の出産育児一時金（約50万円）や伴走型は除外し、自治体独自の助成のみ
        if any(k in t for k in (
            "産科医療補償", "国民健康保険の被保険者向け", "健康保険加入者",
            "出産・子育て応援給付", "妊婦のための支援給付", "伴走型",
        )):
            return None
        vals = []
        for m in re.finditer(r"(\d+(?:\.\d+)?)\s*万円", t):
            vals.append(int(float(m.group(1)) * 10000))
        for m in re.finditer(r"([0-9,]+)\s*円", t):
            v = _yen_int(m.group(1))
            if 30000 <= v <= 400000:
                vals.append(v)
        vals = [v for v in vals if v not in (500000, 488000)]
        return max(vals) if vals else None
    if mode == "funin_cap":
        vals = []
        for m in re.finditer(r"(?:上限|まで)\s*(\d+(?:\.\d+)?)\s*万円", t):
            vals.append(int(float(m.group(1)) * 10000))
        for m in re.finditer(r"(\d+(?:\.\d+)?)\s*万円(?:を)?上限", t):
            vals.append(int(float(m.group(1)) * 10000))
        for m in re.finditer(r"上限\s*([0-9,]+)\s*円", t):
            vals.append(_yen_int(m.group(1)))
        for m in re.finditer(r"([0-9,]+)\s*円上限", t):
            vals.append(_yen_int(m.group(1)))
        vals = [v for v in vals if 10000 <= v <= 500000]
        return max(vals) if vals else None
    if mode == "taishin_cap":
        vals = []
        for m in re.finditer(
            r"(?:耐震改修工事助成|耐震補強工事助成|耐震改修助成|耐震改修(?:費用)?補助|耐震補強工事助成)"
            r"[^。]{0,24}上限\s*(\d+(?:\.\d+)?)\s*万円",
            t,
        ):
            vals.append(int(float(m.group(1)) * 10000))
        for m in re.finditer(r"改修工事上限\s*(\d+(?:\.\d+)?)\s*万円", t):
            vals.append(int(float(m.group(1)) * 10000))
        for m in re.finditer(r"限度額\s*(\d+(?:\.\d+)?)\s*万円", t):
            vals.append(int(float(m.group(1)) * 10000))
        vals = [v for v in vals if 300000 <= v <= 5000000]
        return max(vals) if vals else None
    if mode == "loan_cap":
        # 塾代など誤分類を除外
        if any(k in t for k in ("塾", "受験", "就学", "奨学", "高額療養")):
            return None
        vals = []
        for m in re.finditer(r"(\d+(?:\.\d+)?)\s*万円まで", t):
            vals.append(int(float(m.group(1)) * 10000))
        for m in re.finditer(r"([0-9,]+)\s*円まで", t):
            vals.append(_yen_int(m.group(1)))
        for m in re.finditer(r"(?:上限|以内)\s*(\d+(?:\.\d+)?)\s*万円", t):
            vals.append(int(float(m.group(1)) * 10000))
        for m in re.finditer(r"(\d+(?:\.\d+)?)\s*万円以内", t):
            vals.append(int(float(m.group(1)) * 10000))
        vals = [v for v in vals if 30000 <= v <= 500000]
        return max(vals) if vals else None
    return None

def format_rank_yen(yen, mode):
    s = f"{yen:,}円"
    if mode in ("monthly_cap", "monthly", "rent_monthly", "hoiku_cap"):
        return "月額 " + s
    if mode in ("purchase_cap", "aircon_cap", "funin_cap", "taishin_cap", "loan_cap"):
        return "上限 " + s
    if mode in ("child_gift", "birth_gift", "birth_aid"):
        return s
    return s

def _rank_rows_from_hikaku(cid, mode, top_n=5):
    path = os.path.join(OUT, "hikaku", cid, "index.html")
    if not os.path.isfile(path):
        return []
    with open(path, encoding="utf-8") as f:
        html_t = f.read()
    rows = []
    for href, name, amt in re.findall(
            r'<tr><td class="mn"><a href="([^"]+)">([^<]+)</a></td><td>(.*?)</td>',
            html_t, re.S):
        amt_plain = re.sub(r"<[^>]+>", "", amt).strip()
        yen = extract_rank_yen(amt_plain, mode)
        if yen is None:
            continue
        rows.append((yen, name, href, amt_plain))
    uniq = {}
    for yen, name, href, amt in rows:
        cur = uniq.get(name)
        if cur is None or yen > cur[0]:
            uniq[name] = (yen, name, href, amt)
    return sorted(uniq.values(), key=lambda x: (-x[0], x[1]))[:top_n]

def amount_rank_rows(entries, mode, top_n=5):
    """entries: [(m, slug, program, amount_text, idx), ...] -> [(yen, muni_name, href, amount_text)]"""
    best = {}
    for m, slug, p, amount, idx in entries:
        if not amount:
            continue
        yen = extract_rank_yen(amount, mode)
        if yen is None:
            continue
        mid = m["id"]
        href = f"/area/tokyo/{slug}/seido/{p['id']}/"
        cur = best.get(mid)
        if cur is None or yen > cur[0]:
            best[mid] = (yen, m["municipality_name"], href, amount)
    rows = sorted(best.values(), key=lambda x: (-x[0], x[1]))
    return rows[:top_n]

def _amount_box_html(cid, title, unit, mode, color, rows):
    lis = []
    for i, (yen, name, href, _amt) in enumerate(rows, 1):
        lis.append(
            f'<li><span class="arrk">{i}</span>'
            f'<a class="armn" href="{esc(href)}">{esc(name)}</a>'
            f'<span class="aramt">{esc(format_rank_yen(yen, mode))}</span></li>'
        )
    return (
        f'<div class="arbox" style="--pc:{color}">'
        f'<h3><a href="/hikaku/{cid}/">{esc(title)}</a></h3>'
        f'<p class="arunit">{esc(unit)}</p>'
        f'<ol class="arlist">{"".join(lis)}</ol>'
        f'<p class="armore"><a href="/hikaku/{cid}/">{CHEV_R} 全市区町村の金額を比較</a></p>'
        f'</div>'
    )

def amount_rankings_html(cat_entries=None, top_n=5):
    """目的カテゴリ切替つきの金額ランキングHTML。"""
    chips = []
    panels = []
    first = True
    for ev, specs in AMOUNT_RANK_BY_EVENT:
        persona, _age, color, _ = EV_META[ev]
        boxes = []
        for cid, title, unit, mode in specs:
            if cat_entries and cid in cat_entries:
                rows = amount_rank_rows(cat_entries[cid], mode, top_n)
            else:
                rows = _rank_rows_from_hikaku(cid, mode, top_n)
            min_n = 2 if ev in ("moving", "pregnancy_birth", "retirement_unemployment") else 3
            if len(rows) < min_n:
                continue
            boxes.append(_amount_box_html(cid, title, unit, mode, color, rows))
        if len(boxes) < 2:
            continue
        on = " on" if first else ""
        pressed = "true" if first else "false"
        hidden = "" if first else " hidden"
        chips.append(
            f'<button type="button" class="mchip archip{on}" data-ar="{ev}" '
            f'style="--pc:{color}" aria-pressed="{pressed}">{esc(persona)}</button>'
        )
        panels.append(
            f'<div class="arpanel" data-ar="{ev}"{hidden}>'
            f'<div class="argrid">{"".join(boxes)}</div></div>'
        )
        first = False
    if not panels:
        return ""
    return (
        '<section class="amtrank">'
        '<h2 class="fh">支給額・助成額が高い自治体</h2>'
        '<p class="lead2">目的・年代を選ぶと、金額差が出やすい制度の上位自治体を確認できます。</p>'
        f'<div class="mchips archips" role="tablist" aria-label="金額ランキングの目的">{"".join(chips)}</div>'
        f'{"".join(panels)}'
        '<p class="note">※掲載の金額は公式情報から抽出した上限・月額の目安です。対象条件・世帯状況により異なる場合があります。'
        '申請前に必ず各制度の公式ページでご確認ください。</p>'
        '<script>(function(){'
        'var chips=[].slice.call(document.querySelectorAll(".archip"));'
        'var panels=[].slice.call(document.querySelectorAll(".arpanel"));'
        'chips.forEach(function(c){c.addEventListener("click",function(){'
        'var ar=c.getAttribute("data-ar");'
        'chips.forEach(function(x){var on=x===c;x.classList.toggle("on",on);x.setAttribute("aria-pressed",on);});'
        'panels.forEach(function(p){p.hidden=p.getAttribute("data-ar")!==ar;});'
        '});});'
        '})();</script>'
        '</section>'
    )

def classify(title, summary, benefit, target):
    text = " ".join([x or "" for x in (title, summary, benefit, target)])
    hits = []
    for cid,label,ev,inc,exc in TAXONOMY:
        if any((re.search(k,text) if ("." in k or "*" in k) else (k in text)) for k in inc):
            if not any(k in text for k in exc):
                hits.append(cid)
    return hits

# ── DB ────────────────────────────────────────────────────────────────────
con = sqlite3.connect(DB); con.row_factory = sqlite3.Row; c = con.cursor()

def esc(s): return html.escape(str(s or ""), quote=True)
def write(path, content):
    full = os.path.join(OUT, path.lstrip("/"))
    os.makedirs(os.path.dirname(full), exist_ok=True)
    with open(full, "w", encoding="utf-8") as f: f.write(content)

def clip(s, n):
    s = re.sub(r"\s+"," ", (s or "").strip())
    return s if len(s) <= n else s[:n-1] + "…"

# ── SVG横棒グラフ（量表現＝単一色相。JS不要・直接ラベルで識別）──────────────────
def svg_bars(rows, maxval=100, unit="%"):
    """rows: [(label, value, avg_or_None, note_or_'')]"""
    W=560; padL=118; padR=92; barH=16; rowH=31; top=10
    plotW=W-padL-padR
    H=top+rowH*len(rows)+6
    p=[f'<svg viewBox="0 0 {W} {H}" class="chart" role="img" preserveAspectRatio="xMinYMin meet">']
    for i,(label,val,avg,note) in enumerate(rows):
        y=top+rowH*i; cy=y+barH/2
        bw=plotW*(min(val,maxval)/maxval if maxval else 0)
        p.append(f'<text x="{padL-8}" y="{cy:.0f}" class="c-lbl" text-anchor="end" dominant-baseline="central">{esc(label)}</text>')
        p.append(f'<rect x="{padL}" y="{y}" width="{plotW}" height="{barH}" rx="4" class="c-track"/>')
        p.append(f'<rect x="{padL}" y="{y}" width="{max(bw,3):.1f}" height="{barH}" rx="4" class="c-bar"/>')
        if avg is not None:
            ax=padL+plotW*(min(avg,maxval)/maxval if maxval else 0)
            p.append(f'<line x1="{ax:.1f}" y1="{y-3}" x2="{ax:.1f}" y2="{y+barH+3}" class="c-avg"><title>都平均 {avg:.0f}{unit}</title></line>')
        vlab=f'{val:.0f}{unit}'+(f' · {esc(note)}' if note else '')
        p.append(f'<text x="{padL+bw+6:.1f}" y="{cy:.0f}" class="c-val" dominant-baseline="central">{vlab}</text>')
    p.append('</svg>')
    return ''.join(p)

# ── ページ骨格 ──────────────────────────────────────────────────────────────
def page(*, path, title, description, canonical, jsonld=None, robots="index,follow",
         breadcrumb=None, body=""):
    ld = ""
    blocks = list(jsonld or [])
    if breadcrumb:
        blocks.insert(0, {
          "@context":"https://schema.org","@type":"BreadcrumbList",
          "itemListElement":[{"@type":"ListItem","position":i+1,"name":n,
             **({"item":BASE_URL+u} if u else {})} for i,(n,u) in enumerate(breadcrumb)]})
    for b in blocks:
        ld += '<script type="application/ld+json">%s</script>\n' % json.dumps(b, ensure_ascii=False)
    crumbs = ""
    if breadcrumb:
        parts = []
        for n,u in breadcrumb:
            parts.append(f'<a href="{u}">{esc(n)}</a>' if u else f'<span>{esc(n)}</span>')
        crumbs = '<nav class="crumbs" aria-label="パンくず">'+ " › ".join(parts) +'</nav>'
    canon = BASE_URL + canonical
    ga_tag = ""
    if GA_MEASUREMENT_ID:
        ga_id = esc(GA_MEASUREMENT_ID)
        ga_tag = (
            f'<!-- Google tag (gtag.js) -->\n'
            f'<script async src="https://www.googletagmanager.com/gtag/js?id={ga_id}"></script>\n'
            f'<script>\n'
            f'window.dataLayer=window.dataLayer||[];\n'
            f'function gtag(){{dataLayer.push(arguments);}}\n'
            f"gtag('js',new Date());\n"
            f"gtag('config','{ga_id}');\n"
            f'</script>\n'
        )
    doc = f"""<!doctype html>
<html lang="ja">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{esc(title)}</title>
<meta name="description" content="{esc(description)}">
<meta name="robots" content="{robots},max-image-preview:large,max-snippet:-1,max-video-preview:-1">
<link rel="canonical" href="{esc(canon)}">
<meta property="og:type" content="website">
<meta property="og:site_name" content="{esc(SITE_NAME)}">
<meta property="og:title" content="{esc(title)}">
<meta property="og:description" content="{esc(description)}">
<meta property="og:url" content="{esc(canon)}">
<meta property="og:locale" content="ja_JP">
<meta name="twitter:card" content="summary_large_image">
<meta property="og:image" content="{esc(BASE_URL)}/assets/og.png">
<meta name="twitter:image" content="{esc(BASE_URL)}/assets/og.png">
<link rel="icon" href="/assets/favicon.svg" type="image/svg+xml">
<link rel="icon" href="/favicon.ico" sizes="any">
<link rel="apple-touch-icon" href="/assets/apple-touch-icon.png" sizes="180x180">
<link rel="manifest" href="/assets/site.webmanifest">
<meta name="theme-color" content="#1558d6">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Noto+Sans+JP:wght@400;500;700;800&display=swap">
<link rel="stylesheet" href="/assets/style.css">
{ga_tag}{ld}</head>
<body id="top">
<header class="site"><div class="hbar">
<a class="brand" href="/"><img class="brand-mark" src="/assets/logo-mark.svg" width="28" height="28" alt="" decoding="async">{esc(SITE_SHORT)}</a>
<nav class="gnav" aria-label="メインナビゲーション">
<a href="/find/">目的で探す</a>
<a href="/hikaku/">制度を比較</a>
<a href="/#area">自治体一覧</a>
</nav></div></header>
<main>
{crumbs}
{body}
</main>
<footer class="site">
<p class="totop"><a href="#top">{CHEV_U} ページの先頭へ</a></p>
<nav class="fnav" aria-label="サイト情報">
<a href="/">トップ</a>・<a href="/find/">目的・年代から探す</a>・<a href="/hikaku/">制度を比較する</a>・<a href="/about/">運営者情報</a>・<a href="/update-policy/">情報の更新方針</a>・<a href="/disclaimer/">免責事項</a>・<a href="/privacy/">プライバシーポリシー</a>
</nav>
<p>本サイトは各自治体・公的機関の公表情報をもとに整理した比較・案内サービスです。
最新かつ正確な内容は必ず各制度の公式ページでご確認ください。</p>
<p class="copy">© {ESTABLISHED} {esc(SITE_SHORT)}（東京都62自治体・出典付き / 最終確認日を明記）</p>
</footer>
</body></html>"""
    write(path, doc)

# ── データ取得 ──────────────────────────────────────────────────────────────
munis = c.execute("SELECT * FROM municipalities WHERE is_active=1 ORDER BY id").fetchall()
def muni_slug(m): return SLUGS.get(m["municipality_name"])

def programs_of(mid):
    return c.execute("""
      SELECT p.* FROM programs p
      JOIN program_municipalities pm ON pm.program_id=p.id
      WHERE pm.municipality_id=? AND p.status='active'
      ORDER BY p.id""", (mid,)).fetchall()

def facts_of(pid):
    rows = c.execute("SELECT fact_type,value,evidence_url,confidence_score FROM program_facts WHERE program_id=? ORDER BY id",(pid,)).fetchall()
    seen=set(); out=[]
    for r in rows:
        lbl,order = fact_label(r["fact_type"])
        key=(lbl, (r["value"] or "")[:20])
        if key in seen: continue
        seen.add(key)
        out.append((order,lbl,r["value"],r["evidence_url"],r["confidence_score"]))
    out.sort(key=lambda x:x[0])
    return out

_ev_cache={}
def events_of(pid):
    if pid in _ev_cache: return _ev_cache[pid]
    rows=c.execute("""SELECT le.slug,le.name FROM program_life_events ple
       JOIN life_events le ON le.id=ple.life_event_id WHERE ple.program_id=? ORDER BY ple.relevance_score DESC""",(pid,)).fetchall()
    _ev_cache[pid]=rows
    return rows

def gate_index(p, facts):
    if p["reliability_status"] == "needs_review": return False
    conf = [f[4] for f in facts if f[4] is not None]
    if not conf: return False
    return (sum(conf)/len(conf)) >= GATE_MIN_CONFIDENCE

# ── 自治体スコア（制度掲載数など。発見導線の並べ替えに使用）──────────────────
def compute_scores():
    ev_total={}
    for cid,label,ev,inc,exc in TAXONOMY:
        ev_total[ev]=ev_total.get(ev,0)+1
    muni_cat={}; muni_ev_prog={}
    for m in munis:
        for p in programs_of(m["id"]):
            cats=classify(p["title"],p["summary"],p["benefit_description"],p["target_description"])
            if not cats: continue
            muni_cat.setdefault(m["id"],set()).update(cats)
            evs={CAT_BY_ID[cid][2] for cid in cats if cid in CAT_BY_ID}
            d=muni_ev_prog.setdefault(m["id"],{})
            for ev in evs: d[ev]=d.get(ev,0)+1
    score={}
    for m in munis:
        mid=m["id"]; s={}
        for ev in EVENTS:
            covered=len([cid for cid in muni_cat.get(mid,()) if CAT_BY_ID.get(cid,(None,None,None))[2]==ev])
            total=ev_total.get(ev,0) or 1
            s[ev]={"cov":covered/total*100,"covered":covered,"total":total,
                   "prog":muni_ev_prog.get(mid,{}).get(ev,0)}
        score[mid]=s
    avg={ev: sum(score[m["id"]][ev]["cov"] for m in munis)/len(munis) for ev in EVENTS}
    return score, avg

# ── 制度詳細ページ ──────────────────────────────────────────────────────────
sitemap_urls = []  # (loc, priority)
PT_JA = {"allowance":"手当","subsidy":"助成金","benefit":"給付","medical_subsidy":"医療費助成",
 "service":"サービス","reduction":"軽減・免除","housing_subsidy":"住まい助成","procedure":"手続き",
 "loan":"貸付","education_subsidy":"教育助成","housing_support":"住まい支援","consultation":"相談",
 "fee_reduction":"料金軽減","tax_reduction":"税軽減","cash_benefit":"現金給付","housing":"住まい",
 "transport_subsidy":"交通助成"}

def amount_of(facts):
    for order,lbl,val,ev,cf in facts:
        if lbl in ("支給額・助成額",) and val: return val
    return None

def related_programs(m, slug, p, progs):
    pe = {e["slug"] for e in events_of(p["id"])}
    if not pe or not progs: return ""
    sibs=[q for q in progs if q["id"]!=p["id"] and (pe & {e["slug"] for e in events_of(q["id"])})]
    sibs=sibs[:6]
    if not sibs: return ""
    lis="".join(f'<li><a href="/area/tokyo/{slug}/seido/{q["id"]}/">{esc(q["title"])}</a>'
                f'<span class="pt">{esc(PT_JA.get(q["program_type"],""))}</span></li>' for q in sibs)
    return (f'<section class="related"><h2>{esc(m["municipality_name"])}の関連する制度</h2>'
            f'<ul class="proglist">{lis}</ul></section>')

def build_program(m, slug, p, cats, progs=None):
    facts = facts_of(p["id"])
    idx = gate_index(p, facts)
    robots = "index,follow" if idx else "noindex,follow"
    mn = m["municipality_name"]; title = p["title"]
    url = f"/area/tokyo/{slug}/seido/{p['id']}/"
    ptype = PT_JA.get(p["program_type"],"制度")
    h1 = f"{mn}の{title}"
    page_title = f"{mn}の{title}｜対象・金額・申請方法【{p['last_verified_at'] or ''}時点】"
    desc = clip(p["plain_summary"] or p["summary"] or f"{mn}の{title}（{ptype}）の対象者・支給額・申請方法・期限を、出典付きでわかりやすくまとめています。", 118)

    # 本文（facts定義リスト）
    dl = []
    faq = []
    for order,lbl,val,ev,cf in facts:
        if not val: continue
        src = f' <a class="src" href="{esc(ev)}" target="_blank" rel="nofollow noopener">出典</a>' if ev else ""
        dl.append(f'<div class="fact"><dt>{esc(lbl)}</dt><dd>{esc(val)}{src}</dd></div>')
        q = {"対象者":"誰が対象ですか？","支給額・助成額":"いくらもらえますか？","内容・給付":"どんな支援が受けられますか？",
             "申請方法":"どうやって申請しますか？","申請期限":"申請期限はいつですか？","支給時期":"いつ支給されますか？",
             "条件":"条件はありますか？"}.get(lbl)
        if q and len(faq) < 6:
            faq.append((q, clip(val,300)))
    facts_html = f'<dl class="facts">{"".join(dl)}</dl>' if dl else "<p>詳細は出典の公式ページをご確認ください。</p>"

    summary_html = f'<p class="lead">{esc(p["plain_summary"] or p["summary"] or "")}</p>' if (p["plain_summary"] or p["summary"]) else ""
    official = p["official_url"] or (m["official_site_url"] or "")
    src_block = f'<p class="official">{CHEV_R} 公式ページ: <a href="{esc(official)}" target="_blank" rel="nofollow noopener">{esc(official)}</a></p>' if official else ""
    ev_notice = "" if idx else '<p class="notice">※この情報は自動収集した暫定データで、内容確認中です。必ず公式ページでご確認ください。</p>'

    body = f"""
<article class="program">
<span class="badge">{esc(ptype)}</span>
<h1>{esc(h1)}</h1>
{summary_html}
<p class="meta">最終確認日: <time>{esc(p['last_verified_at'] or '—')}</time> ／ 対象自治体: <a href="/area/tokyo/{slug}/">{esc(mn)}</a></p>
{ev_notice}
<h2>制度の内容</h2>
{facts_html}
{src_block}
<h2>この制度について</h2>
<p>{esc(mn)}に住む方が対象の{esc(title)}（{esc(ptype)}）です。同じ制度を東京都の他の自治体と比べたい場合は、
<a href="/area/tokyo/{slug}/">{esc(mn)}の制度一覧</a>もあわせてご覧ください。</p>
{compare_links(cats)}
{related_programs(m, slug, p, progs)}
</article>"""

    # JSON-LD
    gov = {"@context":"https://schema.org","@type":"GovernmentService","name":title,
      "serviceType":ptype,"description":clip(p["plain_summary"] or p["summary"] or title,300),
      "areaServed":{"@type":"AdministrativeArea","name":mn},
      "provider":{"@type":"GovernmentOrganization","name":mn,
                  **({"url":m["official_site_url"]} if m["official_site_url"] else {})}}
    if official: gov["url"] = official
    blocks=[gov]
    if faq:
        blocks.append({"@context":"https://schema.org","@type":"FAQPage",
          "mainEntity":[{"@type":"Question","name":q,
            "acceptedAnswer":{"@type":"Answer","text":a}} for q,a in faq]})
    bc = [("トップ","/"),(f"{mn}",f"/area/tokyo/{slug}/"),(title,None)]
    page(path=url+"index.html", title=page_title, description=desc, canonical=url,
         jsonld=blocks, robots=robots, breadcrumb=bc, body=body)
    if idx: sitemap_urls.append((url, "0.8", p["last_verified_at"]))
    return idx

def compare_links(cats):
    ls=[c for c in cats if c in CAT_BY_ID]
    if not ls: return ""
    a="".join(f'<li><a href="/hikaku/{cid}/">東京都で「{esc(CAT_BY_ID[cid][1])}」を自治体比較 {CHEV_R}</a></li>' for cid in ls)
    return f'<div class="cmpbox"><strong>東京都の他自治体と比べる</strong><ul>{a}</ul></div>'

# ── 比較ページ（被リンク磁石）────────────────────────────────────────────────
def build_compare(cid, entries, counts=None):
    """entries: [(m, slug, program, amount, idx), ...]  同一カテゴリの全自治体分"""
    counts = counts or {}
    label, ev = CAT_BY_ID[cid][1], CAT_BY_ID[cid][2]
    ev_name = EVENTS.get(ev,("",""))[0]
    url = f"/hikaku/{cid}/"
    # 同一自治体に複数該当制度がある場合は1行に集約（金額記載あり→index対象を優先）
    best={}
    for e in entries:
        mid=e[0]["id"]
        cur=best.get(mid)
        if cur is None: best[mid]=e; continue
        def rank(x): return (1 if x[3] else 0, 1 if x[4] else 0)  # amountあり, index対象
        if rank(e)>rank(cur): best[mid]=e
    # 表示順: 金額の記載がある自治体を上に → 同条件はDB id順（区→市→町村）
    entries = sorted(best.values(), key=lambda e: (0 if e[3] else 1, e[0]["id"]))
    rows=[]
    for m, slug, p, amount, idx in entries:
        mn=m["municipality_name"]
        amt = esc(clip(amount,80)) if amount else '<span class="na">記載を確認中</span>'
        rows.append(f'<tr><td class="mn"><a href="/area/tokyo/{slug}/seido/{p["id"]}/">{esc(mn)}</a></td>'
                    f'<td>{amt}</td><td class="dt">{esc(p["last_verified_at"] or "")}</td></tr>')
    have=len(entries)
    n_amt=sum(1 for e in entries if e[3])
    missing=[m["municipality_name"] for m in munis if m["id"] not in {e[0]["id"] for e in entries}]
    miss_html=""
    if missing:
        miss_html=(f'<p class="miss"><strong>この制度が未確認の自治体（{len(missing)}）：</strong>'
                   f'{esc("、".join(missing))}<br><span class="na">※制度が無い場合と、当サイトで未収集の場合があります。</span></p>')

    # 同じライフイベントの他カテゴリ比較への内部リンク
    sibs=[(c[0],c[1]) for c in TAXONOMY if c[2]==ev and c[0]!=cid and counts.get(c[0],0)>=3]
    rel_html=""
    if sibs:
        lis="".join(f'<li><a href="/hikaku/{sid}/">東京都の「{esc(sl)}」を比較 {CHEV_R}</a></li>' for sid,sl in sibs[:8])
        rel_html=f'<div class="cmpbox"><strong>同じ「{esc(ev_name)}」で自治体を比べる</strong><ul>{lis}</ul></div>'

    # FAQ（可視 + 構造化データ）
    faq=[(f"東京都で{label}があるのはどの自治体ですか？",
          f"当サイトでは東京都{have}自治体で「{label}」に該当する制度を確認しています。各自治体の内容・金額・最終確認日はこのページの一覧で比較できます。"),
         (f"{label}の金額は自治体によって違いますか？",
          f"はい。同じ{label}でも自治体ごとに金額・対象・条件が異なります。金額は制度改定で変わるため、申請前に各自治体の公式ページ（出典リンク）で最新情報をご確認ください。")]
    faq_html="".join(f'<div class="fact"><dt>{esc(q)}</dt><dd>{esc(a)}</dd></div>' for q,a in faq)

    title=f"【{ev_name}】{label} 東京都62自治体を比較｜金額・対象一覧"
    desc=clip(f"東京都の{label}を{have}自治体分まとめて比較。自治体ごとの金額・対象・最終確認日を一覧化。どの区市町村が手厚いかを出典付きで確認できます。",118)
    amt_note=(f"うち{n_amt}自治体は具体的な支給額・助成額を掲載しています。金額の記載がある自治体を上に表示しています。"
              if n_amt else "")
    body=f"""
<span class="badge">{esc(ev_name)}</span>
<h1>東京都の{esc(label)}を自治体で比較</h1>
<p class="lead">東京都62自治体の「{esc(label)}」を横断比較しています（掲載 {have}自治体・各制度に出典/最終確認日つき）。{esc(amt_note)}</p>
<div class="tablewrap"><table class="cmp">
<thead><tr><th>自治体</th><th>支給額・助成額</th><th>確認日</th></tr></thead>
<tbody>{''.join(rows)}</tbody></table></div>
{miss_html}
<p class="note">※金額は制度改定で変わります。申請前に必ず各自治体の公式ページ（各自治体ページ内の出典リンク）でご確認ください。</p>
{rel_html}
<h2>よくある質問</h2>
<dl class="facts">{faq_html}</dl>
<p><a href="/hikaku/">{CHEV_L} 制度カテゴリ比較の一覧にもどる</a></p>"""
    il={"@context":"https://schema.org","@type":"ItemList","name":f"{label} 自治体比較",
        "itemListElement":[{"@type":"ListItem","position":i+1,"name":e[0]["municipality_name"],
          "url":f"{BASE_URL}/area/tokyo/{e[1]}/seido/{e[2]['id']}/"} for i,e in enumerate(entries)]}
    faq_ld={"@context":"https://schema.org","@type":"FAQPage",
        "mainEntity":[{"@type":"Question","name":q,"acceptedAnswer":{"@type":"Answer","text":a}} for q,a in faq]}
    bc=[("トップ","/"),("制度を比較する","/hikaku/"),(label,None)]
    robots="index,follow" if have>=3 else "noindex,follow"
    page(path=url+"index.html",title=title,description=desc,canonical=url,
         jsonld=[il,faq_ld],robots=robots,breadcrumb=bc,body=body)
    dates=[e[2]["last_verified_at"] for e in entries if e[2]["last_verified_at"]]
    if have>=3: sitemap_urls.append((url,"0.9", max(dates) if dates else None))
    return have

def build_compare_index(cat_counts):
    url="/hikaku/"
    groups={}
    for cid,label,ev,_,_ in TAXONOMY:
        groups.setdefault(ev,[]).append((cid,label,cat_counts.get(cid,0)))
    secs=[]
    for ev_slug,(ev_name,_) in EVENTS.items():
        items=groups.get(ev_slug,[])
        lis="".join(f'<li><a href="/hikaku/{cid}/">{esc(label)}</a>'
                    f'<span class="cnt2">{n}自治体</span></li>' for cid,label,n in items if n>=3)
        if lis: secs.append(f'<section><h2>{esc(ev_name)}</h2><ul class="cmplist">{lis}</ul></section>')
    body=f"""
<h1>東京都の給付・手当・助成を「制度ごと」に自治体比較</h1>
<p class="lead">同じ制度でも、金額や対象は自治体でこんなに違います。制度カテゴリを選ぶと、東京都62自治体の内容を横断比較できます。</p>
{''.join(secs)}"""
    page(path=url+"index.html",title="東京都 給付・手当・助成の自治体比較一覧｜制度カテゴリ別",
         description="児童手当・産後ケア・高齢者紙おむつ・家賃補助など、東京都62自治体の制度を制度カテゴリごとに横断比較。金額・対象の違いが一目でわかります。",
         canonical=url,breadcrumb=[("トップ","/"),("制度を比較する",None)],body=body)
    sitemap_urls.append((url,"0.9"))

# ── 目的・年代の発見導線＋ランキング（差別化の核）──────────────────────────────
def rel_rankings(cur):
    ls="".join(f'<li><a href="/ranking/{ev}/">{esc(EVENTS[ev][0])}の制度がある自治体 {CHEV_R}</a></li>'
               for ev in EVENTS if ev!=cur)
    return f'<div class="cmpbox"><strong>ほかの目的でも探す</strong><ul>{ls}</ul></div>'

def build_ranking(ev, score, avg=None):
    persona,age,color,_ = EV_META[ev]
    ev_name = EVENTS[ev][0]
    url=f"/ranking/{ev}/"
    ranked=sorted(munis, key=lambda m:(-score[m["id"]][ev]["prog"], m["id"]))
    top=ranked[:15]
    max_prog=max((score[m["id"]][ev]["prog"] for m in top), default=1) or 1
    rows=[(m["municipality_name"], score[m["id"]][ev]["prog"], None, "") for m in top]
    chart=svg_bars(rows, max_prog, "制度")
    trs=[]
    for rank,m in enumerate(ranked,1):
        s=score[m["id"]][ev]; slug=muni_slug(m)
        cls=' class="top3"' if rank<=3 else ''
        trs.append(f'<tr{cls}><td class="rk">{rank}</td>'
                   f'<td class="mn"><a href="/area/tokyo/{slug}/{ev}/">{esc(m["municipality_name"])}</a></td>'
                   f'<td class="dt">{s["prog"]}制度</td></tr>')
    title=f"{ev_name}の制度がある東京都の自治体｜掲載数でみる"
    desc=clip(f"{persona}向けに、{ev_name}関連の制度掲載数が多い東京都の自治体から順に確認できます。各自治体の制度一覧へ進めます。",118)
    body=f"""
<span class="badge" style="--pc:{color}">{esc(age)}</span>
<h1>{esc(ev_name)}の制度がある東京都の自治体</h1>
<p class="lead">「{esc(persona)}」向けに、{esc(ev_name)}関連の制度を掲載している件数が多い自治体から順に並べています。</p>
<div class="chartcard" style="--pc:{color}">{chart}
<p class="cap">上位15自治体の掲載制度数</p></div>
<div class="tablewrap"><table class="cmp rank">
<thead><tr><th>順位</th><th>自治体</th><th>制度数</th></tr></thead>
<tbody>{''.join(trs)}</tbody></table></div>
<p class="notice">掲載件数は当サイトの収録状況に基づく目安です。金額の多寡や実際の手厚さを示すものではありません。詳細・申請可否は各自治体の公式ページでご確認ください。</p>
{rel_rankings(ev)}
<p><a href="/find/">{CHEV_L} 目的・年代から探す にもどる</a></p>"""
    il={"@context":"https://schema.org","@type":"ItemList","name":f"{ev_name}の制度がある東京都の自治体",
        "itemListElement":[{"@type":"ListItem","position":i+1,"name":m["municipality_name"],
          "url":f"{BASE_URL}/area/tokyo/{muni_slug(m)}/{ev}/"} for i,m in enumerate(ranked[:20])]}
    bc=[("トップ","/"),("目的・年代から探す","/find/"),(f"{ev_name}の自治体",None)]
    page(path=url+"index.html",title=title,description=desc,canonical=url,
         jsonld=[il],breadcrumb=bc,body=body)
    sitemap_urls.append((url,"0.8"))

def build_find_hub(score):
    def top1(ev):
        best=max(munis,key=lambda m:(score[m["id"]][ev]["prog"], -m["id"]))
        return best["municipality_name"], score[best["id"]][ev]["prog"]
    cards=[]
    for ev,(persona,age,color,_) in EV_META.items():
        ev_name=EVENTS[ev][0]; tn,tp=top1(ev)
        cards.append(f'<a class="pcard" href="/ranking/{ev}/" style="--pc:{color}">'
            f'<span class="pic">{icon_svg(ev)}</span>'
            f'<span class="ptxt"><strong>{esc(persona)}</strong>'
            f'<span class="page">{esc(age)}</span>'
            f'<span class="pdesc">{esc(ev_name)}の制度がある自治体をみる</span>'
            f'<span class="ptop">掲載数が多い例：{esc(tn)}（{tp}制度）</span></span>'
            f'<span class="parrow" aria-hidden="true">{CHEV_R}</span></a>')
    body=f"""
<h1>目的・年代から制度がある地域を探す</h1>
<p class="lead">ライフステージや目的を選ぶと、その分野の制度を掲載している東京都の自治体を件数順に確認できます。
「引っ越し先選び」や「いま住む街で使える制度の確認」にお使いください。</p>
<div class="pgrid">{''.join(cards)}</div>
<p class="note">※掲載件数は当サイトの収録状況に基づく目安です。詳細・最新情報は各自治体の公式ページでご確認ください。</p>
<p><a href="/hikaku/">制度カテゴリごとの自治体比較を見る {CHEV_R}</a></p>"""
    page(path="/find/index.html",title="目的・年代から探す｜東京都の制度がある自治体",
         description="子育て・シニア・引っ越し・出産・退職など、目的や年代から、関連制度を掲載している東京都の自治体を見つけられます。",
         canonical="/find/",breadcrumb=[("トップ","/"),("目的・年代から探す",None)],body=body)
    sitemap_urls.append(("/find/","0.9"))

# ── 自治体 × ライフイベント ─────────────────────────────────────────────────
def build_muni_event(m, slug, ev_slug, ev_name, ev_intro, progs):
    mn = m["municipality_name"]
    url = f"/area/tokyo/{slug}/{ev_slug}/"
    items = [p for p in progs if any(e["slug"]==ev_slug for e in events_of(p["id"]))]
    lis = []
    for p in items:
        lis.append(f'<li><a href="/area/tokyo/{slug}/seido/{p["id"]}/">{esc(p["title"])}</a>'
                   f'<span class="pt">{esc(PT_JA.get(p["program_type"],""))}</span></li>')
    listing = f'<ul class="proglist">{"".join(lis)}</ul>' if lis else "<p>該当する制度は現在準備中です。</p>"
    other_lis="".join(f'<li><a href="/area/tokyo/{slug}/{s}/">{esc(mn)}の{esc(EVENTS[s][0])}の制度 {CHEV_R}</a></li>'
                      for s in EVENTS if s!=ev_slug)
    relbox=(f'<div class="cmpbox" style="--pc:{EV_META[ev_slug][2]}"><strong>関連して探す</strong><ul>'
            f'<li><a href="/ranking/{ev_slug}/">{esc(ev_name)}の制度がある自治体をみる {CHEV_R}</a></li>'
            f'{other_lis}</ul></div>')
    title = f"{mn}で{ev_name}のときに使える制度・手当・助成【一覧】"
    desc = clip(f"{mn}で{ev_name}のときに受けられる給付金・手当・助成制度を一覧でまとめました。{ev_intro}", 118)
    body = f"""
<span class="badge" style="--pc:{EV_META[ev_slug][2]}">{esc(ev_name)}</span>
<h1>{esc(mn)}の{esc(ev_name)}で使える制度</h1>
<p class="lead">{esc(ev_intro)}</p>
<p class="meta">{esc(mn)}・{esc(ev_name)}関連の制度 {len(items)}件</p>
{listing}
{relbox}
<p><a href="/area/tokyo/{slug}/">{CHEV_L} {esc(mn)}の制度一覧にもどる</a></p>"""
    il = {"@context":"https://schema.org","@type":"ItemList","itemListElement":[
        {"@type":"ListItem","position":i+1,"name":p["title"],
         "url":f"{BASE_URL}/area/tokyo/{slug}/seido/{p['id']}/"} for i,p in enumerate(items)]}
    bc=[("トップ","/"),(mn,f"/area/tokyo/{slug}/"),(ev_name,None)]
    robots = "index,follow" if items else "noindex,follow"
    page(path=url+"index.html", title=title, description=desc, canonical=url,
         jsonld=[il], robots=robots, breadcrumb=bc, body=body)
    if items: sitemap_urls.append((url,"0.6"))

# ── 自治体ハブ ──────────────────────────────────────────────────────────────
def build_muni(m, slug, score, avg):
    mn = m["municipality_name"]; url = f"/area/tokyo/{slug}/"
    progs = programs_of(m["id"])
    # ライフイベント別セクション
    sections=[]
    counts={}
    for ev_slug,(ev_name,ev_intro) in EVENTS.items():
        items=[p for p in progs if any(e["slug"]==ev_slug for e in events_of(p["id"]))]
        counts[ev_slug]=len(items)
        if not items: continue
        lis="".join(f'<li><a href="/area/tokyo/{slug}/seido/{p["id"]}/">{esc(p["title"])}</a></li>' for p in items[:8])
        color=EV_META[ev_slug][2]
        more = f'<a class="more" href="/area/tokyo/{slug}/{ev_slug}/">{ev_name}の制度をすべて見る（{len(items)}件）{CHEV_R}</a>' if items else ""
        sections.append(
            f'<section class="ev" style="--pc:{color}">'
            f'<h2><span class="evh"><span class="evi">{icon_svg(ev_slug)}</span>'
            f'<a href="/area/tokyo/{slug}/{ev_slug}/">{esc(ev_name)}</a></span>'
            f'<span class="cnt">{len(items)}</span></h2>'
            f'<ul class="proglist">{lis}</ul>{more}'
            f'<p class="evlinks"><a href="/ranking/{ev_slug}/">{esc(ev_name)}の制度がある自治体をみる {CHEV_R}</a></p>'
            f'</section>')
    mid=m["id"]
    # ほかの市区町村（種別を問わず五十音順の近隣）を対等に回遊
    _tj={"ward":"区","city":"市","town":"町","village":"村"}
    _ordered=[x for x in sorted(munis, key=lambda z: YOMI.get(z["municipality_name"], z["municipality_name"])) if muni_slug(x)]
    _n=len(_ordered)
    _idx=next((i for i,x in enumerate(_ordered) if x["id"]==mid), None)
    others_html=""
    if _idx is not None and _n>1:
        lo=max(0,_idx-6); hi=min(_n,_idx+7)
        if hi-lo<13:
            if lo==0: hi=min(_n,13)
            else: lo=max(0,_n-13)
        near=[_ordered[i] for i in range(lo,hi) if i!=_idx]
        chips="".join(f'<a href="/area/tokyo/{muni_slug(x)}/"><em class="mt">{_tj.get(x["municipality_type"],"")}</em>{esc(x["municipality_name"])}</a>' for x in near)
        others_html=(f'<section class="others"><h2>ほかの市区町村を見る</h2>'
                     f'<div class="ostrip">{chips}</div>'
                     f'<p class="more"><a href="/#area">{CHEV_R} 東京都62市区町村の一覧から探す</a></p></section>')
    title = f"{mn}で受けられる給付・手当・助成 一覧｜対象・金額まとめ"
    desc = clip(f"{mn}で受けられる給付金・手当・助成・支援制度を{len(progs)}件、ライフイベント別に出典付きでまとめました。妊娠出産・子育て・引っ越し・退職失業・高齢介護の制度が一目でわかります。",118)
    try:
        _build_dir = os.path.dirname(os.path.abspath(__file__))
        if _build_dir not in sys.path:
            sys.path.insert(0, _build_dir)
        from livability_html import livability_section_html
        live_sec = livability_section_html(slug)
    except Exception:
        live_sec = ""
    body = f"""
<h1>{esc(mn)}で受けられる給付・手当・助成 一覧</h1>
<p class="lead">{esc(mn)}にお住まいの方が使える制度を、ライフイベント別にまとめました（全{len(progs)}件・出典/最終確認日つき）。</p>
{live_sec}
{''.join(sections)}
{others_html}
"""
    bc=[("トップ","/"),(mn,None)]
    page(path=url+"index.html", title=title, description=desc, canonical=url, breadcrumb=bc, body=body)
    sitemap_urls.append((url,"0.7"))
    return progs, counts

# ── 運営者エンティティ（E-E-A-T：発行元を明確化）────────────────────────────
def site_graph():
    org = {"@type":"Organization","@id":BASE_URL+"/#org","name":SITE_SHORT,
           "url":BASE_URL+"/",
           "logo":BASE_URL+"/assets/logo-mark.svg",
           "description":"東京都62自治体の給付金・手当・助成制度を、公式情報の出典と最終確認日つきで横断比較する情報サービス。"}
    if "【" not in CONTACT_EMAIL:
        org["contactPoint"] = {"@type":"ContactPoint","email":CONTACT_EMAIL,
                               "contactType":"customer support","areaServed":"JP","availableLanguage":"ja"}
    web = {"@type":"WebSite","@id":BASE_URL+"/#website","url":BASE_URL+"/",
           "name":SITE_NAME,"inLanguage":"ja","publisher":{"@id":BASE_URL+"/#org"}}
    return {"@context":"https://schema.org","@graph":[org, web]}

# ── 静的ページ（運営者情報・更新方針・免責・プライバシー：YMYLの信頼性ページ）──────
def build_static_pages():
    def wrap(inner):
        return ('<article class="doc">'+inner+
                f'<p class="backtop"><a href="/">{CHEV_L} トップにもどる</a></p></article>')

    # 運営者名・連絡先が未設定（【要記入】のまま）でも体裁が崩れないよう分岐
    has_op = "【" not in OPERATOR_NAME
    has_ct = "【" not in CONTACT_EMAIL
    contact_link = f'<a href="mailto:{esc(CONTACT_EMAIL)}">{esc(CONTACT_EMAIL)}</a>' if has_ct else ""
    report_html = (f'<p>内容に誤りや古い情報を見つけられた場合は、{contact_link} までご連絡ください。'
                   '確認のうえ、可能な範囲で速やかに反映します。</p>' if has_ct else
                   '<p>内容の誤り・更新のご指摘を受け付ける窓口は準備中です。準備が整い次第、こちらでご案内します。</p>')
    inquiry_html = (f'<p>本ポリシーに関するお問い合わせは {contact_link} までお願いします。</p>' if has_ct else
                    '<p>お問い合わせ窓口は準備中です。</p>')
    op_row = f'<div class="fact"><dt>運営者</dt><dd>{esc(OPERATOR_NAME)}</dd></div>' if has_op else ''
    ct_row = f'<div class="fact"><dt>連絡先</dt><dd>{contact_link}</dd></div>' if has_ct else ''
    op_note = ('' if has_op else
               '<p>本サイトは、各自治体・公的機関の公表情報をもとに個人で運営している情報サイトです。'
               '運営者の詳細情報は準備中です。</p>')

    # 運営者情報
    about = wrap(f"""
<h1>運営者情報</h1>
<p class="lead">「{esc(SITE_SHORT)}」は、東京都62自治体の給付金・手当・助成・減免などの制度を、
公式情報をもとに整理し、自治体をまたいで比較できるようにした情報サービスです。</p>
<h2>運営者</h2>
<dl class="facts">
<div class="fact"><dt>サイト名</dt><dd>{esc(SITE_NAME)}</dd></div>
{op_row}
{ct_row}
<div class="fact"><dt>公開開始</dt><dd>{esc(ESTABLISHED)}年</dd></div>
</dl>
{op_note}
<h2>サイトの目的</h2>
<p>「自分の住む街・引っ越し先で、どんな公的支援が受けられるのか」を、
自治体ごとにバラバラな情報を横断して比較できるようにすることを目的としています。
妊娠・出産、子育て、引っ越し、退職・失業、高齢・介護といったライフイベント別に、
受けられる制度を出典つきで整理しています。</p>
<h2>情報の作り方</h2>
<p>掲載内容は、各自治体・公的機関が公表している情報を根拠に整理しています。
制度ごとに出典URLと最終確認日を明記し、確認が不十分なページは検索エンジンにインデックスさせない
品質基準（未検証ページの非公開）を設けています。詳しくは
<a href="/update-policy/">情報の更新方針</a>をご覧ください。</p>
<h2>ご注意</h2>
<p>本サイトは公的機関ではなく、公式の申請窓口でもありません。実際の金額・対象・期限・申請方法は
制度改定などで変わることがあります。申請前に必ず各制度の公式ページでご確認ください
（<a href="/disclaimer/">免責事項</a>）。</p>
""")
    page(path="/about/index.html", title=f"運営者情報｜{SITE_NAME}",
         description=f"{SITE_SHORT}の運営者情報・サイトの目的・情報の作り方について。東京都62自治体の給付・手当・助成を出典つきで比較する情報サービスです。",
         canonical="/about/", breadcrumb=[("トップ","/"),("運営者情報",None)], body=about)
    sitemap_urls.append(("/about/","0.3"))

    # 情報の更新方針
    policy = wrap(f"""
<h1>情報の更新方針・編集方針</h1>
<p class="lead">「{esc(SITE_SHORT)}」の掲載情報を、どのように収集・確認・更新しているかの方針です。</p>
<h2>情報源</h2>
<p>掲載する制度の内容は、各自治体および公的機関が公式サイト等で公表している情報を根拠としています。
各制度ページには、根拠とした公式ページへの<strong>出典リンク</strong>と、
内容を確認した<strong>最終確認日</strong>を表示しています。</p>
<h2>品質基準（YMYL対応）</h2>
<p>お金や暮らしに関わる情報のため、確認が不十分な制度ページは検索エンジンにインデックスさせない
基準（noindex）を設けています。金額・対象・期限などの重要項目は、公式情報との整合を確認したうえで掲載します。</p>
<h2>更新のタイミング</h2>
<ul class="plainlist">
<li>制度の新設・改定・廃止を確認した場合</li>
<li>公式ページの内容に更新があった場合</li>
<li>定期的な再確認により、最終確認日を更新する場合</li>
</ul>
<h2>誤り・古い情報のご指摘</h2>
{report_html}
""")
    page(path="/update-policy/index.html", title=f"情報の更新方針・編集方針｜{SITE_NAME}",
         description=f"{SITE_SHORT}の情報源・品質基準・更新タイミング・訂正対応など、掲載情報の更新方針と編集方針を説明しています。",
         canonical="/update-policy/", breadcrumb=[("トップ","/"),("情報の更新方針",None)], body=policy)
    sitemap_urls.append(("/update-policy/","0.3"))

    # 免責事項
    disc = wrap(f"""
<h1>免責事項</h1>
<p class="lead">本サイト「{esc(SITE_SHORT)}」をご利用の前に、以下をご確認ください。</p>
<h2>情報の正確性について</h2>
<p>本サイトは、各自治体・公的機関が公表する情報をもとに整理していますが、内容の正確性・完全性・最新性を
保証するものではありません。制度の金額・対象・期限・申請方法などは、制度改定や自治体の判断により変更される
ことがあります。</p>
<h2>公式情報での確認のお願い</h2>
<p>本サイトは公的機関が運営するものではなく、公式の申請窓口でもありません。実際に制度を利用・申請される際は、
必ず各制度ページに記載の<strong>公式ページ（出典リンク）</strong>および各自治体の窓口で最新情報をご確認ください。</p>
<h2>免責</h2>
<p>本サイトの情報を利用したことにより生じたいかなる損害についても、運営者は責任を負いかねます。
また、本サイトからリンクする外部サイトの内容についても責任を負いません。</p>
""")
    page(path="/disclaimer/index.html", title=f"免責事項｜{SITE_NAME}",
         description=f"{SITE_SHORT}の免責事項。掲載情報の正確性や、公式ページでの最終確認のお願い、損害責任の範囲について説明しています。",
         canonical="/disclaimer/", breadcrumb=[("トップ","/"),("免責事項",None)], body=disc)
    sitemap_urls.append(("/disclaimer/","0.3"))

    # プライバシーポリシー
    ga = (f"<h2>アクセス解析について</h2><p>本サイトでは、サービス改善のためアクセス解析ツール"
          f"（{esc(ANALYTICS_NOTE)}）を利用しています。Cookie等を通じて閲覧ページ・アクセス日時・"
          f"ブラウザ種別などの利用状況を収集しますが、これにより個人を特定することはありません。"
          f"収集した情報はGoogle社のプライバシーポリシーに基づき取り扱われます。"
          f'詳細は <a href="https://policies.google.com/privacy" rel="noopener noreferrer" target="_blank">Googleのプライバシーポリシー</a> をご確認ください。</p>'
          ) if ANALYTICS_NOTE else ""
    priv = wrap(f"""
<h1>プライバシーポリシー</h1>
<p class="lead">本サイト「{esc(SITE_SHORT)}」における個人情報・アクセス情報の取り扱い方針です。</p>
<h2>取得する情報</h2>
<p>本サイトは、閲覧のみで利用でき、氏名・住所などの個人情報の入力を求めることはありません。
サーバーやアクセス解析により、アクセス日時・ブラウザ種別などの技術的な情報を取得する場合があります。</p>
{ga}
<h2>Cookieについて</h2>
<p>アクセス状況の把握のためにCookieを利用する場合があります。ブラウザの設定でCookieを無効にすることもできます。</p>
<h2>外部リンク</h2>
<p>本サイトは各自治体・公的機関などの外部サイトへのリンクを含みます。リンク先での個人情報の取り扱いについては、
各サイトのポリシーをご確認ください。</p>
<h2>お問い合わせ</h2>
{inquiry_html}
""")
    page(path="/privacy/index.html", title=f"プライバシーポリシー｜{SITE_NAME}",
         description=f"{SITE_SHORT}のプライバシーポリシー。取得する情報・Cookie・アクセス解析・外部リンクの取り扱いについて説明しています。",
         canonical="/privacy/", breadcrumb=[("トップ","/"),("プライバシーポリシー",None)], body=priv)
    sitemap_urls.append(("/privacy/","0.3"))

# ── トップ ──────────────────────────────────────────────────────────────────
def build_home(muni_stats, score, cat_entries=None):
    _tj={"ward":"区","city":"市","town":"町","village":"村"}
    _grp={"ward":"ku","city":"shi","town":"cho","village":"cho"}
    # 62市区町村を対等に：五十音順の単一グリッド（区/市/町村の階層を廃し、種別は小バッジで表示）
    all62=sorted(muni_stats, key=lambda x: (YOMI.get(x[0]["municipality_name"], x[0]["municipality_name"]), x[1]))
    def grid(rows):
        return '<ul class="mgrid" id="mgrid">'+''.join(
          f'<li data-nm="{esc(m["municipality_name"])}" data-yo="{esc(YOMI.get(m["municipality_name"],""))}" '
          f'data-ro="{s}" data-g="{_grp.get(m["municipality_type"],"cho")}">'
          f'<a href="/area/tokyo/{s}/"><em class="mt">{_tj.get(m["municipality_type"],"")}</em>'
          f'{esc(m["municipality_name"])}</a><span>{n}件</span></li>'
          for m,s,n in rows)+'</ul>'
    # 目的・年代の発見カード（トップの主要導線）
    pcards="".join(
      f'<a class="pchip" href="/ranking/{ev}/" style="--pc:{EV_META[ev][2]}">'
      f'<span class="pic">{icon_svg(ev)}</span><span>{esc(EV_META[ev][0])}</span></a>'
      for ev in EV_META)
    amt_sec = amount_rankings_html(cat_entries)
    body=f"""
<h1>東京都の給付・手当・助成を、自治体ごとに比較</h1>
<p class="lead">東京都62自治体で受けられる給付金・手当・助成制度を、出典と最終確認日つきで整理。
「住んでいる街・引っ越し先でどんな支援が受けられるか」を一目で比較できます。</p>
<section class="finder">
<h2 class="fh">目的・年代から制度がある地域を探す</h2>
<div class="pchips">{pcards}</div>
<p class="fmore"><a href="/find/">{CHEV_R} 目的・年代から探す</a></p>
</section>
{amt_sec}
<div class="cmpbox"><strong>制度ごとに自治体を比べる</strong>
<p>児童手当・産後ケア・高齢者紙おむつ・家賃補助など、同じ制度の金額・対象を東京都62自治体で横断比較できます。</p>
<p><a href="/hikaku/">{CHEV_R} 制度カテゴリ別の自治体比較を見る</a></p></div>
<h2 id="area">お住まいの市区町村から探す（東京都62市区町村）</h2>
<p class="lead2">23区・多摩地域の市・町村・島しょを区別なく、五十音順で一覧しています。どの市区町村も同じ粒度で制度をまとめています。</p>
<div class="mfilter">
<input type="search" id="msearch" placeholder="市区町村名で検索（例：世田谷 / せたがや / setagaya）" aria-label="市区町村名で検索" autocomplete="off">
<div class="mchips" role="group" aria-label="種別で絞り込み">
<button type="button" class="mchip on" data-f="all">すべて<b>62</b></button>
<button type="button" class="mchip" data-f="ku">区<b>23</b></button>
<button type="button" class="mchip" data-f="shi">市<b>26</b></button>
<button type="button" class="mchip" data-f="cho">町村・島しょ<b>13</b></button>
</div>
</div>
{grid(all62)}
<p class="mnone" id="mnone" hidden>該当する市区町村が見つかりません。条件を変えてお試しください。</p>
<script>
(function(){{
 var q=document.getElementById('msearch'),g=document.getElementById('mgrid'),
     none=document.getElementById('mnone'),
     chips=[].slice.call(document.querySelectorAll('.mchip')),
     lis=[].slice.call(g.querySelectorAll('li')),f='all';
 function nz(s){{return (s||'').toLowerCase();}}
 function apply(){{
  var t=nz(q.value.trim()),shown=0;
  lis.forEach(function(li){{
   var okF=(f==='all'||li.getAttribute('data-g')===f);
   var okT=(!t||nz(li.getAttribute('data-nm')).indexOf(t)>=0
            ||nz(li.getAttribute('data-yo')).indexOf(t)>=0
            ||nz(li.getAttribute('data-ro')).indexOf(t)>=0);
   var vis=okF&&okT;li.hidden=!vis;if(vis)shown++;
  }});
  none.hidden=shown>0;
 }}
 q.addEventListener('input',apply);
 chips.forEach(function(c){{c.addEventListener('click',function(){{
  f=c.getAttribute('data-f');
  chips.forEach(function(x){{x.classList.toggle('on',x===c);x.setAttribute('aria-pressed',x===c);}});
  apply();
 }});}});
}})();
</script>
"""
    page(path="index.html", title=SITE_NAME,
         description="東京都62自治体の給付金・手当・助成制度を、出典・最終確認日つきで自治体ごとに比較できるサービス。妊娠出産・子育て・引っ越し・退職失業・高齢介護のもらえるお金がわかります。",
         canonical="/", jsonld=[site_graph()], breadcrumb=None, body=body)
    sitemap_urls.append(("/","1.0"))

# ── 実行 ────────────────────────────────────────────────────────────────────
def main():
    score, avg = compute_scores()
    muni_stats=[]; total_prog=0; indexed=0
    cat_entries={}
    for m in munis:
        slug = muni_slug(m)
        if not slug:
            print("NO SLUG:", m["municipality_name"]); continue
        progs, counts = build_muni(m, slug, score, avg)
        for ev_slug,(ev_name,ev_intro) in EVENTS.items():
            build_muni_event(m, slug, ev_slug, ev_name, ev_intro, progs)
        for p in progs:
            total_prog+=1
            cats = classify(p["title"], p["summary"], p["benefit_description"], p["target_description"])
            facts = facts_of(p["id"])
            idx = build_program(m, slug, p, cats, progs)
            if idx: indexed+=1
            amount = amount_of(facts)
            for cid in cats:
                cat_entries.setdefault(cid,[]).append((m, slug, p, amount, idx))
        muni_stats.append((m, slug, len(progs)))
    # 比較ページ（先に自治体数を数え、関連カテゴリの内部リンク判定に使う）
    pre_counts={cid: len({e[0]["id"] for e in cat_entries[cid]}) for cid in cat_entries}
    cat_counts={}
    for cid in CAT_BY_ID:
        if cid in cat_entries:
            cat_counts[cid]=build_compare(cid, cat_entries[cid], pre_counts)
    build_compare_index(cat_counts)
    build_find_hub(score)
    for ev in EVENTS:
        build_ranking(ev, score, avg)
    build_static_pages()
    build_home(muni_stats, score, cat_entries)
    write_sitemap(); write_robots(); write_css()
    cmp_pub=sum(1 for v in cat_counts.values() if v>=3)
    print(f"生成完了: 自治体{len(muni_stats)} / 制度ページ{total_prog}（index {indexed} / noindex {total_prog-indexed}）")
    print(f"比較ページ: {len(cat_counts)}カテゴリ（index {cmp_pub}）")
    print(f"sitemap URL数: {len(sitemap_urls)}  出力先: {OUT}")
    print(f"BASE_URL={BASE_URL}  （本番前に SEIDO_BASE_URL を設定してください）")

def write_sitemap():
    parts=[]
    for entry in sitemap_urls:
        loc, prio = entry[0], entry[1]
        lastmod = entry[2] if len(entry) > 2 else None
        lm = f'<lastmod>{esc(lastmod)}</lastmod>' if lastmod else ''
        parts.append(f'<url><loc>{esc(BASE_URL+loc)}</loc>{lm}<priority>{prio}</priority></url>')
    write("sitemap.xml", f'<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">{"".join(parts)}</urlset>')

def write_robots():
    write("robots.txt", f"User-agent: *\nAllow: /\n\nSitemap: {BASE_URL}/sitemap.xml\n")

def write_css():
    write("assets/style.css", CSS)

CSS = """:root{--fg:#1a2233;--muted:#5b6577;--line:#e5e8ef;--bg:#fff;--accent:#1558d6;--soft:#f5f7fb;--badge:#eaf1fe}
*{box-sizing:border-box}html{-webkit-text-size-adjust:100%}
body{margin:0;font-family:"Noto Sans JP",system-ui,-apple-system,"Hiragino Kaku Gothic ProN",sans-serif;color:var(--fg);background:var(--bg);line-height:1.7}
a{color:var(--accent);text-decoration:none}a:hover{text-decoration:underline}
header.site{position:sticky;top:0;z-index:30;background:rgba(255,255,255,.96);backdrop-filter:saturate(1.2) blur(6px);padding:.55rem 1.1rem;border-bottom:1px solid var(--line)}
.hbar{max-width:960px;margin:0 auto;display:flex;align-items:center;gap:.35rem 1rem;flex-wrap:wrap}
.brand{font-weight:800;font-size:1.12rem;color:var(--fg);display:inline-flex;align-items:center;gap:.45rem;line-height:1.2}
.brand:hover{text-decoration:none}
.brand-mark{width:1.45rem;height:1.45rem;flex:none;display:block}
.gnav{display:flex;gap:.1rem;margin-left:auto;flex-wrap:wrap}
.gnav a{color:var(--fg);font-weight:600;font-size:.9rem;padding:.34rem .6rem;border-radius:8px}
.gnav a:hover{background:var(--soft);text-decoration:none}
@media(max-width:520px){.gnav a{padding:.3rem .44rem;font-size:.82rem}.brand{font-size:1rem}.brand-mark{width:1.3rem;height:1.3rem}header.site{padding:.5rem .8rem}}
@media(max-width:360px){.gnav{gap:0}.gnav a{padding:.3rem .34rem;font-size:.78rem}}
:target{scroll-margin-top:60px}
main{max-width:960px;margin:0 auto;padding:1.1rem 1.1rem 3rem}
.crumbs{font-size:.82rem;color:var(--muted);margin:.2rem 0 1rem}
.crumbs a{color:var(--muted)}
h1{font-size:1.5rem;line-height:1.35;margin:.2rem 0 .7rem}
h2{font-size:1.15rem;margin:1.8rem 0 .6rem;padding-bottom:.3rem;border-bottom:2px solid var(--soft)}
.lead{color:#333;margin:.4rem 0 1rem}
.meta{font-size:.83rem;color:var(--muted);margin:.2rem 0 1rem}
.badge,.tag,.pt,.cnt{display:inline-block}
.badge{background:var(--badge);color:var(--accent);font-size:.75rem;font-weight:700;padding:.15rem .55rem;border-radius:999px}
.notice{background:#fff7e6;border:1px solid #ffe1a8;color:#7a5a00;padding:.6rem .8rem;border-radius:8px;font-size:.85rem}
dl.facts{margin:.4rem 0;border:1px solid var(--line);border-radius:10px;overflow:hidden}
.fact{display:grid;grid-template-columns:8.5rem 1fr;border-top:1px solid var(--line)}
.fact:first-child{border-top:0}
.fact dt{background:var(--soft);font-weight:700;font-size:.86rem;padding:.7rem .8rem;margin:0}
.fact dd{margin:0;padding:.7rem .8rem}
.src{font-size:.72rem;color:var(--muted);white-space:nowrap;margin-left:.3rem}
@media(max-width:560px){.fact{grid-template-columns:1fr}.fact dt{border-bottom:1px solid var(--line)}}
.official{font-size:.9rem;margin:1rem 0}
ul.proglist{list-style:none;padding:0;margin:.3rem 0}
ul.proglist li{padding:.55rem .2rem;border-bottom:1px solid var(--line);display:flex;justify-content:space-between;gap:.6rem;align-items:baseline}
ul.proglist .pt{font-size:.74rem;color:var(--muted)}
.ev h2 .cnt{font-size:.8rem;color:#fff;background:var(--accent);border-radius:999px;padding:.05rem .5rem;margin-left:.4rem;vertical-align:middle}
.more{display:inline-block;margin:.5rem 0 1rem;font-size:.9rem}
ul.mgrid{list-style:none;padding:0;margin:.4rem 0 1rem;display:grid;grid-template-columns:repeat(auto-fill,minmax(150px,1fr));gap:.5rem}
ul.mgrid li{border:1px solid var(--line);border-radius:9px;padding:.5rem .7rem;display:flex;justify-content:space-between;align-items:baseline}
ul.mgrid li span{font-size:.75rem;color:var(--muted)}
ul.mgrid li a{display:inline-flex;align-items:baseline;gap:.35rem}
em.mt{font-style:normal;font-size:.66rem;color:var(--muted);border:1px solid var(--line);border-radius:5px;padding:0 .28rem;line-height:1.5;flex:none}
p.lead2{color:var(--muted);font-size:.86rem;margin:.1rem 0 .6rem}
.mfilter{margin:.2rem 0 .7rem}
#msearch{width:100%;box-sizing:border-box;padding:.6rem .8rem;font-size:1rem;border:1px solid var(--line);border-radius:9px;background:var(--bg,#fff);color:inherit}
#msearch:focus{outline:2px solid var(--accent,#2563eb);outline-offset:1px}
.mchips{display:flex;flex-wrap:wrap;gap:.4rem;margin-top:.5rem}
.mchip{font:inherit;font-size:.82rem;cursor:pointer;border:1px solid var(--line);background:transparent;color:var(--muted);border-radius:999px;padding:.28rem .7rem;display:inline-flex;align-items:center;gap:.3rem}
.mchip b{font-weight:600;font-size:.72rem;opacity:.7}
.mchip.on{background:var(--accent,#2563eb);border-color:var(--accent,#2563eb);color:#fff}
.mchip.on b{opacity:.85}
ul.mgrid li[hidden]{display:none}
p.mnone{color:var(--muted);font-size:.9rem;padding:.6rem 0}
footer.site{border-top:1px solid var(--line);padding:1.2rem 1.1rem;color:var(--muted);font-size:.8rem;max-width:960px;margin:0 auto}
footer.site a{color:var(--muted)}
.cmpbox{background:var(--soft);border:1px solid var(--line);border-radius:10px;padding:.8rem 1rem;margin:1.2rem 0}
.cmpbox strong{display:block;margin-bottom:.3rem}
.cmpbox ul{margin:.3rem 0 0;padding-left:1.1rem}
.cmpbox p{margin:.3rem 0}
.tablewrap{overflow-x:auto;margin:.6rem 0}
table.cmp{border-collapse:collapse;width:100%;font-size:.9rem}
table.cmp th,table.cmp td{border:1px solid var(--line);padding:.5rem .6rem;text-align:left;vertical-align:top}
table.cmp thead th{background:var(--soft);position:sticky;top:0}
table.cmp td.mn{white-space:nowrap;font-weight:600}
table.cmp td.dt{white-space:nowrap;color:var(--muted);font-size:.8rem}
.na{color:var(--muted);font-size:.85em}
.miss{font-size:.85rem;color:#555;background:#fafafa;border:1px solid var(--line);border-radius:8px;padding:.6rem .8rem}
.note{font-size:.8rem;color:var(--muted)}
ul.cmplist{list-style:none;padding:0;margin:.3rem 0}
ul.cmplist li{padding:.5rem .2rem;border-bottom:1px solid var(--line);display:flex;justify-content:space-between;align-items:baseline;gap:.6rem}
ul.cmplist .cnt2{font-size:.75rem;color:var(--muted);white-space:nowrap}
.fnav{margin:0 0 .7rem;line-height:2}
.fnav a{color:var(--muted)}
footer .copy{margin:.3rem 0 0}
.doc h2{font-size:1.08rem}
.doc .lead{margin-bottom:1rem}
ul.plainlist{margin:.3rem 0 .3rem 1.1rem;padding:0}
ul.plainlist li{margin:.2rem 0}
.backtop{margin-top:1.6rem;font-size:.9rem}

/* ── ライフイベント・アクセント（--pc で切替。常にラベル同伴）── */
.badge[style*="--pc"]{background:color-mix(in srgb,var(--pc) 16%,#fff);color:color-mix(in srgb,var(--pc) 72%,#111)}
.ev-ic{width:22px;height:22px;display:block}
.chev{width:.72em;height:.72em;vertical-align:-.08em;display:inline-block;flex:0 0 auto}
.parrow{display:inline-flex}.parrow .chev{width:1.05em;height:1.05em}

/* ── SVGグラフ ── */
.chartcard{border:1px solid var(--line);border-radius:12px;padding:.7rem .8rem .4rem;margin:.6rem 0;--pc:var(--accent)}
.chart{width:100%;max-width:560px;height:auto;display:block}
.chart .c-track{fill:#eef1f6}
.chart .c-bar{fill:var(--pc)}
.chart .c-avg{stroke:#8a94a6;stroke-width:2;stroke-dasharray:2 2}
.chart .c-lbl{fill:var(--fg);font-size:15px}
.chart .c-val{fill:var(--muted);font-size:13px;font-variant-numeric:tabular-nums}
.cap{font-size:.76rem;color:var(--muted);margin:.35rem 0 .2rem}
.profile{margin:1.2rem 0 1.4rem}
.profile .strong{margin:.2rem 0 .3rem}
.profile .strong b{color:var(--accent)}

/* ── 目的・年代の発見カード ── */
.finder{background:var(--soft);border:1px solid var(--line);border-radius:12px;padding:.9rem 1rem;margin:1.2rem 0}
.finder .fh{font-size:1.08rem;margin:.1rem 0 .7rem;border:0;padding:0}
.pchips{display:flex;flex-wrap:wrap;gap:.5rem}
.pchip{display:inline-flex;align-items:center;gap:.4rem;border:1px solid var(--line);background:#fff;border-radius:999px;padding:.4rem .8rem .4rem .55rem;font-size:.9rem;font-weight:600;color:var(--fg)}
.pchip .pic{display:inline-flex;color:#fff;background:var(--pc);border-radius:50%;padding:4px}
.pchip .pic .ev-ic{width:16px;height:16px}
.pchip:hover{border-color:var(--pc);text-decoration:none}
.fmore{margin:.7rem 0 0;font-size:.92rem}
.pgrid{display:grid;grid-template-columns:repeat(auto-fill,minmax(260px,1fr));gap:.7rem;margin:.6rem 0 1rem}
.pcard{display:flex;align-items:center;gap:.7rem;border:1px solid var(--line);border-left:4px solid var(--pc);border-radius:12px;padding:.8rem .9rem;color:var(--fg);background:#fff}
.pcard:hover{background:color-mix(in srgb,var(--pc) 7%,#fff);text-decoration:none}
.pcard .pic{flex:0 0 auto;display:inline-flex;color:#fff;background:var(--pc);border-radius:12px;padding:9px}
.pcard .ptxt{display:flex;flex-direction:column;min-width:0}
.pcard .ptxt strong{font-size:1rem}
.pcard .page{font-size:.74rem;color:var(--muted)}
.pcard .pdesc{font-size:.82rem;color:#333;margin-top:.15rem}
.pcard .ptop{font-size:.76rem;color:var(--pc);font-weight:700;margin-top:.2rem}
.pcard .parrow{margin-left:auto;color:var(--pc);font-weight:700}
table.cmp.rank td.rk{width:2.4rem;text-align:center;color:var(--muted);font-variant-numeric:tabular-nums}
table.cmp.rank tr.top3 td.rk{color:var(--accent);font-weight:800}
table.cmp.rank tr.top3 td.mn a{font-weight:700}

/* ── トップ：金額ランキング（目的カテゴリ切替） ── */
.amtrank{margin:1.4rem 0 1.6rem}
.amtrank .fh{font-size:1.08rem;margin:.1rem 0 .35rem;border:0;padding:0}
.amtrank .lead2{margin:.15rem 0 .35rem}
.archips{margin:.45rem 0 .1rem}
.archip.on{background:var(--pc,var(--accent));border-color:var(--pc,var(--accent));color:#fff}
.arpanel{margin:0}
.argrid{display:grid;grid-template-columns:repeat(auto-fit,minmax(240px,1fr));gap:.7rem;margin:.55rem 0 .5rem}
@media(max-width:820px){.argrid{grid-template-columns:1fr}}
.arbox{border:1px solid var(--line);border-top:3px solid var(--pc,var(--accent));border-radius:12px;padding:.75rem .85rem .7rem;background:#fff}
.arbox h3{margin:0 0 .15rem;font-size:.98rem;border:0;padding:0}
.arbox h3 a{color:var(--fg)}
.arunit{margin:0 0 .45rem;font-size:.75rem;color:var(--muted)}
.arlist{list-style:none;margin:0;padding:0}
.arlist li{display:grid;grid-template-columns:1.4rem 1fr auto;gap:.35rem;align-items:baseline;padding:.32rem 0;border-top:1px solid var(--line);font-size:.9rem}
.arlist li:first-child{border-top:0}
.arrk{color:var(--muted);font-variant-numeric:tabular-nums;font-weight:700}
.arlist li:nth-child(-n+3) .arrk{color:var(--pc,var(--accent))}
.armn{color:var(--fg);font-weight:600}
.aramt{color:var(--fg);font-variant-numeric:tabular-nums;white-space:nowrap;font-size:.86rem}
.armore{margin:.45rem 0 0;font-size:.84rem}
.armore a{color:var(--pc,var(--accent))}

/* ── 自治体：住まい相場・交通 ── */
.livability{margin:1.3rem 0 1.6rem;padding:1rem 1.05rem;border:1px solid var(--line);border-radius:12px;background:linear-gradient(180deg,#f7faf8 0%,#fff 55%)}
.livability .fh{font-size:1.08rem;margin:0 0 .35rem;border:0;padding:0}
.livability .lead2{margin:0 0 .75rem;color:var(--muted);font-size:.92rem}
.lvstats{display:grid;grid-template-columns:repeat(auto-fit,minmax(140px,1fr));gap:.55rem;margin:0 0 .85rem}
.lvstat{padding:.55rem .65rem;border:1px solid var(--line);border-radius:10px;background:#fff}
.lvstat .lvl{display:block;font-size:.72rem;color:var(--muted);margin-bottom:.15rem}
.lvstat .lvv{display:block;font-size:1.02rem;font-weight:700;font-variant-numeric:tabular-nums}
.lvstat .lvs{display:block;font-size:.78rem;color:var(--muted);margin-top:.1rem}
.lvcharts{display:grid;grid-template-columns:repeat(auto-fit,minmax(260px,1fr));gap:.7rem}
.lvbox{border:1px solid var(--line);border-radius:10px;padding:.65rem .75rem .5rem;background:#fff}
.lvbox h3{margin:0 0 .4rem;font-size:.88rem;border:0;padding:0;color:var(--fg)}
.lv-chart{width:100%;height:auto;display:block}
.livability .note{margin:.7rem 0 0;font-size:.78rem;color:var(--muted)}

/* ── 分野別に色分けした自治体ハブのセクション ── */
.ev{border-left:3px solid var(--pc,var(--accent));padding-left:.75rem;margin:1.4rem 0}
.ev>h2{border:0;display:flex;align-items:center;justify-content:flex-start;gap:.5rem;margin:.1rem 0 .5rem;font-size:1.12rem}
.evh{display:inline-flex;align-items:center;gap:.45rem}
.evh a{color:var(--fg)}
.evi{display:inline-flex;color:#fff;background:var(--pc,var(--accent));border-radius:7px;padding:3px}
.evi .ev-ic{width:15px;height:15px}
.ev>h2 .cnt{background:var(--pc,var(--accent))}
.evlinks{font-size:.85rem;margin:.35rem 0 .1rem}
.evlinks a{color:var(--pc,var(--accent))}
.cmpbox[style*="--pc"] strong{color:var(--pc)}
/* ── 関連制度・ほかの自治体（回遊） ── */
.related{margin:1.6rem 0 .4rem;border-top:1px solid var(--line);padding-top:.6rem}
.related h2{font-size:1.05rem;border:0}
.others{margin:1.8rem 0 .4rem}
.others h2{font-size:1.05rem}
.ostrip{display:flex;flex-wrap:wrap;gap:.4rem}
.ostrip a{border:1px solid var(--line);border-radius:999px;padding:.28rem .7rem;font-size:.85rem;color:var(--fg);background:#fff}
.ostrip a:hover{border-color:var(--accent);color:var(--accent);text-decoration:none}
.totop{margin:0 0 .6rem;text-align:right}
.totop a{color:var(--muted);font-size:.82rem}
"""

if __name__ == "__main__":
    main()
