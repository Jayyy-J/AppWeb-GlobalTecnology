from datetime import timedelta

import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.utils import timezone

from apps.catalog.models import Product, ProductImage, SearchLog

pytestmark = pytest.mark.django_db
es_postgres = pytest.mark.skipif(connection.vendor != "postgresql", reason="Requiere PostgreSQL")


# ---------- Precios ----------
def test_precio_sin_descuento():
    p = Product(nombre="X", sku="X", precio=100000)
    assert p.precio_final == 100000 and not p.tiene_descuento and p.porcentaje_ahorro == 0 and p.precio_tachado is None


def test_precio_descuento_porcentaje_redondeado():
    p = Product(nombre="X", sku="X", precio=99999, tipo_descuento="porcentaje", descuento_porcentaje=15)
    # 99999 * 0.85 = 84999.15 → 84999
    assert p.precio_final == 84999
    assert p.precio_tachado == 99999 and p.porcentaje_ahorro == 15 and p.ahorro == 15000
    p.precio = 3
    p.descuento_porcentaje = 50  # 1.5 → 2 (redondeo a pesos, mitad hacia arriba)
    assert p.precio_final == 2


def test_precio_antes_calcula_porcentaje():
    p = Product(nombre="X", sku="X", precio=2500000, tipo_descuento="precio_antes", precio_antes=3000000)
    assert p.precio_final == 2500000
    assert p.precio_tachado == 3000000
    assert p.porcentaje_ahorro == 17  # 16,67 % → 17
    assert p.ahorro == 500000


def test_precio_antes_menor_no_es_descuento():
    p = Product(nombre="X", sku="X", precio=100, tipo_descuento="precio_antes", precio_antes=90)
    assert not p.tiene_descuento and p.precio_final == 100


def test_descuento_con_vigencia():
    ahora = timezone.now()
    p = Product(nombre="X", sku="X", precio=100000, tipo_descuento="porcentaje", descuento_porcentaje=20)
    p.descuento_inicia = ahora + timedelta(days=1)
    assert not p.tiene_descuento and p.precio_final == 100000
    p.descuento_inicia = ahora - timedelta(days=2)
    p.descuento_termina = ahora - timedelta(days=1)
    assert not p.tiene_descuento and p.precio_final == 100000
    p.descuento_termina = ahora + timedelta(days=1)
    assert p.tiene_descuento and p.precio_final == 80000


def test_validacion_descuentos():
    from django.core.exceptions import ValidationError

    with pytest.raises(ValidationError):
        Product(nombre="X", sku="X", precio=100, tipo_descuento="porcentaje", descuento_porcentaje=95).full_clean()
    with pytest.raises(ValidationError):
        Product(nombre="X", sku="X", precio=100, tipo_descuento="precio_antes", precio_antes=50).full_clean()


def test_anotaciones_bd_coinciden_con_python(catalogo):
    for p in Product.objects.con_precios():
        assert p.precio_final_db == p.precio_final, p.nombre
        assert p.descuento_pct_db == p.porcentaje_ahorro, p.nombre


# ---------- Imágenes ----------
def test_imagen_se_convierte_a_webp_en_tres_tamanos(catalogo, imagen):
    im = ProductImage.objects.create(producto=catalogo["s24"], imagen=imagen("foto.jpg", (2400, 1800), fmt="JPEG"))
    assert im.imagen.name.endswith(".webp") and im.imagen_media.name.endswith(".webp") and im.imagen_thumb.name.endswith(".webp")
    from PIL import Image

    assert max(Image.open(im.imagen.path).size) == 1600
    assert max(Image.open(im.imagen_media.path).size) == 800
    assert max(Image.open(im.imagen_thumb.path).size) == 300
    assert "foto" not in im.imagen.name  # nombre aleatorio
    assert im.es_principal is False
    im2 = ProductImage.objects.create(producto=catalogo["s24"], imagen=imagen(), es_principal=True)
    assert catalogo["s24"].imagen_principal == im2


# ---------- Listado, filtros y consultas ----------
def test_listado_numero_de_consultas_acotado(client, catalogo, imagen):
    for p in Product.objects.all():
        ProductImage.objects.create(producto=p, imagen=imagen())
    client.get("/productos/")  # calienta cachés (menú, configuración)
    with CaptureQueriesContext(connection) as ctx:
        r = client.get("/productos/")
    assert r.status_code == 200
    n = len(ctx.captured_queries)
    # Agregar más productos no debe aumentar las consultas (sin N+1)
    for i in range(10):
        p = Product.objects.create(nombre=f"Extra {i}", sku=f"EXT{i}", precio=1000, stock=1)
        ProductImage.objects.create(producto=p, imagen=imagen())
    client.get("/productos/")
    with CaptureQueriesContext(connection) as ctx2:
        client.get("/productos/")
    assert len(ctx2.captured_queries) == n
    assert n <= 15, [q["sql"][:120] for q in ctx.captured_queries]


