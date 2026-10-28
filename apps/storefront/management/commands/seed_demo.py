"""Datos de demostración. Idempotente: se puede ejecutar varias veces sin duplicar."""
import io
import random
from datetime import timedelta

from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone
from PIL import Image, ImageDraw, ImageFont

from apps.accounts.models import Address, User
from apps.catalog.models import Brand, Category, Product, ProductImage
from apps.shipping.models import Departamento, Municipio, ShippingSettings, ShippingZoneRate
from apps.storefront.models import Banner, StoreSettings

ADMIN_EMAIL, ADMIN_PASS = "admin@globaltecnology.co", "Admin12345!"
CLIENTE_EMAIL, CLIENTE_PASS = "cliente@globaltecnology.co", "Cliente12345!"

PALETAS = [
    ("#0A66FF", "#0B3D91"), ("#3B82F6", "#1E3A8A"), ("#0EA5E9", "#0B3D91"),
    ("#6366F1", "#312E81"), ("#14B8A6", "#0B3D91"), ("#2563EB", "#172554"),
]

CATEGORIAS = [
    ("Celulares", "Smartphones y accesorios móviles", ["Smartphones", "Accesorios para celular"]),
    ("Computadores", "Portátiles, monitores y periféricos", ["Portátiles", "Monitores"]),
    ("Audio", "Audífonos y parlantes", ["Audífonos", "Parlantes"]),
    ("Gaming", "Consolas, controles y accesorios gamer", ["Consolas", "Controles"]),
    ("Hogar inteligente", "Iluminación, cámaras y asistentes", ["Iluminación", "Cámaras de seguridad"]),
    ("Accesorios", "Cargadores, cables y almacenamiento", ["Cargadores", "Almacenamiento"]),
]
MARCAS = ["Samsung", "Apple", "Lenovo", "Sony", "Xiaomi"]

