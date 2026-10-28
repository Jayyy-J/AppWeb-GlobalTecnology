from types import SimpleNamespace

import pytest
from django.urls import reverse

from apps.cart import services as cart
from apps.cart.models import CartItem
from apps.orders.models import Order
from apps.shipping.models import ShippingSettings, ShippingZoneRate
from apps.shipping.services import (COTIZACION, DEPARTAMENTO, FIJA, GRATIS, MUNICIPIO, SIN_COBERTURA, Tarifa,
                                    calcular_envio, cotizar_envio)


def cfg(**kw):
    base = dict(envio_gratis_activo=True, envio_gratis_desde=200000, tarifas_por_zona_activas=True,
                tarifa_fija_activa=True, tarifa_fija_valor=15000, cotizacion_manual_activa=True)
    base.update(kw)
    return SimpleNamespace(**base)


# ---------- Función pura: cada regla y su prioridad ----------
def test_regla_1_envio_gratis_tiene_maxima_prioridad():
    q = calcular_envio(250000, cfg(), "Villavicencio", "Meta", Tarifa(8000), Tarifa(12000))
    assert q.codigo == GRATIS and q.valor == 0 and "$200.000" in q.regla


def test_envio_gratis_justo_en_el_minimo():
    assert calcular_envio(200000, cfg()).codigo == GRATIS


def test_envio_gratis_inactivo_no_aplica():
    q = calcular_envio(900000, cfg(envio_gratis_activo=False), "Villavicencio", "Meta", Tarifa(8000))
    assert q.codigo == MUNICIPIO


def test_regla_2_municipio_sobre_departamento():
    q = calcular_envio(100000, cfg(), "Villavicencio", "Meta", Tarifa(8000, "1-2"), Tarifa(12000))
    assert q.codigo == MUNICIPIO and q.valor == 8000 and q.regla == "Envío a Villavicencio: $8.000" and q.dias == "1-2"


def test_regla_3_departamento():
    q = calcular_envio(100000, cfg(), "Acacías", "Meta", None, Tarifa(12000))
    assert q.codigo == DEPARTAMENTO and q.valor == 12000 and "Meta" in q.regla


def test_zonas_inactivas_ignoran_tarifas():
    q = calcular_envio(100000, cfg(tarifas_por_zona_activas=False), "Acacías", "Meta", Tarifa(1), Tarifa(2))
    assert q.codigo == FIJA


def test_regla_4_tarifa_fija():
    q = calcular_envio(100000, cfg(), "Leticia", "Amazonas")
    assert q.codigo == FIJA and q.valor == 15000


def test_regla_5_cotizacion_manual():
    q = calcular_envio(100000, cfg(tarifa_fija_activa=False), "Leticia", "Amazonas")
    assert q.codigo == COTIZACION and q.valor is None and q.requiere_cotizacion and q.disponible


def test_regla_6_sin_cobertura_bloquea():
    q = calcular_envio(100000, cfg(tarifa_fija_activa=False, cotizacion_manual_activa=False), "Leticia", "Amazonas")
    assert q.codigo == SIN_COBERTURA and not q.disponible and "Leticia" in q.regla


@pytest.mark.django_db
def test_cotizar_envio_lee_tarifas_de_bd(ubicaciones):
    c = ShippingSettings.load()
    c.tarifa_fija_activa = False
    c.save()
    ShippingZoneRate.objects.create(departamento=ubicaciones["meta"], valor=12000)
    ShippingZoneRate.objects.create(departamento=ubicaciones["meta"], municipio=ubicaciones["vcio"], valor=8000)
    ShippingZoneRate.objects.create(departamento=ubicaciones["amazonas"], valor=1, activo=False)
    assert cotizar_envio(10000, ubicaciones["vcio"]).valor == 8000
    assert cotizar_envio(10000, ubicaciones["acacias"]).valor == 12000
    assert cotizar_envio(10000, ubicaciones["leticia"]).codigo == COTIZACION  # tarifa inactiva


# ---------- Carrito ----------
pytestmark_db = pytest.mark.django_db


