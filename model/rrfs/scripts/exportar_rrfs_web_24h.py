# -*- coding: utf-8 -*-
from __future__ import print_function
import os, sys, json

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
OUT = os.path.join(ROOT, "datos")
MOTOR = os.path.join(HERE, "rrfs_hispaniola_motor_24h.py")

def ensure(p):
    if not os.path.isdir(p):
        os.makedirs(p)

def save_json(path, obj):
    tmp = path + ".tmp"
    with open(tmp, "w") as f:
        json.dump(obj, f, separators=(",", ":"))
    if os.path.exists(path):
        os.remove(path)
    os.rename(tmp, path)

def load_motor():
    with open(MOTOR, "r") as f:
        src = f.read()
    cut = src.find("class H(")
    if cut < 0:
        raise RuntimeError("No se encontró el bloque del servidor en el motor.")
    ns = {"__file__": MOTOR, "__name__": "rrfs_motor_estatico"}
    exec(compile(src[:cut], MOTOR, "exec"), ns, ns)
    return ns

def main():
    ensure(OUT)
    ns = load_motor()
    products = ns["available_products"]()
    product_hours = ns["product_hours"]
    PRODUCTS = ns["PRODUCTS"]
    field = ns["field"]

    info = {}
    for p in products:
        hs = [h for h in product_hours(p) if 1 <= int(h) <= 24]
        if hs:
            info[p] = {
                "label": PRODUCTS[p]["label"],
                "unit": PRODUCTS[p]["unit"],
                "hours": hs
            }

    catalog = {
        "ok": True,
        "products": info,
        "windows": [3, 6, 9, 12, 24],
        "horizon": 24,
        "mode": "github-static"
    }
    save_json(os.path.join(OUT, "catalog.json"), catalog)

    total = 0
    for p in sorted(info):
        for h in info[p]["hours"]:
            windows = [3]
            if p == "precip":
                windows = [3, 6, 9, 12, 24]
            for w in windows:
                obj = field(p, int(h), int(w))
                name = "%s_f%03d_w%02d.json" % (p, int(h), int(w))
                save_json(os.path.join(OUT, name), obj)
                total += 1
                print("WEB:", name, "OK" if obj.get("ok") else obj.get("error", "NO"))

    marker = {
        "ok": True,
        "files": total,
        "horizon": 24
    }
    save_json(os.path.join(OUT, "estado.json"), marker)
    print("Exportación web terminada:", total, "archivos JSON.")

if __name__ == "__main__":
    main()
