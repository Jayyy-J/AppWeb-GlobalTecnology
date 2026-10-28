from django.contrib import messages
from django.db.models import Count, Q
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from apps.catalog.models import Brand, Category, Product
from apps.core.cache import bump

from .. import audit
from ..forms import BrandForm, CategoryForm
from ..permisos import staff_required


@staff_required
def lista(request):
    raices = list(Category.objects.filter(parent__isnull=True).annotate(n=Count("productos")).order_by("orden", "nombre"))
    hijas = {}
    for h in Category.objects.filter(parent__isnull=False).annotate(n=Count("productos")).order_by("orden", "nombre"):
        hijas.setdefault(h.parent_id, []).append(h)
    for r in raices:
        r.lista_hijas = hijas.get(r.pk, [])
    return render(request, "panel/categorias/lista.html", {"seccion": "categorias", "raices": raices})


@staff_required
@require_POST
def ordenar(request):
    ids = [int(i) for i in request.POST.getlist("orden") if i.isdigit()]
    for pos, cid in enumerate(ids):
        Category.objects.filter(pk=cid).update(orden=pos)
    bump("menu", "home")
    audit.registrar(request, "reordenar", modelo="categoría", cambios={"orden": ids})
    return HttpResponse(status=204)


@staff_required
def formulario(request, pk=None):
    cat = get_object_or_404(Category, pk=pk) if pk else None
    form = CategoryForm(request.POST or None, request.FILES or None, instance=cat)
    if request.method == "POST" and form.is_valid():
        c = form.save()
        audit.registrar(request, "editar" if cat else "crear", c, audit.cambios_de_form(form))
        messages.success(request, f"Categoría «{c.nombre}» guardada.")
        return redirect("panel:categorias")
    return render(request, "panel/form_generico.html", {
        "seccion": "categorias", "form": form, "titulo": f"Editar «{cat.nombre}»" if cat else "Nueva categoría",
        "volver": "panel:categorias", "multipart": True,
    })


@staff_required
def eliminar(request, pk):
    cat = get_object_or_404(Category, pk=pk)
    if request.method == "POST":
        audit.registrar(request, "eliminar", cat)
        cat.delete()
        messages.success(request, "Categoría eliminada. Los productos se conservan.")
        return redirect("panel:categorias")
    n = cat.productos.count()
    sub = cat.hijas.count()
    return render(request, "panel/confirmar.html", {
        "seccion": "categorias", "titulo": f"Eliminar «{cat.nombre}»",
        "mensaje": f"Tiene {n} producto(s) asignado(s){f' y {sub} subcategoría(s), que también se eliminarán' if sub else ''}. "
                   "Los productos no se borran, solo dejan de pertenecer a la categoría.",
        "boton": "Eliminar categoría", "volver": "panel:categorias",
    })


@staff_required
def productos(request, pk):
    """Asignar y quitar productos de una categoría."""
    cat = get_object_or_404(Category, pk=pk)
    if request.method == "POST":
        ids = [int(i) for i in request.POST.getlist("producto") if i.isdigit()]
        prods = list(Product.objects.filter(pk__in=ids))
        if request.POST.get("accion") == "quitar":
            cat.productos.remove(*prods)
            for p in prods:
                if p.categoria_principal_id == cat.pk:
                    p.categoria_principal = None
                    p.save(update_fields=["categoria_principal"])
            texto = "quitado"
        else:
            cat.productos.add(*prods)
            if cat.parent_id:
                cat.parent.productos.add(*prods)
            texto = "asignado"
        audit.registrar(request, f"productos_{texto}", cat, {"productos": [p.sku for p in prods]})
        messages.success(request, f"{len(prods)} producto(s) {texto}(s).")
        return redirect("panel:categoria_productos", pk=cat.pk)
    asignados = cat.productos.select_related("marca").order_by("nombre")
    q = request.GET.get("q", "").strip()
    disponibles = Product.objects.exclude(categorias=cat).select_related("marca").order_by("nombre")
    if q:
        disponibles = disponibles.filter(Q(nombre__icontains=q) | Q(sku__icontains=q))
    ctx = {"seccion": "categorias", "cat": cat, "asignados": asignados, "disponibles": disponibles[:50], "q": q}
    if request.htmx and request.headers.get("HX-Target") == "disponibles":
        return render(request, "panel/categorias/_disponibles.html", ctx)
    return render(request, "panel/categorias/productos.html", ctx)


# ---------- Marcas ----------
@staff_required
def marcas(request):
    return render(request, "panel/marcas/lista.html", {
        "seccion": "marcas", "marcas": Brand.objects.annotate(n=Count("productos")).order_by("nombre"),
    })


@staff_required
def marca_form(request, pk=None):
    m = get_object_or_404(Brand, pk=pk) if pk else None
    form = BrandForm(request.POST or None, request.FILES or None, instance=m)
    if request.method == "POST" and form.is_valid():
        obj = form.save()
        audit.registrar(request, "editar" if m else "crear", obj, audit.cambios_de_form(form))
        messages.success(request, f"Marca «{obj.nombre}» guardada.")
        return redirect("panel:marcas")
    return render(request, "panel/form_generico.html", {
        "seccion": "marcas", "form": form, "titulo": f"Editar «{m.nombre}»" if m else "Nueva marca",
        "volver": "panel:marcas", "multipart": True,
    })


@staff_required
def marca_eliminar(request, pk):
    m = get_object_or_404(Brand, pk=pk)
    if request.method == "POST":
        audit.registrar(request, "eliminar", m)
        m.delete()
        messages.success(request, "Marca eliminada. Sus productos quedaron sin marca.")
        return redirect("panel:marcas")
    return render(request, "panel/confirmar.html", {
        "seccion": "marcas", "titulo": f"Eliminar «{m.nombre}»",
        "mensaje": f"{m.productos.count()} producto(s) quedarán sin marca.", "boton": "Eliminar marca", "volver": "panel:marcas",
    })
