from django.contrib.auth.backends import ModelBackend


class EmailBackend(ModelBackend):
    """Inicio de sesión con email (sin distinguir mayúsculas)."""

    def authenticate(self, request, username=None, password=None, email=None, **kwargs):
        return super().authenticate(request, username=(email or username or "").strip().lower(), password=password, **kwargs)
