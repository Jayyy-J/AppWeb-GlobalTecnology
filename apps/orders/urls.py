from django.urls import path

from apps.core.stubs import proximamente

app_name = "orders"
urlpatterns = [path("cuenta/pedidos/", proximamente, name="mis_pedidos")]
