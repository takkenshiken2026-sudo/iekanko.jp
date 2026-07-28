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
OPERATOR_NAME  = os.environ.get("SEIDO_OPERATOR",  "くらしの制度ナビ 運営事務局")
CONTACT_EMAIL  = os.environ.get("SEIDO_CONTACT",   "takken.shiken.2026@gmail.com")
# お問い合わせフォーム（Googleフォーム等）。設定するとフッター・各ページの窓口がフォーム優先になる。
CONTACT_FORM_URL = os.environ.get("SEIDO_CONTACT_FORM", "https://forms.gle/H3ASWfUnQ44E2LTX6").strip()
ESTABLISHED    = os.environ.get("SEIDO_ESTABLISHED", "2026")
# フッター共通の「お問い合わせ」リンク（全ページ）。フォーム未設定時はメールにフォールバック。
if CONTACT_FORM_URL:
    FOOTER_CONTACT_HTML = f'・<a href="{CONTACT_FORM_URL}" target="_blank" rel="noopener">お問い合わせ</a>'
elif "【" not in CONTACT_EMAIL:
    FOOTER_CONTACT_HTML = f'・<a href="mailto:{CONTACT_EMAIL}">お問い合わせ</a>'
else:
    FOOTER_CONTACT_HTML = ""
# Google Analytics 4 測定ID（全ページの <head> に gtag を出力）。空文字で無効化可。
GA_MEASUREMENT_ID = os.environ.get("SEIDO_GA_ID", "G-9TB0TXT8X0").strip()
# Google AdSense パブリッシャーID（全ページの <head> に adsbygoogle.js を出力／ads.txt も生成）。空文字で無効化可。
ADSENSE_CLIENT = os.environ.get("SEIDO_ADSENSE", "ca-pub-7927260139193410").strip()
# プライバシーポリシーのアクセス解析表記。未設定なら記載を省略。
ANALYTICS_NOTE = os.environ.get(
    "SEIDO_ANALYTICS",
    "Google Analytics 4（測定ID: %s）" % GA_MEASUREMENT_ID if GA_MEASUREMENT_ID else "",
)

# ── 品質ゲート（YMYL: 未検証の薄いページをインデックスさせない）────────────
GATE_MIN_CONFIDENCE = 82   # 制度の平均confidenceがこれ未満なら noindex

# ── ライフイベント別ページ（自治体×イベントの一覧）のインデックス方針 ──────────
# 制度名のリンク一覧が主体で本文が薄いため、AdSense審査中は noindex にして
# 中身の濃い制度詳細ページで評価を受ける。審査通過後に環境変数
# SEIDO_INDEX_LIFEEVENT=1 を設定して再ビルドすればインデックス対象に戻せる。
INDEX_LIFEEVENT = os.environ.get("SEIDO_INDEX_LIFEEVENT", "0") == "1"

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

# ── 解説ガイドの本文（オリジナルの編集コンテンツ）────────────────────────────────
# (url slug, event slug, H1, 短い説明, リード文, [(見出し, 本文HTML), ...])
GUIDES_EV = [
 ("pregnancy-birth","pregnancy_birth",
  "妊娠・出産でもらえるお金と手続きの基礎知識",
  "妊婦健診の助成から出産育児一時金、自治体の祝い金まで",
  "妊娠がわかってから出産までには、国と自治体の両方から受けられる支援があります。"
  "全国共通のものと、住んでいる区市町村によって変わるものを整理しておきましょう。",
  [("妊娠・出産でもらえるお金の主な種類",
    "<ul class=\"plainlist\">"
    "<li><strong>妊婦健診の費用助成</strong>：母子健康手帳の交付時に受診票（補助券）が渡され、健診費用の多くがカバーされます。助成の回数や上限は自治体で異なります。</li>"
    "<li><strong>出産育児一時金</strong>：健康保険から支給される全国共通の給付で、出産費用にあてられます。多くは医療機関へ直接支払う仕組み（直接支払制度）が利用できます。</li>"
    "<li><strong>出産・子育て応援の給付</strong>：妊娠時・出産時に支給される国の給付に、自治体が独自の上乗せや面談・クーポンを組み合わせている場合があります。</li>"
    "<li><strong>自治体独自の出産祝い金・祝品</strong>：区市町村によっては、出産時に祝い金やギフト・地域通貨を支給しています。金額の差が大きい分野です。</li>"
    "<li><strong>不妊治療・不育症治療の助成</strong>：保険適用と組み合わせて、自己負担分を助成する自治体があります。</li></ul>"),
   ("自治体で差が出るポイント",
    "<p>出産育児一時金のような国の給付は全国共通ですが、<strong>出産祝い金の有無や金額、妊婦健診・産後ケアの自己負担、不妊治療の上乗せ助成</strong>は自治体によって大きく変わります。"
    "「隣の区にはある祝い金が自分の区にはない」ということも珍しくありません。引っ越し先を検討している場合は、この差を確認しておくと役立ちます。</p>"),
   ("手続きの流れと注意点",
    "<p>多くの支援は、妊娠届を出して母子健康手帳を受け取るところから始まります。健診の受診票もこのときに交付されるのが一般的です。"
    "給付や助成には申請期限が設けられているものがあり、出産後の届け出とあわせて早めに確認しておくと安心です。"
    "里帰り出産などで住んでいる自治体以外で健診を受ける場合は、費用の払い戻し手続きが必要になることもあります。</p>")]),

 ("childcare","childcare",
  "子育て世帯が受けられる給付・手当の基礎知識",
  "児童手当・子ども医療費助成・保育料軽減などの全体像",
  "子育て期は、国の手当と自治体独自の助成が最も重なり合う時期です。"
  "代表的な支援の種類と、自治体で差が出やすいポイントを押さえておきましょう。",
  [("子育て世帯の主な支援",
    "<ul class=\"plainlist\">"
    "<li><strong>児童手当</strong>：中学生・高校生年代までの子どもを養育する世帯に支給される全国共通の手当です。</li>"
    "<li><strong>子ども医療費助成</strong>：子どもの通院・入院の自己負担を軽減する制度で、対象年齢・所得制限・自己負担額が自治体で大きく異なります。</li>"
    "<li><strong>保育料の軽減・無償化</strong>：幼児教育・保育の無償化に加え、自治体が独自に保育料を軽減している場合があります。</li>"
    "<li><strong>認可外・認証保育の補助</strong>：認可外や認証保育所を利用する世帯への月額補助で、上限額に自治体差があります。</li>"
    "<li><strong>ひとり親家庭への支援</strong>：児童扶養手当やひとり親医療費助成など、対象者向けの制度があります。</li></ul>"),
   ("自治体で差が出るポイント",
    "<p>子育て支援で最も差が出るのは<strong>子ども医療費助成の対象年齢と自己負担</strong>、そして<strong>認可外保育の補助額</strong>です。"
    "高校生年代まで医療費が実質無料の自治体もあれば、一部自己負担が残る自治体もあります。"
    "世帯の状況によって効いてくる制度が変わるため、複数の制度を組み合わせて確認するのがおすすめです。</p>"),
   ("確認しておきたいこと",
    "<p>手当や助成には、所得制限や申請期限があるものがあります。とくに医療費助成は「医療証」の交付申請が必要な自治体が多く、"
    "生まれてすぐや転入直後に手続きしておくと、あとから払い戻しの手間が省けます。"
    "詳しい対象・金額は、各自治体の公式ページで最新の内容を確認してください。</p>")]),

 ("moving","moving",
  "引っ越しの手続きと受けられる助成の基礎知識",
  "転入・転出の届け出と、住まいに関する自治体の支援",
  "引っ越しは、必要な行政手続きと、自治体独自の住まい支援の両方を確認したいタイミングです。"
  "やるべき手続きと、見落としがちな助成を整理しました。",
  [("引っ越しにともなう主な手続き",
    "<ul class=\"plainlist\">"
    "<li><strong>転出届・転入届</strong>：旧住所で転出届、新住所で転入届を出します。転入は引っ越し後おおむね14日以内が目安です。</li>"
    "<li><strong>マイナンバー・住民票の異動</strong>：カードの住所変更や各種登録の切り替えが必要です。</li>"
    "<li><strong>国民健康保険・国民年金・介護保険の異動</strong>：加入者は住所変更にともなう手続きが必要になります。</li>"
    "<li><strong>子育て・医療関連の再申請</strong>：子ども医療費助成などは自治体ごとの制度のため、転入先で改めて申請するのが一般的です。</li></ul>"),
   ("引っ越しで受けられる助成",
    "<p>自治体によっては、<strong>子育て世帯や若年夫婦の引っ越し・住み替えへの補助</strong>、<strong>家賃補助</strong>、"
    "<strong>三世代の同居・近居支援</strong>、<strong>空き家の活用支援</strong>などを設けています。"
    "これらは国の制度ではなく自治体独自のものが多く、条件（年齢・世帯・住む地域など）や金額の差が大きい分野です。"
    "転入前に「引っ越し先の候補ではどんな支援があるか」を比べておくと、実質的な負担がかなり変わることがあります。</p>"),
   ("注意点",
    "<p>助成には申請期限や、転入前後の時期の条件がついていることがあります。"
    "「転入してから◯か月以内」「対象は特定のエリア」といった条件を見落とすと受け取れないこともあるため、"
    "気になる制度は早めに窓口・公式ページで条件を確認しておきましょう。</p>")]),

 ("retirement-unemployment","retirement_unemployment",
  "退職・失業したときの給付と保険料軽減の基礎知識",
  "雇用保険・国保・年金の切り替えと、負担を軽くする制度",
  "退職・失業のときは、収入が減る一方で保険料や税の負担が続きます。"
  "受けられる給付と、負担を軽くするための制度を早めに確認しておきましょう。",
  [("退職・失業時に確認したい主な制度",
    "<ul class=\"plainlist\">"
    "<li><strong>雇用保険の基本手当（失業給付）</strong>：離職して求職活動ができる状態など、一定の条件を満たす場合に受けられる全国共通の給付です。ハローワークで手続きします。</li>"
    "<li><strong>国民健康保険への切り替え</strong>：会社の健康保険を抜けた場合、国民健康保険への加入（または任意継続）が必要です。</li>"
    "<li><strong>国民健康保険料の軽減</strong>：会社都合など非自発的な離職の場合、保険料が軽減される仕組みがあります。</li>"
    "<li><strong>国民年金の免除・納付猶予</strong>：所得が下がったときは、保険料の免除・猶予を申請できる場合があります。</li>"
    "<li><strong>住居確保給付金など</strong>：一定の要件のもとで家賃相当額の支援を受けられる制度があります。</li></ul>"),
   ("自治体で差が出るポイント",
    "<p>雇用保険や年金の免除は全国共通の仕組みですが、<strong>国民健康保険料の料率や軽減の運用</strong>、"
    "自治体独自の相談・生活支援は地域によって異なります。"
    "同じ収入でも、住む自治体によって国保料の負担感が変わることがあります。</p>"),
   ("手続きの順番と注意点",
    "<p>退職後は、健康保険の切り替え・年金の手続き・失業給付の申請を、期限に注意しながら進める必要があります。"
    "とくに国民健康保険や年金の免除は「申請しないと適用されない」ものが多く、放っておくと軽減を受けられません。"
    "会社都合離職の保険料軽減など、自分が対象になる制度を早めに確認しておくことが大切です。</p>")]),

 ("elderly-care","elderly_care",
  "高齢・介護で受けられる助成とサービスの基礎知識",
  "介護保険サービスと、自治体独自の高齢者向け助成",
  "高齢期は、介護保険を中心とした全国共通のサービスに加えて、"
  "自治体独自の助成やサービスが暮らしを支えます。代表的なものを整理しました。",
  [("高齢・介護の主な支援",
    "<ul class=\"plainlist\">"
    "<li><strong>介護保険サービス</strong>：要介護・要支援の認定を受けると、訪問介護やデイサービスなどを自己負担の一部で利用できます。</li>"
    "<li><strong>高額介護（介護予防）サービス費</strong>：自己負担が上限を超えた分が払い戻される仕組みです。</li>"
    "<li><strong>紙おむつの支給・費用助成</strong>：在宅で介護を受ける方などに、紙おむつを現物支給または費用助成する自治体があります。</li>"
    "<li><strong>補聴器の購入費助成</strong>：高齢者の補聴器購入費を助成する自治体が増えています。</li>"
    "<li><strong>住宅改修・福祉用具</strong>：手すりの設置や段差解消など、住まいの改修費を支援する制度があります。</li>"
    "<li><strong>配食・見守り・外出支援</strong>：日常生活を支える自治体独自のサービスがあります。</li></ul>"),
   ("自治体で差が出るポイント",
    "<p>介護保険サービスは全国共通の枠組みですが、<strong>紙おむつ支給・補聴器助成・住宅改修の上乗せ・配食や見守り</strong>といった"
    "上乗せ／横出しのサービスは自治体ごとに大きく異なります。"
    "「同じ介護度でも、住む街によって受けられる助けが違う」のはこの部分です。</p>"),
   ("確認しておきたいこと",
    "<p>介護保険サービスを使うには、まず要介護・要支援の認定申請が必要です。"
    "自治体独自の助成は、対象要件（介護度・所得・年齢など）や申請窓口が制度ごとに分かれていることが多いため、"
    "地域包括支援センターや自治体の窓口で、自分が使える制度をまとめて相談すると効率的です。"
    "具体的な金額・対象は各自治体の公式ページで確認してください。</p>")]),
]

# ライフイベント別メタ（目的・年代の発見導線／カラー＝検証済みパレット slot1-5／アイコン）
# 第2要素は旧・年代ラベル（見出しと重複するためカードでは非表示。互換のためタプル位置は維持）
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

# ── カテゴリ／ライフイベント別の雰囲気写真（docs/assets/photos/cropped/）──
PHOTO_BASE = "/assets/photos/cropped"
EV_PHOTO = {
 "pregnancy_birth": ("preg-boshi-techo.jpg", "母子健康手帳"),
 "childcare": ("child-park.jpg", "公園で遊ぶ子どものいる風景"),
 "moving": ("moving-boxes.jpg", "引っ越し用の段ボール箱"),
 "retirement_unemployment": ("procedure-mynumber.jpg", "行政手続きの申請書類"),
 "elderly_care": ("eld-aircon.jpg", "室内に設置されたエアコン"),
}
# 比較カテゴリごとの上書き（無い場合はライフイベント写真へフォールバック）
CAT_PHOTO = {
 "preg_kenshin": ("preg-boshi-techo.jpg", "母子健康手帳"),
 "preg_gift": ("child-baby-gear.jpg", "ベビー用品が並ぶ店内"),
 "preg_shussanhi": ("preg-boshi-techo.jpg", "母子健康手帳"),
 "preg_sango_care": ("child-infant.jpg", "室内に座る乳児"),
 "preg_funin": ("med-clinic-waiting.jpg", "医療機関の受付・待合"),
 "preg_tamondo": ("child-infant.jpg", "室内に座る乳児"),
 "child_teate": ("child-infant.jpg", "室内に座る乳児"),
 "child_fuyou": ("child-park.jpg", "公園で遊ぶ子どものいる風景"),
 "child_iryo": ("med-clinic-waiting.jpg", "医療機関の受付・待合"),
 "child_hitorioya": ("med-clinic-waiting.jpg", "医療機関の受付・待合"),
 "child_shugaku": ("child-study-desk.jpg", "学習デスク"),
 "child_hoiku_gen": ("child-park.jpg", "公園で遊ぶ子どものいる風景"),
 "child_ninkagai": ("child-baby-gear.jpg", "ベビー用品が並ぶ店内"),
 "child_iwai": ("child-baby-gear.jpg", "ベビー用品が並ぶ店内"),
 "child_shogakukin": ("child-study-desk.jpg", "学習デスク"),
 "child_omutsu_baby": ("child-infant.jpg", "室内に座る乳児"),
 "child_ikusei": ("child-park.jpg", "公園で遊ぶ子どものいる風景"),
 "house_juukyo": ("moving-boxes.jpg", "引っ越し用の段ボール箱"),
 "house_yachin": ("moving-boxes.jpg", "引っ越し用の段ボール箱"),
 "house_sansedai": ("moving-boxes.jpg", "引っ越し用の段ボール箱"),
 "house_reform": ("moving-boxes.jpg", "引っ越し用の段ボール箱"),
 "house_taishin": ("moving-boxes.jpg", "引っ越し用の段ボール箱"),
 "house_eco": ("house-solar.jpg", "住宅の太陽光パネル"),
 "job_kokuho": ("med-clinic-waiting.jpg", "医療機関の受付・待合"),
 "job_nenkin": ("procedure-mynumber.jpg", "行政手続きの申請書類"),
 "job_shurou": ("procedure-mynumber.jpg", "行政手続きの申請書類"),
 "job_kashitsuke": ("procedure-mynumber.jpg", "行政手続きの申請書類"),
 "job_konkyu": ("procedure-mynumber.jpg", "行政手続きの申請書類"),
 "job_shobyo": ("med-clinic-waiting.jpg", "医療機関の受付・待合"),
 "med_kogaku": ("med-clinic-waiting.jpg", "医療機関の受付・待合"),
 "med_sosai": ("procedure-mynumber.jpg", "行政手続きの申請書類"),
 "eld_omutsu": ("eld-aircon.jpg", "室内に設置されたエアコン"),
 "eld_kaigo_gen": ("eld-aircon.jpg", "室内に設置されたエアコン"),
 "eld_hochoki": ("med-clinic-waiting.jpg", "医療機関の受付・待合"),
 "eld_jutaku": ("moving-boxes.jpg", "引っ越し用の段ボール箱"),
 "eld_vaccine": ("med-clinic-waiting.jpg", "医療機関の受付・待合"),
 "eld_kinkyu": ("eld-aircon.jpg", "室内に設置されたエアコン"),
 "eld_haishoku": ("eld-aircon.jpg", "室内に設置されたエアコン"),
 "eld_iwai": ("eld-aircon.jpg", "室内に設置されたエアコン"),
 "eld_yougu": ("eld-aircon.jpg", "室内に設置されたエアコン"),
 "dis_iryo": ("med-clinic-waiting.jpg", "医療機関の受付・待合"),
 "dis_yougu": ("med-clinic-waiting.jpg", "医療機関の受付・待合"),
 "dis_teate": ("med-clinic-waiting.jpg", "医療機関の受付・待合"),
 "low_aircon": ("eld-aircon.jpg", "室内に設置されたエアコン"),
 "low_taxi": ("eld-aircon.jpg", "室内に設置されたエアコン"),
}

def photo_for_cats(cats, ev=None):
    """制度カテゴリ or ライフイベントから写真ファイル名と alt を返す。"""
    for cid in cats or []:
        if cid in CAT_PHOTO:
            return CAT_PHOTO[cid]
    if ev and ev in EV_PHOTO:
        return EV_PHOTO[ev]
    for cid in cats or []:
        if cid in CAT_BY_ID:
            e = CAT_BY_ID[cid][2]
            if e in EV_PHOTO:
                return EV_PHOTO[e]
    return EV_PHOTO.get(ev) or ("procedure-mynumber.jpg", "行政手続きの申請書類")

