import csv
import io

from django.contrib import messages
from django.db import transaction
from django.shortcuts import get_object_or_404, redirect, render

from apps.core.text import normalize
from apps.shipping.models import Departamento, Municipio, ShippingSettings, ShippingZoneRate

from .. import audit
from ..forms import CSVImportForm, ShippingSettingsForm, ZoneRateForm
from ..permisos import staff_required


@staff_required
def envios(request):
    cfg = ShippingSettings.load()
    form = ShippingSettingsForm(request.POST or None, instance=cfg)
    if request.method == "POST" and form.is_valid():
        form.save()
        audit.registrar(request, "configurar_envios", cfg, audit.cambios_de_form(form))
        messages.success(request, "Configuración de envíos guardada.")
        return redirect("panel:envios")
    tarifas = ShippingZoneRate.objects.select_related("departamento", "municipio").order_by("departamento__nombre", "municipio__nombre")
    return render(request, "panel/envios/index.html", {
        "seccion": "envios", "form": form, "tarifas": tarifas, "form_csv": CSVImportForm(),
    })


@staff_required
def tarifa_form(request, pk=None):
    t = get_object_or_404(ShippingZoneRate, pk=pk) if pk else None
    form = ZoneRateForm(request.POST or None, instance=t)
    if request.method == "POST" and form.is_valid():
        obj = form.save()
        audit.registrar(request, "editar" if t else "crear", obj, audit.cambios_de_form(form))
        messages.success(request, "Tarifa guardada.")
        return redirect("panel:envios")
    return render(request, "panel/form_generico.html", {
        "seccion": "envios", "form": form, "titulo": "Editar tarifa" if t else "Nueva tarifa por zona", "volver": "panel:envios",
        "ayuda": "Si eliges un municipio, su tarifa tiene prioridad sobre la del departamento.",
    })


@staff_required
def tarifa_eliminar(request, pk):
    t = get_object_or_404(ShippingZoneRate, pk=pk)
    if request.method == "POST":
        audit.registrar(request, "eliminar", t)
        t.delete()
        messages.success(request, "Tarifa eliminada.")
        return redirect("panel:envios")
    return render(request, "panel/confirmar.html", {
        "seccion": "envios", "titulo": f"Eliminar tarifa {t}", "mensaje": "Los pedidos existentes no cambian.",
        "boton": "Eliminar", "volver": "panel:envios",
    })


def _buscar(modelo, valor, **filtro):
    valor = (valor or "").strip()
    if not valor:
        return None
    if valor.isdigit():
        return modelo.objects.filter(codigo=valor.zfill(2 if modelo is Departamento else 5), **filtro).first()
    n = normalize(valor)
    for obj in modelo.objects.filter(**filtro):
        if normalize(obj.nombre) == n:
            return obj
    return None


def importar_tarifas(contenido: str):
    """Importa/actualiza tarifas desde CSV (separador ; o ,). Devuelve (creadas, actualizadas, errores)."""
    muestra = contenido[:2000]
    dialecto = csv.excel
    if muestra.count(";") > muestra.count(","):
        class PuntoYComa(csv.excel):
            delimiter = ";"
        dialecto = PuntoYComa
    lector = csv.DictReader(io.StringIO(contenido), dialect=dialecto)
    lector.fieldnames = [normalize(f or "").replace(" ", "_") for f in (lector.fieldnames or [])]
    creadas = actualizadas = 0
    errores = []
    with transaction.atomic():
        for i, fila in enumerate(lector, start=2):
            dep = _buscar(Departamento, fila.get("departamento"))
            if dep is None:
                errores.append(f"Fila {i}: departamento «{fila.get('departamento')}» no encontrado.")
                continue
            mun = None
            if (fila.get("municipio") or "").strip():
                mun = _buscar(Municipio, fila.get("municipio"), departamento=dep)
                if mun is None:
                    errores.append(f"Fila {i}: municipio «{fila.get('municipio')}» no encontrado en {dep.nombre}.")
                    continue
            try:
                valor = int(str(fila.get("valor", "")).replace(".", "").replace("$", "").replace(",", "").strip())
                assert valor >= 0
            except (ValueError, AssertionError):
                errores.append(f"Fila {i}: valor inválido «{fila.get('valor')}».")
                continue
            activo = normalize(fila.get("activo") or "si") not in ("no", "0", "false", "falso", "inactivo")
            _, creada = ShippingZoneRate.objects.update_or_create(
                departamento=dep, municipio=mun,
                defaults={"valor": valor, "dias_estimados": (fila.get("dias") or "").strip()[:20], "activo": activo},
            )
            creadas += creada
            actualizadas += not creada
    return creadas, actualizadas, errores


@staff_required
def tarifas_importar(request):
    form = CSVImportForm(request.POST or None, request.FILES or None)
    if request.method == "POST" and form.is_valid():
        raw = form.cleaned_data["archivo"].read()
        try:
            texto = raw.decode("utf-8-sig")
        except UnicodeDecodeError:
            texto = raw.decode("latin-1")
        creadas, actualizadas, errores = importar_tarifas(texto)
        audit.registrar(request, "importar_tarifas", modelo="tarifa por zona",
                        cambios={"creadas": creadas, "actualizadas": actualizadas, "errores": len(errores)})
        messages.success(request, f"Importación lista: {creadas} creadas, {actualizadas} actualizadas.")
        for e in errores[:10]:
            messages.warning(request, e)
        if len(errores) > 10:
            messages.warning(request, f"…y {len(errores) - 10} errores más.")
    elif request.method == "POST":
        messages.error(request, "Adjunta un archivo CSV válido.")
    return redirect("panel:envios")