def test_filtros_marca_precio_descuento_y_especificaciones(client, catalogo):
    def nombres(url):
        r = client.get(url)
        assert r.status_code == 200
        return {p.nombre for p in r.context["productos"]}

    assert nombres("/productos/?marca=lenovo") == {"Portátil Lenovo IdeaPad", "Lenovo ThinkPad E14"}
    assert nombres("/productos/?descuento=1") == {"Samsung Galaxy S24", "Portátil Lenovo IdeaPad"}
    assert nombres("/productos/?disponible=1&marca=lenovo") == {"Portátil Lenovo IdeaPad"}
    assert nombres("/productos/?min=2600000&max=3000000") == {"Samsung Galaxy S24"}  # 2.700.000 con descuento
    assert nombres("/productos/?esp=Color:Negro") == {"Samsung Galaxy S24", "Lenovo ThinkPad E14"}
    assert nombres("/productos/?esp=Color:Negro&esp=Color:Azul&esp=RAM:8 GB") == {"Samsung Galaxy S24", "Samsung Galaxy A55"}
    assert nombres("/categoria/computadores/?sub=portatiles") == {"Portátil Lenovo IdeaPad", "Lenovo ThinkPad E14"}


def test_ordenamiento(client, catalogo):
    r = client.get("/productos/?orden=precio_asc")
    precios = [p.precio_final for p in r.context["productos"]]
    assert precios == sorted(precios)
    r = client.get("/productos/?orden=descuento")
    assert r.context["productos"][0].nombre == "Portátil Lenovo IdeaPad"  # 17 % > 10 %


def test_facetas_dinamicas_y_chips(client, catalogo):
    r = client.get("/productos/?marca=samsung")
    claves = {e["clave"] for e in r.context["facetas"]["especificaciones"]}
    assert "Color" in claves
    assert any("Samsung" == c["texto"] for c in r.context["chips"])


def test_listado_parcial_htmx(client, catalogo):
    r = client.get("/productos/?marca=samsung", HTTP_HX_REQUEST="true", HTTP_HX_TARGET="zona-listado")
    html = r.content.decode()
    assert "<html" not in html and "Galaxy" in html


def test_ficha_producto_json_ld_y_inactivo(client, catalogo):
    r = client.get(catalogo["s24"].get_absolute_url())
    html = r.content.decode()
    assert '"@type": "Product"' in html and '"priceCurrency": "COP"' in html and "$2.700.000" in html
    catalogo["a55"].activo = False
    catalogo["a55"].save()
    assert client.get(catalogo["a55"].get_absolute_url()).status_code == 404


def test_descripcion_se_sanea(catalogo):
    p = catalogo["s24"]
    p.descripcion = '<p onclick="x()">Hola</p><script>alert(1)</script><a href="javascript:x">y</a>'
    p.save()
    assert "<script" not in p.descripcion and "onclick" not in p.descripcion and "javascript:" not in p.descripcion


# ---------- Búsqueda ----------
def test_busqueda_registra_searchlog(client, catalogo):
    client.get("/buscar/?q=Galaxy")
    client.get("/buscar/?q=galaxy")
    log = SearchLog.objects.get(termino="galaxy")
    assert log.cantidad_busquedas == 2 and log.cantidad_resultados == 2


def test_sugerencias_resaltadas(client, catalogo):
    r = client.get("/buscar/sugerencias/?q=gal")
    html = r.content.decode()
    assert "<mark>Gal</mark>axy" in html
    assert client.get("/buscar/sugerencias/?q=g").content.decode().strip() == ""


def test_busqueda_sin_resultados_quisiste_decir(client, catalogo):
    r = client.get("/buscar/?q=lenovoo")
    if r.context["total"] == 0:
        assert r.context["quisiste_decir"] == "lenovo"
    r = client.get("/buscar/?q=zzzzqqq")
    assert r.context["total"] == 0 and "sugeridos" in r.context


def test_busqueda_tolerante_a_tildes(client, catalogo):
    # "portatil" sin tilde encuentra "Portátil" (también en SQLite gracias al texto normalizado)
    r = client.get("/buscar/?q=portatil")
    assert "Portátil Lenovo IdeaPad" in {p.nombre for p in r.context["productos"]}
    r = client.get("/buscar/?q=PORTÁTIL lenovo")
    assert r.context["total"] >= 1


@es_postgres
def test_busqueda_tolerante_a_errores_postgres(client, catalogo):
    for q in ["samsumg", "galaxi", "tinkpad", "lenvo"]:
        r = client.get(f"/buscar/?q={q}")
        assert r.context["total"] >= 1, q
    r = client.get("/buscar/?q=samsumg")
    assert {p.marca.nombre for p in r.context["productos"]} == {"Samsung"}


@es_postgres
def test_busqueda_relevancia_postgres(client, catalogo):
    r = client.get("/buscar/?q=thinkpad")
    assert r.context["productos"][0].nombre == "Lenovo ThinkPad E14"


@es_postgres
def test_extensiones_instaladas():
    with connection.cursor() as c:
        c.execute("SELECT extname FROM pg_extension")
        ext = {r[0] for r in c.fetchall()}
    assert {"pg_trgm", "unaccent"} <= ext
