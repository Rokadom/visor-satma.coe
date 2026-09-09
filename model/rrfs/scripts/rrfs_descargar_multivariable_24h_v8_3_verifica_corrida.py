# -*- coding: utf-8 -*-
from __future__ import print_function
import os,re,sys,subprocess,time,shutil,json,csv,math,datetime
import email.utils
try:
    from urllib.request import urlopen, Request
except ImportError:
    from urllib2 import urlopen, Request

BASE="https://nomads.ncep.noaa.gov/pub/data/nccf/com/para/noaaport/rrfs/"
BASE_2DFLD_ROOT="https://nomads.ncep.noaa.gov/pub/data/nccf/com/rrfs/v1.0/"
ROOT=os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Carpeta que SIEMPRE usa el visor.
ACTIVE=os.path.join(ROOT,"rrfs_multi")

# La corrida nueva se construye aquí SIN tocar ACTIVE.
STAGING=os.path.join(ROOT,"rrfs_multi_nueva")

# Copia temporal de seguridad durante el intercambio.
BACKUP=os.path.join(ROOT,"rrfs_multi_anterior")

# Archivos grandes NA se descargan temporalmente aquí.
TMP=os.path.join(ROOT,"rrfs_tmp_multi")

WGRIB2=r"D:\GFS\App GFS\decoder\wgrib2.exe"

LON1,LON2=-74.8,-67.0
LAT1,LAT2=16.5,20.5
HOURS=list(range(3,25,3))

WANTED=[
 ("APCP","Precipitacion"),
 ("TMP","Temperatura"),
 ("DPT","Punto_rocio"),
 ("RH","Humedad_relativa"),
 ("CAPE","CAPE"),
 ("CIN","CIN"),
 ("HLCY","Helicidad"),
 ("UPHL","Updraft_Helicity"),
 ("MXUPHL","Max_Updraft_Helicity"),
 ("MNUPHL","Min_Updraft_Helicity"),
 ("REFD","Reflectividad"),
 ("REFC","Reflectividad_compuesta"),
 ("MAXREF","Max_reflectividad"),
 ("SIGH","Significant_Hail"),
 ("SCCP","Supercell_Composite"),
 ("STPC","Significant_Tornado"),
 ("SIGT","Significant_Tornado_Fixed"),
 ("UGRD","Viento_U"),
 ("VGRD","Viento_V"),
 ("GUST","Rafagas"),
 ("PWAT","Agua_precipitable"),
 ("PRMSL","Presion_MSL"),
 ("PRES","Presion")
]

# Campos imprescindibles para el visor actual.
REQUIRED=[
 ("APCP","Precipitacion"),
 ("TMP","Temperatura"),
 ("DPT","Punto_rocio"),
 ("CAPE","CAPE"),
 ("CIN","CIN"),
 ("HLCY","Helicidad"),
 ("REFC","Reflectividad_compuesta"),
 ("UGRD","Viento_U"),
 ("VGRD","Viento_V"),
 ("GUST","Rafagas")
]

def ensure_dir(p):
    if not os.path.exists(p): os.makedirs(p)

def safe_rmtree(p):
    if os.path.isdir(p):
        shutil.rmtree(p,ignore_errors=True)

def req(url,timeout=45):
    return urlopen(Request(url,headers={"User-Agent":"Mozilla/5.0 RRFS-HISPANIOLA-DESCARGA-SEGURA"}),timeout=timeout)

def page():
    return req(BASE,30).read().decode("utf-8","ignore")

def available_files(html):
    return set(re.findall(r'grib2\.rrfs\.t(?:00|06|12|18)z\.3km\.f\d{3}\.na',html,re.I))

def remote_stamp(name):
    """Devuelve epoch UTC usando Last-Modified del archivo remoto sin descargarlo completo."""
    url=BASE+name
    r=None
    try:
        q=Request(url,headers={
            "User-Agent":"Mozilla/5.0 RRFS-HISPANIOLA-DESCARGA-SEGURA",
            "Range":"bytes=0-0"
        })
        r=urlopen(q,timeout=30)
        lm=r.headers.get("Last-Modified")
        if not lm:
            return 0,None
        tup=email.utils.parsedate_tz(lm)
        if not tup:
            return 0,lm
        return email.utils.mktime_tz(tup),lm
    except Exception:
        return 0,None
    finally:
        try:
            if r: r.close()
        except:
            pass

def infer_run_date_from_stamp(stamp,cyc):
    """Infiere YYYYMMDD real de la corrida desde Last-Modified de F003.
    La fecha de publicacion puede cruzar 00 UTC, por eso se compara hoy/ayer.
    """
    if not stamp:
        return None,0
    lm_dt=datetime.datetime.utcfromtimestamp(stamp)
    ch=int(cyc)
    candidates=[]
    for back in (0,1):
        d=(lm_dt-datetime.timedelta(days=back)).date()
        run_dt=datetime.datetime(d.year,d.month,d.day,ch,0,0)
        delta=(lm_dt-run_dt).total_seconds()
        # F003 debe publicarse DESPUES de iniciar la corrida y normalmente en pocas horas.
        if -1800 <= delta <= 12*3600:
            candidates.append((abs(delta),run_dt))
    if not candidates:
        d=lm_dt.date()
        run_dt=datetime.datetime(d.year,d.month,d.day,ch,0,0)
        if run_dt > lm_dt + datetime.timedelta(minutes=30):
            run_dt-=datetime.timedelta(days=1)
    else:
        run_dt=sorted(candidates,key=lambda x:x[0])[0][1]
    epoch=(run_dt-datetime.datetime(1970,1,1)).total_seconds()
    return run_dt.strftime("%Y%m%d"),epoch

