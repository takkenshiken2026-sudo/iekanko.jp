#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
制度ナビ 静的サイトジェネレータ (SSG)
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
SITE_NAME = "制度ナビ｜東京都の給付・手当・助成 まるわかり比較"

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

EVENTS = {  # slug -> (表示名, 導入文)
 "pregnancy_birth":("妊娠・出産","妊娠がわかってから出産までにもらえる給付金・助成と、必要な手続きをまとめています。"),
 "childcare":("子育て","児童手当・医療費助成・保育料軽減など、子育て世帯が受けられる支援をまとめています。"),
 "moving":("引っ越し","転入・転出の手続きと、引っ越しに関わる助成・支援をまとめています。"),
 "retirement_unemployment":("退職・失業","退職・失業時の保険料軽減・給付・支援制度をまとめています。"),
 "elderly_care":("高齢・介護","高齢者・介護が必要な方が受けられる助成・サービスをまとめています。"),
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
 ("child_iryo","子ども・乳幼児医療費助成","childcare",["子ども医療費","乳幼児医療","子育て医療","義務教育就学児医療","高校生等医療","マル子","マル乳","こども医療費","子供医療費"],[]),
 ("child_hitorioya","ひとり親家庭医療費助成(マル親)","childcare",["ひとり親家庭医療","母子家庭医療","ひとり親医療","マル親"],[]),
 ("child_shugaku","就学援助","childcare",["就学援助","就学奨励","学用品費"],[]),
 ("child_hoiku_gen","保育料軽減・多子軽減","childcare",["保育料","副食費","給食費無償","第二子","多子"],["就学援助"]),
 ("child_ninkagai","認可外保育料補助","childcare",["認可外","ベビーシッター","一時預かり","病児保育","産休明け"],[]),
 ("child_iwai","出産・入学祝金/子育てクーポン","childcare",["出産祝","誕生祝","入学祝","入学準備","子育てクーポン","誕生記念"],[]),
 ("child_shogakukin","奨学金・進学支援","childcare",["奨学金","進学支援","高校生等奨学","入学支度金","受験生"],[]),
 ("child_omutsu_baby","乳児おむつ・ミルク支援","childcare",["おむつ定期便","乳児用おむつ","おむつ配送","ミルク","液体ミルク","0歳児"],["高齢"]),
 ("house_juukyo","住居確保給付金","moving",["住居確保給付"],[]),
 ("house_yachin","家賃補助(若年・子育て・勤労者)","moving",["家賃助成","家賃補助","住み替え家賃","居住支援","家賃債務","礼金","転居費用"],["住居確保給付"]),
 ("house_sansedai","三世代同居・近居支援","moving",["三世代","近居","親元近居"],[]),
 ("house_reform","住宅リフォーム・バリアフリー改修助成","moving",["リフォーム","住宅改修","バリアフリー","住宅設備改修","増改築","改修助成"],["高齢者住宅改修"]),
 ("house_taishin","耐震・ブロック塀・空き家助成","moving",["耐震","ブロック塀","空き家","除却"],[]),
 ("house_eco","住宅省エネ・創エネ・雨水助成","moving",["太陽光","蓄電池","省エネ","創エネ","再エネ","雨水","高断熱","ゼロエミ"],[]),
 ("job_kokuho","国民健康保険料軽減・減免","retirement_unemployment",["国民健康保険料","国保料","保険料軽減","保険税軽減","国保税"],[]),
 ("job_nenkin","国民年金保険料免除","retirement_unemployment",["国民年金","年金保険料免除","年金免除","付加年金"],[]),
 ("job_shurou","就労支援・職業訓練","retirement_unemployment",["就労支援","職業訓練","再就職","求職","就職支援","マザーズ"],[]),
 ("job_kashitsuke","生活福祉資金・緊急小口貸付","retirement_unemployment",["生活福祉資金","緊急小口","貸付","応急小口"],[]),
 ("job_konkyu","生活困窮者自立支援・家計相談","retirement_unemployment",["生活困窮","自立支援","家計改善","家計相談","くらしとしごと"],[]),
 ("job_shobyo","傷病手当金","retirement_unemployment",["傷病手当"],[]),
 ("eld_omutsu","高齢者紙おむつ支給・助成","elderly_care",["紙おむつ","おむつ支給","おむつ代","おむつ給付"],["乳児","0歳"]),
 ("eld_kaigo_gen","介護保険料減免","elderly_care",["介護保険料","保険料減免"],[]),
 ("eld_hochoki","補聴器購入助成","elderly_care",["補聴器"],[]),
 ("eld_jutaku","高齢者住宅改修・設備改修助成","elderly_care",["高齢者住宅改修","高齢者住宅設備","高齢者リフォーム","住宅改修給付","段差解消"],[]),
 ("eld_vaccine","高齢者ワクチン助成(肺炎球菌/帯状疱疹等)","elderly_care",["肺炎球菌","帯状疱疹","高齢者インフル","高齢者予防接種"],[]),
 ("eld_kinkyu","緊急通報システム・見守り","elderly_care",["緊急通報","見守り","徘徊","位置探索","認知症高齢者位置","声かけ"],[]),
 ("eld_haishoku","配食・栄養・食事サービス","elderly_care",["配食","食事サービス","給食サービス","栄養改善"],[]),
 ("eld_iwai","敬老祝い金・長寿祝品","elderly_care",["敬老","長寿","米寿","高齢者祝","祝い金"],[]),
 ("eld_yougu","介護用具・福祉用具・寝具乾燥","elderly_care",["福祉用具","介護用具","寝具乾燥","日常生活用具","用具受領","レンタル"],["障害"]),
 ("dis_iryo","重度心身障害者医療費助成(マル障)","elderly_care",["障害者医療","心身障害者医療","マル障","重度障害者医療"],[]),
 ("dis_yougu","障害者日常生活用具・補装具","elderly_care",["障害.*日常生活用具","補装具","障害者用具","障害児用具"],[]),
 ("low_aircon","エアコン設置助成(低所得/熱中症)","elderly_care",["エアコン","冷房","熱中症"],[]),
 ("low_taxi","タクシー・移送・交通費助成","elderly_care",["タクシー","移送","福祉交通","交通費助成","バス.*助成","リフト付"],[]),
]
CAT_BY_ID = {c[0]:c for c in TAXONOMY}

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
    doc = f"""<!doctype html>
<html lang="ja">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{esc(title)}</title>
<meta name="description" content="{esc(description)}">
<meta name="robots" content="{robots}">
<link rel="canonical" href="{esc(canon)}">
<meta property="og:type" content="website">
<meta property="og:site_name" content="{esc(SITE_NAME)}">
<meta property="og:title" content="{esc(title)}">
<meta property="og:description" content="{esc(description)}">
<meta property="og:url" content="{esc(canon)}">
<meta property="og:locale" content="ja_JP">
<meta name="twitter:card" content="summary">
<link rel="stylesheet" href="/assets/style.css">
{ld}</head>
<body>
<header class="site"><a class="brand" href="/">制度ナビ</a>
<span class="tag">東京都の給付・手当・助成 比較</span></header>
<main>
{crumbs}
{body}
</main>
<footer class="site">
<p>本サイトは各自治体・公的機関の公表情報をもとに整理した比較・案内サービスです。
最新かつ正確な内容は必ず各制度の公式ページでご確認ください。</p>
<p><a href="/">トップ</a> ・ 東京都62自治体 ・ 出典付き / 最終確認日を明記</p>
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

def events_of(pid):
    return c.execute("""SELECT le.slug,le.name FROM program_life_events ple
       JOIN life_events le ON le.id=ple.life_event_id WHERE ple.program_id=? ORDER BY ple.relevance_score DESC""",(pid,)).fetchall()

def gate_index(p, facts):
    if p["reliability_status"] == "needs_review": return False
    conf = [f[4] for f in facts if f[4] is not None]
    if not conf: return False
    return (sum(conf)/len(conf)) >= GATE_MIN_CONFIDENCE

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

def build_program(m, slug, p, cats):
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
    src_block = f'<p class="official">▶ 公式ページ: <a href="{esc(official)}" target="_blank" rel="nofollow noopener">{esc(official)}</a></p>' if official else ""
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
    if idx: sitemap_urls.append((url, "0.8"))
    return idx

def compare_links(cats):
    ls=[c for c in cats if c in CAT_BY_ID]
    if not ls: return ""
    a="".join(f'<li><a href="/hikaku/{cid}/">東京都で「{esc(CAT_BY_ID[cid][1])}」を自治体比較 ▶</a></li>' for cid in ls)
    return f'<div class="cmpbox"><strong>東京都の他自治体と比べる</strong><ul>{a}</ul></div>'

# ── 比較ページ（被リンク磁石）────────────────────────────────────────────────
def build_compare(cid, entries):
    """entries: [(m, slug, program, amount, idx), ...]  同一カテゴリの全自治体分"""
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
    # 自治体表示順: 区→市→町村（DB id順）
    entries = sorted(best.values(), key=lambda e: e[0]["id"])
    rows=[]
    for m, slug, p, amount, idx in entries:
        mn=m["municipality_name"]
        amt = esc(clip(amount,80)) if amount else '<span class="na">記載を確認中</span>'
        rows.append(f'<tr><td class="mn"><a href="/area/tokyo/{slug}/seido/{p["id"]}/">{esc(mn)}</a></td>'
                    f'<td>{amt}</td><td class="dt">{esc(p["last_verified_at"] or "")}</td></tr>')
    have=len(entries)
    missing=[m["municipality_name"] for m in munis if m["id"] not in {e[0]["id"] for e in entries}]
    miss_html=""
    if missing:
        miss_html=(f'<p class="miss"><strong>この制度が未確認の自治体（{len(missing)}）：</strong>'
                   f'{esc("、".join(missing))}<br><span class="na">※制度が無い場合と、当サイトで未収集の場合があります。</span></p>')
    title=f"【{ev_name}】{label} 東京都62自治体を比較｜金額・対象一覧"
    desc=clip(f"東京都の{label}を{have}自治体分まとめて比較。自治体ごとの金額・対象・最終確認日を一覧化。どの区市町村が手厚いかを出典付きで確認できます。",118)
    body=f"""