@pytest.mark.django_db
def test_visitante_no_puede_agregar_al_carrito(client, catalogo):
    r = client.post(reverse("cart:agregar", args=[catalogo["s24"].pk]), {"cantidad": 1})
    assert r.status_code == 302 and "/cuenta/ingresar/" in r.url
    assert CartItem.objects.count() == 0
    r = client.post(reverse("cart:agregar", args=[catalogo["s24"].pk]), {"cantidad": 1}, HTTP_HX_REQUEST="true")
    assert r.status_code == 204 and "/cuenta/ingresar/" in r["HX-Redirect"]
    assert client.get(reverse("cart:detalle")).status_code == 302


@pytest.mark.django_db
def test_agregar_tras_login_completa_la_accion(client, catalogo, cliente):
    r = client.post(reverse("cart:agregar", args=[catalogo["s24"].pk]), {"cantidad": 2, "volver": "/productos/"})
    login_url = r.url
    nxt = login_url.split("next=")[1]
    from urllib.parse import unquote

    r = client.post(login_url, {"username": cliente.email, "password": "Clave-segura-123", "next": unquote(nxt)})
    assert r.status_code == 302 and "agregar-pendiente" in r.url
    r = client.get(r.url)
    assert r.status_code == 302 and r.url == "/productos/"
    assert CartItem.objects.get(carrito__usuario=cliente).cantidad == 2


@pytest.mark.django_db
def test_token_pendiente_manipulado_es_rechazado(client, cliente, catalogo):
    client.force_login(cliente)
    r = client.get(reverse("cart:pendiente", args=["token-falso:abc"]))
    assert r.status_code == 302 and CartItem.objects.count() == 0


@pytest.mark.django_db
def test_carrito_limita_al_stock_y_recalcula_precio(client, cliente, catalogo):
    client.force_login(cliente)
    p = catalogo["a55"]
    client.post(reverse("cart:agregar", args=[p.pk]), {"cantidad": 50})
    assert CartItem.objects.get().cantidad == p.stock
    p.precio = 1000000
    p.save()
    res = cart.resumen(cliente)
    assert res.subtotal == 1000000 * p.stock  # siempre el precio actual
    assert client.post(reverse("cart:agregar", args=[catalogo["thinkpad"].pk])).status_code == 302  # agotado
    assert CartItem.objects.count() == 1


@pytest.mark.django_db
def test_actualizar_y_eliminar_htmx(client, cliente, catalogo, otro_cliente):
    client.force_login(cliente)
    client.post(reverse("cart:agregar", args=[catalogo["a55"].pk]))
    item = CartItem.objects.get()
    r = client.post(reverse("cart:actualizar", args=[item.pk]), {"accion": "mas"}, HTTP_HX_REQUEST="true")
    assert r.status_code == 200 and "carrito-actualizado" in r["HX-Trigger"]
    item.refresh_from_db()
    assert item.cantidad == 2
    # otro usuario no puede tocar este item
    client.force_login(otro_cliente)
    assert client.post(reverse("cart:actualizar", args=[item.pk]), {"accion": "mas"}).status_code == 404
    client.force_login(cliente)
    client.post(reverse("cart:eliminar", args=[item.pk]))
    assert CartItem.objects.count() == 0


# ---------- Checkout ----------
def _datos_checkout(direccion="", **extra):
    d = {"direccion": direccion, "first_name": "Ana", "last_name": "Pérez", "email": "ana@test.co",
         "telefono": "3001112233", "tipo_documento": "CC", "numero_documento": "1234567", "acepta_terminos": "on"}
    d.update(extra)
    return d


@pytest.mark.django_db
def test_checkout_crea_pedido_con_precios_del_servidor(client, cliente, catalogo, direccion):
    ShippingZoneRate.objects.create(departamento=direccion.departamento, municipio=direccion.municipio, valor=8000)
    client.force_login(cliente)
    cart.add_item(cliente, catalogo["a55"], 1)
    CartItem.objects.update(precio_al_agregar=1)  # un valor manipulado no afecta el cobro
    r = client.post(reverse("orders:checkout"), _datos_checkout(str(direccion.pk), total="10"))
    order = Order.objects.get()
    assert r.status_code == 302 and r.url == reverse("payments:iniciar", args=[order.numero])
    assert order.numero.startswith("GT-") and order.subtotal == 1800000
    assert order.costo_envio == 0 and "gratis" in order.regla_envio_aplicada.lower()  # ≥ 200.000
    assert order.total == 1800000 and order.estado_pedido == "pendiente_pago" and order.estado_pago == "pendiente"
    assert order.envio_municipio == "Villavicencio" and order.items.count() == 1
    assert not order.stock_descontado
    assert CartItem.objects.count() == 1  # el carrito se conserva hasta que el pago se apruebe


