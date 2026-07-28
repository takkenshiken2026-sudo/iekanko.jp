#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
公開中の docs/ から 原本DB(gov_life_support.sqlite3) を復元する。

build/build_site.py が参照する 6 テーブル
(municipalities / programs / program_municipalities /
 program_facts / program_life_events / life_events)
を、生成物 docs/ の各制度ページ・目的別ページから逆算して再構築する。

用途: 元DBがこのリポジトリに無い状況で、公開中サイトの内容を「原本」として
      取り込み、以後は DB を編集 → build_site.py で再生成 という運用に載せるため。

  python3 build/rebuild_db_from_docs.py            # -> gov_life_support.sqlite3
  python3 build/rebuild_db_from_docs.py out.sqlite3
"""
import os, re, sys, html, glob, json, sqlite3

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DOCS = os.path.join(ROOT, "docs")

# 自治体スラッグ -> 公式サイトURL（生成物の JSON-LD provider.url から回収）
def recover_muni_urls():
    prov = re.compile(r'"provider":\s*\{[^}]*?"url":\s*"(https?://[^"]+)"')
    out = {}
    for fp in glob.glob(os.path.join(DOCS, "area", "tokyo", "*", "seido", "*", "index.html")):
        slug = re.search(r"/tokyo/([^/]+)/seido", fp.replace("\\", "/")).group(1)
        if slug in out:
            continue
        m = prov.search(open(fp, encoding="utf-8").read())
        if m:
            out[slug] = m.group(1)
    return out
SCHEMA = os.path.join(ROOT, "build", "schema.sql")
OUT_DB = sys.argv[1] if len(sys.argv) > 1 else os.path.join(ROOT, "gov_life_support.sqlite3")

# ── build_site.py と同一の対応表（逆引き）─────────────────────────────
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
SLUG2NAME = {v: k for k, v in SLUGS.items()}

EVENTS = {  # slug -> 表示名
 "pregnancy_birth":"妊娠・出産","childcare":"子育て","moving":"引っ越し",
 "retirement_unemployment":"退職・失業","elderly_care":"高齢・介護",
}
EVENT_ORDER = {"pregnancy_birth":1,"childcare":2,"moving":3,"retirement_unemployment":4,"elderly_care":5}

# 表示ラベル -> fact_type（build_site の FACT_LABELS を逆引き。代表値を採用）
LABEL2FT = {
 "対象者":"target","対象の詳細":"target_detail","支給額・助成額":"amount","内容・給付":"benefit",
 "支援内容":"support","サービス内容":"service","対象範囲":"coverage","条件":"condition","上限":"limit",
 "申請方法":"application","必要書類":"document","申請期限":"deadline","日程":"schedule","期間":"duration",
 "支給時期":"payment","オンライン手続き":"online","窓口":"office","目的":"purpose","返済":"repayment",
 "定員":"capacity","開始":"start","関連手続き":"related_procedures","引っ越し関連":"move_value",
}
# 表示バッジ(日本語) -> program_type（PT_JA 逆引き）
JA2PT = {
 "手当":"allowance","助成金":"subsidy","給付":"benefit","医療費助成":"medical_subsidy","サービス":"service",
 "軽減・免除":"reduction","住まい助成":"housing_subsidy","手続き":"procedure","貸付":"loan",
 "教育助成":"education_subsidy","住まい支援":"housing_support","相談":"consultation","料金軽減":"fee_reduction",
 "税軽減":"tax_reduction","現金給付":"cash_benefit","住まい":"housing","交通助成":"transport_subsidy",
}

def muni_type(name):
    if name.endswith("区"): return "special_ward"
    if name.endswith("市"): return "city"
    if name.endswith("町"): return "town"
    if name.endswith("村"): return "village"
    return "city"

def strip_tags(s): return html.unescape(re.sub(r"<[^>]+>", "", s)).strip()

# ── パース ───────────────────────────────────────────────────────────
# dt にはアイコンSVGが先頭に入ることがあるため読み飛ばしてラベルを取得する。
FACT_RE = re.compile(r'<div class="fact"><dt>(?:<svg\b[^>]*>.*?</svg>)?\s*([^<]*?)\s*</dt><dd>(.*?)</dd></div>', re.S)
SRC_RE  = re.compile(r'<a class="src"[^>]*href="([^"]+)"[^>]*>出典</a>')
BADGE_RE = re.compile(r'<span class="badge[^"]*">([^<]+)</span>')
TITLE_RE = re.compile(r'<h1[^>]*>(.*?)</h1>', re.S)
LEAD_RE  = re.compile(r'<p class="lead"[^>]*>(.*?)</p>', re.S)
VERIFIED_RE = re.compile(r'最終確認日[:：]\s*(\d{4}-\d{2}-\d{2})')
VERIFIED2_RE = re.compile(r'【(\d{4}-\d{2}-\d{2})時点】')
# 公式URL: FAQ直下の「公式ページ」セクション（現行）→ 旧・制度の内容表の行 → 旧p.official の順。
OFFICIAL_SEC_RE = re.compile(
    r'<h2[^>]*>.*?公式ページ</h2>.*?<a class="offbtn"[^>]*href="([^"]+)"', re.S)
OFFICIAL0_RE = re.compile(r'<dt>(?:<svg\b[^>]*>.*?</svg>)?\s*公式ページ</dt><dd><a[^>]*href="([^"]+)"', re.S)
OFFICIAL_RE = re.compile(r'公式ページ[:：]\s*<a[^>]*href="([^"]+)"')
OFFICIAL2_RE = re.compile(r'公式ページ[^h<]*?(https?://[^\s"<]+)')
ROBOTS_RE = re.compile(r'<meta name="robots" content="([^"]+)"')

def parse_program_page(fp):
    t = open(fp, encoding="utf-8").read()
    m = re.search(r"/tokyo/([^/]+)/seido/(\d+)/index\.html$", fp.replace("\\", "/"))
    slug, pid = m.group(1), int(m.group(2))
    mn = SLUG2NAME.get(slug)
    if not mn:
        return None
    # title (h1 = "○○市の△△" -> strip muni prefix)
    h1 = strip_tags(TITLE_RE.search(t).group(1)) if TITLE_RE.search(t) else ""
    title = re.sub(r"^" + re.escape(mn) + r"の", "", h1).strip() or h1
    # badge -> program_type
    badge = BADGE_RE.search(t)
    ptype = JA2PT.get(strip_tags(badge.group(1)) if badge else "", "subsidy")
    # lead / summary（原本の summary は「○○市では、…」を含む全文）
    summary = strip_tags(LEAD_RE.search(t).group(1)) if LEAD_RE.search(t) else ""
    # verified date
    d = VERIFIED_RE.search(t) or VERIFIED2_RE.search(t)
    verified = d.group(1) if d else None
    # official url
    o = (OFFICIAL_SEC_RE.search(t) or OFFICIAL0_RE.search(t)
         or OFFICIAL_RE.search(t) or OFFICIAL2_RE.search(t))
    official = o.group(1) if o else ""
    # robots -> reliability
    rb = ROBOTS_RE.search(t)
    noindex = bool(rb and rb.group(1).startswith("noindex"))
    # facts
    facts = []
    tgt_vals, ben_vals = [], []
    for lbl_raw, dd in FACT_RE.findall(t):
        lbl = strip_tags(lbl_raw)
        ft = LABEL2FT.get(lbl)
        if not ft:
            continue
        ev = SRC_RE.search(dd)
        evurl = ev.group(1) if ev else (official or "")
        val = strip_tags(SRC_RE.sub("", dd))
        if not val:
            continue
        facts.append((ft, val, evurl))
        if ft in ("target", "target_detail", "coverage"):
            tgt_vals.append(val)
        if ft in ("benefit", "amount", "support", "service"):
            ben_vals.append(val)
    if not official and facts:
        official = facts[0][2]
    return {
        "id": pid, "slug": slug, "muni": mn, "title": title or "制度",
        "program_type": ptype, "summary": summary, "verified": verified,
        # 公式URLが取れない制度は、制度ごとに一意なダミー(example.invalid/slug/pid)にする。
        # official_url は NOT NULL かつ UNIQUE(title, official_url) のため、同名・公式URL無しの
        # 別制度が衝突しないよう一意にする必要がある。build_site 側はこのダミーを「公式なし」として扱う。
        "official_url": official or f"https://www.example.invalid/{slug}/{pid}", "noindex": noindex,
        "facts": facts,
        "target_description": " / ".join(tgt_vals[:3]),
        "benefit_description": " / ".join(ben_vals[:3]),
    }

def collect_life_events():
    """目的別ページ docs/area/tokyo/<slug>/<event>/ から program_id -> {event} を復元"""
    pe = {}
    for slug in SLUGS.values():
        for ev in EVENTS:
            fp = os.path.join(DOCS, "area", "tokyo", slug, ev, "index.html")
            if not os.path.exists(fp):
                continue
            t = open(fp, encoding="utf-8").read()
            for pid in set(int(x) for x in re.findall(r"/seido/(\d+)/", t)):
                pe.setdefault(pid, set()).add(ev)
    return pe

# ── DB 構築 ──────────────────────────────────────────────────────────
def main():
    if os.path.exists(OUT_DB):
        os.remove(OUT_DB)
    con = sqlite3.connect(OUT_DB)
    con.executescript(open(SCHEMA, encoding="utf-8").read())
    c = con.cursor()

    # municipalities（SLUGS の順で id 付与。公式URLは生成物から回収）
    muni_urls = recover_muni_urls()
    muni_id = {}
    for i, (name, slug) in enumerate(SLUGS.items(), start=1):
        muni_id[name] = i
        c.execute("""INSERT INTO municipalities
            (id,prefecture_code,prefecture_name,municipality_code,municipality_name,
             municipality_type,official_site_url,is_active)
            VALUES (?,?,?,?,?,?,?,1)""",
            (i, "13", "東京都", None, name, muni_type(name),
             muni_urls.get(slug, f"https://www.example.invalid/{slug}")))

    # life_events
    le_id = {}
    for slug, name in EVENTS.items():
        c.execute("INSERT INTO life_events (slug,name,sort_order) VALUES (?,?,?)",
                  (slug, name, EVENT_ORDER[slug]))
        le_id[slug] = c.lastrowid

    pe = collect_life_events()

    n_prog = n_fact = n_ple = 0
    seen_pid = set()
    for fp in glob.glob(os.path.join(DOCS, "area", "tokyo", "*", "seido", "*", "index.html")):
        p = parse_program_page(fp)
        if not p or p["id"] in seen_pid:
            continue
        seen_pid.add(p["id"])
        reliability = "needs_review" if p["noindex"] else "reviewed"
        conf = 60 if p["noindex"] else 85     # gate: index は avg>=82 が必要
        c.execute("""INSERT INTO programs
            (id,title,program_type,summary,plain_summary,target_description,benefit_description,
             status,official_url,reliability_status,last_verified_at)
            VALUES (?,?,?,?,?,?,?, 'active', ?,?,?)""",
            (p["id"], p["title"], p["program_type"], p["summary"], p["summary"],
             p["target_description"], p["benefit_description"],
             p["official_url"], reliability, p["verified"]))
        n_prog += 1
        c.execute("""INSERT OR IGNORE INTO program_municipalities
            (program_id,municipality_id,area_scope) VALUES (?,?, 'municipal')""",
            (p["id"], muni_id[p["muni"]]))
        for ft, val, evurl in p["facts"]:
            c.execute("""INSERT INTO program_facts
                (program_id,fact_type,value,evidence_url,confidence_score,
                 extraction_method,reviewed_status)
                VALUES (?,?,?,?,?, 'reconstructed_from_docs', ?)""",
                (p["id"], ft, val, evurl, conf,
                 "reviewed" if not p["noindex"] else "needs_review"))
            n_fact += 1
        for ev in sorted(pe.get(p["id"], []), key=lambda e: EVENT_ORDER[e]):
            c.execute("""INSERT INTO program_life_events
                (program_id,life_event_id,relevance_score) VALUES (?,?,?)""",
                (p["id"], le_id[ev], 100 - EVENT_ORDER[ev]))
            n_ple += 1

    con.commit()
    print(f"DB復元完了: {OUT_DB}")
    print(f"  municipalities={len(muni_id)}  life_events={len(le_id)}")
    print(f"  programs={n_prog}  program_facts={n_fact}  program_life_events={n_ple}")
    con.close()

if __name__ == "__main__":
    main()