<span class="badge">{esc(ev_name)}</span>
<h1>東京都の{esc(label)}を自治体で比較</h1>
<p class="lead">東京都62自治体の「{esc(label)}」を横断比較しています（掲載 {have}自治体・各制度に出典/最終確認日つき）。
金額欄は各自治体の代表的な支給額・助成額の記載です。詳細は自治体名から各ページでご確認ください。</p>
<div class="tablewrap"><table class="cmp">
<thead><tr><th>自治体</th><th>支給額・助成額</th><th>確認日</th></tr></thead>
<tbody>{''.join(rows)}</tbody></table></div>
{miss_html}
<p class="note">※金額は制度改定で変わります。申請前に必ず各自治体の公式ページ（各自治体ページ内の出典リンク）でご確認ください。</p>
<p><a href="/hikaku/">◀ 制度カテゴリ比較の一覧にもどる</a></p>"""
    il={"@context":"https://schema.org","@type":"ItemList","name":f"{label} 自治体比較",
        "itemListElement":[{"@type":"ListItem","position":i+1,"name":e[0]["municipality_name"],
          "url":f"{BASE_URL}/area/tokyo/{e[1]}/seido/{e[2]['id']}/"} for i,e in enumerate(entries)]}
    bc=[("トップ","/"),("制度を比較する","/hikaku/"),(label,None)]
    robots="index,follow" if have>=3 else "noindex,follow"
    page(path=url+"index.html",title=title,description=desc,canonical=url,
         jsonld=[il],robots=robots,breadcrumb=bc,body=body)
    if have>=3: sitemap_urls.append((url,"0.9"))
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
    title = f"{mn}で{ev_name}のときに使える制度・手当・助成【一覧】"
    desc = clip(f"{mn}で{ev_name}のときに受けられる給付金・手当・助成制度を一覧でまとめました。{ev_intro}", 118)
    body = f"""
