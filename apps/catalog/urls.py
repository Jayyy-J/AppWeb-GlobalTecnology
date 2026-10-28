from django.urls import path

from . import views

app_name = "catalog"
urlpatterns = [
    path("productos/", views.productos, name="productos"),
    path("ofertas/", views.ofertas, name="ofertas"),
    path("buscar/", views.buscar, name="buscar"),
    path("buscar/sugerencias/", views.sugerencias, name="sugerencias"),
    path("categoria/<slug:slug>/", views.categoria, name="categoria"),
    path("marca/<slug:slug>/", views.marca, name="marca"),
    path("producto/<slug:slug>/", views.producto, name="producto"),
]
