# Vuelta atrás

`index-20260818-pre-buscador.html` es **exactamente** el catálogo que estaba en
producción antes de agregarle el marco web (barra fija, buscador, WhatsApp, pie).
Se bajó de `https://semilleroelmanantial.com.ar/catalogo/` el 20/08/2026 y se
verificó byte a byte contra `web-semillero-fresh/public/catalogo/index.html`.

Son 49 páginas con datos al 18/08/2026. Los `assets/` no cambiaron: el marco web
no agregó ni una imagen (los íconos de WhatsApp y de "volver arriba" son SVG
escritos adentro del HTML).

## Volver atrás en 1 minuto

Producción es Vercel, no el VPS (ver más abajo). El catálogo son archivos estáticos
dentro de `web-semillero-fresh/public/catalogo/`, así que revertir es copiar y pushear:

    cp _backup/index-20260818-pre-buscador.html \
       ../web-semillero-fresh/public/catalogo/index.html
    cd ../web-semillero-fresh && git commit -am "revert: catálogo previo al buscador" && git push

Vercel redeploya solo.

## Volver atrás en el generador

El `build.py` de antes está en el tag `pre-buscador`:

    git checkout pre-buscador -- build.py
    python build.py

Las 49 hojas de la revista quedaron **idénticas byte a byte** después del cambio
(se comparó el HTML generado por los dos `build.py` con los mismos datos), así que
volver atrás sólo saca el marco: no toca ni una hoja.

## Ojo: producción se mudó

El `deploy.sh` de este repo todavía apunta al VPS de la empresa, que está caído
desde el 18/08/2026 — y con él se cayó el cron de las 6:30 que regeneraba el
catálogo. Hoy la web está congelada en los datos del 18/08. Mientras no vuelva el
VPS, publicar es copiar `index.html` + `assets/` a `web-semillero-fresh/public/catalogo/`
y pushear.
