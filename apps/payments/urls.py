from django.urls import path

from . import views

app_name = "payments"
urlpatterns = [
    path("iniciar/<str:numero>/", views.iniciar, name="iniciar"),
    path("pagar/<str:numero>/", views.pagar, name="pagar"),
    path("resultado/", views.resultado, name="resultado"),
    path("wompi/eventos/", views.eventos, name="eventos"),
]
