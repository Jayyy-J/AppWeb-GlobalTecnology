from django.urls import path

from . import views

app_name = "orders"
urlpatterns = [
    path("checkout/", views.checkout, name="checkout"),
    path("checkout/resumen/", views.checkout_resumen, name="checkout_resumen"),
    path("cuenta/pedidos/", views.mis_pedidos, name="mis_pedidos"),
    path("cuenta/pedidos/<str:numero>/", views.detalle, name="detalle"),
    path("pedidos/evidencia/<int:pk>/", views.evidencia, name="evidencia"),
]
