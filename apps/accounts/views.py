from django.contrib import messages
from django.contrib.auth import login
from django.contrib.auth import views as auth_views
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse, reverse_lazy
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_POST

from apps.core.emails import send_templated

from .forms import (AddressForm, ClaveCambioForm, LoginForm, NuevaClaveForm,
                    PerfilForm, RecuperarForm, RegistroForm)
from .models import Address


def _safe_next(request, default=None):
    nxt = request.POST.get("next") or request.GET.get("next")
    if nxt and url_has_allowed_host_and_scheme(nxt, {request.get_host()}, require_https=request.is_secure()):
        return nxt
    return default or reverse("storefront:home")


class IngresarView(auth_views.LoginView):
    template_name = "accounts/login.html"
    authentication_form = LoginForm
    redirect_authenticated_user = True

    def form_valid(self, form):
        resp = super().form_valid(form)
        messages.success(self.request, f"¡Hola, {form.get_user().nombre_corto}!")
        return resp


def registro(request):
    if request.user.is_authenticated:
        return redirect(_safe_next(request))
    form = RegistroForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        user = form.save()
        login(request, user, backend="apps.accounts.backends.EmailBackend")
        send_templated("bienvenida", "¡Bienvenido a GlobalTecnology!", user.email, {"usuario": user})
        messages.success(request, "Tu cuenta fue creada. ¡Bienvenido!")
        return redirect(_safe_next(request))
    return render(request, "accounts/registro.html", {"form": form, "next": request.GET.get("next", "")})


@require_POST
def salir(request):
    from django.contrib.auth import logout

    logout(request)
    messages.info(request, "Cerraste sesión.")
    return redirect("storefront:home")


@login_required
def perfil(request):
    form = PerfilForm(request.POST or None, instance=request.user)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Tus datos se actualizaron.")
        return redirect("accounts:perfil")
    return render(request, "accounts/perfil.html", {"form": form, "seccion": "perfil"})


@login_required
def direcciones(request):
    return render(request, "accounts/direcciones.html", {
        "direcciones": request.user.direcciones.select_related("municipio", "departamento"),
        "seccion": "direcciones",
    })


@login_required
def direccion_form(request, pk=None):
    instance = get_object_or_404(Address, pk=pk, usuario=request.user) if pk else Address(usuario=request.user)
    form = AddressForm(request.POST or None, instance=instance)
    if request.method == "POST" and form.is_valid():
        addr = form.save(commit=False)
        addr.usuario = request.user
        addr.save()
        messages.success(request, "Dirección guardada.")
        return redirect(_safe_next(request, reverse("accounts:direcciones")))
    return render(request, "accounts/direccion_form.html", {
        "form": form, "direccion": instance if pk else None, "seccion": "direcciones",
        "next": request.GET.get("next", ""),
    })


@login_required
@require_POST
def direccion_eliminar(request, pk):
    addr = get_object_or_404(Address, pk=pk, usuario=request.user)
    era_pred = addr.es_predeterminada
    addr.delete()
    if era_pred:
        otra = request.user.direcciones.first()
        if otra:
            otra.es_predeterminada = True
            otra.save()
    messages.info(request, "Dirección eliminada.")
    return redirect("accounts:direcciones")


@login_required
@require_POST
def direccion_predeterminada(request, pk):
    addr = get_object_or_404(Address, pk=pk, usuario=request.user)
    addr.es_predeterminada = True
    addr.save()
    return redirect("accounts:direcciones")


class ClaveCambioView(auth_views.PasswordChangeView):
    template_name = "accounts/clave_cambio.html"
    form_class = ClaveCambioForm
    success_url = reverse_lazy("accounts:perfil")

    def form_valid(self, form):
        messages.success(self.request, "Tu contraseña fue actualizada.")
        return super().form_valid(form)

    def get_context_data(self, **kwargs):
        return {**super().get_context_data(**kwargs), "seccion": "clave"}


class RecuperarView(auth_views.PasswordResetView):
    template_name = "accounts/recuperar.html"
    form_class = RecuperarForm
    success_url = reverse_lazy("accounts:recuperar_enviado")

    def form_valid(self, form):
        from django.conf import settings
        from urllib.parse import urlparse

        url = urlparse(settings.SITE_URL)
        self.extra_email_context = {"site_url": settings.SITE_URL}
        self.domain_override = url.netloc
        return super().form_valid(form)

    def get_form_kwargs(self):
        return super().get_form_kwargs()


class NuevaClaveView(auth_views.PasswordResetConfirmView):
    template_name = "accounts/nueva_clave.html"
    form_class = NuevaClaveForm
    success_url = reverse_lazy("accounts:recuperar_listo")
