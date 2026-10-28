import pytest
from django.core import mail
from django.urls import reverse

from apps.orders import services
from apps.orders.forms import CambioEstadoForm
from apps.orders.models import OrderStatusEvent
from apps.payments import services as pagos

pytestmark = pytest.mark.django_db


def aprobar(pedido):
    pago = pagos.crear_pago(pedido)
    pagos.aplicar_transaccion({"id": "tx", "status": "APPROVED", "reference": pago.referencia,
                               "amount_in_cents": pago.monto_centavos, "currency": "COP"}, "test")
    pedido.refresh_from_db()
    return pedido


# ---------- Máquina de estados ----------
def test_transiciones_invalidas_rechazadas(pedido):
    with pytest.raises(services.TransicionInvalida):
        services.cambiar_estado(pedido, "entregado")
    with pytest.raises(services.TransicionInvalida):
        services.cambiar_estado(pedido, "enviado", metodo_entrega="personal", entregado_por="X", foto="x")


def test_en_proceso_requiere_pago_aprobado(pedido):
    with pytest.raises(services.TransicionInvalida, match="pago está aprobado"):
        services.cambiar_estado(pedido, "en_proceso")
    pedido = aprobar(pedido)
    assert pedido.estado_pedido == "en_proceso"


def test_enviado_exige_metodo_y_foto(pedido, imagen):
    pedido = aprobar(pedido)
    with pytest.raises(services.TransicionInvalida) as e:
        services.cambiar_estado(pedido, "enviado")
    assert "metodo_entrega" in e.value.error_dict and "foto" in e.value.error_dict
    with pytest.raises(services.TransicionInvalida) as e:
        services.cambiar_estado(pedido, "enviado", metodo_entrega="transportadora", foto=imagen())
    assert "transportadora" in e.value.error_dict
    with pytest.raises(services.TransicionInvalida) as e:
        services.cambiar_estado(pedido, "enviado", metodo_entrega="personal", foto=imagen())
    assert "entregado_por" in e.value.error_dict
    with pytest.raises(services.TransicionInvalida) as e:
        services.cambiar_estado(pedido, "enviado", metodo_entrega="transportadora", transportadora="Servientrega")
    assert "foto" in e.value.error_dict


def test_flujo_transportadora_completo_con_emails(pedido, imagen):
    pedido = aprobar(pedido)
    mail.outbox.clear()
    services.cambiar_estado(pedido, "enviado", metodo_entrega="transportadora", transportadora="Servientrega",
                            numero_guia="123456", url_rastreo="https://rastreo.test/123456", foto=imagen(), nota="Sale hoy")
    pedido.refresh_from_db()
    assert pedido.estado_pedido == "enviado" and pedido.transportadora == "Servientrega" and pedido.numero_guia == "123456"
    ev = pedido.eventos.get(estado="enviado")
    assert ev.foto.name.startswith("evidencias/") and ev.foto.name.endswith(".webp") and ev.nota == "Sale hoy"
    assert "va en camino" in mail.outbox[-1].subject and mail.outbox[-1].attachments  # foto adjunta
    # Entregado por transportadora: foto opcional
    services.cambiar_estado(pedido, "entregado")
    pedido.refresh_from_db()
    assert pedido.estado_pedido == "entregado" and "entregado" in mail.outbox[-1].subject


def test_entrega_personal_exige_foto_al_entregar(pedido, imagen):
    pedido = aprobar(pedido)
    services.cambiar_estado(pedido, "enviado", metodo_entrega="personal", entregado_por="Carlos", foto=imagen())
    pedido.refresh_from_db()
    assert pedido.entregado_por == "Carlos"
    with pytest.raises(services.TransicionInvalida, match="obligatoria"):
        services.cambiar_estado(pedido, "entregado")
    services.cambiar_estado(pedido, "entregado", foto=imagen())


def test_estados_finales_no_cambian(pedido):
    services.cancelar(pedido)
    pedido.refresh_from_db()
    for nuevo in ["pendiente_pago", "en_proceso", "enviado", "entregado"]:
        with pytest.raises(services.TransicionInvalida):
            services.cambiar_estado(pedido, nuevo)


def test_cancelar_devuelve_stock(pedido, catalogo):
    stock = catalogo["a55"].stock
    pedido = aprobar(pedido)
    catalogo["a55"].refresh_from_db()
    assert catalogo["a55"].stock == stock - 2
    services.cancelar(pedido, nota="Sin cobertura")
    catalogo["a55"].refresh_from_db()
    pedido.refresh_from_db()
    assert catalogo["a55"].stock == stock and pedido.stock_devuelto and pedido.estado_pedido == "cancelado"
    services.devolver_stock(pedido)  # idempotente
    catalogo["a55"].refresh_from_db()
    assert catalogo["a55"].stock == stock


