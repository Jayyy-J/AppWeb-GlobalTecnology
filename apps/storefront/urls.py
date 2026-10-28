from django.urls import path

from . import views

app_name = "storefront"
urlpatterns = [
    path("", views.home, name="home"),
    path("paginas/<slug:slug>/", views.legal, name="legal"),
]
