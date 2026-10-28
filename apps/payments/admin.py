from django.contrib import admin

from .models import Payment, WompiEvent


@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
    list_display = ["referencia", "pedido", "monto_centavos", "estado", "metodo", "creado"]
    list_filter = ["estado"]
    search_fields = ["referencia", "transaccion_id", "pedido__numero"]


@admin.register(WompiEvent)
class WompiEventAdmin(admin.ModelAdmin):
    list_display = ["recibido", "evento", "referencia", "estado", "valido", "resultado"]
    list_filter = ["valido", "estado", "resultado"]
    search_fields = ["referencia", "transaccion_id"]
