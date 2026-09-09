# -*- coding: utf-8 -*-
from __future__ import print_function
import os,re,json,csv,math
try:
    from http.server import BaseHTTPRequestHandler,HTTPServer
    from urllib.parse import urlparse,parse_qs
except ImportError:
    from BaseHTTPServer import BaseHTTPRequestHandler,HTTPServer
    from urlparse import urlparse,parse_qs

ROOT=os.path.dirname(os.path.abspath(__file__))
CACHE={}

PRODUCTS={
 "precip":{"label":"Precipitación","dir":"Precipitacion","abbr":"APCP","unit":"mm"},
 "tmp":{"label":"Temperatura 2 m","dir":"Temperatura","abbr":"TMP","unit":"°C"},
 "dpt":{"label":"Punto de rocío 2 m","dir":"Punto_rocio","abbr":"DPT","unit":"°C"},
 "cape":{"label":"CAPE","dir":"CAPE","abbr":"CAPE","unit":"J/kg"},
 "cin":{"label":"CIN","dir":"CIN","abbr":"CIN","unit":"J/kg"},
 "hlcy":{"label":"Helicidad","dir":"Helicidad","abbr":"HLCY","unit":"m²/s²"},
 "refc":{"label":"Reflectividad compuesta","dir":"Reflectividad_compuesta","abbr":"REFC","unit":"dBZ"},
 "gust":{"label":"Ráfagas","dir":"Rafagas","abbr":"GUST","unit":"km/h"},
 "wind":{"label":"Viento 10 m","dir":None,"abbr":"WIND","unit":"km/h"}
}

def multi_dir():
    for c in (os.path.join(ROOT,"rrfs_multi"),os.path.join(os.path.dirname(ROOT),"rrfs_multi")):
        if os.path.isdir(c): return c
    return os.path.join(ROOT,"rrfs_multi")

def csv_path(product,h):
    p=PRODUCTS[product]
    d=multi_dir()
    if product=="wind": return None
    return os.path.join(d,p["dir"],"RRFS_HISP_F%03d_%s.csv"%(h,p["abbr"]))

def wind_path(comp,h):
    label="Viento_U" if comp=="u" else "Viento_V"
    abbr="UGRD" if comp=="u" else "VGRD"
    return os.path.join(multi_dir(),label,"RRFS_HISP_F%03d_%s.csv"%(h,abbr))

def product_hours(product):
    out=[]
    if product=="wind":
        for h in range(3,49,3):
            if os.path.exists(wind_path("u",h)) and os.path.exists(wind_path("v",h)): out.append(h)
        return out
    for h in range(3,49,3):
        p=csv_path(product,h)
        if p and os.path.exists(p) and os.path.getsize(p)>0: out.append(h)
    return out

def available_products():
    return [k for k in PRODUCTS if product_hours(k)]

def read_rows(path):
    rows=[]
    if not path or not os.path.exists(path): return rows
    with open(path,"r") as f:
        r=csv.reader(f)
        for a in r:
            # wgrib2 -csv:
            # time0,time1,field,level,longitude,latitude,grid-value
            if len(a)<7: continue
            try:
                lon=float(a[4]); lat=float(a[5]); val=float(a[6])
            except: continue
            if abs(val)>=9.0e19: continue
            run=(a[0] if len(a)>0 else "").strip().strip('"')
            valid=(a[1] if len(a)>1 else "").strip().strip('"')
            var=(a[2] if len(a)>2 else "").strip().strip('"')
            level=(a[3] if len(a)>3 else "").strip().strip('"')
            if -74.9<=lon<=-66.8 and 16.3<=lat<=20.7:
                rows.append((lat,lon,val,var,level,run,valid))
    return rows

def level_score(product,level):
    s=(level or "").lower()
    if product in ("tmp","dpt"):
        return 100 if ("2 m" in s and "above ground" in s) else (10 if "surface" in s else 0)
    if product=="cape":
        if "surface" in s: return 100
        if "180-0 mb" in s or "255-0 mb" in s: return 80
        return 20
    if product=="cin":
        if "surface" in s: return 100
        if "180-0 mb" in s or "255-0 mb" in s: return 80
        return 20
    if product=="hlcy":
        if "0-3000 m" in s or "3000 m above ground" in s: return 100
        if "0-1000 m" in s or "1000 m above ground" in s: return 80
        return 20
    if product in ("refc","gust","precip"): return 100
    if product=="wind": return 100 if ("10 m" in s and "above ground" in s) else 0
    return 10

def select_rows(product,rows):
    if not rows: return [],""
    groups={}
    for r in rows:
        key=r[4]   # group ONLY by meteorological level
        groups.setdefault(key,[]).append(r)
    best=max(groups, key=lambda k:(level_score(product,k),len(groups[k])))
    return groups[best], best

def convert(product,v):
    if product in ("tmp","dpt") and v>150: return v-273.15
    if product in ("gust","wind"): return v*3.6
    return v

def run_from_rows(rows):
    if not rows: return None
    s=re.sub(r"\D","",rows[0][5])
    return s[:10] if len(s)>=10 else None

