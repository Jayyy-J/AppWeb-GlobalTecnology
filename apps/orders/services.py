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


# ---------------------------------------------------------------- stock
def descontar_stock(order):
    """Descuenta el stock una sola vez (idempotente vía `stock_descontado`), de forma atómica."""
    with transaction.atomic():
        order = Order.objects.select_for_update().get(pk=order.pk)
        if order.stock_descontado:
            return False
        items = list(order.items.all())
        ids = sorted({i.producto_id for i in items if i.producto_id})
        productos = {p.pk: p for p in Product.objects.select_for_update().filter(pk__in=ids).order_by("pk")}
        faltantes = []
        for it in items:
            p = productos.get(it.producto_id)
            if p is None:
                faltantes.append(f"{it.nombre}: el producto ya no existe")
                continue
            if p.stock < it.cantidad:
                faltantes.append(f"{it.nombre}: pedidas {it.cantidad}, disponibles {p.stock}")
                Product.objects.filter(pk=p.pk).update(stock=0)
            else:
                Product.objects.filter(pk=p.pk).update(stock=F("stock") - it.cantidad)
        order.stock_descontado = True
        campos = ["stock_descontado", "actualizado"]
        if faltantes:
            order.alerta_stock = True
            order.alerta_detalle = (order.alerta_detalle + "\n" if order.alerta_detalle else "") + (
                "Stock insuficiente al aprobar el pago: " + "; ".join(faltantes)
            )
            campos += ["alerta_stock", "alerta_detalle"]
            logger.error("stock_insuficiente pedido=%s detalle=%s", order.numero, "; ".join(faltantes))
        order.save(update_fields=campos)
        return True


def devolver_stock(order):
    with transaction.atomic():
        order = Order.objects.select_for_update().get(pk=order.pk)
        if not order.stock_descontado or order.stock_devuelto:
            return False
        for it in order.items.all():
            if it.producto_id:
                Product.objects.filter(pk=it.producto_id).update(stock=F("stock") + it.cantidad)
        order.stock_devuelto = True
        order.save(update_fields=["stock_devuelto", "actualizado"])
        return True


# ---------------------------------------------------------------- estados
def validar_transicion(order, nuevo, *, foto=None, metodo_entrega=None, transportadora="", entregado_por="",
                       desde_cotizacion=False):
    """Reglas de negocio de cada transición. Lanza TransicionInvalida con mensajes en español."""
    actual = order.estado_pedido
    if nuevo not in TRANSICIONES.get(actual, set()):
        raise TransicionInvalida(
            f"No se puede pasar de «{EstadoPedido(actual).label}» a «{EstadoPedido(nuevo).label}»."
        )
    if nuevo == EstadoPedido.PENDIENTE_PAGO and actual == EstadoPedido.ESPERANDO_COTIZACION and not desde_cotizacion:
        raise TransicionInvalida("Para habilitar el pago ingresa primero la cotización del envío.")
    if nuevo == EstadoPedido.EN_PROCESO and order.estado_pago != EstadoPago.APROBADO:
        raise TransicionInvalida("Solo se puede pasar a «En proceso» cuando el pago está aprobado.")
    if nuevo == EstadoPedido.ENVIADO:
        errores = {}
        if metodo_entrega not in MetodoEntrega.values:
            errores["metodo_entrega"] = "Elige si el envío es por transportadora o entrega personal."
        if not foto:
            errores["foto"] = (
                "Sube la foto de la guía o del flete." if metodo_entrega == MetodoEntrega.TRANSPORTADORA
                else "Sube la foto de la entrega o del paquete listo."
            )
        if metodo_entrega == MetodoEntrega.TRANSPORTADORA and not (transportadora or "").strip():
            errores["transportadora"] = "Indica el nombre de la transportadora."
        if metodo_entrega == MetodoEntrega.PERSONAL and not (entregado_por or "").strip():
            errores["entregado_por"] = "Indica el nombre de quien entrega."
        if errores:
            raise TransicionInvalida(errores)
    if nuevo == EstadoPedido.ENTREGADO and order.metodo_entrega == MetodoEntrega.PERSONAL and not foto:
        raise TransicionInvalida({"foto": "En entregas personales la foto de la entrega es obligatoria."})


