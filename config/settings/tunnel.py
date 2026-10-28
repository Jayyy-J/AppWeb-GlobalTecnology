"""Entorno de prueba local compartible mediante VS Code Ports (Dev Tunnels).

Nunca DEBUG por un enlace público. El túnel ya entrega HTTPS, así que no se
redirige a HTTPS (evita bucles) ni se envía HSTS, pero las cookies siguen
siendo seguras.
"""
from .base import *  # noqa: F401,F403
from .base import env

DEBUG = False
SITE_URL = env.str("SITE_URL", default="http://127.0.0.1:8000").rstrip("/")

ALLOWED_HOSTS = list(dict.fromkeys(env.list("ALLOWED_HOSTS", default=[]) + [
    ".devtunnels.ms", "localhost", "127.0.0.1",
]))
CSRF_TRUSTED_ORIGINS = list(dict.fromkeys(env.list("CSRF_TRUSTED_ORIGINS", default=[]) + [
    "https://*.devtunnels.ms", "http://127.0.0.1:8000", "http://localhost:8000",
]))

SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
USE_X_FORWARDED_HOST = True
SECURE_SSL_REDIRECT = False
SECURE_HSTS_SECONDS = 0
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
SECURE_CONTENT_TYPE_NOSNIFF = True

# Consola salvo que se configure SMTP en .env.tunnel
if not env.str("EMAIL_HOST", default=""):
    EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"
