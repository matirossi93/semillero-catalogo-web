"""Verifica el catálogo generado en un navegador (Playwright), a 390 px.

Uso: python tests/verificar_catalogo.py [ruta/al/index.html]   (por defecto ./index.html)
Sale con código 1 si algo falla. Cubre lo que se arregló en SEM-400:
el buscador, los nombres cortados y las fotos con rótulos de otros productos.
"""
import asyncio, os, re, sys, html as H
from playwright.async_api import async_playwright

RUTA = os.path.abspath(sys.argv[1] if len(sys.argv) > 1 else "index.html")

# búsqueda -> (mínimo de resultados, texto que NO debe aparecer en los resultados)
BUSQUEDAS = {
    "alimento gato": (20, None), "comida perro": (40, None), "balanceado": (100, None),
    "gallina": (3, None), "veneno rata": (5, None), "maiz pisado": (2, None),
    "perro adulto": (10, None), "pollo": (3, "hamster"), "gandum 15kg": (1, None),
    "constructor": (0, None), "xyzzy": (0, None),
}

fallas = []

def ok(cond, msg):
    if not cond:
        fallas.append(msg)

def fotos_ajenas(texto):
    """Fotos de Venenos y Accesorios cuyo primer rótulo no es el producto de la foto.

    Ahí cada foto es UN producto (colores de sección #0C5013 y #8000FF). Antes la caja
    de Glacoxan decía también «Bandeja sanitaria» y «Blister fino p/ gato x 12».
    Una foto puede llevar más rótulos sólo si esos productos tienen la MISMA imagen.
    """
    t = lambda x: H.unescape(re.sub("<[^>]+>", "", x)).strip().lower()
    malas = 0
    for s in re.findall(r'<section class="pag contenido" style="--c:#(?:0C5013|8000FF)">(.*?)</section>',
                        texto, re.S):
        for alt, cap in re.findall(r'<img src="[^"]+" alt="([^"]*)"[^>]*></span>.*?<figcaption>(.*?)</figcaption>',
                                   s, re.S):
            pills = [t(p).replace("*", "").strip() for p in re.findall(r"<span>(.*?)</span>", cap)]
            if pills and not t(alt).endswith(pills[0]):
                malas += 1
                print("   foto", repr(alt), "rotulada", pills)
    return malas

async def main():
    texto = open(RUTA, encoding="utf-8").read()
    async with async_playwright() as pw:
        b = await pw.chromium.launch()
        pg = await (await b.new_context(viewport={"width": 390, "height": 844})).new_page()
        errores = []
        pg.on("pageerror", lambda e: errores.append(str(e)))
        await pg.goto("file://" + RUTA)
        await pg.wait_for_timeout(1200)
        # A 390 px se ven las hojas de la revista, como en la compu (SEM-734, Mati 27/11:
        # «aprieto el botón de revista, no hace nada… no se ve el catálogo»).
        hojas = """() => {
            const v = [...document.querySelectorAll('main.revista>.pag')]
              .filter(e => getComputedStyle(e).display != 'none' && e.getBoundingClientRect().height > 100);
            return { visibles: v.length, total: document.querySelectorAll('main.revista>.pag').length,
              ancho: document.documentElement.scrollWidth };
        }"""
        cel = await pg.evaluate(hojas)
        ok(cel["total"] > 40 and cel["visibles"] == cel["total"],
           f"celu al abrir: {cel['visibles']} de {cel['total']} hojas visibles")
        ok(cel["ancho"] <= 390, f"la página se desborda a 390 px ({cel['ancho']})")
        # El botón REVISTA, después de BUSCAR, vuelve a mostrar las hojas
        await pg.click("button.tab[data-vista=buscar]")
        await pg.wait_for_timeout(300)
        await pg.click("button.tab[data-vista=revista]")
        await pg.wait_for_timeout(300)
        cel = await pg.evaluate(hojas)
        ok(cel["visibles"] == cel["total"], f"celu tras tocar REVISTA: {cel['visibles']} de {cel['total']} hojas visibles")
        # Saltar a una sección desde la barra lleva a su hoja
        await pg.click(".secnav a[href='#perros']")
        await pg.wait_for_timeout(1200)
        y = await pg.evaluate("() => document.getElementById('perros').getBoundingClientRect().top")
        ok(-50 < y < 400, f"celu: el salto a Perros dejó la hoja en y={y:.0f}")
        for ancho in (320, 360):
            ctx = await b.new_context(viewport={"width": ancho, "height": 780})
            pa = await ctx.new_page()
            await pa.goto("file://" + RUTA)
            await pa.wait_for_timeout(600)
            sw = await pa.evaluate("document.documentElement.scrollWidth")
            ok(sw <= ancho, f"la página se desborda a {ancho} px ({sw})")
            await ctx.close()
        pc = await (await b.new_context(viewport={"width": 1080, "height": 1920})).new_page()
        await pc.goto("file://" + RUTA)
        await pc.wait_for_timeout(1200)
        cortados = await pc.evaluate("""() => [...document.querySelectorAll('.fila span')]
            .filter(x => x.scrollWidth > x.clientWidth + 1).map(x => x.textContent)""")
        ok(not cortados, f"nombres cortados en la revista a 1080 px: {cortados[:5]}")
        await pg.click("button.tab[data-vista=buscar]")
        for q, (minimo, prohibido) in BUSQUEDAS.items():
            await pg.fill("#q", q)
            await pg.wait_for_timeout(250)
            n = int((await pg.text_content("#conteo")).split()[0])
            if minimo:
                ok(n >= minimo, f"«{q}»: {n} resultados, se esperaban ≥ {minimo}")
            if prohibido:
                txt = (await pg.evaluate("() => document.querySelector('#res').innerText")).lower()
                ok(prohibido not in txt, f"«{q}» trae «{prohibido}»")
        ok(not errores, f"errores de JS: {errores[:3]}")
        await b.close()
    ok(fotos_ajenas(texto) == 0, f"{fotos_ajenas(texto)} fotos con rótulo de otro producto (Venenos y Accesorios)")

asyncio.run(main())
for f in fallas:
    print("FALLA:", f)
print("OK" if not fallas else f"{len(fallas)} fallas")
sys.exit(1 if fallas else 0)
