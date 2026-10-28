import json

import pytest
from django.urls import URLPattern, reverse

from apps.catalog.models import Category, Product
from apps.orders.models import Order
from apps.panel.models import AuditLog
from apps.panel.urls import urlpatterns
from apps.shipping.models import ShippingZoneRate

pytestmark = pytest.mark.django_db


def _urls_panel(pedido=None):
    """Todas las rutas del panel con argumentos de ejemplo."""
    out = []
    for p in urlpatterns:
        assert isinstance(p, URLPattern)
        kw = {}
        for nombre in p.pattern.converters:
            kw[nombre] = pedido.numero if (nombre == "numero" and pedido) else ("GT-X" if nombre == "numero" else 1)
        out.append(reverse(f"panel:{p.name}", kwargs=kw))
    return out


def test_anonimo_redirigido_a_login(client):
    for url in _urls_panel():
        r = client.get(url)
        assert r.status_code == 302 and "/cuenta/ingresar/" in r.url, url


def test_cliente_no_staff_no_entra_al_panel(client, cliente):
    client.force_login(cliente)
    for url in _urls_panel():
        assert client.get(url).status_code == 403, url
        assert client.post(url).status_code == 403, url


def test_staff_entra_al_dashboard(client, staff, pedido):
    client.force_login(staff)
    r = client.get(reverse("panel:dashboard"))
    assert r.status_code == 200 and "Ventas de hoy" in r.content.decode()


def _datos_producto(**extra):
    d = {"nombre": "Tablet X", "sku": "tab-1", "precio": "1000000", "tipo_descuento": "ninguno", "stock": "5",
         "stock_minimo_alerta": "2", "activo": "on", "especificaciones_json": json.dumps([{"k": "Color", "v": "Gris"}])}
    d.update(extra)
    return d


def test_crear_producto_con_fotos_descuento_y_categorias(client, staff, catalogo, imagen):
    client.force_login(staff)
    smart = catalogo["cats"]["smart"]
    datos = _datos_producto(tipo_descuento="porcentaje", descuento_porcentaje="20", categoria_principal=smart.pk,
                            categorias=[catalogo["cats"]["port"].pk])
    datos["imagenes_nuevas"] = [imagen("a.png"), imagen("b.jpg", fmt="JPEG"), imagen("c.png")]
    r = client.post(reverse("panel:producto_nuevo"), datos)
    assert r.status_code == 302, r.context["form"].errors if r.context else r
    p = Product.objects.get(sku="TAB-1")
    assert p.precio_final == 800000 and p.especificaciones == {"Color": "Gris"}
    assert set(p.categorias.values_list("nombre", flat=True)) == {"Smartphones", "Celulares", "Portátiles"}
    assert p.imagenes.count() == 3 and p.imagenes.filter(es_principal=True).count() == 1
    assert AuditLog.objects.filter(accion="crear", modelo="producto").exists()


def test_editar_precio_queda_en_auditoria(client, staff, catalogo):
    client.force_login(staff)
    p = catalogo["a55"]
    datos = _datos_producto(nombre=p.nombre, sku=p.sku, precio="1700000", tipo_descuento="precio_antes", precio_antes="1900000")
    r = client.post(reverse("panel:producto_editar", args=[p.pk]), datos)
    assert r.status_code == 302
    p.refresh_from_db()
    assert p.precio == 1700000 and p.porcentaje_ahorro == 11
    log = AuditLog.objects.get(accion="editar")
    assert log.cambios["precio"] == [1800000, 1700000] and log.usuario == staff


def test_validacion_descuento_en_panel(client, staff):
    client.force_login(staff)
    r = client.post(reverse("panel:producto_nuevo"), _datos_producto(tipo_descuento="precio_antes", precio_antes="10"))
    assert r.status_code == 200 and "precio_antes" in r.context["form"].errors


def test_imagen_falsa_rechazada(client, staff):
    from django.core.files.uploadedfile import SimpleUploadedFile

    client.force_login(staff)
    datos = _datos_producto()
    datos["imagenes_nuevas"] = [SimpleUploadedFile("x.png", b"no soy imagen", content_type="image/png")]
    r = client.post(reverse("panel:producto_nuevo"), datos)
    assert r.status_code == 200 and not Product.objects.filter(sku="TAB-1").exists()


