from django.urls import path

from apps.core.stubs import proximamente

app_name = "panel"
urlpatterns = [
    path("", proximamente, name="dashboard"),
    path("pedidos/<str:numero>/", proximamente, name="pedido"),
]
