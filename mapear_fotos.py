#!/usr/bin/env python3
"""
Mapea cada producto de la lista mayorista a una foto.

Fuente unificada de imágenes (en orden de preferencia):
  1. web-semillero-fresh  products-hq/  (versión de alta calidad)
  2. web-semillero-fresh  images/wp/    (la original del WordPress)
  3. fotos recortadas del PDF del catálogo viejo

No usa similitud de strings a secas: eso confunde "CABALLO X 40 KG" con
"jabon ala 400 g". Compara el nombre y la presentación (el peso) por separado, y
descarta el match si los dos declaran peso y no coinciden — mostrar la foto del
producto equivocado es peor que no mostrar ninguna.

    python mapear_fotos.py            # genera mapa_fotos.json + cobertura.txt
"""
import json, os, re, sys, unicodedata, collections

BASE = os.path.dirname(os.path.abspath(__file__))
WEB = os.path.expanduser("~/dev/semillero/web-semillero-fresh")
sys.path.insert(0, BASE)
from build import parsear, bajar_csv, limpiar, separar_mezclas          # noqa: E402

# Abreviaturas de la planilla -> palabra entera, para que matcheen con la web.
SINONIMOS = {
    "cacho": "cachorro", "cach": "cachorro", "cachorros": "cachorro",
    "ad": "adulto", "adultos": "adulto", "adul": "adulto",
    "rp": "razapequena", "peq": "pequena", "pequeqa": "pequena", "pequena": "pequena",
    "med": "mediana", "mediano": "mediana", "gde": "grande", "gdes": "grande",
    "veget": "vegetales", "vegetal": "vegetales", "cock": "cocktail",
    "ds": "dogselection", "e": "exact", "frac": "fraccionado",
    "vit": "vitamina", "sem": "semanas", "un": "unidades", "u": "unidades",
    "liq": "liquido", "past": "pastilla", "sob": "sobres", "sobre": "sobres",
    "nutrimas": "nutrimax", "minino": "mininio", "nino": "mininio", "ninio": "mininio",
}
# Palabras que no distinguen un producto de otro.
RUIDO = {"x", "de", "y", "para", "p", "con", "c", "s", "el", "la", "por", "kg", "kgr",
         "gr", "g", "cc", "lt", "ml", "k", "un", "uds", "kilo", "kilos", "nuevo"}

UNID = {"kg": 1000, "k": 1000, "kgr": 1000, "g": 1, "gr": 1, "grs": 1,
        "lt": 1000, "l": 1000, "cc": 1, "ml": 1}


def desarmar(nombre):
    """'BALANCED ADULTO RAZA PEQUEÑA X 7,5KG' -> (tokens, pesos_en_gramos)."""
    s = limpiar(nombre)
    s = re.sub(r"\s*-\s*[A-Za-z ]+$", "", s)                  # sufijo de marca
    s = unicodedata.normalize("NFKD", s.lower()).encode("ascii", "ignore").decode()
    s = s.replace(",", ".")
    pesos = set()
    for num, uni in re.findall(r"(\d+(?:\.\d+)?)\s*(kgr|kg|grs|gr|g|lt|l|cc|ml|k)\b", s):
        pesos.add(round(float(num) * UNID[uni]))
    s = re.sub(r"\d+(?:\.\d+)?\s*(kgr|kg|grs|gr|g|lt|l|cc|ml|k)\b", " ", s)
    s = re.sub(r"[^a-z0-9]+", " ", s)
    toks = []
    for t in s.split():
        t = SINONIMOS.get(t, t)
        if t in RUIDO:
            continue
        toks.append(t)
    # "raza pequena" -> un solo token, para que no matchee con cualquier "raza"
    j = " ".join(toks).replace("raza pequena", "razapequena") \
                      .replace("raza mediana", "razamediana") \
                      .replace("raza grande", "razagrande")
    return set(j.split()), pesos


# Tokens que identifican una marca: si aparecen de un lado y no del otro, es otro
# producto (si no, "EXACT PREMIUM ADULTO" matchea con "PREMIUM ADULTO", y
# "CONEJO - CONECAR" con "CONEJO GEPSA").
MARCAS = set()


