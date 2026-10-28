from django.db import migrations


def crear(apps, schema_editor):
    ShippingSettings = apps.get_model("shipping", "ShippingSettings")
    ShippingSettings.objects.get_or_create(
        pk=1,
        defaults={
            "tarifa_fija_activa": False, "tarifa_fija_valor": 18000,
            "envio_gratis_activo": True, "envio_gratis_desde": 200000,
            "tarifas_por_zona_activas": True, "cotizacion_manual_activa": True,
        },
    )


class Migration(migrations.Migration):
    dependencies = [("shipping", "0001_initial")]
    operations = [migrations.RunPython(crear, migrations.RunPython.noop)]
