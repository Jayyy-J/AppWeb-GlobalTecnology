from django.contrib import admin

from .models import AuditLog


@admin.register(AuditLog)
class AuditLogAdmin(admin.ModelAdmin):
    list_display = ["fecha", "usuario", "accion", "modelo", "objeto_repr"]
    list_filter = ["accion", "modelo"]
    search_fields = ["objeto_repr", "usuario__email"]
