from datetime import datetime

from django.contrib import messages
from django.core.paginator import Paginator
from django.db.models import Prefetch, Q
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from apps.orders import services
from apps.orders.forms import CambioEstadoForm, CotizacionForm
from apps.orders.models import EstadoPago, EstadoPedido, Order, OrderStatusEvent

from .. import audit
from ..permisos import staff_required


def _fecha(valor, fin=False):
    try:
        d = datetime.strptime(valor, "%Y-%m-%d").date()
    except (TypeError, ValueError):
        return None
    t = datetime.max.time() if fin else datetime.min.time()
    return timezone.make_aware(datetime.combine(d, t))


@staff_required
def lista(request):
    g = request.GET
    qs = Order.objects.select_related("usuario").prefetch_related("items").order_by("-creado")
    if q := g.get("q", "").strip():
        qs = qs.filter(Q(numero__icontains=q) | Q(cliente_nombre__icontains=q) | Q(cliente_email__icontains=q)
                       | Q(wompi_referencia__icontains=q) | Q(cliente_numero_documento__icontains=q))
    if e := g.get("estado_pedido"):
        qs = qs.filter(estado_pedido=e)
    if e := g.get("estado_pago"):
        qs = qs.filter(estado_pago=e)
    if g.get("alerta") == "1":
        qs = qs.filter(alerta_stock=True)
    if d := _fecha(g.get("desde")):
        qs = qs.filter(creado__gte=d)
    if h := _fecha(g.get("hasta"), fin=True):
        qs = qs.filter(creado__lte=h)
    pagina = Paginator(qs, 25).get_page(g.get("pagina"))
    ctx = {"seccion": "pedidos", "pagina": pagina, "estados_pedido": EstadoPedido.choices, "estados_pago": EstadoPago.choices}
    if request.htmx and request.headers.get("HX-Target") == "tabla-pedidos":
        return render(request, "panel/pedidos/_tabla.html", ctx)
    return render(request, "panel/pedidos/lista.html", ctx)


def _pedido(numero):
    return get_object_or_404(
        Order.objects.select_related("usuario").prefetch_related(
            "items", "pagos", Prefetch("eventos", queryset=OrderStatusEvent.objects.select_related("usuario").order_by("creado", "id"))
        ),
        numero=numero,
    )


@staff_required
def detalle(request, numero, form_estado=None, form_cotizacion=None):
    order = _pedido(numero)
    return render(request, "panel/pedidos/detalle.html", {
        "seccion": "pedidos", "pedido": order,
        "form_estado": form_estado or CambioEstadoForm(pedido=order),
        "form_cotizacion": form_cotizacion or CotizacionForm(),
        "transportadoras": ["Servientrega", "Interrapidísimo", "Coordinadora", "Envía", "TCC", "Deprisa", "472", "Mensajeros Urbanos"],
    })


@staff_required
@require_POST
def cambiar_estado(request, numero):
    order = _pedido(numero)
    form = CambioEstadoForm(request.POST, request.FILES, pedido=order)
    if not form.is_valid():
        messages.error(request, "Revisa el formulario de cambio de estado.")
        return detalle(request, numero, form_estado=form)
    c = form.cleaned_data
    anterior = order.estado_pedido
    try:
        services.cambiar_estado(
            order, c["estado"], usuario=request.user, nota=c.get("nota", ""), foto=c.get("foto"),
            metodo_entrega=c.get("metodo_entrega") or None, transportadora=c.get("transportadora", ""),
            numero_guia=c.get("numero_guia", ""), url_rastreo=c.get("url_rastreo", ""), entregado_por=c.get("entregado_por", ""),
        )
    except services.TransicionInvalida as e:
        messages.error(request, " ".join(e.messages))
        return redirect("panel:pedido", numero=numero)
    audit.registrar(request, "cambiar_estado", order, {"estado_pedido": [anterior, c["estado"]]})
    messages.success(request, f"Pedido {numero}: estado actualizado a «{EstadoPedido(c['estado']).label}».")
    return redirect("panel:pedido", numero=numero)


@staff_required
@require_POST
def cotizar(request, numero):
    order = _pedido(numero)
    form = CotizacionForm(request.POST)
    if not form.is_valid():
        return detalle(request, numero, form_cotizacion=form)
    try:
        services.registrar_cotizacion(order, form.cleaned_data["costo_envio"], form.cleaned_data["nota"], usuario=request.user)
    except services.TransicionInvalida as e:
        messages.error(request, " ".join(e.messages))
        return redirect("panel:pedido", numero=numero)
    audit.registrar(request, "cotizar_envio", order, {"costo_envio": form.cleaned_data["costo_envio"]})
    messages.success(request, "Cotización registrada. Le enviamos al cliente el enlace para pagar.")
    return redirect("panel:pedido", numero=numero)


@staff_required
@require_POST
def notas(request, numero):
    order = get_object_or_404(Order, numero=numero)
    antes = order.notas_internas
    order.notas_internas = request.POST.get("notas_internas", "")[:5000]
    if request.POST.get("resolver_alerta") == "1":
        order.alerta_stock = False
    order.save(update_fields=["notas_internas", "alerta_stock", "actualizado"])
    audit.registrar(request, "notas_internas", order, {"notas": [antes, order.notas_internas],
                                                        "alerta_resuelta": request.POST.get("resolver_alerta") == "1"})
    if request.htmx:
        return render(request, "panel/pedidos/_notas.html", {"pedido": order, "guardado": True})
    messages.success(request, "Notas guardadas.")
    return redirect("panel:pedido", numero=numero)


@staff_required
def rotulo(request, numero):
    order = _pedido(numero)
    return render(request, "panel/pedidos/rotulo.html", {"pedido": order})
