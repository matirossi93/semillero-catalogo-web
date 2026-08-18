#!/usr/bin/env python3
"""
Generador del Catálogo Semillero El Manantial (web).

Replica el diseño del PDF original (Catalogo Semillero.pdf, InDesign, 1080x1920)
pero armando las páginas solo, a partir de la lista de precios mayorista viva.

Fuente de datos: Google Sheet "LISTA DE PRECIOS MAYORISTA" (el mismo CSV que ya
consume la app precios.semilleroelmanantial.com.ar).

    python build.py            # baja el sheet y genera index.html
    python build.py --cache    # usa mayorista.csv local (sin red)
"""
import csv, io, json, os, re, sys, unicodedata, urllib.request
from datetime import date

BASE = os.path.dirname(os.path.abspath(__file__))
SHEET_CSV = ("https://docs.google.com/spreadsheets/d/"
             "17iVa59vBeEt3UF3mMdt1ztLXqDL5L2hNylnnJ8p4RQU/export?format=csv&gid=1909734028")
URL_PRECIOS = "https://precios.semilleroelmanantial.com.ar"
URL_WEB = "https://www.semilleroelmanantial.com.ar"

# ---------------------------------------------------------------- geometría
# Todas las medidas salen del PDF original (página 1080x1920).
PAG_W, PAG_H = 1080, 1920
TABLA_X, TABLA_W = 96, 477      # columna izquierda
TABLA_Y0 = 302                  # arranca abajo del header
TABLA_Y1 = 1650                 # tope antes del footer
H_GRUPO, H_FILA = 70, 49        # alto de la barra de marca y de cada fila

CREMA_BG, CREMA_MARCO = "#F8EEE2", "#F0DFCB"
FILA_A, FILA_B = "#EFDFCA", "#F3E7D7"   # zebra
VERDE_TXT, GRIS_TXT = "#236B3E", "#584845"

# (nombre en el sheet, slug de assets, color, título que va en la píldora)
SECCIONES = [
    ("ALIMENTO BALANCEADO ANIMAL", "balanceados", "#DB2525", "ALIMENTO BALANCEADO ANIMAL", "ALIMENTO P/ ANIMALES", "Animales"),
    ("ALIMENTO PARA PERROS",       "perros",      "#FFA500", "ALIMENTO P/ PERROS",         "ALIMENTO P/ PERROS", "Perros"),
    ("ALIMENTO PARA GATOS",        "gatos",       "#E0E055", "ALIMENTO P/ GATOS",          "ALIMENTO P/ GATOS", "Gatos"),
    ("CEREALES PARA DESAYUNO",     "desayuno",    "#82FF82", "CEREALES P/ DESAYUNO",       "CEREALES P/ DESAYUNO", "Cereales p/ desayuno"),
    ("CEREALES",                   "cereales",    "#2FD482", "CEREALES",                   "CEREALES", "Cereales"),
    ("FORRAJES",                   "forrajes",    "#00BEE0", "FORRAJES",                   "FORRAJES", "Forrajes"),
    ("LEGUMBRES",                  "legumbres",   "#2B2BD6", "LEGUMBRES",                  "LEGUMBRES", "Legumbres"),
    ("CONDIMENTOS",                "condimentos", "#FF69B4", "CONDIMENTOS",                "CONDIMENTOS", "Condimentos"),
    ("FRUTOS SECOS",               "frutos",      "#FF00FF", "FRUTOS SECOS",               "FRUTOS SECOS", "Frutos Secos"),
    ("SNACKS",                     "snacks",      "#A17C0D", "SNACKS",                     "SNACKS", "Snacks"),
    ("VENENOS",                    "venenos",     "#0C5013", "VENENOS",                    "VENENOS", "Venenos"),
    ("ACCESORIOS",                 "accesorios",  "#8000FF", "ACCESORIOS",                 "ACCESORIOS", "Accesorios"),
]
NOMBRES = [s[0] for s in SECCIONES]


def q(px, base=PAG_W):
    """px del diseño original -> unidades de contenedor (escala con el ancho)."""
    return f"{px / base * 100:.4f}cqw"


def luminancia(hexcol):
    r, g, b = (int(hexcol[i:i + 2], 16) / 255 for i in (1, 3, 5))
    f = lambda c: c / 12.92 if c <= .03928 else ((c + .055) / 1.055) ** 2.4
    return .2126 * f(r) + .7152 * f(g) + .0722 * f(b)


def txt_sobre(hexcol):
    """El PDF usa crema sobre colores oscuros y casi-negro sobre los claros."""
    return "#291C19" if luminancia(hexcol) > 0.4 else CREMA_BG


# ---------------------------------------------------------------- datos
def bajar_csv(usar_cache=False):
    cache = os.path.join(BASE, "mayorista.csv")
    if usar_cache and os.path.exists(cache):
        return open(cache, "rb").read().decode("utf-8")
    req = urllib.request.Request(SHEET_CSV, headers={"User-Agent": "catalogo-semillero/1.0"})
    data = urllib.request.urlopen(req, timeout=60).read()
    open(cache, "wb").write(data)
    return data.decode("utf-8")


# Códigos que en la planilla mayorista están MAL y en InfoManager son otros.
# El Flecky carne fresca se cargó copiando la fila del tradicional y quedó con su
# mismo código; en IM son artículos aparte y con stock propio (verificado contra
# GET /articulos/stock el 11/08/2026: 284 -> 203 bolsas, 285 -> 116).
# Clave: (sección, código de la planilla, descripción) -> código real de IM.
CODIGOS_IM = {
    ("ALIMENTO PARA PERROS", "165", 'FLECKY AD "NUEVO" CARNE  FRESCA X 15 KG'): "284",
    ("ALIMENTO PARA PERROS", "166", 'FLECKY AD "NUEVO" CARNE  FRESCA X 20 KG'): "285",
}


def parsear(texto):
    """Sheet -> {seccion: {grupo: [productos]}}.

    El sheet marca las secciones en la columna 1 y las marcas/subgrupos en la 2
    (salvo NUTRIFOOD, que va en la 1). El layout de precios cambia por sección,
    así que se detecta con la fila 'COD'.
    """
    rows = list(csv.reader(io.StringIO(texto)))
    out, sec, grupo, hdr = {}, None, None, None
    for i, r in enumerate(rows):
        if i < 27:                      # encabezado del sheet e índice
            continue
        c = [x.strip() for x in (r + [""] * 9)[:9]]
        a, b = c[1], c[2]
        precios = [x for x in c[3:] if x.startswith("$")]
        if a in NOMBRES and not b:
            sec = a
            out.setdefault(sec, {})     # ACCESORIOS aparece 2 veces: no pisar
            grupo = None
            continue
        if sec is None:
            continue
        if a.upper() == "COD":
            hdr = [x for x in c[3:] if x]
            continue
        if a and not b and not precios and len(a) > 3 and not a.replace(".", "").isdigit():
            if a.startswith("*"):
                continue
            grupo = a
            out[sec].setdefault(grupo, [])
            continue
        if b and not a and not precios and len(b) > 2:
            grupo = b
            out[sec].setdefault(grupo, [])
            continue
        if b and (a or precios):
            out[sec].setdefault(grupo or "VARIEDADES", []).append(
                {"cod": CODIGOS_IM.get((sec, a, b), a), "desc": b,
                 "cols": hdr or [], "precios": [x for x in c[3:] if x]})
    return out


def separar_mani_king(datos):
    """Mani King como sección propia dentro de SNACKS.

    Es una marca entera (pastas + fraccionados) que estaba diluida entre los
    snacks sueltos. En la planilla se reconoce por el sufijo "- Mani King" o por
    las líneas Cheff/Crocante, que también son de ellos.
    """
    sec = datos.get("SNACKS")
    if not sec:
        return datos
    king, resto = [], {}
    for grupo, items in sec.items():
        quedan = []
        for it in items:
            d = limpiar(it["desc"]).upper()
            if "KING" in d or "CHEFF" in d or "CROCANTE" in d:
                king.append(it)
            else:
                quedan.append(it)
        if quedan:
            resto[grupo] = quedan
    if king:
        datos["SNACKS"] = {"MANI KING": king, **resto}
    return datos


def separar_granolas(datos):
    """Las granolas artesanales son producción nuestra, no NutriFood.

    En la planilla están mezcladas dentro del bloque NUTRIFOOD, pero las armamos
    acá, así que van con grupo propio y primeras.
    """
    sec = datos.get("CEREALES PARA DESAYUNO")
    if not sec:
        return datos
    propias, resto = [], {}
    for grupo, items in sec.items():
        quedan = []
        for it in items:
            if "ARTESANAL" in limpiar(it["desc"]).upper():
                propias.append(it)
            else:
                quedan.append(it)
        if quedan:
            resto[grupo] = quedan
    if propias:
        datos["CEREALES PARA DESAYUNO"] = {"GRANOLAS ARTESANALES": propias, **resto}
    return datos


