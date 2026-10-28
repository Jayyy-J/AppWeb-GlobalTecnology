from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect, render

from apps.storefront.models import Banner, LegalPage, StoreSettings

from .. import audit
from ..forms import BannerForm, LegalPageForm, StoreSettingsForm
from ..permisos import staff_required


@staff_required
def tienda(request):
    obj = StoreSettings.objects.get_or_create(pk=1)[0]
    form = StoreSettingsForm(request.POST or None, request.FILES or None, instance=obj)
    if request.method == "POST" and form.is_valid():
        form.save()
        audit.registrar(request, "configurar_tienda", obj, audit.cambios_de_form(form))
        messages.success(request, "Configuración de la tienda guardada.")
        return redirect("panel:tienda")
    return render(request, "panel/form_generico.html", {
        "seccion": "contenido", "form": form, "titulo": "Configuración de la tienda", "multipart": True,
        "ayuda": "Logo, WhatsApp, redes sociales, barra de anuncios y datos legales que se muestran en la tienda.",
    })


@staff_required
def banners(request):
    return render(request, "panel/contenido/banners.html", {"seccion": "contenido", "banners": Banner.objects.all()})


@staff_required
def banner_form(request, pk=None):
    b = get_object_or_404(Banner, pk=pk) if pk else None
    form = BannerForm(request.POST or None, request.FILES or None, instance=b)
    if request.method == "POST" and form.is_valid():
        obj = form.save()
        audit.registrar(request, "editar" if b else "crear", obj, audit.cambios_de_form(form))
        messages.success(request, "Banner guardado.")
        return redirect("panel:banners")
    return render(request, "panel/form_generico.html", {
        "seccion": "contenido", "form": form, "titulo": "Editar banner" if b else "Nuevo banner",
        "volver": "panel:banners", "multipart": True,
    })


@staff_required
def banner_eliminar(request, pk):
    b = get_object_or_404(Banner, pk=pk)
    if request.method == "POST":
        audit.registrar(request, "eliminar", b)
        b.delete()
        messages.success(request, "Banner eliminado.")
        return redirect("panel:banners")
    return render(request, "panel/confirmar.html", {
        "seccion": "contenido", "titulo": f"Eliminar banner «{b.titulo}»", "mensaje": "Dejará de mostrarse en el inicio.",
        "boton": "Eliminar", "volver": "panel:banners",
    })


@staff_required
def legales(request):
    return render(request, "panel/contenido/legales.html", {"seccion": "contenido", "paginas": LegalPage.objects.all()})


@staff_required
def legal_form(request, pk):
    p = get_object_or_404(LegalPage, pk=pk)
    form = LegalPageForm(request.POST or None, instance=p)
    if request.method == "POST" and form.is_valid():
        form.save()
        audit.registrar(request, "editar", p, {k: "(texto modificado)" if k == "contenido" else v
                                                for k, v in audit.cambios_de_form(form).items()})
        messages.success(request, "Página legal guardada.")
        return redirect("panel:legales")
    return render(request, "panel/form_generico.html", {
        "seccion": "contenido", "form": form, "titulo": f"Editar «{p.titulo}»", "volver": "panel:legales",
        "ayuda": "HTML básico: <h2>, <p>, <ul>, <li>, <strong>, <a>. Desmarca «pendiente de revisión» cuando un abogado lo apruebe.",
        "ver": p.get_absolute_url(),
    })