def test_eliminar_producto_con_pedidos_lo_desactiva(client, staff, pedido, catalogo):
    client.force_login(staff)
    client.post(reverse("panel:producto_eliminar", args=[catalogo["a55"].pk]))
    catalogo["a55"].refresh_from_db()
    assert catalogo["a55"].activo is False
    client.post(reverse("panel:producto_eliminar", args=[catalogo["thinkpad"].pk]))
    assert not Product.objects.filter(pk=catalogo["thinkpad"].pk).exists()


def test_duplicar_producto(client, staff, catalogo, imagen):
    from apps.catalog.models import ProductImage

    ProductImage.objects.create(producto=catalogo["s24"], imagen=imagen())
    client.force_login(staff)
    r = client.post(reverse("panel:producto_duplicar", args=[catalogo["s24"].pk]))
    copia = Product.objects.get(sku="S24-COPIA")
    assert r.status_code == 302 and not copia.activo and copia.imagenes.count() == 1
    assert copia.imagenes.get().imagen.name != catalogo["s24"].imagenes.get().imagen.name


def test_acciones_masivas(client, staff, catalogo):
    client.force_login(staff)
    ids = [catalogo["s24"].pk, catalogo["a55"].pk]
    client.post(reverse("panel:productos_acciones"), {"accion": "aplicar_descuento", "porcentaje": 30, "ids": ids})
    assert all(p.precio_final == round(p.precio * 0.7) for p in Product.objects.filter(pk__in=ids))
    client.post(reverse("panel:productos_acciones"), {"accion": "desactivar", "ids": ids})
    assert not Product.objects.filter(pk__in=ids, activo=True).exists()
    port = catalogo["cats"]["port"]
    client.post(reverse("panel:productos_acciones"), {"accion": "asignar_categoria", "categoria": port.pk, "ids": ids})
    assert port.productos.filter(pk__in=ids).count() == 2
    assert AuditLog.objects.filter(accion__startswith="masivo:").count() == 3


def test_categoria_asignar_quitar_y_reordenar(client, staff, catalogo):
    client.force_login(staff)
    port = catalogo["cats"]["port"]
    client.post(reverse("panel:categoria_productos", args=[port.pk]), {"accion": "agregar", "producto": [catalogo["s24"].pk]})
    assert port.productos.filter(pk=catalogo["s24"].pk).exists()
    client.post(reverse("panel:categoria_productos", args=[port.pk]), {"accion": "quitar", "producto": [catalogo["s24"].pk]})
    assert not port.productos.filter(pk=catalogo["s24"].pk).exists()
    cel, comp = catalogo["cats"]["cel"], catalogo["cats"]["comp"]
    r = client.post(reverse("panel:categorias_orden"), {"orden": [comp.pk, cel.pk]})
    assert r.status_code == 204
    assert list(Category.objects.filter(parent__isnull=True).order_by("orden").values_list("pk", flat=True)) == [comp.pk, cel.pk]


def test_importar_tarifas_csv(client, staff, ubicaciones):
    from django.core.files.uploadedfile import SimpleUploadedFile

    client.force_login(staff)
    csv_txt = "departamento;municipio;valor;dias;activo\nMeta;Villavicencio;8.000;1-2;si\n50;;12000;2-3;si\nNoExiste;;1;;si\nAmazonas;Leticia;abc;;si\n"
    r = client.post(reverse("panel:tarifas_importar"), {"archivo": SimpleUploadedFile("t.csv", csv_txt.encode("utf-8-sig"))})
    assert r.status_code == 302
    assert ShippingZoneRate.objects.get(municipio=ubicaciones["vcio"]).valor == 8000
    assert ShippingZoneRate.objects.get(departamento=ubicaciones["meta"], municipio=None).valor == 12000
    assert ShippingZoneRate.objects.count() == 2
    # reimportar actualiza en lugar de duplicar
    csv2 = "departamento,municipio,valor\nMeta,Villavicencio,9000\n"
    client.post(reverse("panel:tarifas_importar"), {"archivo": SimpleUploadedFile("t.csv", csv2.encode())})
    assert ShippingZoneRate.objects.count() == 2 and ShippingZoneRate.objects.get(municipio=ubicaciones["vcio"]).valor == 9000