def separar_mezclas(datos):
    """Saca las mezclas de la bolsa de 'VARIEDADES' y les da grupo propio.

    Las mezclas las armamos nosotros (no son reventa), así que van primeras y con
    su propia barra, no perdidas en la lista alfabética de forrajes.
    """
    forr = datos.get("FORRAJES")
    if not forr:
        return datos
    mezclas, resto = [], {}
    for grupo, items in forr.items():
        quedan = []
        for it in items:
            d = limpiar(it["desc"]).upper()
            if d.startswith("MEZCLA") or "CABALLO PREMIUM" in d:
                mezclas.append(it)
            else:
                quedan.append(it)
        if quedan:
            resto[grupo] = quedan
    if mezclas:
        datos["FORRAJES"] = {"MEZCLAS PROPIAS": mezclas, **resto}
    return datos


# Caracteres mal cargados en el Sheet mayorista (verificado 11/08/2026: 130
# productos). Se limpian acá para no arrastrar la basura al catálogo, pero el
# arreglo de fondo va en la planilla: ver reporte_sheet.txt.
BASURA = {"░": "°", "║": "°", "Ð": "Ñ", "�": "Ñ"}


def limpiar(s):
    for malo, bueno in BASURA.items():
        s = s.replace(malo, bueno)
    return s


def linda(s):
    """MAYUSCULAS DEL SHEET -> 'Capitalizado como en el catálogo'."""
    s = limpiar(s).strip()
    s = re.sub(r"\s*-\s*[A-Za-z ]+$", "", s)          # saca el sufijo de marca
    s = re.sub(r"\s+", " ", s)
    s = s[:1].upper() + s[1:].lower()
    s = re.sub(r"\bx\s*(\d)", r"x \1", s)
    s = re.sub(r"(\d)\s*(kgr|kg|gr|cc|lt|ml|k|g)\b", r"\1 \2", s)
    s = re.sub(r"(\d) kgr\b", r"\1 kg", s)      # el sheet escribe "8 kgr"
    s = re.sub(r"(\d) k\b", r"\1 kg", s)        # y a veces "10 k"
    s = re.sub(r"\bn[°ºo]\s*(\d)", r"n° \1", s)
    return s.strip()


