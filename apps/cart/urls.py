from django.urls import path

from apps.core.stubs import proximamente

app_name = "cart"
urlpatterns = [
    path("carrito/", proximamente, name="detalle"),
    path("carrito/agregar/<int:producto_id>/", proximamente, name="agregar"),
]
