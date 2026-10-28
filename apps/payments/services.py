"""Aplicación idempotente de transacciones de Wompi a los pedidos."""
import logging

from django.conf import settings
from django.db import transaction
from django.urls import reverse
from django.utils import timezone

from apps.core.emails import send_templated
from apps.orders.models import EstadoPago, EstadoPedido, Order
from apps.orders import services as order_services

from .models import Payment

logger = logging.getLogger("wompi")

MAPA_ESTADOS = {
    "APPROVED": EstadoPago.APROBADO,
    "DECLINED": EstadoPago.RECHAZADO,
    "VOIDED": EstadoPago.ANULADO,
    "ERROR": EstadoPago.ERROR,
}
METODOS = {
    "CARD": "Tarjeta", "PSE": "PSE", "NEQUI": "Nequi", "BANCOLOMBIA_TRANSFER": "Botón Bancolombia",
    "BANCOLOMBIA_QR": "QR Bancolombia", "BANCOLOMBIA_COLLECT": "Corresponsal Bancolombia", "DAVIPLATA": "Daviplata",
    "PCOL": "Puntos Colombia", "BNPL": "Compra ahora, paga después", "SU_PLUS": "SU+ Pay",
}


@transaction.atomic
def crear_pago(order: Order) -> Payment:
    """Genera una referencia nueva (también para reintentos) vinculada al pedido."""
    order = Order.objects.select_for_update().get(pk=order.pk)
    n = order.pagos.count() + 1
    referencia = f"{order.numero}-{n}"
    while Payment.objects.filter(referencia=referencia).exists():
        n += 1
        referencia = f"{order.numero}-{n}"
    pago = Payment.objects.create(pedido=order, referencia=referencia, monto_centavos=order.total_centavos)
    order.wompi_referencia = referencia
    if order.estado_pago in (EstadoPago.RECHAZADO, EstadoPago.ANULADO, EstadoPago.ERROR):
        order.estado_pago = EstadoPago.PENDIENTE
    order.save(update_fields=["wompi_referencia", "estado_pago", "actualizado"])
    logger.info("wompi_pago_creado pedido=%s referencia=%s monto_centavos=%s", order.numero, referencia, pago.monto_centavos)
    return pago


def aplicar_transaccion(tx: dict, fuente: str) -> str:
    """Aplica el estado de una transacción de Wompi. Idempotente y seguro ante eventos repetidos.

    Devuelve un código de resultado para registro: ok, sin_cambios, referencia_desconocida,
    monto_invalido, pendiente.
    """
    referencia = str(tx.get("reference") or "")
    estado = str(tx.get("status") or "").upper()
    tx_id = str(tx.get("id") or "")
    with transaction.atomic():
        pago = Payment.objects.select_for_update().select_related("pedido").filter(referencia=referencia).first()
        if pago is None:
            logger.warning("wompi_referencia_desconocida fuente=%s referencia=%s tx=%s", fuente, referencia, tx_id)
            return "referencia_desconocida"
        order = Order.objects.select_for_update().get(pk=pago.pedido_id)

        monto = tx.get("amount_in_cents")
        moneda = str(tx.get("currency") or "COP")
        if monto is None or int(monto) != pago.monto_centavos or moneda != pago.moneda:
            logger.error(
                "wompi_monto_invalido fuente=%s referencia=%s esperado=%s recibido=%s moneda=%s",
                fuente, referencia, pago.monto_centavos, monto, moneda,
            )
            pago.detalle = f"Monto/moneda no coinciden ({monto} {moneda})"
            pago.save(update_fields=["detalle", "actualizado"])
            return "monto_invalido"

        if pago.estado == estado and (estado != "APPROVED" or order.stock_descontado or order.estado_pedido == EstadoPedido.CANCELADO):
            return "sin_cambios"

        metodo_raw = str(tx.get("payment_method_type") or "")
        pago.estado = estado if estado in Payment.Estado.values else Payment.Estado.ERROR
        pago.transaccion_id = tx_id or pago.transaccion_id
        pago.metodo = METODOS.get(metodo_raw, metodo_raw.title())
        pago.detalle = str(tx.get("status_message") or "")[:255]
        pago.respuesta = {k: tx.get(k) for k in ("id", "status", "reference", "amount_in_cents", "currency",
                                                  "payment_method_type", "status_message", "created_at", "finalized_at")}
        pago.save()

        if estado == "PENDING":
            return "pendiente"
        if estado == "APPROVED":
            return _aprobar(order, pago, fuente)
        return _rechazar(order, pago, estado, fuente)