# (nombre, sku, marca, subcategoría, precio, descuento, stock, especificaciones, flags)
PRODUCTOS = [
    ("Samsung Galaxy S24 128 GB", "GT-CEL-001", "Samsung", "Smartphones", 3299900, ("porcentaje", 12), 15, {"Color": "Negro", "RAM": "8 GB", "Almacenamiento": "128 GB", "Pantalla": "6,2 pulgadas"}, "destacado"),
    ("Samsung Galaxy A55 5G 256 GB", "GT-CEL-002", "Samsung", "Smartphones", 1899900, ("precio_antes", 2199900), 22, {"Color": "Azul", "RAM": "8 GB", "Almacenamiento": "256 GB", "Pantalla": "6,6 pulgadas"}, "nuevo"),
    ("iPhone 15 128 GB", "GT-CEL-003", "Apple", "Smartphones", 4299900, None, 8, {"Color": "Negro", "RAM": "6 GB", "Almacenamiento": "128 GB", "Pantalla": "6,1 pulgadas"}, "destacado"),
    ("iPhone 15 Pro 256 GB", "GT-CEL-004", "Apple", "Smartphones", 6199900, ("porcentaje", 8), 3, {"Color": "Titanio natural", "RAM": "8 GB", "Almacenamiento": "256 GB", "Pantalla": "6,1 pulgadas"}, "destacado"),
    ("Xiaomi Redmi Note 13 Pro 256 GB", "GT-CEL-005", "Xiaomi", "Smartphones", 1449900, ("porcentaje", 15), 30, {"Color": "Morado", "RAM": "8 GB", "Almacenamiento": "256 GB", "Pantalla": "6,67 pulgadas"}, "nuevo"),
    ("Xiaomi Redmi 13C 128 GB", "GT-CEL-006", "Xiaomi", "Smartphones", 599900, None, 40, {"Color": "Azul", "RAM": "4 GB", "Almacenamiento": "128 GB", "Pantalla": "6,74 pulgadas"}, ""),
    ("Cargador rápido Samsung 25 W USB-C", "GT-ACC-007", "Samsung", "Cargadores", 89900, ("precio_antes", 119900), 50, {"Color": "Blanco", "Potencia": "25 W", "Conector": "USB-C"}, ""),
    ("Cable Apple USB-C a Lightning 1 m", "GT-ACC-008", "Apple", "Cargadores", 119900, None, 25, {"Color": "Blanco", "Longitud": "1 m", "Conector": "Lightning"}, ""),
    ("Lenovo IdeaPad Slim 3 Ryzen 7 16 GB", "GT-COM-009", "Lenovo", "Portátiles", 3199900, ("porcentaje", 18), 10, {"Color": "Gris", "RAM": "16 GB", "Almacenamiento": "512 GB SSD", "Procesador": "AMD Ryzen 7", "Pantalla": "15,6 pulgadas"}, "destacado"),
    ("Lenovo ThinkPad E14 Core i5", "GT-COM-010", "Lenovo", "Portátiles", 3899900, None, 6, {"Color": "Negro", "RAM": "16 GB", "Almacenamiento": "512 GB SSD", "Procesador": "Intel Core i5", "Pantalla": "14 pulgadas"}, ""),
    ("MacBook Air 13 M3 8 GB", "GT-COM-011", "Apple", "Portátiles", 5799900, ("precio_antes", 6499900), 4, {"Color": "Medianoche", "RAM": "8 GB", "Almacenamiento": "256 GB SSD", "Procesador": "Apple M3", "Pantalla": "13,6 pulgadas"}, "destacado,nuevo"),
    ("Lenovo IdeaPad Gaming 3 RTX 4050", "GT-COM-012", "Lenovo", "Portátiles", 4599900, ("porcentaje", 10), 5, {"Color": "Negro", "RAM": "16 GB", "Almacenamiento": "1 TB SSD", "Procesador": "AMD Ryzen 7", "Pantalla": "15,6 pulgadas"}, ""),
    ("Monitor Samsung Odyssey G5 27\" 165 Hz", "GT-COM-013", "Samsung", "Monitores", 1299900, ("porcentaje", 20), 9, {"Pantalla": "27 pulgadas", "Resolución": "2K QHD", "Frecuencia": "165 Hz", "Color": "Negro"}, ""),
    ("Monitor Lenovo L24i 24\" Full HD", "GT-COM-014", "Lenovo", "Monitores", 649900, None, 14, {"Pantalla": "24 pulgadas", "Resolución": "Full HD", "Frecuencia": "100 Hz", "Color": "Gris"}, ""),
    ("Sony WH-1000XM5 inalámbricos", "GT-AUD-015", "Sony", "Audífonos", 1699900, ("porcentaje", 15), 12, {"Color": "Negro", "Conectividad": "Bluetooth 5.2", "Cancelación de ruido": "Sí", "Batería": "30 horas"}, "destacado"),
    ("AirPods Pro (2.ª generación)", "GT-AUD-016", "Apple", "Audífonos", 1199900, None, 18, {"Color": "Blanco", "Conectividad": "Bluetooth 5.3", "Cancelación de ruido": "Sí", "Batería": "6 horas"}, "nuevo"),
    ("Samsung Galaxy Buds3 Pro", "GT-AUD-017", "Samsung", "Audífonos", 999900, ("precio_antes", 1149900), 2, {"Color": "Plata", "Conectividad": "Bluetooth 5.4", "Cancelación de ruido": "Sí", "Batería": "6 horas"}, "nuevo"),
    ("Xiaomi Redmi Buds 5", "GT-AUD-018", "Xiaomi", "Audífonos", 189900, None, 35, {"Color": "Negro", "Conectividad": "Bluetooth 5.3", "Cancelación de ruido": "Sí", "Batería": "10 horas"}, ""),
    ("Parlante Sony SRS-XB100", "GT-AUD-019", "Sony", "Parlantes", 279900, ("porcentaje", 25), 20, {"Color": "Azul", "Conectividad": "Bluetooth 5.3", "Resistencia": "IP67", "Batería": "16 horas"}, ""),
    ("Parlante Xiaomi Sound Outdoor 30 W", "GT-AUD-020", "Xiaomi", "Parlantes", 329900, None, 0, {"Color": "Negro", "Conectividad": "Bluetooth 5.4", "Resistencia": "IP67", "Batería": "12 horas"}, ""),
    ("PlayStation 5 Slim 1 TB", "GT-GAM-021", "Sony", "Consolas", 2899900, ("precio_antes", 3199900), 7, {"Color": "Blanco", "Almacenamiento": "1 TB", "Resolución": "4K"}, "destacado"),
    ("Control DualSense PS5", "GT-GAM-022", "Sony", "Controles", 349900, ("porcentaje", 10), 25, {"Color": "Blanco", "Conectividad": "Bluetooth"}, ""),
    ("Control DualSense Edge PS5", "GT-GAM-023", "Sony", "Controles", 899900, None, 4, {"Color": "Negro", "Conectividad": "Bluetooth"}, "nuevo"),
    ("Lenovo Legion Go 512 GB", "GT-GAM-024", "Lenovo", "Consolas", 3799900, ("porcentaje", 12), 3, {"Color": "Negro", "RAM": "16 GB", "Almacenamiento": "512 GB", "Pantalla": "8,8 pulgadas"}, ""),
    ("Bombillo inteligente Xiaomi Smart LED", "GT-HOG-025", "Xiaomi", "Iluminación", 69900, None, 60, {"Color": "Multicolor", "Conectividad": "Wi-Fi", "Potencia": "9 W"}, ""),
    ("Tira LED Xiaomi Lightstrip 2 m", "GT-HOG-026", "Xiaomi", "Iluminación", 159900, ("porcentaje", 20), 15, {"Color": "Multicolor", "Conectividad": "Wi-Fi", "Longitud": "2 m"}, ""),
    ("Cámara de seguridad Xiaomi C400 2.5K", "GT-HOG-027", "Xiaomi", "Cámaras de seguridad", 229900, ("precio_antes", 279900), 11, {"Color": "Blanco", "Conectividad": "Wi-Fi", "Resolución": "2.5K"}, "nuevo"),
    ("Cámara Samsung SmartThings Vision", "GT-HOG-028", "Samsung", "Cámaras de seguridad", 389900, None, 6, {"Color": "Negro", "Conectividad": "Wi-Fi", "Resolución": "Full HD"}, ""),
    ("Memoria USB Samsung BAR Plus 256 GB", "GT-ACC-029", "Samsung", "Almacenamiento", 129900, ("porcentaje", 15), 45, {"Color": "Plata", "Almacenamiento": "256 GB", "Conector": "USB-A"}, ""),
    ("Disco SSD Samsung T7 1 TB", "GT-ACC-030", "Samsung", "Almacenamiento", 549900, ("precio_antes", 649900), 13, {"Color": "Azul", "Almacenamiento": "1 TB", "Conector": "USB-C"}, "destacado"),
]

