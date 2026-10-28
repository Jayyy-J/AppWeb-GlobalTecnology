import os
import tempfile
from pathlib import Path
from urllib.parse import urlparse

from django.conf import settings
from django.core.management.base import BaseCommand
from django.http.request import validate_host


class Command(BaseCommand):
    help = "Verifica la configuración del entorno de prueba compartible (VS Code Ports / Dev Tunnels)."

    def handle(self, *args, **opts):
        resultados = []

        def ok(cond, texto, ayuda=""):
            resultados.append((bool(cond), texto, ayuda))

        modulo = os.environ.get("DJANGO_SETTINGS_MODULE", "")
        ok(modulo.endswith(".tunnel"), f"Settings de túnel activos ({modulo or 'sin definir'})",
           "Ejecuta con DJANGO_SETTINGS_MODULE=config.settings.tunnel (scripts/demo.ps1 lo hace).")
        ok(not settings.DEBUG, "DEBUG desactivado", "Nunca expongas DEBUG=True por un enlace público.")

        url = urlparse(settings.SITE_URL)
        ok(bool(settings.SITE_URL) and url.scheme == "https", f"SITE_URL definida y en HTTPS ({settings.SITE_URL})",
           "Copia la 'Forwarded Address' de la pestaña Ports en SITE_URL de .env.tunnel.")
        host = url.hostname or ""
        ok(host and validate_host(host, settings.ALLOWED_HOSTS), f"Host '{host}' permitido en ALLOWED_HOSTS",
           "Agrega el dominio a ALLOWED_HOSTS (por defecto se permite .devtunnels.ms).")
        origen = f"{url.scheme}://{url.netloc}"
        permitido = any(
            origen == o or (("*" in o) and origen.endswith(o.split("*", 1)[1]) and origen.startswith(o.split("*", 1)[0]))
            for o in settings.CSRF_TRUSTED_ORIGINS
        )
        ok(permitido, f"Origen '{origen}' en CSRF_TRUSTED_ORIGINS", "Agrega https://*.devtunnels.ms a CSRF_TRUSTED_ORIGINS.")
        ok(not getattr(settings, "SECURE_SSL_REDIRECT", False), "SECURE_SSL_REDIRECT desactivado (evita bucles en el túnel)")
        ok(settings.SESSION_COOKIE_SECURE and settings.CSRF_COOKIE_SECURE, "Cookies de sesión y CSRF seguras")

        media = Path(settings.MEDIA_ROOT)
        try:
            media.mkdir(parents=True, exist_ok=True)
            with tempfile.NamedTemporaryFile(dir=media, delete=True) as fh:
                fh.write(b"ok")
            escribible = True
        except OSError:
            escribible = False
        ok(escribible, f"Carpeta de media escribible ({media})", "Revisa MEDIA_ROOT y los permisos de la carpeta.")

        pub, prv = settings.WOMPI_PUBLIC_KEY, settings.WOMPI_PRIVATE_KEY
        ok(pub.startswith("pub_test_"), "Llave pública de Wompi de PRUEBAS (pub_test_…)", "Usa solo llaves de sandbox en el túnel.")
        ok(prv.startswith("prv_test_"), "Llave privada de Wompi de PRUEBAS (prv_test_…)", "Usa solo llaves de sandbox en el túnel.")
        ok(settings.WOMPI_ENV == "sandbox", "WOMPI_ENV=sandbox")
        ok(bool(settings.WOMPI_INTEGRITY_SECRET) and bool(settings.WOMPI_EVENTS_SECRET),
           "Secretos de integridad y de eventos de Wompi definidos", "Cópialos del panel de Wompi (Desarrolladores).")

        self.stdout.write("\nVerificación del entorno de prueba compartible\n" + "-" * 48)
        for bien, texto, ayuda in resultados:
            marca = self.style.SUCCESS("  [OK]   ") if bien else self.style.ERROR("  [FALLA]")
            self.stdout.write(f"{marca} {texto}")
            if not bien and ayuda:
                self.stdout.write(f"          → {ayuda}")
        fallas = sum(1 for r in resultados if not r[0])
        self.stdout.write("-" * 48)
        if fallas:
            self.stdout.write(self.style.WARNING(f"{fallas} punto(s) por corregir."))
        else:
            self.stdout.write(self.style.SUCCESS("Todo listo. URL de eventos para Wompi: " + settings.SITE_URL + "/pagos/wompi/eventos/"))
