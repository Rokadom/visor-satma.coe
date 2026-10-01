#!/usr/bin/env python3
# Radar RD GitHub updater - stdlib only
from __future__ import print_function
import os, re, json, time, ssl, struct, zlib, binascii, math
try:
    from urllib.request import Request, urlopen
    from urllib.parse import urljoin, urlparse, parse_qs
except ImportError:
    from urllib2 import Request, urlopen
    from urlparse import urljoin, urlparse, parse_qs

ROOT = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(ROOT, "radar_rd.json")
LAY = os.path.join(ROOT, "capas")
BASE = "https://www.idac.gob.do/visor-radar/"
UPDATE = urljoin(BASE, "update.php")
UA = "Mozilla/5.0 (Windows NT 6.1; Win64; x64) AppleWebKit/537.36 Chrome/109 Safari/537.36"
RADAR_BOUNDS = [[12.743945, -81.767979], [23.863055, -61.158021]]
NFRAMES = 10

os.makedirs(LAY, exist_ok=True)

def fetch(url, timeout=45, maxbytes=25*1024*1024):
    req = Request(url, headers={
        "User-Agent": UA, "Accept": "*/*", "Cache-Control": "no-cache",
        "Pragma": "no-cache", "Referer": BASE
    })
    last = None
    for ctx in (ssl.create_default_context(), ssl._create_unverified_context()):
        try:
            r = urlopen(req, timeout=timeout, context=ctx)
            try:
                return r.read(maxbytes), r.geturl()
            finally:
                try: r.close()
                except Exception: pass
        except Exception as e:
            last = e
    raise last

def extract_urls(text):
    out, seen = [], set()
    pats = [
        r'(?:src|data-src|data-lazy)\s*=\s*["\']([^"\']*image\.php\?file=[^"\']+)["\']',
        r'["\']([^"\']*image\.php\?file=[^"\']+)["\']'
    ]
    for pat in pats:
        for m in re.findall(pat, text, re.I):
            u = urljoin(BASE, m.replace("&amp;", "&").strip())
            if u not in seen:
                seen.add(u); out.append(u)
    return out

def token(url):
    try:
        return (parse_qs(urlparse(url).query).get("file") or ["frame.png"])[0]
    except Exception:
        return "frame.png"

def tok_ms(s):
    m = re.search(r'(\d{10,13})', str(s or ""))
    if not m: return -1
    t = m.group(1)
    v = int(t)
    return v * 1000 if len(t) == 10 else v

def paeth(a,b,c):
    p=a+b-c; pa=abs(p-a); pb=abs(p-b); pc=abs(p-c)
    if pa<=pb and pa<=pc: return a
    if pb<=pc: return b
    return c

