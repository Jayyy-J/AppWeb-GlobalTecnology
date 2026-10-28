from django.apps import AppConfig


class StorefrontConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.storefront"
    label = "storefront"
    verbose_name = "Tienda"

    def ready(self):
        from . import signals  # noqa: F401
