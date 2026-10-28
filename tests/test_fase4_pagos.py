import json
from datetime import timedelta
from unittest import mock

import pytest
from django.core import mail
from django.urls import reverse
from django.utils import timezone

from apps.cart.models import CartItem
from apps.payments import services, wompi
from apps.payments.models import Payment, WompiEvent
from tests.conftest import evento_wompi

pytestmark = pytest.mark.django_db


# ---------- Firmas ----------
def test_firma_integridad_ejemplo_documentacion_wompi():
    # Ejemplo de la documentación oficial de Wompi (Widget & Checkout Web)
    firma = wompi.integrity_signature("sk8-438k4-xmxm392-sn2m", 2490000, "COP",
                                      "prod_integrity_Z5mMke9x0k8gpErbDqwrJXMqsI6SFli6")
    assert firma == "37c8407747e595535433ef8f6a811d853cd943046624a0ec04662b17bbf33bf5"


def test_checksum_evento_valido_e_invalido():
    tx = {"id": "1234-1610641025-49201", "status": "APPROVED", "amount_in_cents": 4490000, "reference": "R1", "currency": "COP"}
    ev = evento_wompi(tx)
    assert wompi.verify_event(ev)
    assert not wompi.verify_event(ev, secret="otro_secreto")
    ev_malo = evento_wompi(tx, alterar=lambda e: e["signature"].update(checksum="0" * 64))
    assert not wompi.verify_event(ev_malo)
    sin_firma = evento_wompi(tx, alterar=lambda e: e.pop("signature"))
    assert not wompi.verify_event(sin_firma)


def test_checksum_detecta_monto_alterado():
    tx = {"id": "1", "status": "APPROVED", "amount_in_cents": 100, "reference": "R1", "currency": "COP"}
    ev = evento_wompi(tx, alterar=lambda e: e["data"]["transaction"].update(amount_in_cents=1))
    assert not wompi.verify_event(ev)


# ---------- Inicio del pago ----------
def test_iniciar_pago_genera_formulario_wompi(client, cliente, pedido):
    client.force_login(cliente)
    r = client.get(reverse("payments:iniciar", args=[pedido.numero]))
    assert r.status_code == 200
    campos = dict(r.context["campos"])
    pago = Payment.objects.get()
    assert pago.referencia == f"{pedido.numero}-1" and pago.monto_centavos == 360000000
    assert campos["amount-in-cents"] == "360000000" and campos["currency"] == "COP"
    assert campos["signature:integrity"] == wompi.integrity_signature(pago.referencia, 360000000, "COP")
    assert campos["redirect-url"].endswith("/pagos/resultado/")
    assert campos["customer-data:legal-id"] == "123456" and campos["shipping-address:city"] == "Villavicencio"
    assert 'action="https://checkout.wompi.co/p/"' in r.content.decode()
    assert "card" not in json.dumps(campos).lower()  # nunca datos de tarjeta


def test_otro_usuario_no_puede_pagar_pedido_ajeno(client, otro_cliente, pedido):
    client.force_login(otro_cliente)
    assert client.get(reverse("payments:iniciar", args=[pedido.numero])).status_code == 404


def test_reintento_genera_referencia_nueva(client, cliente, pedido):
    client.force_login(cliente)
    client.get(reverse("payments:iniciar", args=[pedido.numero]))
    p1 = Payment.objects.get()
    services.aplicar_transaccion({"id": "tx1", "status": "DECLINED", "reference": p1.referencia,
                                  "amount_in_cents": p1.monto_centavos, "currency": "COP"}, "test")
    pedido.refresh_from_db()
    assert pedido.estado_pago == "rechazado" and pedido.puede_pagar
    r = client.post(reverse("payments:pagar", args=[pedido.numero]))
    client.get(r.url)
    refs = list(Payment.objects.order_by("creado").values_list("referencia", flat=True))
    assert refs == [f"{pedido.numero}-1", f"{pedido.numero}-2"]
    pedido.refresh_from_db()
    assert pedido.wompi_referencia == refs[1] and pedido.estado_pago == "pendiente"