def _aprobar(order: Order, pago: Payment, fuente: str) -> str:
    if order.estado_pago == EstadoPago.APROBADO and order.wompi_transaccion_id and order.wompi_transaccion_id != pago.transaccion_id:
        # Dos pagos aprobados para el mismo pedido: no se descuenta stock dos veces; alerta para reembolso.
        order.alerta_stock = True
        order.alerta_detalle = (order.alerta_detalle + "\n" if order.alerta_detalle else "") + (
            f"Pago duplicado aprobado ({pago.referencia}, transacción {pago.transaccion_id}). Revisar reembolso."
        )
        order.save(update_fields=["alerta_stock", "alerta_detalle", "actualizado"])
        logger.error("wompi_pago_duplicado pedido=%s referencia=%s", order.numero, pago.referencia)
        return "duplicado"

    order.estado_pago = EstadoPago.APROBADO
    order.wompi_referencia = pago.referencia
    order.wompi_transaccion_id = pago.transaccion_id
    order.metodo_pago = pago.metodo
    order.pagado_en = order.pagado_en or timezone.now()
    order.save()

    if order.estado_pedido == EstadoPedido.CANCELADO:
        order.alerta_stock = True
        order.alerta_detalle = (order.alerta_detalle + "\n" if order.alerta_detalle else "") + (
            "Se aprobó un pago para un pedido cancelado. Revisar reembolso o reactivar."
        )
        order.save(update_fields=["alerta_stock", "alerta_detalle", "actualizado"])
        logger.error("wompi_pago_en_cancelado pedido=%s", order.numero)
        return "pago_en_cancelado"

    order_services.descontar_stock(order)  # una sola vez gracias a stock_descontado
    if order.estado_pedido == EstadoPedido.PENDIENTE_PAGO:
        order_services.cambiar_estado(
            order, EstadoPedido.EN_PROCESO, nota=f"Pago aprobado con {pago.metodo or 'Wompi'}.", sistema=True,
        )
    from apps.cart.services import clear_cart

    clear_cart(order.usuario)
    url = f"{settings.SITE_URL}{order.get_absolute_url()}"
    url_panel = f"{settings.SITE_URL}{reverse('panel:pedido', args=[order.numero])}"
    numero, email = order.numero, order.cliente_email
    transaction.on_commit(lambda: send_templated(
        "pago_aprobado", f"¡Pago aprobado! Pedido {numero}", email,
        {"pedido": Order.objects.get(pk=order.pk), "url_pedido": url},
    ))
    transaction.on_commit(lambda: send_templated(
        "admin_pedido_pagado", f"Nuevo pedido pagado {numero}", settings.ADMIN_NOTIFY_EMAIL,
        {"pedido": Order.objects.get(pk=order.pk), "url_panel": url_panel},
    ))
    logger.info("wompi_aprobado fuente=%s pedido=%s referencia=%s tx=%s", fuente, order.numero, pago.referencia, pago.transaccion_id)
    return "ok"


def _rechazar(order: Order, pago: Payment, estado: str, fuente: str) -> str:
    if order.estado_pago == EstadoPago.APROBADO:
        # Un intento viejo rechazado no cambia un pedido ya pagado.
        return "sin_cambios"
    if order.wompi_referencia and order.wompi_referencia != pago.referencia:
        # Hay un intento más reciente en curso: solo se registra.
        logger.info("wompi_rechazo_intento_viejo pedido=%s referencia=%s", order.numero, pago.referencia)
        return "sin_cambios"
    order.estado_pago = MAPA_ESTADOS.get(estado, EstadoPago.ERROR)
    order.wompi_transaccion_id = pago.transaccion_id
    order.save(update_fields=["estado_pago", "wompi_transaccion_id", "actualizado"])
    order_services.registrar_evento(
        order, order.estado_pedido, titulo=f"Pago {order.get_estado_pago_display().lower()}",
        nota="Puedes reintentar el pago desde este pedido. Tus productos siguen en el carrito.",
    )
    url = f"{settings.SITE_URL}{order.get_absolute_url()}"
    numero, email = order.numero, order.cliente_email
    transaction.on_commit(lambda: send_templated(
        "pago_rechazado", f"No se completó el pago del pedido {numero}", email,
        {"pedido": Order.objects.get(pk=order.pk), "url_pedido": url},
    ))
    logger.info("wompi_no_aprobado fuente=%s pedido=%s referencia=%s estado=%s", fuente, order.numero, pago.referencia, estado)
    return "ok"
