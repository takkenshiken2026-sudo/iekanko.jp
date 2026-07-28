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
CACHE = os.environ.get("TOKYO_GEOJSON", "/tmp/tokyo.geojson")

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

    # ── 対話マップ（トップのヒーロー用。本土53＋島しょ部9を同一SVGに内包）──
    # 島しょ部は地理的に遠いため、地図下のインセットパネルに拡大配置する。
    ILAND="#9eafc6"; ISEA="#ffffff"; ILINE="#ffffff"
    ISLE_ORDER=["大島町","利島村","新島村","神津島村","三宅村","御蔵島村","八丈町","青ヶ島村","小笠原村"]

    def isle_path(name, bx,by,bw,bh, pad=3, eps=0.45):
        rs=rings(name2geom[name]); amax=max(ring_area(r) for r in rs) if rs else 0
        keep=[r for r in rs if ring_area(r) >= amax*0.04] or rs
        if name=="小笠原村":
            keep=sorted(rs, key=ring_area, reverse=True)[:4]
        pts=[p for r in keep for p in r]
        if not pts: return ""
        lon0=min(p[0] for p in pts); lon1=max(p[0] for p in pts)
        lat0=min(p[1] for p in pts); lat1=max(p[1] for p in pts)
        if lon1-lon0 < 0.02:
            mid=(lon0+lon1)/2; lon0,lon1=mid-0.03, mid+0.03
        if lat1-lat0 < 0.02:
            mid=(lat0+lat1)/2; lat0,lat1=mid-0.03, mid+0.03
        pad_lon=(lon1-lon0)*0.18; pad_lat=(lat1-lat0)*0.18
        lon0-=pad_lon; lon1+=pad_lon; lat0-=pad_lat; lat1+=pad_lat
        kx=math.cos(math.radians((lat0+lat1)/2))
        sx=(bw-2*pad)/max((lon1-lon0)*kx,1e-9)
        sy=(bh-2*pad)/max(lat1-lat0,1e-9)
        s=min(sx,sy)
        def proj(x,y): return bx+pad+(x-lon0)*kx*s, by+pad+(lat1-y)*s
        allp=[]; ds=[]
        for r in keep:
            pts2=[proj(x,y) for x,y in r]
            pts2=dp(pts2, eps)
            pts2=[(round(a,1),round(b,1)) for a,b in pts2]
            out=[]; last=None
            for p in pts2:
                if p!=last: out.append(p); last=p
            if len(out)<3: continue
            area2=abs(sum(out[i][0]*out[(i+1)%len(out)][1]-out[(i+1)%len(out)][0]*out[i][1]
                          for i in range(len(out))))
            if area2 < 2: continue
            allp.extend(out); ds.append(out)
        if not allp: return ""
        minx=min(p[0] for p in allp); maxx=max(p[0] for p in allp)
        miny=min(p[1] for p in allp); maxy=max(p[1] for p in allp)
        if max(maxx-minx, maxy-miny) < 10: return ""
        tx=bx+bw/2-(minx+maxx)/2; ty=by+bh/2-(miny+maxy)/2
        return "".join("M"+" ".join(f"{a+tx:.1f} {b+ty:.1f}" for a,b in out)+"Z" for out in ds)

    def isle_shape(name, bx,by,bw,bh):
        d=isle_path(name, bx,by,bw,bh)
        if d: return f'<path class="mr" d="{d}"/>'
        cx=bx+bw/2; cy=by+bh/2
        rx=min(14, bw*0.32); ry=min(18, bh*0.38)
        return f'<ellipse class="mr" cx="{cx:.1f}" cy="{cy:.1f}" rx="{rx:.1f}" ry="{ry:.1f}"/>'

    INSET_TOP=round(H+7.2,1); INSET_H=100.0; H_I=INSET_TOP+INSET_H+8
    izu=ISLE_ORDER[:-1]; oga=ISLE_ORDER[-1]
    gap_oga=18; oga_w=88; mx=20
    left=mx; right=W-mx-oga_w-gap_oga
    cell_w=(right-left)/len(izu)
    shape_top=INSET_TOP+10; shape_h=INSET_H-20

    istyle=(f"<style>.mr{{fill:{ILAND};stroke:{ILINE};stroke-width:1.15;stroke-linejoin:round;"
            f"cursor:pointer;transition:fill .12s}}a:hover .mr,a:focus .mr{{fill:{ACCENT}}}"
            f".isle-bg{{fill:#f5f7fb;stroke:#d7dde8;stroke-width:1}}"
            f".isle-div{{stroke:#c5cedes;stroke-width:1;stroke-dasharray:3 3}}</style>")
    ip=[f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {int(W)} {H_I}" '
        f'role="img" aria-label="東京都の市区町村マップ（本土と島しょ部）。クリックで各自治体のページへ移動できます。" '
        f'preserveAspectRatio="xMidYMid meet" class="tokyomap">',
        f'<rect x="0" y="0" width="{int(W)}" height="{H_I}" fill="{ISEA}"/>', istyle, '<g>']
    for name in mainland:
        slug=SL[name]
        ip.append(f'<a href="/area/tokyo/{slug}/" aria-label="{name}">'
                  f'<path class="mr" d="{dpaths[name]}"><title>{name}</title></path></a>')
    ip.append('</g>')
    # 島しょ部インセット（本土の下。伊豆諸島＋区切り＋小笠原）
    ip.append('<g class="isle-panel" aria-label="島しょ部">')
    ip.append(f'<rect class="isle-bg" x="12" y="{INSET_TOP}" width="736" height="{INSET_H}" rx="8"/>')
    div_x=right+gap_oga/2
    ip.append(f'<line class="isle-div" x1="{div_x:.1f}" y1="{INSET_TOP+14}" x2="{div_x:.1f}" y2="{INSET_TOP+INSET_H-14}"/>')
    for i,name in enumerate(izu):
        bx=left+i*cell_w
        shape=isle_shape(name, bx+2, shape_top, cell_w-4, shape_h)
        slug=SL[name]
        ip.append(f'<a href="/area/tokyo/{slug}/" aria-label="{name}">{shape}<title>{name}</title></a>')
    bx=W-mx-oga_w
    shape=isle_shape(oga, bx+2, shape_top, oga_w-4, shape_h)
    slug=SL[oga]
    ip.append(f'<a href="/area/tokyo/{slug}/" aria-label="{oga}">{shape}<title>{oga}</title></a>')
    ip.append('</g></svg>')
    open(os.path.join(OUT,"tokyo-interactive.svg"),"w",encoding="utf-8").write("".join(ip))
    print("wrote interactive map: tokyo-interactive.svg (with island inset)")

    # サイズ目安
    import glob
    sizes=[os.path.getsize(p) for p in glob.glob(os.path.join(OUT,'*.svg'))]
    print("svg bytes: min",min(sizes),"max",max(sizes),"avg",sum(sizes)//len(sizes))

if __name__=="__main__":
    main()