def cambiar_estado(order, nuevo, *, usuario=None, nota="", foto=None, metodo_entrega=None, transportadora="",
                   numero_guia="", url_rastreo="", entregado_por="", sistema=False, desde_cotizacion=False, titulo=None):
    """Única puerta para cambiar `estado_pedido`. Valida, guarda, registra el evento y notifica."""
    with transaction.atomic():
        order = Order.objects.select_for_update().get(pk=order.pk)
        validar_transicion(order, nuevo, foto=foto, metodo_entrega=metodo_entrega, transportadora=transportadora,
                           entregado_por=entregado_por, desde_cotizacion=desde_cotizacion)
        if nuevo == EstadoPedido.ENVIADO:
            order.metodo_entrega = metodo_entrega
            if metodo_entrega == MetodoEntrega.TRANSPORTADORA:
                order.transportadora = transportadora.strip()
                order.numero_guia = (numero_guia or "").strip()
                order.url_rastreo = (url_rastreo or "").strip()
                order.entregado_por = ""
            else:
                order.entregado_por = entregado_por.strip()
                order.transportadora = order.numero_guia = order.url_rastreo = ""
        order.estado_pedido = nuevo
        order.save()
        if nuevo == EstadoPedido.CANCELADO:
            devolver_stock(order)
            order.refresh_from_db()
        ev = registrar_evento(order, nuevo, titulo=titulo, nota=nota, foto=foto, usuario=usuario)

    url = url_absoluta(order.get_absolute_url())
    if nuevo == EstadoPedido.ENVIADO:
        adjuntos = []
        if ev.foto:
            try:
                with ev.foto.open("rb") as fh:
                    adjuntos.append(("evidencia-envio.webp", fh.read(), "image/webp"))
            except OSError:
                pass
        send_templated("pedido_enviado", f"Tu pedido {order.numero} va en camino", order.cliente_email,
                       {"pedido": order, "evento": ev, "url_pedido": url}, attachments=adjuntos)
    elif nuevo == EstadoPedido.ENTREGADO:
        send_templated("pedido_entregado", f"Pedido {order.numero} entregado", order.cliente_email,
                       {"pedido": order, "evento": ev, "url_pedido": url})
    logger.info("pedido_estado numero=%s estado=%s usuario=%s", order.numero, nuevo, getattr(usuario, "pk", "sistema"))
    return order


def cancelar(order, usuario=None, nota=""):
    return cambiar_estado(order, EstadoPedido.CANCELADO, usuario=usuario, nota=nota)


def registrar_cotizacion(order, costo_envio: int, nota: str = "", usuario=None):
    """Flujo de cotización manual: fija el envío, recalcula el total y habilita el pago."""
    with transaction.atomic():
        order = Order.objects.select_for_update().get(pk=order.pk)
        if order.estado_pedido != EstadoPedido.ESPERANDO_COTIZACION:
            raise TransicionInvalida("Este pedido no está esperando cotización.")
        order.costo_envio = int(costo_envio)
        order.total = order.subtotal + order.costo_envio
        from apps.core.templatetags.cop import format_cop

        order.regla_envio_aplicada = f"Envío cotizado a {order.envio_municipio}: {format_cop(order.costo_envio)}"
        order.save()
        cambiar_estado(order, EstadoPedido.PENDIENTE_PAGO, usuario=usuario, desde_cotizacion=True,
                       titulo="Envío cotizado · pendiente de pago",
                       nota=(nota or f"Envío cotizado: {format_cop(order.costo_envio)}. Ya puedes pagar tu pedido."))
        order.refresh_from_db()
    url = url_absoluta(order.get_absolute_url())
    send_templated("cotizacion_lista", f"Tu envío está cotizado · Pedido {order.numero}", order.cliente_email,
                   {"pedido": order, "nota": nota, "url_pagar": url, "url_pedido": url})
    return order
