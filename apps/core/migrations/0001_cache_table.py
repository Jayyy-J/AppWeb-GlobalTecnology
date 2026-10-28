from django.core.management import call_command
from django.db import migrations


def create_cache_table(apps, schema_editor):
    # Tabla de la caché compartida (DatabaseCache). Idempotente.
    call_command("createcachetable", database=schema_editor.connection.alias, verbosity=0)


class Migration(migrations.Migration):
    initial = True
    dependencies = []
    operations = [migrations.RunPython(create_cache_table, migrations.RunPython.noop)]