<h1>{esc(mn)}の{esc(ev_name)}で使える制度</h1>
<p class="lead">{esc(ev_intro)}</p>
<p class="meta">{esc(mn)}・{esc(ev_name)}関連の制度 {len(items)}件</p>
{listing}
<p><a href="/area/tokyo/{slug}/">◀ {esc(mn)}の制度一覧にもどる</a></p>"""
    il = {"@context":"https://schema.org","@type":"ItemList","itemListElement":[
        {"@type":"ListItem","position":i+1,"name":p["title"],
         "url":f"{BASE_URL}/area/tokyo/{slug}/seido/{p['id']}/"} for i,p in enumerate(items)]}
    bc=[("トップ","/"),(mn,f"/area/tokyo/{slug}/"),(ev_name,None)]
    robots = "index,follow" if items else "noindex,follow"
    page(path=url+"index.html", title=title, description=desc, canonical=url,
         jsonld=[il], robots=robots, breadcrumb=bc, body=body)
    if items: sitemap_urls.append((url,"0.6"))

# ── 自治体ハブ ──────────────────────────────────────────────────────────────
def build_muni(m, slug):
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
        more = f'<a class="more" href="/area/tokyo/{slug}/{ev_slug}/">{ev_name}の制度をすべて見る（{len(items)}件）▶</a>' if items else ""
        sections.append(f'<section class="ev"><h2><a href="/area/tokyo/{slug}/{ev_slug}/">{esc(ev_name)}</a> '
                        f'<span class="cnt">{len(items)}</span></h2><ul class="proglist">{lis}</ul>{more}</section>')
    title = f"{mn}で受けられる給付・手当・助成 一覧｜対象・金額まとめ"
    desc = clip(f"{mn}で受けられる給付金・手当・助成・支援制度を{len(progs)}件、ライフイベント別に出典付きでまとめました。妊娠出産・子育て・引っ越し・退職失業・高齢介護の制度が一目でわかります。",118)
    body = f"""
