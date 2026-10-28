# Decisiones de diseño · GlobalTecnology

Registro de decisiones tomadas donde el SPEC era ambiguo o dejaba opciones abiertas.

## Fase 1 · Base

1. **Raíz del repositorio = raíz del proyecto Django.** El SPEC muestra una carpeta `globaltecnology/`; se usa la raíz del repo para que Railway detecte `requirements.txt`, `manage.py` y `railway.json` sin configurar un "root directory".
2. **App `apps/core` adicional** para utilidades compartidas (filtro `|cop`, íconos SVG, procesamiento de imágenes, vista de media, emails, singletons, caché de fragmentos). Evita dependencias cruzadas entre apps de dominio.
3. **Selección de settings:** `manage.py` usa `config.settings.prod` si existe `RAILWAY_ENVIRONMENT` y `config.settings.dev` en otro caso; `wsgi.py` usa `prod` por defecto. `DJANGO_SETTINGS_MODULE` siempre tiene prioridad (el túnel usa `config.settings.tunnel`).
4. **Caché compartida en base de datos** (`DatabaseCache`). Con 3 workers de gunicorn una caché en memoria no se invalidaría en todos los procesos. La tabla se crea con una migración (`core.0001`) para no cambiar el comando de inicio exigido.
5. **Frontend sin build:** HTMX 2.0.3, Alpine.js 3.14.3, Chart.js 4.4.6 y SortableJS 1.15.3 se incluyen como archivos estáticos versionados en `static/vendor/` (no dependen de un CDN en tiempo de ejecución).
6. **CSRF con HTMX:** el token se lee de la cookie `csrftoken` en cada petición (`htmx:configRequest`), porque con `hx-boost` el `<body>` no se reemplaza y un token fijo en un atributo quedaría obsoleto tras iniciar sesión.
7. **Color de texto secundario:** el gris `#6E6E73` del SPEC se oscureció a `#5E5E63` para garantizar contraste AA (≥ 4,5:1) incluso sobre las superficies de vidrio con fondo azul claro.
8. **Ubicaciones DIVIPOLA:** el portal datos.gov.co no era accesible desde el entorno de construcción, así que el fixture `fixtures/divipola.json` (33 departamentos incluyendo Bogotá D.C., 1.121 municipios y áreas no municipalizadas, con códigos DANE) se generó a partir del paquete npm `divipola` 1.0.3 (licencia MIT), que reproduce la codificación DIVIPOLA del DANE. Los nombres se normalizaron a mayúsculas/minúsculas. `cargar_ubicaciones` es idempotente y acepta `--archivo` para recargar desde un CSV/JSON oficial actualizado convertido al mismo formato.
9. **Túnel con waitress:** por defecto waitress elimina las cabeceras `X-Forwarded-*` (comprobado). `scripts/demo.ps1` lo inicia con `--trusted-proxy=127.0.0.1 --trusted-proxy-headers="x-forwarded-proto x-forwarded-host x-forwarded-for"` para que Django sepa que la conexión del túnel es HTTPS y conozca el host público.
10. **Health check de Railway** en `/salud/` (exento de la redirección HTTPS y con `healthcheck.railway.app` permitido).
11. **HSTS preload** queda desactivado por defecto (`SECURE_HSTS_PRELOAD=False`, aviso W021 de `check --deploy`): inscribir el dominio en la lista de precarga es una decisión irreversible del dueño del dominio. Se activa con la variable `SECURE_HSTS_PRELOAD=True`.
12. **collectstatic en el build** se ejecuta explícitamente con `--settings=config.settings.prod` para que use el almacenamiento con manifiesto de WhiteNoise, igual que en tiempo de ejecución.

## Fase 2 · Catálogo

13. **Normalización de texto en Python + `unaccent` en la BD.** El `search_vector` se construye con texto ya sin tildes (configuración `spanish`), y la similitud de trigramas usa `unaccent(lower(nombre))`. Además se guarda `search_text` (texto normalizado con nombre, SKU, marca, categorías y especificaciones), que sirve para la similitud por palabra y como respaldo `icontains` en SQLite.
14. **Relevancia** = `2 × SearchRank + max(TrigramWordSimilarity(nombre), 0,9 × TrigramWordSimilarity(search_text))`, con umbral de similitud 0,42 (probado con errores como "samsumg", "galaxi", "tinkpad").
15. **"¿Quisiste decir…?"** corrige palabra por palabra contra un vocabulario cacheado (palabras de productos, marcas, categorías y búsquedas exitosas) usando `similarity()` de pg_trgm; en SQLite usa `difflib`.
16. **Índice de búsqueda síncrono**: se recalcula en señales al guardar productos, marcas, categorías o cambiar las categorías de un producto (una actualización por producto; barato y nunca queda desfasado).
17. **Precios en la BD**: `con_precios()` anota `precio_final_db` y `descuento_pct_db` con la misma lógica que las propiedades Python (incluida la vigencia por fechas) para filtrar por rango de precio y ordenar por precio o descuento. Una prueba verifica que ambos cálculos coinciden.
18. **Redondeo**: precio con descuento porcentual = `precio × (100 − %) / 100`, redondeado a pesos con mitad hacia arriba. El "% de ahorro" de "precio antes" se redondea igual.
19. **Facetas de especificaciones**: se calculan en Python sobre los resultados (máx. 2.000 filas) con semántica "OR dentro de una clave, AND entre claves"; solo se muestran claves con al menos 2 valores. Los conteos de marca/categoría usan una subconsulta de ids para no arrastrar anotaciones al `GROUP BY`.
20. **Caché del home**: el fragmento completo se cachea 10 min con una versión que se incrementa al guardar productos, categorías, marcas, banners o la configuración de la tienda. Las tarjetas en caché no incluyen `csrf_token` (sería el de otro usuario); el botón "Agregar" usa HTMX, que envía el token desde la cookie.
21. **Paginación "Cargar más"**: 24 productos por página; el botón trae la página siguiente y se reemplaza a sí mismo por las tarjetas nuevas y un nuevo botón, conservando los filtros.

## Fase 3 · Carrito y checkout

22. **"Agregar al carrito" de un visitante**: la intención (producto, cantidad, página de origen y si era "Comprar ahora") se firma con `django.core.signing` y viaja en el `?next=` del login/registro. Tras autenticarse, `/carrito/agregar-pendiente/<token>/` la completa y vuelve a la página original. El token expira en 2 horas y no se puede manipular.
23. **Stock en el carrito**: la cantidad se limita al stock disponible al agregar/actualizar. Si el stock o el estado cambian, el carrito muestra el problema y bloquea "Continuar al pago".
24. **Creación del pedido**: se bloquean las filas de producto (`select_for_update`), se revalidan stock y precio, y se recalcula el envío con el subtotal definitivo. El stock **no** se descuenta al crear el pedido; solo cuando Wompi aprueba el pago. El carrito se conserva hasta la aprobación.
25. **Nueva dirección en el checkout**: se valida junto con el formulario y solo se guarda si todo es válido; queda disponible en "Mis direcciones".
26. **Número de pedido** `GT-AAAA-NNNNNN`, derivado del id (único y legible).
27. **El checkout completa el perfil** (teléfono, tipo y número de documento) si estaban vacíos, porque Wompi los usa para PSE.
28. **htmx `attributesToSettle`** se limita a `width/height`: el valor por defecto restauraba `style`/`class` después de que Alpine los aplicaba (mostraba el desplegable de sugerencias vacío tras navegar con hx-boost).
