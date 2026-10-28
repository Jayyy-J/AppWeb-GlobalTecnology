from django.conf import settings
from django.core.paginator import EmptyPage, Paginator
from django.db.models import Prefetch
from django.http import Http404
from django.shortcuts import get_object_or_404, render
from django.views.decorators.http import require_GET

from . import filters as flt
from .models import Brand, Category, Product, ProductImage
from .search import did_you_mean, log_search, suggestions

POR_PAGINA = 24


def _listado(request, *, base_qs, titulo, contexto_extra=None, plantilla="catalog/listado.html", registrar_busqueda=False):
    f = flt.Filtros.desde_request(request.GET)
    base_qs = base_qs.con_precios()
    qs = flt.ordenar(flt.aplicar(base_qs, f), f)

    paginator = Paginator(qs.para_listado(), POR_PAGINA)
    try:
        pagina = paginator.page(int(request.GET.get("pagina") or 1))
    except (EmptyPage, ValueError):
        pagina = paginator.page(1)

    ctx = {
        "titulo": titulo,
        "f": f,
        "pagina": pagina,
        "productos": pagina.object_list,
        "total": paginator.count,
        "ordenes": flt.ORDENES,
    }
    # "Cargar más": solo las tarjetas nuevas y el siguiente botón
    if request.htmx and request.headers.get("HX-Target") == "mas-productos":
        return render(request, "catalog/_items.html", ctx)

    fac = flt.facetas(base_qs, f, categoria=(contexto_extra or {}).get("categoria"))
    nombres_marca = {m["marca__slug"]: m["marca__nombre"] for m in fac["marcas"]}
    nombres_sub = {s["categorias__slug"]: s["categorias__nombre"] for s in fac["subcategorias"]}
    ctx.update({
        "facetas": fac,
        "chips": flt.chips(f, request, nombres_marca, nombres_sub),
        "hay_filtros": flt.hay_filtros(f),
        **(contexto_extra or {}),
    })
    if f.q and registrar_busqueda and not request.GET.get("pagina"):
        log_search(f.q, paginator.count)
    if f.q and paginator.count == 0:
        sugerido = did_you_mean(f.q)
        ctx["quisiste_decir"] = sugerido
        ctx["sugeridos"] = list(
            Product.objects.activos().con_precios().para_listado().filter(stock__gt=0)
            .order_by("-destacado", "-descuento_pct_db")[:8]
        )
    if request.htmx and request.headers.get("HX-Target") == "zona-listado":
        return render(request, "catalog/_zona_listado.html", ctx)
    return render(request, plantilla, ctx)


@require_GET
def productos(request):
    return _listado(request, base_qs=Product.objects.activos(), titulo="Todos los productos")


@require_GET
def ofertas(request):
    return _listado(
        request, base_qs=Product.objects.activos().con_descuento(), titulo="Ofertas del día",
        contexto_extra={"descripcion": "Productos con descuento por tiempo limitado."},
    )


@require_GET
def buscar(request):
    q = request.GET.get("q", "").strip()
    base = Product.objects.activos()
    cat_slug = request.GET.get("categoria")
    categoria = None
    if cat_slug:
        categoria = Category.objects.filter(slug=cat_slug, activa=True).first()
        if categoria:
            base = base.filter(categorias__in=categoria.ids_con_hijas()).distinct()
    titulo = f'Resultados para "{q}"' if q else "Buscar"
    return _listado(
        request, base_qs=base, titulo=titulo, registrar_busqueda=True,
        contexto_extra={"es_busqueda": True, "categoria_busqueda": categoria},
    )


@require_GET
def categoria(request, slug):
    cat = get_object_or_404(Category.objects.select_related("parent"), slug=slug, activa=True)
    base = Product.objects.activos().filter(categorias__in=cat.ids_con_hijas()).distinct()
    migas = [(cat.parent.nombre, cat.parent.get_absolute_url())] if cat.parent_id else []
    return _listado(
        request, base_qs=base, titulo=cat.nombre,
        contexto_extra={
            "categoria": cat, "descripcion": cat.descripcion, "migas": migas,
            "subcategorias_nav": list(cat.hijas.filter(activa=True)) if not cat.parent_id else
            list(cat.parent.hijas.filter(activa=True)),
        },
    )


@require_GET
def marca(request, slug):
    m = get_object_or_404(Brand, slug=slug, activa=True)
    return _listado(request, base_qs=Product.objects.activos().filter(marca=m), titulo=m.nombre, contexto_extra={"marca": m})


@require_GET
def sugerencias(request):
    q = request.GET.get("q", "").strip()[:100]
    if len(q) < 2:
        return render(request, "catalog/_sugerencias.html", {"q": q, "vacio": True})
    data = suggestions(q)
    return render(request, "catalog/_sugerencias.html", {"q": q, **data})


@require_GET
def producto(request, slug):
    qs = Product.objects.select_related("marca", "categoria_principal", "categoria_principal__parent").prefetch_related(
        Prefetch("imagenes", queryset=ProductImage.objects.order_by("-es_principal", "orden", "id"))
    )
    p = get_object_or_404(qs, slug=slug)
    if not p.activo and not request.user.is_staff:
        raise Http404
    relacionados = []
    if p.categoria_principal_id:
        relacionados = list(
            Product.objects.activos().filter(categorias=p.categoria_principal_id).exclude(pk=p.pk)
            .para_listado().order_by("-destacado", "-creado")[:8]
        )
    migas = []
    if p.categoria_principal_id:
        cp = p.categoria_principal
        if cp.parent_id:
            migas.append((cp.parent.nombre, cp.parent.get_absolute_url()))
        migas.append((cp.nombre, cp.get_absolute_url()))
    imagenes = list(p.imagenes.all())
    url = settings.SITE_URL + p.get_absolute_url()
    json_ld = {
        "@context": "https://schema.org/",
        "@type": "Product",
        "name": p.nombre,
        "sku": p.sku,
        "description": p.descripcion_corta or p.nombre,
        "image": [settings.SITE_URL + im.imagen.url for im in imagenes],
        "url": url,
        "offers": {
            "@type": "Offer",
            "priceCurrency": "COP",
            "price": str(p.precio_final),
            "availability": "https://schema.org/InStock" if p.disponible else "https://schema.org/OutOfStock",
            "itemCondition": "https://schema.org/NewCondition",
            "url": url,
        },
    }
    if p.marca_id:
        json_ld["brand"] = {"@type": "Brand", "name": p.marca.nombre}
    return render(request, "catalog/producto.html", {
        "p": p, "imagenes": imagenes, "relacionados": relacionados, "migas": migas, "json_ld": json_ld,
        "especificaciones": sorted((p.especificaciones or {}).items()),
    })

