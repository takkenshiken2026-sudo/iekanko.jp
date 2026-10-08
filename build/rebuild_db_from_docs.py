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
DOCS = os.environ.get("SEIDO_DOCS", os.path.join(ROOT, "docs"))  # 入力docs（サンドボックス検証用に上書き可）

# 都道府県レジストリ（単一ソース。build_site.py と共有）。DB非依存なので復元時でも安全に import 可。
sys.path.insert(0, os.path.join(ROOT, "build"))
from pref_registry import PREFECTURES, SLUGS_BY_PREF, SLUG2CODE

# 自治体スラッグ -> 公式サイトURL（生成物の JSON-LD provider.url から回収）
def recover_muni_urls():
    prov = re.compile(r'"provider":\s*\{[^}]*?"url":\s*"(https?://[^"]+)"')
    out = {}
    for fp in glob.glob(os.path.join(DOCS, "area", "*", "*", "seido", "*", "index.html")):
        mm = re.search(r"/area/([^/]+)/([^/]+)/seido", fp.replace("\\", "/"))
        key = (mm.group(1), mm.group(2))   # (都道府県スラッグ, 自治体スラッグ)
        if key in out:
            continue
        m = prov.search(open(fp, encoding="utf-8").read())
        if m:
            out[key] = m.group(1)
    return out
SCHEMA = os.path.join(ROOT, "build", "schema.sql")
OUT_DB = sys.argv[1] if len(sys.argv) > 1 else os.path.join(ROOT, "gov_life_support.sqlite3")

# ── 対応表（build_site.py と単一ソース = pref_registry から導出）─────────────
# pref_slug -> {muni_slug: 自治体名}（復元時のパス解釈に使用）
SLUG2NAME_BY_PREF = {PREFECTURES[code][0]: {s: n for n, s in name2slug.items()}
                     for code, name2slug in SLUGS_BY_PREF.items()}
# 互換: 全県フラットな name->slug / slug->name（同名自治体の衝突は muni は (県,名) で解決）
SLUGS = {n: s for name2slug in SLUGS_BY_PREF.values() for n, s in name2slug.items()}
SLUG2NAME = {s: n for name2slug in SLUGS_BY_PREF.values() for n, s in name2slug.items()}

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
    m = re.search(r"/area/([^/]+)/([^/]+)/seido/(\d+)/index\.html$", fp.replace("\\", "/"))
    pref_slug, slug, pid = m.group(1), m.group(2), int(m.group(3))
    mn = SLUG2NAME_BY_PREF.get(pref_slug, {}).get(slug)
    if not mn:
        return None
    pref_code = SLUG2CODE.get(pref_slug, "13")
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
        "id": pid, "slug": slug, "muni": mn, "pref_code": pref_code, "title": title or "制度",
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
    """目的別ページ docs/area/<pref>/<slug>/<event>/ から program_id -> {event} を復元"""
    pe = {}
    for code, name2slug in SLUGS_BY_PREF.items():
        pref = PREFECTURES[code][0]
        for slug in name2slug.values():
            for ev in EVENTS:
                fp = os.path.join(DOCS, "area", pref, slug, ev, "index.html")
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

    # municipalities（都道府県レジストリの順で id 付与。公式URLは生成物から回収）
    # 東京を先頭に、県ごとに連番。muni_id は (都道府県コード, 自治体名) で引く（同名衝突回避）。
    muni_urls = recover_muni_urls()
    muni_id = {}
    i = 0
    for code, name2slug in SLUGS_BY_PREF.items():
        pref_slug, pref_name = PREFECTURES[code][0], PREFECTURES[code][1]
        for name, slug in name2slug.items():
            i += 1
            muni_id[(code, name)] = i
            c.execute("""INSERT INTO municipalities
                (id,prefecture_code,prefecture_name,municipality_code,municipality_name,
                 municipality_type,official_site_url,is_active)
                VALUES (?,?,?,?,?,?,?,1)""",
                (i, code, pref_name, None, name, muni_type(name),
                 muni_urls.get((pref_slug, slug), f"https://www.example.invalid/{slug}")))

    # life_events
    le_id = {}
    for slug, name in EVENTS.items():
        c.execute("INSERT INTO life_events (slug,name,sort_order) VALUES (?,?,?)",
                  (slug, name, EVENT_ORDER[slug]))
        le_id[slug] = c.lastrowid

    pe = collect_life_events()

    n_prog = n_fact = n_ple = 0
    seen_pid = set()
    for fp in glob.glob(os.path.join(DOCS, "area", "*", "*", "seido", "*", "index.html")):
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
            (p["id"], muni_id[(p["pref_code"], p["muni"])]))
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
