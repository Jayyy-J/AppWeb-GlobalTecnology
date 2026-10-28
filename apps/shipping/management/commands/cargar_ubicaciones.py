import json

from django.conf import settings
from django.core.management.base import BaseCommand
from django.db import transaction

from apps.shipping.models import Departamento, Municipio


class Command(BaseCommand):
    help = "Carga (o actualiza) departamentos y municipios de Colombia desde fixtures/divipola.json. Idempotente."

    def add_arguments(self, parser):
        parser.add_argument("--archivo", default=str(settings.BASE_DIR / "fixtures" / "divipola.json"))

    @transaction.atomic
    def handle(self, *args, archivo, **opts):
        with open(archivo, encoding="utf-8") as fh:
            data = json.load(fh)
        existentes = {d.codigo: d for d in Departamento.objects.all()}
        for d in data["departamentos"]:
            obj = existentes.get(d["codigo"])
            if obj is None:
                existentes[d["codigo"]] = Departamento.objects.create(**d)
            elif obj.nombre != d["nombre"]:
                obj.nombre = d["nombre"]
                obj.save(update_fields=["nombre"])
        muni = {m.codigo: m for m in Municipio.objects.all()}
        nuevos, cambiados = [], []
        for m in data["municipios"]:
            dep = existentes[m["departamento"]]
            obj = muni.get(m["codigo"])
            if obj is None:
                nuevos.append(Municipio(codigo=m["codigo"], nombre=m["nombre"], departamento=dep))
            elif obj.nombre != m["nombre"] or obj.departamento_id != dep.id:
                obj.nombre, obj.departamento = m["nombre"], dep
                cambiados.append(obj)
        Municipio.objects.bulk_create(nuevos, batch_size=500)
        if cambiados:
            Municipio.objects.bulk_update(cambiados, ["nombre", "departamento"], batch_size=500)
        self.stdout.write(self.style.SUCCESS(
            f"Ubicaciones listas: {len(existentes)} departamentos, {Municipio.objects.count()} municipios "
            f"({len(nuevos)} nuevos, {len(cambiados)} actualizados)."
        ))