# ---------------------------------------------------------------- paginado
def paginar(grupos):
    """Reparte grupos y productos en páginas, igual que se hizo a mano en el PDF.

    Llena cada página hasta abajo antes de pasar a la siguiente: la versión anterior
    cortaba en el primer grupo que no entraba entero y dejaba medio pliego en blanco
    (había páginas donde la tabla terminaba a un tercio de la hoja). Un grupo nunca
    queda con su barra de marca sola al pie: si abajo del título no entran al menos
    MIN_FILAS renglones, el grupo arranca en la página siguiente.
    """
    alto = TABLA_Y1 - TABLA_Y0
    MIN_FILAS = 3
    paginas, actual, usado = [], [], 0
    for nombre, items in grupos.items():
        if not items:
            continue
        resto, primero = list(items), True
        while resto:
            libre = int((alto - usado - H_GRUPO) // H_FILA)
            if libre < min(MIN_FILAS, len(resto)):
                if actual:
                    paginas.append(actual)
                actual, usado = [], 0
                libre = int((alto - H_GRUPO) // H_FILA)
            tanda, resto = resto[:libre], resto[libre:]
            actual.append({"grupo": nombre if primero else nombre + " (cont.)",
                           "items": tanda})
            usado += H_GRUPO + H_FILA * len(tanda)
            primero = False
    if actual:
        paginas.append(actual)
    return paginas


# ---------------------------------------------------------------- HTML
def esc(s):
    return (s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))


# Ancho medio por carácter, medido sobre el PDF original (em por carácter).
EM_ROBOTO, EM_BEBAS = 0.409, 0.366


def encoger(texto, ancho, size, em, minimo):
    """Devuelve el font-size que hace entrar el texto en una línea.

    El PDF original tiene todo en una línea; si algo no entra, la diseñadora lo
    abreviaba. Acá se abrevia primero (ABREVIA) y esto queda de red de seguridad.
    """
    if not texto:
        return size
    necesario = ancho / (len(texto) * em)
    return round(max(minimo, min(size, necesario)), 1)


# Abreviaturas que el catálogo original ya usaba, para que el texto entre.
ABREVIA = [
    ("PRODUCCION PROPIA SEMILLERO", "PROD. PROPIA SEMILLERO"),
    ("VENENOS MOSCAS Y CUCARACHAS", "MOSCAS Y CUCARACHAS"),
    ("FRACCIONADOS NUTRIFOOD", "NUTRIFOOD FRACCIONADO"),
    ("VENENOS HORMIGAS", "HORMIGAS"), ("VENENOS RATAS", "RATAS"),
    ("VENENOS INSECTOS", "INSECTOS"), ("DOG SELECCIÓN", "DOG SELECTION"),
    ("PIEDRAS SANITARIAS", "PIEDRAS SANITARIAS"), ("PAJAROS", "AVES"),
]


def abreviar_grupo(g):
    cont = g.endswith(" (cont.)")
    base = limpiar(g[:-8] if cont else g)
    for a, b in ABREVIA:
        if base.upper() == a:
            base = b
            break
    return base + (" (cont.)" if cont else "")


ABREV_PROD = [
    ("raza pequeña", "rza. peq"), ("raza mediana", "rza. med"),
    ("raza grande", "rza. gde"), ("cachorro", "cach."),
    ("nutrimax", "nutrimax"), ("sanitaria", "sanit."),
    ("semanas", "sem"), ("unidades", "u"),
]


def abreviar_prod(s, limite=34):
    """Va abreviando de a poco hasta que el nombre entre en la fila."""
    for a, b in ABREV_PROD:
        if len(s) <= limite:
            break
        s = re.sub(a, b, s, flags=re.I)
    return s


def sin_marca(desc, marca):
    """'FLECKY ADULTO CARNE X 15 KG' + marca FLECKY -> 'Adulto carne x 15 kg'.

    En el catálogo original la píldora dice sólo la variante ("Adulto x15 kg"),
    nunca repite la marca: ya está en la barra de arriba de la tabla. Repetirla
    hacía píldoras larguísimas que se salían de la columna.
    """
    d, m = limpiar(desc).upper().strip(), limpiar(marca).upper().strip()
    for pref in (m, m.replace("-", " "), m.split()[0] if m else ""):
        if pref and len(pref) > 2 and d.startswith(pref):
            resto = d[len(pref):].strip(" -.")
            if len(resto) > 3:
                return linda(resto)
    return linda(desc)


COL_FOTOS_W = 384          # ancho de la columna derecha
H_PILDORA, GAP_FOTO = 56, 26
COL_H = TABLA_Y1 - TABLA_Y0
# Una foto por familia, así que el tope es cuántas MARCAS distintas se muestran.
# En el PDF van de 1 a 9 según el tamaño de las fotos; el alto lo resuelve entran().
TOPE_TARJETAS = 5
MAX_PILDORAS = 4      # el original nunca lista más de 4 variedades por foto
# Secciones donde cada producto se muestra con SU foto en vez de agrupar la familia:
# son surtidos donde la gracia es justamente ver cada variedad (Mati, 12/08).
POR_PRODUCTO = {"CEREALES PARA DESAYUNO"}
TOPE_ABSOLUTO = 9     # el máximo que llegó a poner la diseñadora en una página
DIAM_CIRCULO = 0.86   # diámetro del círculo, en fracción del ancho de la columna
# Secciones a granel: el original muestra el producto en círculo con aro de color
# (una toma del cereal, la especia, la mezcla). Las de envase van recortadas y sueltas.
GRANEL = {"desayuno", "cereales", "forrajes", "legumbres", "condimentos", "frutos"}
ALTO_MAX, ALTO_MIN = 760, 170   # rango de alto de una foto de producto
# La foto de fondo sólo entra cuando queda MUCHO libre: si los productos ocupan
# casi toda la columna, el fondo se ve por hilitos entre las fotos y queda peor que
# no ponerlo. En el PDF el fondo aparece con 0-4 fotos chicas flotando, nunca lleno.
ALTO_AMBIENTE_MIN = int((TABLA_Y1 - TABLA_Y0) * 0.55)
# Hueco mínimo al pie de una columna para que valga la pena taparlo con foto.
ALTO_RELLENO = 420
# Las píldoras montan sobre el borde de abajo de la foto (así lo hace el original).
MONTA_PILDORA = 30


def alto_imagen(fn, tope, redonda=False):
    """Alto que va a ocupar la foto en la columna, con ese tope.

    Las recortadas conservan su forma (una bolsa queda vertical, una banda queda
    apaisada). Las de las secciones a granel van en círculo, como en el original,
    así que su alto es el diámetro.
    """
    if redonda:
        return min(tope, COL_FOTOS_W * DIAM_CIRCULO)
    try:
        from PIL import Image
        w, h = Image.open(os.path.join(BASE, "assets", fn)).size
        return min(tope, COL_FOTOS_W * h / w)
    except Exception:
        return tope


def alto_foto(fn, tope=300, pills=1, redonda=False):
    """Alto de la tarjeta entera: la imagen, sus píldoras y el aire de abajo."""
    # Las píldoras van montadas SOBRE la foto (position:absolute), así que no suman
    # alto: por eso las fotos pueden ser mucho más grandes que antes.
    return alto_imagen(fn, tope, redonda) + GAP_FOTO


def entran(fotos, reservado=0, granel=False):
    """Arma la columna: las fotos lo más grandes posible sin pasarse de largo.

    Busca el tope de alto más grande con el que TODAS entren (búsqueda binaria, no
    escalones fijos: los escalones dejaban 100-200 px de hueco al pedo). Si ni con
    el mínimo entran, saca la última y vuelve a probar.

    Devuelve (fotos, tope, sobrante). El sobrante aparece cuando las fotos son
    apaisadas —una mezcla, un fertilizante— y por más que se agrande el tope no
    llenan la columna: ese hueco es el que después tapa la foto de ambiente.
    """
    libre0 = COL_H - (reservado or 0)

    def es_redonda(f):
        return granel

    def total(fs, tope):
        return sum(alto_foto(f["img"], tope, len(f.get("variantes", [1])), es_redonda(f))
                   for f in fs)

    def ajustar(fs):
        """El tope más grande con el que entra esta lista, o None si no entra."""
        if not fs or total(fs, ALTO_MIN) > libre0:
            return None
        lo, hi = ALTO_MIN, ALTO_MAX
        for _ in range(16):
            mid = (lo + hi) / 2
            if total(fs, mid) <= libre0:
                lo = mid
            else:
                hi = mid
        return fs, lo, libre0 - total(fs, lo)

    n = min(len(fotos), TOPE_TARJETAS)
    mejor = None
    while n > 0 and mejor is None:
        mejor = ajustar(fotos[:n])
        n -= 1
    if mejor is None:
        return [], ALTO_MIN, libre0
    # Las tomas apaisadas (mezclas, fertilizantes) tocan techo por su propia forma:
    # por más que se agrande el tope no llenan la columna. En ese caso se suman más
    # productos en vez de dejar el hueco — es lo que pidió Mati: ocupar con otros.
    # Se suman más fotos mientras entren SIN achicar a las que ya están: es lo que
    # llena la columna en vez de dejar el hueco (mezclas, fertilizantes), y lo que
    # pidió Mati — ocupar ese espacio con los otros productos.
    elegidas, tope, sobra = mejor
    for f in fotos[len(elegidas):TOPE_ABSOLUTO]:
        a = alto_foto(f["img"], tope, len(f.get("variantes", [1])), es_redonda(f))
        if a > sobra:
            break
        elegidas = elegidas + [f]
        sobra -= a
    return elegidas, tope, sobra


# Ambiente: se va rotando para que dos páginas seguidas de la misma sección no
# repitan la misma foto (fue el reclamo con las fotos de relleno de accesorios).
_TURNO_AMB = {}


_ALFA = {}


def recortada(fn):
    """¿La foto viene con el fondo sacado (canal alfa)?

    Sobre la foto de fondo sólo pueden ir productos recortados: si la foto todavía
    tiene su fondo de estudio se ve el rectángulo pegoteado encima, que es
    exactamente lo que el original NO hace.
    """
    if fn not in _ALFA:
        try:
            from PIL import Image
            im = Image.open(os.path.join(BASE, "assets", fn))
            if im.mode not in ("RGBA", "LA"):
                _ALFA[fn] = False
            else:
                _ALFA[fn] = im.getchannel("A").getextrema()[0] < 250
        except Exception:
            _ALFA[fn] = False
    return _ALFA[fn]


_VACIO = {}


def transparencia(fn):
    """Qué proporción de la foto es transparente (0-1)."""
    if fn not in _VACIO:
        try:
            from PIL import Image
            im = Image.open(os.path.join(BASE, "assets", fn))
            if im.mode not in ("RGBA", "LA"):
                _VACIO[fn] = 0.0
            else:
                a = im.getchannel("A").resize((64, 64))
                _VACIO[fn] = sum(1 for v in a.getdata() if v < 128) / 4096
        except Exception:
            _VACIO[fn] = 0.0
    return _VACIO[fn]


def ambiente_hay(slug):
    d = os.path.join(BASE, "assets", "ambiente")
    return os.path.isdir(d) and any(f.startswith(slug + "-") for f in os.listdir(d))


def ambiente_de(slug):
    d = os.path.join(BASE, "assets", "ambiente")
    if not os.path.isdir(d):
        return None
    opciones = sorted(f for f in os.listdir(d) if f.startswith(slug + "-"))
    if not opciones:
        return None
    i = _TURNO_AMB.get(slug, 0)
    _TURNO_AMB[slug] = i + 1
    return "ambiente/" + opciones[i % len(opciones)]


def boton_precios(compacto=True):
    txt = "CLICK AQUÍ PARA<br>VER LOS PRECIOS" if compacto else \
          "CLICK AQUÍ PARA CONSULTAR LOS PRECIOS"
    sub = "" if compacto else '<em>TAMBIÉN PODÉS ENCONTRAR ESTE BOTÓN EN CADA SECCIÓN</em>'
    return (f'<a class="btn-precios{" ancho" if not compacto else ""}" href="{URL_PRECIOS}" '
            f'target="_blank" rel="noopener"><span class="pesito">$</span>'
            f'<span class="btxt">{txt}{sub}</span></a>')


def pag_portada():
    tiras_top = ["balanceados", "perros", "gatos", "desayuno", "cereales", "forrajes"]
    tiras_bot = ["legumbres", "condimentos", "frutos", "snacks", "venenos", "accesorios"]
    col = {s[1]: s[2] for s in SECCIONES}
    def tira(slugs, pos):
        out = []
        for s in slugs:
            out.append(f'<div class="tira"><i style="background:{col[s]}"></i>'
                       f'<img src="assets/iconos/{s}.webp" alt=""></div>')
        return f'<div class="tiras {pos}">' + "".join(out) + "</div>"
    return f"""
<section class="pag portada" id="p1">
  {tira(tiras_top, 'arriba')}
  <div class="portada-centro">
    <div class="pill-catalogo">CATÁLOGO</div>
    <img class="logo-grande" src="assets/iconos/logo.webp" alt="Semillero El Manantial S.R.L.">
    <hr>
    <p>0381 331-5389</p>
    <p>SAN MARTIN 105, BANDA DE RÍO SALÍ, TUCUMÁN, ARGENTINA</p>
    <p><a href="{URL_WEB}" target="_blank" rel="noopener">WWW.SEMILLEROELMANANTIAL.COM.AR</a></p>
  </div>
  {tira(tiras_bot, 'abajo')}
</section>"""


def pag_indice(indice, actualizado):
    filas = []
    for nombre, slug, color, _p, _t, corto in SECCIONES:
        if nombre not in indice:
            continue
        filas.append(
            f'<li><i style="background:{color}"></i>'
            f'<a href="#{slug}"><span>{esc(corto)}</span>'
            f'<b>{indice[nombre]:02d}</b></a></li>')
    return f"""
<section class="pag indice" id="p2">
  <img class="foto-indice" src="assets/hero/cereales.webp" alt="">
  <img class="logo-indice" src="assets/iconos/logo.webp" alt="Semillero El Manantial">
  <h2>ÍNDICE</h2>
  <ul class="lista-indice">{''.join(filas)}</ul>
  {boton_precios(compacto=False)}
  <div class="foot"><span class="nropag">2</span></div>
  <p class="actualizado">Actualizado el {actualizado} · se sincroniza solo con la lista de precios</p>
</section>"""


def pag_seccion(slug, color, titulo, nro, ext):
    return f"""
<section class="pag sec-portada" id="{slug}" style="--c:{color}">
  <img class="hero" src="assets/hero/{slug}.{ext}" alt="">
  <img class="logo-chip" src="assets/iconos/logo_chip.webp" alt="Semillero El Manantial">
  <div class="sec-pie">
    <img class="ico-grande" src="assets/iconos/{slug}.webp" alt="">
    <div class="barra"></div>
    <h1>{esc(titulo)}</h1>
  </div>
  <div class="foot"><span class="nropag">{nro}</span></div>
</section>"""


def pag_descripcion(slug, color, pill, familia, productos, nro, ban_ext, fotos=()):
    """Hoja de explicación: sin tabla, la familia y un texto contándole al cliente
    de qué se trata el producto, con una foto de ambiente al costado.

    Son las páginas 6 y 7 del PDF original, que el catálogo web no tenía. El texto
    sale de descripciones.json (extraído del PDF, no reescrito). Va en flujo normal,
    no posicionado: calcular el alto de un párrafo a ojo se pasaba y los bloques se
    pisaban entre sí.
    """
    def alto_con(fs):
        """Alto estimado de la hoja con ese cuerpo de letra (para elegir el tamaño)."""
        cpl_txt = max(12, (TABLA_W - 36 - 44) / (fs * EM_ROBOTO)) * 0.92
        cpl_nom = max(12, (TABLA_W - 30) / (30 * EM_ROBOTO))
        alto = H_GRUPO
        for pr in productos:
            alto += 28 + 34 * max(1, -(-len(pr["nombre"]) // int(cpl_nom)))
            renglones = max(1, -(-len(pr["texto"]) // int(cpl_txt)))
            for b in pr.get("bullets", []):
                renglones += max(1, -(-len(b) // int(cpl_txt * 0.9)))
            alto += 40 + renglones * fs * 1.32 + 10 * len(pr.get("bullets", []))
        return alto

    # El cuerpo se achica solo hasta que la hoja entre entera: calcular el alto a ojo
    # se pasaba y el último párrafo quedaba cortado a la mitad.
    fs = next((t for t in (26, 24, 22, 20, 18, 16) if alto_con(t) <= COL_H), 16)
    bloques = []
    for pr in productos:
        cuerpo = f'<p>{esc(pr["texto"])}</p>'
        if pr.get("bullets"):
            cuerpo += "<ul>" + "".join(f"<li>{esc(b)}</li>" for b in pr["bullets"]) + "</ul>"
        bloques.append(f'<h3>{esc(pr["nombre"])}</h3><div class="desc-txt">{cuerpo}</div>')
    # El original ilustra estas hojas de dos maneras: con las fotos de los productos
    # que describe, en círculo con aro del color de la sección (pág. 5 del PDF), o con
    # una foto de ambiente de columna entera cuando no hay suficientes (pág. 6 y 7).
    if len(fotos) >= 3:
        alto = min(330, (COL_H - GAP_FOTO * len(fotos)) / len(fotos))
        tarjetas = "".join(
            f'<figure class="{"der" if k % 2 else "izq"} redonda'
            f'{" recorte" if transparencia(f) > 0.10 else ""}" style="--alto:{q(alto)}">'
            f'<span class="marco"><img src="assets/{f}" alt="" loading="lazy"></span></figure>'
            for k, f in enumerate(fotos[:4]))
        foto = f'<div class="fotos reparte">{tarjetas}</div>'
    else:
        amb = ambiente_de(slug)
        foto = (f'<div class="fotos"><img class="fondo" src="assets/{amb}" alt=""'
                f' loading="lazy"></div>') if amb else ""
    return f"""
<section class="pag contenido" style="--c:{color}">
  <div class="banner"><img src="assets/banner/{slug}.{ban_ext}" alt=""></div>
  {boton_precios()}
  <div class="pill-sec"><img src="assets/iconos/{slug}.webp" alt=""><span>{esc(pill)}</span></div>
  <div class="desc-col" style="font-size:{q(fs)}">
    <div class="grupo desc" style="color:{txt_sobre(color)}">{esc(familia)}</div>
    {''.join(bloques)}
  </div>
  {foto}
  <div class="foot">
    <img class="logo-foot" src="assets/iconos/logo.webp" alt="">
    <span class="nropag">{nro}</span>
    <span class="disclaimer">* Precios sujetos a modificación<br>sin previo aviso.</span>
  </div>
  <div class="barra-pie"></div>
</section>"""


def bloque_ambiente(slug, alto, ancho_col, arriba=None):
    """Foto de ambiente para tapar el hueco que queda al pie de una columna.

    Es lo que hace el original cuando la tabla se termina antes que la hoja
    (págs. 19, 28 y 30 del PDF: la toma de la sección ocupa lo que sobra de la
    columna izquierda). Sin esto quedaban páginas con medio pliego en blanco.
    """
    amb = ambiente_de(slug)
    if not amb:
        return ""
    pos = f"top:{q(arriba)};" if arriba is not None else ""
    return (f'<div class="relleno" style="{pos}height:{q(alto)};width:{q(ancho_col)}">'
            f'<img src="assets/{amb}" alt="" loading="lazy"></div>')


def pag_contenido(slug, color, pill, bloques, fotos, nro, ban_ext):
    filas_html, y = [], TABLA_Y0
    for b in bloques:
        g = abreviar_grupo(b["grupo"])
        fs = encoger(g, 436, 46, EM_BEBAS, 30)
        filas_html.append(
            f'<div class="grupo" style="top:{q(y)};color:{txt_sobre(color)};'
            f'font-size:{q(fs)}">{esc(g)}</div>')
        y += H_GRUPO
        for k, it in enumerate(b["items"]):
            bg = FILA_A if k % 2 else FILA_B
            nom = abreviar_prod(linda(it["desc"]))
            fs = encoger(nom, 448, 32, EM_ROBOTO, 19)
            filas_html.append(
                f'<div class="fila" style="top:{q(y)};background:{bg};'
                f'font-size:{q(fs)}"><span>{esc(nom)}</span></div>')
            y += H_FILA
    # Columna derecha: una tarjeta por producto de ESTA página que tenga foto.
    # Criterio único para todas: mismo cuadro, imagen contenida sin recortar,
    # sin marco, y la píldora con el nombre abajo (como el original).
    sobra_tabla = TABLA_Y1 - y
    logo = next((LOGOS_MARCA[b["grupo"].replace(" (cont.)", "")] for b in bloques
                 if b["grupo"].replace(" (cont.)", "") in LOGOS_MARCA), None)
    tarjetas, sobra, elegidas = [], COL_H, []
    if logo:
        tarjetas.append(f'<figure class="logo-marca"><img src="assets/{logo}" alt=""></figure>')
    if fotos:
        reserva_logo = 118 if logo else 0
        elegidas, tope, sobra = entran(fotos, reserva_logo, slug in GRANEL)
        # Dos maneras de resolver una página floja, las dos del PDF: llenar la columna
        # con fotos prestadas de la misma sección, o mostrar sólo las propias sobre una
        # foto de fondo de columna entera. Se elige la del fondo sólo si de verdad
        # queda lugar para que se vea; si no, gana llenar con productos.
        propias = [f for f in fotos if not f.get("prestada")]
        if propias and len(propias) < len(fotos) and ambiente_hay(slug):
            # sobre el fondo sólo van productos recortados: los que traen su fondo de
            # estudio se ven como un rectángulo pegoteado, que es lo que el PDF no hace
            limpias = [f for f in propias if recortada(f["img"]) or slug in GRANEL]
            alt = entran(limpias, reserva_logo, slug in GRANEL) if limpias else None
            if alt and alt[2] >= ALTO_AMBIENTE_MIN:
                elegidas, tope, sobra = alt
            else:
                sobra = 0        # se queda con las prestadas: no va foto de fondo
        for k, f in enumerate(elegidas):
            # El badge del original: círculo negro con aro blanco, la palabra
            # PROTEÍNAS en una píldora naranja montada a caballo del borde de arriba,
            # y el asterisco abajo del % cuando el dato es de otra variante (cachorro).
            badge = "".join(
                f'<span class="prot"><i>PROTEÍNAS</i><u>{v}<b>%</b>'
                f'{"<s>*</s>" if j else ""}</u></span>'
                for j, v in enumerate(f.get("prots") or ([f["prot"]] if f.get("prot") else [])))
            pills = "".join(f"<span>{esc(v)}</span>" for v in f.get("variantes", [f["nom"]]))
            # Las fotos alternan de lado y se solapan un poco, como la cadena del
            # original; las píldoras van SIEMPRE montadas sobre la esquina inferior
            # izquierda de la foto, nunca colgando abajo.
            lado = "der" if k % 2 else "izq"
            if slug in GRANEL:
                # sólo se muestra entera adentro del círculo si es un recorte de
                # verdad; una toma llena el círculo (cover), como en el PDF
                forma = " redonda" + (" recorte" if transparencia(f["img"]) > 0.10 else "")
            else:
                # fuera de las secciones a granel el envase va suelto; las tomas que
                # traen su propio fondo van en marco crema, nunca sueltas en la hoja
                forma = "" if recortada(f["img"]) else " marco-foto"
            tarjetas.append(
                f'<figure class="{lado}{forma}" style="--alto:{q(alto_imagen(f["img"], tope, bool(forma)))}">'
                f'<span class="marco">'
                f'<img src="assets/{f["img"]}" alt="{esc(f["nom"])}" loading="lazy">'
                f'</span>{badge}<figcaption>{pills}</figcaption></figure>')
    # Cuando las fotos de producto no llenan la columna va una FOTO DE FONDO que
    # ocupa la columna entera, con los productos encima. Así lo hace el PDF (pág. 26:
    # la toma de especias de arriba abajo y los productos flotando sobre ella); antes
    # yo la apilaba abajo como una tarjeta más y quedaba una banda achatada.
    fondo = ""
    if sobra >= ALTO_AMBIENTE_MIN:
        amb = ambiente_de(slug)
        if amb:
            fondo = f'<img class="fondo" src="assets/{amb}" alt="" loading="lazy">'
    # El hueco del pie se tapa con una toma de la sección, en la columna que haya
    # quedado corta. Sólo en UNA de las dos: dos fotos de ambiente en la misma hoja
    # se leen como relleno, y el original nunca lo hace.
    relleno_tabla = relleno_fotos = ""
    if sobra_tabla >= ALTO_RELLENO:
        relleno_tabla = bloque_ambiente(slug, sobra_tabla - GAP_FOTO, TABLA_W, y + GAP_FOTO)
    elif not fondo and tarjetas and sobra >= ALTO_RELLENO:
        relleno_fotos = bloque_ambiente(slug, sobra - GAP_FOTO, COL_FOTOS_W)
    if not tarjetas and not fondo:
        fotos_html = ""
    else:
        clase = "fotos confondo" if fondo else "fotos"
        fotos_html = f'<div class="{clase}">{fondo}{"".join(tarjetas)}{relleno_fotos}</div>'
    return f"""
<section class="pag contenido" style="--c:{color}">
  <div class="banner"><img src="assets/banner/{slug}.{ban_ext}" alt=""></div>
  {boton_precios()}
  <div class="pill-sec"><img src="assets/iconos/{slug}.webp" alt=""><span>{esc(pill)}</span></div>
  <div class="tabla">{''.join(filas_html)}{relleno_tabla}</div>
  {fotos_html}
  <div class="foot">
    <img class="logo-foot" src="assets/iconos/logo.webp" alt="">
    <span class="nropag">{nro}</span>
    <span class="disclaimer">* Precios sujetos a modificación<br>sin previo aviso.</span>
  </div>
  <div class="barra-pie"></div>
</section>"""


def css():
    return f"""
:root{{--crema:{CREMA_BG};--marco:{CREMA_MARCO};--verde:{VERDE_TXT};--gris:{GRIS_TXT}}}
*{{box-sizing:border-box;margin:0;padding:0}}
body{{background:#e6ded3;font-family:'Roboto Condensed','Arial Narrow','Liberation Sans Narrow',system-ui,sans-serif;font-stretch:condensed;
  display:flex;flex-direction:column;align-items:center;gap:{q(28)};padding:{q(28)} 0}}
.pag{{container-type:inline-size;position:relative;width:min(1080px,100vw);aspect-ratio:1080/1920;
  background:var(--crema);overflow:hidden;box-shadow:0 .3rem 1.4rem #0003;flex:none}}
.pag::before{{content:"";position:absolute;inset:0;border:{q(28)} solid var(--marco);
  pointer-events:none;z-index:6}}

/* ---------- portada ---------- */
.portada{{display:flex;flex-direction:column;justify-content:space-between}}
.tiras{{display:flex;justify-content:center;gap:{q(14)};position:relative;z-index:2}}
.tiras.arriba{{padding-top:{q(28)}}}
.tiras.abajo{{padding-bottom:{q(28)};align-items:flex-end}}
.tira{{position:relative;width:{q(118)}}}
.tira i{{display:block;height:{q(210)};border-radius:0 0 {q(10)} {q(10)}}}
.tiras.abajo .tira i{{border-radius:{q(10)} {q(10)} 0 0}}
.tira img{{position:absolute;left:50%;transform:translateX(-50%);bottom:{q(-34)};
  width:{q(88)};border-radius:50%}}
.tiras.abajo .tira img{{bottom:auto;top:{q(-34)}}}
.portada-centro{{text-align:center;padding:0 {q(70)}}}
.pill-catalogo{{background:#14562A;color:#fff;font-family:'Bebas Neue',sans-serif;
  font-size:{q(62)};letter-spacing:{q(14)};padding:{q(14)} 0 {q(8)};
  border-radius:{q(46)};margin-bottom:{q(46)}}}
.logo-grande{{width:{q(620)}}}
.portada-centro hr{{border:0;border-top:{q(4)} solid var(--verde);width:{q(190)};margin:{q(60)} auto {q(28)}}}
.portada-centro p{{font-size:{q(26)};letter-spacing:{q(1.5)};color:var(--gris);line-height:1.9}}
.portada-centro a{{color:inherit;text-decoration:none}}

/* ---------- índice ---------- */
.foto-indice{{position:absolute;top:{q(28)};left:{q(96)};width:{q(888)};height:{q(500)};
  object-fit:cover;border-radius:0 0 {q(60)} {q(60)}}}
.logo-indice{{position:absolute;top:{q(566)};left:50%;transform:translateX(-50%);
  width:{q(700)}}}
.indice h2{{position:absolute;top:{q(786)};left:{q(203)};font-family:'Bebas Neue',sans-serif;
  font-size:{q(60)};color:var(--verde);letter-spacing:{q(2)}}}
.lista-indice{{position:absolute;top:{q(880)};left:{q(203)};right:{q(208)};
  list-style:none}}
.lista-indice li{{position:relative;display:flex;align-items:center;height:{q(58)}}}
/* las pastillas de color cuelgan a la izquierda del bloque, como el original */
.lista-indice i{{position:absolute;left:{q(-155)};width:{q(86)};height:{q(26)};
  border-radius:{q(13)};flex:none}}
.lista-indice a{{flex:1;display:flex;align-items:baseline;gap:{q(10)};text-decoration:none;
  color:var(--verde);font-size:{q(30)}}}
.lista-indice span::after{{content:"";flex:1;border-bottom:{q(3)} dotted #bda98f;
  margin:0 {q(10)} {q(6)}}}
.lista-indice a{{align-items:center}}
.lista-indice span{{flex:1;display:flex;align-items:center}}
.lista-indice b{{font-weight:400;color:var(--verde);font-size:{q(30)}}}
.actualizado{{position:absolute;bottom:{q(56)};left:0;right:0;text-align:center;
  font-size:{q(19)};color:#8d7a68;font-style:italic}}

/* ---------- portada de sección ---------- */
.sec-portada .hero{{position:absolute;top:0;left:{q(96)};width:{q(888)};height:{q(1730)};
  object-fit:cover;border-radius:0 0 {q(50)} {q(50)}}}
.logo-chip{{position:absolute;top:{q(-14)};left:50%;transform:translateX(-50%);z-index:4;
  width:{q(540)}}}
.sec-pie{{position:absolute;left:{q(96)};right:{q(96)};bottom:{q(190)};z-index:3;text-align:center}}
.ico-grande{{width:{q(226)};border-radius:50%;margin-bottom:{q(-18)}}}
.sec-pie .barra{{height:{q(8)};background:var(--c);margin:{q(20)} {q(60)} {q(24)};border-radius:{q(4)}}}
.sec-pie h1{{font-family:'Bebas Neue',sans-serif;font-size:{q(72)};color:#fff;letter-spacing:{q(3)}}}

/* ---------- páginas de contenido ---------- */
.banner{{position:absolute;top:0;left:{q(99)};width:{q(882)};height:{q(264)};
  border-radius:0 0 {q(46)} {q(46)};overflow:hidden}}
.banner img{{width:100%;height:100%;object-fit:cover}}
.pill-sec{{position:absolute;top:{q(126)};left:{q(89)};height:{q(114)};z-index:3;
  display:flex;align-items:center}}
.pill-sec img{{width:{q(114)};border-radius:50%;flex:none;position:relative;z-index:2}}
.pill-sec span{{background:var(--c);color:#fff;font-family:'Bebas Neue',sans-serif;
  font-size:{q(44)};letter-spacing:{q(1)};padding:{q(12)} {q(40)} {q(8)} {q(64)};
  margin-left:{q(-46)};border-radius:0 {q(34)} {q(34)} 0;white-space:nowrap}}
.btn-precios{{position:absolute;top:{q(30)};left:{q(102)};z-index:4;display:flex;align-items:center;
  gap:{q(14)};background:#fff;border-radius:{q(40)};padding:{q(10)} {q(28)} {q(10)} {q(10)};
  text-decoration:none;box-shadow:0 {q(3)} {q(10)} #0002}}
.btn-precios .pesito{{width:{q(46)};height:{q(46)};border-radius:50%;background:var(--c,#14562A);
  color:#fff;display:grid;place-items:center;font-weight:700;font-size:{q(28)};flex:none}}
.btn-precios .btxt{{font-family:'Bebas Neue',sans-serif;font-size:{q(24)};line-height:1.05;
  color:#333;letter-spacing:{q(.6)}}}
.btn-precios.ancho{{position:absolute;top:auto;bottom:{q(150)};left:{q(203)};right:{q(208)};
  background:#14562A;justify-content:center;padding:{q(16)}}}
.btn-precios.ancho .btxt{{color:#fff;text-align:center}}
.btn-precios.ancho .btxt em{{display:block;font-style:italic;font-size:{q(17)};font-family:
  'Roboto Condensed',sans-serif;opacity:.9}}
.btn-precios:hover{{filter:brightness(1.06)}}

.tabla{{position:absolute;left:{q(TABLA_X)};top:0;width:{q(TABLA_W)};height:100%}}
.grupo{{position:absolute;left:0;width:100%;height:{q(H_GRUPO)};background:var(--c);
  font-family:'Bebas Neue',sans-serif;letter-spacing:{q(1)};white-space:nowrap;
  display:flex;align-items:center;padding:{q(6)} 0 0 {q(24)};border-radius:{q(3)};
  overflow:hidden}}
.fila{{position:absolute;left:0;width:100%;height:{q(H_FILA)};display:flex;align-items:center;
  padding:0 {q(12)} 0 {q(14)};color:var(--verde);overflow:hidden}}
/* El nombre va en su propio span: en un contenedor flex el text-overflow no aplica
   al texto suelto y las filas largas se cortaban a cuchillo ("...x 21 k"). */
.fila>span{{min-width:0;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}}

/* Un único criterio para todas las fotos de producto: mismo cuadro, imagen
   contenida sin recortar ni deformar, sin marco, píldora con el nombre abajo. */
/* Una foto por familia y, al lado, las presentaciones en píldoras: así lo arma el
   catálogo original (una bolsa de Gran Campeón + "» Adulto x21 kg / » Cachorro
   x10 kg"), en vez de repetir una foto casi igual por cada presentación. */
.fotos{{position:absolute;left:{q(600)};top:{q(TABLA_Y0)};width:{q(384)};
  height:{q(COL_H)};display:flex;flex-direction:column;
  align-items:center;gap:{q(GAP_FOTO)}}}
.fotos figure.logo-marca{{width:{q(250)};margin-bottom:{q(4)}}}
.fotos figure.logo-marca img{{max-height:{q(110)};width:auto;height:auto}}
.fotos figure{{position:relative;z-index:1;width:100%;flex:none;
  display:flex;flex-direction:column;align-items:center;justify-content:flex-end}}
/* MARCO: todas las fotos de una columna ocupan el MISMO cuadro. En el original
   todas tienen la misma huella y llenan la columna; dejando que cada archivo
   mandara su propio ancho quedaban unas de 105 px al lado de otras de 222. */
.fotos .marco{{position:relative;display:block;width:100%;height:var(--alto,{q(300)})}}
.fotos .marco>img{{width:100%;height:100%;object-fit:contain;object-position:center}}
/* Las píldoras van MONTADAS sobre el tercio de abajo de la foto, apoyadas en una
   esquina — no colgando debajo. Salen del flujo: así no le roban alto a la foto. */
.fotos figcaption{{position:absolute;bottom:{q(4)};z-index:5;max-width:96%;
  display:flex;flex-direction:column;gap:{q(6)};font-size:{q(19)};line-height:1}}
.fotos figure.izq figcaption{{left:{q(-14)};align-items:flex-start}}
.fotos figure.der figcaption{{right:{q(-14)};align-items:flex-end}}
.fotos figcaption span{{background:var(--c);color:#fff;padding:{q(7)} {q(16)} {q(6)};
  border-radius:{q(16)};white-space:nowrap;max-width:100%;overflow:hidden;
  text-overflow:ellipsis;box-shadow:0 {q(2)} {q(6)} #0003;font-style:italic;font-weight:700}}
.fotos figcaption span::before{{content:"» ";opacity:.75;font-style:normal}}
/* FOTOS QUE TRAEN SU PROPIO FONDO (mezclas, especias, cereales a granel): el
   original las muestra en CÍRCULO con doble aro —crema grueso y un hilo del color de
   la sección—. Las recortadas (bolsas, frascos) van flotando sin marco. Es el mismo
   criterio del PDF y evita el rectángulo con fondo de estudio pegoteado en la página. */
.fotos figure.redonda .marco{{width:var(--alto);height:var(--alto);margin:0 auto;
  border-radius:50%;overflow:hidden;background:{CREMA_BG};
  box-shadow:0 0 0 {q(9)} {CREMA_BG},0 0 0 {q(11)} var(--c)}}
.fotos figure.redonda .marco>img{{object-fit:cover}}
.fotos figure.marco-foto .marco{{background:{CREMA_MARCO};border-radius:{q(18)};
  overflow:hidden}}
.fotos figure.marco-foto .marco>img{{object-fit:cover}}
.fotos figure.redonda.recorte .marco>img{{object-fit:contain;padding:{q(16)}}}
.fotos figure.redonda.izq .marco{{margin-left:0}}
.fotos figure.redonda.der .marco{{margin-right:0}}

/* FOTO DE FONDO: cuando los productos no llenan la columna, una toma de la sección
   ocupa la columna ENTERA y los productos van encima. Es el recurso del PDF (pág. 26,
   las especias de arriba abajo con los frascos flotando), no una tarjeta más abajo. */
.fotos>img.fondo{{position:absolute;inset:0;width:100%;height:100%;object-fit:cover;
  border-radius:{q(40)};z-index:0}}
.fotos.confondo{{justify-content:space-around;gap:0}}
.fotos.reparte{{justify-content:space-around}}
/* Relleno de pie de columna: la toma de la sección ocupando lo que sobró. */
.relleno{{position:absolute;left:0;overflow:hidden;border-radius:{q(40)}}}
.relleno img{{width:100%;height:100%;object-fit:cover;display:block}}
.fotos .relleno{{position:relative;top:auto;margin-top:auto;flex:none}}
/* Sobre la foto el producto necesita despegarse del fondo. */
.fotos.confondo figure img{{filter:drop-shadow(0 {q(3)} {q(9)} #00000059)
  drop-shadow(0 0 {q(7)} #FFFFFF80)}}
.fotos.confondo figure:nth-of-type(odd){{align-self:flex-start}}
.fotos.confondo figure:nth-of-type(even){{align-self:flex-end}}
/* BADGE DE PROTEÍNA, calcado del original: círculo negro con aro blanco, la palabra
   PROTEÍNAS en píldora naranja montada a caballo del borde de arriba, y el asterisco
   debajo del % cuando el valor es de otra variante de la familia. */
.prot{{position:absolute;top:{q(-10)};right:{q(-12)};z-index:6;width:{q(112)};
  height:{q(112)};border-radius:50%;background:#2B2B2B;color:{CREMA_BG};
  display:flex;align-items:center;justify-content:center;
  box-shadow:0 0 0 {q(6)} {CREMA_BG};
  font-family:'Bebas Neue',sans-serif;font-size:{q(52)};line-height:.82}}
.prot+.prot{{top:{q(130)};right:{q(10)};z-index:7}}
.prot i{{position:absolute;top:{q(-2)};left:50%;transform:translate(-50%,-50%);
  background:#F5A63C;color:#3A2C1C;border-radius:{q(20)};padding:{q(5)} {q(11)} {q(4)};
  font-family:'Roboto Condensed',sans-serif;font-style:normal;font-weight:700;
  font-size:{q(15)};letter-spacing:{q(.4)};white-space:nowrap}}
.prot u{{text-decoration:none;white-space:nowrap;display:block;margin-top:{q(10)}}}
.prot b{{font-size:{q(26)};font-weight:400;vertical-align:super}}
.prot s{{text-decoration:none;font-size:{q(26)};vertical-align:sub;margin-left:{q(-14)}}}

/* Hoja de explicación (PDF pág. 6-7): nombre del producto en verde y el texto en
   gris sobre un panel apenas más oscuro que la página, como el original. */
.desc-col{{position:absolute;left:{q(TABLA_X)};top:{q(TABLA_Y0)};width:{q(TABLA_W)};
  max-height:{q(COL_H)};overflow:hidden;
  font-family:'Roboto Condensed',sans-serif;line-height:1.3}}
.desc-col .grupo.desc{{position:static;height:{q(H_GRUPO - 8)};display:flex;
  align-items:center;padding:0 {q(18)};background:var(--c);border-radius:{q(6)};
  font-family:'Bebas Neue',sans-serif;font-size:{q(46)};letter-spacing:{q(.5)}}}
.desc-col h3{{margin:{q(20)} 0 {q(8)} {q(18)};color:var(--verde);font-weight:400;
  font-size:{q(30)};line-height:1.15}}
.desc-txt{{margin-left:{q(36)};background:{FILA_B};border-radius:{q(10)};
  padding:{q(16)} {q(22)};color:var(--gris);font-weight:300}}
.desc-txt p{{margin:0}}
.desc-txt ul{{margin:{q(10)} 0 0 {q(26)};padding:0}}
.desc-txt li{{margin-bottom:{q(6)}}}
.foot{{position:absolute;left:{q(96)};right:{q(96)};bottom:{q(96)};height:{q(64)};
  display:flex;align-items:center;justify-content:space-between;z-index:5}}
.logo-foot{{width:{q(230)}}}
.nropag{{width:{q(60)};height:{q(60)};border-radius:50%;background:#222;color:#fff;
  display:grid;place-items:center;font-size:{q(28)};font-weight:700}}
.disclaimer{{font-size:{q(19)};color:var(--gris);text-align:right;line-height:1.3}}
.sec-portada .foot,.indice .foot{{justify-content:center}}
.barra-pie{{position:absolute;left:{q(98)};right:{q(102)};bottom:{q(-12)};height:{q(68)};
  background:var(--c);border-radius:{q(8)} {q(8)} 0 0}}

@media (max-width:700px){{body{{padding:0;gap:{q(10)}}}}}
"""


def proteina_de(sec, marca, desc, prot):
    """% de proteína del producto. Lo específico gana sobre lo genérico.

    Dentro de una marca el valor cambia por variante (Balanced raza grande 25%,
    raza pequeña 27%), así que primero se buscan las reglas por producto.
    """
    d = limpiar(desc).upper()
    for r in prot.get("por_producto", []):
        if r["sec"] != sec:
            continue
        if not all(t in d for t in r["contiene"]):
            continue
        if any(t in d for t in r.get("excluye", [])):
            continue          # el dato es del adulto, no del cachorro / raza chica
        return r["prot"]
    return prot.get("por_marca", {}).get(sec, {}).get(marca)


# Logo de la marca arriba de la columna de fotos: lo hacía el catálogo original
# (Mani King, NutriFoods) y ayuda a que la página se lea como "esta es la marca".
LOGOS_MARCA = {"MANI KING": "marcas/mani-king.webp"}
# Fotos que SON de la marca (recortadas de su página del catálogo) van primero.
MARCA_SLUG = {"MANI KING": "mani-king"}


# Marcas propias primero: son las que conviene mostrar. Ken-L queda listado en la
# tabla pero nunca destacado en foto (está descontinuado y se repone sin publicidad).
PRIORIDAD = ("PRODUCCION PROPIA SEMILLERO", "POLAR", "NUTRIMAX")
# Productos que queremos mostrar sí o sí cuando compiten por lugar en la página.
# Las mezclas se arman acá adentro: son lo nuestro y es lo que conviene mostrar.
DESTACADOS = {"FORRAJES": ("MEZCLA", "CABALLO PREMIUM")}
# Qué producto representa a una familia cuando la elección automática no es la mejor.
# En producción propia salía la foto del caballo (una toma de un caballo, no del
# alimento); la bolsa de Nutrimax muestra lo que en realidad vendemos.
# Qué producto representa a una familia cuando la elección automática no es la mejor.
# En producción propia salía la foto de un caballo —una toma de un caballo, no del
# alimento—; la bolsa de Nutrimax muestra lo que en realidad vendemos.
REPRESENTANTE = {("ALIMENTO BALANCEADO ANIMAL", "PRODUCCION PROPIA SEMILLERO"): "PREINICIADOR"}
FOTO_FAMILIA = {}
SIN_DESTACAR = ("KEN-L RATION",)


# Cuántas veces se usó cada foto para tapar un hueco. Sirve para no repetir
# siempre la misma cuando varias páginas seguidas se quedan sin fotos propias.
YA_RELLENO = {}


def fotos_de(bloques, sec, mapa, prot, reserva=None):
    """Arma la columna de fotos: UNA por familia, con sus variedades al lado.

    Igual que el catálogo original: una bolsa por marca y, pegadas a la foto, las
    presentaciones de esa misma familia. Las familias salen EN EL MISMO ORDEN que la
    tabla de la izquierda (en el PDF la foto está a la altura de su bloque) y ningún
    producto puede aparecer dos veces, ni como píldora y como foto aparte.
    """
    porgrupo, ya_nombrados = [], set()
    for b in bloques:
        marca = b["grupo"].replace(" (cont.)", "")
        if marca in SIN_DESTACAR:
            continue
        candidatos = []
        for it in b["items"]:
            hit = mapa.get(f"{sec}|{it['cod']}|{it['desc']}")
            if hit:
                candidatos.append({"img": hit["local"],
                                   "nom": abreviar_prod(sin_marca(it["desc"], marca), 26),
                                   "desc": limpiar(it["desc"]).upper(),
                                   "prot": proteina_de(sec, marca, it["desc"], prot),
                                   "score": hit.get("score", 0)})
        if not candidatos:
            continue
        # Representa a la familia el que tenga % de proteína (así el badge no se
        # desperdicia) y, entre esos, el de match más confiable.
        elegido = REPRESENTANTE.get((sec, marca))
        candidatos.sort(key=lambda c: (0 if elegido and elegido in c["desc"] else 1,
                                       0 if c.get("prot") else 1, -c["score"]))
        jefe = dict(candidatos[0])
        propia = FOTO_FAMILIA.get((sec, marca))
        if propia:
            jefe["img"] = propia
        # Las píldoras son las VARIEDADES DE LA FAMILIA tal como están en la tabla,
        # tengan foto o no: el original lista las presentaciones, no las fotos.
        # Hasta dos valores de proteína por familia (adulto y cachorro), como el PDF.
        # El segundo lleva asterisco Y se le pone el mismo asterisco a las variedades
        # que le corresponden: sin ese vínculo son dos números sueltos que no se
        # entienden (es lo que pasaba).
        principal = jefe.get("prot")
        otros = []
        for it in b["items"]:
            v = proteina_de(sec, marca, it["desc"], prot)
            if v and v != principal and v not in otros:
                otros.append(v)
        segundo = otros[0] if len(otros) == 1 else None
        jefe["prots"] = [x for x in (principal, segundo) if x]
        pildoras = []
        for it in b["items"][:MAX_PILDORAS]:
            nom = abreviar_prod(sin_marca(it["desc"], marca), 26)
            if segundo and proteina_de(sec, marca, it["desc"], prot) == segundo:
                nom += " *"
            pildoras.append(nom)
        jefe["variantes"] = pildoras
        porgrupo.append((marca, jefe))
        ya_nombrados.update(f"{sec}|{it['cod']}|{it['desc']}" for it in b["items"])

    elegidas = [c for _, c in porgrupo]

    # Si la página tiene una sola familia (secciones tipo VARIEDADES o MEZCLAS), se
    # muestran varios productos distintos de esa familia en vez de repetir el mismo.
    # OJO: tiene que ser el único BLOQUE de la página. Con `len(porgrupo)==1` alcanzaba
    # con que una sola familia tuviera fotos y Rosco se desarmaba en 5 fotos sueltas.
    if porgrupo and (sec in POR_PRODUCTO or (len(porgrupo) == 1 and len(bloques) == 1)):
        marca = porgrupo[0][0]
        todos, vistos = [], set()
        for b in bloques:
            for it in b["items"]:
                hit = mapa.get(f"{sec}|{it['cod']}|{it['desc']}")
                if hit and hit["local"] not in vistos:
                    vistos.add(hit["local"])
                    todos.append({"img": hit["local"],
                                  "nom": abreviar_prod(sin_marca(it["desc"], marca), 26),
                                  "variantes": [abreviar_prod(sin_marca(it["desc"], marca), 26)],
                                  "prot": proteina_de(sec, marca, it["desc"], prot),
                                  "desc": it["desc"].upper(),
                                  "propia": hit.get("slug", "") in MARCA_SLUG.get(marca, "")})
        # las mezclas van primero: son producción nuestra y es lo que queremos mostrar
        destacar = DESTACADOS.get(sec, ())
        todos.sort(key=lambda c: (0 if any(d in c["desc"] for d in destacar) else 1,
                                  0 if c.get("propia") else 1))
        elegidas = todos

    # Cuando la página no llena la columna se completa con fotos de otros productos
    # de la misma sección. Nunca con uno que YA esté nombrado en esta página (era el
    # bug de "Pajaro 4 mm" apareciendo como píldora de GANAVE y otra vez como foto).
    # Con 3 familias propias la página ya se sostiene sola: prestar fotos de otras
    # páginas sólo achicaría a las de acá.
    tope_relleno = 0 if len(elegidas) >= 3 else TOPE_ABSOLUTO
    if reserva and len(elegidas) < tope_relleno:
        # Orden del relleno: primero el mismo subgrupo que la página, y dentro de eso
        # las que todavía no se mostraron en ninguna página. Así el cliente va viendo
        # productos distintos y no la misma foto repetida página tras página.
        aca = {b["grupo"].replace(" (cont.)", "") for b in bloques}
        reserva = sorted(reserva, key=lambda c: (
            0 if c.get("grupo", "").replace(" (cont.)", "") in aca else 1,
            YA_RELLENO.get(c["img"], 0)))
        usadas = {c["img"] for c in elegidas}
        for c in reserva:
            if len(elegidas) >= tope_relleno:
                break
            if c["img"] in usadas or (c.get("claves") or {c.get("clave")}) & ya_nombrados:
                continue
            elegidas.append(dict(c, prestada=True))
            usadas.add(c["img"])
            YA_RELLENO[c["img"]] = YA_RELLENO.get(c["img"], 0) + 1
    return elegidas


def main():
    usar_cache = "--cache" in sys.argv
    datos = separar_mani_king(separar_granolas(separar_mezclas(parsear(bajar_csv(usar_cache)))))
    manifest = json.load(open(os.path.join(BASE, "assets", "manifest.json"), encoding="utf-8"))
    def _carga(n, d):
        p = os.path.join(BASE, n)
        return json.load(open(p, encoding="utf-8")) if os.path.exists(p) else d
    mapa_fotos = _carga("mapa_fotos.json", {})
    proteinas = {k: v for k, v in _carga("proteinas.json", {}).items() if not k.startswith("_")}
    # Hojas de explicación (las páginas 6-7 del PDF): van después de las tablas de
    # esa sección, sin tabla, contándole al cliente de qué se trata el producto.
    descripciones = {k: v for k, v in _carga("descripciones.json", {}).items()
                     if not k.startswith("_")}

    # primera pasada: paginar todo para saber los números del índice
    plan, nro, indice = [], 3, {}
    for nombre, slug, color, pill, titulo, _c in SECCIONES:
        grupos = datos.get(nombre)
        if not grupos:
            continue
        indice[nombre] = nro
        paginas = paginar(grupos)
        hojas = descripciones.get(nombre, {}).get("paginas", [])
        plan.append((nombre, slug, color, pill, titulo, nro, paginas, hojas))
        nro += 1 + len(paginas) + len(hojas)

    hoy = date.today().strftime("%d/%m/%Y")
    html = [pag_portada(), pag_indice(indice, hoy)]
    for nombre, slug, color, pill, titulo, n0, paginas, hojas in plan:
        ext = manifest[slug]["hero"].split(".")[-1]
        ban_ext = (manifest[slug]["banner"] or "x.jpeg").split(".")[-1]
        html.append(pag_seccion(slug, color, titulo, n0, ext))
        # La reserva también va POR FAMILIA, no producto por producto: si no, una
        # página prestada terminaba con tres fotos de Dog Selection una debajo de otra.
        reserva = []
        for g, items in datos[nombre].items():
            marca = g.replace(" (cont.)", "")
            con_foto = [(it, mapa_fotos[f"{nombre}|{it['cod']}|{it['desc']}"])
                        for it in items
                        if f"{nombre}|{it['cod']}|{it['desc']}" in mapa_fotos]
            if not con_foto:
                continue
            con_foto.sort(key=lambda par: (0 if proteina_de(nombre, marca, par[0]["desc"],
                                                            proteinas) else 1,
                                           -par[1].get("score", 0)))
            if nombre in POR_PRODUCTO:
                for x, hx in con_foto:
                    n = abreviar_prod(sin_marca(x["desc"], marca), 26)
                    reserva.append({"img": hx["local"], "nom": n, "variantes": [n],
                                    "clave": f"{nombre}|{x['cod']}|{x['desc']}",
                                    "claves": {f"{nombre}|{x['cod']}|{x['desc']}"},
                                    "prot": proteina_de(nombre, marca, x["desc"], proteinas),
                                    "grupo": g})
                continue
            it, hit = con_foto[0]
            reserva.append({
                "img": hit["local"],
                "nom": abreviar_prod(sin_marca(it["desc"], marca), 26),
                "variantes": [abreviar_prod(sin_marca(x["desc"], marca), 26)
                              for x, _ in con_foto][:MAX_PILDORAS],
                "clave": f"{nombre}|{it['cod']}|{it['desc']}",
                "claves": {f"{nombre}|{x['cod']}|{x['desc']}" for x, _ in con_foto},
                "prot": proteina_de(nombre, marca, it["desc"], proteinas),
                "grupo": g})
        for i, bloques in enumerate(paginas):
            fp = fotos_de(bloques, nombre, mapa_fotos, proteinas, reserva)
            html.append(pag_contenido(slug, color, pill, bloques, fp, n0 + 1 + i, ban_ext))
        familia = descripciones.get(nombre, {}).get("familia", "")
        for j, prods in enumerate(hojas):
            # la foto de cada producto descripto, si la hay (la clave del mapa lleva
            # la descripción tal cual está en la planilla, así que se busca por nombre)
            fp = []
            for pr in prods:
                base = limpiar(pr["nombre"]).upper().split(" X ")[0].strip()
                for k, hit in mapa_fotos.items():
                    ks = k.split("|")
                    if ks[0] == nombre and limpiar(ks[2]).upper().startswith(base):
                        if hit["local"] not in fp:
                            fp.append(hit["local"])
                        break
            html.append(pag_descripcion(slug, color, pill, familia, prods,
                                        n0 + 1 + len(paginas) + j, ban_ext, fp))

    total_prod = sum(len(v) for g in datos.values() for v in g.values())
    doc = f"""<!doctype html>
<html lang="es">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Catálogo · Semillero El Manantial S.R.L.</title>
<meta name="description" content="Catálogo mayorista de Semillero El Manantial: balanceados, alimento para perros y gatos, cereales, forrajes, legumbres, condimentos, venenos y accesorios.">
<link rel="stylesheet" href="assets/fonts/fuentes.css">
<style>{css()}</style>
</head>
<body>
{''.join(html)}
</body>
</html>
"""
    # Reporte de lo que hay que corregir en la planilla (el catálogo lo tapa,
    # pero la app de precios y Amira lo muestran tal cual está cargado).
    sucios = []
    for sec, grupos in datos.items():
        for g, items in grupos.items():
            for it in items:
                malos = [m for m in BASURA if m in it["desc"]]
                if malos:
                    sucios.append(f"{sec:28s} cod {it['cod']:>5s}  {it['desc']}"
                                  f"   ->   {limpiar(it['desc'])}")
    rep = os.path.join(BASE, "reporte_sheet.txt")
    open(rep, "w", encoding="utf-8").write(
        f"Productos con caracteres mal cargados en el Sheet mayorista: {len(sucios)}\n"
        f"(el catálogo los corrige al vuelo; la planilla sigue sucia)\n\n" + "\n".join(sucios))

    out = os.path.join(BASE, "index.html")
    open(out, "w", encoding="utf-8").write(doc)
    print(f"OK  {out}")
    if sucios:
        print(f"    OJO: {len(sucios)} productos con caracteres rotos en el Sheet -> reporte_sheet.txt")
    print(f"    {len(html)} páginas · {total_prod} productos · {len(plan)} secciones · datos al {hoy}")
    for nombre, slug, _, _, _, n0, paginas, hojas in plan:
        n = sum(len(b["items"]) for p in paginas for b in p)
        print(f"    p{n0:<3d} {nombre:28s} {n:4d} prod -> {len(paginas)} pág")


if __name__ == "__main__":
    main()