def valid_from_rows(rows):
    if not rows: return None
    s=re.sub(r"\D","",rows[0][6])
    return s[:10] if len(s)>=10 else None

def simple_field(product,h):
    k=("simple",product,h)
    if k in CACHE:return CACHE[k]
    rows=read_rows(csv_path(product,h))
    rows,level=select_rows(product,rows)
    pts=[]
    for lat,lon,v,var,lev,ftime,date in rows:
        v=convert(product,v)
        pts.append([lat,lon,round(v,3)])
    res={"ok":True,"product":product,"hour":h,"points":pts,"count":len(pts),
         "run":run_from_rows(rows),"valid":valid_from_rows(rows),"level":level,"unit":PRODUCTS[product]["unit"],
         "label":PRODUCTS[product]["label"]}
    CACHE[k]=res
    return res

def wind_field(h):
    k=("wind",h)
    if k in CACHE:return CACHE[k]
    ur,ulevel=select_rows("wind",read_rows(wind_path("u",h)))
    vr,vlevel=select_rows("wind",read_rows(wind_path("v",h)))
    u={(round(x[0],5),round(x[1],5)):x for x in ur}
    v={(round(x[0],5),round(x[1],5)):x for x in vr}
    pts=[]
    for key,a in u.items():
        if key not in v: continue
        uu=a[2]; vv=v[key][2]
        sp=math.sqrt(uu*uu+vv*vv)*3.6
        pts.append([a[0],a[1],round(sp,3),round(uu,3),round(vv,3)])
    rows=ur or vr
    res={"ok":True,"product":"wind","hour":h,"points":pts,"count":len(pts),
         "run":run_from_rows(rows),"valid":valid_from_rows(rows),"level":ulevel or vlevel,"unit":"km/h","label":"Viento 10 m"}
    CACHE[k]=res
    return res

def precip_base(h):
    k=("pbase",h)
    if k in CACHE:return CACHE[k]
    rows=read_rows(csv_path("precip",h))
    rows,level=select_rows("precip",rows)
    vals={(round(r[0],5),round(r[1],5)):r for r in rows}
    CACHE[k]=(vals,level,run_from_rows(rows),valid_from_rows(rows))
    return CACHE[k]

def precip_window(end_hour,window):
    k=("precip",end_hour,window)
    if k in CACHE:return CACHE[k]
    start=end_hour-window
    hs=product_hours("precip")
    if end_hour not in hs:
        return {"ok":False,"error":"F%03d no disponible"%end_hour,"points":[]}
    if start<0 or (start>0 and start not in hs):
        return {"ok":False,"error":"Periodo no disponible","points":[]}
    endv,level,run,valid=precip_base(end_hour)
    if start==0:
        vals={key:r[2] for key,r in endv.items()}
    else:
        startv,_,_,_=precip_base(start)
        vals={key:max(0.0,r[2]-(startv[key][2] if key in startv else 0.0)) for key,r in endv.items()}
    pts=[[lat,lon,round(v,3)] for (lat,lon),v in vals.items() if v>=1.0]
    res={"ok":True,"product":"precip","hour":end_hour,"end_hour":end_hour,"start_hour":start,
         "window":window,"points":pts,"count":len(pts),"run":run,"valid":valid,"level":level,
         "unit":"mm","label":"Precipitación"}
    CACHE[k]=res
    return res

def field(product,h,window=3):
    if product not in PRODUCTS:return {"ok":False,"error":"Producto desconocido","points":[]}
    if h not in product_hours(product):return {"ok":False,"error":"F%03d no disponible para %s"%(h,PRODUCTS[product]["label"]),"points":[]}
    if product=="precip":return precip_window(h,window)
    if product=="wind":return wind_field(h)
    return simple_field(product,h)

class H(BaseHTTPRequestHandler):
    def sendj(self,obj):
        raw=json.dumps(obj,separators=(",",":")).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type","application/json; charset=utf-8")
        self.send_header("Content-Length",str(len(raw)))
        self.send_header("Access-Control-Allow-Origin","*")
        self.end_headers();self.wfile.write(raw)
    def do_GET(self):
        u=urlparse(self.path)
        if u.path in ("/","/list","/status"):
            aps=available_products()
            info={}
            for p in aps:
                info[p]={"label":PRODUCTS[p]["label"],"unit":PRODUCTS[p]["unit"],"hours":product_hours(p)}
            return self.sendj({"ok":True,"products":info,"windows":[3,6,9,12,24],"data_dir":multi_dir()})
        if u.path=="/field":
            try:
                q=parse_qs(u.query)
                p=q.get("product",["precip"])[0]
                h=int(q.get("h",["3"])[0]);w=int(q.get("window",["3"])[0])
                return self.sendj(field(p,h,w))
            except Exception as e:
                return self.sendj({"ok":False,"error":str(e),"points":[]})
        self.send_response(404);self.end_headers()
    def log_message(self,fmt,*args): print(fmt%args)

print("RRFS HISPANIOLA - VISOR MULTIVARIABLE V40 - 48H - INEST")
print("Datos:",multi_dir())
print("Productos:",available_products())
print("Servidor: http://127.0.0.1:8807")
HTTPServer(("127.0.0.1",8807),H).serve_forever()