@pytest.mark.django_db
def test_checkout_exige_terminos(client, cliente, catalogo, direccion):
    client.force_login(cliente)
    cart.add_item(cliente, catalogo["a55"], 1)
    datos = _datos_checkout(str(direccion.pk))
    datos.pop("acepta_terminos")
    r = client.post(reverse("orders:checkout"), datos)
    assert r.status_code == 200 and Order.objects.count() == 0


@pytest.mark.django_db
def test_checkout_cotizacion_manual(client, cliente, catalogo, ubicaciones, mailoutbox):
    c = ShippingSettings.load()
    c.tarifa_fija_activa = False
    c.envio_gratis_activo = False
    c.save()
    client.force_login(cliente)
    cart.add_item(cliente, catalogo["a55"], 1)
    datos = _datos_checkout("nueva", **{
        "nueva-alias": "Leticia", "nueva-nombre_recibe": "Ana", "nueva-telefono": "3001112233",
        "nueva-departamento": ubicaciones["amazonas"].pk, "nueva-municipio": ubicaciones["leticia"].pk,
        "nueva-direccion": "Calle 1",
    })
    r = client.post(reverse("orders:checkout"), datos)
    order = Order.objects.get()
    assert r.url == order.get_absolute_url()
    assert order.estado_pedido == "esperando_cotizacion" and order.costo_envio == 0
    assert cliente.direcciones.filter(municipio=ubicaciones["leticia"]).exists()


@pytest.mark.django_db
def test_checkout_sin_cobertura_bloquea(client, cliente, catalogo, direccion):
    c = ShippingSettings.load()
    c.tarifa_fija_activa = c.cotizacion_manual_activa = c.envio_gratis_activo = False
    c.save()
    client.force_login(cliente)
    cart.add_item(cliente, catalogo["a55"], 1)
    client.post(reverse("orders:checkout"), _datos_checkout(str(direccion.pk)))
    assert Order.objects.count() == 0


@pytest.mark.django_db
def test_checkout_revalida_stock(client, cliente, catalogo, direccion):
    client.force_login(cliente)
    cart.add_item(cliente, catalogo["a55"], 5)
    catalogo["a55"].stock = 2
    catalogo["a55"].save()
    r = client.post(reverse("orders:checkout"), _datos_checkout(str(direccion.pk)))
    assert r.status_code == 302 and r.url == reverse("cart:detalle") and Order.objects.count() == 0


@pytest.mark.django_db
def test_resumen_checkout_muestra_regla(client, cliente, catalogo, direccion):
    ShippingZoneRate.objects.create(departamento=direccion.departamento, municipio=direccion.municipio, valor=8000)
    c = ShippingSettings.load()
    c.envio_gratis_activo = False
    c.save()
    client.force_login(cliente)
    cart.add_item(cliente, catalogo["a55"], 1)
    r = client.get(reverse("orders:checkout_resumen"), {"direccion": direccion.pk})
    assert "Envío a Villavicencio: $8.000" in r.content.decode()


@pytest.mark.django_db
def test_municipios_dependientes(client, ubicaciones):
    r = client.get(reverse("shipping:municipios"), {"nueva-departamento": ubicaciones["meta"].pk})
    html = r.content.decode()
    assert "Villavicencio" in html and "Leticia" not in html


@pytest.mark.django_db
def test_direcciones_ajenas_no_accesibles(client, cliente, otro_cliente, direccion):
    client.force_login(otro_cliente)
    assert client.get(reverse("accounts:direccion_editar", args=[direccion.pk])).status_code == 404
    assert client.post(reverse("accounts:direccion_eliminar", args=[direccion.pk])).status_code == 404
