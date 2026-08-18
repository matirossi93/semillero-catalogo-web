#!/usr/bin/env python3
"""
Saca del PDF original las fotos de AMBIENTE (las que la diseñadora usaba para
rellenar la columna cuando una página no tenía suficientes fotos de producto).

Son tomas de estilo de vida —una gallina, un perro, especias, maní— que ocupan
toda la altura de la columna con las esquinas redondeadas. No son producto: son
el recurso que evita que la página quede coja. El catálogo web no las tenía y
por eso las páginas flacas (accesorios, balanceados) se veían pobres.

Para las secciones que en el PDF no tienen una propia, se recorta la foto de
portada de esa sección al mismo formato vertical.

    python extraer_ambiente.py
"""
import os
from PIL import Image
import fitz

BASE = os.path.dirname(os.path.abspath(__file__))
PDF = r"G:\Unidades compartidas\Herramientas de Ventas\Catalogo Semillero.pdf"
SALIDA = os.path.join(BASE, "assets", "ambiente")

# (página del PDF, xref de la imagen, slug de sección). Relevado midiendo qué
# imágenes ocupan la columna entera y mirándolas una por una.
DEL_PDF = [
    (6,  43,  "balanceados"),
    (7,  53,  "balanceados"),
    (12, 96,  "perros"),
    (19, 172, "cereales"),
    (26, 227, "condimentos"),
    (28, 241, "frutos"),
    (30, 254, "snacks"),
]
# Las que faltan salen de la portada de la sección, recortada al mismo formato.
DE_PORTADA = ["gatos", "desayuno", "forrajes", "legumbres", "venenos", "accesorios"]

# La columna del PDF mide 384 x 1348 -> el fondo va en ESE formato, no en retrato
# normal. Las que salen del PDF YA vienen así (son justo esa región): no se las
# vuelve a recortar. Recortarlas a retrato fue el error: dejaba primerísimos planos
# irreconocibles, una maceta se veía como una mancha.
ASPECTO = 384 / 1348
ANCHO = 620


def al_formato(im, ya_esta=False):
    """Deja la foto en el formato alto de la columna, recortando desde el centro."""
    if ya_esta:
        return im.resize((ANCHO, int(ANCHO * im.height / im.width)), Image.LANCZOS)
    objetivo = ASPECTO
    if im.width / im.height > objetivo:
        w = int(im.height * objetivo)
        im = im.crop(((im.width - w) // 2, 0, (im.width - w) // 2 + w, im.height))
    else:
        h = int(im.width / objetivo)
        y = max(0, (im.height - h) // 3)      # un poco arriba del centro: cae mejor
        im = im.crop((0, y, im.width, min(im.height, y + h)))
    return im.resize((ANCHO, int(ANCHO / objetivo)), Image.LANCZOS)


def main():
    os.makedirs(SALIDA, exist_ok=True)
    doc = fitz.open(PDF)
    hechas = {}
    for pag, xref, slug in DEL_PDF:
        p = doc[pag - 1]
        rects = p.get_image_rects(xref)
        if not rects:
            print(f"  ojo: p{pag} xref {xref} sin rect")
            continue
        # Se renderiza la REGIÓN (no se extrae el archivo interno) porque en el PDF
        # varias vienen rotadas y recortadas por el marco: así sale como se ve.
        pix = p.get_pixmap(clip=rects[0], dpi=150)
        im = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
        n = hechas.get(slug, 0) + 1
        hechas[slug] = n
        dest = os.path.join(SALIDA, f"{slug}-{n}.webp")
        al_formato(im, ya_esta=True).save(dest, "WEBP", quality=82, method=6)
        print(f"  {os.path.basename(dest):24s} <- p{pag}")

    for slug in DE_PORTADA:
        origen = os.path.join(BASE, "assets", "hero", f"{slug}.webp")
        if not os.path.exists(origen):
            print(f"  falta portada de {slug}")
            continue
        dest = os.path.join(SALIDA, f"{slug}-1.webp")
        al_formato(Image.open(origen).convert("RGB")).save(dest, "WEBP", quality=82, method=6)
        print(f"  {os.path.basename(dest):24s} <- portada")

    total = len(os.listdir(SALIDA))
    print(f"OK  {total} fotos de ambiente en assets/ambiente/")


if __name__ == "__main__":
    main()
