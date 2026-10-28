"""Producción (Railway)."""
from .base import *  # noqa: F401,F403
from .base import env

SECRET_KEY = env.str("SECRET_KEY")
DEBUG = env.bool("DEBUG", default=False)

SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
SECURE_SSL_REDIRECT = env.bool("SECURE_SSL_REDIRECT", default=True)
# Railway hace el health check por HTTP interno; no redirigir esa ruta.
SECURE_REDIRECT_EXEMPT = [r"^salud/$"]
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
SECURE_HSTS_SECONDS = env.int("SECURE_HSTS_SECONDS", default=60 * 60 * 24 * 365)
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_HSTS_PRELOAD = env.bool("SECURE_HSTS_PRELOAD", default=False)
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_REFERRER_POLICY = "strict-origin-when-cross-origin"
X_FRAME_OPTIONS = "DENY"

# Health check interno de Railway
if "healthcheck.railway.app" not in ALLOWED_HOSTS:  # noqa: F405
    ALLOWED_HOSTS.append("healthcheck.railway.app")  # noqa: F405

# Railway entrega el dominio público en esta variable; se agrega automáticamente.
_railway_domain = env.str("RAILWAY_PUBLIC_DOMAIN", default="")
if _railway_domain:
    if _railway_domain not in ALLOWED_HOSTS:  # noqa: F405
        ALLOWED_HOSTS.append(_railway_domain)  # noqa: F405
    _origin = f"https://{_railway_domain}"
    if _origin not in CSRF_TRUSTED_ORIGINS:  # noqa: F405
        CSRF_TRUSTED_ORIGINS.append(_origin)  # noqa: F405