TARIFAS = [
    # (código depto, código municipio o None, valor, días)
    ("50", None, 12000, "2-3"),
    ("50", "50001", 8000, "1-2"),      # Villavicencio
    ("11", None, 10000, "1-3"),        # Bogotá D.C.
    ("25", None, 13000, "2-4"),        # Cundinamarca
    ("05", None, 15000, "2-5"),        # Antioquia
    ("05", "05001", 12000, "2-3"),     # Medellín
    ("76", "76001", 14000, "2-4"),     # Cali
    ("08", "08001", 16000, "3-5"),     # Barranquilla
]


def _fuente(tam):
    try:
        return ImageFont.load_default(size=tam)
    except TypeError:  # Pillow sin FreeType
        return ImageFont.load_default()


def _degradado(w, h, c1, c2):
    img = Image.new("RGB", (w, h), c1)
    top = Image.new("RGB", (w, h), c2)
    mask = Image.linear_gradient("L").resize((w, h))
    return Image.composite(top, img, mask)


def imagen_producto(nombre, idx, tam=1200):
    c1, c2 = PALETAS[idx % len(PALETAS)]
    img = Image.new("RGB", (tam, tam), "#F4F8FF")
    d = ImageDraw.Draw(img)
    fondo = _degradado(tam - 240, tam - 240, c1, c2)
    mask = Image.new("L", fondo.size, 0)
    ImageDraw.Draw(mask).rounded_rectangle([0, 0, *fondo.size], radius=120, fill=255)
    img.paste(fondo, (120, 120), mask)
    d.ellipse([tam * 0.55, tam * 0.15, tam * 0.85, tam * 0.45], fill="#FFFFFF30" if False else "#5B95FF")
    d.rounded_rectangle([tam * 0.3, tam * 0.3, tam * 0.7, tam * 0.62], radius=40, outline="#FFFFFF", width=10)
    iniciales = "".join(p[0] for p in nombre.split()[:2]).upper()
    f = _fuente(160)
    d.text((tam / 2, tam * 0.46), iniciales, fill="#FFFFFF", font=f, anchor="mm")
    f2 = _fuente(46)
    texto = nombre if len(nombre) < 34 else nombre[:32] + "…"
    d.text((tam / 2, tam * 0.75), texto, fill="#FFFFFF", font=f2, anchor="mm")
    return img


