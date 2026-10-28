from django.contrib import admin

from .models import Banner, LegalPage, StoreSettings

admin.site.register(StoreSettings)


@admin.register(Banner)
class BannerAdmin(admin.ModelAdmin):
    list_display = ["titulo", "orden", "activo", "inicia", "termina"]


@admin.register(LegalPage)
class LegalPageAdmin(admin.ModelAdmin):
    list_display = ["titulo", "slug", "activa", "borrador_revision"]
    prepopulated_fields = {"slug": ["titulo"]}