# ---------- Webhook ----------
def _pago(pedido):
    return services.crear_pago(pedido)


def _post(client, ev):
    return client.post(reverse("payments:eventos"), data=json.dumps(ev), content_type="application/json")


def test_webhook_aprobado_descuenta_stock_vacia_carrito_y_envia_emails(client, pedido, catalogo):
    pago = _pago(pedido)
    stock_antes = catalogo["a55"].stock
    tx = {"id": "tx-ok", "status": "APPROVED", "reference": pago.referencia, "amount_in_cents": pago.monto_centavos,
          "currency": "COP", "payment_method_type": "NEQUI"}
    mail.outbox.clear()
    with mock.patch("django.db.transaction.on_commit", side_effect=lambda f, *a, **k: f()):
        r = _post(client, evento_wompi(tx))
    assert r.status_code == 200 and r.json()["resultado"] == "ok"
    pedido.refresh_from_db()
    catalogo["a55"].refresh_from_db()
    assert pedido.estado_pago == "aprobado" and pedido.estado_pedido == "en_proceso"
    assert pedido.stock_descontado and pedido.metodo_pago == "Nequi" and pedido.wompi_transaccion_id == "tx-ok"
    assert catalogo["a55"].stock == stock_antes - 2
    assert CartItem.objects.filter(carrito__usuario=pedido.usuario).count() == 0
    asuntos = [m.subject for m in mail.outbox]
    assert any("Pago aprobado" in s for s in asuntos) and any("Nuevo pedido pagado" in s for s in asuntos)
    assert pedido.eventos.filter(estado="en_proceso").exists()


def test_webhook_idempotente_doble_aprobado_descuenta_una_vez(client, pedido, catalogo):
    pago = _pago(pedido)
    stock_antes = catalogo["a55"].stock
    tx = {"id": "tx-ok", "status": "APPROVED", "reference": pago.referencia, "amount_in_cents": pago.monto_centavos, "currency": "COP"}
    ev = evento_wompi(tx)
    assert _post(client, ev).json()["resultado"] == "ok"
    assert _post(client, ev).json()["resultado"] == "sin_cambios"
    assert _post(client, evento_wompi(tx, timestamp=1530299999)).json()["resultado"] == "sin_cambios"
    catalogo["a55"].refresh_from_db()
    assert catalogo["a55"].stock == stock_antes - 2
    assert pedido.eventos.filter(estado="en_proceso").count() == 1
    assert WompiEvent.objects.count() == 3


def test_webhook_firma_invalida_rechazado(client, pedido):
    pago = _pago(pedido)
    tx = {"id": "tx", "status": "APPROVED", "reference": pago.referencia, "amount_in_cents": pago.monto_centavos, "currency": "COP"}
    r = _post(client, evento_wompi(tx, secret="secreto-equivocado"))
    assert r.status_code == 401
    pedido.refresh_from_db()
    assert pedido.estado_pago == "pendiente"
    assert WompiEvent.objects.get().valido is False


def test_webhook_monto_alterado_no_aprueba(client, pedido):
    pago = _pago(pedido)
    tx = {"id": "tx", "status": "APPROVED", "reference": pago.referencia, "amount_in_cents": 100, "currency": "COP"}
    r = _post(client, evento_wompi(tx))  # firma válida, pero el monto no coincide con el pedido
    assert r.json()["resultado"] == "monto_invalido"
    pedido.refresh_from_db()
    assert pedido.estado_pago == "pendiente" and not pedido.stock_descontado


def test_webhook_referencia_desconocida(client):
    tx = {"id": "tx", "status": "APPROVED", "reference": "NO-EXISTE", "amount_in_cents": 100, "currency": "COP"}
    assert _post(client, evento_wompi(tx)).json()["resultado"] == "referencia_desconocida"


def test_webhook_json_invalido(client):
    r = client.post(reverse("payments:eventos"), data="no-json", content_type="application/json")
    assert r.status_code == 400


