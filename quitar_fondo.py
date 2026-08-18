#!/usr/bin/env python3
"""
Deja las fotos de producto sobre fondo transparente.

Las imágenes de la web vienen en JPEG con fondo blanco: puestas sobre el crema del
catálogo se ve el recuadro. Acá se saca solo el fondo *conectado a los bordes*, con
flood fill desde el marco, para no agujerear las partes blancas del envase (una
bolsa blanca tiene que seguir siendo blanca).

    python quitar_fondo.py            # procesa assets/productos/ en el lugar
"""
import os, sys
from PIL import Image, ImageDraw

BASE = os.path.dirname(os.path.abspath(__file__))
DIR = os.path.join(BASE, "assets", "productos")
MAGICO = (255, 0, 255)      # color testigo que después se vuelve transparente
TOLERANCIA = 38             # cuánto se aleja del blanco y sigue siendo fondo


def limpiar_una(ruta):
    im = Image.open(ruta).convert("RGBA")
    w, h = im.size
    fondo_ya_transparente = im.getchannel("A").getextrema()[0] < 250
    if fondo_ya_transparente:
        return False                       # ya venía recortada (PNG con alpha)

    rgb = im.convert("RGB")
    # el fondo tiene que ser claro; si las esquinas son oscuras, no toco nada
    esquinas = [rgb.getpixel(p) for p in ((0, 0), (w - 1, 0), (0, h - 1), (w - 1, h - 1))]
    if sum(min(c) for c in esquinas) / 4 < 225:
        return False

    semillas = []
    for x in range(0, w, max(1, w // 24)):
        semillas += [(x, 0), (x, h - 1)]
    for y in range(0, h, max(1, h // 24)):
        semillas += [(0, y), (w - 1, y)]
    for s in semillas:
        if min(rgb.getpixel(s)) >= 255 - TOLERANCIA:
            ImageDraw.floodfill(rgb, s, MAGICO, thresh=TOLERANCIA)

    datos = []
    for r, g, b in rgb.getdata():
        datos.append((255, 255, 255, 0) if (r, g, b) == MAGICO else (r, g, b, 255))
    out = Image.new("RGBA", (w, h))
    out.putdata(datos)

    caja = out.getbbox()                   # recorta el aire sobrante
    if caja:
        out = out.crop(caja)
    out.save(ruta, "WEBP", quality=88, method=6)
    return True


def main():
    archivos = sorted(f for f in os.listdir(DIR) if f.endswith(".webp"))
    tocadas = 0
    for f in archivos:
        try:
            if limpiar_una(os.path.join(DIR, f)):
                tocadas += 1
        except Exception as e:
            print(f"  fallo {f}: {e}")
    peso = sum(os.path.getsize(os.path.join(DIR, f)) for f in archivos) / 1e6
    print(f"{tocadas}/{len(archivos)} fotos recortadas · {peso:.1f} MB")


if __name__ == "__main__":
    main()
