from django.shortcuts import get_object_or_404, redirect
from django.urls import path

app_name = "payments"


def iniciar(request, numero):  # provisional (Fase 4)
    from apps.orders.models import Order

    return redirect(get_object_or_404(Order, numero=numero, usuario=request.user).get_absolute_url())


urlpatterns = [
    path("iniciar/<str:numero>/", iniciar, name="iniciar"),
    path("pagar/<str:numero>/", iniciar, name="pagar"),
]