def test_formulario_cambio_estado_valida_reglas(pedido, imagen):
    pedido = aprobar(pedido)
    f = CambioEstadoForm({"estado": "enviado", "metodo_entrega": "transportadora"}, pedido=pedido)
    assert not f.is_valid() and "foto" in f.errors and "transportadora" in f.errors
    f = CambioEstadoForm({"estado": "enviado", "metodo_entrega": "personal", "entregado_por": "Ana"}, {"foto": imagen()}, pedido=pedido)
    assert f.is_valid(), f.errors
    opciones = [c[0] for c in f.fields["estado"].choices]
    assert opciones == ["enviado", "cancelado"]


# ---------- Cotización manual ----------
def test_cotizacion_manual_de_punta_a_punta(client, cliente, pedido):
    pedido.estado_pedido = "esperando_cotizacion"
    pedido.save()
    client.force_login(cliente)
    assert client.get(reverse("payments:iniciar", args=[pedido.numero])).status_code == 302  # aún no se puede pagar
    with pytest.raises(services.TransicionInvalida):
        services.cambiar_estado(pedido, "pendiente_pago")  # solo vía cotización
    mail.outbox.clear()
    services.registrar_cotizacion(pedido, 25000, "Llega en 5 días")
    pedido.refresh_from_db()
    assert pedido.estado_pedido == "pendiente_pago" and pedido.costo_envio == 25000
    assert pedido.total == pedido.subtotal + 25000 and "cotizado" in pedido.regla_envio_aplicada
    assert "cotizado" in mail.outbox[-1].subject and pedido.get_absolute_url() in mail.outbox[-1].alternatives[0][0]
    r = client.get(reverse("payments:iniciar", args=[pedido.numero]))
    assert r.status_code == 200 and dict(r.context["campos"])["amount-in-cents"] == str(pedido.total * 100)
    pedido = aprobar(pedido)
    assert pedido.estado_pedido == "en_proceso"


def test_cotizacion_revalida_stock_al_pagar(client, cliente, pedido, catalogo):
    pedido.estado_pedido = "esperando_cotizacion"
    pedido.save()
    services.registrar_cotizacion(pedido, 10000)
    catalogo["a55"].stock = 1
    catalogo["a55"].save()
    client.force_login(cliente)
    r = client.get(reverse("payments:iniciar", args=[pedido.numero]))
    assert r.status_code == 302  # sin stock suficiente no se crea el pago


# ---------- Privacidad de pedidos y evidencias ----------
def _evidencia(pedido, imagen):
    pedido = aprobar(pedido)
    services.cambiar_estado(pedido, "enviado", metodo_entrega="personal", entregado_por="Carlos", foto=imagen())
    return OrderStatusEvent.objects.get(pedido=pedido, estado="enviado")


def test_cliente_ve_su_evidencia_y_nadie_mas(client, cliente, otro_cliente, staff, pedido, imagen):
    ev = _evidencia(pedido, imagen)
    url = reverse("orders:evidencia", args=[ev.pk])
    assert client.get(url).status_code == 302  # anónimo → login
    client.force_login(otro_cliente)
    assert client.get(url).status_code == 404
    client.force_login(cliente)
    r = client.get(url)
    assert r.status_code == 200 and r["Content-Type"] == "image/webp" and "private" in r["Cache-Control"]
    client.force_login(staff)
    assert client.get(url).status_code == 200


def test_evidencia_no_es_publica_por_media(client, pedido, imagen):
    ev = _evidencia(pedido, imagen)
    assert client.get(f"/media/{ev.foto.name}").status_code == 404
    assert client.get(f"/media/privado/{ev.foto.name}").status_code == 404


def test_cliente_no_ve_pedidos_ajenos(client, otro_cliente, cliente, pedido):
    client.force_login(otro_cliente)
    assert client.get(pedido.get_absolute_url()).status_code == 404
    assert pedido.numero not in client.get(reverse("orders:mis_pedidos")).content.decode()
    client.force_login(cliente)
    r = client.get(pedido.get_absolute_url())
    assert r.status_code == 200 and pedido.numero in r.content.decode()


def test_linea_de_tiempo_muestra_guia_y_foto(client, cliente, pedido, imagen):
    pedido = aprobar(pedido)
    services.cambiar_estado(pedido, "enviado", metodo_entrega="transportadora", transportadora="Coordinadora",
                            numero_guia="G-999", url_rastreo="https://rastreo.test/G-999", foto=imagen())
    client.force_login(cliente)
    html = client.get(pedido.get_absolute_url()).content.decode()
    assert "Coordinadora" in html and "G-999" in html and "https://rastreo.test/G-999" in html
    assert "/pedidos/evidencia/" in html


def test_email_falla_sin_romper_flujo(pedido, settings, imagen):
    settings.EMAIL_BACKEND = "tests.test_fase5_pedidos.BackendRoto"
    pedido = aprobar(pedido)
    services.cambiar_estado(pedido, "enviado", metodo_entrega="personal", entregado_por="X", foto=imagen())
    pedido.refresh_from_db()
    assert pedido.estado_pedido == "enviado"


class BackendRoto:
    def __init__(self, *a, **k):
        pass

    def send_messages(self, msgs):
        raise OSError("SMTP caído")
