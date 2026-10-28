from django.contrib import admin

from .models import Brand, Category, Product, ProductImage, SearchLog


class ProductImageInline(admin.TabularInline):
    model = ProductImage
    extra = 0


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = ["nombre", "sku", "precio", "tipo_descuento", "stock", "activo", "destacado"]
    list_filter = ["activo", "destacado", "tipo_descuento", "marca"]
    search_fields = ["nombre", "sku"]
    filter_horizontal = ["categorias"]
    inlines = [ProductImageInline]


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ["nombre", "parent", "orden", "activa", "mostrar_en_menu"]


admin.site.register(Brand)


@admin.register(SearchLog)
class SearchLogAdmin(admin.ModelAdmin):
    list_display = ["termino", "cantidad_busquedas", "cantidad_resultados", "ultima_fecha"]
