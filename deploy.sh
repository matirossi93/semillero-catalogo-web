#!/usr/bin/env bash
# Publica el catálogo en semilleroelmanantial.com.ar/catalogo
#
# Es HTML estático: se copia a /var/www/semillero-catalogo/catalogo y nginx lo
# sirve. No hay proceso corriendo ni nada que reiniciar.
#
#   ./deploy.sh              # regenera desde el Sheet y sube
#   ./deploy.sh --no-build   # sube lo que ya está generado
set -euo pipefail

HOST="${HOST:-semillero}"
RAIZ="${RAIZ:-/var/www/semillero-catalogo}"
DESTINO="$RAIZ/catalogo"
AQUI="$(cd "$(dirname "$0")" && pwd)"

if [[ "${1:-}" != "--no-build" ]]; then
  echo "==> regenerando desde la lista de precios"
  python "$AQUI/build.py"
fi
[[ -s "$AQUI/index.html" ]] || { echo "falta index.html — corré build.py"; exit 1; }

# Los archivos del server son de www-data: hay que tomarlos prestados para poder
# sobrescribirlos, y devolverlos al terminar.
echo "==> subiendo el sitio"
tar czf - -C "$AQUI" index.html assets \
  | ssh "$HOST" "sudo mkdir -p $DESTINO && sudo chown -R \$USER:\$USER $RAIZ \
      && tar xzf - -C $DESTINO --overwrite \
      && sudo chown -R www-data:www-data $RAIZ"

echo "==> actualizando el generador en /opt/catalogo"
tar czf - -C "$AQUI" build.py proteinas.json mapa_fotos.json descripciones.json \
  | ssh "$HOST" "tar xzf - -C /opt/catalogo --overwrite"

echo "==> verificando"
curl -sL -o /dev/null -w "    catalogo: %{http_code}\n" -m 30 \
  https://semilleroelmanantial.com.ar/catalogo
curl -s -o /dev/null -w "    web:      %{http_code}\n" -m 30 \
  https://semilleroelmanantial.com.ar/
echo "==> listo"