def test_cotizacion_desde_panel(client, staff, pedido, mailoutbox):
    Order.objects.filter(pk=pedido.pk).update(estado_pedido="esperando_cotizacion")
    client.force_login(staff)
    r = client.post(reverse("panel:pedido_cotizar", args=[pedido.numero]), {"costo_envio": 30000, "nota": "5 días"})
    assert r.status_code == 302
    pedido.refresh_from_db()
    assert pedido.estado_pedido == "pendiente_pago" and pedido.total == pedido.subtotal + 30000
    assert AuditLog.objects.filter(accion="cotizar_envio").exists()


def test_cambio_estado_desde_panel_exige_foto(client, staff, pedido, imagen):
    from apps.payments import services as pagos

    pago = pagos.crear_pago(pedido)
    pagos.aplicar_transaccion({"id": "t", "status": "APPROVED", "reference": pago.referencia,
                               "amount_in_cents": pago.monto_centavos, "currency": "COP"}, "test")
    client.force_login(staff)
    url = reverse("panel:pedido_estado", args=[pedido.numero])
    r = client.post(url, {"estado": "enviado", "metodo_entrega": "personal", "entregado_por": "Juan"})
    assert r.status_code == 200 and "foto" in r.context["form_estado"].errors
    r = client.post(url, {"estado": "enviado", "metodo_entrega": "personal", "entregado_por": "Juan", "foto": imagen()})
    assert r.status_code == 302
    pedido.refresh_from_db()
    assert pedido.estado_pedido == "enviado" and pedido.entregado_por == "Juan"


def test_notas_internas_no_visibles_al_cliente(client, staff, cliente, pedido):
    client.force_login(staff)
    client.post(reverse("panel:pedido_notas", args=[pedido.numero]), {"notas_internas": "Cliente VIP secreto"})
    client.force_login(cliente)
    assert "Cliente VIP secreto" not in client.get(pedido.get_absolute_url()).content.decode()


def test_solo_superusuario_da_staff(client, staff, superusuario, cliente):
    client.force_login(staff)
    assert client.post(reverse("panel:cliente_staff", args=[cliente.pk])).status_code == 403
    client.force_login(superusuario)
    client.post(reverse("panel:cliente_staff", args=[cliente.pk]))
    cliente.refresh_from_db()
    assert cliente.is_staff


def test_desactivar_cliente(client, staff, cliente):
    client.force_login(staff)
    client.post(reverse("panel:cliente_activar", args=[cliente.pk]))
    cliente.refresh_from_db()
    assert not cliente.is_active


def test_exportar_csv(client, staff, pedido):
    client.force_login(staff)
    from django.utils import timezone

    hoy = timezone.localtime(pedido.creado).date()
    r = client.get(reverse("panel:reportes"), {"desde": hoy, "hasta": hoy, "exportar": "pedidos"})
    contenido = r.content.decode("utf-8-sig")
    assert r["Content-Type"].startswith("text/csv") and pedido.numero in contenido and "Número;Fecha" in contenido
    r = client.get(reverse("panel:reportes"), {"desde": hoy, "hasta": hoy, "exportar": "productos"})
    assert "Galaxy A55" in r.content.decode("utf-8-sig")


def test_configuracion_tienda_invalida_cache(client, staff):
    client.force_login(staff)
    from apps.storefront.models import StoreSettings

    datos = {"nombre": "GlobalTecnology", "barra_anuncios": "Envío gratis HOY", "email_contacto": "a@b.co"}
    r = client.post(reverse("panel:tienda"), datos)
    assert r.status_code == 302 and StoreSettings.load().barra_anuncios == "Envío gratis HOY"
    assert "Envío gratis HOY" in client.get("/").content.decode()


def test_cambios_de_categoria_invalidan_menu(client, staff, catalogo):
    assert "Celulares" in client.get("/").content.decode()
    client.force_login(staff)
    cel = catalogo["cats"]["cel"]
    client.post(reverse("panel:categoria_editar", args=[cel.pk]), {"nombre": "Teléfonos", "orden": 0, "activa": "on", "mostrar_en_menu": "on"})
    assert "Teléfonos" in client.get("/").content.decode()
