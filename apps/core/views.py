import mimetypes
from pathlib import Path

from django.conf import settings
from django.db import connection
from django.http import FileResponse, Http404, HttpResponse, JsonResponse
from django.shortcuts import render
from django.views.decorators.cache import cache_control
from django.views.decorators.http import require_GET

PUBLIC_PREFIXES = ("productos/", "categorias/", "marcas/", "banners/", "tienda/")


@require_GET
@cache_control(public=True, max_age=60 * 60 * 24 * 365, immutable=True)
def public_media(request, path):
    """Sirve archivos públicos de MEDIA_ROOT (volumen de Railway) con caché larga.

    Los nombres son aleatorios y únicos, por eso la caché puede ser "immutable".
    Las evidencias (carpeta privada) nunca se sirven aquí.
    """
    if not path.startswith(PUBLIC_PREFIXES) or ".." in Path(path).parts:
        raise Http404
    root = Path(settings.MEDIA_ROOT).resolve()
    full = (root / path).resolve()
    if root not in full.parents or not full.is_file():
        raise Http404
    ctype, _ = mimetypes.guess_type(str(full))
    return FileResponse(open(full, "rb"), content_type=ctype or "application/octet-stream")


def health(request):
    try:
        with connection.cursor() as c:
            c.execute("SELECT 1")
        return JsonResponse({"estado": "ok"})
    except Exception:  # pragma: no cover
        return JsonResponse({"estado": "error"}, status=503)


def error_404(request, exception=None):
    return render(request, "404.html", status=404)


def error_500(request):
    from django.template import loader

    try:  # sin context processors: la BD podría no estar disponible
        return HttpResponse(loader.get_template("500.html").render({}), status=500)
    except Exception:  # pragma: no cover - último recurso
        return HttpResponse("<h1>Error del servidor</h1>", status=500)
