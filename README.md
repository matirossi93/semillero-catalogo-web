# Catálogo Semillero — versión web autoactualizable

Réplica del catálogo PDF (`G:\Unidades compartidas\Herramientas de Ventas\Catalogo Semillero.pdf`,
InDesign, 46 páginas de 1080×1920) generada por código desde la **lista de precios
mayorista viva**, en vez de mantenerse a mano.

```bash
python build.py           # baja el Sheet y regenera index.html
python build.py --cache   # usa el CSV local, sin red
python preview.py 4 9 39  # arma _preview.html con esas páginas sueltas
```

## Por qué se puede replicar

El PDF **es** un espejo manual de la lista de precios mayorista: mismas 12 secciones,
mismo orden, misma agrupación por marca. La diseñadora maquetaba lo que había en la
planilla. Por eso el generador puede armar las páginas solo: pagina con las mismas
reglas (barra de marca 70 px, fila 49 px, área útil 302→1650) y le sale la misma
cantidad de páginas que el original.

## De dónde sale cada cosa

| Pieza | Origen |
|---|---|
| Productos, secciones, marcas | Google Sheet mayorista (mismo CSV que usa `precios.semilleroelmanantial.com.ar`) |
| Fotos de producto, banners, fotos de sección | extraídas del PDF original con su máscara de transparencia |
| Íconos de sección, logo | recortados del PDF (eran vectores, no imágenes) |
| Colores, tipografías, medidas | medidos sobre el PDF, no estimados a ojo |

Paleta por sección, tal cual el original: `#DB2525` animales · `#FFA500` perros ·
`#E0E055` gatos · `#82FF82` desayuno · `#2FD482` cereales · `#00BEE0` forrajes ·
`#2B2BD6` legumbres · `#FF69B4` condimentos · `#FF00FF` frutos secos · `#A17C0D`
snacks · `#0C5013` venenos · `#8000FF` accesorios.

Tipografías: Bebas Neue (títulos) y Roboto Condensed (texto) — las dos gratis en
Google Fonts, son las mismas del PDF.

## Diferencias a favor respecto del PDF

- **El botón "VER LOS PRECIOS" ahora funciona.** En el PDF está dibujado en las 46
  páginas pero no es un hipervínculo: el archivo no tiene ni un link ni una anotación.
  Acá apunta a `precios.semilleroelmanantial.com.ar`.
- **623 productos** contra 517 del PDF, en 52 páginas contra 46.
- El índice numera las páginas solo; si crece una sección, se renumera todo.
- Escala a cualquier pantalla sin perder el diseño (medidas en `cqw` sobre el
  contenedor de 1080 px, no píxeles fijos).

## Publicado

**https://semilleroelmanantial.com.ar/catalogo** — estático, servido por nginx desde
`/var/www/semillero-catalogo/catalogo` en el VPS de la empresa (165.1.123.161).

Se regenera solo: `/opt/catalogo/actualizar.sh` corre por cron **todos los días a las
6:30** (hora de Tucumán), baja el Sheet, rearma las 52 páginas y publica. Si el Sheet
no responde, deja el catálogo anterior en vez de publicar uno vacío.
Log en `/opt/catalogo/logs/actualizar.log`.

Para publicar a mano desde acá: `./deploy.sh`.

## Integrado con

- **Amira**: el SOUL tiene la regla del catálogo (bloque de links, línea ~277). Cuando
  el cliente pide "el catálogo" o "qué productos manejan", manda
  `semilleroelmanantial.com.ar/catalogo`. Al no tener precios, es seguro para cualquier
  tipo de cliente — no hay riesgo de cruzar listas mayorista/minorista.
  Backup del SOUL: `SOUL.md.bak-catalogoweb-*`.
- **La web**: CTA "Ver catálogo" en el hero de la home + link en el menú mobile, con
  `data-cta` para que quede medido. Va como `<a>` y no `<Link>`: la ruta la sirve nginx,
  no el router de Next, así que un Link daría 404 del lado del cliente.
- **App de precios**: el botón "Ver Catálogo" apunta acá (antes abría un PDF de Drive de
  2024). Queda un circuito cerrado: el catálogo se regenera de la lista de precios y la
  lista de precios linkea al catálogo.

## Cómo replica el diseño

Todo lo del layout está **medido** sobre el PDF con PyMuPDF (`get_image_rects`,
`get_text("dict")`), no estimado. Las reglas que salieron de ahí:

- **Una foto por familia**, con las variedades en píldoras montadas sobre la foto. Las
  píldoras salen de la tabla (tengan foto o no) y van fuera del flujo: si sumaran alto,
  obligarían a achicar las fotos.