def choose_cycle(files):
    # V8.3: elegir la corrida COMPLETA mas reciente por FECHA+HORA DE CORRIDA,
    # no simplemente por el numero 18/12/06/00 ni por Last-Modified aislado.
    complete=[]
    for c in ["00","06","12","18"]:
        have=sum(("grib2.rrfs.t%sz.3km.f%03d.na"%(c,h)) in files for h in HOURS)
        if have==len(HOURS):
            name="grib2.rrfs.t%sz.3km.f003.na"%c
            stamp,lm=remote_stamp(name)
            run_date,run_epoch=infer_run_date_from_stamp(stamp,c)
            complete.append((run_epoch,c,lm,run_date))
    if not complete:
        return None,0,None,None

    dated=[x for x in complete if x[0]]
    if dated:
        dated.sort(reverse=True)
        _,c,lm,run_date=dated[0]
        return c,len(HOURS),lm,run_date

    # Sin Last-Modified no se arriesga a reemplazar la corrida activa: no hay
    # forma fiable de distinguir, por ejemplo, 18Z de ayer frente a 00Z de hoy.
    return None,0,None,None

def download(url,path):
    part=path+".part"
    try:
        if os.path.exists(part): os.remove(part)
    except: pass
    r=req(url,120)
    total=int(r.headers.get("Content-Length") or 0)
    got=0
    with open(part,"wb") as f:
        while True:
            chunk=r.read(1024*1024)
            if not chunk: break
            f.write(chunk); got+=len(chunk)
            if total:
                sys.stdout.write("\r  %.1f / %.1f MB  %3.0f%%"%(got/1048576.0,total/1048576.0,got*100.0/total))
            else:
                sys.stdout.write("\r  %.1f MB"%(got/1048576.0))
            sys.stdout.flush()
    print("")
    if total and got!=total:
        raise RuntimeError("Descarga incompleta: %d de %d bytes"%(got,total))
    if got<1024*1024:
        raise RuntimeError("Archivo descargado demasiado pequeno.")
    os.rename(part,path)
    return got

def run(args):
    p=subprocess.Popen(args,stdout=subprocess.PIPE,stderr=subprocess.STDOUT)
    data=p.communicate()[0]
    try: txt=data.decode("utf-8","ignore")
    except: txt=str(data)
    return p.returncode,txt

def inventory(path):
    return run([WGRIB2,path])[1]

def grib_reference_time(path):
    """Devuelve (YYYYMMDD, HH) leyendo d=YYYYMMDDHH del GRIB2 con wgrib2."""
    inv=inventory(path)
    m=re.search(r"\bd=(\d{10})\b",inv)
    if not m:
        return None,None
    d=m.group(1)
    return d[:8],d[8:10]

def verify_grib_cycle(path,run_date,cyc,label="GRIB2"):
    gd,gh=grib_reference_time(path)
    if not gd or not gh:
        raise RuntimeError("%s sin hora inicial d=YYYYMMDDHH verificable: %s"%(label,os.path.basename(path)))
    if str(gd)!=str(run_date) or str(gh).zfill(2)!=str(cyc).zfill(2):
        raise RuntimeError("%s NO pertenece a la corrida objetivo %s %sZ; contiene %s %sZ: %s"%(
            label,run_date,cyc,gd,gh,os.path.basename(path)))
    print("VERIFICADO %s: hora inicial %s %sZ"%(label,gd,gh))
    return True

def csv_reference_time(path):
    """Lee la primera columna time0 del CSV de wgrib2 y devuelve YYYYMMDD,HH."""
    try:
        with open(path,"r") as f:
            row=next(csv.reader(f))
        if not row: return None,None
        t=row[0].strip().strip('"')
        for fmt in ("%Y-%m-%d %H:%M:%S","%Y-%m-%d %H:%M","%d/%m/%Y %H:%M:%S","%d/%m/%Y %H:%M"):
            try:
                dt=datetime.datetime.strptime(t,fmt)
                return dt.strftime("%Y%m%d"),dt.strftime("%H")
            except:
                pass
    except:
        pass
    return None,None

def csv_cycle_matches(path,run_date,cyc):
    d,h=csv_reference_time(path)
    return bool(d and h and str(d)==str(run_date) and str(h).zfill(2)==str(cyc).zfill(2))

def present_vars(inv):
    return [(abbr,label) for abbr,label in WANTED if re.search(r":"+re.escape(abbr)+r":",inv)]

def extract_one(raw_rd,h,abbr,label):
    d=os.path.join(STAGING,label)
    ensure_dir(d)
    grib=os.path.join(d,"RRFS_HISP_F%03d_%s.grib2"%(h,abbr))
    csv=os.path.join(d,"RRFS_HISP_F%03d_%s.csv"%(h,abbr))
    run([WGRIB2,raw_rd,"-match",":"+abbr+":","-grib",grib])
    if not os.path.exists(grib) or os.path.getsize(grib)==0:
        return None
    run([WGRIB2,grib,"-csv",csv])
    if not os.path.exists(csv) or os.path.getsize(csv)==0:
        return None
    return (grib,csv,os.path.getsize(grib))