def test_webhook_rechazado_conserva_carrito(client, pedido):
    pago = _pago(pedido)
    tx = {"id": "tx", "status": "DECLINED", "reference": pago.referencia, "amount_in_cents": pago.monto_centavos, "currency": "COP"}
    _post(client, evento_wompi(tx))
    pedido.refresh_from_db()
    assert pedido.estado_pago == "rechazado" and pedido.estado_pedido == "pendiente_pago"
    assert CartItem.objects.filter(carrito__usuario=pedido.usuario).exists()


@pytest.mark.parametrize("estado,esperado", [("VOIDED", "anulado"), ("ERROR", "error")])
def test_webhook_otros_estados(client, pedido, estado, esperado):
    pago = _pago(pedido)
    tx = {"id": "tx", "status": estado, "reference": pago.referencia, "amount_in_cents": pago.monto_centavos, "currency": "COP"}
    _post(client, evento_wompi(tx))
    pedido.refresh_from_db()
    assert pedido.estado_pago == esperado


def test_rechazo_tardio_no_revierte_aprobado(client, pedido):
    pago = _pago(pedido)
    base = {"reference": pago.referencia, "amount_in_cents": pago.monto_centavos, "currency": "COP"}
    _post(client, evento_wompi({**base, "id": "tx", "status": "APPROVED"}))
    _post(client, evento_wompi({**base, "id": "tx", "status": "DECLINED"}))
    pedido.refresh_from_db()
    assert pedido.estado_pago == "aprobado"


def test_aprobado_sin_stock_genera_alerta(client, pedido, catalogo):
    pago = _pago(pedido)
    catalogo["a55"].stock = 1
    catalogo["a55"].save()
    tx = {"id": "tx", "status": "APPROVED", "reference": pago.referencia, "amount_in_cents": pago.monto_centavos, "currency": "COP"}
    _post(client, evento_wompi(tx))
    pedido.refresh_from_db()
    catalogo["a55"].refresh_from_db()
    assert pedido.estado_pago == "aprobado" and pedido.alerta_stock and "Stock insuficiente" in pedido.alerta_detalle
    assert catalogo["a55"].stock == 0


# ---------- Redirect y sincronización ----------
def test_pagina_resultado_consulta_api(client, cliente, pedido):
    pago = _pago(pedido)
    tx = {"id": "tx-r", "status": "APPROVED", "reference": pago.referencia, "amount_in_cents": pago.monto_centavos, "currency": "COP"}
    client.force_login(cliente)
    with mock.patch.object(wompi, "get_transaction", return_value=tx) as m:
        r = client.get(reverse("payments:resultado"), {"id": "tx-r"})
    m.assert_called_once_with("tx-r")
    assert r.status_code == 200 and "Pago aprobado" in r.content.decode()
    pedido.refresh_from_db()
    assert pedido.estado_pago == "aprobado"


def test_pagina_resultado_si_api_falla(client, pedido):
    with mock.patch.object(wompi, "get_transaction", side_effect=wompi.WompiError("timeout")):
        r = client.get(reverse("payments:resultado"), {"id": "x"})
    assert r.status_code == 200 and "confirmando" in r.content.decode()


def test_wompi_sync(pedido):
    from django.core.management import call_command

    pago = _pago(pedido)
    Payment.objects.filter(pk=pago.pk).update(creado=timezone.now() - timedelta(minutes=20))
    tx = {"id": "tx-s", "status": "APPROVED", "reference": pago.referencia, "amount_in_cents": pago.monto_centavos, "currency": "COP"}
    with mock.patch.object(wompi, "find_transactions", return_value=[tx]) as m:
        call_command("wompi_sync")
    m.assert_called_once_with(pago.referencia)
    pedido.refresh_from_db()
    assert pedido.estado_pago == "aprobado" and pedido.stock_descontado


def test_wompi_sync_ignora_pagos_recientes(pedido):
    from django.core.management import call_command

    _pago(pedido)
    with mock.patch.object(wompi, "find_transactions") as m:
        call_command("wompi_sync")
    m.assert_not_called()
