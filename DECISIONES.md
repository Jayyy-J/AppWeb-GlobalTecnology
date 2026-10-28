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