def process(full,h):
    raw=os.path.join(TMP,"RRFS_HISP_F%03d_ALL.grib2"%h)
    run([WGRIB2,full,"-small_grib","%g:%g"%(LON1,LON2),"%g:%g"%(LAT1,LAT2),raw])
    if not os.path.exists(raw) or os.path.getsize(raw)==0:
        raise RuntimeError("No se pudo recortar F%03d"%h)

    inv=inventory(raw)
    with open(os.path.join(STAGING,"INVENTARIO_F%03d.txt"%h),"wb") as f:
        f.write(inv.encode("utf-8","ignore"))

    found=present_vars(inv)
    extracted=[]
    for abbr,label in found:
        r=extract_one(raw,h,abbr,label)
        if r: extracted.append((abbr,label,r[2]))

    try: os.remove(raw)
    except: pass
    return found,extracted

def csv_is_valid(path):
    # Validación ligera pero real del CSV de wgrib2:
    # 7 columnas: time0,time1,field,level,lon,lat,value
    if not os.path.exists(path) or os.path.getsize(path)<1000:
        return False
    good=0
    try:
        with open(path,"r") as f:
            for line in f:
                a=[x.strip().strip('"') for x in line.rstrip("\r\n").split(",")]
                if len(a)<7: continue
                try:
                    lon=float(a[4]); lat=float(a[5]); val=float(a[6])
                except:
                    continue
                if LON1-1 <= lon <= LON2+1 and LAT1-1 <= lat <= LAT2+1:
                    good+=1
                if good>=20: return True
    except:
        return False
    return False

def validate_staging(run_date,cycle):
    errors=[]
    for h in HOURS:
        for abbr,label in REQUIRED:
            grib=os.path.join(STAGING,label,"RRFS_HISP_F%03d_%s.grib2"%(h,abbr))
            csv=os.path.join(STAGING,label,"RRFS_HISP_F%03d_%s.csv"%(h,abbr))
            if not os.path.exists(grib) or os.path.getsize(grib)<100:
                errors.append("F%03d %s GRIB2 faltante/vacio"%(h,abbr)); continue
            if not csv_is_valid(csv):
                errors.append("F%03d %s CSV invalido"%(h,abbr))
            elif not csv_cycle_matches(csv,run_date,cycle):
                errors.append("F%03d %s pertenece a otra corrida"%(h,abbr))
    if errors:
        print("\nVALIDACION FALLIDA:")
        for e in errors[:60]: print(" -",e)
        if len(errors)>60: print(" ... y %d errores mas"%(len(errors)-60))
        return False

    marker={
      "cycle":cycle+"Z",
      "run_date":run_date,
      "hours":HOURS,
      "status":"VALIDADA_COMPLETA",
      "created_local":time.strftime("%Y-%m-%d %H:%M:%S"),
      "selection":"newest_complete_by_remote_last_modified"
    }
    with open(os.path.join(STAGING,"CORRIDA_ACTIVA.json"),"w") as f:
        json.dump(marker,f,indent=2)
    return True

def active_cycle():
    p=os.path.join(ACTIVE,"CORRIDA_ACTIVA.json")
    try:
        with open(p,"r") as f:
            return json.load(f).get("cycle","desconocida")
    except:
        # Carpetas antiguas no tienen marcador; se preservan hasta validar la nueva.
        return "corrida anterior"

def activate_new_cycle():
    # Intercambio transaccional:
    # 1) ACTIVE -> BACKUP
    # 2) STAGING -> ACTIVE
    # 3) borrar BACKUP solo después del éxito.
    # Si falla el paso 2, restaurar BACKUP.
    safe_rmtree(BACKUP)
    had_active=os.path.isdir(ACTIVE)
    try:
        if had_active:
            os.rename(ACTIVE,BACKUP)
        os.rename(STAGING,ACTIVE)
    except Exception:
        if not os.path.isdir(ACTIVE) and os.path.isdir(BACKUP):
            os.rename(BACKUP,ACTIVE)
        raise
    safe_rmtree(BACKUP)


def lm_to_yyyymmdd(lm):
    try:
        tup=email.utils.parsedate_tz(lm)
        if not tup: return None
        epoch=email.utils.mktime_tz(tup)
        return time.strftime("%Y%m%d",time.gmtime(epoch))
    except:
        return None

def remote_exists(url):
    r=None
    try:
        q=Request(url,headers={
            "User-Agent":"Mozilla/5.0 RRFS-HISPANIOLA-2DFLD",
            "Range":"bytes=0-0"
        })
        r=urlopen(q,timeout=30)
        return True
    except:
        return False
    finally:
        try:
            if r: r.close()
        except:
            pass

def base_2dfld(run_date,cyc):
    return BASE_2DFLD_ROOT+"rrfs.%s/%s/"%(run_date,cyc)

def name_2dfld(cyc,h):
    return "rrfs.t%sz.2dfld.2p5km.f%03d.pr.grib2"%(cyc,h)

