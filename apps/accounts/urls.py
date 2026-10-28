from django.contrib.auth import views as auth_views
from django.urls import path

from . import views

app_name = "accounts"

urlpatterns = [
    path("ingresar/", views.IngresarView.as_view(), name="login"),
    path("registro/", views.registro, name="registro"),
    path("salir/", views.salir, name="logout"),
    path("", views.perfil, name="perfil"),
    path("direcciones/", views.direcciones, name="direcciones"),
    path("direcciones/nueva/", views.direccion_form, name="direccion_nueva"),
    path("direcciones/<int:pk>/editar/", views.direccion_form, name="direccion_editar"),
    path("direcciones/<int:pk>/eliminar/", views.direccion_eliminar, name="direccion_eliminar"),
    path("direcciones/<int:pk>/predeterminada/", views.direccion_predeterminada, name="direccion_predeterminada"),
    path("clave/", views.ClaveCambioView.as_view(), name="clave_cambio"),
    path("recuperar/", views.RecuperarView.as_view(), name="recuperar"),
    path("recuperar/enviado/", auth_views.PasswordResetDoneView.as_view(template_name="accounts/recuperar_enviado.html"), name="recuperar_enviado"),
    path("recuperar/<uidb64>/<token>/", views.NuevaClaveView.as_view(), name="recuperar_confirmar"),
    path("recuperar/listo/", auth_views.PasswordResetCompleteView.as_view(template_name="accounts/recuperar_listo.html"), name="recuperar_listo"),
]
