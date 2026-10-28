from django.urls import path

from . import views

app_name = "shipping"
urlpatterns = [path("ubicaciones/municipios/", views.municipios, name="municipios")]