def check_2dfld_complete(run_date,cyc):
    b=base_2dfld(run_date,cyc)
    missing=[]
    for h in HOURS:
        u=b+name_2dfld(cyc,h)
        if not remote_exists(u):
            missing.append(h)
    return (len(missing)==0,missing,b)

def extract_exact(raw,h,abbr,label,match_text):
    d=os.path.join(STAGING,label)
    ensure_dir(d)
    grib=os.path.join(d,"RRFS_HISP_F%03d_%s.grib2"%(h,abbr))
    csvp=os.path.join(d,"RRFS_HISP_F%03d_%s.csv"%(h,abbr))
    run([WGRIB2,raw,"-match",match_text,"-grib",grib])
    if not os.path.exists(grib) or os.path.getsize(grib)==0:
        return None
    run([WGRIB2,grib,"-csv",csvp])
    if not os.path.exists(csvp) or os.path.getsize(csvp)==0:
        return None
    return csvp

def read_wgrib_csv(path):
    data={}
    first_meta=None
    with open(path,"r") as f:
        for row in csv.reader(f):
            if len(row)<7: continue
            try:
                lon=float(row[4]); lat=float(row[5]); val=float(row[6])
            except:
                continue
            key=("%.5f"%lon,"%.5f"%lat)
            data[key]=(lon,lat,val,row[0],row[1])
            if first_meta is None:
                first_meta=(row[0],row[1])
    return data,first_meta

def write_derived_csv(path,h,field,level,rows):
    ensure_dir(os.path.dirname(path))
    with open(path,"w",newline="") as f:
        w=csv.writer(f)
        for t0,t1,lon,lat,val in rows:
            w.writerow([t0,t1,field,level,"%.6f"%lon,"%.6f"%lat,"%.6f"%val])

def derive_supercell_products(h,cape_csv,efhl_csv,uesh_csv,vesh_csv):
    # IMPORTANTE:
    # UESH/VESH están definidos por NCEP en kt. Se convierten a m/s.
    # Este índice usa CAPE de superficie + EFHL + EBWD. Se guarda explícitamente
    # como DERIVADO, porque el SCP oficial clásico utiliza MUCAPE y ESRH apropiada
    # para movimiento de supercélula.
    cape,_=read_wgrib_csv(cape_csv)
    efhl,_=read_wgrib_csv(efhl_csv)
    uesh,_=read_wgrib_csv(uesh_csv)
    vesh,_=read_wgrib_csv(vesh_csv)

    common=set(cape.keys()) & set(efhl.keys()) & set(uesh.keys()) & set(vesh.keys())
    ebwd_rows=[]
    scp_rows=[]
    for k in sorted(common):
        lon,lat,c,t0,t1=cape[k]
        e=efhl[k][2]
        u=uesh[k][2]
        v=vesh[k][2]
        ebwd_kt=math.sqrt(u*u+v*v)
        ebwd_ms=ebwd_kt*0.514444

        if ebwd_ms < 10.0:
            shear_term=0.0
        else:
            shear_term=min(ebwd_ms/20.0,1.0)

        # Solo contribución ciclónica/positiva para la visualización derivada.
        scp=(max(c,0.0)/1000.0)*(max(e,0.0)/50.0)*shear_term

        ebwd_rows.append((t0,t1,lon,lat,ebwd_ms))
        scp_rows.append((t0,t1,lon,lat,scp))

    d1=os.path.join(STAGING,"Cizalladura_Efectiva")
    d2=os.path.join(STAGING,"Supercell_Composite_Derivado")
    ebwd_csv=os.path.join(d1,"RRFS_HISP_F%03d_EBWD.csv"%h)
    scp_csv=os.path.join(d2,"RRFS_HISP_F%03d_SCP_DERIVADO.csv"%h)
    write_derived_csv(ebwd_csv,h,"EBWD","effective layer (derived from UESH/VESH)",ebwd_rows)
    write_derived_csv(scp_csv,h,"SCP_DERIVADO","surface CAPE + EFHL + EBWD",scp_rows)
    return ebwd_csv,scp_csv

