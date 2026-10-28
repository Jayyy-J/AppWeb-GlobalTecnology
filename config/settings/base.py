"""Configuración común a todos los entornos de GlobalTecnology."""
import os
from pathlib import Path

import dj_database_url
import environ

BASE_DIR = Path(__file__).resolve().parent.parent.parent

env = environ.Env()
# Archivo .env opcional (solo desarrollo). En producción las variables vienen del entorno.
_env_file = env.str("ENV_FILE", default=str(BASE_DIR / ".env"))
if Path(_env_file).is_file():
    environ.Env.read_env(_env_file, overwrite=False)

# Variables definidas pero vacías se tratan como no definidas.
for _var in ("DATABASE_URL", "MEDIA_ROOT", "SITE_URL", "EMAIL_BACKEND", "ALLOWED_HOSTS", "CSRF_TRUSTED_ORIGINS"):
    if os.environ.get(_var, None) == "":
        os.environ.pop(_var)

SECRET_KEY = env.str("SECRET_KEY", default="dev-inseguro-cambiar-esta-clave")
DEBUG = env.bool("DEBUG", default=False)
ALLOWED_HOSTS = env.list("ALLOWED_HOSTS", default=["localhost", "127.0.0.1"])
CSRF_TRUSTED_ORIGINS = env.list("CSRF_TRUSTED_ORIGINS", default=[])
SITE_URL = env.str("SITE_URL", default="http://127.0.0.1:8000").rstrip("/")

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "django.contrib.postgres",
    "django.contrib.sitemaps",
    "django.contrib.humanize",
    "axes",
    "apps.core",
    "apps.accounts",
    "apps.shipping",
    "apps.catalog",
    "apps.cart",
    "apps.orders",
    "apps.payments",
    "apps.storefront",
    "apps.panel",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.locale.LocaleMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "apps.core.middleware.HtmxMiddleware",
    "axes.middleware.AxesMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "apps.core.context_processors.store",
            ],
            "builtins": ["apps.core.templatetags.cop", "apps.core.templatetags.iconos"],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"

# Base de datos: PostgreSQL vía DATABASE_URL; SQLite como respaldo local.
DATABASES = {
    "default": dj_database_url.config(
        default=f"sqlite:///{BASE_DIR / 'db.sqlite3'}",
        conn_max_age=env.int("DB_CONN_MAX_AGE", default=60),
    )
}
IS_POSTGRES = DATABASES["default"]["ENGINE"].endswith("postgresql")

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
AUTH_USER_MODEL = "accounts.User"

AUTHENTICATION_BACKENDS = [
    "axes.backends.AxesStandaloneBackend",
    "apps.accounts.backends.EmailBackend",
]

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator", "OPTIONS": {"min_length": 8}},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LOGIN_URL = "accounts:login"
LOGIN_REDIRECT_URL = "storefront:home"
LOGOUT_REDIRECT_URL = "storefront:home"

# Internacionalización
LANGUAGE_CODE = "es-co"
LANGUAGES = [("es-co", "Español (Colombia)")]
TIME_ZONE = "America/Bogota"
USE_I18N = True
USE_TZ = True

# Estáticos y media
STATIC_URL = "/static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
STATICFILES_DIRS = [BASE_DIR / "static"]
STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage"},
}

MEDIA_URL = "/media/"
MEDIA_ROOT = Path(env.str("MEDIA_ROOT", default=str(BASE_DIR / "media")))
# Evidencias de envío: fuera de la URL pública, servidas por una vista protegida.
PRIVATE_MEDIA_DIR = "privado"
MAX_UPLOAD_MB = 8
DATA_UPLOAD_MAX_MEMORY_SIZE = 30 * 1024 * 1024
FILE_UPLOAD_MAX_MEMORY_SIZE = 5 * 1024 * 1024

# Caché compartida entre workers (tabla creada por migración de apps.core)
CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.db.DatabaseCache",
        "LOCATION": "gt_cache",
        "TIMEOUT": 60 * 30,
    }
}

# Sesiones y mensajes
SESSION_COOKIE_AGE = 60 * 60 * 24 * 30
MESSAGE_STORAGE = "django.contrib.messages.storage.session.SessionStorage"

# Email
EMAIL_BACKEND = env.str("EMAIL_BACKEND", default="django.core.mail.backends.console.EmailBackend")
EMAIL_HOST = env.str("EMAIL_HOST", default="")
EMAIL_PORT = env.int("EMAIL_PORT", default=587)
EMAIL_HOST_USER = env.str("EMAIL_HOST_USER", default="")
EMAIL_HOST_PASSWORD = env.str("EMAIL_HOST_PASSWORD", default="")
EMAIL_USE_TLS = env.bool("EMAIL_USE_TLS", default=True)
EMAIL_USE_SSL = env.bool("EMAIL_USE_SSL", default=False)
EMAIL_TIMEOUT = env.int("EMAIL_TIMEOUT", default=15)
DEFAULT_FROM_EMAIL = env.str("DEFAULT_FROM_EMAIL", default="GlobalTecnology <no-responder@globaltecnology.co>")
ADMIN_NOTIFY_EMAIL = env.str("ADMIN_NOTIFY_EMAIL", default="")
SERVER_EMAIL = DEFAULT_FROM_EMAIL

# Ruta no obvia del Django admin
ADMIN_URL = env.str("ADMIN_URL", default="gestion-tecnica-gt/").strip("/") + "/"

# Wompi
WOMPI_PUBLIC_KEY = env.str("WOMPI_PUBLIC_KEY", default="")
WOMPI_PRIVATE_KEY = env.str("WOMPI_PRIVATE_KEY", default="")
WOMPI_EVENTS_SECRET = env.str("WOMPI_EVENTS_SECRET", default="")
WOMPI_INTEGRITY_SECRET = env.str("WOMPI_INTEGRITY_SECRET", default="")
WOMPI_ENV = env.str("WOMPI_ENV", default="sandbox")
WOMPI_API_URL = (
    "https://production.wompi.co/v1" if WOMPI_ENV == "production" else "https://sandbox.wompi.co/v1"
)
WOMPI_CHECKOUT_URL = "https://checkout.wompi.co/p/"

# django-axes: límite de intentos de inicio de sesión
AXES_FAILURE_LIMIT = env.int("AXES_FAILURE_LIMIT", default=5)
AXES_COOLOFF_TIME = 0.5  # horas
AXES_RESET_ON_SUCCESS = True
AXES_LOCKOUT_PARAMETERS = [["username", "ip_address"]]
AXES_USERNAME_FORM_FIELD = "username"
AXES_LOCKOUT_TEMPLATE = "accounts/bloqueado.html"
AXES_IPWARE_PROXY_COUNT = env.int("AXES_PROXY_COUNT", default=1)
AXES_IPWARE_META_PRECEDENCE_ORDER = ["HTTP_X_FORWARDED_FOR", "REMOTE_ADDR"]

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "estructurado": {
            "format": "%(asctime)s level=%(levelname)s logger=%(name)s %(message)s",
        },
    },
    "handlers": {
        "console": {"class": "logging.StreamHandler", "formatter": "estructurado"},
    },
    "root": {"handlers": ["console"], "level": "INFO"},
    "loggers": {
        "django": {"handlers": ["console"], "level": "INFO", "propagate": False},
        "wompi": {"handlers": ["console"], "level": "INFO", "propagate": False},
        "axes": {"handlers": ["console"], "level": "WARNING", "propagate": False},
    },
}

