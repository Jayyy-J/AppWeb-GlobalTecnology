from urllib.parse import urlparse

from django.http import HttpResponse


def _zona(path: str) -> str:
    return "panel" if path.startswith("/panel/") else "tienda"


class HtmxMiddleware:
    """Marca request.htmx / request.htmx_boosted.

    La tienda y el panel usan <head> distintos (CSS/JS). Con hx-boost solo se
    reemplaza el <body>, así que si una navegación con boost cruza de una zona a
    la otra se pide al navegador una carga completa (HX-Redirect).
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        request.htmx = request.headers.get("HX-Request") == "true"
        request.htmx_boosted = request.headers.get("HX-Boosted") == "true"
        actual = request.headers.get("HX-Current-URL", "")
        if request.htmx and request.method == "GET" and actual and not request.headers.get("HX-Target"):
            if _zona(urlparse(actual).path) != _zona(request.path):
                resp = HttpResponse(status=200)
                resp["HX-Redirect"] = request.get_full_path()
                return resp
        response = self.get_response(request)
        if request.htmx or "HX-Request" in request.headers:
            response.headers["Vary"] = ", ".join(filter(None, [response.headers.get("Vary"), "HX-Request"]))
        return response
