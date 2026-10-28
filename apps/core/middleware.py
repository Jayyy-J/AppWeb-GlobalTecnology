class HtmxMiddleware:
    """Marca request.htmx cuando la petición viene de HTMX (y si es hx-boost)."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        request.htmx = request.headers.get("HX-Request") == "true"
        request.htmx_boosted = request.headers.get("HX-Boosted") == "true"
        response = self.get_response(request)
        # Las respuestas varían según HTMX; evita que el navegador mezcle caché parcial/completa.
        if request.htmx or "HX-Request" in request.headers:
            response.headers["Vary"] = ", ".join(filter(None, [response.headers.get("Vary"), "HX-Request"]))
        return response
