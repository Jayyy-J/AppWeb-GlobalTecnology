from django import template
from django.core.cache import cache
from django.template.loader import render_to_string

from apps.core.cache import get_version

register = template.Library()


def categorias_menu():
    """Categorías raíz del menú con sus hijas (cacheado; se invalida al guardar desde el panel)."""
    from apps.catalog.models import Category

    def build():
        raices = list(
            Category.objects.filter(activa=True, mostrar_en_menu=True, parent__isnull=True).order_by("orden", "nombre")
        )
        hijas = {}
        for h in Category.objects.filter(activa=True, mostrar_en_menu=True, parent__isnull=False).order_by("orden", "nombre"):
            hijas.setdefault(h.parent_id, []).append(h)
        for r in raices:
            r.hijas_menu = hijas.get(r.id, [])
        return raices

    return cache.get_or_set(f"menu:categorias:{get_version('menu')}", build, 60 * 30)


@register.simple_tag(takes_context=True)
def menu_categorias_html(context, variante="barra"):
    """Fragmento cacheado del menú de categorías."""
    key = f"frag:menu:{variante}:{get_version('menu')}"
    html = cache.get(key)
    if html is None:
        html = render_to_string("partials/menu_categorias.html", {"categorias": categorias_menu(), "variante": variante})
        cache.set(key, html, 60 * 30)
    from django.utils.safestring import mark_safe

    return mark_safe(html)


@register.inclusion_tag("catalog/_tarjeta.html", takes_context=True)
def tarjeta_producto(context, producto, prioridad=False):
    return {"p": producto, "prioridad": prioridad, "request": context.get("request"), "user": context.get("user")}
