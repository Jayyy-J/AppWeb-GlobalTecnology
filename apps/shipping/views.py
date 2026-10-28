from django.shortcuts import render
from django.views.decorators.cache import cache_control

from .models import Municipio


@cache_control(max_age=3600)
def municipios(request):
    """Opciones <option> de municipios para el select dependiente (HTMX)."""
    dep = request.GET.get("departamento") or next(
        (v for k, v in request.GET.items() if k.endswith("departamento")), ""
    )
    qs = Municipio.objects.filter(departamento_id=dep).only("id", "nombre") if str(dep).isdigit() else []
    return render(request, "shipping/_municipios.html", {"municipios": qs})