def photo_figure(fn, alt, css="progphoto", eager=False):
    load = 'loading="eager" fetchpriority="high"' if eager else 'loading="lazy"'
    return (f'<figure class="{css}">'
            f'<img src="{PHOTO_BASE}/{fn}" alt="{esc(alt)}" '
            f'width="960" height="640" {load} decoding="async">'
            f'</figure>')

# モノクロのシェブロン・アイコン（三角記号{CHEV_R}{CHEV_L}▲の代替。currentColorで文字色に追従）
_CHV='<svg class="chev" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="%s"/></svg>'
CHEV_R=_CHV % "M9 5l7 7-7 7"
CHEV_L=_CHV % "M15 5l-7 7 7 7"
CHEV_U=_CHV % "M5 15l7-7 7 7"

# 汎用アイコン（stroke/currentColor）。見出し・factラベルの視認性向上に使用。
_ICON_PATHS = {
 "user":'<circle cx="12" cy="8" r="3.6"/><path d="M5 20c0-3.6 3.1-6 7-6s7 2.4 7 6"/>',
 "yen":'<path d="M6 4l6 8 6-8"/><path d="M12 12v8"/><path d="M8 14h8"/><path d="M8 17.5h8"/>',
 "gift":'<rect x="4.5" y="9.5" width="15" height="10.5" rx="1"/><path d="M3.5 9.5h17M12 9.5V20"/>',
 "check":'<circle cx="12" cy="12" r="8.5"/><path d="M8 12.2l2.6 2.6L16 9.5"/>',
 "file":'<path d="M7 3.5h7l4 4V20.5H7z"/><path d="M14 3.5v4h4M9.5 13h5M9.5 16.5h5"/>',
 "calendar":'<rect x="4.5" y="5.5" width="15" height="14.5" rx="2"/><path d="M4.5 9.5h15M9 3.5v4M15 3.5v4"/>',
 "clock":'<circle cx="12" cy="12" r="8.5"/><path d="M12 7.5V12l3 1.8"/>',
 "globe":'<circle cx="12" cy="12" r="8.5"/><path d="M3.5 12h17M12 3.5c2.8 2.8 2.8 14.2 0 17M12 3.5c-2.8 2.8-2.8 14.2 0 17"/>',
 "building":'<rect x="5.5" y="4" width="13" height="16.5" rx="1"/><path d="M9 8h2M13 8h2M9 12h2M13 12h2M10.5 20.5v-3.5h3v3.5"/>',
 "external":'<path d="M14 4.5h5.5V10M19.5 4.5L11 13M18 14v5.5H5.5V6H11"/>',
 "info":'<circle cx="12" cy="12" r="8.5"/><path d="M12 11v5.5M12 7.6h.01"/>',
 "clipboard":'<rect x="6" y="4.5" width="12" height="16" rx="1.5"/><path d="M9 4.5a3 3 0 0 1 6 0M9 11h6M9 14.5h6"/>',
 "help":'<circle cx="12" cy="12" r="8.5"/><path d="M9.6 9.2a2.5 2.5 0 1 1 3.6 2.4c-.9.5-1.2.9-1.2 1.9M12 16.6h.01"/>',
 "link":'<path d="M9.5 14.5l5-5M8.5 11l-2 2a3.2 3.2 0 0 0 4.5 4.5l2-2M15.5 13l2-2A3.2 3.2 0 0 0 13 6.5l-2 2"/>',
 "bars":'<path d="M5 20V11M12 20V4M19 20v-6"/>',
 "home":'<path d="M4 11l8-7 8 7M6 10v9h12v-9"/>',
 "book":'<path d="M5 4.5h9a2.5 2.5 0 0 1 2.5 2.5V20a2 2 0 0 0-2-2H5zM19 6.5V18"/>',
 "compass":'<circle cx="12" cy="12" r="8.5"/><path d="M15.5 8.5l-2 5-5 2 2-5z"/>',
}
def ic(name, cls="ic"):
    p=_ICON_PATHS.get(name)
    if not p: return ""
    return (f'<svg class="{cls}" viewBox="0 0 24 24" fill="none" stroke="currentColor" '
            f'stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">{p}</svg>')

# factラベル -> アイコン名
FACT_ICONS = {
 "対象者":"user","対象の詳細":"user","対象範囲":"user","定員":"user",
 "支給額・助成額":"yen","上限":"yen","返済":"yen",
 "内容・給付":"gift","支援内容":"gift","サービス内容":"gift",
 "条件":"check","申請方法":"file","必要書類":"file",
 "申請期限":"calendar","日程":"calendar","期間":"calendar","開始":"calendar",
 "支給時期":"clock","オンライン手続き":"globe","窓口":"building",
 "目的":"info","公式ページ":"external",
}

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

# 比較ページのグラフ対象カテゴリ: cid -> (単位ラベル, 抽出モード, 色)
# 比較ページのグラフのみ追加するカテゴリ（トップの金額ランキングには載せない）。
# 金額差が出て比較に意味があるものを厳選。mode="generic" は妥当な範囲の最大円額を抽出。
EXTRA_CHART_CATS = [
 ("child_ninkagai","月額上限の目安","hoiku_cap"),
 ("child_shugaku","支給額の目安","generic"),
 ("child_shogakukin","支給・貸付上限の目安","generic"),
 ("house_reform","助成上限の目安","generic"),
 ("house_eco","助成上限の目安","generic"),
 ("eld_iwai","支給額の目安","generic"),
 ("eld_yougu","助成上限の目安","generic"),
 ("dis_yougu","助成上限の目安","generic"),
]
CHART_SPEC = {}
for _ev, _specs in AMOUNT_RANK_BY_EVENT:
    _color = EV_META[_ev][2]
    for _cid, _title, _unit, _mode in _specs:
        CHART_SPEC.setdefault(_cid, (_unit, _mode, _color))
for _cid, _unit, _mode in EXTRA_CHART_CATS:
    _ev = CAT_BY_ID[_cid][2]
    CHART_SPEC.setdefault(_cid, (_unit, _mode, EV_META[_ev][2]))

# 比較ページの「対応状況」可視化（金額が共通基準で揃うカテゴリ向け）。
# 妊婦健診は公費負担額が東京都共通の受診票で統一され金額差が出ないため、金額棒グラフの代わりに
# 「基本の健診に加えてどこまで助成があるか」の対応自治体数をカバレッジ・バーで可視化する。
# feats の判定は各自治体の該当制度テキスト（タイトル/概要/内容/対象/金額）に対する正規表現。
# note は誤解を避けるための注記（なぜ金額でなく対応状況で比べるか）。
COVERAGE_SPEC = {
 "preg_kenshin": {
   "ev":"pregnancy_birth",
   "note":("妊婦健診そのものの公費負担額は東京都共通の受診票（都基準単価）でほぼ統一されているため、"
           "金額ではなく「基本の健診に加えてどこまで助成があるか」で比較しています。"
           "各自治体の詳細・出典は下の一覧からご確認ください。"),
   "feats":[
     ("里帰り出産（都外受診）に対応", r"里帰り"),
     ("産婦健診（産後の健診）",       r"(?<!妊)産婦健|産後.{0,3}健診"),
     ("多胎妊婦への追加助成",         r"多胎"),
     ("妊婦歯科健診",                 r"歯科"),
   ],
 },
 "preg_sango_care": {
   "ev":"pregnancy_birth",
   "note":("産後ケアは自治体によって実施している形態（宿泊・日帰り・訪問）や利用料が異なります。"
           "ここでは提供している事業形態に対応する自治体数を比較しています。"
           "利用料・利用回数の詳細は各自治体ページの出典でご確認ください。"),
   "feats":[
     ("宿泊型（ショートステイ）", r"宿泊|ショートステイ"),
     ("デイ型（日帰り・通所）",   r"デイ|日帰り|通所"),
     ("訪問型（アウトリーチ）",   r"訪問|アウトリーチ"),
   ],
 },
 "eld_kinkyu": {
   "ev":"elderly_care",
   "note":("緊急通報・見守りは自治体によって提供するサービスが分かれます。"
           "ここでは提供しているサービスに対応する自治体数を比較しています。"
           "対象要件・費用・機器の種類は各自治体ページの出典でご確認ください。"),
   "feats":[
     ("緊急通報システム（通報装置）",   r"緊急通報|救急通報|安否通報|非常通報|シルバーホン"),
     ("見守り・安否確認",             r"見守り|安否確認|センサー"),
     ("自動通話録音機（特殊詐欺対策）", r"通話録音|自動通話"),
   ],
 },
}

def _yen_int(s):
    return int(str(s).replace(",", "").replace("，", ""))

def extract_rank_yen(text, mode):
    """比較可能な円額を抽出。抽出できない／比較不向きなら None。"""
    t = re.sub(r"<[^>]+>", "", text or "")
    t = t.replace("，", ",")
    if not t or "記載を確認中" in t:
        return None
    if mode == "generic":
        vals = []
        for m in re.finditer(r"(\d+(?:\.\d+)?)\s*万円", t):
            vals.append(int(float(m.group(1)) * 10000))
        for m in re.finditer(r"([0-9,]+)\s*円", t):
            v = _yen_int(m.group(1))
            if 1000 <= v <= 10000000:
                vals.append(v)
        return max(vals) if vals else None
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


def extract_any_yen(text):
    """制度の支給額テキストから代表的な円額を1つ抽出（合計用）。"""
    if not text:
        return None
    for mode in (
        "taishin_cap", "funin_cap", "aircon_cap", "hoiku_cap", "rent_monthly",
        "purchase_cap", "monthly_cap", "monthly", "birth_aid", "birth_gift",
        "child_gift", "loan_cap",
    ):
        v = extract_rank_yen(text, mode)
        if v:
            return v
    t = re.sub(r"<[^>]+>", "", text or "")
    t = t.replace("，", ",")
    if not t or "記載を確認中" in t or "公式ページで要確認" in t:
        return None
    vals = []
    for m in re.finditer(r"(\d+(?:\.\d+)?)\s*万円", t):
        vals.append(int(float(m.group(1)) * 10000))
    for m in re.finditer(r"([0-9,]+)\s*円", t):
        v = _yen_int(m.group(1))
        if 1000 <= v <= 50000000:
            vals.append(v)
    return max(vals) if vals else None


def format_sum_yen(yen):
    """件数と並べる金額合計の短い表記。"""
    if not yen:
        return ""
    if yen >= 100000000:
        s = f"{yen/100000000:.2f}".rstrip("0").rstrip(".")
        return f"{s}億円"
    if yen >= 10000:
        man = yen / 10000
        if man >= 100:
            return f"{man:,.0f}万円"
        s = f"{man:.1f}".rstrip("0").rstrip(".")
        return f"{s}万円"
    return f"{yen:,}円"

def amount_prefix(amt_text):
    """金額テキストから「月額」「上限」などの区分だけを取り出す（一覧の目安表示用）。"""
    t = amt_text or ""
    if "月額" in t or "月々" in t:
        return "月額"
    if any(k in t for k in ("上限", "限度", "以内", "まで", "を超えない")):
        return "上限"
    return ""


def amount_sum_of_programs(items):
    """プログラム一覧の支給額合計と、金額が取れた件数。"""
    total = 0
    n_amt = 0
    for p in items:
        amt = amount_of(facts_of(p["id"]))
        yen = extract_any_yen(amt) if amt else None
        if yen:
            total += yen
            n_amt += 1
    return total, n_amt


def cnt_with_sum_html(n_prog, yen_sum):
    """制度数バッジ + 金額合計バッジ。"""
    html_s = f'<span class="cnt">{n_prog}</span>'
    if yen_sum:
        html_s += f'<span class="csum" title="金額が分かる制度の合計（上限・月額などの目安）">計{esc(format_sum_yen(yen_sum))}</span>'
    return html_s

