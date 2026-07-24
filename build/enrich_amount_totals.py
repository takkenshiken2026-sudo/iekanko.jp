#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
既存の docs/ から制度ページの支給額を集計し、
自治体ハブ・イベント一覧・ランキングに「金額合計」を追記する。

元DBが無くても docs だけで反映できる。
"""
from __future__ import annotations

import html as html_mod
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "docs")
EVENTS = (
    "pregnancy_birth",
    "childcare",
    "moving",
    "retirement_unemployment",
    "elderly_care",
)

sys.path.insert(0, os.path.join(ROOT, "build"))
# build_site の抽出関数だけ取り出す（DB接続前まで）
_code = open(os.path.join(ROOT, "build", "build_site.py"), encoding="utf-8").read()
_code = _code.split("\ncon = sqlite3.connect")[0]
_ns = {"__file__": os.path.join(ROOT, "build", "build_site.py"), "__name__": "build_site_partial"}
exec(_code, _ns)
extract_any_yen = _ns["extract_any_yen"]
format_sum_yen = _ns["format_sum_yen"]
EVENTS_META = _ns["EVENTS"]
EV_META = _ns["EV_META"]


def esc(s):
    return html_mod.escape(str(s or ""), quote=True)


def svg_bars(rows, maxval=100, unit="%"):
    """rows: [(label, value, avg_or_None, note_or_'')]"""
    W = 560
    padL = 118
    padR = 92
    barH = 16
    rowH = 31
    top = 10
    plotW = W - padL - padR
    H = top + rowH * len(rows) + 6
    p = [f'<svg viewBox="0 0 {W} {H}" class="chart" role="img" preserveAspectRatio="xMinYMin meet">']
    for i, (label, val, avg, note) in enumerate(rows):
        y = top + rowH * i
        cy = y + barH / 2
        bw = plotW * (min(val, maxval) / maxval if maxval else 0)
        p.append(
            f'<text x="{padL-8}" y="{cy:.0f}" class="c-lbl" text-anchor="end" '
            f'dominant-baseline="central">{esc(label)}</text>'
        )
        p.append(f'<rect x="{padL}" y="{y}" width="{plotW}" height="{barH}" rx="4" class="c-track"/>')
        p.append(
            f'<rect x="{padL}" y="{y}" width="{max(bw, 3):.1f}" height="{barH}" rx="4" class="c-bar"/>'
        )
        vlab = f"{val:.0f}{unit}" + (f" · {esc(note)}" if note else "")
        p.append(
            f'<text x="{padL+bw+6:.1f}" y="{cy:.0f}" class="c-val" dominant-baseline="central">{vlab}</text>'
        )
    p.append("</svg>")
    return "".join(p)


def amount_from_program(slug: str, pid: str):
    path = os.path.join(OUT, "area", "tokyo", slug, "seido", str(pid), "index.html")
    if not os.path.isfile(path):
        return None
    t = open(path, encoding="utf-8").read()
    m = re.search(r"<dt>支給額・助成額</dt><dd>(.*?)</dd>", t, re.S)
    if not m:
        return None
    plain = re.sub(r"<a[^>]*>.*?</a>", "", m.group(1))
    plain = re.sub(r"<[^>]+>", "", plain)
    return extract_any_yen(plain)


def programs_on_event_page(slug: str, ev: str):
    path = os.path.join(OUT, "area", "tokyo", slug, ev, "index.html")
    if not os.path.isfile(path):
        return []
    t = open(path, encoding="utf-8").read()
    return re.findall(rf'/area/tokyo/{re.escape(slug)}/seido/(\d+)/', t)


def sum_for(slug: str, pids):
    total = 0
    n = 0
    seen = set()
    for pid in pids:
        if pid in seen:
            continue
        seen.add(pid)
        yen = amount_from_program(slug, pid)
        if yen:
            total += yen
            n += 1
    return total, n


def cnt_html(n_prog, yen_sum):
    s = f'<span class="cnt">{n_prog}</span>'
    if yen_sum:
        s += (
            f'<span class="csum" title="金額が分かる制度の合計（上限・月額などの目安）">'
            f'計{html_mod.escape(format_sum_yen(yen_sum))}</span>'
        )
    return s


def patch_muni_hub(slug: str):
    path = os.path.join(OUT, "area", "tokyo", slug, "index.html")
    if not os.path.isfile(path):
        return False
    html = open(path, encoding="utf-8").read()
    changed = False
    total_pids = []
    for ev in EVENTS:
        # section for this event
        pat = re.compile(
            rf'(<section class="ev"[^>]*>\s*<h2>.*?<a href="/area/tokyo/{re.escape(slug)}/{ev}/">.*?</a></span>)'
            rf'(?:<span class="cnt">\d+</span>(?:<span class="csum"[^>]*>.*?</span>)?)?(</h2>)',
            re.S,
        )
        pids = programs_on_event_page(slug, ev)
        # fallback: ids listed inside the hub section
        if not pids:
            msec = re.search(
                rf'<section class="ev"[^>]*>.*?/{ev}/.*?</section>',
                html,
                re.S,
            )
            if msec:
                pids = re.findall(rf'/area/tokyo/{re.escape(slug)}/seido/(\d+)/', msec.group(0))
        yen_sum, _n = sum_for(slug, pids)
        total_pids.extend(pids)

        def repl(m, yen_sum=yen_sum):
            # 件数は既存の数字を維持し、金額合計だけ付与
            existing = re.search(r'<span class="cnt">(\d+)</span>', m.group(0))
            n = int(existing.group(1)) if existing else len(set(pids))
            return m.group(1) + cnt_html(n, yen_sum) + m.group(2)

        new_html, nsub = pat.subn(repl, html, count=1)
        if nsub:
            html = new_html
            changed = True

    # lead line
    total_yen, total_n = sum_for(slug, total_pids)
    # also count unique programs from all seido dirs for lead
    seido_dir = os.path.join(OUT, "area", "tokyo", slug, "seido")
    all_pids = []
    if os.path.isdir(seido_dir):
        all_pids = [d for d in os.listdir(seido_dir) if d.isdigit()]
    total_yen, total_n = sum_for(slug, all_pids)
    n_progs = len(all_pids)

    lead_pat = re.compile(
        r'(<p class="lead">[^<]*?)（全\d+件(?:・金額が分かるもの合計[^）]*）)?・出典/最終確認日つき）。</p>'
    )
    lead_extra = f"全{n_progs}件"
    if total_yen:
        lead_extra += f"・金額が分かるもの合計{format_sum_yen(total_yen)}（{total_n}件）"

    def lead_repl(m):
        # rebuild from municipality name already in lead
        prefix = m.group(1)
        # strip old（全N件...） if partially captured wrong — rebuild whole paren
        prefix = re.sub(r'（全\d+件(?:・金額が分かるもの合計[^）]*)?$', '', prefix)
        return f'{prefix}（{html_mod.escape(lead_extra)}・出典/最終確認日つき）。</p>'

    new_html, nsub = lead_pat.subn(lead_repl, html, count=1)
    if nsub:
        html = new_html
        changed = True
    else:
        # simpler replace
        new_html2, nsub2 = re.subn(
            r'（全\d+件(?:・金額が分かるもの合計[^）]*）)?・出典/最終確認日つき）',
            f'（{html_mod.escape(lead_extra)}・出典/最終確認日つき）',
            html,
            count=1,
        )
        if nsub2:
            html = new_html2
            changed = True

    if changed:
        open(path, "w", encoding="utf-8").write(html)
    return changed


def patch_muni_event(slug: str, ev: str):
    path = os.path.join(OUT, "area", "tokyo", slug, ev, "index.html")
    if not os.path.isfile(path):
        return False
    html = open(path, encoding="utf-8").read()
    pids = programs_on_event_page(slug, ev)
    yen_sum, n_amt = sum_for(slug, pids)
    extra = ""
    if yen_sum:
        extra = f'・金額が分かるもの合計 {html_mod.escape(format_sum_yen(yen_sum))}（{n_amt}件）'
    new_html, nsub = re.subn(
        r'(<p class="meta">[^<]*関連の制度 )(\d+)件(?:・金額が分かるもの合計[^<]*)?(</p>)',
        rf'\g<1>\2件{extra}\3',
        html,
        count=1,
    )
    if not nsub:
        return False
    open(path, "w", encoding="utf-8").write(new_html)
    return True


def patch_ranking(ev: str):
    path = os.path.join(OUT, "ranking", ev, "index.html")
    if not os.path.isfile(path):
        return False
    html = open(path, encoding="utf-8").read()
    # rows: slug, name, n_prog
    rows = []
    for m in re.finditer(
        rf'<tr[^>]*>\s*<td class="rk">\d+</td>\s*'
        rf'<td class="mn"><a href="/area/tokyo/([^/]+)/{ev}/">([^<]+)</a></td>\s*'
        rf'<td class="dt">(\d+)制度</td>'
        rf'(?:<td class="dt yen">[^<]*</td>)?',
        html,
    ):
        slug, name, n = m.group(1), m.group(2), int(m.group(3))
        pids = programs_on_event_page(slug, ev)
        yen_sum, _ = sum_for(slug, pids)
        rows.append((slug, name, n, yen_sum))

    if not rows:
        return False

    # rebuild table body
    trs = []
    for rank, (slug, name, n, yen_sum) in enumerate(rows, 1):
        cls = ' class="top3"' if rank <= 3 else ""
        yen_cell = f'計{esc(format_sum_yen(yen_sum))}' if yen_sum else "—"
        trs.append(
            f'<tr{cls}><td class="rk">{rank}</td>'
            f'<td class="mn"><a href="/area/tokyo/{slug}/{ev}/">{esc(name)}</a></td>'
            f'<td class="dt">{n}制度</td>'
            f'<td class="dt yen">{yen_cell}</td></tr>'
        )
    html = re.sub(
        r'<thead><tr><th>順位</th><th>自治体</th><th>制度数</th>(?:<th>[^<]*</th>)?</tr></thead>\s*'
        r'<tbody>.*?</tbody>',
        '<thead><tr><th>順位</th><th>自治体</th><th>制度数</th><th>金額合計（目安）</th></tr></thead>\n'
        f'<tbody>{"".join(trs)}</tbody>',
        html,
        count=1,
        flags=re.S,
    )

    # chart top 15
    top = rows[:15]
    max_prog = max((n for _, _, n, _ in top), default=1) or 1
    chart_rows = []
    for name, n, yen in ((r[1], r[2], r[3]) for r in top):
        note = f'計{format_sum_yen(yen)}' if yen else ""
        chart_rows.append((name, n, None, note))
    chart = svg_bars(chart_rows, max_prog, "制度")
    html = re.sub(
        r'<div class="chartcard"[^>]*>.*?</svg>\s*<p class="cap">.*?</p></div>',
        lambda m: (
            re.match(r'<div class="chartcard"[^>]*>', m.group(0)).group(0)
            + chart
            + '<p class="cap">上位15自治体の掲載制度数と金額合計</p></div>'
        ),
        html,
        count=1,
        flags=re.S,
    )

    html = html.replace(
        "件数が多い自治体から順に並べています。</p>",
        "件数が多い自治体から順に並べています。金額が分かる制度の合計（上限・月額などの目安）も併記します。</p>",
    )
    html = re.sub(
        r'<p class="notice">掲載件数は当サイトの収録状況に基づく目安です。金額の多寡や実際の手厚さを示すものではありません。[^<]*</p>',
        '<p class="notice">掲載件数・金額合計は当サイトの収録状況に基づく目安です。月額と一時金を単純合算しているため、実際の手厚さや受給可否を示すものではありません。詳細・申請可否は各自治体の公式ページでご確認ください。</p>',
        html,
        count=1,
    )
    html = re.sub(
        r'<title>[^<]*</title>',
        f'<title>{EVENTS_META[ev][0]}の制度がある東京都の自治体｜掲載数・金額でみる</title>',
        html,
        count=1,
    )
    open(path, "w", encoding="utf-8").write(html)
    return True


def patch_find_hub():
    path = os.path.join(OUT, "find", "index.html")
    if not os.path.isfile(path):
        return False
    html = open(path, encoding="utf-8").read()
    changed = False
    for ev in EVENTS:
        # find top municipality from ranking page order
        rpath = os.path.join(OUT, "ranking", ev, "index.html")
        if not os.path.isfile(rpath):
            continue
        rt = open(rpath, encoding="utf-8").read()
        m = re.search(
            rf'<tr class="top3"><td class="rk">1</td><td class="mn"><a href="/area/tokyo/([^/]+)/{ev}/">([^<]+)</a></td>'
            rf'<td class="dt">(\d+)制度</td>(?:<td class="dt yen">計([^<]+)</td>)?',
            rt,
        )
        if not m:
            continue
        slug, name, n, yen_label = m.group(1), m.group(2), m.group(3), m.group(4)
        note = f"掲載数が多い例：{name}（{n}制度"
        if yen_label:
            note += f"・計{yen_label}"
        note += "）"
        new_html, nsub = re.subn(
            rf'(<a class="pcard" href="/ranking/{ev}/"[^>]*>.*?)<span class="ptop">[^<]*</span>',
            rf'\1<span class="ptop">{html_mod.escape(note)}</span>',
            html,
            count=1,
            flags=re.S,
        )
        if nsub:
            html = new_html
            changed = True
    if "金額が分かる制度の合計" not in html:
        html = html.replace(
            "にお使いください。</p>",
            "にお使いください。金額が分かる制度の合計もあわせて表示します。</p>",
            1,
        )
        html = html.replace(
            "※掲載件数は当サイトの収録状況に基づく目安です。",
            "※掲載件数・金額合計は当サイトの収録状況に基づく目安です。",
            1,
        )
        changed = True
    if changed:
        open(path, "w", encoding="utf-8").write(html)
    return changed


def main():
    area = os.path.join(OUT, "area", "tokyo")
    hubs = events = ranks = 0
    for slug in sorted(os.listdir(area)):
        if not os.path.isdir(os.path.join(area, slug)):
            continue
        if patch_muni_hub(slug):
            hubs += 1
        for ev in EVENTS:
            if patch_muni_event(slug, ev):
                events += 1
    for ev in EVENTS:
        if patch_ranking(ev):
            ranks += 1
    find_ok = patch_find_hub()
    print(f"hubs={hubs} events={events} ranks={ranks} find={find_ok}")


if __name__ == "__main__":
    main()
