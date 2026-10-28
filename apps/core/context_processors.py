from django.conf import settings
from django.core.cache import cache

from apps.core.cache import get_version


def store(request):
    from apps.catalog.templatetags.catalogo import categorias_menu
    from apps.storefront.models import LegalPage, StoreSettings

    menu_version = get_version("menu")
    legales = cache.get_or_set(
        f"legales:{menu_version}", lambda: list(LegalPage.objects.filter(activa=True).only("titulo", "slug")), 60 * 30
    )
    ctx = {
        "tienda": StoreSettings.load(),
        "SITE_URL": settings.SITE_URL,
        "home_version": get_version("home"),
        "menu_version": menu_version,
        "categorias_menu": categorias_menu(),
        "paginas_legales": legales,
        "cart_count": 0,
    }
    user = getattr(request, "user", None)
    if user is not None and user.is_authenticated:
        from apps.cart.services import cart_count

        ctx["cart_count"] = cart_count(user)
    return ctx
