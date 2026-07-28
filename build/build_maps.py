#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""東京都62市区町村の位置マップSVGを生成する（docs/assets/maps/<slug>.svg）。
本土(23区+多摩)は境界ポリゴンを描画し対象地域をハイライト。島しょ部は本土地図＋南方マーカー。
データ: 公開GeoJSON(dataofjapan/land)。生成物(SVG)はリポジトリにコミットし、build_site.py は
<img>で参照するだけ（DB再生成の対象外の静的アセット）。手動再生成用。"""
import json, math, os, re, ast, sys, urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT  = os.path.join(ROOT, "docs", "assets", "maps")
GEO_URL = "https://raw.githubusercontent.com/dataofjapan/land/master/tokyo.geojson"
CACHE = os.environ.get("TOKYO_GEOJSON", "/tmp/claude-0/-home-user-iekanko-jp/f8d4a443-cc9d-5d70-8bc1-543550627f3f/scratchpad/tokyo.geojson")

ISLANDS = {"大島町","利島村","新島村","神津島村","三宅村","御蔵島村","八丈町","青ヶ島村","小笠原村"}
ACCENT="#1558d6"; LAND="#dfe4ec"; LINE="#ffffff"; SEA="#eef2f7"

def load_geo():
    if os.path.exists(CACHE):
        return json.load(open(CACHE, encoding="utf-8"))
    data=urllib.request.urlopen(GEO_URL, timeout=60).read()
    open(CACHE,"wb").write(data)
    return json.loads(data)

def slugs():
    src=open(os.path.join(ROOT,"build","build_site.py"),encoding="utf-8").read()
    return ast.literal_eval(re.search(r'\nSLUGS = (\{.*?\n\})\n',src,re.S).group(1))

def rings(geom):
    """exterior rings only, as list of [ [lon,lat],... ]"""
    t=geom["type"]; cs=geom["coordinates"]
    out=[]
    if t=="Polygon": out.append(cs[0])
    elif t=="MultiPolygon":
        for poly in cs: out.append(poly[0])
    return out

def ring_area(r):
    a=0
    for i in range(len(r)-1):
        a+=r[i][0]*r[i+1][1]-r[i+1][0]*r[i][1]
    return abs(a)/2

def main():
    gj=load_geo(); SL=slugs()
    name2geom={f["properties"].get("ward_ja"):f["geometry"] for f in gj["features"]}
    mainland=[n for n in SL if n not in ISLANDS]
    # projection over mainland extent
    lons=[];lats=[]
    for n in mainland:
        for r in rings(name2geom[n]):
            for x,y in r: lons.append(x); lats.append(y)
    lon0,lon1=min(lons),max(lons); lat0,lat1=min(lats),max(lats)
    latm=(lat0+lat1)/2; kx=math.cos(math.radians(latm))
    W=760.0; pad=14.0
    sx=(W-2*pad)/((lon1-lon0)*kx)
    H=(lat1-lat0)*sx+2*pad
    def proj(x,y):
        return (pad+(x-lon0)*kx*sx, pad+(lat1-y)*sx)
    def _pd(p,a,b):
        (x,y),(x1,y1),(x2,y2)=p,a,b
        dx,dy=x2-x1,y2-y1
        if dx==0 and dy==0: return math.hypot(x-x1,y-y1)
        t=((x-x1)*dx+(y-y1)*dy)/(dx*dx+dy*dy)
        t=max(0,min(1,t))
        return math.hypot(x-(x1+t*dx),y-(y1+t*dy))
    def dp(pts,eps):
        if len(pts)<3: return pts
        dmax=0;idx=0
        for i in range(1,len(pts)-1):
            d=_pd(pts[i],pts[0],pts[-1])
            if d>dmax: dmax=d;idx=i
        if dmax>eps:
            return dp(pts[:idx+1],eps)[:-1]+dp(pts[idx:],eps)
        return [pts[0],pts[-1]]
    EPS=1.1
    def path_d(name):
        ds=[]
        rs=rings(name2geom[name])
        amax=max(ring_area(r) for r in rs) if rs else 0
        for r in rs:
            if ring_area(r) < amax*0.06:   # 細かな飛び地・海岸の小片は省略
                continue
            pts=[proj(x,y) for x,y in r]
            pts=dp(pts,EPS)                 # Douglas-Peucker で点を大幅削減
            pts=[(int(round(a)),int(round(b))) for a,b in pts]
            out=[];last=None
            for p in pts:
                if p!=last: out.append(p); last=p
            if len(out)<3: continue
            ds.append("M"+" ".join(f"{a} {b}" for a,b in out)+"Z")
        return "".join(ds)
    dpaths={n:path_d(n) for n in mainland}
    # 島しょ部の重心（南方マーカー用）
    def centroid(name):
        rs=rings(name2geom[name]); big=max(rs,key=ring_area)
        xs=[p[0] for p in big]; ys=[p[1] for p in big]
        return sum(xs)/len(xs), sum(ys)/len(ys)

    style=(f"<style>.mreg{{fill:{LAND};stroke:{LINE};stroke-width:1;stroke-linejoin:round}}"
           f".mreg.on{{fill:{ACCENT}}}.mk{{fill:{ACCENT}}}.mkt{{fill:#33404f;"
           f"font:600 15px 'Noto Sans JP',sans-serif}}.mnote{{fill:#5b6577;font:500 12px sans-serif}}</style>")
    Hs=round(H,1)

    os.makedirs(OUT, exist_ok=True)
    for name,slug in SL.items():
        parts=[f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {int(W)} {Hs}" '
               f'role="img" aria-label="東京都における{name}の位置" preserveAspectRatio="xMidYMid meet">',
               f'<rect x="0" y="0" width="{int(W)}" height="{Hs}" fill="{SEA}"/>', style,'<g>']
        is_isl = name in ISLANDS
        for n in mainland:
            cls="mreg on" if (n==name) else "mreg"
            parts.append(f'<path class="{cls}" d="{dpaths[n]}"/>')
        parts.append('</g>')
        if is_isl:
            # 本土は文脈として灰色、対象島を南方マーカーで示す
            cx=W*0.5; cy=Hs-26
            parts.append(f'<circle class="mk" cx="{cx:.0f}" cy="{cy:.0f}" r="7"/>')
            parts.append(f'<text class="mkt" x="{cx+13:.0f}" y="{cy+5:.0f}">{name}（島しょ部）</text>')
            parts.append(f'<text class="mnote" x="{cx-150:.0f}" y="{cy-14:.0f}">▼ 東京都の南方海上（伊豆・小笠原諸島）</text>')
        parts.append('</svg>')
        svg="".join(parts)
        open(os.path.join(OUT,f"{slug}.svg"),"w",encoding="utf-8").write(svg)
    print(f"wrote {len(SL)} maps to {OUT}  (viewBox 760x{Hs})")

    # ── 対話マップ（トップのヒーロー用。全自治体クリック可能＋ホバーで名称表示）──
    ISLE_ORDER=["大島町","利島村","新島村","神津島村","三宅村","御蔵島村","八丈町","青ヶ島村","小笠原村"]
    isle_h=48; ivH=round(Hs+isle_h,1)
    istyle=(f"<style>.mr{{fill:{LAND};stroke:{LINE};stroke-width:1;stroke-linejoin:round;"
            f"cursor:pointer;transition:fill .12s}}a:hover .mr,a:focus .mr{{fill:{ACCENT}}}"
            f".mk{{fill:#8aa0bf;cursor:pointer;transition:fill .12s}}a:hover .mk,a:focus .mk{{fill:{ACCENT}}}"
            f".isl{{fill:#5b6577;font:600 12px 'Noto Sans JP',sans-serif}}"
            f".idv{{stroke:#d7dde7;stroke-width:1}}</style>")
    ip=[f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {int(W)} {ivH}" '
        f'role="img" aria-label="東京都の市区町村マップ。クリックで各自治体のページへ移動できます。" '
        f'preserveAspectRatio="xMidYMid meet" class="tokyomap">',
        f'<rect x="0" y="0" width="{int(W)}" height="{ivH}" fill="{SEA}"/>', istyle, '<g>']
    for name in mainland:
        slug=SL[name]
        ip.append(f'<a href="/area/tokyo/{slug}/" aria-label="{name}">'
                  f'<path class="mr" d="{dpaths[name]}"><title>{name}</title></path></a>')
    ip.append('</g>')
    ip.append(f'<line class="idv" x1="0" y1="{Hs}" x2="{int(W)}" y2="{Hs}"/>')
    ip.append(f'<text class="isl" x="14" y="{Hs+28:.0f}">島しょ部</text>')
    n=len(ISLE_ORDER); x0=120.0; x1=W-26; gap=(x1-x0)/(n-1)
    for i,name in enumerate(ISLE_ORDER):
        slug=SL[name]; cx=x0+i*gap; cy=Hs+23
        ip.append(f'<a href="/area/tokyo/{slug}/" aria-label="{name}">'
                  f'<circle class="mk" cx="{cx:.0f}" cy="{cy:.0f}" r="7"><title>{name}</title></circle></a>')
    ip.append('</svg>')
    open(os.path.join(OUT,"tokyo-interactive.svg"),"w",encoding="utf-8").write("".join(ip))
    print("wrote interactive map: tokyo-interactive.svg")

    # サイズ目安
    import glob
    sizes=[os.path.getsize(p) for p in glob.glob(os.path.join(OUT,'*.svg'))]
    print("svg bytes: min",min(sizes),"max",max(sizes),"avg",sum(sizes)//len(sizes))

if __name__=="__main__":
    main()
