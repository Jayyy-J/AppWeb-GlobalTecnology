from django.contrib import admin

from .models import Order, OrderItem, OrderStatusEvent


class OrderItemInline(admin.TabularInline):
    model = OrderItem
    extra = 0
    raw_id_fields = ["producto"]


class EventInline(admin.TabularInline):
    model = OrderStatusEvent
    extra = 0
    raw_id_fields = ["usuario"]


@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = ["numero", "cliente_nombre", "total", "estado_pago", "estado_pedido", "creado"]
    list_filter = ["estado_pago", "estado_pedido"]
    search_fields = ["numero", "cliente_email", "cliente_nombre", "wompi_referencia"]
    raw_id_fields = ["usuario"]
    inlines = [OrderItemInline, EventInline]
