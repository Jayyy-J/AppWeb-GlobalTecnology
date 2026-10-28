from django.contrib import messages
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import F, Prefetch, Q
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from apps.catalog.models import Brand, Category, Product, ProductImage
from apps.catalog.search import update_search_index
from apps.core.text import normalize
from apps.orders.models import OrderItem

from .. import audit
from ..forms import ProductBulkForm, ProductForm
from ..permisos import staff_required

CAMPOS_AUDITADOS = ["nombre", "sku", "precio", "tipo_descuento", "descuento_porcentaje", "precio_antes",
                    "descuento_inicia", "descuento_termina", "stock", "activo", "destacado"]


def _filtrar(request):
    qs = Product.objects.select_related("marca", "categoria_principal").prefetch_related(
        Prefetch("imagenes", queryset=ProductImage.objects.order_by("-es_principal", "orden", "id"))
    )
    g = request.GET
    if q := g.get("q", "").strip():
        nq = normalize(q)
        qs = qs.filter(Q(nombre__icontains=q) | Q(sku__icontains=q) | Q(search_text__contains=nq))
    if c := g.get("categoria"):
        qs = qs.filter(categorias__pk=c).distinct() if c.isdigit() else qs
    if m := g.get("marca"):
        qs = qs.filter(marca_id=m) if m.isdigit() else qs
    estado = g.get("estado")
    if estado == "activos":
        qs = qs.filter(activo=True)
    elif estado == "inactivos":
        qs = qs.filter(activo=False)
    elif estado == "stock_bajo":
        qs = qs.filter(stock__lte=F("stock_minimo_alerta"))
    elif estado == "agotados":
        qs = qs.filter(stock=0)
    elif estado == "descuento":
        qs = qs.exclude(tipo_descuento="ninguno")
    elif estado == "destacados":
        qs = qs.filter(destacado=True)
    orden = g.get("orden", "-creado")
    if orden not in ("-creado", "nombre", "precio", "-precio", "stock", "-stock"):
        orden = "-creado"
    return qs.order_by(orden, "-id")


@staff_required
def lista(request):
    pagina = Paginator(_filtrar(request), 25).get_page(request.GET.get("pagina"))
    ctx = {
        "seccion": "productos", "pagina": pagina, "categorias": Category.objects.select_related("parent").order_by("parent__nombre", "nombre"),
        "marcas": Brand.objects.order_by("nombre"), "acciones": ProductBulkForm.ACCIONES,
    }
    if request.htmx and request.headers.get("HX-Target") == "tabla-productos":
        return render(request, "panel/productos/_tabla.html", ctx)
    return render(request, "panel/productos/lista.html", ctx)


@staff_required
@require_POST
def acciones(request):
    form = ProductBulkForm(request.POST)
    if not form.is_valid():
        for errs in form.errors.values():
            messages.error(request, " ".join(errs))
        return redirect(request.POST.get("volver") or "panel:productos")
    accion, productos = form.cleaned_data["accion"], list(form.cleaned_data["ids"])
    ids = [p.pk for p in productos]
    qs = Product.objects.filter(pk__in=ids)
    cat = form.cleaned_data.get("categoria")
    with transaction.atomic():
        if accion == "activar":
            qs.update(activo=True)
        elif accion == "desactivar":
            qs.update(activo=False)
        elif accion == "destacar":
            qs.update(destacado=True)
        elif accion == "no_destacar":
            qs.update(destacado=False)
        elif accion == "asignar_categoria":
            cat.productos.add(*productos)
            if cat.parent_id:
                cat.parent.productos.add(*productos)
        elif accion == "quitar_categoria":
            cat.productos.remove(*productos)
        elif accion == "aplicar_descuento":
            qs.update(tipo_descuento="porcentaje", descuento_porcentaje=form.cleaned_data["porcentaje"],
                      precio_antes=None, descuento_inicia=None, descuento_termina=None)
        elif accion == "quitar_descuento":
            qs.update(tipo_descuento="ninguno", descuento_porcentaje=None, precio_antes=None)
    update_search_index(ids)
    from apps.core.cache import bump

    bump()
    audit.registrar(request, f"masivo:{accion}", modelo="producto", cambios={
        "productos": [p.sku for p in productos], "categoria": str(cat) if cat else None,
        "porcentaje": form.cleaned_data.get("porcentaje"),
    })
    messages.success(request, f"Acción aplicada a {len(ids)} producto{'s' if len(ids) != 1 else ''}.")
    return redirect(request.POST.get("volver") or "panel:productos")


def _guardar_imagenes(producto, archivos):
    tiene_principal = producto.imagenes.filter(es_principal=True).exists()
    orden = (producto.imagenes.order_by("-orden").values_list("orden", flat=True).first() or 0) + 1
    for i, f in enumerate(archivos):
        ProductImage.objects.create(producto=producto, imagen=f, orden=orden + i,
                                    es_principal=(not tiene_principal and i == 0))


@staff_required
def formulario(request, pk=None):
    producto = get_object_or_404(Product, pk=pk) if pk else None
    antes = audit.snapshot(producto, CAMPOS_AUDITADOS) if producto else {}
    form = ProductForm(request.POST or None, request.FILES or None, instance=producto)
    if request.method == "POST" and form.is_valid():
        with transaction.atomic():
            p = form.save()
            _guardar_imagenes(p, form.cleaned_data.get("imagenes_nuevas") or [])
        update_search_index([p.pk])
        cambios = {k: v for k, v in audit.cambios_de_form(form, antes).items() if k != "imagenes_nuevas"}
        if form.cleaned_data.get("imagenes_nuevas"):
            cambios["imagenes_subidas"] = len(form.cleaned_data["imagenes_nuevas"])
        audit.registrar(request, "editar" if producto else "crear", p, cambios)
        messages.success(request, f"Producto «{p.nombre}» guardado.")
        if request.POST.get("seguir") == "1":
            return redirect("panel:producto_editar", pk=p.pk)
        return redirect("panel:productos")
    imagenes = list(producto.imagenes.order_by("-es_principal", "orden", "id")) if producto else []
    return render(request, "panel/productos/form.html", {
        "seccion": "productos", "form": form, "producto": producto, "imagenes": imagenes,
        "tiene_pedidos": producto and OrderItem.objects.filter(producto=producto).exists(),
    })


