import io

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from PIL import Image


@pytest.fixture(autouse=True)
def _cache_limpia():
    from django.core.cache import cache

    cache.clear()
    yield
    cache.clear()


def imagen_subida(nombre="foto.png", tam=(400, 300), color="#0A66FF", fmt="PNG"):
    buf = io.BytesIO()
    Image.new("RGB", tam, color).save(buf, fmt)
    return SimpleUploadedFile(nombre, buf.getvalue(), content_type=f"image/{fmt.lower()}")


@pytest.fixture
def imagen():
    return imagen_subida


@pytest.fixture
def ubicaciones(db):
    from apps.shipping.models import Departamento, Municipio

    meta = Departamento.objects.create(codigo="50", nombre="Meta")
    amazonas = Departamento.objects.create(codigo="91", nombre="Amazonas")
    vcio = Municipio.objects.create(codigo="50001", nombre="Villavicencio", departamento=meta)
    acacias = Municipio.objects.create(codigo="50006", nombre="Acacías", departamento=meta)
    leticia = Municipio.objects.create(codigo="91001", nombre="Leticia", departamento=amazonas)
    return {"meta": meta, "amazonas": amazonas, "vcio": vcio, "acacias": acacias, "leticia": leticia}


@pytest.fixture
def cliente(db):
    from apps.accounts.models import User

    return User.objects.create_user(
        email="cliente@test.co", password="Clave-segura-123", first_name="Ana", last_name="Pérez",
        telefono="3001112233", numero_documento="123456", acepta_tratamiento_datos=True,
    )


@pytest.fixture
def otro_cliente(db):
    from apps.accounts.models import User

    return User.objects.create_user(email="otro@test.co", password="Clave-segura-123", first_name="Luis", last_name="Gómez")


@pytest.fixture
def staff(db):
    from apps.accounts.models import User

    return User.objects.create_user(
        email="staff@test.co", password="Clave-segura-123", first_name="Sara", last_name="Admin", is_staff=True
    )


@pytest.fixture
def superusuario(db):
    from apps.accounts.models import User

    return User.objects.create_superuser(email="root@test.co", password="Clave-segura-123", first_name="Root", last_name="Admin")


@pytest.fixture
def direccion(cliente, ubicaciones):
    from apps.accounts.models import Address

    return Address.objects.create(
        usuario=cliente, alias="Casa", nombre_recibe="Ana Pérez", telefono="3001112233",
        departamento=ubicaciones["meta"], municipio=ubicaciones["vcio"], direccion="Calle 1 # 2-3",
    )


@pytest.fixture
def catalogo(db):
    """Catálogo pequeño con categorías, marcas y productos variados."""
    from apps.catalog.models import Brand, Category, Product

    cel = Category.objects.create(nombre="Celulares")
    smart = Category.objects.create(nombre="Smartphones", parent=cel)
    comp = Category.objects.create(nombre="Computadores")
    port = Category.objects.create(nombre="Portátiles", parent=comp)
    samsung = Brand.objects.create(nombre="Samsung")
    lenovo = Brand.objects.create(nombre="Lenovo")

    def crear(nombre, sku, precio, cat, marca, stock=10, **kw):
        p = Product.objects.create(nombre=nombre, sku=sku, precio=precio, categoria_principal=cat, marca=marca, stock=stock, **kw)
        p.categorias.set([cat, cat.parent])
        return p

    productos = {
        "s24": crear("Samsung Galaxy S24", "S24", 3000000, smart, samsung, especificaciones={"Color": "Negro", "RAM": "8 GB"},
                     tipo_descuento="porcentaje", descuento_porcentaje=10),
        "a55": crear("Samsung Galaxy A55", "A55", 1800000, smart, samsung, especificaciones={"Color": "Azul", "RAM": "8 GB"}),
        "ideapad": crear("Portátil Lenovo IdeaPad", "IDEA", 2500000, port, lenovo, especificaciones={"Color": "Gris", "RAM": "16 GB"},
                         tipo_descuento="precio_antes", precio_antes=3000000),
        "thinkpad": crear("Lenovo ThinkPad E14", "THINK", 3900000, port, lenovo, stock=0,
                          especificaciones={"Color": "Negro", "RAM": "16 GB"}),
    }
    return {"cats": {"cel": cel, "smart": smart, "comp": comp, "port": port},
            "marcas": {"samsung": samsung, "lenovo": lenovo}, **productos}