def decode_png_rgba(data):
    if data[:8] != b"\x89PNG\r\n\x1a\n":
        raise ValueError("No es PNG")
    pos=8; idat=[]; w=h=bd=ct=interlace=None; palette=None; trns=None
    while pos+12 <= len(data):
        n=struct.unpack(">I", data[pos:pos+4])[0]
        typ=data[pos+4:pos+8]; payload=data[pos+8:pos+8+n]; pos += 12+n
        if typ==b'IHDR':
            w,h,bd,ct,comp,flt,interlace=struct.unpack(">IIBBBBB", payload)
        elif typ==b'PLTE': palette=payload
        elif typ==b'tRNS': trns=payload
        elif typ==b'IDAT': idat.append(payload)
        elif typ==b'IEND': break
    if bd != 8 or interlace != 0:
        raise ValueError("PNG no soportado")
    channels={0:1,2:3,3:1,4:2,6:4}[ct]
    raw=zlib.decompress(b''.join(idat)); stride=w*channels
    rows=[]; prev=bytearray(stride); off=0
    for y in range(h):
        f=raw[off]; off+=1
        cur=bytearray(raw[off:off+stride]); off+=stride
        for x in range(stride):
            a=cur[x-channels] if x>=channels else 0
            b=prev[x]
            c=prev[x-channels] if x>=channels else 0
            if f==1: cur[x]=(cur[x]+a)&255
            elif f==2: cur[x]=(cur[x]+b)&255
            elif f==3: cur[x]=(cur[x]+((a+b)//2))&255
            elif f==4: cur[x]=(cur[x]+paeth(a,b,c))&255
            elif f!=0: raise ValueError("Filtro PNG no soportado")
        rows.append(cur); prev=cur
    rgba=bytearray(w*h*4); oi=0; pal=[]
    if palette:
        for i in range(0,len(palette),3):
            pal.append(tuple(palette[i:i+3]))
    for row in rows:
        for x in range(w):
            i=x*channels
            if ct==6: r,g,b,a=row[i:i+4]
            elif ct==2: r,g,b=row[i:i+3]; a=255
            elif ct==4: g,a=row[i:i+2]; r=b=g
            elif ct==0: g=row[i]; r=b=g; a=255
            else:
                idx=row[i]
                r,g,b=pal[idx] if idx<len(pal) else (0,0,0)
                a=trns[idx] if trns and idx<len(trns) else 255
            rgba[oi:oi+4]=bytes((r,g,b,a)); oi+=4
    return w,h,rgba

def chunk(typ,payload):
    return struct.pack(">I",len(payload))+typ+payload+struct.pack(">I",binascii.crc32(typ+payload)&0xffffffff)

def encode_rgba_png(w,h,rgba):
    raw=bytearray(); stride=w*4
    for y in range(h):
        raw.append(0)
        raw.extend(rgba[y*stride:(y+1)*stride])
    return (b"\x89PNG\r\n\x1a\n" +
            chunk(b'IHDR',struct.pack(">IIBBBBB",w,h,8,6,0,0,0)) +
            chunk(b'IDAT',zlib.compress(bytes(raw),6)) +
            chunk(b'IEND',b''))

def sat_val(r,g,b):
    mx=max(r,g,b); mn=min(r,g,b)
    sat=0 if mx==0 else (mx-mn)/float(mx)
    return sat, mx/255.0

def detect_palette(rgba,w,h):
    sx=w/1920.0; sy=h/898.0
    x0=max(0,int(round(74*sx))); x1=min(w,int(round(295*sx)))
    y0=max(0,int(round(170*sy))); y1=min(h,int(round(176*sy)))
    colors=[]; seen=set()
    for y in range(y0,y1):
        base=y*w*4
        for x in range(x0,x1):
            i=base+x*4; r,g,b,a=rgba[i:i+4]
            if a<200: continue
            s,v=sat_val(r,g,b)
            if s<0.35 or v<0.20: continue
            c=(int(r),int(g),int(b))
            if c not in seen:
                seen.add(c); colors.append(c)
    if len(colors)<60:
        raise RuntimeError("No se pudo leer la barra dBZ del IDAC")
    return colors

def classify(rgba,w,h,palette,tol=8):
    mask=bytearray(w*h)
    for y in range(h):
        for x in range(w):
            if x<540 and y<280: continue
            i=(y*w+x)*4; r,g,b,a=rgba[i:i+4]
            if a==0: continue
            s,v=sat_val(r,g,b)
            if s<0.35 or v<0.22: continue
            best=999
            for p in palette:
                d=math.sqrt((r-p[0])**2+(g-p[1])**2+(b-p[2])**2)
                if d<best: best=d
            if best<=tol: mask[y*w+x]=1
    return mask

def neighbor_filter(mask,w,h):
    out=bytearray(w*h)
    for y in range(1,h-1):
        for x in range(1,w-1):
            k=y*w+x
            if not mask[k]: continue
            n=0
            for yy in (y-1,y,y+1):
                row=yy*w
                for xx in (x-1,x,x+1):
                    if mask[row+xx]: n+=1
            if n>=2: out[k]=1
    return out

def make_layer(rgba,w,h,mask):
    out=bytearray(w*h*4); kept=0
    xmin=w; ymin=h; xmax=-1; ymax=-1
    for y in range(h):
        for x in range(w):
            k=y*w+x
            if not mask[k]: continue
            i=k*4; r,g,b,a=rgba[i:i+4]
            out[i:i+4]=bytes((r,g,b,235))
            kept += 1
            xmin=min(xmin,x); xmax=max(xmax,x); ymin=min(ymin,y); ymax=max(ymax,y)
    bbox=None if kept==0 else [xmin,ymin,xmax,ymax]
    return out,kept,bbox

def load_report():
    with open(OUT,"r",encoding="utf-8") as f:
        return json.load(f)

def process_one(url, report):
    t=token(url)
    print("Procesando", t, flush=True)
    b,_=fetch(url)
    w,h,rgba=decode_png_rgba(b)
    palette=detect_palette(rgba,w,h)
    mask=neighbor_filter(classify(rgba,w,h,palette,8),w,h)
    layer,kept,bbox=make_layer(rgba,w,h,mask)
    lname="eco_auto_"+re.sub(r'[^0-9A-Za-z._-]+','_',t)
    if not lname.lower().endswith(".png"): lname += ".png"
    with open(os.path.join(LAY,lname),"wb") as f:
        f.write(encode_rgba_png(w,h,layer))
    rec={
        "index":0,"source_index":0,"url":url,"token":t,"layer":lname,"preview":"",
        "kept_pixels":kept,"kept_pct":round(kept*100.0/(w*h),4),
        "bbox_px":bbox,"similarity_to_previous_kept":0.0,"bounds":RADAR_BOUNDS
    }
    frames=report.get("frames") or []
    frames.append(rec)
    uniq={str(f.get("token","")):f for f in frames}
    frames=sorted(uniq.values(), key=lambda f: tok_ms(f.get("token","")))[-NFRAMES:]
    for i,f in enumerate(frames,1): f["index"]=i
    report["frames"]=frames
    report["unique_frames"]=len(frames)
    report["source_frames"]=len(frames)
    report["checked_epoch"]=int(time.time())
    report["latest_checked_token"]=t
    report["latest_idac_token"]=t
    report["width"]=w; report["height"]=h
    report["palette_rgb"]=palette
    report["radar_bounds"]=RADAR_BOUNDS
    return report

def save_report(report):
    tmp=OUT+".tmp"
    with open(tmp,"w",encoding="utf-8") as f:
        json.dump(report,f,indent=2,ensure_ascii=False)
    os.replace(tmp,OUT)

def main():
    raw,_=fetch(UPDATE, timeout=45, maxbytes=2*1024*1024)
    text=raw.decode("utf-8","replace")
    urls=extract_urls(text)
    if not urls:
        raise RuntimeError("IDAC update.php no devolvio imagenes")
    urls=sorted(urls, key=lambda u: tok_ms(token(u)))
    # Solo conservar referencias a los 10 barridos mas recientes del IDAC.
    urls=urls[-NFRAMES:]
    report=load_report()
    existing={str(f.get("token","")) for f in (report.get("frames") or [])}
    pending=[u for u in urls if token(u) not in existing]
    if not pending:
        latest=token(urls[-1])
        report["checked_epoch"]=int(time.time())
        report["latest_checked_token"]=latest
        report["latest_idac_token"]=latest
        save_report(report)
        print("Sin barridos nuevos:", latest)
        return
    for u in pending:
        report=process_one(u, report)
        save_report(report)
    print("Actualizado hasta", report.get("latest_idac_token"), "con", len(report.get("frames") or []), "cuadros")

if __name__=="__main__":
    main()
