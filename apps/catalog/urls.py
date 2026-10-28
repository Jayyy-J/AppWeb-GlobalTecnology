from django.urls import path

from apps.core.stubs import proximamente

app_name = "catalog"
urlpatterns = [
    path("productos/", proximamente, name="productos"),
    path("ofertas/", proximamente, name="ofertas"),
    path("buscar/", proximamente, name="buscar"),
    path("buscar/sugerencias/", proximamente, name="sugerencias"),
    path("categoria/<slug:slug>/", proximamente, name="categoria"),
    path("marca/<slug:slug>/", proximamente, name="marca"),
    path("producto/<slug:slug>/", proximamente, name="producto"),
]
