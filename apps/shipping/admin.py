from django.contrib import admin

from .models import Departamento, Municipio, ShippingSettings, ShippingZoneRate

admin.site.register(ShippingSettings)


@admin.register(Departamento)
class DepartamentoAdmin(admin.ModelAdmin):
    list_display = ["codigo", "nombre"]
    search_fields = ["nombre"]


@admin.register(Municipio)
class MunicipioAdmin(admin.ModelAdmin):
    list_display = ["codigo", "nombre", "departamento"]
    list_filter = ["departamento"]
    search_fields = ["nombre", "codigo"]


@admin.register(ShippingZoneRate)
class ShippingZoneRateAdmin(admin.ModelAdmin):
    list_display = ["departamento", "municipio", "valor", "dias_estimados", "activo"]
    list_filter = ["activo", "departamento"]
    raw_id_fields = ["municipio"]
