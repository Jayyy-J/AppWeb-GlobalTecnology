import json
from urllib.parse import urlencode

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core import signing
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_POST

from apps.catalog.models import Product

from . import services
from .models import CartItem

SALT = "carrito-pendiente"


def _volver(request, valor, default="/"):
    if valor and url_has_allowed_host_and_scheme(valor, {request.get_host()}, require_https=request.is_secure()):
        return valor
    return default


def _cantidad(valor):
    try:
        return max(1, min(int(valor), 999))
    except (TypeError, ValueError):
        return 1


def _trigger(request, mensaje, tipo="success"):
    return json.dumps({
        "carrito-actualizado": {"count": services.cart_count(request.user)},
        "toast": {"texto": mensaje, "tipo": tipo},
    })


@require_POST
def agregar(request, producto_id):
    producto = get_object_or_404(Product, pk=producto_id)
    cantidad = _cantidad(request.POST.get("cantidad"))
    comprar_ahora = request.POST.get("comprar_ahora") == "1"
    volver = _volver(request, request.POST.get("volver"), producto.get_absolute_url())

    if not request.user.is_authenticated:
        # Se firma la intención para completarla al volver del login (no se puede manipular).
        token = signing.dumps({"p": producto.pk, "c": cantidad, "v": volver, "a": comprar_ahora}, salt=SALT)
        destino = reverse("cart:pendiente", args=[token])
        login_url = f"{reverse('accounts:login')}?{urlencode({'next': destino})}"
        if request.htmx:
            resp = HttpResponse(status=204)
            resp["HX-Redirect"] = login_url
            return resp
        return redirect(login_url)

    try:
        _, mensaje = services.add_item(request.user, producto, cantidad)
        ok = True
    except services.CartError as e:
        mensaje, ok = str(e), False

    if comprar_ahora and ok:
        return redirect("orders:checkout")
    if request.htmx:
        resp = HttpResponse(status=204)
        resp["HX-Trigger"] = _trigger(request, mensaje, "success" if ok else "error")
        return resp
    (messages.success if ok else messages.error)(request, mensaje)
    return redirect(volver)


@login_required
def pendiente(request, token):
    """Completa el 'agregar al carrito' que un visitante pidió antes de iniciar sesión."""
    try:
        data = signing.loads(token, salt=SALT, max_age=60 * 60 * 2)
    except signing.BadSignature:
        messages.error(request, "El enlace expiró. Agrega el producto de nuevo.")
        return redirect("storefront:home")
    producto = Product.objects.filter(pk=data.get("p")).first()
    volver = _volver(request, data.get("v"), "/")
    if producto is None:
        messages.error(request, "El producto ya no existe.")
        return redirect(volver)
    try:
        _, mensaje = services.add_item(request.user, producto, _cantidad(data.get("c")))
        messages.success(request, mensaje)
        if data.get("a"):
            return redirect("orders:checkout")
    except services.CartError as e:
        messages.error(request, str(e))
    return redirect(volver)


def _contexto(request):
    municipio = None
    direccion = request.user.direcciones.select_related("municipio__departamento").filter(es_predeterminada=True).first()
    if direccion:
        municipio = direccion.municipio
    return {"res": services.resumen(request.user, municipio), "direccion": direccion}


@login_required
def detalle(request):
    return render(request, "cart/detalle.html", _contexto(request))


@login_required
@require_POST
def actualizar(request, item_id):
    get_object_or_404(CartItem, pk=item_id, carrito__usuario=request.user)
    accion = request.POST.get("accion")
    item = CartItem.objects.get(pk=item_id)
    cantidad = item.cantidad + (1 if accion == "mas" else -1 if accion == "menos" else 0)
    if accion not in ("mas", "menos"):
        cantidad = _cantidad(request.POST.get("cantidad"))
    _, mensaje = services.update_item(request.user, item_id, cantidad)
    return _respuesta_parcial(request, mensaje)


@login_required
@require_POST
def eliminar(request, item_id):
    services.remove_item(request.user, item_id)
    return _respuesta_parcial(request, "Producto eliminado del carrito.")


def _respuesta_parcial(request, mensaje):
    if request.htmx:
        resp = render(request, "cart/_contenido.html", _contexto(request))
        resp["HX-Trigger"] = _trigger(request, mensaje, "info") if mensaje else json.dumps(
            {"carrito-actualizado": {"count": services.cart_count(request.user)}}
        )
        return resp
    if mensaje:
        messages.info(request, mensaje)
    return redirect("cart:detalle")


@login_required
def contador(request):
    return render(request, "cart/_contador.html", {"cart_count": services.cart_count(request.user)})