<h1>{esc(mn)}で受けられる給付・手当・助成 一覧</h1>
<p class="lead">{esc(mn)}にお住まいの方が使える制度を、ライフイベント別にまとめました（全{len(progs)}件・出典/最終確認日つき）。</p>
{''.join(sections)}
"""
    bc=[("トップ","/"),(mn,None)]
    page(path=url+"index.html", title=title, description=desc, canonical=url, breadcrumb=bc, body=body)
    sitemap_urls.append((url,"0.7"))
    return progs, counts

# ── トップ ──────────────────────────────────────────────────────────────────
def build_home(muni_stats):
    wards=[x for x in muni_stats if x[0]["municipality_type"]=="ward"]
    cities=[x for x in muni_stats if x[0]["municipality_type"]=="city"]
    others=[x for x in muni_stats if x[0]["municipality_type"] in ("town","village")]
    def grid(rows):
        return '<ul class="mgrid">'+''.join(
          f'<li><a href="/area/tokyo/{s}/">{esc(m["municipality_name"])}</a><span>{n}件</span></li>'
          for m,s,n in rows)+'</ul>'
    body=f"""
<h1>東京都の給付・手当・助成を、自治体ごとに比較</h1>
<p class="lead">東京都62自治体で受けられる給付金・手当・助成制度を、出典と最終確認日つきで整理。
「住んでいる街・引っ越し先でどんな支援が受けられるか」を一目で比較できます。</p>
<div class="cmpbox"><strong>制度ごとに自治体を比べる</strong>
<p>児童手当・産後ケア・高齢者紙おむつ・家賃補助など、同じ制度の金額・対象を東京都62自治体で横断比較できます。</p>
<p><a href="/hikaku/">▶ 制度カテゴリ別の自治体比較を見る</a></p></div>
<h2>23区から探す</h2>{grid(wards)}
<h2>市部から探す</h2>{grid(cities)}
<h2>町村・島しょから探す</h2>{grid(others)}
"""
    page(path="index.html", title=SITE_NAME,
         description="東京都62自治体の給付金・手当・助成制度を、出典・最終確認日つきで自治体ごとに比較できるサービス。妊娠出産・子育て・引っ越し・退職失業・高齢介護のもらえるお金がわかります。",
         canonical="/", breadcrumb=None, body=body)
    sitemap_urls.append(("/","1.0"))

# ── 実行 ────────────────────────────────────────────────────────────────────
def main():
    muni_stats=[]; total_prog=0; indexed=0
    cat_entries={}
    for m in munis:
        slug = muni_slug(m)
        if not slug:
            print("NO SLUG:", m["municipality_name"]); continue
        progs, counts = build_muni(m, slug)
        for ev_slug,(ev_name,ev_intro) in EVENTS.items():
            build_muni_event(m, slug, ev_slug, ev_name, ev_intro, progs)
        for p in progs:
            total_prog+=1
            cats = classify(p["title"], p["summary"], p["benefit_description"], p["target_description"])
            facts = facts_of(p["id"])
            idx = build_program(m, slug, p, cats)
            if idx: indexed+=1
            amount = amount_of(facts)
            for cid in cats:
                cat_entries.setdefault(cid,[]).append((m, slug, p, amount, idx))
        muni_stats.append((m, slug, len(progs)))
    # 比較ページ
    cat_counts={}
    for cid in CAT_BY_ID:
        if cid in cat_entries:
            cat_counts[cid]=build_compare(cid, cat_entries[cid])
    build_compare_index(cat_counts)
    build_home(muni_stats)
    write_sitemap(); write_robots(); write_css()
    cmp_pub=sum(1 for v in cat_counts.values() if v>=3)
    print(f"生成完了: 自治体{len(muni_stats)} / 制度ページ{total_prog}（index {indexed} / noindex {total_prog-indexed}）")
    print(f"比較ページ: {len(cat_counts)}カテゴリ（index {cmp_pub}）")
    print(f"sitemap URL数: {len(sitemap_urls)}  出力先: {OUT}")
    print(f"BASE_URL={BASE_URL}  （本番前に SEIDO_BASE_URL を設定してください）")

def write_sitemap():
    items="".join(f'<url><loc>{esc(BASE_URL+u)}</loc><priority>{p}</priority></url>' for u,p in sitemap_urls)
    write("sitemap.xml", f'<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">{items}</urlset>')

def write_robots():
    write("robots.txt", f"User-agent: *\nAllow: /\n\nSitemap: {BASE_URL}/sitemap.xml\n")

def write_css():
    write("assets/style.css", CSS)

CSS = """:root{--fg:#1a2233;--muted:#5b6577;--line:#e5e8ef;--bg:#fff;--accent:#1558d6;--soft:#f5f7fb;--badge:#eaf1fe}
*{box-sizing:border-box}html{-webkit-text-size-adjust:100%}
body{margin:0;font-family:system-ui,-apple-system,"Hiragino Kaku Gothic ProN","Noto Sans JP",sans-serif;color:var(--fg);background:var(--bg);line-height:1.7}
a{color:var(--accent);text-decoration:none}a:hover{text-decoration:underline}
header.site{display:flex;align-items:center;gap:.6rem;padding:.8rem 1.1rem;border-bottom:1px solid var(--line);flex-wrap:wrap}
.brand{font-weight:800;font-size:1.15rem;color:var(--fg)}
header .tag{color:var(--muted);font-size:.8rem}
main{max-width:820px;margin:0 auto;padding:1.1rem 1.1rem 3rem}
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
footer.site{border-top:1px solid var(--line);padding:1.2rem 1.1rem;color:var(--muted);font-size:.8rem;max-width:820px;margin:0 auto}
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
"""

if __name__ == "__main__":
    main()
