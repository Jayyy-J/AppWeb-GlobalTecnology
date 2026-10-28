from django.shortcuts import get_object_or_404, render

from .models import Banner, LegalPage


def home(request):
    """Los bloques se calculan de forma perezosa: si el fragmento está en caché no se consulta la BD."""
    from apps.catalog.models import Category, Product

    def ofertas():
        return list(Product.objects.activos().con_descuento().para_listado().filter(stock__gt=0)
                    .order_by("-descuento_pct_db", "-creado")[:10])

    def destacados():
        return list(Product.objects.activos().filter(destacado=True).para_listado().order_by("-creado")[:10])

    def nuevos():
        return list(Product.objects.activos().para_listado().order_by("-nuevo", "-creado")[:10])

    def categorias():
        return list(Category.objects.filter(activa=True, parent__isnull=True).order_by("orden", "nombre")[:12])

    def banners():
        return list(Banner.objects.vigentes())

    return render(request, "storefront/home.html", {
        "ofertas": ofertas, "destacados": destacados, "nuevos": nuevos,
        "categorias_home": categorias, "banners": banners,
    })


def legal(request, slug):
    pagina = get_object_or_404(LegalPage, slug=slug, activa=True)
    return render(request, "storefront/legal.html", {"pagina": pagina})


def robots_txt(request):
    return render(request, "robots.txt", content_type="text/plain")