def process_2dfld(full,h):
    raw=os.path.join(TMP,"RRFS_HISP_F%03d_2DFLD.grib2"%h)
    run([WGRIB2,full,"-small_grib","%g:%g"%(LON1,LON2),"%g:%g"%(LAT1,LAT2),raw])
    if not os.path.exists(raw) or os.path.getsize(raw)==0:
        raise RuntimeError("No se pudo recortar 2DFLD F%03d"%h)

    inv=inventory(raw)
    invpath=os.path.join(STAGING,"INVENTARIO_2DFLD_F%03d.txt"%h)
    with open(invpath,"wb") as f:
        f.write(inv.encode("utf-8","ignore"))

    # Extracción inequívoca por variable + nivel.
    cape=extract_exact(raw,h,"CAPE_SFC","CAPE_2DFLD",":CAPE:surface:")
    efhl=extract_exact(raw,h,"EFHL","Helicidad_Efectiva",":EFHL:surface:")
    uesh=extract_exact(raw,h,"UESH","Cizalladura_Efectiva_U",":UESH:level of free convection:")
    vesh=extract_exact(raw,h,"VESH","Cizalladura_Efectiva_V",":VESH:level of free convection:")
    mx25=extract_exact(raw,h,"MXUPHL_2_5KM","Max_Updraft_Helicity_2_5km",":MXUPHL:5000-2000 m above ground:")
    mx03=extract_exact(raw,h,"MXUPHL_0_3KM","Max_Updraft_Helicity_0_3km",":MXUPHL:3000-0 m above ground:")
    hl03=extract_exact(raw,h,"HLCY_0_3KM","Helicidad_0_3km_2DFLD",":HLCY:3000-0 m above ground:")
    hl01=extract_exact(raw,h,"HLCY_0_1KM","Helicidad_0_1km_2DFLD",":HLCY:1000-0 m above ground:")
    dcape=extract_exact(raw,h,"DCAPE","DCAPE_2DFLD",":DCAPE:400-0 mb above ground:")

    needed=[("CAPE surface",cape),("EFHL",efhl),("UESH",uesh),("VESH",vesh)]
    miss=[n for n,p in needed if not p]
    if miss:
        raise RuntimeError("2DFLD F%03d sin campos necesarios: %s"%(h,", ".join(miss)))

    ebwd_csv,scp_csv=derive_supercell_products(h,cape,efhl,uesh,vesh)

    try: os.remove(raw)
    except: pass

    return {
      "CAPE":cape,"EFHL":efhl,"UESH":uesh,"VESH":vesh,
      "MXUPHL_2_5KM":mx25,"MXUPHL_0_3KM":mx03,
      "HLCY_0_3KM":hl03,"HLCY_0_1KM":hl01,"DCAPE":dcape,
      "EBWD":ebwd_csv,"SCP_DERIVADO":scp_csv
    }

def validate_2dfld_staging():
    errors=[]
    for h in HOURS:
        checks=[
          os.path.join(STAGING,"Helicidad_Efectiva","RRFS_HISP_F%03d_EFHL.csv"%h),
          os.path.join(STAGING,"Cizalladura_Efectiva_U","RRFS_HISP_F%03d_UESH.csv"%h),
          os.path.join(STAGING,"Cizalladura_Efectiva_V","RRFS_HISP_F%03d_VESH.csv"%h),
          os.path.join(STAGING,"Cizalladura_Efectiva","RRFS_HISP_F%03d_EBWD.csv"%h),
          os.path.join(STAGING,"Supercell_Composite_Derivado","RRFS_HISP_F%03d_SCP_DERIVADO.csv"%h)
        ]
        for p in checks:
            if not csv_is_valid(p):
                errors.append("F%03d 2DFLD invalido: %s"%(h,os.path.basename(p)))
    if errors:
        print("\nVALIDACION 2DFLD FALLIDA:")
        for e in errors[:60]: print(" -",e)
        return False
    return True


# ------------------------------------------------------------------
# V8.3 - REANUDACION SEGURA + VERIFICACION DE CORRIDA
# rrfs_multi_nueva se conserva si Internet se interrumpe.
# Cada F ya procesado y validado se reutiliza; solo se repiten
# archivos faltantes, incompletos o invalidos.
# ------------------------------------------------------------------

STAGING_STATE="DESCARGA_EN_CURSO.json"

def staging_state_path():
    return os.path.join(STAGING,STAGING_STATE)

def read_staging_state():
    try:
        with open(staging_state_path(),"r") as f:
            return json.load(f)
    except:
        return {}

def write_staging_state(run_date,cyc,mode):
    ensure_dir(STAGING)
    state={
      "run_date":run_date,
      "cycle":cyc,
      "mode":mode,
      "status":"EN_PROGRESO",
      "updated_local":time.strftime("%Y-%m-%d %H:%M:%S")
    }
    with open(staging_state_path(),"w") as f:
        json.dump(state,f,indent=2)

def staging_matches(run_date,cyc,mode):
    st=read_staging_state()
    return (str(st.get("run_date",""))==str(run_date)
            and str(st.get("cycle","")).replace("Z","").zfill(2)==str(cyc).zfill(2)
            and str(st.get("mode",""))==str(mode))

def required_hour_valid(h):
    """True si Fxxx de la parte NA ya fue procesado correctamente."""
    for abbr,label in REQUIRED:
        grib=os.path.join(STAGING,label,"RRFS_HISP_F%03d_%s.grib2"%(h,abbr))
        csvp=os.path.join(STAGING,label,"RRFS_HISP_F%03d_%s.csv"%(h,abbr))
        if not os.path.exists(grib) or os.path.getsize(grib)<100:
            return False
        if not csv_is_valid(csvp):
            return False
    return True

def dfld_hour_valid(h):
    """True si Fxxx 2DFLD contiene los productos que usa el visor actual."""
    checks=[
      os.path.join(STAGING,"Helicidad_Efectiva","RRFS_HISP_F%03d_EFHL.csv"%h),
      os.path.join(STAGING,"Cizalladura_Efectiva_U","RRFS_HISP_F%03d_UESH.csv"%h),
      os.path.join(STAGING,"Cizalladura_Efectiva_V","RRFS_HISP_F%03d_VESH.csv"%h),
      os.path.join(STAGING,"Cizalladura_Efectiva","RRFS_HISP_F%03d_EBWD.csv"%h),
      os.path.join(STAGING,"Supercell_Composite_Derivado","RRFS_HISP_F%03d_SCP_DERIVADO.csv"%h),
      os.path.join(STAGING,"Max_Updraft_Helicity_2_5km","RRFS_HISP_F%03d_MXUPHL_2_5KM.csv"%h),
      os.path.join(STAGING,"Max_Updraft_Helicity_0_3km","RRFS_HISP_F%03d_MXUPHL_0_3KM.csv"%h),
      os.path.join(STAGING,"DCAPE_2DFLD","RRFS_HISP_F%03d_DCAPE.csv"%h)
    ]
    for p in checks:
        if not csv_is_valid(p):
            return False
    return True

