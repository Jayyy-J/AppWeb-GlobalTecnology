from django.urls import path

from . import views

app_name = "cart"
urlpatterns = [
    path("carrito/", views.detalle, name="detalle"),
    path("carrito/agregar/<int:producto_id>/", views.agregar, name="agregar"),
    path("carrito/agregar-pendiente/<str:token>/", views.pendiente, name="pendiente"),
    path("carrito/item/<int:item_id>/actualizar/", views.actualizar, name="actualizar"),
    path("carrito/item/<int:item_id>/eliminar/", views.eliminar, name="eliminar"),
    path("carrito/contador/", views.contador, name="contador"),
]