def _rank_rows_from_hikaku(cid, mode, top_n=5):
    path = os.path.join(OUT, "hikaku", cid, "index.html")
    if not os.path.isfile(path):
        return []
    with open(path, encoding="utf-8") as f:
        html_t = f.read()
    rows = []
    for href, name, amt in re.findall(
            r'<tr[^>]*><td class="mn"><a href="([^"]+)">([^<]+)</a></td><td>(.*?)</td>',
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

def svg_amount_bars(rows, mode, avg=None):
    """rows: [(yen, name, href, amt), ...] 降順。JS不要のSVG横棒グラフ。"""
    W=640; padL=112; padR=148; barH=15; rowH=29; top=8
    plotW=W-padL-padR
    maxval=max((r[0] for r in rows), default=1) or 1
    H=top+rowH*len(rows)+6
    p=[f'<svg viewBox="0 0 {W} {H}" class="chart" role="img" '
       f'preserveAspectRatio="xMinYMin meet" aria-label="支給額・助成額の自治体比較（横棒グラフ）">']
    for i,(yen,name,href,_amt) in enumerate(rows):
        y=top+rowH*i; cy=y+barH/2
        bw=plotW*(yen/maxval)
        p.append(f'<text x="{padL-8}" y="{cy:.0f}" class="c-lbl" text-anchor="end" dominant-baseline="central">{esc(name)}</text>')
        p.append(f'<rect x="{padL}" y="{y}" width="{plotW}" height="{barH}" rx="4" class="c-track"/>')
        p.append(f'<rect x="{padL}" y="{y}" width="{max(bw,3):.1f}" height="{barH}" rx="4" class="c-bar"/>')
        if avg:
            ax=padL+plotW*(min(avg,maxval)/maxval)
            p.append(f'<line x1="{ax:.1f}" y1="{y-2}" x2="{ax:.1f}" y2="{y+barH+2}" class="c-avg"/>')
        p.append(f'<text x="{W-8}" y="{cy:.0f}" class="c-val" text-anchor="end" dominant-baseline="central">{esc(format_rank_yen(yen,mode))}</text>')
    p.append('</svg>')
    return ''.join(p)

def compare_chart_html(cid, entries):
    """比較ページ上部の金額グラフ。金額差が出るカテゴリのみ描画（無ければ空）。"""
    spec=CHART_SPEC.get(cid)
    if not spec: return ""
    unit,mode,color=spec
    allrows=amount_rank_rows(entries, mode, top_n=999)
    if len(allrows)<4: return ""
    vals=[r[0] for r in allrows]
    if len(set(vals))<3: return ""
    avg=sum(vals)/len(vals)
    rows=allrows[:12]
    svg=svg_amount_bars(rows, mode, avg)
    return (f'<figure class="cmpchart" style="--pc:{color}">'
            f'<figcaption>支給額・助成額の比較（上位{len(rows)}自治体／{esc(unit)}）</figcaption>'
            f'{svg}'
            f'<p class="c-cap">破線は掲載{len(allrows)}自治体の平均の目安。公式情報から抽出した金額の目安で、'
            f'対象・条件により異なります。金額の記載がある自治体のみ表示しています。</p>'
            f'</figure>')

def compare_coverage_html(cid, entries):
    """金額が共通基準で揃うカテゴリ向けの『対応状況』可視化。金額棒グラフの代わりに、
    自治体で対応が分かれる項目ごとに『対応している自治体数』をカバレッジ・バーで描く。
    COVERAGE_SPEC 未登録・変化のない項目しか無い場合は空を返す。"""
    spec=COVERAGE_SPEC.get(cid)
    if not spec: return ""
    color=EV_META[spec["ev"]][2]
    # 自治体ごとに該当制度すべてのテキストを結合（entries は集約前の全該当制度）
    by_m={}
    for m, slug, p, amount, idx in entries:
        blob=" ".join(str(x or "") for x in
              (p["title"], p["summary"], p["benefit_description"], p["target_description"], amount))
        by_m.setdefault(m["id"], []).append(blob)
    total=len(by_m)
    if total<4: return ""
    texts=[" ".join(bl) for bl in by_m.values()]
    bars=[]; any_var=False
    for label, pat in spec["feats"]:
        rx=re.compile(pat)
        n=sum(1 for t in texts if rx.search(t))
        if 0<n<total: any_var=True
        bars.append((label, n, round(n/total*100)))
    if not any_var: return ""            # 全項目が全自治体一致なら描かない（比較価値なし）
    bars.sort(key=lambda b:-b[1])        # 対応が多い順
    lis="".join(
      f'<li><span class="cl">{esc(label)}</span>'
      f'<span class="cbar"><span class="cfill" style="width:{pct}%"></span></span>'
      f'<span class="cn">{n}<small>/{total}</small></span></li>'
      for label,n,pct in bars)
    return (f'<figure class="covchart" style="--pc:{color}">'
            f'<figcaption>自治体で対応が分かれる項目（掲載{total}自治体中の対応数）</figcaption>'
            f'<ul class="covbars">{lis}</ul>'
            f'<p class="c-cap">{esc(spec["note"])}</p>'
            f'</figure>')

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
        f'<h2 class="fh">{ic("yen","hi")}支給額・助成額が高い自治体</h2>'
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
    """rows: [(label, value, avg_or_None, note_or_'')]
    または [(label, value, avg_or_None, note_or_'', display_or_None)]
    display があれば右端の数値ラベルに使い、無ければ value+unit(+note) を組み立てる。"""
    W=640; padL=112; padR=148; barH=16; rowH=31; top=10
    plotW=W-padL-padR
    H=top+rowH*len(rows)+6
    p=[f'<svg viewBox="0 0 {W} {H}" class="chart" role="img" preserveAspectRatio="xMinYMin meet">']
    for i,row in enumerate(rows):
        label,val,avg,note = row[0],row[1],row[2],row[3]
        disp = row[4] if len(row) >= 5 else None
        y=top+rowH*i; cy=y+barH/2
        bw=plotW*(min(val,maxval)/maxval if maxval else 0)
        p.append(f'<text x="{padL-8}" y="{cy:.0f}" class="c-lbl" text-anchor="end" dominant-baseline="central">{esc(label)}</text>')
        p.append(f'<rect x="{padL}" y="{y}" width="{plotW}" height="{barH}" rx="4" class="c-track"/>')
        p.append(f'<rect x="{padL}" y="{y}" width="{max(bw,3):.1f}" height="{barH}" rx="4" class="c-bar"/>')
        if avg is not None:
            ax=padL+plotW*(min(avg,maxval)/maxval if maxval else 0)
            p.append(f'<line x1="{ax:.1f}" y1="{y-3}" x2="{ax:.1f}" y2="{y+barH+3}" class="c-avg"><title>都平均 {avg:.0f}{unit}</title></line>')
        if disp is not None:
            vlab=esc(disp)
        else:
            vlab=f'{val:.0f}{unit}'+(f' · {esc(note)}' if note else '')
        p.append(f'<text x="{W-8}" y="{cy:.0f}" class="c-val" text-anchor="end" dominant-baseline="central">{vlab}</text>')
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
    adsense_tag = ""
    if ADSENSE_CLIENT:
        ads_id = esc(ADSENSE_CLIENT)
        adsense_tag = (
            f'<!-- Google AdSense -->\n'
            f'<meta name="google-adsense-account" content="{ads_id}">\n'
            f'<script async src="https://pagead2.googlesyndication.com/pagead/js/adsbygoogle.js?client={ads_id}" crossorigin="anonymous"></script>\n'
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
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Noto+Sans+JP:wght@400;600;700;800&display=swap">
<link rel="stylesheet" href="/assets/style.css">
{adsense_tag}{ga_tag}{ld}</head>
<body id="top">
<header class="site"><div class="hbar">
<a class="brand" href="/"><img class="brand-mark" src="/assets/logo-mark.svg" width="28" height="28" alt="" decoding="async">{esc(SITE_SHORT)}</a>
<nav class="gnav" aria-label="メインナビゲーション">
<a href="/find/">目的で探す</a>
<a href="/hikaku/">制度を比較</a>
<a href="/guide/">ガイド</a>
<a href="/#area">自治体一覧</a>
</nav></div></header>
<main>
{crumbs}
{body}
</main>
<footer class="site">
<p class="totop"><a href="#top">{CHEV_U} ページの先頭へ</a></p>
<nav class="fnav" aria-label="サイト情報">
<a href="/">トップ</a>・<a href="/find/">目的・年代から探す</a>・<a href="/hikaku/">制度を比較する</a>・<a href="/guide/">くらしの制度ガイド</a>・<a href="/about/">運営者情報</a>・<a href="/update-policy/">情報の更新方針</a>・<a href="/disclaimer/">免責事項</a>・<a href="/privacy/">プライバシーポリシー</a>{FOOTER_CONTACT_HTML}
</nav>
<p class="copy">© {ESTABLISHED} {esc(SITE_SHORT)}（東京都62自治体・出典付き / 最終確認日を明記）</p>
</footer>
<script>document.addEventListener("click",function(e){{var tr=e.target.closest("tr[data-href]");if(!tr||e.target.closest("a,button,input,label,select"))return;var u=tr.getAttribute("data-href");if(u)location.href=u;}});</script>
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
    muni_cat={}; muni_ev_prog={}; muni_ev_yen={}
    for m in munis:
        for p in programs_of(m["id"]):
            cats=classify(p["title"],p["summary"],p["benefit_description"],p["target_description"])
            if not cats: continue
            muni_cat.setdefault(m["id"],set()).update(cats)
            evs={CAT_BY_ID[cid][2] for cid in cats if cid in CAT_BY_ID}
            d=muni_ev_prog.setdefault(m["id"],{})
            y=muni_ev_yen.setdefault(m["id"],{})
            amt = amount_of(facts_of(p["id"]))
            yen = extract_any_yen(amt) if amt else None
            for ev in evs:
                d[ev]=d.get(ev,0)+1
                if yen:
                    y[ev]=y.get(ev,0)+yen
    score={}
    for m in munis:
        mid=m["id"]; s={}
        for ev in EVENTS:
            covered=len([cid for cid in muni_cat.get(mid,()) if CAT_BY_ID.get(cid,(None,None,None))[2]==ev])
            total=ev_total.get(ev,0) or 1
            s[ev]={"cov":covered/total*100,"covered":covered,"total":total,
                   "prog":muni_ev_prog.get(mid,{}).get(ev,0),
                   "yen_sum":muni_ev_yen.get(mid,{}).get(ev,0)}
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

def program_cat_of(p):
    """制度の代表カテゴリ（ライフイベント）と表示色を返す。
    returns: (ev_attr, catname, color)  ev_attr は data-ev 用の空白区切りslug。"""
    evs = [e["slug"] for e in events_of(p["id"])]
    if not evs:
        return "other", "その他", "#7a8699"
    cat0 = next((e for e in EVENTS if e in evs), evs[0])
    catname = EVENTS[cat0][0] if cat0 in EVENTS else "その他"
    color = EV_META[cat0][2] if cat0 in EV_META else "#7a8699"
    return " ".join(evs), catname, color

def program_row_html(p, slug, i, href=None):
    """制度一覧テーブル1行（ハブ／ライフイベント／関連で共通）。"""
    href = href or f'/area/tokyo/{slug}/seido/{p["id"]}/'
    amt = amount_of(facts_of(p["id"]))
    yen = extract_any_yen(amt) if amt else 0
    amt_disp = (amount_prefix(amt) + format_sum_yen(yen)) if yen else "—"
    ev_attr, catname, color = program_cat_of(p)
    return (
        f'<tr data-nm="{esc(p["title"])}" data-ev="{esc(ev_attr)}" '
        f'data-amt="{yen or 0}" data-i="{i}" data-href="{href}">'
        f'<td class="c-name"><a href="{href}">{esc(p["title"])}</a></td>'
        f'<td class="c-amt{"" if yen else " na"}">{esc(amt_disp)}</td>'
        f'<td class="c-cat"><span class="ptag" style="--pc:{color}">{esc(catname)}</span></td>'
        f'<td class="c-type">{esc(PT_JA.get(p["program_type"],"制度"))}</td></tr>')

def program_table_html(rows_html, *, tbody_id="plist", sortable=True):
    """手当・助成の一覧テーブル（制度・金額・カテゴリ・種別＋任意で見出しソート）。"""
    if sortable:
        head = (
            f'<thead><tr>'
            f'<th class="c-name sortable" data-sort="name"><button type="button">制度・手当 <span class="sarr"></span></button></th>'
            f'<th class="c-amt sortable" data-sort="amt"><button type="button">金額の目安 <span class="sarr"></span></button></th>'
            f'<th class="c-cat">カテゴリ</th><th class="c-type">種別</th></tr></thead>')
    else:
        head = (
            f'<thead><tr><th class="c-name">制度・手当</th><th class="c-amt">金額の目安</th>'
            f'<th class="c-cat">カテゴリ</th><th class="c-type">種別</th></tr></thead>')
    return (f'<div class="tablewrap"><table class="ptable">{head}'
            f'<tbody id="{tbody_id}">{rows_html}</tbody></table></div>')

def order_programs_by_category(progs):
    """カテゴリ（EVENTS順）→その他の順に重複なく並べる。"""
    prog_ev = {p["id"]: [e["slug"] for e in events_of(p["id"])] for p in progs}
    seen = set(); ordered = []
    for ev_slug in EVENTS:
        for p in progs:
            if p["id"] not in seen and ev_slug in prog_ev[p["id"]]:
                seen.add(p["id"]); ordered.append(p)
    for p in progs:
        if p["id"] not in seen:
            seen.add(p["id"]); ordered.append(p)
    return ordered, prog_ev

def related_programs(m, slug, p, progs):
    pe = {e["slug"] for e in events_of(p["id"])}
    if not pe or not progs: return ""
    sibs = [q for q in progs if q["id"] != p["id"] and (pe & {e["slug"] for e in events_of(q["id"])})]
    if not sibs: return ""
    ordered, _ = order_programs_by_category(sibs)
    ordered = ordered[:6]
    rows = "".join(program_row_html(q, slug, i) for i, q in enumerate(ordered))
    return (f'<section class="related"><h2>{ic("link","hi")}{esc(m["municipality_name"])}の関連する制度</h2>'
            f'{program_table_html(rows, tbody_id="plist")}{PLIST_JS}</section>')

def _fact_clean(v):
    return re.sub(r"[。\.．\s]+$", "", (v or "").strip())

def program_about(mn, title, ptype, fm):
    """収集済みのfacts(fm: ラベル→値)だけから制度説明の本文を組み立てる。
    データが無い項目は文章に含めない（＝存在しない情報は書かない）。"""
    tgt = fm.get("対象者") or fm.get("対象の詳細")
    ben = fm.get("内容・給付") or fm.get("支援内容") or fm.get("サービス内容")
    amt = fm.get("支給額・助成額")
    cond = fm.get("条件")
    app = fm.get("申請方法")
    doc = fm.get("必要書類")
    ddl = fm.get("申請期限")
    pay = fm.get("支給時期")
    tclean = _fact_clean(title)
    s = []
    if tgt:
        s.append(f"{esc(mn)}の{esc(title)}は、{esc(_fact_clean(tgt))}を対象とした{esc(ptype)}です。")
    else:
        s.append(f"{esc(mn)}の{esc(title)}は、{esc(mn)}が実施する{esc(ptype)}です。")
    bc = _fact_clean(ben)
    if bc and bc != tclean and bc not in title:  # タイトルと同義の重複は書かない
        s.append(f"支援内容は、{esc(bc)}です。")
    if amt:
        s.append(f"支給額・助成額の目安は{esc(_fact_clean(amt))}です。")
    if cond:
        s.append(f"主な条件は、{esc(_fact_clean(cond))}です。")
    proc = []
    if app: proc.append(f"申請方法は{esc(_fact_clean(app))}")
    if doc: proc.append(f"必要書類は{esc(_fact_clean(doc))}")
    if ddl: proc.append(f"申請期限は{esc(_fact_clean(ddl))}")
    if pay: proc.append(f"支給時期は{esc(_fact_clean(pay))}")
    html_out = "<p>" + "".join(s) + "</p>"
    if proc:
        html_out += "<p>" + "、".join(proc) + "です。</p>"
    return html_out

def build_faq(fm, title, mn, ptype, cats):
    """facts(fm)を元に、表や説明文とは別の言い回し・別角度でFAQを組み立てる。
    値そのものは実データだが、質問・前後の文はQ&A用に言い換え、丸写しの重複を避ける。
    データが無い項目は作らない（憶測しない）。最大6問。"""
    c=_fact_clean
    tclean=c(title)
    tgt=fm.get("対象者") or fm.get("対象の詳細")
    amt=fm.get("支給額・助成額")
    ben=fm.get("内容・給付") or fm.get("支援内容") or fm.get("サービス内容")
    app=fm.get("申請方法")
    doc=fm.get("必要書類")
    ddl=fm.get("申請期限")
    pay=fm.get("支給時期")
    cond=fm.get("条件")
    out=[]
    if tgt:
        out.append(("誰が対象になりますか？",
            f"対象となるのは{c(tgt)}です。ご自身が当てはまるかどうかは、申請前に{mn}の窓口や公式ページで確認しておくと安心です。"))
    if amt:
        out.append(("どのくらいの金額を受け取れますか？",
            f"受け取れる金額の目安は{c(amt)}です。所得や世帯の状況、年度によって変わることがあるため、確定額は申請時にご確認ください。"))
    bc=c(ben)
    if bc and bc!=tclean and bc not in title:
        out.append(("どんな支援を受けられますか？",
            f"この制度では、{bc}という支援が受けられます。"))
    if app:
        out.append(("どうやって申請すればよいですか？",
            f"申請は{c(app)}という形で手続きします。必要書類や当日の流れは、公式ページの最新の案内もあわせてご確認ください。"))
    if doc and len(out)<5:
        out.append(("申請に必要なものは何ですか？",
            f"手続きには{c(doc)}が必要です。ケースによって追加書類を求められることもあります。"))
    if ddl:
        out.append(("いつまでに申請すればよいですか？",
            f"申請期限は{c(ddl)}です。期限を過ぎると対象外になることがあるため、早めの準備がおすすめです。"))
    if pay and len(out)<6:
        out.append(("いつ頃もらえますか？",
            f"支給の時期の目安は{c(pay)}です。審査や書類確認により前後する場合があります。"))
    if cond and len(out)<6:
        out.append(("利用に条件はありますか？",
            f"利用にあたっては、{c(cond)}などの条件があります。ほかにも要件が設けられている場合があるため、詳細は公式ページでご確認ください。"))
    out=out[:6]
    cl=[x for x in (cats or []) if x in CAT_BY_ID]
    if cl and len(out)<6:
        out.append(("同じような制度は他の自治体にもありますか？",
            f"はい。東京都の他の自治体にも「{CAT_BY_ID[cl[0]][1]}」にあたる制度があり、金額や対象は自治体ごとに異なります。"
            f"当サイトの比較ページで、各自治体の内容を見比べられます。"))
    return out[:6]

def faq_table_html(faq):
    """FAQを表形式（質問｜回答）で描画。制度詳細ページ・比較ページで共用。"""
    if not faq: return ""
    rows="".join(f'<tr><th scope="row">{esc(q)}</th><td>{esc(a)}</td></tr>' for q,a in faq)
    return (f'<div class="tablewrap"><table class="faqtable">'
            f'<thead><tr><th>質問</th><th>回答</th></tr></thead>'
            f'<tbody>{rows}</tbody></table></div>')

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
    fm = {}
    for order,lbl,val,ev,cf in facts:
        if not val: continue
        fm.setdefault(lbl, val)
        src = f' <a class="src" href="{esc(ev)}" target="_blank" rel="nofollow noopener">出典</a>' if ev else ""
        dl.append(f'<div class="fact"><dt>{ic(FACT_ICONS.get(lbl,""),"fi")}{esc(lbl)}</dt>'
                  f'<dd>{esc(val)}{src}</dd></div>')
    faq = build_faq(fm, title, mn, ptype, cats)
    official = p["official_url"] or (m["official_site_url"] or "")
    if "example.invalid" in official:  # 復元DBの「公式URL無し」ダミーは公式リンクを出さない
        official = ""
    off_host = re.sub(r"^https?://", "", official).split("/")[0] if official else ""
    facts_html = f'<dl class="facts">{"".join(dl)}</dl>' if dl else "<p>詳細は出典の公式ページをご確認ください。</p>"
    faq_html = ""
    if faq:
        faq_html = f'<h2>{ic("help","hi")}よくある質問</h2>{faq_table_html(faq)}'
    # 公式ページは FAQ の直下に独立セクション（制度の内容表からは外す）
    official_html = ""
    if official:
        official_html = (
            f'<h2>{ic("external","hi")}公式ページ</h2>'
            f'<p class="offlead">最新の対象・金額・申請方法は、{esc(mn)}の公式ページでご確認ください。</p>'
            f'<p class="official"><a class="offbtn" href="{esc(official)}" target="_blank" rel="nofollow noopener">'
            f'公式ページで詳細・申請方法を確認{CHEV_R}'
            f'<span class="offbtn-host">{esc(off_host)}</span></a></p>'
            f'<p class="offnote">※金額・対象・申請方法は制度改定で変わることがあります。'
            f'最新情報は公式ページや{esc(mn)}の窓口で必ずご確認ください。</p>')

    summary_html = f'<p class="lead">{esc(p["plain_summary"] or p["summary"] or "")}</p>' if (p["plain_summary"] or p["summary"]) else ""
    ev_notice = "" if idx else '<p class="provnote">※このページは公表情報から自動収集した暫定データを含み、内容を確認中です。正確な最新情報は各制度の公式ページでご確認ください。</p>'
    # 信頼シグナル（掲載基準を満たしたindexページのみ。暫定ページは上の注意書きを表示）
    trustbar = ""
    if idx:
        _lvm = re.match(r"(\d{4})-(\d{2})", p["last_verified_at"] or "")
        tchips = []
        if _lvm:
            tchips.append(f'<span class="tchip">{ic("check","tci")}{_lvm.group(1)}年{int(_lvm.group(2))}月時点で確認済み</span>')
        tchips.append(f'<span class="tchip">{ic("external" if official else "file","tci")}'
                      f'{"公式サイトを出典に明記" if official else "自治体の公表情報をもとに作成"}</span>')
        trustbar = f'<div class="trustbar">{"".join(tchips)}</div>'

    _photo_fn, _photo_alt = photo_for_cats(cats)
    _header_zone = (
        f'<div class="area-head"><div class="area-head-main">'
        f'<span class="badge">{esc(ptype)}</span>'
        f'<h1>{esc(h1)}</h1>{summary_html}'
        f'<p class="meta">最終確認日: <time>{esc(p["last_verified_at"] or "—")}</time> ／ 対象自治体: <a href="/area/tokyo/{slug}/">{esc(mn)}</a></p>'
        f'</div>'
        f'{photo_figure(_photo_fn, _photo_alt, "progphoto")}'
        f'</div>{trustbar}')
    _about_zone = (
        f'<h2>{ic("info","hi")}この制度について</h2>{program_about(mn, title, ptype, fm)}'
        f'<p>{esc(mn)}で使えるほかの給付・手当は、<a href="/area/tokyo/{slug}/">{esc(mn)}の制度一覧</a>でまとめて確認できます。同じ制度の他自治体との比較は、ページ下部の比較リンクからどうぞ。</p>')
    _facts_zone = f'<h2>{ic("clipboard","hi")}制度の内容</h2>{facts_html}'
    if not official_html:
        _facts_zone += (
            f'<p class="offnote">※金額・対象・申請方法は制度改定で変わることがあります。'
            f'最新情報は公式ページや{esc(mn)}の窓口で必ずご確認ください。</p>')
    _tail_zone = related_programs(m, slug, p, progs) + compare_links(cats)
    _zones = [_header_zone, _about_zone, _facts_zone]
    if faq_html: _zones.append(faq_html)
    if official_html: _zones.append(official_html)
    if _tail_zone.strip(): _zones.append(_tail_zone)
    if ev_notice: _zones[-1] += ev_notice   # 暫定データの注記は控えめに、ページ下部へ
    _bands = "".join(
        f'<section class="band {"band-white" if i%2==0 else "band-soft"}"><div class="bandin">{z}</div></section>'
        for i,z in enumerate(_zones))
    body = f'<article class="program">{_bands}</article>'

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
    return f'<div class="cmpbox"><strong>{ic("bars","hi")}東京都の他自治体と比べる</strong><ul>{a}</ul></div>'

# ── 比較ページ（被リンク磁石）────────────────────────────────────────────────
def build_compare(cid, entries, counts=None):
    """entries: [(m, slug, program, amount, idx), ...]  同一カテゴリの全自治体分"""
    counts = counts or {}
    label, ev = CAT_BY_ID[cid][1], CAT_BY_ID[cid][2]
    ev_name = EVENTS.get(ev,("",""))[0]
    url = f"/hikaku/{cid}/"
    all_entries = entries          # 集約前の全該当制度（対応状況の判定に使う）
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
        rows.append(f'<tr data-href="/area/tokyo/{slug}/seido/{p["id"]}/"><td class="mn"><a href="/area/tokyo/{slug}/seido/{p["id"]}/">{esc(mn)}</a></td>'
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
    faq_html=faq_table_html(faq)

    title=f"【{ev_name}】{label} 東京都62自治体を比較｜金額・対象一覧"
    desc=clip(f"東京都の{label}を{have}自治体分まとめて比較。自治体ごとの金額・対象・最終確認日を一覧化。どの区市町村が手厚いかを出典付きで確認できます。",118)
    amt_note=(f"うち{n_amt}自治体は具体的な支給額・助成額を掲載しています。金額の記載がある自治体を上に表示しています。"
              if n_amt else "")
    body=f"""
<span class="badge">{esc(ev_name)}</span>
<h1>東京都の{esc(label)}を自治体で比較</h1>
<p class="lead">東京都62自治体の「{esc(label)}」を横断比較しています（掲載 {have}自治体・各制度に出典/最終確認日つき）。{esc(amt_note)}</p>
{photo_figure(*photo_for_cats([cid], ev), "evphoto")}
{compare_chart_html(cid, entries)}{compare_coverage_html(cid, all_entries)}
<div class="tablewrap"><table class="cmp">
<thead><tr><th>自治体</th><th>支給額・助成額</th><th>確認日</th></tr></thead>
<tbody>{''.join(rows)}</tbody></table></div>
{miss_html}
<p class="note">※金額は制度改定で変わります。申請前に必ず各自治体の公式ページ（各自治体ページ内の出典リンク）でご確認ください。</p>
{rel_html}
<h2>{ic("help","hi")}よくある質問</h2>
{faq_html}
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
        if not lis: continue
        color=EV_META[ev_slug][2]
        h2=(f'<h2 class="cmpsec-h" style="--pc:{color}">'
            f'<span class="pic">{icon_svg(ev_slug)}</span>{esc(ev_name)}</h2>')
        secs.append(f'<section class="cmpsec">{h2}<ul class="cmplist">{lis}</ul></section>')
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
    persona,_age,color,_ = EV_META[ev]
    ev_name = EVENTS[ev][0]
    url=f"/ranking/{ev}/"
    # yen_sum をスコアに載せる（無い場合は0）
    def yen_of(m):
        return score[m["id"]][ev].get("yen_sum", 0) or 0
    ranked=sorted(munis, key=lambda m:(-score[m["id"]][ev]["prog"], -yen_of(m), m["id"]))
    top=ranked[:15]
    max_prog=max((score[m["id"]][ev]["prog"] for m in top), default=1) or 1
    rows_prog=[]
    for m in top:
        s=score[m["id"]][ev]
        yen_txt=f'計{format_sum_yen(s["yen_sum"])}' if s.get("yen_sum") else "金額—"
        rows_prog.append((m["municipality_name"], s["prog"], None, "",
                          f'{s["prog"]}制度 · {yen_txt}'))
    chart_prog=svg_bars(rows_prog, max_prog, "制度")

    ranked_yen=sorted(munis, key=lambda m:(-yen_of(m), -score[m["id"]][ev]["prog"], m["id"]))
    top_yen=[m for m in ranked_yen if yen_of(m) > 0][:15]
    if not top_yen:
        top_yen=ranked_yen[:15]
    max_yen=max((yen_of(m) for m in top_yen), default=1) or 1
    rows_yen=[]
    for m in top_yen:
        s=score[m["id"]][ev]
        yen=yen_of(m)
        rows_yen.append((m["municipality_name"], yen, None, "",
                         f'計{format_sum_yen(yen)} · {s["prog"]}制度'))
    chart_yen=svg_bars(rows_yen, max_yen, "")

    trs=[]
    for rank,m in enumerate(ranked,1):
        s=score[m["id"]][ev]; slug=muni_slug(m)
        cls=' class="top3"' if rank<=3 else ''
        yen=yen_of(m)
        yen_cell = f'計{esc(format_sum_yen(yen))}' if yen else "—"
        trs.append(
            f'<tr{cls} data-href="/area/tokyo/{slug}/{ev}/" data-prog="{s["prog"]}" '
            f'data-yen="{yen}" data-i="{rank}">'
            f'<td class="rk">{rank}</td>'
            f'<td class="mn"><a href="/area/tokyo/{slug}/{ev}/">{esc(m["municipality_name"])}</a></td>'
            f'<td class="dt">{s["prog"]}制度</td>'
            f'<td class="dt yen">{yen_cell}</td></tr>')
    title=f"{ev_name}の制度がある東京都の自治体｜掲載数・金額でみる"
    desc=clip(f"{persona}向けに、{ev_name}関連の制度掲載数が多い東京都の自治体から順に確認できます。金額が分かる制度の合計もあわせて表示します。",118)
    chart_js=('''<script>(function(){var root=document.currentScript&&document.currentScript.previousElementSibling;'''
              '''if(!root||!root.classList.contains("chartcard"))root=document.querySelector(".chartcard");'''
              '''if(!root)return;var chips=[].slice.call(root.querySelectorAll("[data-rsort].mchip"));'''
              '''var panels=[].slice.call(root.querySelectorAll(".rsort-panel"));'''
              '''chips.forEach(function(c){c.addEventListener("click",function(){var k=c.getAttribute("data-rsort");'''
              '''chips.forEach(function(x){var on=x===c;x.classList.toggle("on",on);x.setAttribute("aria-pressed",on?"true":"false");});'''
              '''panels.forEach(function(p){p.hidden=p.getAttribute("data-rsort")!==k;});});});})();</script>''')
    body=f"""
<span class="badge" style="--pc:{color}">{esc(persona)}</span>
<h1>{esc(ev_name)}の制度がある東京都の自治体</h1>
<p class="lead">「{esc(persona)}」向けに、{esc(ev_name)}関連の制度を掲載している件数が多い自治体から順に並べています。金額が分かる制度の合計（上限・月額などの目安）も併記します。表の「制度数」「金額合計」見出しをクリックすると並び替えできます。</p>
{photo_figure(*EV_PHOTO[ev], "evphoto")}
<div class="chartcard" style="--pc:{color}">
<div class="mchips rsort" role="tablist" aria-label="グラフの並び替え">
<button type="button" class="mchip on" data-rsort="prog" aria-pressed="true">制度順</button>
<button type="button" class="mchip" data-rsort="yen" aria-pressed="false">金額順</button>
</div>
<div class="rsort-panel" data-rsort="prog">{chart_prog}
<p class="cap">上位15自治体（掲載制度数順）の制度数と金額合計</p></div>
<div class="rsort-panel" data-rsort="yen" hidden>{chart_yen}
<p class="cap">上位15自治体（金額合計順）の金額合計と制度数</p></div>
</div>
{chart_js}
<div class="tablewrap"><table class="cmp rank" id="ranktbl">
<thead><tr>
<th class="rk">順位</th>
<th class="mn">自治体</th>
<th class="sortable" data-sort="prog" aria-sort="descending"><button type="button">制度数 <span class="sarr"></span></button></th>
<th class="sortable" data-sort="yen" aria-sort="none"><button type="button">金額合計（目安） <span class="sarr"></span></button></th>
</tr></thead>
<tbody>{''.join(trs)}</tbody></table></div>
{RANK_TABLE_JS}
<p class="notice">掲載件数・金額合計は当サイトの収録状況に基づく目安です。月額と一時金を単純合算しているため、実際の手厚さや受給可否を示すものではありません。詳細・申請可否は各自治体の公式ページでご確認ください。</p>
{rel_rankings(ev)}
<p><a href="/find/">{CHEV_L} 目的・年代から探す にもどる</a></p>"""
    il={"@context":"https://schema.org","@type":"ItemList","name":f"{ev_name}の制度がある東京都の自治体",
        "itemListElement":[{"@type":"ListItem","position":i+1,"name":m["municipality_name"],
          "url":f"{BASE_URL}/area/tokyo/{muni_slug(m)}/{ev}/"} for i,m in enumerate(ranked[:20])]}
    bc=[("トップ","/"),("目的・年代から探す","/find/"),(f"{ev_name}の自治体",None)]
    page(path=url+"index.html",title=title,description=desc,canonical=url,
         jsonld=[il],breadcrumb=bc,body=body)
    sitemap_urls.append((url,"0.8"))

def purpose_cards_html(score):
    """目的・年代の発見カード（掲載数が多い例つきのリッチカード）。トップと /find/ で共用。"""
    def top1(ev):
        best=max(munis,key=lambda m:(score[m["id"]][ev]["prog"], score[m["id"]][ev].get("yen_sum",0), -m["id"]))
        return best["municipality_name"], score[best["id"]][ev]["prog"], score[best["id"]][ev].get("yen_sum",0)
    cards=[]
    for ev,(persona,_age,color,_) in EV_META.items():
        ev_name=EVENTS[ev][0]; tn,tp,ty=top1(ev)
        top_note=f"掲載数が多い例：{esc(tn)}（{tp}制度"
        if ty:
            top_note += f"・計{esc(format_sum_yen(ty))}"
        top_note += "）"
        fn, alt = EV_PHOTO[ev]
        cards.append(f'<a class="pcard" href="/ranking/{ev}/" style="--pc:{color}">'
            f'<span class="pimg"><img src="{PHOTO_BASE}/{fn}" alt="" width="320" height="200" loading="lazy" decoding="async"></span>'
            f'<span class="ptxt">'
            f'<span class="ptitle"><span class="pic">{icon_svg(ev)}</span><strong>{esc(persona)}</strong></span>'
            f'<span class="pdesc">{esc(ev_name)}の制度がある自治体をみる</span>'
            f'<span class="ptop">{top_note}</span></span>'
            f'<span class="parrow" aria-hidden="true">{CHEV_R}</span></a>')
    return f'<div class="pgrid">{"".join(cards)}</div>'

def build_find_hub(score):
    body=f"""
<h1>目的・年代から制度がある地域を探す</h1>
<p class="lead">ライフステージや目的を選ぶと、その分野の制度を掲載している東京都の自治体を件数順に確認できます。
「引っ越し先選び」や「いま住む街で使える制度の確認」にお使いください。金額が分かる制度の合計もあわせて表示します。</p>
{purpose_cards_html(score)}
<p class="note">※掲載件数・金額合計は当サイトの収録状況に基づく目安です。詳細・最新情報は各自治体の公式ページでご確認ください。</p>
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
    ordered, _ = order_programs_by_category(items)
    rows = "".join(program_row_html(p, slug, i) for i, p in enumerate(ordered))
    if ordered:
        listing=(
            '<div class="plist-ctrl">'
            '<input type="search" id="psearch" placeholder="制度名で検索" aria-label="制度名で検索" autocomplete="off">'
            '<div class="plist-row"><span class="lead2" style="margin:0">タップで対象・金額・申請方法がわかります</span>'
            '<label class="psort">並び替え <select id="psort" aria-label="並び替え">'
            '<option value="cat">カテゴリ順</option><option value="name">名称順</option>'
            '<option value="amt">金額が高い順</option></select></label></div></div>'
            f'{program_table_html(rows)}'
            '<p class="pnone" id="pnone" hidden>該当する制度が見つかりません。</p>')
    else:
        listing = "<p>該当する制度は現在準備中です。</p>"
    other_lis="".join(f'<li><a href="/area/tokyo/{slug}/{s}/">{esc(mn)}の{esc(EVENTS[s][0])}の制度 {CHEV_R}</a></li>'
                      for s in EVENTS if s!=ev_slug)
    relbox=(f'<div class="cmpbox" style="--pc:{EV_META[ev_slug][2]}"><strong>関連して探す</strong><ul>'
            f'<li><a href="/ranking/{ev_slug}/">{esc(ev_name)}の制度がある自治体をみる {CHEV_R}</a></li>'
            f'{other_lis}</ul></div>')
    title = f"{mn}で{ev_name}のときに使える制度・手当・助成【一覧】"
    desc = clip(f"{mn}で{ev_name}のときに受けられる給付金・手当・助成制度を一覧でまとめました。{ev_intro}", 118)
    yen_sum, n_amt = amount_sum_of_programs(items)
    if yen_sum:
        body_meta_extra = f'・金額が分かるもの合計 {esc(format_sum_yen(yen_sum))}（{n_amt}件）'
    else:
        body_meta_extra = ""
    body = f"""
<div class="area-head">
<div class="area-head-main">
<span class="badge" style="--pc:{EV_META[ev_slug][2]}">{esc(ev_name)}</span>
<h1>{esc(mn)}の{esc(ev_name)}で使える制度</h1>
<p class="lead">{esc(ev_intro)}</p>
<p class="meta">{esc(mn)}・{esc(ev_name)}関連の制度 {len(items)}件{body_meta_extra}</p>
</div>
<figure class="areamap"><img src="/assets/maps/{slug}.svg" width="760" height="395" alt="東京都における{esc(mn)}の位置を示した地図" decoding="async"><figcaption>東京都のなかの{esc(mn)}の位置</figcaption></figure>
</div>
{listing}
{relbox}
<p><a href="/area/tokyo/{slug}/">{CHEV_L} {esc(mn)}の制度一覧にもどる</a></p>
{PLIST_JS if ordered else ""}"""
    il = {"@context":"https://schema.org","@type":"ItemList","itemListElement":[
        {"@type":"ListItem","position":i+1,"name":p["title"],
         "url":f"{BASE_URL}/area/tokyo/{slug}/seido/{p['id']}/"} for i,p in enumerate(ordered)]}
    bc=[("トップ","/"),(mn,f"/area/tokyo/{slug}/"),(ev_name,None)]
    robots = "index,follow" if (items and INDEX_LIFEEVENT) else "noindex,follow"
    page(path=url+"index.html", title=title, description=desc, canonical=url,
         jsonld=[il], robots=robots, breadcrumb=bc, body=body)
    if items and INDEX_LIFEEVENT: sitemap_urls.append((url,"0.6"))

# ── 目的別ランキング表の並び替え（制度数／金額）──────────────────────────────
RANK_TABLE_JS = """<script>
(function(){
 var tbl=document.getElementById('ranktbl');
 if(!tbl)return;
 var body=tbl.tBodies[0];
 if(!body)return;
 var ths=[].slice.call(tbl.querySelectorAll('th[data-sort]'));
 var dir={prog:'desc'};
 function renumber(){
  [].slice.call(body.rows).forEach(function(tr,i){
   var rk=tr.querySelector('.rk');
   if(rk)rk.textContent=String(i+1);
   tr.classList.toggle('top3', i<3);
  });
 }
 function applySort(key){
  var natural='desc';
  var d=dir[key]?(dir[key]==='asc'?'desc':'asc'):natural;
  dir={}; dir[key]=d;
  var rows=[].slice.call(body.rows);
  rows.sort(function(a,b){
   var av=+(a.getAttribute('data-'+key)||0), bv=+(b.getAttribute('data-'+key)||0);
   if(av!==bv) return av-bv;
   var ai=+(a.getAttribute('data-i')||0), bi=+(b.getAttribute('data-i')||0);
   return ai-bi;
  });
  if(d==='desc') rows.reverse();
  rows.forEach(function(tr){body.appendChild(tr);});
  renumber();
  ths.forEach(function(th){
   th.setAttribute('aria-sort', th.getAttribute('data-sort')===key
     ?(d==='asc'?'ascending':'descending'):'none');
  });
 }
 ths.forEach(function(th){
  th.addEventListener('click',function(){applySort(th.getAttribute('data-sort'));});
 });
})();
</script>"""

# ── 自治体ハブ ──────────────────────────────────────────────────────────────
PLIST_JS = """<script>
(function(){
 var list=document.getElementById('plist');
 if(!list)return;
 var q=document.getElementById('psearch'),
     none=document.getElementById('pnone'),
     chips=[].slice.call(document.querySelectorAll('.pchip2')),
     sortsel=document.getElementById('psort'),
     lis=[].slice.call(list.children),ev='all';
 function nz(s){return (s||'').toLowerCase();}
 function apply(){
  var t=q?nz(q.value.trim()):'',shown=0;
  lis.forEach(function(li){
   var okE=(ev==='all'||(' '+li.getAttribute('data-ev')+' ').indexOf(' '+ev+' ')>=0);
   var okT=(!t||nz(li.getAttribute('data-nm')).indexOf(t)>=0);
   var vis=okE&&okT;li.hidden=!vis;if(vis)shown++;
  });
  if(none)none.hidden=shown>0;
 }
 var dir={},tbl=list.closest('table'),
     ths=tbl?[].slice.call(tbl.querySelectorAll('th[data-sort]')):[];
 function applySort(key){
  var natural=(key==='amt')?'desc':'asc';
  var d=dir[key]?(dir[key]==='asc'?'desc':'asc'):natural;dir[key]=d;
  var arr=lis.slice();
  if(key==='name')arr.sort(function(a,b){return a.getAttribute('data-nm').localeCompare(b.getAttribute('data-nm'),'ja');});
  else if(key==='amt')arr.sort(function(a,b){return (+a.getAttribute('data-amt'))-(+b.getAttribute('data-amt'));});
  else arr.sort(function(a,b){return (+a.getAttribute('data-i'))-(+b.getAttribute('data-i'));});
  if(d==='desc')arr.reverse();
  arr.forEach(function(li){list.appendChild(li);});
  ths.forEach(function(th){th.setAttribute('aria-sort',th.getAttribute('data-sort')===key?(d==='asc'?'ascending':'descending'):'none');});
  if(sortsel)sortsel.value=(key==='name'||key==='amt')?key:'cat';
 }
 if(q)q.addEventListener('input',apply);
 chips.forEach(function(c){c.addEventListener('click',function(){
  ev=c.getAttribute('data-ev');
  chips.forEach(function(x){var on=x===c;x.classList.toggle('on',on);x.setAttribute('aria-pressed',on);});
  apply();
 });});
 ths.forEach(function(th){th.addEventListener('click',function(){applySort(th.getAttribute('data-sort'));});});
 if(sortsel)sortsel.addEventListener('change',function(){dir[sortsel.value]=null;applySort(sortsel.value);});
})();
</script>"""

def build_muni(m, slug, score, avg):
    mn = m["municipality_name"]; url = f"/area/tokyo/{slug}/"
    progs = programs_of(m["id"])
    # 全制度を1つの一覧に（検索・カテゴリ絞り込み・並び替え可能）
    counts={}
    yen_sums={}
    prog_ev={p["id"]:[e["slug"] for e in events_of(p["id"])] for p in progs}
    for ev_slug,(ev_name,ev_intro) in EVENTS.items():
        items=[p for p in progs if ev_slug in prog_ev[p["id"]]]
        counts[ev_slug]=len(items)
        yen_sums[ev_slug]=amount_sum_of_programs(items)[0]
    # カテゴリ順（EVENTS順→その他）に重複なく整列
    ordered, prog_ev = order_programs_by_category(progs)
    ev_order=list(EVENTS.keys())
    other_count=sum(1 for p in ordered if not prog_ev[p["id"]])
    li_html=[program_row_html(p, slug, i) for i,p in enumerate(ordered)]
    chip_html=f'<button type="button" class="pchip2 on" data-ev="all" aria-pressed="true">すべて<b>{len(ordered)}</b></button>'
    for ev_slug in ev_order:
        if counts.get(ev_slug,0)>0:
            chip_html+=(f'<button type="button" class="pchip2" data-ev="{ev_slug}" '
                        f'style="--pc:{EV_META[ev_slug][2]}" aria-pressed="false">'
                        f'{esc(EVENTS[ev_slug][0])}<b>{counts[ev_slug]}</b></button>')
    if other_count>0:
        chip_html+=f'<button type="button" class="pchip2" data-ev="other" aria-pressed="false">その他<b>{other_count}</b></button>'
    purpose_links="".join(
      f'<a href="/area/tokyo/{slug}/{ev_slug}/">{esc(EVENTS[ev_slug][0])}（{counts[ev_slug]}件）{CHEV_R}</a>'
      for ev_slug in ev_order if counts.get(ev_slug,0)>0)
    purpose_html=(f'<p class="plist-purpose">目的・年代別のまとめページ：{purpose_links}</p>'
                  if purpose_links else "")
    plist_html=(
      f'<section class="plist-sec"><h2>{ic("list","hi")}{esc(mn)}の制度・手当の一覧（全{len(ordered)}件）</h2>'
      f'<p class="lead2">キーワード検索・カテゴリ絞り込み・並び替えができます。制度名をタップすると、対象・金額・申請方法の詳細が見られます。</p>'
      f'<div class="plist-ctrl">'
      f'<input type="search" id="psearch" placeholder="制度名で検索（例：児童手当 / 家賃 / 医療費）" aria-label="制度名で検索" autocomplete="off">'
      f'<div class="plist-row"><div class="pchips2" role="group" aria-label="カテゴリで絞り込み">{chip_html}</div>'
      f'<label class="psort">並び替え <select id="psort" aria-label="並び替え">'
      f'<option value="cat">カテゴリ順</option><option value="name">名称順</option>'
      f'<option value="amt">金額が高い順</option></select></label></div></div>'
      f'{program_table_html("".join(li_html))}'
      f'<p class="pnone" id="pnone" hidden>該当する制度が見つかりません。条件を変えてお試しください。</p>'
      f'{purpose_html}</section>')
    total_yen = sum(yen_sums.values())
    # 同一制度が複数ライフイベントに紐づく場合があるため、全体合計はプログラム単位で再計算
    total_yen, total_amt_n = amount_sum_of_programs(progs)
    mid=m["id"]
    # ほかの市区町村（種別を問わず五十音順の近隣）を対等に回遊
    _tj={"special_ward":"区","city":"市","town":"町","village":"村"}
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
        others_html=(f'<section class="others"><h2>{ic("building","hi")}ほかの市区町村を見る</h2>'
                     f'<div class="ostrip">{chips}</div>'
                     f'<p class="more"><a href="/#area">{CHEV_R} 東京都62市区町村の一覧から探す</a></p></section>')
    title = f"{mn}で受けられる給付・手当・助成 一覧｜対象・金額まとめ"
    desc = clip(f"{mn}で受けられる給付金・手当・助成・支援制度を{len(progs)}件、ライフイベント別に出典付きでまとめました。妊娠出産・子育て・引っ越し・退職失業・高齢介護の制度が一目でわかります。",118)
    try:
        _build_dir = os.path.dirname(os.path.abspath(__file__))
        if _build_dir not in sys.path:
            sys.path.insert(0, _build_dir)
        from livability_html import figures_section_html
        live_benefit = figures_section_html(slug, part="benefit")
        live_place = figures_section_html(slug, part="place")
    except Exception:
        live_benefit = live_place = ""
    lead_extra = f"全{len(progs)}件"
    if total_yen:
        lead_extra += f"・金額が分かるもの合計{format_sum_yen(total_yen)}（{total_amt_n}件）"
    body = f"""
<div class="area-head">
<div class="area-head-main">
<h1>{esc(mn)}で受けられる給付・手当・助成 一覧</h1>
<p class="lead">{esc(mn)}にお住まいの方が使える制度をまとめました（{esc(lead_extra)}・出典/最終確認日つき）。検索・カテゴリ絞り込み・並び替えで探せます。</p>
</div>
<figure class="areamap"><img src="/assets/maps/{slug}.svg" width="760" height="395" alt="東京都における{esc(mn)}の位置を示した地図" decoding="async"><figcaption>東京都のなかの{esc(mn)}の位置</figcaption></figure>
</div>
{live_benefit}
{plist_html}
{live_place}
{others_html}
{PLIST_JS}
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
    has_form = bool(CONTACT_FORM_URL)
    contact_link = f'<a href="mailto:{esc(CONTACT_EMAIL)}">{esc(CONTACT_EMAIL)}</a>' if has_ct else ""
    form_link = (f'<a href="{esc(CONTACT_FORM_URL)}" target="_blank" rel="noopener">お問い合わせフォーム</a>'
                 if has_form else "")
    if has_form:
        report_html = (f'<p>掲載内容に誤りや古い情報を見つけられた場合は、{form_link}よりお知らせください。'
                       '確認のうえ、可能な範囲で速やかに反映します。</p>')
        inquiry_html = f'<p>本サイト・本ポリシーに関するお問い合わせは、{form_link}よりお願いします。</p>'
    elif has_ct:
        report_html = (f'<p>内容に誤りや古い情報を見つけられた場合は、{contact_link} までご連絡ください。'
                       '確認のうえ、可能な範囲で速やかに反映します。</p>')
        inquiry_html = f'<p>本ポリシーに関するお問い合わせは {contact_link} までお願いします。</p>'
    else:
        report_html = '<p>内容の誤り・更新のご指摘を受け付ける窓口は準備中です。準備が整い次第、こちらでご案内します。</p>'
        inquiry_html = '<p>お問い合わせ窓口は準備中です。</p>'
    op_row = f'<div class="fact"><dt>運営者</dt><dd>{esc(OPERATOR_NAME)}</dd></div>' if has_op else ''
    ct_row = f'<div class="fact"><dt>連絡先</dt><dd>{contact_link}</dd></div>' if has_ct else ''
    form_row = f'<div class="fact"><dt>お問い合わせ</dt><dd>{form_link}</dd></div>' if has_form else ''
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
{form_row}
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
<h2>お問い合わせ</h2>
{inquiry_html}
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
<p>本サイトは各自治体・公的機関の公表情報をもとに整理した比較・案内サービスです。
最新かつ正確な内容は必ず各制度の公式ページでご確認ください。</p>
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
    ads = ('<h2>広告の配信について</h2>'
           '<p>本サイトは、第三者配信の広告サービス「Google AdSense」を利用しています。'
           'Googleなどの第三者配信事業者は、Cookieを利用して、ユーザーが本サイトや他のサイトに'
           '過去にアクセスした情報に基づいて広告を配信します。パーソナライズ広告は '
           '<a href="https://myadcenter.google.com/" rel="noopener noreferrer" target="_blank">Google 広告設定</a> '
           'で無効にできます。また、'
           '<a href="https://www.aboutads.info/choices/" rel="noopener noreferrer" target="_blank">www.aboutads.info</a> '
           'では第三者配信事業者のCookieを無効にできます。詳細は '
           '<a href="https://policies.google.com/technologies/ads" rel="noopener noreferrer" target="_blank">Googleの広告に関するポリシー</a> '
           'をご確認ください。</p>') if ADSENSE_CLIENT else ""
    priv = wrap(f"""
<h1>プライバシーポリシー</h1>
<p class="lead">本サイト「{esc(SITE_SHORT)}」における個人情報・アクセス情報の取り扱い方針です。</p>
<h2>取得する情報</h2>
<p>本サイトは、閲覧のみで利用でき、氏名・住所などの個人情報の入力を求めることはありません。
サーバーやアクセス解析により、アクセス日時・ブラウザ種別などの技術的な情報を取得する場合があります。</p>
{ga}
{ads}
<h2>Cookieについて</h2>
<p>アクセス状況の把握や広告配信のためにCookieを利用する場合があります。ブラウザの設定でCookieを無効にすることもできます。</p>
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

# ── 解説ガイド（オリジナルの編集コンテンツ：制度の基礎知識と探し方）────────────────
def build_guides():
    """データの一覧とは別に、制度の全体像・探し方・比較の勘どころをまとめた
    オリジナルの解説記事。ライフイベントごとの基礎知識から、当サイトの比較ページへ導線を張る。"""
    def wrap(inner):
        return ('<article class="doc">'+inner+
                f'<p class="backtop"><a href="/">{CHEV_L} トップにもどる</a></p></article>')
    note = ('<p class="note">※本ページは制度の全体像をつかむための一般的な解説です。'
            '金額・対象・期限・申請方法は自治体や年度によって異なり、改定されることがあります。'
            '実際の利用時は必ず各制度の公式ページと自治体の窓口で最新情報をご確認ください'
            '（<a href="/disclaimer/">免責事項</a>）。</p>')

    # ── ガイド一覧（ハブ）──
    ev_cards = "".join(
        f'<li><a href="/guide/{g[0]}/"><strong>{esc(g[2])}</strong>'
        f'<span class="pdesc">{esc(g[3])}</span></a></li>' for g in GUIDES_EV)
    hub = wrap(f"""
<h1>くらしの制度ガイド</h1>
<p class="lead">「どんなときに、どんな給付金・手当・助成が受けられるのか」を、ライフイベントごとに整理した解説記事です。
制度の全体像をつかんでから、<a href="/find/">目的・年代から探す</a>や
<a href="/hikaku/">制度カテゴリの自治体比較</a>で、お住まいの地域の実際の内容を確認できます。</p>
<h2>はじめての方へ</h2>
<p>公的な支援は「国の制度」と「自治体（東京都・区市町村）の制度」が重なり合っています。
国の制度は全国共通ですが、上乗せ・独自の助成は自治体ごとに大きく異なり、
同じライフイベントでも住む街によって受け取れる金額や対象が変わります。
まずは自分のライフイベントに近いガイドから読み進めてみてください。</p>
<h2>ライフイベント別ガイド</h2>
<ul class="cmplist guidegrid">{ev_cards}
<li><a href="/guide/how-to-find/"><strong>使える制度の探し方</strong>
<span class="pdesc">自分が対象になる給付・手当を見つける手順</span></a></li></ul>
{note}
""")
    page(path="/guide/index.html", title=f"くらしの制度ガイド｜給付・手当・助成の基礎知識｜{SITE_NAME}",
         description="妊娠・出産、子育て、引っ越し、退職・失業、高齢・介護など、ライフイベントごとにもらえる給付金・手当・助成の基礎知識と探し方をまとめた解説ガイドです。",
         canonical="/guide/", breadcrumb=[("トップ","/"),("くらしの制度ガイド",None)], body=hub)
    sitemap_urls.append(("/guide/","0.7"))

    # ── 探し方ガイド ──
    htf = wrap(f"""
<span class="badge">はじめに</span>
<h1>自分が使える給付金・手当の探し方</h1>
<p class="lead">公的な支援は「知っていれば受け取れたのに、知らずに申請しなかった」ということが起こりがちです。
自分が対象になりうる制度を見つけるための、基本的な手順を整理しました。</p>
<h2>1. いまの「ライフイベント」から考える</h2>
<p>給付・手当の多くは、妊娠・出産、子育て、引っ越し、退職・失業、高齢・介護といった
「暮らしの節目」に結びついています。まずは自分や家族がいまどの段階にいるかを起点にすると、
関連する制度をまとめて把握できます。当サイトの<a href="/find/">目的・年代から探す</a>では、
ライフイベントを選ぶだけで、その分野の制度を掲載している自治体を一覧できます。</p>
<h2>2. 「国の制度」と「自治体の制度」を分けて考える</h2>
<p>児童手当や高額療養費のように全国共通の国の制度と、各区市町村が独自に上乗せする助成は別ものです。
国の制度は原則どこに住んでいても受けられますが、金額や対象が手厚くなるかどうかは自治体次第です。
「自分の街ではどうか」を確認することが、受け取れる支援を取りこぼさないコツです。</p>
<h2>3. 住んでいる自治体で「実際の金額・対象」を確認する</h2>
<p>同じ名前の制度でも、支給額や対象条件は自治体でかなり違います。当サイトの
<a href="/hikaku/">制度カテゴリ別の自治体比較</a>では、制度ごとに東京都62自治体の内容を横断で並べて確認でき、
各制度ページには<strong>公式ページへの出典リンク</strong>と<strong>最終確認日</strong>を明記しています。
気になる制度は、必ず出典先の公式ページで最新の条件を確認してください。</p>
<h2>4. 申請期限と必要書類を早めにチェックする</h2>
<p>給付・手当には申請期限があるものが多く、出生・転入・退職などの「事由が発生した日」から
数週間〜数か月以内に手続きが必要なケースもあります。対象になりそうな制度を見つけたら、
早めに申請時期・窓口・必要書類を確認しておくと安心です。</p>
{note}
""")
    page(path="/guide/how-to-find/index.html", title=f"自分が使える給付金・手当の探し方｜くらしの制度ガイド｜{SITE_SHORT}",
         description="自分や家族が対象になる給付金・手当・助成を見つけるための手順を解説。ライフイベントから考え、国と自治体の制度を分け、住んでいる自治体で実際の金額・対象・申請期限を確認する流れを紹介します。",
         canonical="/guide/how-to-find/",
         breadcrumb=[("トップ","/"),("くらしの制度ガイド","/guide/"),("使える制度の探し方",None)], body=htf)
    sitemap_urls.append(("/guide/how-to-find/","0.6"))

    # ── ライフイベント別ガイド ──
    for slug, ev_slug, h1title, short, lead, sections in GUIDES_EV:
        ev_name = EVENTS[ev_slug][0]
        secs_html = "".join(f"<h2>{esc(h)}</h2>\n{p}\n" for h,p in sections)
        rel = (f'<h2>{esc(ev_name)}の制度を自治体で比べる</h2>'
               f'<p>当サイトでは、{esc(ev_name)}に関する制度を掲載している東京都の自治体を件数順・金額順で確認できます。'
               f'お住まいの地域や引っ越し先の候補で、実際にどんな支援があるかを比べてみてください。</p>'
               f'<div class="cmpbox"><strong>あわせて確認する</strong><ul>'
               f'<li><a href="/ranking/{ev_slug}/">{esc(ev_name)}の制度がある自治体をみる {CHEV_R}</a></li>'
               f'<li><a href="/find/">目的・年代から制度がある地域を探す {CHEV_R}</a></li>'
               f'<li><a href="/hikaku/">制度カテゴリごとに自治体を比較する {CHEV_R}</a></li>'
               f'</ul></div>')
        body = wrap(f"""
<span class="badge">{esc(ev_name)}</span>
<h1>{esc(h1title)}</h1>
<p class="lead">{esc(lead)}</p>
{secs_html}{rel}
{note}
""")
        page(path=f"/guide/{slug}/index.html",
             title=f"{h1title}｜くらしの制度ガイド｜{SITE_SHORT}",
             description=clip(f"{h1title}。{lead}", 118),
             canonical=f"/guide/{slug}/",
             breadcrumb=[("トップ","/"),("くらしの制度ガイド","/guide/"),(ev_name,None)], body=body)
        sitemap_urls.append((f"/guide/{slug}/","0.6"))

# ── トップ ──────────────────────────────────────────────────────────────────
def build_home(muni_stats, score, cat_entries=None):
    _tj={"special_ward":"区","city":"市","town":"町","village":"村"}
    _grp={"special_ward":"ku","city":"shi","town":"cho","village":"cho"}
    # 62市区町村を対等に：五十音順の単一グリッド（区/市/町村の階層を廃し、種別は小バッジで表示）
    all62=sorted(muni_stats, key=lambda x: (YOMI.get(x[0]["municipality_name"], x[0]["municipality_name"]), x[1]))
    def grid(rows):
        return '<ul class="mgrid" id="mgrid">'+''.join(
          f'<li data-nm="{esc(m["municipality_name"])}" data-yo="{esc(YOMI.get(m["municipality_name"],""))}" '
          f'data-ro="{s}" data-g="{_grp.get(m["municipality_type"],"cho")}">'
          f'<a href="/area/tokyo/{s}/">{esc(m["municipality_name"])}</a><span>{n}件</span></li>'
          for m,s,n in rows)+'</ul>'
    # 目的・年代の発見カード（トップの主要導線）
    pcards="".join(
      f'<a class="pchip" href="/ranking/{ev}/" style="--pc:{EV_META[ev][2]}">'
      f'<span class="pic">{icon_svg(ev)}</span><span>{esc(EV_META[ev][0])}</span></a>'
      for ev in EV_META)
    amt_sec = amount_rankings_html(cat_entries)
    try:
        _hero_svg = open(os.path.join(ROOT, "docs", "assets", "maps", "tokyo-interactive.svg"), encoding="utf-8").read()
    except OSError:
        _hero_svg = ""
    _map_js=('<script>(function(){var w=document.querySelector(".tokyomap-wrap");if(!w)return;'
             'var t=w.querySelector(".mtip"),s=w.querySelector("svg");if(!s)return;'
             's.addEventListener("pointermove",function(e){var a=e.target.closest("a");'
             'if(a&&a.getAttribute("aria-label")){t.textContent=a.getAttribute("aria-label");t.hidden=false;'
             'var r=w.getBoundingClientRect();t.style.left=(e.clientX-r.left)+"px";t.style.top=(e.clientY-r.top)+"px";}'
             'else{t.hidden=true;}});'
             's.addEventListener("pointerleave",function(){t.hidden=true;});})();</script>')
    hero_map_html = (f'<div class="hero-map"><figure>'
        f'<div class="tokyomap-wrap">{_hero_svg}<span class="mtip" hidden></span></div>'
        f'</figure></div>{_map_js}') if _hero_svg else ""
    body=f"""
<section class="hero" aria-labelledby="hero-title">
<div class="bandin hero-grid">
<div class="hero-main">
<p class="hero-eyebrow">東京都62市区町村の給付・手当・助成</p>
<h1 id="hero-title"><span class="hero-tokyo">東京都</span>で<span class="hero-em">もらえるお金</span>が、<br class="hero-br">住む街ごとにひと目でわかる</h1>
<p class="hero-lead">給付金・手当・助成を東京都62市区町村ごとに整理しました。出典と最終確認日つきなので、引っ越し先選びや制度の申請にそのまま使えます。</p>
<form class="hsearch" role="search" aria-label="市区町村を検索">
<span class="hsearch-ic" aria-hidden="true"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="11" cy="11" r="7"/><path d="m20 20-3.2-3.2"/></svg></span>
<input type="search" id="hsearch" name="q" placeholder="市区町村・制度名で検索（例：世田谷 / 家賃補助 / 産後ケア）" aria-label="市区町村名・制度名で検索" autocomplete="off" role="combobox" aria-expanded="false" aria-controls="hsac" aria-autocomplete="list">
<button type="submit" class="hsearch-btn">検索</button>
<ul class="hsac" id="hsac" role="listbox" aria-label="候補の市区町村・制度" hidden></ul>
</form>
</div>
{hero_map_html}
</div>
</section>
<section class="band band-white">
<div class="bandin">
<h2 class="fh">{ic("compass","hi")}目的・年代から制度がある地域を探す</h2>
{purpose_cards_html(score)}
<p class="fmore"><a href="/find/">{CHEV_R} 目的・年代から探す をすべて見る</a></p>
</div>
</section>
<section class="band band-soft">
<div class="bandin">
{amt_sec}
</div>
</section>
<section class="band band-white" id="area">
<div class="bandin">
<h2 class="fh">{ic("home","hi")}お住まいの市区町村から探す（東京都62市区町村）</h2>
<p class="lead2">23区・多摩地域の市・町村・島しょを区別なく、五十音順で一覧しています。どの市区町村も同じ粒度で制度をまとめています。</p>
<div class="mfilter">
<div class="mchips" role="group" aria-label="種別で絞り込み">
<button type="button" class="mchip on" data-f="all" aria-pressed="true">すべて<b>62</b></button>
<button type="button" class="mchip" data-f="ku" aria-pressed="false">区<b>23</b></button>
<button type="button" class="mchip" data-f="shi" aria-pressed="false">市<b>26</b></button>
<button type="button" class="mchip" data-f="cho" aria-pressed="false">町村・島しょ<b>13</b></button>
</div>
</div>
{grid(all62)}
<p class="mnone" id="mnone" hidden>該当する市区町村が見つかりません。条件を変えてお試しください。</p>
</div>
</section>
<section class="band band-soft">
<div class="bandin">
<h2 class="fh">{ic("bars","hi")}制度ごとに自治体を比べる</h2>
<p class="lead2">児童手当・産後ケア・高齢者紙おむつ・家賃補助など、同じ制度の金額・対象を東京都62市区町村で横断比較できます。</p>
<p class="fmore"><a href="/hikaku/">{CHEV_R} 制度カテゴリ別の自治体比較を見る</a></p>
</div>
</section>
<script>
(function(){{
 var g=document.getElementById('mgrid'),
     none=document.getElementById('mnone'),
     chips=[].slice.call(document.querySelectorAll('.mchip')),
     lis=[].slice.call(g.querySelectorAll('li')),f='all';
 function apply(){{
  var shown=0;
  lis.forEach(function(li){{
   var vis=(f==='all'||li.getAttribute('data-g')===f);
   li.hidden=!vis;if(vis)shown++;
  }});
  none.hidden=shown>0;
 }}
 chips.forEach(function(c){{c.addEventListener('click',function(){{
  f=c.getAttribute('data-f');
  chips.forEach(function(x){{var on=x===c;x.classList.toggle('on',on);x.setAttribute('aria-pressed',on);}});
  apply();
 }});}});
}})();
(function(){{
 var box=document.getElementById('hsearch');if(!box)return;
 var form=box.closest('form'),ac=document.getElementById('hsac'),
     grid=document.getElementById('mgrid');if(!form||!ac||!grid)return;
 var munis=[].slice.call(grid.querySelectorAll('li')).map(function(li){{
  var a=li.querySelector('a'),mt=li.querySelector('.mt');
  return {{nm:li.getAttribute('data-nm')||'',yo:li.getAttribute('data-yo')||'',
          ro:li.getAttribute('data-ro')||'',mt:mt?mt.textContent:'',
          href:a?a.getAttribute('href'):'#'}};
 }});
 var slug2nm={{}};munis.forEach(function(m){{var s=(m.href.match(/\/area\/tokyo\/([^/]+)\//)||[])[1];if(s)slug2nm[s]=m.nm;}});
 var SUGGEST=[{{t:'児童手当',u:'/hikaku/child_teate/'}},{{t:'家賃補助',u:'/hikaku/house_yachin/'}},
  {{t:'子ども・乳幼児医療費助成',u:'/hikaku/child_iryo/'}},{{t:'産後ケア',u:'/hikaku/preg_sango_care/'}},
  {{t:'出産・入学祝金',u:'/hikaku/child_iwai/'}},{{t:'高齢者の紙おむつ助成',u:'/hikaku/eld_omutsu/'}},
  {{t:'補聴器の購入助成',u:'/hikaku/eld_hochoki/'}},{{t:'エアコン設置助成',u:'/hikaku/low_aircon/'}}];
 var idx=null,loading=false,active=-1,rows=[];
 function nz(s){{return (s||'').toLowerCase();}}
 function esc(s){{return (s||'').replace(/[&<>"]/g,function(c){{return {{'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}}[c];}});}}
 function load(){{
  if(idx||loading)return;loading=true;
  fetch('/assets/search-index.json').then(function(r){{return r.json();}}).then(function(d){{
   idx=d;loading=false;if(document.activeElement===box&&box.value.trim())render();
  }}).catch(function(){{loading=false;}});
 }}
 function close(){{ac.hidden=true;ac.innerHTML='';active=-1;rows=[];
  box.setAttribute('aria-expanded','false');box.removeAttribute('aria-activedescendant');}}
 function setActive(i,kbd){{
  active=i;
  rows.forEach(function(r,j){{var on=j===i;r.el.classList.toggle('on',on);
   if(on){{r.el.setAttribute('aria-selected','true');if(kbd)r.el.scrollIntoView({{block:'nearest'}});}}
   else r.el.removeAttribute('aria-selected');}});
  box.setAttribute('aria-activedescendant',i>=0?rows[i].el.id:'');
 }}
 function go(href){{if(href)location.href=href;}}
 function head(t){{var li=document.createElement('li');li.className='hsac-head';li.setAttribute('role','presentation');li.textContent=t;ac.appendChild(li);}}
 function opt(o){{
  var li=document.createElement('li');li.className='hsac-item';li.setAttribute('role','option');li.id='hsac-'+rows.length;
  var b=o.badge?'<em class="hsac-mt">'+esc(o.badge)+'</em>':'';
  var sec=o.sec?'<span class="hsac-sub">'+esc(o.sec)+'</span>':'';
  li.innerHTML=b+'<span class="hsac-nm">'+esc(o.pri)+'</span>'+sec;
  var href=o.href,i=rows.length;
  li.addEventListener('mousedown',function(e){{e.preventDefault();go(href);}});
  li.addEventListener('mouseenter',function(){{setActive(i,false);}});
  ac.appendChild(li);rows.push({{el:li,href:href}});
 }}
 function renderSuggest(){{
  ac.innerHTML='';active=-1;rows=[];
  head('よく検索される制度');
  SUGGEST.forEach(function(s){{opt({{pri:s.t,badge:'比較',href:s.u}});}});
  ac.hidden=false;box.setAttribute('aria-expanded','true');
 }}
 function render(){{
  var t=nz(box.value.trim());ac.innerHTML='';active=-1;rows=[];
  if(!t){{renderSuggest();return;}}
  var mm=[];
  munis.forEach(function(m){{
   var nm=nz(m.nm),yo=nz(m.yo),ro=nz(m.ro),s=-1;
   if(nm.indexOf(t)===0||yo.indexOf(t)===0||ro.indexOf(t)===0)s=0;
   else if(nm.indexOf(t)>=0||yo.indexOf(t)>=0||ro.indexOf(t)>=0)s=1;
   if(s>=0)mm.push({{s:s,m:m}});
  }});
  mm.sort(function(a,b){{return a.s-b.s;}});
  var cc=[];
  if(idx&&idx.c)idx.c.forEach(function(c){{
   var lt=nz(c.t),s=-1;
   if(lt.indexOf(t)===0)s=0;else if(lt.indexOf(t)>=0)s=1;else if(nz(c.k).indexOf(t)>=0)s=2;
   if(s>=0)cc.push({{s:s,c:c}});
  }});
  cc.sort(function(a,b){{return a.s-b.s;}});
  var pp=[];
  if(idx&&idx.p)idx.p.forEach(function(p){{
   var tt=nz(p.t),s=-1;
   if(tt.indexOf(t)===0)s=0;else if(tt.indexOf(t)>=0)s=1;else if(nz(p.d).indexOf(t)>=0)s=3;
   if(s>=0)pp.push({{s:s,p:p}});
  }});
  pp.sort(function(a,b){{return a.s-b.s;}});
  if(mm.length){{head('市区町村');mm.slice(0,5).forEach(function(x){{opt({{pri:x.m.nm,badge:x.m.mt,href:x.m.href}});}});}}
  if(cc.length){{head('制度を自治体で比較');cc.slice(0,4).forEach(function(x){{opt({{pri:x.c.t,sec:x.c.n+'自治体で比較',href:x.c.u}});}});}}
  if(pp.length){{head('制度');pp.slice(0,8).forEach(function(x){{opt({{pri:x.p.t,badge:x.p.y,sec:slug2nm[x.p.s]||'',href:'/area/tokyo/'+x.p.s+'/seido/'+x.p.i+'/'}});}});}}
  if(!rows.length){{
   if(idx){{var li=document.createElement('li');li.className='hsac-none';li.textContent=loading?'読み込み中…':'該当する候補が見つかりません';ac.appendChild(li);ac.hidden=false;box.setAttribute('aria-expanded','true');return;}}
   close();return;
  }}
  ac.hidden=false;box.setAttribute('aria-expanded','true');
 }}
 box.addEventListener('focus',function(){{load();if(box.value.trim())render();else renderSuggest();}});
 box.addEventListener('input',function(){{load();render();}});
 box.addEventListener('keydown',function(e){{
  if(ac.hidden||!rows.length)return;
  if(e.key==='ArrowDown'){{e.preventDefault();setActive((active+1)%rows.length,true);}}
  else if(e.key==='ArrowUp'){{e.preventDefault();setActive((active-1+rows.length)%rows.length,true);}}
  else if(e.key==='Enter'){{if(active>=0){{e.preventDefault();go(rows[active].href);}}}}
  else if(e.key==='Escape'){{close();}}
 }});
 form.addEventListener('submit',function(e){{
  e.preventDefault();
  if(!box.value.trim()){{if(active>=0&&rows[active])go(rows[active].href);return;}}
  if(rows.length){{go(active>=0?rows[active].href:rows[0].href);return;}}
  var area=document.getElementById('area');
  if(area)area.scrollIntoView({{behavior:'smooth'}});
 }});
 document.addEventListener('click',function(e){{if(!form.contains(e.target))close();}});
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
    search_progs=[]
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
            summ = re.sub(r"\s+"," ",(p["plain_summary"] or p["summary"] or "")).strip()
            search_progs.append({"s":slug,"i":p["id"],"t":p["title"],
                                 "y":PT_JA.get(p["program_type"],"制度"),"d":clip(summ,64)})
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
    build_guides()
    build_home(muni_stats, score, cat_entries)
    write_search_index(search_progs, cat_counts)
    write_sitemap(); write_robots(); write_ads_txt(); write_css()
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

def write_ads_txt():
    # AdSense の所有権証明。ca-pub-XXXX から pub-XXXX を取り出して DIRECT 行を出力。
    if not ADSENSE_CLIENT:
        return
    pub = ADSENSE_CLIENT.replace("ca-", "", 1) if ADSENSE_CLIENT.startswith("ca-") else ADSENSE_CLIENT
    write("ads.txt", f"google.com, {pub}, DIRECT, f08c47fec0942fa0\n")

def write_search_index(search_progs, cat_counts):
    """トップページの横断検索用インデックス（制度名・内容＋比較カテゴリ）。"""
    cats=[]
    for cid,label,ev,inc,exc in TAXONOMY:
        if cat_counts.get(cid,0) < 1:
            continue
        # 正規表現メタ文字を含む収集キーワードは検索語として使わない
        kws=[k for k in inc if not re.search(r"[.*+?{}()\[\]\\|]", k)]
        cats.append({"u":f"/hikaku/{cid}/","t":label,
                     "n":cat_counts.get(cid,0),"k":" ".join(kws)})
    data={"c":cats,"p":search_progs}
    write("assets/search-index.json",
          json.dumps(data, ensure_ascii=False, separators=(",",":")))

def write_css():
    write("assets/style.css", CSS)

CSS = """/* ── Design tokens ── */
:root{
  /* 文字色は2階層のみ: --fg（本文・見出し）/ --muted（補助）。中間グレーは使わない */
  --fg:#1a2233;
  --fg-2:var(--fg); /* 互換エイリアス（旧中間色は本文色に統合） */
  --muted:#5b6577;
  --line:#e5e8ef;
  --bg:#fff;
  --accent:#1558d6;
  --soft:#f5f7fb;
  --badge:#eaf1fe;
  --track:#e8edf2;
  --warn-bg:#fff7e6;
  --warn-line:#ffe1a8;
  --warn-fg:#7a5a00;
  --pc-birth:#e87ba4;
  --pc-child:#2a78d6;
  --pc-house:#1baf7a;
  --pc-job:#eda100;
  --pc-senior:#eb6834;
  --radius:6px;
  --radius-sm:4px;
  /* サイズ役割: base本文 / sm補助UI / xsラベル / h2·h1·display見出し（mdはsm同義） */
  --fs-xs:.78rem;
  --fs-sm:.875rem;
  --fs-md:.875rem;
  --fs-lg:1rem;
  --fs-h3:1rem;
  --fs-h2:1.15rem;
  --fs-h1:1.5rem;
  --fs-display:clamp(1.85rem,4.2vw,2.4rem);
  --content-width:1080px;
  --fw-normal:400;
  --fw-semi:600;
  --fw-bold:700;
  --fw-black:800;
  /* 市区町村名の共通タイポ（一覧・ランキング・比較表などで揃える） */
  --mn-fs:var(--fs-md);
  --mn-fw:var(--fw-semi);
}
*{box-sizing:border-box}html{-webkit-text-size-adjust:100%;overflow-x:clip}
body{margin:0;font-family:"Noto Sans JP",system-ui,-apple-system,"Hiragino Kaku Gothic ProN",sans-serif;color:var(--fg);background:var(--bg);line-height:1.7;font-weight:var(--fw-normal);font-size:var(--fs-lg)}
a{color:var(--fg);text-decoration:none}a:hover{color:var(--accent);text-decoration:underline}
header.site{position:sticky;top:0;z-index:30;background:rgba(255,255,255,.96);backdrop-filter:saturate(1.2) blur(6px);padding:.55rem 1.1rem;border-bottom:1px solid var(--line)}
.hbar{max-width:var(--content-width);margin:0 auto;display:flex;align-items:center;gap:.35rem 1rem;flex-wrap:wrap}
.brand{font-weight:var(--fw-black);font-size:var(--fs-h2);color:var(--fg);display:inline-flex;align-items:center;gap:.45rem;line-height:1.2}
.brand:hover{text-decoration:none}
.brand-mark{width:1.45rem;height:1.45rem;flex:none;display:block}
.gnav{display:flex;gap:.1rem;margin-left:auto;flex-wrap:wrap}
.gnav a{color:var(--fg);font-weight:var(--fw-semi);font-size:var(--fs-md);padding:.34rem .6rem;border-radius:var(--radius-sm)}
.gnav a:hover{background:var(--soft);text-decoration:none}
@media(max-width:520px){.gnav a{padding:.3rem .44rem;font-size:var(--fs-sm)}.brand{font-size:var(--fs-lg)}.brand-mark{width:1.3rem;height:1.3rem}header.site{padding:.5rem .8rem}}
@media(max-width:360px){.gnav{gap:0}.gnav a{padding:.3rem .34rem}}
:target{scroll-margin-top:60px}
main{max-width:var(--content-width);margin:0 auto;padding:1.1rem 1.1rem 3rem}
.crumbs{font-size:var(--fs-sm);color:var(--muted);margin:.2rem 0 1rem}
.crumbs a{color:var(--muted)}
h1{font-size:var(--fs-h1);line-height:1.35;margin:.2rem 0 .7rem;font-weight:var(--fw-bold)}
h2{font-size:var(--fs-h2);margin:1.8rem 0 .6rem;padding-bottom:.3rem;border-bottom:2px solid var(--soft);font-weight:var(--fw-bold)}
h3{font-size:var(--fs-h3);font-weight:var(--fw-bold)}
.lead{color:var(--fg);margin:.4rem 0 1rem;font-size:var(--fs-lg)}
.meta{font-size:var(--fs-sm);color:var(--muted);margin:.2rem 0 1rem}
.badge,.tag,.pt,.cnt{display:inline-block}
.badge{background:var(--badge);color:var(--accent);font-size:var(--fs-xs);font-weight:var(--fw-bold);padding:.15rem .55rem;border-radius:999px}
.notice{background:var(--warn-bg);border:1px solid var(--warn-line);color:var(--warn-fg);padding:.6rem .8rem;border-radius:var(--radius-sm);font-size:var(--fs-sm)}
.trustbar{display:flex;flex-wrap:wrap;gap:.45rem;margin:.1rem 0 1rem}
.tchip{display:inline-flex;align-items:center;gap:.32rem;font-size:var(--fs-sm);font-weight:var(--fw-normal);color:var(--muted);background:var(--soft);border:1px solid var(--line);border-radius:999px;padding:.26rem .7rem}
.tci{width:1em;height:1em;color:var(--pc-house);flex:none}
.offbtn{display:inline-flex;align-items:center;flex-wrap:wrap;gap:.1rem .45rem;font-weight:var(--fw-semi);color:var(--accent);text-decoration:none;line-height:1.5}
.offbtn:hover{text-decoration:underline}
.offbtn .ic{width:1.05em;height:1.05em;vertical-align:-.16em}
.offbtn-host{font-size:var(--fs-xs);font-weight:var(--fw-normal);color:var(--muted);word-break:break-all}
.offlead{color:var(--fg);margin:.2rem 0 .85rem;font-size:var(--fs-lg)}
.offnote{font-size:var(--fs-sm);color:var(--muted);margin:.6rem 0 0;line-height:1.65}
.official{font-size:var(--fs-lg);margin:.2rem 0 .4rem}
dl.facts{margin:.4rem 0;border:1px solid var(--line);border-radius:var(--radius);overflow:hidden}
.fact{display:grid;grid-template-columns:8.5rem 1fr;border-top:1px solid var(--line)}
.fact:first-child{border-top:0}
.fact dt{background:var(--soft);font-weight:var(--fw-bold);font-size:var(--fs-lg);padding:.7rem .8rem;margin:0}
.fact dd{margin:0;padding:.7rem .8rem}
.fact dd .offlink{word-break:break-all}
.src{font-size:var(--fs-xs);color:var(--muted);white-space:nowrap;margin-left:.3rem}
@media(max-width:560px){.fact{grid-template-columns:1fr}.fact dt{border-bottom:1px solid var(--line)}}
.hi{width:1.08em;height:1.08em;vertical-align:-.16em;margin-right:.42rem;color:var(--accent);flex:none}
.fi{width:1em;height:1em;vertical-align:-.13em;margin-right:.36rem;color:var(--muted);flex:none}
.fact dt .fi{color:color-mix(in srgb,var(--accent) 55%,var(--muted))}
/* FAQ 表形式（質問｜回答）。淡色帯の上でも埋もれないよう白背景＋濃いめの罫線 */
table.faqtable{width:100%;border-collapse:collapse;font-size:var(--fs-lg);margin:.4rem 0 1rem;background:var(--bg)}
table.faqtable th,table.faqtable td{border:1px solid var(--line);padding:.6rem .75rem;text-align:left;vertical-align:top;background:var(--bg)}
table.faqtable thead th{background:var(--badge);font-size:var(--fs-sm);white-space:nowrap;color:var(--fg)}
table.faqtable tbody th{width:34%;font-weight:var(--fw-bold);color:var(--fg);background:var(--bg)}
table.faqtable tbody th::before{content:"Q. ";color:var(--accent);font-weight:var(--fw-black)}
table.faqtable tbody td{color:var(--fg);line-height:1.7}
@media(max-width:560px){table.faqtable thead{display:none}table.faqtable tbody th,table.faqtable tbody td{display:block;width:auto}table.faqtable tbody th{border-bottom:0;background:var(--soft)}table.faqtable tbody td{border-top:0}}
/* 行全体クリック可能な表 */
tr[data-href]{cursor:pointer}
table.cmp tbody tr[data-href]:hover,table.ptable tbody tr[data-href]:hover{background:var(--soft)}
/* クリックで並び替えできる見出し */
th.sortable{cursor:pointer;white-space:nowrap}
th.sortable button{font:inherit;color:inherit;background:none;border:0;padding:0;margin:0;cursor:pointer;display:inline-flex;align-items:center;gap:.25rem}
th.sortable:hover button{color:var(--accent)}
th.sortable .sarr::after{content:"↕";opacity:.45;font-size:.9em}
th.sortable[aria-sort="ascending"] .sarr::after{content:"▲";opacity:1;color:var(--accent)}
th.sortable[aria-sort="descending"] .sarr::after{content:"▼";opacity:1;color:var(--accent)}
ul.proglist{list-style:none;padding:0;margin:.3rem 0}
ul.proglist li{padding:.55rem .2rem;border-bottom:1px solid var(--line);display:flex;justify-content:space-between;gap:.6rem;align-items:baseline}
ul.proglist .pt{font-size:var(--fs-xs);color:var(--muted)}
.ev h2 .cnt{font-size:var(--fs-sm);color:#fff;background:var(--accent);border-radius:999px;padding:.05rem .5rem;margin-left:.4rem;vertical-align:middle}
.ev h2 .csum{font-size:var(--fs-xs);color:var(--pc,var(--accent));background:color-mix(in srgb,var(--pc,var(--accent)) 12%,#fff);
  border:1px solid color-mix(in srgb,var(--pc,var(--accent)) 28%,#fff);border-radius:999px;padding:.05rem .5rem;margin-left:.3rem;vertical-align:middle;font-weight:var(--fw-bold)}
table.cmp.rank td.yen{font-variant-numeric:tabular-nums;white-space:nowrap;color:var(--fg)}
.more,.fmore,.armore,.fig-more,.evlinks,.backtop{display:inline-block;margin:.5rem 0 1rem;font-size:var(--fs-sm)}
.fmore{display:block;margin:.7rem 0 0}
.armore{display:block;margin:.45rem 0 0}
.fig-more{display:block;margin:.55rem 0 0}
.evlinks{display:block;margin:.35rem 0 .1rem}
.backtop{display:block;margin-top:1.6rem}
ul.mgrid{list-style:none;padding:0;margin:.4rem 0 1rem;display:grid;grid-template-columns:repeat(auto-fill,minmax(150px,1fr));gap:.5rem}
ul.mgrid li{border:1px solid var(--line);border-radius:var(--radius);padding:.5rem .7rem;display:flex;justify-content:space-between;align-items:baseline}
ul.mgrid li span{font-size:var(--fs-xs);color:var(--muted)}
ul.mgrid li a{font-size:var(--mn-fs);font-weight:var(--mn-fw);color:var(--fg)}
em.mt{font-style:normal;font-size:var(--fs-xs);color:var(--muted);border:1px solid var(--line);border-radius:5px;padding:0 .28rem;line-height:1.5;flex:none}
p.lead2{color:var(--muted);font-size:var(--fs-sm);margin:.1rem 0 .6rem}
.mfilter{margin:.2rem 0 .7rem}
.mchips{display:flex;flex-wrap:wrap;gap:.4rem;margin-top:.15rem}
.mchip{font:inherit;font-size:var(--fs-sm);font-weight:var(--fw-semi);cursor:pointer;border:1px solid var(--line);background:transparent;color:var(--muted);border-radius:999px;padding:.28rem .7rem;display:inline-flex;align-items:center;gap:.3rem}
.mchip b{font-weight:var(--fw-semi);font-size:var(--fs-xs);opacity:.7}
.mchip.on{background:var(--accent);border-color:var(--accent);color:#fff}
.mchip.on b{opacity:.85}
ul.mgrid li[hidden]{display:none}
p.mnone{color:var(--muted);font-size:var(--fs-sm);padding:.6rem 0}
/* ── 自治体：制度の全一覧（検索・絞り込み・並び替え）── */
.plist-sec{margin:1.4rem 0}
.plist-ctrl{margin:.5rem 0 .5rem}
#psearch{width:100%;box-sizing:border-box;padding:.6rem .8rem;font-size:var(--fs-lg);border:1px solid var(--line);border-radius:var(--radius);background:var(--bg);color:inherit}
#psearch:focus{outline:2px solid var(--accent);outline-offset:1px}
.plist-row{display:flex;flex-wrap:wrap;gap:.5rem .8rem;align-items:center;justify-content:space-between;margin-top:.55rem}
.pchips2{display:flex;flex-wrap:wrap;gap:.4rem}
.pchip2{font:inherit;font-size:var(--fs-sm);font-weight:var(--fw-semi);cursor:pointer;border:1px solid var(--line);background:transparent;color:var(--muted);border-radius:999px;padding:.28rem .7rem;display:inline-flex;align-items:center;gap:.3rem}
.pchip2 b{font-weight:var(--fw-semi);font-size:var(--fs-xs);opacity:.7}
.pchip2.on{background:var(--pc,var(--accent));border-color:var(--pc,var(--accent));color:#fff}
.pchip2.on b{opacity:.85}
.psort{font-size:var(--fs-sm);color:var(--muted);display:inline-flex;align-items:center;gap:.35rem;white-space:nowrap}
.psort select{font:inherit;font-size:var(--fs-sm);padding:.32rem .5rem;border:1px solid var(--line);border-radius:var(--radius-sm);background:var(--bg);color:var(--fg);cursor:pointer}
.area-head{display:flex;gap:1.3rem;align-items:flex-start;flex-wrap:wrap;margin:.2rem 0 .8rem}
.area-head-main{flex:1 1 300px;min-width:0}
.area-head-main>h1{margin-top:.2rem}
.area-head-main>:last-child{margin-bottom:0}
.areamap{margin:.4rem 0 1.1rem;border:1px solid var(--line);border-radius:var(--radius);background:var(--soft);padding:.5rem}
.area-head .areamap{flex:0 1 470px;margin:0;align-self:flex-start}
.areamap img{display:block;width:100%;height:auto;max-width:640px;margin:0 auto}
.area-head .areamap img{max-width:100%}
.areamap figcaption{text-align:center;font-size:var(--fs-xs);color:var(--muted);margin-top:.25rem}
.progphoto,.evphoto{margin:.4rem 0 1rem;border-radius:var(--radius);overflow:hidden;border:1px solid var(--line);background:var(--soft)}
.area-head .progphoto{flex:0 1 420px;margin:0;align-self:flex-start}
.progphoto img,.evphoto img{display:block;width:100%;height:auto;aspect-ratio:16/10;object-fit:cover}
.evphoto{max-width:720px}
@media(max-width:680px){.area-head{gap:.5rem}.area-head .areamap,.area-head .progphoto{flex-basis:100%}}
table.ptable{width:100%;border-collapse:collapse;font-size:var(--fs-lg);margin:.5rem 0}
table.ptable thead th{text-align:left;font-size:var(--fs-xs);color:var(--muted);font-weight:var(--fw-bold);background:var(--soft);border-bottom:1px solid var(--line);padding:.55rem .55rem;white-space:nowrap}
table.ptable thead th.c-amt{text-align:right}
table.ptable thead th.c-cat{text-align:center}
table.ptable td{padding:.55rem .55rem;border-bottom:1px solid var(--line);vertical-align:baseline}
table.ptable tr[hidden]{display:none}
table.ptable td.c-name a{font-weight:var(--fw-semi)}
table.ptable .c-amt{text-align:right;white-space:nowrap;font-variant-numeric:tabular-nums}
table.ptable td.c-amt{font-weight:var(--fw-bold);color:var(--fg)}
table.ptable td.c-amt.na{color:var(--muted);font-weight:var(--fw-normal)}
table.ptable .c-cat,table.ptable .c-type{white-space:nowrap;width:1%}
table.ptable td.c-cat{text-align:center}
table.ptable td.c-type{color:var(--muted);font-size:var(--fs-sm)}
.ptag{display:inline-block;font-size:var(--fs-xs);color:#fff;background:var(--pc,var(--accent));border-radius:999px;padding:.1rem .6rem;white-space:nowrap}
.plist-purpose{font-size:var(--fs-sm);color:var(--muted);margin:.7rem 0 0;line-height:2}
.plist-purpose a{margin-right:.7rem;white-space:nowrap}
p.pnone{color:var(--muted);font-size:var(--fs-sm);padding:.6rem 0}
@media(max-width:560px){table.ptable td.c-name{min-width:8.5rem}}
footer.site{border-top:1px solid var(--line);padding:1.2rem 1.1rem;color:var(--muted);font-size:var(--fs-sm);max-width:var(--content-width);margin:0 auto}
footer.site a{color:var(--muted)}
.cmpbox{background:var(--soft);border:1px solid var(--line);border-radius:var(--radius);padding:.9rem 1rem;margin:1.2rem 0}
.cmpbox strong{display:block;margin-bottom:.35rem;font-size:var(--fs-h2);font-weight:var(--fw-bold);color:var(--fg)}
.cmpbox ul{margin:.3rem 0 0;padding-left:1.1rem}
.cmpbox p{margin:.3rem 0;color:var(--muted);font-size:var(--fs-sm)}
.cmpbox p a{font-size:var(--fs-sm)}
.tablewrap{overflow-x:auto;margin:.6rem 0}
table.cmp{border-collapse:collapse;width:100%;font-size:var(--fs-lg)}
table.cmp th,table.cmp td{border:1px solid var(--line);padding:.5rem .6rem;text-align:left;vertical-align:top}
table.cmp thead th{background:var(--soft);position:sticky;top:0;white-space:nowrap}
table.cmp td.mn{white-space:nowrap;font-size:var(--mn-fs);font-weight:var(--mn-fw)}
table.cmp td.mn a{font-size:var(--mn-fs);font-weight:var(--mn-fw);color:var(--fg)}
table.cmp td.dt{white-space:nowrap;color:var(--muted);font-size:var(--fs-sm)}
table.cmp.rank th.rk,table.cmp.rank td.rk{width:3.2rem;min-width:3.2rem;text-align:center;white-space:nowrap;color:var(--muted);font-variant-numeric:tabular-nums}
table.cmp.rank th.mn,table.cmp.rank td.mn{white-space:nowrap}
.na{color:var(--muted);font-size:.85em}
.miss{font-size:var(--fs-sm);color:var(--muted);background:var(--soft);border:1px solid var(--line);border-radius:var(--radius-sm);padding:.6rem .8rem}
.note{font-size:var(--fs-sm);color:var(--muted)}
ul.cmplist{list-style:none;padding:0;margin:.3rem 0}
ul.cmplist li{padding:.5rem .2rem;border-bottom:1px solid var(--line);display:flex;justify-content:space-between;align-items:baseline;gap:.6rem}
ul.cmplist .cnt2{font-size:var(--fs-xs);color:var(--muted);white-space:nowrap}
.cmpsec{margin:1.4rem 0 1.1rem}
.cmpsec-h{display:flex;align-items:center;gap:.5rem;margin:.2rem 0 .45rem}
.cmpsec-h .pic{flex:0 0 auto;display:inline-flex;color:#fff;background:var(--pc);border-radius:var(--radius-sm);padding:5px}
.cmpsec-h .pic .ev-ic{width:15px;height:15px}
.homeguide{margin:1.9rem 0}
ul.guidegrid{display:grid;grid-template-columns:repeat(auto-fill,minmax(210px,1fr));gap:.55rem;margin:.6rem 0}
ul.guidegrid li{display:block;border:1px solid var(--line);border-radius:10px;padding:.7rem .8rem}
ul.guidegrid li a{display:block;font-weight:600;text-decoration:none}
ul.guidegrid .pdesc{display:block;font-size:var(--fs-sm);color:var(--muted);margin-top:.2rem;font-weight:400}
.fnav{margin:0 0 .7rem;line-height:2}
.fnav a{color:var(--muted)}
footer .copy{margin:.3rem 0 0}
.doc h2{font-size:var(--fs-h2)}
.doc .lead{margin-bottom:1rem}
ul.plainlist{margin:.3rem 0 .3rem 1.1rem;padding:0}
ul.plainlist li{margin:.2rem 0}

/* ── ライフイベント・アクセント ── */
.badge[style*="--pc"]{background:color-mix(in srgb,var(--pc) 16%,#fff);color:color-mix(in srgb,var(--pc) 72%,#111)}
.ev-ic{width:22px;height:22px;display:block}
.chev{width:.72em;height:.72em;vertical-align:-.08em;display:inline-block;flex:0 0 auto}
.parrow{display:inline-flex}.parrow .chev{width:1.05em;height:1.05em}

/* ── SVGグラフ ── */
.chartcard{border:1px solid var(--line);border-radius:var(--radius);padding:.7rem .8rem .4rem;margin:.6rem 0;--pc:var(--accent)}
.chartcard .rsort{margin:0 0 .55rem}
.chartcard .mchip.on{background:var(--pc,var(--accent));border-color:var(--pc,var(--accent));color:#fff}
.chart{width:100%;max-width:640px;height:auto;display:block;font-family:"Noto Sans JP",system-ui,-apple-system,"Hiragino Kaku Gothic ProN",sans-serif}
.chart .c-track{fill:var(--track)}
.chart .c-bar{fill:var(--pc)}
.chart .c-avg{stroke:var(--muted);stroke-width:2;stroke-dasharray:2 2}
.chart .c-lbl{fill:var(--fg);font-size:var(--mn-fs);font-weight:var(--mn-fw);font-family:inherit}
.chart .c-val{fill:var(--muted);font-size:var(--fs-sm);font-weight:var(--fw-semi);font-variant-numeric:tabular-nums;font-family:inherit}
.cmpchart{margin:1rem 0 1.2rem;padding:.85rem 1rem .7rem;border:1px solid var(--line);border-left:4px solid var(--pc,var(--accent));border-radius:var(--radius);background:var(--bg)}
.cmpchart figcaption{font-weight:var(--fw-bold);font-size:var(--fs-md);margin:0 0 .5rem;color:var(--fg)}
.cmpchart .chart{max-width:640px}
.cmpchart .chart .c-val{fill:var(--fg);font-weight:var(--fw-semi)}
.cmpchart .c-cap{font-size:var(--fs-xs);color:var(--muted);margin:.5rem 0 0;line-height:1.6}
.covchart{margin:1rem 0 1.2rem;padding:.85rem 1rem .7rem;border:1px solid var(--line);border-left:4px solid var(--pc,var(--accent));border-radius:var(--radius);background:var(--bg)}
.covchart figcaption{font-weight:var(--fw-bold);font-size:var(--fs-md);margin:0 0 .6rem;color:var(--fg)}
.covbars{list-style:none;margin:0;padding:0;display:grid;gap:.5rem;max-width:640px}
.covbars li{display:grid;grid-template-columns:minmax(9.5em,15em) 1fr auto;align-items:center;gap:.6rem}
.covbars .cl{font-size:var(--fs-sm);color:var(--muted)}
.covbars .cbar{height:.7rem;background:var(--track);border-radius:999px;overflow:hidden}
.covbars .cfill{display:block;height:100%;background:var(--pc,var(--accent));border-radius:999px}
.covbars .cn{font-size:var(--fs-sm);font-weight:var(--fw-semi);color:var(--fg);white-space:nowrap;font-variant-numeric:tabular-nums}
.covbars .cn small{color:var(--muted);font-weight:var(--fw-normal)}
.covchart .c-cap{font-size:var(--fs-xs);color:var(--muted);margin:.6rem 0 0;line-height:1.6}
@media(max-width:560px){.covbars li{grid-template-columns:1fr auto;grid-template-areas:"l n" "b b";row-gap:.2rem}.covbars .cl{grid-area:l}.covbars .cn{grid-area:n}.covbars .cbar{grid-area:b}}
.cap{font-size:var(--fs-xs);color:var(--muted);margin:.35rem 0 .2rem}
.profile{margin:1.2rem 0 1.4rem}
.profile .strong{margin:.2rem 0 .3rem}
.profile .strong b{color:var(--accent)}

/* ── トップ：ヒーロー ── */
/* 全幅の背景帯（中身は中央寄せ）。トップ・詳細のセクション区切りに使用 */
.band{width:100vw;margin-left:calc(50% - 50vw)}
.bandin{max-width:var(--content-width);margin:0 auto;padding:2rem 1.1rem}
.bandin>:first-child{margin-top:0}
.bandin>:last-child{margin-bottom:0}
.band-white{background:var(--bg)}
.band-soft{background:var(--soft)}
.band-tint{background:var(--badge)}
.hero{width:100vw;margin-left:calc(50% - 50vw);margin-top:-1.1rem;position:relative;
  background:radial-gradient(circle at 88% -20%,color-mix(in srgb,var(--accent) 12%,transparent) 0%,transparent 45%),linear-gradient(155deg,var(--badge) 0%,var(--soft) 48%,var(--bg) 100%);
  border-bottom:1px solid var(--line)}
.hero .bandin{padding-top:4.4rem;padding-bottom:4rem}
.hero-eyebrow{margin:0 0 .55rem;font-size:var(--fs-sm);font-weight:var(--fw-bold);letter-spacing:.04em;
  color:var(--accent);position:relative}
.hero h1{font-size:var(--fs-display);line-height:1.3;margin:0 0 .75rem;font-weight:var(--fw-black);
  letter-spacing:-.02em;position:relative}
.hero-tokyo{color:var(--accent)}
.hero-em{color:var(--fg);background:linear-gradient(transparent 58%,color-mix(in srgb,var(--accent) 22%,transparent) 58%);padding:0 .06em;border-radius:2px}
.hero-br{display:none}
.hero-lead{margin:0 0 1.2rem;font-size:var(--fs-lg);color:var(--fg);line-height:1.75;max-width:40em;position:relative}
.hero-grid{display:flex;gap:2rem;align-items:center}
.hero-main{flex:1 1 460px;min-width:0}
.hero-map{flex:0 1 400px;min-width:0}
.hero-map figure{margin:0}
.hero-map .tokyomap{width:100%;height:auto;display:block;background:#fff;border:1px solid var(--line);border-radius:var(--radius)}
.tokyomap-wrap{position:relative;line-height:0}
.mtip{position:absolute;transform:translate(-50%,-140%);background:var(--fg);color:#fff;font-size:var(--fs-sm);font-weight:var(--fw-bold);padding:.18rem .5rem;border-radius:var(--radius-sm);white-space:nowrap;pointer-events:none;z-index:3;line-height:1.35}
@media(max-width:820px){.hero-grid{flex-direction:column;align-items:stretch;gap:1.4rem}.hero-main,.hero-map{flex:0 0 auto}.hero-map{max-width:520px;margin:0 auto;width:100%}}
.provnote{margin:1.3rem 0 0;font-size:var(--fs-sm);color:var(--muted);background:var(--soft);border:1px solid var(--line);border-left:3px solid var(--track);padding:.55rem .75rem;border-radius:var(--radius-sm);line-height:1.65}
.hero-stats{display:flex;flex-wrap:wrap;gap:.4rem;margin:0 0 1.15rem;position:relative}
.hero-stat{display:inline-flex;align-items:baseline;gap:.2rem;background:var(--bg);border:1px solid var(--line);
  border-radius:999px;padding:.28rem .7rem;font-size:var(--fs-sm);color:var(--muted);font-weight:var(--fw-semi)}
.hero-stat strong{color:var(--fg);font-size:var(--fs-lg);font-weight:var(--fw-black);font-variant-numeric:tabular-nums}
.hero-cta{display:flex;flex-wrap:wrap;gap:.5rem;position:relative}
.hero-btn{display:inline-flex;align-items:center;justify-content:center;font:inherit;font-weight:var(--fw-bold);
  font-size:var(--fs-md);padding:.58rem 1rem;border-radius:var(--radius-sm);border:1px solid var(--line);background:var(--bg);color:var(--fg);
  text-decoration:none;transition:background .15s,border-color .15s}
.hero-btn:hover{text-decoration:none;background:var(--soft);border-color:color-mix(in srgb,var(--accent) 35%,var(--line))}
.hero-btn.primary{background:var(--accent);border-color:var(--accent);color:#fff}
.hero-btn.primary:hover{background:color-mix(in srgb,var(--accent) 88%,#000);border-color:color-mix(in srgb,var(--accent) 88%,#000);color:#fff}
.hero-btn.ghost{background:transparent}
@media(min-width:640px){.hero-br{display:inline}}
@media(max-width:520px){.hero{padding:1.7rem 1rem 1.6rem}.hero-cta .hero-btn{flex:1 1 calc(50% - .3rem);min-width:0}.hero-cta .hero-btn.ghost{flex-basis:100%}}
.hsearch{position:relative;display:flex;align-items:stretch;gap:.4rem;margin:0 0 1.15rem;max-width:34em}
.hsearch-ic{position:absolute;left:.75rem;top:50%;transform:translateY(-50%);color:var(--muted);display:inline-flex;pointer-events:none}
.hsearch-ic svg{width:20px;height:20px}
#hsearch{flex:1 1 auto;min-width:0;box-sizing:border-box;padding:.7rem .8rem .7rem 2.5rem;font-size:var(--fs-lg);
  border:1px solid var(--line);border-radius:var(--radius);background:var(--bg);color:inherit}
#hsearch:focus{outline:2px solid var(--accent);outline-offset:1px}
.hsearch-btn{flex:0 0 auto;font:inherit;font-weight:var(--fw-bold);font-size:var(--fs-md);cursor:pointer;
  padding:.5rem 1.1rem;border-radius:var(--radius);border:1px solid var(--accent);background:var(--accent);color:#fff;transition:background .15s,border-color .15s}
.hsearch-btn:hover{background:color-mix(in srgb,var(--accent) 88%,#000);border-color:color-mix(in srgb,var(--accent) 88%,#000)}
.hsac{position:absolute;z-index:20;top:calc(100% + .3rem);left:0;right:0;margin:0;padding:.25rem;list-style:none;
  background:var(--bg);border:1px solid var(--line);border-radius:var(--radius);box-shadow:0 8px 24px rgba(0,0,0,.12);
  max-height:min(72vh,440px);overflow:auto}
.hsac-head{padding:.45rem .6rem .2rem;font-size:var(--fs-xs);font-weight:var(--fw-bold);color:var(--muted);letter-spacing:.02em}
.hsac-head:not(:first-child){margin-top:.15rem;border-top:1px solid var(--line);padding-top:.5rem}
.hsac-item{display:flex;align-items:center;gap:.45rem;padding:.5rem .6rem;border-radius:var(--radius-sm);cursor:pointer;font-size:var(--fs-md)}
.hsac-item.on{background:var(--soft)}
.hsac-nm{flex:1 1 auto;min-width:0;font-weight:var(--fw-semi);color:var(--fg);overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.hsac-sub{flex:none;padding-left:.4rem;font-size:var(--fs-xs);color:var(--muted);white-space:nowrap}
.hsac-none{padding:.6rem;font-size:var(--fs-sm);color:var(--muted)}
.hsac-mt{font-style:normal;font-size:var(--fs-xs);color:var(--muted);border:1px solid var(--line);border-radius:5px;padding:0 .28rem;line-height:1.5;flex:none}
@media(max-width:520px){.hsearch{max-width:none}.hsearch-btn{padding:.5rem .8rem}}

/* ── 目的・年代の発見 ── */
/* トップの各セクションを同一の余白・背景（白）・見出し様式に統一 */
.hsec{margin:1.9rem 0}
.hsec:first-of-type{margin-top:1.2rem}
.finder{margin:1.9rem 0}
.fh{font-size:var(--fs-h2);margin:.1rem 0 .7rem;border:0;padding:0;font-weight:var(--fw-bold)}
.pchips{display:flex;flex-wrap:wrap;gap:.5rem}
.pchip{display:inline-flex;align-items:center;gap:.4rem;border:1px solid var(--line);background:var(--bg);border-radius:999px;padding:.4rem .8rem .4rem .55rem;font-size:var(--fs-md);font-weight:var(--fw-semi);color:var(--fg)}
.pchip .pic{display:inline-flex;color:#fff;background:var(--pc);border-radius:50%;padding:4px}
.pchip .pic .ev-ic{width:16px;height:16px}
.pchip:hover{border-color:var(--pc);text-decoration:none}
.pgrid{display:grid;grid-template-columns:repeat(auto-fill,minmax(260px,1fr));gap:.7rem;margin:.6rem 0 1rem}
.pcard{display:flex;flex-wrap:wrap;align-items:flex-start;gap:.55rem;border:1px solid var(--line);border-left:4px solid var(--pc);border-radius:var(--radius);padding:0;overflow:hidden;color:var(--fg);background:var(--bg)}
.pcard:hover{background:color-mix(in srgb,var(--pc) 7%,#fff);text-decoration:none}
.pcard .pimg{flex:1 1 100%;display:block;aspect-ratio:16/10;overflow:hidden;background:var(--soft)}
.pcard .pimg img{display:block;width:100%;height:100%;object-fit:cover}
.pcard .ptxt{display:flex;flex-direction:column;min-width:0;flex:1 1 auto;padding:.7rem .2rem .75rem .85rem}
.pcard .ptitle{display:inline-flex;align-items:center;gap:.45rem;min-width:0}
.pcard .pic{flex:0 0 auto;display:inline-flex;color:#fff;background:var(--pc);border-radius:var(--radius-sm);padding:5px}
.pcard .pic .ev-ic{width:15px;height:15px}
.pcard .ptxt strong{font-size:var(--fs-lg);font-weight:var(--fw-bold);line-height:1.35}
.pcard .pdesc{font-size:var(--fs-sm);color:var(--muted);margin-top:.2rem}
.pcard .ptop{font-size:var(--fs-xs);color:var(--pc);font-weight:var(--fw-bold);margin-top:.25rem}
.pcard .parrow{margin-left:auto;margin-top:.15rem;margin-right:.75rem;align-self:center;color:var(--pc);font-weight:var(--fw-bold);flex:0 0 auto}
table.cmp.rank tr.top3 td.rk{color:var(--accent);font-weight:var(--fw-black)}
table.cmp.rank tr.top3 td.mn a{font-weight:var(--mn-fw)}

/* ── トップ：金額ランキング ── */
.amtrank{margin:1.9rem 0}
.amtrank .fh{margin:.1rem 0 .35rem}
.amtrank .lead2{margin:.15rem 0 .35rem}
.archips{margin:.45rem 0 .1rem}
.archip.on{background:var(--pc,var(--accent));border-color:var(--pc,var(--accent));color:#fff}
.arpanel{margin:0}
.argrid{display:grid;grid-template-columns:repeat(auto-fit,minmax(240px,1fr));gap:.7rem;margin:.55rem 0 .5rem}
@media(max-width:820px){.argrid{grid-template-columns:1fr}}
.arbox{border:1px solid var(--line);border-top:3px solid var(--pc,var(--accent));border-radius:var(--radius);padding:.75rem .85rem .7rem;background:var(--bg)}
.arbox h3{margin:0 0 .15rem;font-size:var(--fs-h3);border:0;padding:0}
.arbox h3 a{color:var(--fg)}
.arunit{margin:0 0 .45rem;font-size:var(--fs-xs);color:var(--muted)}
.arlist{list-style:none;margin:0;padding:0}
.arlist li{display:grid;grid-template-columns:1.4rem 1fr auto;gap:.35rem;align-items:baseline;padding:.32rem 0;border-top:1px solid var(--line);font-size:var(--fs-md)}
.arlist li:first-child{border-top:0}
.arrk{color:var(--muted);font-variant-numeric:tabular-nums;font-weight:var(--fw-bold)}
.arlist li:nth-child(-n+3) .arrk{color:var(--pc,var(--accent))}
.armn{font-size:var(--mn-fs);font-weight:var(--mn-fw);color:var(--fg)}
.aramt{color:var(--fg);font-variant-numeric:tabular-nums;white-space:nowrap;font-size:var(--fs-sm)}
.armore a{color:var(--pc,var(--accent))}

/* ── 自治体：数字でみるダッシュボード ── */
.figures{margin:1.5rem 0 1.8rem}
.figures-intro{margin:0 0 1rem}
.figures-intro h2{margin:0 0 .3rem;font-size:var(--fs-h2);border:0;padding:0}
.figures-intro p{margin:0;color:var(--muted);font-size:var(--fs-sm);line-height:1.55;max-width:36em}
.figures-grid{display:flex;flex-direction:column;gap:1.1rem}
.fig-panel{padding:0;border-top:1px solid var(--line)}
.fig-head{margin:.85rem 0 .65rem}
.fig-head h3{margin:0 0 .2rem;font-size:var(--fs-h3);border:0;padding:0}
.fig-head p{margin:0;font-size:var(--fs-sm);color:var(--muted)}

.fig-brows{display:flex;flex-direction:column;gap:0}
.fig-brow{display:grid;grid-template-columns:4.2rem minmax(0,1fr) auto auto auto;gap:.45rem .55rem;align-items:baseline;
  padding:.55rem 0;border-bottom:1px solid var(--line);color:var(--fg);text-decoration:none}
.fig-brow:hover{background:color-mix(in srgb,var(--accent) 5%,transparent);text-decoration:none}
.fig-btag{font-size:var(--fs-xs);font-weight:var(--fw-bold);color:#fff;background:#6b7c8f;border-radius:4px;padding:.12rem .35rem;text-align:center}
.fig-blabel{font-size:var(--fs-md);font-weight:var(--fw-semi)}
.fig-bunit{font-size:var(--fs-xs);color:var(--muted);white-space:nowrap}
.fig-bval{font-size:var(--fs-lg);font-weight:var(--fw-black);font-variant-numeric:tabular-nums;letter-spacing:.01em;white-space:nowrap}
.fig-rank{font-size:var(--fs-xs);color:var(--muted);white-space:nowrap;min-width:4.5rem;text-align:right}
.fig-more a{color:var(--accent)}

.fig-costs{display:flex;flex-direction:column;gap:.85rem}
.fig-cost{display:grid;grid-template-columns:minmax(0,1.2fr) minmax(0,1fr);gap:.9rem 1.2rem;align-items:end;
  padding:.75rem 0;border-bottom:1px solid var(--line)}
.fig-cost.slim{display:flex;align-items:baseline;gap:.75rem;padding:.45rem 0;grid-template-columns:unset}
.fig-kicker{display:block;font-size:var(--fs-xs);color:var(--muted);margin-bottom:.2rem}
.fig-big{display:block;font-size:clamp(1.25rem,2.6vw,1.55rem);font-weight:var(--fw-black);font-variant-numeric:tabular-nums;line-height:1.15;letter-spacing:.01em}
.fig-mid{font-size:var(--fs-h2);font-weight:var(--fw-bold);font-variant-numeric:tabular-nums}
.fig-sub{display:block;margin-top:.25rem;font-size:var(--fs-sm);color:var(--muted)}
.fig-vs{display:block;margin-top:.35rem;font-size:var(--fs-sm);color:var(--muted)}
.fig-vs strong{color:var(--fg);font-weight:var(--fw-bold)}
.fig-cost-side,.fig-cost-chart{min-width:0}
.fig-side-label{display:block;font-size:var(--fs-xs);color:var(--muted);margin-bottom:.2rem}

.fig-tri{display:flex;flex-wrap:wrap;gap:1rem 1.1rem;align-items:stretch;padding:.35rem 0 .55rem}
.fig-card{flex:1 1 220px;min-width:0;padding:.55rem 0 .2rem;border-top:1px solid var(--line)}
.fig-card .fig-cost-chart{margin-top:.55rem}
.fig-card .fig-cmp li>a,.fig-card .fig-cmp li>div{grid-template-columns:3.6rem 1fr auto;gap:.28rem}
.fig-card .fig-cmp-name{font-size:var(--fs-xs)}
.fig-card .fig-cmp-name em{font-size:var(--fs-xs)}
.fig-card .fig-cmp-n{font-size:var(--fs-xs)}

.fig-cmp{list-style:none;margin:0;padding:0;display:flex;flex-direction:column;gap:.28rem}
.fig-cmp li>a,.fig-cmp li>div{display:grid;grid-template-columns:4.8rem 1fr auto;gap:.4rem;align-items:center;
  padding:.18rem 0;color:var(--fg);text-decoration:none}
.fig-cmp li>a:hover{text-decoration:none;opacity:.85}
.fig-cmp-name{font-size:var(--fs-xs);line-height:1.25;min-width:0}
.fig-cmp-name em{display:block;font-style:normal;font-size:var(--fs-xs);color:var(--muted);font-weight:var(--fw-semi)}
.fig-cmp li.fig-self .fig-cmp-name{font-weight:var(--fw-bold)}
.fig-cmp li.fig-tokyo .fig-cmp-name{color:var(--muted)}
.fig-cmp-bar{display:block;height:9px;background:var(--track);border-radius:999px;overflow:hidden}
.fig-cmp-bar i{display:block;height:100%;width:var(--w,0);border-radius:999px;background:var(--c,var(--pc-child));
  transform:scaleX(0);transform-origin:left}
.fig-cmp li.fig-tokyo .fig-cmp-bar i{background:#b7c0ca}
.fig-cmp li.fig-near .fig-cmp-bar i{opacity:.72}
.figures.on .fig-cmp-bar i{transform:scaleX(1);transition:transform .7s cubic-bezier(.2,.7,.2,1)}
.fig-cmp li:nth-child(1) .fig-cmp-bar i{transition-delay:.04s}
.fig-cmp li:nth-child(2) .fig-cmp-bar i{transition-delay:.08s}
.fig-cmp li:nth-child(3) .fig-cmp-bar i{transition-delay:.12s}
.fig-cmp li:nth-child(4) .fig-cmp-bar i{transition-delay:.16s}
.fig-cmp li:nth-child(5) .fig-cmp-bar i{transition-delay:.2s}
.fig-cmp-n{font-variant-numeric:tabular-nums;font-size:var(--fs-xs);color:var(--muted);white-space:nowrap}
.fig-cmp li.fig-self .fig-cmp-n{color:var(--fg);font-weight:var(--fw-bold)}

.fig-meter{display:flex;flex-direction:column;gap:.28rem;margin-top:.35rem}
.fig-meter-row{display:grid;grid-template-columns:4.8rem 1fr;gap:.4rem;align-items:center;font-size:var(--fs-xs);color:var(--fg)}
.fig-meter-row.muted{color:var(--muted)}
.fig-meter-track{height:8px;background:var(--track);border-radius:999px;overflow:hidden}
.fig-meter-track i{display:block;height:100%;border-radius:999px;background:var(--c,var(--pc-child));
  transform:scaleX(0);transform-origin:left}
.fig-meter-track i.ref{background:#b7c0ca}
.figures.on .fig-meter-track i{transform:scaleX(1);transition:transform .7s cubic-bezier(.2,.7,.2,1)}
.figures.on .fig-st-bar i:nth-child(1){transition-delay:.05s}
.figures.on .fig-st-list li:nth-child(2) .fig-st-bar i{transition-delay:.1s}
.figures.on .fig-st-list li:nth-child(3) .fig-st-bar i{transition-delay:.15s}
.figures.on .fig-st-list li:nth-child(4) .fig-st-bar i{transition-delay:.2s}
.figures.on .fig-st-list li:nth-child(5) .fig-st-bar i{transition-delay:.25s}

.fig-st-list{list-style:none;margin:0;padding:0}
.fig-st-list li{display:grid;grid-template-columns:5.5rem 1fr auto;gap:.5rem;align-items:center;padding:.38rem 0;border-bottom:1px solid var(--line);font-size:var(--fs-md)}
.fig-st-name{font-weight:var(--fw-semi)}
.fig-st-bar{display:block;height:10px;background:var(--track);border-radius:999px;overflow:hidden}
.fig-st-bar i{display:block;height:100%;width:var(--w,0);background:var(--pc-house);border-radius:999px;
  transform:scaleX(0);transform-origin:left}
.figures.on .fig-st-bar i{transform:scaleX(1);transition:transform .65s cubic-bezier(.2,.7,.2,1)}
.fig-st-n{font-variant-numeric:tabular-nums;font-size:var(--fs-sm);color:var(--muted);white-space:nowrap}
.figures-note{margin:.9rem 0 0;font-size:var(--fs-xs);color:var(--muted);line-height:1.5}
.fig-st-wrap{padding:.35rem 0 .15rem}

@media(prefers-reduced-motion:reduce){
  .figures .fig-meter-track i,.figures .fig-st-bar i,.figures .fig-cmp-bar i{transform:none;transition:none}
}

@media(max-width:720px){
  .fig-brow{grid-template-columns:3.6rem minmax(0,1fr) auto;gap:.3rem .4rem}
  .fig-bunit{display:none}
  .fig-rank{grid-column:2;text-align:left;margin-top:-.15rem}
  .fig-bval{grid-column:3;grid-row:1/3;align-self:center}
  .fig-cost{grid-template-columns:1fr;gap:.45rem}
  .fig-tri{grid-template-columns:1fr;gap:.65rem}
}

.fig-brow .fig-btag[data-g="子育て"],.fig-btag.g-child{background:var(--pc-child)}
.fig-btag.g-birth{background:var(--pc-birth)}
.fig-btag.g-house{background:var(--pc-house)}
.fig-btag.g-life{background:var(--pc-job)}
.fig-btag.g-senior{background:var(--pc-senior)}

/* ── 分野別セクション ── */
.ev{border-left:3px solid var(--pc,var(--accent));padding-left:.75rem;margin:1.4rem 0}
.ev>h2{border:0;display:flex;align-items:center;justify-content:flex-start;gap:.5rem;margin:.1rem 0 .5rem;font-size:var(--fs-h2)}
.evh{display:inline-flex;align-items:center;gap:.45rem}
.evh a{color:var(--fg)}
.evi{display:inline-flex;color:#fff;background:var(--pc,var(--accent));border-radius:7px;padding:3px}
.evi .ev-ic{width:15px;height:15px}
.ev>h2 .cnt{background:var(--pc,var(--accent))}
.ev>h2 .csum{color:var(--pc,var(--accent))}
.evlinks a{color:var(--pc,var(--accent))}
.cmpbox[style*="--pc"] strong{color:var(--pc)}

/* ── 関連制度・ほかの自治体 ── */
.related{margin:1.6rem 0 .4rem;border-top:1px solid var(--line);padding-top:.6rem}
.related h2{font-size:var(--fs-h2);border:0}
.others{margin:1.8rem 0 .4rem}
.others h2{font-size:var(--fs-h2)}
.ostrip{display:flex;flex-wrap:wrap;gap:.4rem}
.ostrip a{border:1px solid var(--line);border-radius:999px;padding:.28rem .7rem;font-size:var(--mn-fs);font-weight:var(--mn-fw);color:var(--fg);background:var(--bg)}
.ostrip a:hover{border-color:var(--accent);color:var(--accent);text-decoration:none}
.totop{margin:0 0 .6rem;text-align:right}
.totop a{color:var(--muted);font-size:var(--fs-sm)}
"""


if __name__ == "__main__":
    main()
