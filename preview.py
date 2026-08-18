#!/usr/bin/env python3
"""Arma _preview.html con solo las páginas pedidas, para revisar el diseño.

    python preview.py 1 2 3 4      # páginas 1 a 4 del index.html generado
"""
import re, sys, os

BASE = os.path.dirname(os.path.abspath(__file__))
html = open(os.path.join(BASE, "index.html"), encoding="utf-8").read()
head = html.split("<body>")[0]
pags = re.findall(r'<section class="pag.*?</section>', html, re.S)
nums = [int(x) for x in sys.argv[1:]] or [1]
sel = [pags[n - 1] for n in nums if 0 < n <= len(pags)]
open(os.path.join(BASE, "_preview.html"), "w", encoding="utf-8").write(
    head + "<body>" + "\n".join(sel) + "</body></html>")
print(f"_preview.html  paginas {nums}  (de {len(pags)})")