def cargar_marcas(datos):
    for sec, grupos in datos.items():
        for g in grupos:
            if g in ("VARIEDADES", "—") or "VENENOS" in g or "PIEDRAS" in g:
                continue
            t, _ = desarmar(g)
            MARCAS.update(x for x in t if len(x) >= 4)
    MARCAS.difference_update({"raza", "adulto", "cachorro", "gatos", "gato", "perro",
                              "perros", "propia", "produccion", "semillero", "arroz",
                              "criadores", "sanitarias", "fraccionado"})


def puntuar(a_tok, a_pes, b_tok, b_pes):
    """Devuelve 0..1. 0 = no es el mismo producto."""
    if not a_tok or not b_tok:
        return 0.0
    # la marca tiene que estar de los dos lados (o de ninguno)
    if (a_tok & MARCAS) ^ (b_tok & MARCAS):
        return 0.0
    fuertes_a = {t for t in a_tok if len(t) >= 4}
    fuertes_b = {t for t in b_tok if len(t) >= 4}
    if not fuertes_a or not fuertes_b:
        fuertes_a, fuertes_b = a_tok, b_tok
    # Las palabras con peso tienen que ser LAS MISMAS de los dos lados. Alcanza con
    # que sobre una para que sea otro producto: "HARINA DE ARROZ INTEGRAL" no es
    # "ARROZ INTEGRAL", ni "EXACT PREMIUM ADULTO" es "PREMIUM ADULTO".
    if fuertes_a != fuertes_b:
        return 0.0
    # si los dos declaran presentación y no coincide, es otro producto
    if a_pes and b_pes and not (a_pes & b_pes):
        return 0.0
    inter = len(a_tok & b_tok)
    score = inter / max(len(a_tok), len(b_tok))
    if a_pes and b_pes and (a_pes & b_pes):
        score += 0.25                       # el peso confirma
    elif a_pes and not b_pes:
        score -= 0.05                       # la web no aclara presentación
    return min(1.0, score)


def main():
    prods = json.load(open(f"{WEB}/src/data/productos.json", encoding="utf-8"))
    ov = json.load(open(f"{WEB}/src/data/product-image-overrides.json", encoding="utf-8"))
    datos = separar_mezclas(parsear(bajar_csv(True)))
    cargar_marcas(datos)

    catalogo = []
    for p in prods:
        if not p.get("imagen"):
            continue
        t, w = desarmar(p["nombre"])
        catalogo.append((t, w, p))

    mapa, sin_foto = {}, []
    for sec, grupos in datos.items():
        for g, items in grupos.items():
            for it in items:
                t, w = desarmar(it["desc"])
                mejor = (0.0, None)
                for ct, cw, p in catalogo:
                    s = puntuar(t, w, ct, cw)
                    if s > mejor[0]:
                        mejor = (s, p)
                clave = f"{sec}|{it['cod']}|{it['desc']}"
                if mejor[0] >= 0.55:
                    p = mejor[1]
                    img = ov.get(p["imagen"], p["imagen"])
                    mapa[clave] = {"img": img, "slug": p["slug"],
                                   "nombre_web": p["nombre"], "score": round(mejor[0], 2)}
                else:
                    sin_foto.append({"seccion": sec, "cod": it["cod"], "desc": it["desc"],
                                     "mejor": mejor[1]["nombre"] if mejor[1] else "",
                                     "score": round(mejor[0], 2)})

    json.dump(mapa, open(f"{BASE}/mapa_fotos.json", "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    json.dump(sin_foto, open(f"{BASE}/sin_foto.json", "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)

    tot = len(mapa) + len(sin_foto)
    L = [f"Cobertura de fotos: {len(mapa)}/{tot} ({len(mapa)/tot*100:.0f}%)", ""]
    porsec = collections.Counter(x["seccion"] for x in sin_foto)
    L.append(f"{'SECCION':30s} {'con foto':>9s} {'sin foto':>9s}")
    for sec in datos:
        n = sum(len(v) for v in datos[sec].values())
        L.append(f"{sec:30s} {n - porsec[sec]:9d} {porsec[sec]:9d}")
    L += ["", "--- SIN FOTO ---"]
    for x in sin_foto:
        L.append(f"  [{x['seccion'][:12]:12s}] cod {x['cod']:>5s}  {x['desc']}")
    open(f"{BASE}/cobertura.txt", "w", encoding="utf-8").write("\n".join(L))
    print("\n".join(L[:16]))
    print(f"\n-> mapa_fotos.json ({len(mapa)}) · sin_foto.json ({len(sin_foto)}) · cobertura.txt")


if __name__ == "__main__":
    main()
