"""Carga departamentos y municipios (DIVIPOLA) al migrar, para que producción
quede lista solo con `migrate`. Equivale a `manage.py cargar_ubicaciones`."""
import json
from pathlib import Path

from django.db import migrations

ARCHIVO = Path(__file__).resolve().parents[3] / "fixtures" / "divipola.json"


def cargar(apps, schema_editor):
    Departamento = apps.get_model("shipping", "Departamento")
    Municipio = apps.get_model("shipping", "Municipio")
    if Municipio.objects.exists() or not ARCHIVO.exists():
        return
    data = json.loads(ARCHIVO.read_text(encoding="utf-8"))
    deps = {}
    for d in data["departamentos"]:
        deps[d["codigo"]], _ = Departamento.objects.get_or_create(codigo=d["codigo"], defaults={"nombre": d["nombre"]})
    Municipio.objects.bulk_create(
        [Municipio(codigo=m["codigo"], nombre=m["nombre"], departamento=deps[m["departamento"]]) for m in data["municipios"]],
        batch_size=500,
    )


class Migration(migrations.Migration):
    dependencies = [("shipping", "0002_configuracion_inicial")]
    operations = [migrations.RunPython(cargar, migrations.RunPython.noop)]