def imagen_categoria(nombre, idx):
    c1, c2 = PALETAS[idx % len(PALETAS)]
    img = _degradado(800, 800, c1, c2)
    d = ImageDraw.Draw(img)
    d.ellipse([480, -80, 900, 340], fill="#7FB0FF")
    d.text((400, 420), nombre, fill="#FFFFFF", font=_fuente(64), anchor="mm")
    return img


def imagen_banner(titulo, w, h, idx):
    c1, c2 = PALETAS[idx % len(PALETAS)]
    img = _degradado(w, h, c2, c1)
    d = ImageDraw.Draw(img)
    d.ellipse([w * 0.6, -h * 0.3, w * 1.1, h * 0.9], fill="#5B95FF")
    d.ellipse([w * 0.72, h * 0.35, w * 0.95, h * 1.2], fill="#9CC2FF")
    d.text((w * 0.78, h * 0.5), "GT", fill="#FFFFFF", font=_fuente(int(h * 0.25)), anchor="mm")
    return img


def subida(img, nombre="img.png"):
    buf = io.BytesIO()
    img.save(buf, "PNG")
    return SimpleUploadedFile(nombre, buf.getvalue(), content_type="image/png")


class Command(BaseCommand):
    help = "Crea datos de demostración (tienda, categorías, marcas, 30 productos, banners, tarifas y usuarios). Idempotente."

    def add_arguments(self, parser):
        parser.add_argument("--sin-imagenes", action="store_true", help="No generar imágenes (más rápido)")

    @transaction.atomic
    def handle(self, *args, sin_imagenes=False, **opts):
        random.seed(42)
        if not Departamento.objects.exists():
            call_command("cargar_ubicaciones")

        tienda = StoreSettings.load()
        if not tienda.whatsapp:
            tienda.whatsapp = "573001234567"
            tienda.telefono = "+57 300 123 4567"
            tienda.direccion = "Villavicencio, Meta, Colombia"
            tienda.instagram = "https://instagram.com/globaltecnology"
            tienda.facebook = "https://facebook.com/globaltecnology"
            tienda.save()

        cats = {}
        for i, (nombre, desc, hijas) in enumerate(CATEGORIAS):
            c, creada = Category.objects.get_or_create(nombre=nombre, parent=None, defaults={"descripcion": desc, "orden": i})
            if not c.imagen and not sin_imagenes:
                c.imagen = subida(imagen_categoria(nombre, i))
                c.save()
            cats[nombre] = c
            for j, h in enumerate(hijas):
                cats[h], _ = Category.objects.get_or_create(nombre=h, parent=c, defaults={"orden": j})

        marcas = {n: Brand.objects.get_or_create(nombre=n)[0] for n in MARCAS}

        ahora = timezone.now()
        creados = 0
        for idx, (nombre, sku, marca, sub, precio, desc, stock, specs, flags) in enumerate(PRODUCTOS):
            sub_cat = cats[sub]
            p, creado = Product.objects.get_or_create(sku=sku, defaults={
                "nombre": nombre, "marca": marcas[marca], "categoria_principal": sub_cat, "precio": precio,
                "stock": stock, "especificaciones": specs,
                "descripcion_corta": f"{nombre} con garantía oficial y envío a toda Colombia.",
                "descripcion": (
                    f"<p><strong>{nombre}</strong> de {marca}. Producto original, nuevo y sellado, con garantía de fabricante.</p>"
                    "<ul><li>Envío asegurado a todo el país</li><li>Pago seguro con Wompi</li><li>Soporte por WhatsApp</li></ul>"
                ),
                "destacado": "destacado" in flags, "nuevo": "nuevo" in flags,
            })
            if creado:
                creados += 1
                if desc:
                    p.tipo_descuento = desc[0]
                    if desc[0] == "porcentaje":
                        p.descuento_porcentaje = desc[1]
                    else:
                        p.precio_antes = desc[1]
                    if idx % 7 == 0:  # algunos con vigencia por fechas
                        p.descuento_inicia = ahora - timedelta(days=1)
                        p.descuento_termina = ahora + timedelta(days=30)
                    p.save()
                p.categorias.set([sub_cat, sub_cat.parent])
            if not sin_imagenes and not p.imagenes.exists():
                for k in range(2 if idx % 3 == 0 else 1):
                    ProductImage.objects.create(
                        producto=p, imagen=subida(imagen_producto(nombre, idx + k * 2)), es_principal=(k == 0), orden=k,
                        texto_alternativo=f"{nombre}{' (vista ' + str(k + 1) + ')' if k else ''}",
                    )

        if not Banner.objects.exists():
            for i, (titulo, sub, enlace) in enumerate([
                ("Ofertas en tecnología", "Hasta 25 % de descuento en celulares, audio y gaming.", "/ofertas/"),
                ("Lo más nuevo en portátiles", "Equipos para estudiar, trabajar y jugar. Envío a toda Colombia.", "/categoria/portatiles/"),
            ]):
                Banner.objects.create(
                    titulo=titulo, subtitulo=sub, enlace=enlace, orden=i, texto_boton="Ver ofertas" if i == 0 else "Ver portátiles",
                    imagen_escritorio=subida(imagen_banner(titulo, 2000, 750, i + 1)),
                    imagen_movil=subida(imagen_banner(titulo, 1000, 1250, i + 1)),
                )

        cfg = ShippingSettings.load()
        cfg.save()
        for dep, mun, valor, dias in TARIFAS:
            d = Departamento.objects.get(codigo=dep)
            m = Municipio.objects.get(codigo=mun) if mun else None
            ShippingZoneRate.objects.get_or_create(departamento=d, municipio=m, defaults={"valor": valor, "dias_estimados": dias})

        admin, creado = User.objects.get_or_create(email=ADMIN_EMAIL, defaults={
            "first_name": "Admin", "last_name": "GlobalTecnology", "is_staff": True, "is_superuser": True,
            "acepta_tratamiento_datos": True, "telefono": "3001234567",
        })
        if creado:
            admin.set_password(ADMIN_PASS)
            admin.save()
        cliente, creado = User.objects.get_or_create(email=CLIENTE_EMAIL, defaults={
            "first_name": "Camila", "last_name": "Rojas", "telefono": "3109876543", "tipo_documento": "CC",
            "numero_documento": "1121000000", "acepta_tratamiento_datos": True,
        })
        if creado:
            cliente.set_password(CLIENTE_PASS)
            cliente.save()
        if not cliente.direcciones.exists():
            vcio = Municipio.objects.get(codigo="50001")
            Address.objects.create(
                usuario=cliente, alias="Casa", nombre_recibe="Camila Rojas", telefono="3109876543",
                departamento=vcio.departamento, municipio=vcio, direccion="Calle 15 # 40-21", barrio="Barzal",
                indicaciones="Portería, apto 302", es_predeterminada=True,
            )
            leticia = Municipio.objects.get(codigo="91001")
            Address.objects.create(
                usuario=cliente, alias="Oficina (cotización)", nombre_recibe="Camila Rojas", telefono="3109876543",
                departamento=leticia.departamento, municipio=leticia, direccion="Carrera 10 # 8-30",
            )

        self.stdout.write(self.style.SUCCESS(
            f"Demo lista: {Category.objects.count()} categorías, {Brand.objects.count()} marcas, "
            f"{Product.objects.count()} productos ({creados} nuevos), {Banner.objects.count()} banners."
        ))
        self.stdout.write(f"  Admin:   {ADMIN_EMAIL} / {ADMIN_PASS}")
        self.stdout.write(f"  Cliente: {CLIENTE_EMAIL} / {CLIENTE_PASS}")
