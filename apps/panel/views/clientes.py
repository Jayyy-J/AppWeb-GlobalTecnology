from django.contrib import messages
from django.core.paginator import Paginator
from django.db.models import Count, Q, Sum
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from apps.accounts.models import User

from .. import audit
from ..permisos import staff_required, superuser_required


@staff_required
def lista(request):
    qs = User.objects.annotate(
        n_pedidos=Count("pedidos", distinct=True),
        total_comprado=Sum("pedidos__total", filter=Q(pedidos__estado_pago="aprobado")),
    ).order_by("-date_joined")
    if q := request.GET.get("q", "").strip():
        qs = qs.filter(Q(email__icontains=q) | Q(first_name__icontains=q) | Q(last_name__icontains=q)
                       | Q(numero_documento__icontains=q) | Q(telefono__icontains=q))
    if request.GET.get("tipo") == "staff":
        qs = qs.filter(is_staff=True)
    elif request.GET.get("tipo") == "inactivos":
        qs = qs.filter(is_active=False)
    return render(request, "panel/clientes/lista.html", {
        "seccion": "clientes", "pagina": Paginator(qs, 25).get_page(request.GET.get("pagina")),
    })


@staff_required
def detalle(request, pk):
    u = get_object_or_404(User, pk=pk)
    pedidos = u.pedidos.order_by("-creado")
    total = pedidos.filter(estado_pago="aprobado").aggregate(t=Sum("total"))["t"] or 0
    return render(request, "panel/clientes/detalle.html", {
        "seccion": "clientes", "cliente": u, "pedidos": pedidos[:50], "total": total,
        "direcciones": u.direcciones.select_related("municipio", "departamento"),
    })


@staff_required
@require_POST
def activar(request, pk):
    u = get_object_or_404(User, pk=pk)
    if u == request.user:
        messages.error(request, "No puedes desactivar tu propia cuenta.")
        return redirect("panel:cliente", pk=pk)
    if u.is_superuser and not request.user.is_superuser:
        messages.error(request, "Solo un superusuario puede desactivar a otro superusuario.")
        return redirect("panel:cliente", pk=pk)
    u.is_active = not u.is_active
    u.save(update_fields=["is_active"])
    audit.registrar(request, "activar" if u.is_active else "desactivar", u)
    messages.success(request, f"Cuenta {'activada' if u.is_active else 'desactivada'}.")
    return redirect("panel:cliente", pk=pk)


@superuser_required
@require_POST
def staff(request, pk):
    u = get_object_or_404(User, pk=pk)
    if u == request.user:
        messages.error(request, "No puedes quitarte el acceso a ti mismo.")
        return redirect("panel:cliente", pk=pk)
    u.is_staff = not u.is_staff
    u.save(update_fields=["is_staff"])
    audit.registrar(request, "dar_staff" if u.is_staff else "quitar_staff", u)
    messages.success(request, f"Acceso al panel {'otorgado' if u.is_staff else 'retirado'}.")
    return redirect("panel:cliente", pk=pk)