@staff_required
@require_POST
def duplicar(request, pk):
    original = get_object_or_404(Product, pk=pk)
    cats = list(original.categorias.all())
    copia = Product.objects.get(pk=pk)
    copia.pk = None
    copia.id = None
    copia.slug = ""
    base_sku = f"{original.sku}-COPIA"
    sku, n = base_sku, 2
    while Product.objects.filter(sku=sku).exists():
        sku, n = f"{base_sku}{n}", n + 1
    copia.sku = sku
    copia.nombre = f"{original.nombre} (copia)"
    copia.activo = False
    copia.search_vector = None
    copia.save()
    copia.categorias.set(cats)
    # Copia las imágenes (los archivos se reutilizan como nuevas subidas para tener nombres propios)
    for im in original.imagenes.all():
        try:
            with im.imagen.open("rb") as fh:
                from django.core.files.uploadedfile import SimpleUploadedFile

                ProductImage.objects.create(
                    producto=copia, imagen=SimpleUploadedFile("copia.webp", fh.read(), content_type="image/webp"),
                    texto_alternativo=im.texto_alternativo, orden=im.orden, es_principal=im.es_principal,
                )
        except OSError:
            continue
    audit.registrar(request, "duplicar", copia, {"original": original.sku})
    messages.success(request, "Producto duplicado. Quedó inactivo para que lo revises antes de publicarlo.")
    return redirect("panel:producto_editar", pk=copia.pk)


@staff_required
def eliminar(request, pk):
    producto = get_object_or_404(Product, pk=pk)
    tiene_pedidos = OrderItem.objects.filter(producto=producto).exists()
    if request.method == "POST":
        if tiene_pedidos:
            producto.activo = False
            producto.save(update_fields=["activo", "actualizado"])
            audit.registrar(request, "desactivar (tiene pedidos)", producto)
            messages.info(request, f"«{producto.nombre}» tiene pedidos: se desactivó en lugar de borrarse para conservar el historial.")
        else:
            audit.registrar(request, "eliminar", producto, {"sku": producto.sku})
            for im in producto.imagenes.all():
                im.delete()
            producto.delete()
            messages.success(request, "Producto eliminado.")
        return redirect("panel:productos")
    return render(request, "panel/confirmar.html", {
        "seccion": "productos", "titulo": f"Eliminar «{producto.nombre}»",
        "mensaje": ("Este producto tiene pedidos asociados, así que se desactivará en lugar de borrarse."
                    if tiene_pedidos else "Esta acción no se puede deshacer. Se borrarán también sus fotos."),
        "boton": "Desactivar" if tiene_pedidos else "Eliminar definitivamente", "volver": "panel:productos",
    })


# ---------- Imágenes (HTMX) ----------
def _galeria(request, producto):
    return render(request, "panel/productos/_galeria.html", {
        "producto": producto, "imagenes": list(producto.imagenes.order_by("-es_principal", "orden", "id")),
    })


@staff_required
@require_POST
def imagenes_subir(request, pk):
    from ..forms import MultipleImageField
    from django import forms as djforms

    producto = get_object_or_404(Product, pk=pk)
    try:
        archivos = MultipleImageField().clean(request.FILES.getlist("imagenes"))
    except djforms.ValidationError as e:
        resp = _galeria(request, producto)
        resp["HX-Trigger"] = '{"toast": {"texto": "%s", "tipo": "error"}}' % " ".join(e.messages).replace('"', "'")
        return resp
    _guardar_imagenes(producto, archivos)
    audit.registrar(request, "subir_fotos", producto, {"cantidad": len(archivos)})
    return _galeria(request, producto)


@staff_required
@require_POST
def imagenes_orden(request, pk):
    producto = get_object_or_404(Product, pk=pk)
    ids = [int(i) for i in request.POST.getlist("orden") if i.isdigit()]
    for pos, img_id in enumerate(ids):
        ProductImage.objects.filter(pk=img_id, producto=producto).update(orden=pos)
    return HttpResponse(status=204)


@staff_required
@require_POST
def imagen_principal(request, img_id):
    im = get_object_or_404(ProductImage, pk=img_id)
    im.es_principal = True
    im.save()
    return _galeria(request, im.producto)


@staff_required
@require_POST
def imagen_eliminar(request, img_id):
    im = get_object_or_404(ProductImage, pk=img_id)
    producto = im.producto
    era_principal = im.es_principal
    im.delete()
    if era_principal:
        otra = producto.imagenes.order_by("orden", "id").first()
        if otra:
            otra.es_principal = True
            otra.save()
    audit.registrar(request, "eliminar_foto", producto)
    return _galeria(request, producto)


@staff_required
@require_POST
def imagen_alt(request, img_id):
    im = get_object_or_404(ProductImage, pk=img_id)
    im.texto_alternativo = request.POST.get("texto_alternativo", "")[:200]
    im.save(update_fields=["texto_alternativo"])
    return HttpResponse(status=204)
