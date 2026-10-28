"""Lógica de pedidos: creación desde el carrito, máquina de estados, stock y cotización."""
import logging

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import F
from django.urls import reverse
from django.utils import timezone

from apps.catalog.models import Product
from apps.core.emails import send_templated

from .models import EstadoPago, EstadoPedido, MetodoEntrega, Order, OrderItem, OrderStatusEvent

logger = logging.getLogger("orders")

TITULOS = {
    EstadoPedido.ESPERANDO_COTIZACION: "Esperando cotización de envío",
    EstadoPedido.PENDIENTE_PAGO: "Pedido recibido · pendiente de pago",
    EstadoPedido.EN_PROCESO: "Pago aprobado · en proceso",
    EstadoPedido.ENVIADO: "Pedido enviado",
    EstadoPedido.ENTREGADO: "Pedido entregado",
    EstadoPedido.CANCELADO: "Pedido cancelado",
}

# Máquina de estados: único lugar donde se definen las transiciones válidas.
TRANSICIONES = {
    EstadoPedido.ESPERANDO_COTIZACION: {EstadoPedido.PENDIENTE_PAGO, EstadoPedido.CANCELADO},
    EstadoPedido.PENDIENTE_PAGO: {EstadoPedido.EN_PROCESO, EstadoPedido.CANCELADO},
    EstadoPedido.EN_PROCESO: {EstadoPedido.ENVIADO, EstadoPedido.CANCELADO},
    EstadoPedido.ENVIADO: {EstadoPedido.ENTREGADO},
    EstadoPedido.ENTREGADO: set(),
    EstadoPedido.CANCELADO: set(),
}


class TransicionInvalida(ValidationError):
    pass


def url_absoluta(path):
    return f"{settings.SITE_URL}{path}"


def transiciones_posibles(order):
    return sorted(TRANSICIONES.get(order.estado_pedido, set()), key=lambda e: list(EstadoPedido.values).index(e))


# ---------------------------------------------------------------- creación
class CheckoutError(Exception):
    pass


@transaction.atomic
def crear_pedido(user, direccion, contacto: dict, quote):
    """Crea el pedido desde el carrito revalidando stock y precios en el servidor.

    `quote` es el ShippingQuote calculado para el municipio de la dirección.
    No descuenta stock: eso ocurre solo cuando el pago es aprobado.
    """
    from apps.cart.services import resumen

    if not quote.disponible:
        raise CheckoutError(quote.regla)
    res = resumen(user)
    if res.vacio:
        raise CheckoutError("Tu carrito está vacío.")
    # Bloquea las filas de producto para leer stock/precio consistentes
    ids = [l.producto.pk for l in res.lineas]
    productos = {p.pk: p for p in Product.objects.select_for_update().filter(pk__in=ids).order_by("pk")}
    for l in res.lineas:
        p = productos[l.producto.pk]
        if not p.activo or p.stock < l.cantidad:
            raise CheckoutError(f"No hay stock suficiente de {p.nombre}. Revisa tu carrito.")
    # Recalcular el envío con el subtotal definitivo
    from apps.shipping.services import cotizar_envio

    quote = cotizar_envio(sum(productos[l.producto.pk].precio_final * l.cantidad for l in res.lineas), direccion.municipio)
    if not quote.disponible:
        raise CheckoutError(quote.regla)

    cotizacion = quote.requiere_cotizacion
    order = Order(
        usuario=user,
        cliente_nombre=f"{contacto['first_name']} {contacto['last_name']}".strip(),
        cliente_email=contacto["email"],
        cliente_telefono=contacto["telefono"],
        cliente_tipo_documento=contacto["tipo_documento"],
        cliente_numero_documento=contacto["numero_documento"],
        envio_nombre=direccion.nombre_recibe,
        envio_telefono=direccion.telefono,
        envio_departamento=direccion.departamento.nombre,
        envio_municipio=direccion.municipio.nombre,
        envio_municipio_codigo=direccion.municipio.codigo,
        envio_direccion=direccion.direccion,
        envio_barrio=direccion.barrio,
        envio_indicaciones=direccion.indicaciones,
        regla_envio_aplicada=quote.regla,
        envio_dias_estimados=quote.dias,
        costo_envio=quote.valor or 0,
        notas_cliente=contacto.get("notas_cliente", ""),
        estado_pedido=EstadoPedido.ESPERANDO_COTIZACION if cotizacion else EstadoPedido.PENDIENTE_PAGO,
        estado_pago=EstadoPago.PENDIENTE,
    )
    order.save()
    order.numero = f"GT-{timezone.localdate().year}-{order.pk:06d}"
    subtotal = ahorro = 0
    items = []
    for l in res.lineas:
        p = productos[l.producto.pk]
        img = l.producto.imagen_principal
        precio = p.precio_final
        items.append(OrderItem(
            pedido=order, producto=p, nombre=p.nombre, sku=p.sku, imagen=img.url_thumb if img else "",
            precio_unitario=precio, precio_antes=p.precio_tachado, cantidad=l.cantidad, subtotal=precio * l.cantidad,
        ))
        subtotal += precio * l.cantidad
        ahorro += (p.precio_tachado - precio) * l.cantidad if p.precio_tachado else 0
    OrderItem.objects.bulk_create(items)
    order.subtotal, order.descuentos = subtotal, ahorro
    order.total = subtotal + order.costo_envio
    order.save()
    registrar_evento(order, order.estado_pedido, usuario=user, nota=(
        "Te enviaremos el valor del envío por email para que puedas pagar." if cotizacion else ""
    ))
    # Completar el perfil con los datos de contacto si faltaban (Wompi los usa para PSE)
    cambios = []
    for campo in ("telefono", "numero_documento", "tipo_documento"):
        if not getattr(user, campo) and contacto.get(campo):
            setattr(user, campo, contacto[campo])
            cambios.append(campo)
    if cambios:
        user.save(update_fields=cambios)

    url = url_absoluta(order.get_absolute_url())
    transaction.on_commit(lambda: send_templated(
        "pedido_recibido", f"Recibimos tu pedido {order.numero}", order.cliente_email, {"pedido": order, "url_pedido": url}
    ))
    if cotizacion:
        transaction.on_commit(lambda: send_templated(
            "admin_cotizacion", f"Cotizar envío del pedido {order.numero}", settings.ADMIN_NOTIFY_EMAIL,
            {"pedido": order, "url_panel": url_absoluta(reverse("panel:pedido", args=[order.numero]))},
        ))
    logger.info("pedido_creado numero=%s total=%s estado=%s", order.numero, order.total, order.estado_pedido)
    return order


# ---------------------------------------------------------------- eventos
def registrar_evento(order, estado, titulo=None, nota="", foto=None, usuario=None, visible=True):
    ev = OrderStatusEvent(
        pedido=order, estado=estado, titulo=titulo or TITULOS.get(estado, str(estado)), nota=nota or "",
        usuario=usuario, visible_cliente=visible,
    )
    if foto:
        ev.foto = foto
    ev.save()
    return ev
