from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin

from .models import Address, User


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    ordering = ["-date_joined"]
    list_display = ["email", "first_name", "last_name", "telefono", "is_staff", "is_active", "date_joined"]
    search_fields = ["email", "first_name", "last_name", "numero_documento"]
    fieldsets = (
        (None, {"fields": ("email", "password")}),
        ("Datos personales", {"fields": ("first_name", "last_name", "telefono", "tipo_documento", "numero_documento")}),
        ("Datos personales (habeas data)", {"fields": ("acepta_tratamiento_datos", "fecha_aceptacion_datos")}),
        ("Permisos", {"fields": ("is_active", "is_staff", "is_superuser", "groups", "user_permissions")}),
        ("Fechas", {"fields": ("last_login", "date_joined")}),
    )
    add_fieldsets = ((None, {"classes": ("wide",), "fields": ("email", "first_name", "last_name", "password1", "password2")}),)


@admin.register(Address)
class AddressAdmin(admin.ModelAdmin):
    list_display = ["usuario", "alias", "municipio", "es_predeterminada"]
    search_fields = ["usuario__email", "direccion"]
    raw_id_fields = ["usuario", "municipio"]
