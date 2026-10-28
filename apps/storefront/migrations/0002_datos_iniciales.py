"""Crea la configuración de la tienda, de envíos y las páginas legales base (borrador)."""
from django.db import migrations

from apps.storefront.legal_texts import PAGINAS, render


def crear(apps, schema_editor):
    StoreSettings = apps.get_model("storefront", "StoreSettings")
    LegalPage = apps.get_model("storefront", "LegalPage")
    StoreSettings.objects.get_or_create(pk=1)
    for slug, titulo, texto, orden in PAGINAS:
        LegalPage.objects.get_or_create(
            slug=slug, defaults={"titulo": titulo, "contenido": render(texto), "orden": orden, "borrador_revision": True}
        )


class Migration(migrations.Migration):
    dependencies = [("storefront", "0001_initial")]
    operations = [migrations.RunPython(crear, migrations.RunPython.noop)]