def prepare_full_staging(run_date,cyc):
    if staging_matches(run_date,cyc,"FULL"):
        print("\nSe encontro una descarga interrumpida de ESTA MISMA corrida.")
        print("Se conservaran los F ya procesados y validos.")
        return
    if os.path.isdir(STAGING):
        print("\nLa carpeta de reanudacion pertenece a otra corrida o proceso.")
        print("Se inicia una candidata nueva.")
    safe_rmtree(STAGING)
    ensure_dir(STAGING)
    write_staging_state(run_date,cyc,"FULL")

def prepare_2dfld_staging(run_date,cyc):
    if staging_matches(run_date,cyc,"2DFLD_ONLY"):
        print("\nSe encontro una descarga 2DFLD interrumpida de ESTA MISMA corrida.")
        print("Se conservaran los F 2DFLD ya procesados y validos.")
        return
    safe_rmtree(STAGING)
    if not os.path.isdir(ACTIVE):
        raise RuntimeError("No existe rrfs_multi activa para reutilizar.")
    shutil.copytree(ACTIVE,STAGING)
    write_staging_state(run_date,cyc,"2DFLD_ONLY")

def clean_hour_na(h):
    """Limpia solo salidas NA de una hora que deba reprocesarse."""
    for abbr,label in WANTED:
        d=os.path.join(STAGING,label)
        for ext in ("grib2","csv"):
            p=os.path.join(d,"RRFS_HISP_F%03d_%s.%s"%(h,abbr,ext))
            try:
                if os.path.exists(p): os.remove(p)
            except: pass
    try:
        p=os.path.join(STAGING,"INVENTARIO_F%03d.txt"%h)
        if os.path.exists(p): os.remove(p)
    except: pass

def clean_hour_2dfld(h):
    """Limpia solo salidas 2DFLD de una hora que deba reprocesarse."""
    patterns=[
      ("CAPE_2DFLD","RRFS_HISP_F%03d_CAPE_SFC"%h),
      ("Helicidad_Efectiva","RRFS_HISP_F%03d_EFHL"%h),
      ("Cizalladura_Efectiva_U","RRFS_HISP_F%03d_UESH"%h),
      ("Cizalladura_Efectiva_V","RRFS_HISP_F%03d_VESH"%h),
      ("Max_Updraft_Helicity_2_5km","RRFS_HISP_F%03d_MXUPHL_2_5KM"%h),
      ("Max_Updraft_Helicity_0_3km","RRFS_HISP_F%03d_MXUPHL_0_3KM"%h),
      ("Helicidad_0_3km_2DFLD","RRFS_HISP_F%03d_HLCY_0_3KM"%h),
      ("Helicidad_0_1km_2DFLD","RRFS_HISP_F%03d_HLCY_0_1KM"%h),
      ("DCAPE_2DFLD","RRFS_HISP_F%03d_DCAPE"%h),
      ("Cizalladura_Efectiva","RRFS_HISP_F%03d_EBWD"%h),
      ("Supercell_Composite_Derivado","RRFS_HISP_F%03d_SCP_DERIVADO"%h)
    ]
    for label,base in patterns:
        d=os.path.join(STAGING,label)
        for ext in ("grib2","csv"):
            p=os.path.join(d,base+"."+ext)
            try:
                if os.path.exists(p): os.remove(p)
            except: pass
    try:
        p=os.path.join(STAGING,"INVENTARIO_2DFLD_F%03d.txt"%h)
        if os.path.exists(p): os.remove(p)
    except: pass

def active_marker():
    p=os.path.join(ACTIVE,"CORRIDA_ACTIVA.json")
    try:
        with open(p,"r") as f:
            return json.load(f)
    except:
        return {}

def active_matches(run_date,cyc):
    m=active_marker()
    ac=str(m.get("cycle","")).replace("Z","").zfill(2)
    rd=str(m.get("run_date",""))
    if not ac:
        ac=active_cycle()
    # Older marker may not have run_date. In that case, compare only cycle.
    if rd:
        return ac==cyc and rd==run_date
    return ac==cyc

def copy_active_to_staging():
    safe_rmtree(STAGING)
    if not os.path.isdir(ACTIVE):
        raise RuntimeError("No existe rrfs_multi activa para reutilizar.")
    shutil.copytree(ACTIVE,STAGING)

