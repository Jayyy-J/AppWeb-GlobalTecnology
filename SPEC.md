# PROMPT PARA CLAUDE CODE — Tienda en línea "GlobalTecnology"

Eres un ingeniero senior full-stack en Django. Vas a construir **de principio a fin** una tienda en línea lista para producción llamada **GlobalTecnology**, para un cliente en Colombia. Trabaja por fases (al final de este documento), ejecuta pruebas al cerrar cada fase, haz commits pequeños con mensajes claros y no des el proyecto por terminado hasta que toda la checklist final esté en verde.

Si algo de este documento es ambiguo, toma la decisión más razonable, déjala anotada en `DECISIONES.md` y continúa. Antes de implementar la integración de Wompi, **verifica los endpoints y la fórmula de las firmas contra la documentación oficial vigente (https://docs.wompi.co)**: si algo difiere de lo que dice aquí, manda la documentación oficial.

---

## 1. Stack técnico (obligatorio)

- Python 3.12, **Django 5.x**
- **PostgreSQL** (Railway en producción) con `psycopg[binary]` 3 y `dj-database-url`
- `django.contrib.postgres` habilitado; extensiones `pg_trgm` y `unaccent` creadas desde una migración (`TrigramExtension`, `UnaccentExtension`)
- Frontend: **Django Templates + HTMX + Alpine.js** (servidos desde CDN con versión fija o como archivos estáticos dentro del repo). Sin React, sin paso de build de Node
- CSS propio con variables (design tokens), en archivos estáticos. Sin Tailwind ni otra herramienta que requiera compilación
- `whitenoise` para estáticos, `gunicorn` como servidor
- `Pillow` para procesar imágenes
- `django-axes` para limitar intentos de inicio de sesión
- `requests` para la API de Wompi
- `pytest` + `pytest-django` para pruebas
- Configuración mediante variables de entorno (`os.environ` / `django-environ`), sin secretos en el código
- Desarrollo local en **Windows con PowerShell y VS Code**: todas las instrucciones del README deben funcionar en PowerShell
- Despliegue: **GitHub → Railway**

**Desarrollo local:** si `DATABASE_URL` no está definida, usar SQLite como respaldo. En ese caso la búsqueda debe degradar con elegancia a `icontains` (sin trigramas). En producción siempre se usa PostgreSQL.

---

## 2. Estructura del proyecto

```
globaltecnology/
├── config/                 # settings (base, dev, prod), urls, wsgi
├── apps/
│   ├── accounts/           # usuario personalizado, registro, login, perfil, direcciones
│   ├── catalog/            # categorías, marcas, productos, imágenes, búsqueda, filtros
│   ├── cart/               # carrito persistente en BD
│   ├── orders/             # pedidos, historial de estados, evidencias de envío
│   ├── payments/           # integración Wompi (checkout, redirect, webhook)
│   ├── shipping/           # configuración y cálculo de costos de envío, ubicaciones de Colombia
│   ├── storefront/         # home, banners, páginas legales, configuración de la tienda
│   └── panel/              # panel de administración propio (/panel/)
├── templates/
├── static/
├── media/                  # solo local; en Railway es el volumen
├── fixtures/               # departamentos y municipios de Colombia (DIVIPOLA)
├── tests/
├── requirements.txt
├── Procfile / railway.json
├── .env.example
├── README.md
└── DECISIONES.md
```

---

## 3. Modelo de datos

### accounts
- **User** personalizado (`AbstractUser`) con **email como identificador de login** (sin username). Campos: nombre, apellido, email (único), teléfono, tipo y número de documento (CC, CE, NIT, PP; Wompi lo usa para PSE), `acepta_tratamiento_datos` (bool + fecha), `is_staff`.
- **Address**: usuario, alias ("Casa", "Oficina"), nombre de quien recibe, teléfono, departamento (FK), municipio (FK), dirección, barrio, indicaciones adicionales, `es_predeterminada`.

### shipping
- **Departamento** y **Municipio**: cargados desde un fixture con la **lista completa DIVIPOLA del DANE** (32 departamentos + Bogotá D.C. y todos los municipios). Genera el fixture a partir del dataset oficial de datos.gov.co e inclúyelo en el repo.
- **ShippingSettings** (singleton, editable desde el panel):
  - `tarifa_fija_activa` (bool) + `tarifa_fija_valor`
  - `envio_gratis_activo` (bool) + `envio_gratis_desde` (monto mínimo del subtotal)
  - `tarifas_por_zona_activas` (bool)
  - `cotizacion_manual_activa` (bool): para destinos sin tarifa definida
- **ShippingZoneRate**: departamento (obligatorio), municipio (opcional; si existe, tiene prioridad sobre la tarifa del departamento), valor, días estimados de entrega, activo.

**Algoritmo de cálculo del envío** (función pura en `shipping/services.py`, con pruebas unitarias de cada rama):
1. Si `envio_gratis_activo` y subtotal ≥ `envio_gratis_desde` → **$0**.
2. Si `tarifas_por_zona_activas` y existe tarifa para el **municipio** → esa tarifa.
3. Si `tarifas_por_zona_activas` y existe tarifa para el **departamento** → esa tarifa.
4. Si `tarifa_fija_activa` → tarifa fija.
5. Si `cotizacion_manual_activa` → el pedido queda en estado **"Esperando cotización de envío"** (ver flujo en la sección 7).
6. Si ninguna aplica → mostrar al cliente que no hay envíos a ese destino y bloquear el checkout.

El checkout siempre muestra al cliente cuál regla se aplicó ("Envío gratis por compras superiores a $X", "Envío a Villavicencio: $Y", etc.).

### catalog
- **Category**: nombre, slug, descripción, imagen, `parent` (opcional, para subcategorías de un nivel), orden, activa, `mostrar_en_menu`.
- **Brand**: nombre, slug, logo (opcional), activa.
- **Product**:
  - nombre, slug, SKU (único), marca (FK opcional)
  - **categorías: ManyToMany** + `categoria_principal` (FK); un producto puede pertenecer a varias categorías
  - descripción corta, descripción larga (texto enriquecido básico con saneamiento de HTML, por ejemplo con `bleach` o `nh3`)
  - `precio` (precio de venta real, entero en COP con IVA incluido)
  - `tipo_descuento`: `ninguno` | `porcentaje` | `precio_antes`
    - `porcentaje`: `descuento_porcentaje` (1–90). Precio final = precio × (1 − %), redondeado a pesos
    - `precio_antes`: `precio_antes` (> precio). Se muestra tachado y el % de ahorro se calcula automáticamente
  - Opcional: `descuento_inicia` y `descuento_termina` (fechas); fuera del rango no se aplica descuento
  - stock, `stock_minimo_alerta`, activo, destacado, `nuevo`
  - **especificaciones**: `JSONField` clave/valor (por ejemplo `{"RAM": "8 GB", "Color": "Negro"}`), usado en la ficha y en los filtros dinámicos
  - `search_vector` (`SearchVectorField`) + índices GIN (trigramas sobre nombre, `search_vector`)
  - timestamps
  - Propiedades: `precio_final`, `porcentaje_ahorro`, `tiene_descuento`, `disponible`
- **ProductImage**: producto, imagen, texto alternativo, orden, `es_principal`. Al guardar se convierte a **WebP** y se generan tamaños (thumb 300 px, media 800 px, grande 1600 px) con Pillow. Validar tipo real del archivo y peso máximo de 8 MB.
- **SearchLog**: término normalizado, cantidad de búsquedas, cantidad de resultados, última fecha. Alimenta "búsquedas populares" y le muestra al admin qué buscan los clientes y no encuentran.

### cart
- **Cart** (uno por usuario) y **CartItem** (producto, cantidad, `precio_al_agregar` como referencia). El precio que se cobra **siempre se recalcula en el servidor** al momento del checkout.

### orders
- **Order**:
  - número legible y único (por ejemplo `GT-2026-000123`), usuario
  - **snapshot** de la dirección de envío y de los datos del cliente (texto copiado, no FK que pueda cambiar)
  - subtotal, descuentos, costo de envío, total (enteros COP)
  - `regla_envio_aplicada` (texto)
  - `estado_pago`: `pendiente` | `aprobado` | `rechazado` | `anulado` | `error`
  - `estado_pedido`: `esperando_cotizacion` | `pendiente_pago` | `en_proceso` | `enviado` | `entregado` | `cancelado`
  - `metodo_entrega`: `transportadora` | `personal` (se define al marcar "enviado")
  - transportadora (nombre), número de guía (opcional), URL de rastreo (opcional)
  - referencia Wompi, ID de transacción Wompi, método de pago usado
  - `stock_descontado` (bool, para idempotencia)
  - notas internas del admin (no visibles al cliente)
- **OrderItem**: snapshot de nombre, SKU, imagen, precio unitario final, precio antes (si aplicaba), cantidad, subtotal; FK al producto con `SET_NULL`.
- **OrderStatusEvent** (historial / línea de tiempo): pedido, estado, nota visible al cliente, **foto de evidencia**, usuario que hizo el cambio, fecha.

**Reglas de evidencia (validadas en formulario y en el modelo/servicio):**
- Pasar a **"Enviado"** exige elegir `metodo_entrega` y **subir foto obligatoria**:
  - `transportadora`: foto o captura de la guía/flete + nombre de la transportadora (número de guía y URL de rastreo opcionales)
  - `personal`: foto de la entrega o del paquete listo + nombre de quien entrega
- Pasar a **"Entregado"**: foto obligatoria si la entrega es personal; opcional si es por transportadora.
- Solo se puede pasar a "En proceso" si `estado_pago = aprobado`.
- Las transiciones válidas se definen en un solo lugar (una pequeña máquina de estados en `orders/services.py`). Las transiciones inválidas se rechazan.

**Privacidad de las evidencias:** las fotos de envío **no** son públicas. Se sirven mediante una vista protegida que solo permite verlas al dueño del pedido y al staff. Las imágenes de productos, categorías y banners sí son públicas.

### storefront
- **StoreSettings** (singleton): nombre de la tienda, logo, favicon, número de WhatsApp, email de contacto, redes sociales, texto del pie de página, texto de la barra de anuncios superior (por ejemplo "Envío gratis desde $200.000"), NIT/razón social para la sección legal.
- **Banner**: imagen escritorio, imagen móvil, título, subtítulo, enlace, orden, activo, fechas de vigencia.
- **LegalPage**: términos y condiciones, política de privacidad y tratamiento de datos, política de envíos, cambios, devoluciones y **derecho de retracto**. Son editables desde el panel y se crean con un texto base que cubra la Ley 1480 de 2011 (Estatuto del Consumidor, incluido el retracto en ventas a distancia) y la Ley 1581 de 2012 (habeas data). Marca ese texto como borrador para revisión de un abogado.

---

## 4. Diseño visual: azul y blanco con estilo "Apple Glass"

- Paleta en variables CSS en `:root`:
  - azul primario `#0A66FF`, azul profundo `#0B3D91`, azul claro `#E8F1FF`, blanco `#FFFFFF`, gris texto `#1D1D1F`, gris secundario `#6E6E73`
  - verde para "ahorro" y rojo suave para "agotado", usados con moderación
- **Glassmorphism**: superficies `rgba(255,255,255,0.6–0.75)` con `backdrop-filter: blur(20px) saturate(180%)`, borde `1px solid rgba(255,255,255,0.5)`, sombras suaves y difusas, radios de 14–20 px. El fondo general es un degradado sutil blanco → azul muy claro con algunas "manchas" de color difuminadas para que el vidrio se note.
- **Fallback**: con `@supports not (backdrop-filter: blur(1px))`, fondos sólidos blancos al 95%.
- Tipografía: `-apple-system, BlinkMacSystemFont, "SF Pro Display", "Inter", "Segoe UI", Roboto, sans-serif` (Inter desde Google Fonts como respaldo).
- Micro-interacciones: hover con elevación leve, transiciones de 150–250 ms, respetando `prefers-reduced-motion`.
- Contraste mínimo **WCAG AA** en todo el texto, incluido el que va sobre vidrio.
- Solo modo claro.
- Diseño **mobile-first**, totalmente responsivo. En móvil: menú inferior o cajón lateral, carrito accesible con un toque y barra de búsqueda siempre visible.

---

## 5. Experiencia del cliente (referencia: Amazon)

**Navegar no requiere cuenta.** Solo se exige iniciar sesión para **agregar al carrito**, ver el carrito, pagar y gestionar direcciones.

- Si un visitante sin sesión pulsa "Agregar al carrito", se le lleva a login/registro con `?next=` y, al autenticarse, **el producto se agrega automáticamente** y vuelve a la página donde estaba.

### Navegación fluida
- `hx-boost` en la navegación principal para transiciones tipo SPA, con historial del navegador funcional.
- Filtros, ordenamiento, paginación y búsqueda se actualizan con HTMX **sin recargar la página**, y la URL se actualiza (`hx-push-url`) para que se pueda compartir y usar el botón "atrás".
- Imágenes con `loading="lazy"`, `srcset` con los tamaños generados y dimensiones fijas para evitar saltos de diseño.
- Skeletons o indicadores durante las cargas HTMX.
- Consultas optimizadas (`select_related`, `prefetch_related`), sin consultas N+1. Agrega una prueba que verifique el número de consultas en el listado de productos.
- Caché de fragmentos para el menú de categorías y la home, invalidada al guardar desde el panel.

### Header (sticky, con efecto vidrio)
Logo GlobalTecnology · selector de categoría + **barra de búsqueda central** · "Hola, [nombre] / Iniciar sesión" · "Mis pedidos" · **ícono de carrito con contador** actualizado por HTMX. Debajo, la barra de categorías y la barra de anuncios.

### Home
Carrusel de banners · grilla de categorías con imagen · "Ofertas del día" (productos con descuento) · "Destacados" · "Lo más nuevo" · beneficios (envíos, pago seguro con Wompi, soporte por WhatsApp).

### Búsqueda predictiva
- Con debounce de 250 ms y desde 2 caracteres, se muestra un **desplegable de sugerencias** con:
  - productos coincidentes (miniatura, nombre, precio final)
  - categorías coincidentes
  - términos populares relacionados (de `SearchLog`)
  - el texto buscado resaltado en las sugerencias
- Tolerante a **tildes** (`unaccent`) y a **errores de escritura** (`TrigramSimilarity` / `trigram_similar`), combinado con `SearchRank` sobre el `search_vector` (nombre con peso A, marca y categorías con peso B, descripción y especificaciones con peso C).
- Navegable con teclado (flechas, Enter, Esc) y accesible (roles ARIA de combobox/listbox).
- Si no hay resultados: "¿Quisiste decir…?" con el término más parecido, más productos sugeridos.
- Cada búsqueda enviada se registra en `SearchLog`.

### Listado y filtros
- Filtros en barra lateral (en móvil, panel deslizable):
  - categoría y subcategoría
  - marca
  - rango de precio (mínimo/máximo)
  - solo con descuento
  - solo disponibles
  - **especificaciones dinámicas**: se generan a partir de las claves de `especificaciones` presentes en los productos del resultado actual (por ejemplo, Color, RAM, Almacenamiento), con conteo por valor
- Ordenar por: relevancia, precio menor a mayor, precio mayor a menor, más nuevos, mayor descuento.
- Chips de filtros activos con "x" para quitarlos y botón "Limpiar todo".
- Paginación con "Cargar más" (HTMX) que conserva los filtros.

### Ficha de producto
Galería con miniaturas y zoom al pasar el cursor (en móvil, deslizar) · nombre, marca, SKU · **precio final**, precio anterior tachado y badge "-X%" si aplica · disponibilidad y stock bajo ("¡Quedan 3!") · selector de cantidad limitado al stock · botones "Agregar al carrito" y "Comprar ahora" (este último agrega y va directo al checkout) · caja de compra fija en escritorio · descripción · tabla de especificaciones · productos relacionados de la misma categoría · breadcrumbs · metadatos SEO y Open Graph.

### Carrito
Lista de productos con cambio de cantidad y eliminación por HTMX · validación de stock en tiempo real · subtotal, ahorro total y estimado de envío según la dirección predeterminada · botón "Continuar al pago".

### Checkout
1. Selección o creación de **dirección de envío** (selects dependientes Departamento → Municipio con HTMX).
2. Datos de contacto y documento (precargados del perfil).
3. Resumen con el costo de envío calculado y la regla aplicada.
4. Casilla obligatoria de aceptación de términos.
5. Botón **"Pagar con Wompi"**.

**El cliente NUNCA escribe datos de tarjeta en nuestro sitio.** El pago se hace en el checkout de Wompi (tarjeta, PSE, Nequi, Bancolombia, etc.).

### Mi cuenta
Perfil · direcciones · **Mis pedidos** con lista y detalle · **seguimiento** del pedido como línea de tiempo vertical (En proceso → Enviado → Entregado) que muestra fecha, nota, transportadora, número y enlace de guía, y las **fotos de evidencia** (en un lightbox) · botón "Pagar ahora" en pedidos pendientes de pago o ya cotizados.

### Autenticación
Registro (nombre, email, contraseña, teléfono y aceptación de tratamiento de datos), login, logout, recuperación de contraseña por email, cambio de contraseña. Límite de intentos con `django-axes`.

---

## 6. Integración de pagos con Wompi

Usa el **Web Checkout de Wompi** (redirección a `https://checkout.wompi.co/p/` mediante un formulario GET), o el Widget si te resulta más limpio. Documenta la elección en `DECISIONES.md`.

**Variables de entorno:** `WOMPI_PUBLIC_KEY`, `WOMPI_PRIVATE_KEY`, `WOMPI_EVENTS_SECRET`, `WOMPI_INTEGRITY_SECRET`, `WOMPI_ENV` (`sandbox` | `production`).
- API sandbox: `https://sandbox.wompi.co/v1`
- API producción: `https://production.wompi.co/v1`

**Flujo:**
1. Al confirmar el checkout: se revalidan stock y precios en el servidor, se crea el `Order` con `estado_pago=pendiente` y `estado_pedido=pendiente_pago`, y se genera una **referencia única**.
2. Se calcula la **firma de integridad**: `SHA256(referencia + monto_en_centavos + moneda + integrity_secret)` y se envían al checkout de Wompi la llave pública, `COP`, el monto en centavos, la referencia, la firma, la `redirect-url` y los datos del cliente (email, nombre, teléfono, documento y dirección de envío).
3. **Redirect URL** (`/pagos/resultado/`): recibe el `id` de la transacción y la **consulta en la API de Wompi** (`GET /transactions/{id}`) para mostrar el resultado. Esta página **nunca** debe ser la única fuente de verdad.
4. **Webhook** (`POST /pagos/wompi/eventos/`, exento de CSRF):
   - verificar el checksum: concatenar los valores de `signature.properties` (leídos desde `data`) + `timestamp` + `WOMPI_EVENTS_SECRET`, aplicar SHA256 y comparar con `signature.checksum` mediante comparación en tiempo constante
   - verificar que el **monto y la referencia coincidan** con el pedido
   - **ser idempotente**: procesar el mismo evento varias veces no debe duplicar efectos
   - con `APPROVED`: `estado_pago=aprobado`, `estado_pedido=en_proceso`, **descontar stock** de forma atómica (`select_for_update`, una sola vez gracias a `stock_descontado`), vaciar el carrito, registrar un evento en la línea de tiempo y enviar emails al cliente y al admin
   - con `DECLINED`, `VOIDED` o `ERROR`: actualizar el estado; el carrito se conserva para que el cliente reintente
   - si después de aprobado no hay stock suficiente, marcar el pedido con una alerta visible en el panel
5. Botón "Reintentar pago" en pedidos rechazados, generando una referencia nueva vinculada al mismo pedido.
6. Comando `python manage.py wompi_sync` que consulta en Wompi las transacciones de pedidos `pendiente` de más de 15 minutos, como respaldo si un webhook se pierde.

---

## 7. Flujo de cotización manual del envío

Cuando el destino no tiene tarifa y la cotización manual está activa:
1. El cliente confirma el pedido **sin pagar**. Estado: `esperando_cotizacion`. Se le informa que recibirá el valor del envío por email.
2. El admin ve el pedido destacado en el panel, ingresa el valor del envío y una nota opcional.
3. El pedido pasa a `pendiente_pago`, se recalcula el total y se envía un email al cliente con un enlace para pagar.
4. El cliente paga desde "Mis pedidos" con el flujo normal de Wompi.
5. El stock **no** se reserva durante la cotización. Se revalida al pagar.

---

## 8. Panel de administración propio (`/panel/`)

Solo para usuarios `is_staff`. Usa el mismo lenguaje visual (vidrio azul y blanco), con barra lateral, responsivo y operado con HTMX. El Django admin queda disponible en una ruta no obvia (configurable por variable de entorno) como respaldo técnico.

El admin **controla todo lo que se muestra en la tienda**:

- **Dashboard**: ventas de hoy, de la semana y del mes; pedidos por estado; pedidos que requieren acción (por enviar, por cotizar, con alerta de stock); productos con stock bajo; top de productos vendidos; búsquedas sin resultados más frecuentes; gráfica simple de ventas de 30 días (Chart.js).
- **Productos**: listado con búsqueda, filtros y acciones masivas (activar/desactivar, destacar, asignar categoría, aplicar o quitar descuento). Formulario completo con:
  - subida **múltiple de fotos** con arrastrar y soltar, reordenamiento y selección de la principal
  - selector de tipo de descuento con **vista previa en vivo** de cómo verá el cliente el precio
  - editor de especificaciones clave/valor
  - asignación a varias categorías
  - duplicar producto
  - eliminar con confirmación (si el producto tiene pedidos, se desactiva en lugar de borrarse, para conservar el historial)
- **Categorías**: crear, editar, eliminar, reordenar con arrastrar y soltar, subcategorías, imagen, y una vista para **asignar y quitar productos** de cada categoría.
- **Marcas**: CRUD.
- **Pedidos**: listado con filtros (estado de pago, estado de pedido, fechas, búsqueda por número, cliente o email). En el detalle:
  - datos del cliente y dirección (con botón "copiar dirección")
  - productos
  - pagos y transacción Wompi
  - línea de tiempo
  - **formulario de cambio de estado** con las reglas de evidencia de la sección 3 (selección de transportadora o entrega personal, foto obligatoria, guía y nota para el cliente)
  - ingreso de cotización de envío
  - notas internas
  - cancelar pedido (con devolución de stock si ya se había descontado)
  - imprimir rótulo o guía interna en PDF o vista imprimible
- **Envíos**: configuración de `ShippingSettings` y CRUD de tarifas por departamento y municipio, con importación desde CSV.
- **Clientes**: listado y detalle (pedidos y total comprado); activar o desactivar cuentas; dar o quitar acceso de staff (solo superusuario).
- **Contenido**: banners, configuración de la tienda (logo, nombre, WhatsApp, redes, barra de anuncios) y páginas legales.
- **Reportes**: exportar pedidos y productos a CSV por rango de fechas.
- **Auditoría**: registro de quién cambió qué y cuándo en productos, precios, pedidos y configuración.

Todos los formularios validan en el servidor y muestran mensajes claros en español.

---

## 9. Notificaciones por email

Backend SMTP configurable por variables de entorno (en desarrollo, salida por consola). Plantillas HTML con la marca para:
- bienvenida
- recuperación de contraseña
- pedido recibido
- pago aprobado
- pago rechazado
- cotización de envío lista
- pedido enviado (con guía y foto)
- pedido entregado
- aviso al admin de pedido nuevo pagado

Los envíos de email no deben romper el flujo si el SMTP falla: captura y registra el error.

---

## 10. Seguridad y calidad

- `DEBUG=False` en producción, `ALLOWED_HOSTS` y `CSRF_TRUSTED_ORIGINS` desde variables de entorno, `SECURE_PROXY_SSL_HEADER`, cookies seguras, HSTS y `SECURE_SSL_REDIRECT`.
- Todos los precios, descuentos y totales se calculan **en el servidor**. Nunca se confía en valores enviados por el navegador.
- Validación de archivos subidos (tipo real con Pillow, tamaño máximo y nombres aleatorios).
- Permisos verificados en cada vista del panel y en cada pedido (un cliente nunca puede ver pedidos ajenos; agrega pruebas de esto).
- Logging estructurado de los eventos de Wompi.
- Páginas 404 y 500 personalizadas con el diseño de la tienda.
- SEO: `sitemap.xml`, `robots.txt`, URLs con slug, metadatos por página y datos estructurados `Product` (JSON-LD) en la ficha.
- Formato de moneda colombiano en toda la app: `$1.299.900` (punto de miles, sin decimales). Crea un filtro de plantilla `|cop`.
- Zona horaria `America/Bogota`, idioma `es-co`.

---

## 11. Despliegue en Railway

- Servicio web desde GitHub + plugin **PostgreSQL** de Railway (`DATABASE_URL`).
- **Volumen** de Railway montado en `/app/media`, con `MEDIA_ROOT` leído de una variable de entorno. El volumen solo existe en tiempo de ejecución, no durante el build.
- Servir `/media/` en producción:
  - archivos públicos (productos, categorías, banners) mediante una vista con cabeceras de caché largas
  - evidencias de envío mediante la vista protegida descrita en la sección 3
  - documenta en `DECISIONES.md` que, si el tráfico crece, se puede migrar a un almacenamiento de objetos
- Comando de inicio: `python manage.py migrate --noinput && gunicorn config.wsgi --bind 0.0.0.0:$PORT --workers 3`
- `collectstatic` durante el build.
- `.env.example` con **todas** las variables: `SECRET_KEY`, `DEBUG`, `DATABASE_URL`, `ALLOWED_HOSTS`, `CSRF_TRUSTED_ORIGINS`, `MEDIA_ROOT`, las variables de Wompi, `EMAIL_*`, `ADMIN_URL`, `SITE_URL`.
- En el README: cómo configurar en el panel de Wompi la URL del webhook (`https://<dominio>/pagos/wompi/eventos/`) para sandbox y producción.

---

## 12. Entorno de prueba local compartible con VS Code (Ports / Dev Tunnels)

Además de Railway, el proyecto debe poder ejecutarse **en mi máquina Windows** como entorno de prueba y exponerse con un **enlace público** generado por la pestaña **Ports** de VS Code, para compartirlo con el cliente. Implementa lo siguiente y escribe en el README una sección **"Entorno de prueba compartible"** con el paso a paso exacto (comandos de PowerShell incluidos).

### 12.1 Ajustes en el código
- Archivo de settings `config/settings/tunnel.py` (hereda de `prod` o `base`) que:
  - usa `DEBUG=False` (nunca exponer el modo debug por un enlace público)
  - agrega `.devtunnels.ms` a `ALLOWED_HOSTS` y `https://*.devtunnels.ms` a `CSRF_TRUSTED_ORIGINS`
  - activa `SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")` y `USE_X_FORWARDED_HOST = True`
  - **desactiva** `SECURE_SSL_REDIRECT` y HSTS (el túnel ya entrega HTTPS; si se redirige se produce un bucle)
  - mantiene `SESSION_COOKIE_SECURE` y `CSRF_COOKIE_SECURE` en `True`
  - toma `SITE_URL` de una variable de entorno (la URL del túnel), usada para construir la `redirect-url` de Wompi y los enlaces de los emails
  - usa el backend de email por consola (o SMTP si está configurado)
  - sirve estáticos con `whitenoise` y media con las vistas de la sección 11 (públicas y protegidas)
- Agrega **`waitress`** a `requirements.txt` como servidor para Windows (`gunicorn` no funciona en Windows).
- Script **`scripts/demo.ps1`** que:
  1. activa el entorno virtual
  2. carga las variables desde `.env.tunnel` (crea `.env.tunnel.example` con todas las variables necesarias)
  3. ejecuta `migrate`, `collectstatic --noinput`, `cargar_ubicaciones` y `seed_demo` (idempotentes)
  4. inicia `waitress-serve --listen=127.0.0.1:8000 config.wsgi:application`
  5. imprime en consola las credenciales de prueba y un recordatorio de los pasos en VS Code
- Base de datos local: PostgreSQL recomendado (instalador oficial para Windows o Docker Desktop con `docker run` documentado en el README) para que la búsqueda con trigramas funcione igual que en producción. SQLite queda como respaldo, avisando que la búsqueda es más básica.

### 12.2 Paso a paso que debe quedar en el README
1. Clonar el repo, crear el entorno virtual e instalar dependencias (comandos PowerShell, incluyendo `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned` si hace falta para activar el venv).
2. Copiar `.env.tunnel.example` a `.env.tunnel` y llenarlo (dejar `SITE_URL` para el paso 6).
3. Ejecutar `.\scripts\demo.ps1` y confirmar que `http://127.0.0.1:8000` abre la tienda.
4. En VS Code, abrir el panel inferior → pestaña **Ports** → **Forward a Port** → escribir `8000`. La primera vez pide iniciar sesión con **GitHub o Microsoft**.
5. Clic derecho sobre el puerto → **Port Visibility → Public**. Sin esto, quien abra el enlace tendrá que iniciar sesión con una cuenta. Copiar la **Forwarded Address** (con la forma `https://xxxxx-8000.use2.devtunnels.ms`).
6. Pegar esa URL en `SITE_URL` de `.env.tunnel` y reiniciar el script (Ctrl+C y `.\scripts\demo.ps1`).
7. **Wompi sandbox**: en el panel de comercios de Wompi (modo pruebas), registrar la URL de eventos `https://<url-del-tunel>/pagos/wompi/eventos/`. Usar solo llaves `pub_test_` / `prv_test_`, nunca las de producción. Incluir en el README los datos de prueba de Wompi (tarjetas y escenarios de aprobado/rechazado) tomados de su documentación oficial.
8. Compartir el enlace. Aclarar en el README que:
   - el enlace solo funciona **mientras el PC esté encendido, VS Code abierto y el script corriendo**
   - la primera vez que alguien abre el enlace en el navegador, Microsoft muestra una **página de aviso** del túnel y hay que darle "Continuar"
   - mientras el puerto no se elimine, la URL normalmente se conserva entre sesiones; si cambia, repetir los pasos 6 y 7
   - al terminar la demo, volver el puerto a **Private** o eliminarlo
9. Sección **"Problemas comunes"**: error 400 por `ALLOWED_HOSTS`, error 403 de CSRF, bucle de redirecciones HTTPS, imágenes que no cargan, webhook de Wompi que no llega (revisar visibilidad pública y la URL registrada) y el puerto 8000 ocupado (`netstat -ano | findstr :8000`).

### 12.3 Verificación
Crea el comando `python manage.py check_tunnel` que, con los settings de túnel, verifique que `SITE_URL` esté definida y sea HTTPS, que su host esté permitido en `ALLOWED_HOSTS` y `CSRF_TRUSTED_ORIGINS`, que el volumen de media sea escribible y que las llaves de Wompi sean de prueba. Debe mostrar un resumen claro en español.

---

## 13. Datos iniciales y comandos

- `python manage.py cargar_ubicaciones`: carga el fixture DIVIPOLA.
- `python manage.py seed_demo`: crea la configuración de la tienda, 6 categorías tecnológicas con subcategorías, 5 marcas, 30 productos de ejemplo con imágenes de marcador generadas por Pillow (con especificaciones variadas para probar los filtros), 2 banners, tarifas de envío de ejemplo, un superusuario de prueba y un cliente de prueba. Debe ser **idempotente**.
- `python manage.py wompi_sync`: ver sección 6.

---

## 14. Pruebas mínimas obligatorias

- Cálculo de envío: cada regla y su prioridad.
- Cálculo de precios con descuento por porcentaje, por precio antes y con vigencia por fechas.
- Firma de integridad y verificación del checksum del webhook de Wompi (válido, inválido y monto alterado).
- Idempotencia del webhook (doble evento `APPROVED` → stock descontado una sola vez).
- Máquina de estados del pedido y reglas de foto obligatoria.
- Permisos: un visitante no puede agregar al carrito; un cliente no ve pedidos ajenos ni evidencias ajenas; un no-staff no entra al panel.
- Búsqueda: tolerancia a tildes y errores de escritura (en PostgreSQL).
- Número de consultas acotado en el listado de productos.

---

## 15. Fases de trabajo

1. **Base**: proyecto, settings por entorno (incluido `tunnel`), usuario personalizado, autenticación, diseño base (layout, header, footer, tokens de vidrio), `scripts/demo.ps1` funcionando con el enlace de VS Code Ports, y despliegue inicial en Railway funcionando.
2. **Catálogo**: modelos, imágenes y procesamiento, home, listado, ficha, búsqueda predictiva y filtros.
3. **Carrito y checkout**: carrito, direcciones, ubicaciones de Colombia, cálculo de envío y cotización manual.
4. **Pagos**: Wompi en sandbox de punta a punta (checkout, redirect, webhook y sincronización).
5. **Pedidos y seguimiento**: estados, evidencias, línea de tiempo del cliente y emails.
6. **Panel de administración** completo.
7. **Pulido**: SEO, páginas legales, accesibilidad, rendimiento, pruebas, README y `DECISIONES.md`.

Al final de cada fase: ejecuta las pruebas, revisa que no haya errores en consola ni en `manage.py check --deploy` (en la configuración de producción) y haz commit.

---

## 16. Checklist final (todo debe cumplirse)

- [ ] Un visitante navega, busca y filtra sin cuenta; al agregar al carrito se le pide iniciar sesión y el producto se agrega al volver.
- [ ] La búsqueda sugiere productos y categorías mientras se escribe y tolera tildes y errores de escritura.
- [ ] Los filtros y el ordenamiento funcionan sin recargar la página y la URL se puede compartir.
- [ ] El checkout calcula el envío según la configuración del admin y muestra la regla aplicada.
- [ ] El pago en sandbox de Wompi aprueba el pedido mediante webhook verificado, descuenta stock una sola vez y envía los emails.
- [ ] El admin crea, edita y elimina productos con varias fotos, descuento por porcentaje o precio antes, y los asigna a categorías.
- [ ] El admin cambia el estado del pedido; "Enviado" exige foto y método de entrega (transportadora o personal).
- [ ] El cliente ve la línea de tiempo con las fotos de evidencia de su pedido, y nadie más puede verlas.
- [ ] La cotización manual de envío funciona de punta a punta.
- [ ] Las fotos sobreviven a un redeploy en Railway (volumen) y los datos viven en PostgreSQL.
- [ ] Diseño azul y blanco con efecto vidrio, responsivo, con contraste AA.
- [ ] Todas las pruebas pasan y `manage.py check --deploy` no muestra advertencias críticas.
- [ ] La tienda corre en mi PC con `.\scripts\demo.ps1` y se puede compartir con un enlace público de VS Code Ports: navegación, login, carrito, pago sandbox de Wompi (con webhook) y panel funcionan a través del túnel.
- [ ] README con instalación local en PowerShell, entorno de prueba compartible paso a paso, despliegue en Railway, configuración de Wompi y comandos.

Empieza por la Fase 1. Cuando termines cada fase, resume qué hiciste, qué decisiones tomaste y qué sigue.
