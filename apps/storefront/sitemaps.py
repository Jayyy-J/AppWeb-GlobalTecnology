from urllib.parse import urlparse

from django.conf import settings
from django.contrib.sitemaps import Sitemap
from django.urls import reverse

from apps.catalog.models import Brand, Category, Product

from .models import LegalPage


class BaseSitemap(Sitemap):
    """Usa el dominio y protocolo de SITE_URL (no requiere django.contrib.sites)."""

    def get_domain(self, site=None):
        return urlparse(settings.SITE_URL).netloc

    def get_protocol(self, protocol=None):
        return urlparse(settings.SITE_URL).scheme or "https"


class EstaticasSitemap(BaseSitemap):
    priority = 1.0
    changefreq = "daily"

    def items(self):
        return ["storefront:home", "catalog:productos", "catalog:ofertas"]

    def location(self, item):
        return reverse(item)


class ProductosSitemap(BaseSitemap):
    changefreq = "weekly"
    priority = 0.8

    def items(self):
        return Product.objects.filter(activo=True).only("slug", "actualizado").order_by("pk")

    def lastmod(self, obj):
        return obj.actualizado


class CategoriasSitemap(BaseSitemap):
    changefreq = "weekly"
    priority = 0.7

    def items(self):
        return Category.objects.filter(activa=True).order_by("pk")

    def lastmod(self, obj):
        return obj.actualizado


class MarcasSitemap(BaseSitemap):
    priority = 0.5

    def items(self):
        return Brand.objects.filter(activa=True).order_by("pk")


class LegalesSitemap(BaseSitemap):
    priority = 0.3
    changefreq = "monthly"

    def items(self):
        return LegalPage.objects.filter(activa=True).order_by("pk")

    def lastmod(self, obj):
        return obj.actualizado


SITEMAPS = {
    "paginas": EstaticasSitemap, "productos": ProductosSitemap, "categorias": CategoriasSitemap,
    "marcas": MarcasSitemap, "legales": LegalesSitemap,
}