def process_only_2dfld_same_run(run_date,cyc,base2):
    print("\nLa corrida activa coincide con la corrida mas reciente.")
    print("Se REUTILIZARAN los datos .NA ya existentes.")
    print("Solo se descargara RRFS 2DFLD F003..F024.\n")

    prepare_2dfld_staging(run_date,cyc)
    safe_rmtree(TMP)
    ensure_dir(TMP)

    reused=0
    downloaded=0
    try:
        for i,h in enumerate(HOURS,1):
            print("\n[2DFLD %d/%d] F%03d - corrida %sZ"%(i,len(HOURS),h,cyc))
            if dfld_hour_valid(h):
                reused+=1
                print("YA EXISTE Y ES VALIDO -> se omite la descarga.")
                continue

            clean_hour_2dfld(h)
            name2=name_2dfld(cyc,h)
            full2=os.path.join(TMP,name2)
            print("Faltante/incompleto -> descargando SOLO RRFS 2DFLD...")
            download(base2+name2,full2)
            print("Extrayendo EFHL, UESH/VESH, MXUPHL, DCAPE y productos derivados...")
            process_2dfld(full2,h)
            if not dfld_hour_valid(h):
                raise RuntimeError("F%03d 2DFLD no quedo valido despues de procesar."%h)
            downloaded+=1
            print("2DFLD listo y validado.")
            try: os.remove(full2)
            except: pass
            write_staging_state(run_date,cyc,"2DFLD_ONLY")

        print("\nResumen reanudacion 2DFLD: %d reutilizados, %d descargados."%(reused,downloaded))
        print("\nValidando productos RRFS 2DFLD...")
        if not validate_2dfld_staging():
            print("\nVALIDACION 2DFLD FALLIDA.")
            print("rrfs_multi permanece intacta.")
            print("rrfs_multi_nueva SE CONSERVA para continuar en el proximo intento.")
            return False

        marker_path=os.path.join(STAGING,"CORRIDA_ACTIVA.json")
        marker=active_marker()
        marker["cycle"]=cyc
        marker["run_date"]=run_date
        marker["rrfs_2dfld"]="COMPLETO_F003_F024"
        marker["scp"]="SCP_DERIVADO_SFC_CAPE_EFHL_EBWD"
        try:
            with open(marker_path,"w") as f:
                json.dump(marker,f,indent=2)
        except:
            pass
        try:
            os.remove(staging_state_path())
        except:
            pass

        print("\nActivando nuevos productos 2DFLD sin redescargar los .NA...")
        safe_rmtree(BACKUP)
        if os.path.exists(ACTIVE):
            os.rename(ACTIVE,BACKUP)
        try:
            os.rename(STAGING,ACTIVE)
        except:
            if not os.path.isdir(ACTIVE) and os.path.isdir(BACKUP):
                os.rename(BACKUP,ACTIVE)
            raise
        safe_rmtree(BACKUP)
        print("ACTUALIZACION 2DFLD COMPLETADA CORRECTAMENTE")
        print("Corrida activa: %sZ"%cyc)
        return True
    except Exception as e:
        print("\nERROR DURANTE 2DFLD:",e)
        print("Los archivos validos de rrfs_multi_nueva SE CONSERVAN.")
        print("Al ejecutar de nuevo, se continuara con los F pendientes.")
        raise
    finally:
        safe_rmtree(TMP)

