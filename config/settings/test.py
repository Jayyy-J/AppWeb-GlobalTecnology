"""Pruebas automatizadas."""
import tempfile
from pathlib import Path

from .base import *  # noqa: F401,F403

DEBUG = False
SECRET_KEY = "pruebas"
ALLOWED_HOSTS = ["*"]
PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]
EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"
MEDIA_ROOT = Path(tempfile.mkdtemp(prefix="gt-media-"))
CACHES = {"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}}
STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
}
AXES_ENABLED = False
WOMPI_PUBLIC_KEY = "pub_test_abc"
WOMPI_PRIVATE_KEY = "prv_test_abc"
WOMPI_EVENTS_SECRET = "test_events_secret"
WOMPI_INTEGRITY_SECRET = "test_integrity_secret"
ADMIN_NOTIFY_EMAIL = "admin@globaltecnology.co"
