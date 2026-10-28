from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db.models import Prefetch
from django.http import FileResponse, Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.cache import never_cache

from apps.accounts.forms import AddressForm
from apps.cart.services import resumen
from apps.shipping.models import Municipio

from . import services
from .forms import CheckoutForm
from .models import Order, OrderStatusEvent


def _municipio_desde(request, direcciones):
    """Municipio para calcular el envío según la dirección elegida (o la nueva)."""
    sel = request.GET.get("direccion") or request.POST.get("direccion")
    if sel == "nueva":
        mid = request.GET.get("nueva-municipio") or request.POST.get("nueva-municipio")
        if mid and str(mid).isdigit():
            return Municipio.objects.select_related("departamento").filter(pk=mid).first(), None
        return None, None
    d = None
    if sel and str(sel).isdigit():
        d = next((x for x in direcciones if x.pk == int(sel)), None)
    if d is None and sel != "nueva":
        d = next((x for x in direcciones if x.es_predeterminada), None) or (direcciones[0] if direcciones else None)
    return (d.municipio if d else None), d


@login_required
@never_cache
def checkout(request):
    user = request.user
    direcciones = list(user.direcciones.select_related("municipio__departamento", "departamento"))
    res = resumen(user)
    if res.vacio:
        messages.info(request, "Tu carrito está vacío.")
        return redirect("cart:detalle")
    if res.problemas:
        messages.warning(request, "Revisa tu carrito: algunos productos cambiaron de disponibilidad.")
        return redirect("cart:detalle")

    inicial = {
        "first_name": user.first_name, "last_name": user.last_name, "email": user.email, "telefono": user.telefono,
        "tipo_documento": user.tipo_documento, "numero_documento": user.numero_documento,
    }
    form = CheckoutForm(request.POST or None, initial=inicial, user=user)
    addr_form = AddressForm(request.POST if request.POST.get("direccion") == "nueva" else None, prefix="nueva")
    municipio, direccion = _municipio_desde(request, direcciones)
    seleccion = request.POST.get("direccion") or (str(direccion.pk) if direccion else ("nueva" if not direcciones else ""))

    if request.method == "POST":
        valido = form.is_valid()
        if seleccion == "nueva":
            valido = addr_form.is_valid() and valido
        elif direccion is None:
            messages.error(request, "Selecciona o crea una dirección de envío.")
            valido = False
        if valido:
            if seleccion == "nueva":
                direccion = addr_form.save(commit=False)
                direccion.usuario = user
                direccion.save()
            from apps.shipping.services import cotizar_envio

            quote = cotizar_envio(res.subtotal, direccion.municipio)
            try:
                order = services.crear_pedido(user, direccion, form.cleaned_data, quote)
            except services.CheckoutError as e:
                messages.error(request, str(e))
                return redirect("cart:detalle")
            if order.estado_pedido == "esperando_cotizacion":
                messages.success(request, f"Pedido {order.numero} confirmado. Te enviaremos el valor del envío por email.")
                return redirect(order.get_absolute_url())
            return redirect("payments:iniciar", numero=order.numero)

    if municipio is not None:
        res = resumen(user, municipio)
    return render(request, "orders/checkout.html", {
        "form": form, "addr_form": addr_form, "direcciones": direcciones, "seleccion": seleccion,
        "res": res, "direccion": direccion,
    })


@login_required
def checkout_resumen(request):
    direcciones = list(request.user.direcciones.select_related("municipio__departamento"))
    municipio, direccion = _municipio_desde(request, direcciones)
    res = resumen(request.user, municipio)
    return render(request, "orders/_resumen_checkout.html", {"res": res, "direccion": direccion})


@login_required
def mis_pedidos(request):
    qs = Order.objects.filter(usuario=request.user).prefetch_related("items").order_by("-creado")
    pagina = Paginator(qs, 10).get_page(request.GET.get("pagina"))
    return render(request, "orders/mis_pedidos.html", {"pagina": pagina, "seccion": "pedidos"})


def _pedido_del_usuario(request, numero):
    """Un cliente solo ve sus pedidos; el staff ve todos."""
    qs = Order.objects.prefetch_related(
        "items", Prefetch("eventos", queryset=OrderStatusEvent.objects.filter(visible_cliente=True).order_by("creado", "id"))
    )
    if request.user.is_staff:
        return get_object_or_404(qs, numero=numero)
    return get_object_or_404(qs, numero=numero, usuario=request.user)


@login_required
def detalle(request, numero):
    order = _pedido_del_usuario(request, numero)
    pasos = ["en_proceso", "enviado", "entregado"]
    orden_estados = ["esperando_cotizacion", "pendiente_pago", *pasos]
    idx = orden_estados.index(order.estado_pedido) if order.estado_pedido in orden_estados else -1
    progreso = [
        {"clave": p, "nombre": {"en_proceso": "En proceso", "enviado": "Enviado", "entregado": "Entregado"}[p],
         "hecho": idx >= orden_estados.index(p)}
        for p in pasos
    ]
    return render(request, "orders/detalle.html", {
        "pedido": order, "eventos": order.eventos.all(), "progreso": progreso, "seccion": "pedidos",
    })


@login_required
def evidencia(request, pk):
    """Sirve una foto de evidencia solo al dueño del pedido o al staff (nunca pública)."""
    ev = get_object_or_404(OrderStatusEvent.objects.select_related("pedido"), pk=pk)
    if not (request.user.is_staff or (ev.pedido.usuario_id == request.user.id and ev.visible_cliente)):
        raise Http404
    if not ev.foto:
        raise Http404
    try:
        f = ev.foto.open("rb")
    except FileNotFoundError:
        raise Http404
    resp = FileResponse(f, content_type="image/webp")
    resp["Cache-Control"] = "private, max-age=3600"
    resp["X-Content-Type-Options"] = "nosniff"
    return resp
