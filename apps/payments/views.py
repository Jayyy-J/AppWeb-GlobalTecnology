import json
import logging

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import HttpResponseBadRequest, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.cache import never_cache
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from apps.orders.models import Order

from . import services, wompi
from .models import Payment, WompiEvent

logger = logging.getLogger("wompi")


def _stock_suficiente(order):
    faltantes = []
    for it in order.items.select_related("producto"):
        p = it.producto
        if p is None or not p.activo or p.stock < it.cantidad:
            faltantes.append(it.nombre)
    return faltantes


@login_required
@never_cache
def iniciar(request, numero):
    """Crea un intento de pago (referencia nueva) y redirige al Web Checkout de Wompi."""
    order = get_object_or_404(Order, numero=numero, usuario=request.user)
    if not order.puede_pagar:
        messages.info(request, "Este pedido no tiene pagos pendientes.")
        return redirect(order.get_absolute_url())
    # El stock no se reserva: se revalida antes de cada intento de pago.
    faltantes = _stock_suficiente(order)
    if faltantes:
        messages.error(request, "Sin stock suficiente para: " + ", ".join(faltantes) + ". Escríbenos para ayudarte.")
        return redirect(order.get_absolute_url())
    if not settings.WOMPI_PUBLIC_KEY or not settings.WOMPI_INTEGRITY_SECRET:
        messages.error(request, "Los pagos en línea no están configurados. Contáctanos para completar tu compra.")
        return redirect(order.get_absolute_url())
    pago = services.crear_pago(order)
    order.refresh_from_db()
    redirect_url = f"{settings.SITE_URL}{reverse('payments:resultado')}"
    return render(request, "payments/redirigir.html", {
        "pedido": order, "pago": pago, "accion": settings.WOMPI_CHECKOUT_URL,
        "campos": wompi.checkout_fields(pago, order, redirect_url),
    })


@login_required
@require_POST
def pagar(request, numero):
    """Botón "Pagar ahora" / "Reintentar pago" de Mis pedidos."""
    get_object_or_404(Order, numero=numero, usuario=request.user)
    return redirect("payments:iniciar", numero=numero)


@never_cache
def resultado(request):
    """Página de retorno de Wompi. Consulta la transacción en la API (nunca confía en la URL)."""
    tx_id = request.GET.get("id", "")[:80]
    tx, error = None, False
    if tx_id:
        try:
            tx = wompi.get_transaction(tx_id)
            services.aplicar_transaccion(tx, fuente="redirect")
        except wompi.WompiError:
            error = True
    pago = Payment.objects.select_related("pedido").filter(referencia=(tx or {}).get("reference", "")).first()
    order = pago.pedido if pago else None
    if order and request.user.is_authenticated and order.usuario_id != request.user.id and not request.user.is_staff:
        order = None  # no mostrar pedidos ajenos
    if order:
        order.refresh_from_db()
    return render(request, "payments/resultado.html", {
        "tx": tx, "estado": (tx or {}).get("status", ""), "pedido": order, "error": error,
    })


@csrf_exempt
@require_POST
def eventos(request):
    """Webhook de eventos de Wompi (POST /pagos/wompi/eventos/)."""
    try:
        evento = json.loads(request.body.decode("utf-8"))
        if not isinstance(evento, dict):
            raise ValueError
    except (ValueError, UnicodeDecodeError):
        logger.warning("wompi_evento_json_invalido")
        return HttpResponseBadRequest("JSON inválido")

    tx = ((evento.get("data") or {}).get("transaction")) or {}
    valido = wompi.verify_event(evento)
    registro = WompiEvent.objects.create(
        evento=str(evento.get("event", ""))[:60], transaccion_id=str(tx.get("id", ""))[:80],
        referencia=str(tx.get("reference", ""))[:60], estado=str(tx.get("status", ""))[:20],
        ambiente=str(evento.get("environment", ""))[:10],
        checksum=str((evento.get("signature") or {}).get("checksum", ""))[:128], valido=valido, payload=evento,
    )
    if not valido:
        logger.warning("wompi_evento_firma_invalida id=%s tx=%s", registro.pk, registro.transaccion_id)
        registro.resultado = "firma_invalida"
        registro.save(update_fields=["resultado"])
        return JsonResponse({"ok": False, "error": "checksum inválido"}, status=401)

    if registro.evento == "transaction.updated":
        resultado = services.aplicar_transaccion(tx, fuente="webhook")
    else:
        resultado = "ignorado"
    registro.resultado = resultado
    registro.save(update_fields=["resultado"])
    logger.info("wompi_evento id=%s evento=%s tx=%s estado=%s resultado=%s",
                registro.pk, registro.evento, registro.transaccion_id, registro.estado, resultado)
    return JsonResponse({"ok": True, "resultado": resultado})


