from django.shortcuts import get_object_or_404, render

from .models import LegalPage


def home(request):
    return render(request, "storefront/home.html")


def legal(request, slug):
    pagina = get_object_or_404(LegalPage, slug=slug, activa=True)
    return render(request, "storefront/legal.html", {"pagina": pagina})


def robots_txt(request):
    return render(request, "robots.txt", content_type="text/plain")
