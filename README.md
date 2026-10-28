# GlobalTecnology · Tienda en línea

Tienda de tecnología para Colombia construida con **Django 5 + PostgreSQL + HTMX + Alpine.js**, con diseño azul y blanco estilo "Apple Glass", pagos con **Wompi**, envíos configurables por zona (DIVIPOLA), seguimiento de pedidos con evidencias fotográficas y un **panel de administración propio** en `/panel/`.

- Navegación, búsqueda predictiva (tolerante a tildes y errores) y filtros sin recargar la página.
- Carrito persistente; el visitante inicia sesión al agregar y el producto se agrega solo al volver.
- Checkout con cálculo de envío (gratis, municipio, departamento, tarifa fija, cotización manual o sin cobertura).
- Wompi Web Checkout + webhook verificado e idempotente + sincronización de respaldo.
- Panel: dashboard, productos con fotos y descuentos, categorías, marcas, pedidos con evidencias, envíos, clientes, contenido, reportes CSV y auditoría.

Las decisiones de diseño están en [`DECISIONES.md`](DECISIONES.md).

---

## Contenido

1. [Requisitos](#1-requisitos)
2. [Instalación local en Windows (PowerShell)](#2-instalación-local-en-windows-powershell)
3. [Entorno de prueba compartible (VS Code Ports)](#3-entorno-de-prueba-compartible)
4. [Despliegue en Railway](#4-despliegue-en-railway)
5. [Configuración de Wompi](#5-configuración-de-wompi)
6. [Comandos](#6-comandos)
7. [Pruebas](#7-pruebas)
8. [Estructura del proyecto](#8-estructura-del-proyecto)
9. [Variables de entorno](#9-variables-de-entorno)

---

## 1. Requisitos

- **Python 3.12** ([python.org](https://www.python.org/downloads/windows/), marca "Add python.exe to PATH").
- **Git** y **VS Code**.
- **PostgreSQL 14+** (recomendado, igual que producción). Sin PostgreSQL se usa SQLite automáticamente, pero la búsqueda es más básica (no tolera errores de escritura).

## 2. Instalación local en Windows (PowerShell)

```powershell
# 1. Clonar
git clone https://github.com/Jayyy-J/AppWeb-GlobalTecnology.git
cd AppWeb-GlobalTecnology

# 2. Entorno virtual (si PowerShell bloquea la activación, ejecuta primero la línea de Set-ExecutionPolicy)
Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1

# 3. Dependencias
python -m pip install --upgrade pip
pip install -r requirements.txt

# 4. Variables de entorno de desarrollo
Copy-Item .env.example .env
notepad .env   # pon DEBUG=True y tu DATABASE_URL (o bórrala para usar SQLite)
```

### Base de datos PostgreSQL

**Opción A – Instalador oficial:** descarga PostgreSQL desde [postgresql.org/download/windows](https://www.postgresql.org/download/windows/), instala con el usuario `postgres` y crea la base:

```powershell
& "C:\Program Files\PostgreSQL\16\bin\createdb.exe" -U postgres globaltec
```

**Opción B – Docker Desktop:**

```powershell
docker run --name globaltec-db -e POSTGRES_PASSWORD=postgres -e POSTGRES_DB=globaltec -p 5432:5432 -d postgres:16
```

En ambos casos, en `.env`:

```
DATABASE_URL=postgres://postgres:postgres@localhost:5432/globaltec
```

> Las extensiones `pg_trgm` y `unaccent` se crean solas con las migraciones.

### Primer arranque

```powershell
python manage.py migrate          # crea tablas, extensiones y carga los 1.121 municipios DIVIPOLA
python manage.py seed_demo        # datos de demostración (idempotente)
python manage.py runserver
```

Abre <http://127.0.0.1:8000>. Credenciales de demostración:

| Rol | Email | Contraseña |
|---|---|---|
| Administrador (panel `/panel/`) | `admin@globaltecnology.co` | `Admin12345!` |
| Cliente | `cliente@globaltecnology.co` | `Cliente12345!` |

Los emails se imprimen en la consola mientras no configures SMTP.

---

## 3. Entorno de prueba compartible

Permite correr la tienda **en tu PC con Windows** y compartirla con el cliente mediante un enlace público de la pestaña **Ports** de VS Code (Dev Tunnels). Usa `config.settings.tunnel` (DEBUG siempre apagado, HTTPS del túnel, cookies seguras) y el servidor **waitress** (gunicorn no funciona en Windows).

### Paso a paso

1. **Instala el proyecto** como en la [sección 2](#2-instalación-local-en-windows-powershell) (venv + `pip install -r requirements.txt`). Si PowerShell no deja activar el entorno: `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned`.

2. **Crea el archivo de variables del túnel** y llénalo (deja `SITE_URL` vacío por ahora):

   ```powershell
   Copy-Item .env.tunnel.example .env.tunnel
   notepad .env.tunnel
   ```

   Completa `SECRET_KEY`, `DATABASE_URL` (PostgreSQL recomendado) y las llaves **de prueba** de Wompi (`pub_test_…`, `prv_test_…`, `test_events_…`, `test_integrity_…`).

3. **Ejecuta el script** y confirma que <http://127.0.0.1:8000> abre la tienda:

   ```powershell
   .\scripts\demo.ps1
   ```

   El script activa el venv, carga `.env.tunnel`, ejecuta `migrate`, `collectstatic`, `cargar_ubicaciones`, `seed_demo` (todos idempotentes), verifica la configuración con `check_tunnel`, imprime las credenciales e inicia waitress en `127.0.0.1:8000`.

4. **Reenvía el puerto en VS Code:** panel inferior → pestaña **Ports** → **Forward a Port** → escribe `8000`. La primera vez te pedirá iniciar sesión con **GitHub o Microsoft**.

5. **Hazlo público:** clic derecho sobre el puerto → **Port Visibility → Public** (sin esto, quien abra el enlace tendrá que iniciar sesión con una cuenta). Copia la **Forwarded Address**, con la forma `https://xxxxx-8000.use2.devtunnels.ms`.

6. **Pega esa URL en `SITE_URL`** de `.env.tunnel` (sin `/` al final) y reinicia el script: `Ctrl+C` y `.\scripts\demo.ps1`. Se usa para la `redirect-url` de Wompi y los enlaces de los emails. `check_tunnel` debe mostrar todo en `[OK]`.

7. **Wompi sandbox:** en el [panel de comercios de Wompi](https://comercios.wompi.co/) en **modo pruebas** → *Desarrolladores* → *URL de eventos*, registra:

   ```
   https://<url-del-tunel>/pagos/wompi/eventos/
   ```

   Usa **solo** llaves `pub_test_` / `prv_test_`, nunca las de producción. Para pagar usa los [datos de prueba de Wompi](#datos-de-prueba-de-wompi-sandbox).

8. **Comparte el enlace.** Ten en cuenta que:
   - Funciona **solo mientras el PC esté encendido, VS Code abierto y el script corriendo**.
   - La primera vez que alguien abre el enlace, Microsoft muestra una **página de aviso** del túnel: hay que darle **"Continuar"**.
   - Mientras no elimines el puerto, la URL normalmente se conserva entre sesiones. **Si cambia, repite los pasos 6 y 7.**
   - Al terminar la demo, vuelve el puerto a **Private** o elimínalo.

### Problemas comunes

| Síntoma | Causa y solución |
|---|---|
| **Error 400 (Bad Request)** | El host no está en `ALLOWED_HOSTS`. Los settings de túnel ya permiten `.devtunnels.ms`; verifica que el script use `DJANGO_SETTINGS_MODULE=config.settings.tunnel` y revisa `python manage.py check_tunnel`. |
| **Error 403 de CSRF** al iniciar sesión o pagar | `SITE_URL` no coincide con la URL del túnel o falta reiniciar el script tras cambiarla. Debe empezar por `https://`. |
| **Bucle de redirecciones HTTPS** | Algo activó `SECURE_SSL_REDIRECT`. En el túnel debe estar en `False` (el túnel ya entrega HTTPS). No uses `config.settings.prod` para la demo. |
| **No cargan estilos o imágenes** | Ejecuta el script completo (hace `collectstatic`). Las imágenes subidas viven en `MEDIA_ROOT` (por defecto `media\`); confirma que la carpeta existe y es escribible. |
| **El webhook de Wompi no llega** | El puerto debe estar en **Public**, la URL registrada en Wompi debe ser exactamente `https://<url-del-tunel>/pagos/wompi/eventos/` y el PC debe seguir encendido. Como respaldo, ejecuta `python manage.py wompi_sync`. |
| **Puerto 8000 ocupado** | `netstat -ano \| findstr :8000` muestra el PID; ciérralo con `taskkill /PID <pid> /F` o cierra el otro servidor. |
| **El script no se ejecuta** | `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned` y vuelve a intentarlo. |

> `demo.ps1` inicia waitress con `--trusted-proxy=127.0.0.1 --trusted-proxy-headers="x-forwarded-proto x-forwarded-host x-forwarded-for"`: sin eso waitress descarta las cabeceras del túnel y Django no sabría que la conexión es HTTPS.

---

## 4. Despliegue en Railway

1. **Proyecto:** en [railway.com](https://railway.com) → *New Project* → *Deploy from GitHub repo* → elige este repositorio. Railway detecta `railway.json`:
   - Build: `python manage.py collectstatic --noinput --settings=config.settings.prod`
   - Inicio: `python manage.py migrate --noinput && gunicorn config.wsgi --bind 0.0.0.0:$PORT --workers 3`
   - Health check: `/salud/`
2. **Base de datos:** *+ New → Database → PostgreSQL*. En el servicio web, agrega la variable `DATABASE_URL` referenciando la del plugin (`${{Postgres.DATABASE_URL}}`).
3. **Volumen para fotos:** en el servicio web → *Settings → Volumes → Add volume* con *Mount path* **`/app/media`**, y la variable `MEDIA_ROOT=/app/media`. Las fotos de productos, banners y evidencias sobreviven a cada redeploy. (El volumen solo existe en tiempo de ejecución, no durante el build; por eso nada en el build escribe en media.)
4. **Variables** (*Variables* del servicio web): todas las de [`.env.example`](.env.example). Mínimo:

   ```
   SECRET_KEY=<cadena larga aleatoria>
   DEBUG=False
   ALLOWED_HOSTS=tudominio.com,www.tudominio.com
   CSRF_TRUSTED_ORIGINS=https://tudominio.com,https://www.tudominio.com
   SITE_URL=https://tudominio.com
   MEDIA_ROOT=/app/media
   ADMIN_URL=<ruta-secreta>/
   WOMPI_PUBLIC_KEY=... WOMPI_PRIVATE_KEY=... WOMPI_EVENTS_SECRET=... WOMPI_INTEGRITY_SECRET=... WOMPI_ENV=production
   EMAIL_BACKEND=django.core.mail.backends.smtp.EmailBackend
   EMAIL_HOST=... EMAIL_PORT=587 EMAIL_HOST_USER=... EMAIL_HOST_PASSWORD=... DEFAULT_FROM_EMAIL=... ADMIN_NOTIFY_EMAIL=...
   ```

   El dominio `*.up.railway.app` que asigna Railway (`RAILWAY_PUBLIC_DOMAIN`) se agrega solo a `ALLOWED_HOSTS` y `CSRF_TRUSTED_ORIGINS`. Generar dominio: *Settings → Networking → Generate Domain* (o conecta tu dominio propio).
5. **Primer despliegue:** las migraciones crean las extensiones de PostgreSQL, la configuración inicial, las páginas legales base y cargan los municipios DIVIPOLA. Crea el administrador con la [CLI de Railway](https://docs.railway.com/guides/cli):

   ```powershell
   railway link
   railway ssh            # o: railway run python manage.py createsuperuser
   python manage.py createsuperuser
   ```

   No ejecutes `seed_demo` en producción (son datos de demostración).
6. **Respaldo de webhooks:** crea un segundo servicio desde el mismo repo con *Cron Schedule* `*/20 * * * *` y comando de inicio `python manage.py wompi_sync` (mismas variables). Así se recuperan pagos si un webhook se pierde.

`python manage.py check --deploy --settings=config.settings.prod` solo debe mostrar el aviso opcional de `SECURE_HSTS_PRELOAD` (ver `DECISIONES.md`).

---

## 5. Configuración de Wompi

1. Crea la cuenta en [comercios.wompi.co](https://comercios.wompi.co/).
2. En *Desarrolladores* copia, para cada ambiente:
   - Llave pública → `WOMPI_PUBLIC_KEY`
   - Llave privada → `WOMPI_PRIVATE_KEY`
   - Secreto de **eventos** → `WOMPI_EVENTS_SECRET`
   - Secreto de **integridad** → `WOMPI_INTEGRITY_SECRET`
   - `WOMPI_ENV=sandbox` (pruebas) o `production`.
3. Registra la **URL de eventos** (webhook) en cada ambiente:
   - Sandbox (pruebas, túnel o Railway de pruebas): `https://<dominio-de-pruebas>/pagos/wompi/eventos/`
   - Producción: `https://<tu-dominio>/pagos/wompi/eventos/`
4. El cliente nunca escribe datos de tarjeta en la tienda: se le redirige al **Web Checkout** de Wompi (`https://checkout.wompi.co/p/`) con la firma de integridad `SHA256(referencia + monto_en_centavos + COP + secreto_integridad)`. Al volver, `/pagos/resultado/` consulta la transacción en la API; el webhook (con checksum verificado) es quien aprueba el pedido y descuenta stock una sola vez.

### Datos de prueba de Wompi (sandbox)

Según la documentación de Wompi (*Datos de prueba en Sandbox*); verifícalos allí por si cambian:

| Medio | Aprobada | Rechazada |
|---|---|---|
| Tarjeta | `4242 4242 4242 4242` | `4111 1111 1111 1111` |
| Nequi | `3991111111` | `3992222222` |
| PSE | Banco "que aprueba" en el simulador | Banco "que rechaza" en el simulador |
| Botón Bancolombia | Elige el resultado en la pantalla del simulador | — |

Para tarjetas usa cualquier fecha de vencimiento futura, cualquier CVC de 3 dígitos y cualquier nombre.

---

## 6. Comandos

| Comando | Descripción |
|---|---|
| `python manage.py migrate` | Crea/actualiza la BD (incluye extensiones, configuración inicial, páginas legales y DIVIPOLA). |
| `python manage.py cargar_ubicaciones [--archivo ruta.json]` | Carga o actualiza departamentos y municipios desde `fixtures/divipola.json` (idempotente). |
| `python manage.py seed_demo [--sin-imagenes]` | Datos de demostración: tienda, 6 categorías con subcategorías, 5 marcas, 30 productos con imágenes, 2 banners, tarifas y usuarios de prueba (idempotente). |
| `python manage.py wompi_sync [--minutos 15]` | Consulta en Wompi los pagos pendientes de más de 15 minutos (respaldo de webhooks). |
| `python manage.py check_tunnel` | Verifica la configuración del entorno de túnel (SITE_URL HTTPS, hosts, CSRF, media escribible, llaves de prueba). |
| `python manage.py createsuperuser` | Crea un administrador. |
| `.\scripts\demo.ps1` | Arranca el entorno de prueba compartible en Windows. |

---

## 7. Pruebas

```powershell
pytest
```

116 pruebas: cálculo de envío (cada regla y su prioridad), precios con descuento y vigencia, firma de integridad (con el ejemplo oficial de Wompi) y checksum del webhook (válido, inválido y monto alterado), idempotencia (doble `APPROVED` descuenta stock una vez), máquina de estados y fotos obligatorias, permisos (visitante sin carrito, pedidos y evidencias ajenas, no-staff fuera del panel), búsqueda con tildes y errores de escritura (en PostgreSQL), número de consultas del listado, panel y exportaciones. Con SQLite se omiten las 3 pruebas exclusivas de PostgreSQL.

---

## 8. Estructura del proyecto

```
config/            settings (base, dev, prod, tunnel, test), urls, wsgi
apps/
  core/            utilidades: filtro |cop, íconos, imágenes WebP, media, emails, caché, check_tunnel
  accounts/        usuario con email, registro, login, perfil, direcciones
  catalog/         categorías, marcas, productos, imágenes, búsqueda, filtros, SearchLog
  cart/            carrito persistente
  orders/          pedidos, máquina de estados, evidencias, línea de tiempo
  payments/        Wompi: checkout, resultado, webhook, wompi_sync
  shipping/        DIVIPOLA, configuración y cálculo de envíos
  storefront/      home, banners, páginas legales, configuración, sitemap, seed_demo
  panel/           panel de administración /panel/ y auditoría
templates/         plantillas (tienda, panel y emails)
static/            CSS (tokens + vidrio), JS y librerías vendorizadas (htmx, Alpine, Chart.js, Sortable)
fixtures/          divipola.json
scripts/demo.ps1   entorno de prueba compartible
tests/             pruebas (pytest)
```

## 9. Variables de entorno

Ver [`.env.example`](.env.example) (producción/desarrollo) y [`.env.tunnel.example`](.env.tunnel.example) (túnel). Opcionales adicionales: `SECURE_HSTS_PRELOAD`, `SECURE_HSTS_SECONDS`, `AXES_FAILURE_LIMIT` (intentos de login, por defecto 5), `WOMPI_ENVIAR_DIRECCION` (enviar dirección a Wompi, por defecto `True`), `DB_CONN_MAX_AGE`.