def main():
    ensure_dir(TMP)
    if not os.path.exists(WGRIB2):
        raise RuntimeError("No encuentro wgrib2: "+WGRIB2)

    print("==============================================================")
    print(" RRFS HISPANIOLA - ACTUALIZADOR 24H V8.3 VERIFICA CORRIDA + 2DFLD")
    print("==============================================================")
    print("Corrida actualmente activa:",active_cycle())
    print("Buscando una corrida NUEVA y COMPLETA F003..F024...")

    files=available_files(page())
    cyc,n,remote_lm,run_date=choose_cycle(files)
    if not cyc or n!=len(HOURS):
        print("\nNO HAY UNA CORRIDA COMPLETA F003..F024.")
        print("No se toca rrfs_multi. El visor continua con los datos actuales.")
        return

    print("Corrida candidata MAS RECIENTE: %sZ (%d/%d archivos)"%(cyc,n,len(HOURS)))
    if remote_lm: print("Fecha remota de la corrida:",remote_lm)

    if not run_date:
        print("\nNo pude determinar con seguridad la fecha YYYYMMDD de la corrida.")
        print("No se toca rrfs_multi.")
        return
    print("Fecha/hora objetivo verificada por seleccion: %s %sZ"%(run_date,cyc))

    print("\nComprobando RRFS 2DFLD para la MISMA corrida %sZ del %s..."%(cyc,run_date))
    ok2,missing2,base2=check_2dfld_complete(run_date,cyc)
    if not ok2:
        print("RRFS 2DFLD aun NO esta completo F003..F024.")
        print("Horas faltantes:",", ".join("F%03d"%x for x in missing2))
        print("No se toca rrfs_multi; se conserva la corrida activa.")
        return
    print("RRFS 2DFLD completo: 16/16 archivos.")

    if active_matches(run_date,cyc):
        ok=process_only_2dfld_same_run(run_date,cyc,base2)
        return

    # V8.3: conservar una candidata incompleta de la MISMA corrida.
    prepare_full_staging(run_date,cyc)
    safe_rmtree(TMP)
    ensure_dir(TMP)

    summary=[]
    try:
        reused_na=0
        reused_2dfld=0
        downloaded_na=0
        downloaded_2dfld=0

        for i,h in enumerate(HOURS,1):
            name="grib2.rrfs.t%sz.3km.f%03d.na"%(cyc,h)
            full=os.path.join(TMP,name)
            print("\n[%d/%d] F%03d - corrida %sZ"%(i,len(HOURS),h,cyc))

            if required_hour_valid(h):
                reused_na+=1
                print("NA: YA PROCESADO Y VALIDO -> se omite la descarga.")
                summary.append((h,["REUTILIZADO_VALIDO"]))
            else:
                clean_hour_na(h)
                print("NA: faltante/incompleto -> descargando...")
                download(BASE+name,full)
                verify_grib_cycle(full,run_date,cyc,"RRFS NA")
                print("Recortando Hispaniola y extrayendo parametros...")
                found,extracted=process(full,h)
                if not required_hour_valid(h):
                    raise RuntimeError("F%03d NA no quedo valido despues de procesar."%h)
                downloaded_na+=1
                print("NA listo y validado. Extraidos:",", ".join(x[0] for x in extracted) if extracted else "ninguno")
                summary.append((h,[x[0] for x in extracted]))
                try: os.remove(full)
                except: pass

            if dfld_hour_valid(h):
                reused_2dfld+=1
                print("2DFLD: YA PROCESADO Y VALIDO -> se omite la descarga.")
            else:
                clean_hour_2dfld(h)
                print("2DFLD: faltante/incompleto -> descargando...")
                name2=name_2dfld(cyc,h)
                full2=os.path.join(TMP,name2)
                download(base2+name2,full2)
                verify_grib_cycle(full2,run_date,cyc,"RRFS 2DFLD")
                print("Extrayendo EFHL, UESH/VESH, MXUPHL, DCAPE y productos derivados...")
                process_2dfld(full2,h)
                if not dfld_hour_valid(h):
                    raise RuntimeError("F%03d 2DFLD no quedo valido despues de procesar."%h)
                downloaded_2dfld+=1
                print("2DFLD listo y validado.")
                try: os.remove(full2)
                except: pass

            # Actualiza el marcador tras completar esta hora.
            write_staging_state(run_date,cyc,"FULL")

        print("\nRESUMEN DE REANUDACION")
        print(" NA    : %d reutilizados / %d descargados"%(reused_na,downloaded_na))
        print(" 2DFLD : %d reutilizados / %d descargados"%(reused_2dfld,downloaded_2dfld))

        rpt=os.path.join(STAGING,"RESUMEN_MULTIVARIABLE_RRFS.txt")
        with open(rpt,"w") as f:
            f.write("RRFS HISPANIOLA DESCARGA MULTIVARIABLE 24H\nCorrida: %sZ\n"%cyc)
            f.write("Caja: %.2f..%.2f / %.2f..%.2f\n\n"%(LON1,LON2,LAT1,LAT2))
            for h,vars_ in summary:
                f.write("F%03d: %s\n"%(h,", ".join(vars_)))

        print("\nComprobando que la corrida nueva este COMPLETA y sea valida...")
        if not validate_staging(run_date,cyc):
            print("\nLA CORRIDA NUEVA NO SE ACTIVARA.")
            print("rrfs_multi permanece intacta y el visor sigue funcionando.")
            print("rrfs_multi_nueva SE CONSERVA para continuar en el proximo intento.")
            return

        print("Validando tambien los productos RRFS 2DFLD...")
        if not validate_2dfld_staging():
            print("\nLOS DATOS 2DFLD NO SE ACTIVARAN.")
            print("rrfs_multi permanece intacta.")
            print("rrfs_multi_nueva SE CONSERVA para continuar en el proximo intento.")
            return

        # Anotar que la corrida activa incluye 2DFLD y el SCP derivado.
        marker_path=os.path.join(STAGING,"CORRIDA_ACTIVA.json")
        try:
            with open(marker_path,"r") as f:
                marker=json.load(f)
            marker["rrfs_2dfld"]="COMPLETO_F003_F024"
            marker["scp"]="SCP_DERIVADO_SFC_CAPE_EFHL_EBWD"
            marker["run_date"]=run_date
            with open(marker_path,"w") as f:
                json.dump(marker,f,indent=2)
        except:
            pass

        old=active_cycle()
        print("\nValidacion correcta.")
        print("Activando %sZ y retirando %s..."%(cyc,old))
        try:
            os.remove(staging_state_path())
        except:
            pass
        activate_new_cycle()

        print("\n==============================================================")
        print(" ACTUALIZACION COMPLETADA CORRECTAMENTE")
        print(" Corrida activa:",cyc+"Z")
        print(" La corrida anterior fue eliminada DESPUES del intercambio.")
        print(" rrfs_multi nunca se borro antes de validar la nueva corrida.")
        print("==============================================================")

    except Exception as e:
        print("\nERROR DURANTE LA ACTUALIZACION:",e)
        print("La corrida activa NO se reemplazara.")
        print("El visor puede continuar utilizando rrfs_multi actual.")
        print("Los F validos de rrfs_multi_nueva SE CONSERVAN.")
        print("Al ejecutar nuevamente, se continuara desde los pendientes.")
        raise
    finally:
        safe_rmtree(TMP)

if __name__=="__main__":
    try:
        main()
    except Exception as e:
        print("\nPROCESO FINALIZADO CON ERROR:",e)
        sys.exit(1)
    sys.exit(0)