- **Dos tratamientos según la sección**: envase (balanceados, perros, gatos, venenos,
  accesorios) = recorte suelto · granel (cereales, forrajes, legumbres, condimentos,
  frutos) = círculo con doble aro, crema grueso + hilo del color de la sección.
- **% de proteína**: círculo negro con "PROTEÍNAS" en píldora naranja montada sobre el
  borde de arriba, y hasta dos valores por familia. El asterisco **ata** el badge con su
  variedad (`24%*` ↔ `» Perro adulto x 20 kg *`); sin ese vínculo son dos números sueltos.
- **Foto de fondo**: cuando los productos no llenan la columna, una toma de la sección la
  ocupa **entera** con los productos encima (pág. 26 del PDF). Encima sólo van productos
  recortados: uno con su fondo de estudio se ve como un rectángulo pegoteado.
- **Hojas de explicación** (`descripciones.json`): son las páginas 5, 6 y 7 del PDF, sin
  tabla, con el texto contándole al cliente de qué se trata cada alimento. Texto extraído
  del PDF, no reescrito. La primera lleva fotos circulares; las otras, foto de ambiente.
- **Sin huecos**: el paginador llena cada hoja hasta abajo y parte los grupos con
  "(cont.)"; lo que sobra al pie de una columna se tapa con una foto de ambiente.
  Verificado recorriendo las 35 páginas de contenido con Playwright.

## Fotos

Fuente unificada en `assets/productos/{codigo}.webp`, armada con `mapear_fotos.py`
cruzando la lista mayorista contra el catálogo de la web (`web-semillero-fresh`).
El matcher compara nombre y presentación por separado y exige que la marca coincida:
prefiere dejar un producto sin foto antes que ponerle la del vecino.

- `quitar_fondo.py` deja las fotos sobre transparente (venían en JPEG con fondo blanco).
- El placeholder con el logo de la empresa se detecta por hash y se descarta: estaba
  puesto en 18 productos distintos.
- Las mezclas salen del PDF original, renderizando la región tal como se ve (apaisada).
- En cada página se muestra **una foto por marca**, y la columna se llena según la
  forma de cada foto en vez de un número fijo (~4 por página).
- Si una página no tiene fotos propias, se completa con otras de la misma sección:
  primero del mismo subgrupo y priorizando las que menos se usaron, para que el
  cliente vaya viendo productos distintos y no la misma foto repetida.
- Balanceados usa las fotos del PDF original (bolsas Ganave/Conecar/Gepsa, caballo,
  cerdo, lechón), porque en la web esos productos tenían el logo como placeholder.

## Lo que falta

1. **Cobertura de fotos: 236 de 623 productos.** El agujero es ACCESORIOS (220 sin foto),
   después SNACKS (45), perros (30) y venenos (30). La carpeta de Drive
   (`Herramientas de Ventas\Imagenes`) tiene 521 fotos pero 364 son `IMG_xxxx` sin
   identificar, así que no se pueden mapear solas: hay que nombrarlas por código.
2. **% de proteína: 27 badges.** Faltan Compinche, Belcan, Exact Criadores, Belcat,
   Tiernitos gato, Gran Campeón gato, 9 Lives castrado y las variantes cachorro de
   Balanced/Premium/Complete. Ver `proteinas.json`: la web da datos de OTRA línea de la
   misma marca, así que el dato tiene que salir de la etiqueta o de la ficha del proveedor.
3. **El collage de bolsas superpuestas** que el PDF usa en algunas familias (4 bolsas de
   Rosco encastradas en 2×2). La diseñadora lo armó a mano en Photoshop.

## Higiene de datos

`build.py` deja `reporte_sheet.txt` con los productos cuyo nombre viene mal cargado
en la planilla (`░` y `║` en vez de `°`, `Ð` en vez de `Ñ`). El catálogo los corrige
al vuelo, pero **la planilla sigue sucia y la app de precios los muestra así**.

También cruza los códigos contra InfoManager. Hallazgos abiertos (verificados contra
`GET /articulos/stock`, no contra resúmenes):

- **Flecky carne fresca son los códigos `284` y `285`**, no 165/166 como figura en la
  planilla (esos son del Flecky tradicional). `build.py` los corrige al vuelo con
  `CODIGOS_IM`, pero **la planilla sigue mal: columna B, filas 98 y 99**.
- `1953` SUPER FLOW está cargado dos veces, y **BIOFERTILIZANTE x 3 kg no existe en IM**
  con ningún código (el 1978 es de VELOXAN).
