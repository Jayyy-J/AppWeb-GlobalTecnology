import csv
from datetime import datetime

from django.core.paginator import Paginator
from django.db.models import Q, Sum
from django.http import HttpResponse
from django.shortcuts import render
from django.utils import timezone

from apps.catalog.models import Product
from apps.orders.models import Order, OrderItem

from .. import audit
from ..forms import FiltroFechasForm
from ..models import AuditLog
from ..permisos import staff_required


def _rango(form):
    d, h = form.cleaned_data["desde"], form.cleaned_data["hasta"]
    tz = timezone.get_current_timezone()
    return (timezone.make_aware(datetime.combine(d, datetime.min.time()), tz),
            timezone.make_aware(datetime.combine(h, datetime.max.time()), tz))


def _csv(nombre):
    resp = HttpResponse(content_type="text/csv; charset=utf-8")
    resp["Content-Disposition"] = f'attachment; filename="{nombre}"'
    resp.write("﻿")  # BOM: Excel abre bien tildes y ñ
    return resp, csv.writer(resp, delimiter=";")


@staff_required
def reportes(request):
    hoy = timezone.localdate()
    datos = request.GET if "desde" in request.GET else {"desde": hoy.replace(day=1), "hasta": hoy}
    form = FiltroFechasForm(datos)
    tipo = request.GET.get("exportar")
    if tipo and form.is_valid():
        desde, hasta = _rango(form)
        audit.registrar(request, f"exportar_{tipo}", modelo="reporte",
                        cambios={"desde": str(form.cleaned_data["desde"]), "hasta": str(form.cleaned_data["hasta"])})
        if tipo == "pedidos":
            return _export_pedidos(desde, hasta, form)
        if tipo == "productos":
            return _export_productos(desde, hasta, form)
    resumen = None
    if form.is_valid():
        desde, hasta = _rango(form)
        pagados = Order.objects.filter(estado_pago="aprobado", pagado_en__range=(desde, hasta))
        resumen = {
            "pedidos": Order.objects.filter(creado__range=(desde, hasta)).count(),
            "pagados": pagados.count(),
            "ventas": pagados.aggregate(t=Sum("total"))["t"] or 0,
            "envios": pagados.aggregate(t=Sum("costo_envio"))["t"] or 0,
        }
    return render(request, "panel/reportes.html", {"seccion": "reportes", "form": form, "resumen": resumen})


def _export_pedidos(desde, hasta, form):
    resp, w = _csv(f"pedidos_{form.cleaned_data['desde']}_{form.cleaned_data['hasta']}.csv")
    w.writerow(["Número", "Fecha", "Cliente", "Email", "Teléfono", "Documento", "Departamento", "Municipio", "Dirección",
                "Productos", "Subtotal", "Ahorro", "Envío", "Total", "Estado pago", "Estado pedido", "Método de pago",
                "Referencia Wompi", "Transacción Wompi", "Transportadora", "Guía"])
    qs = Order.objects.filter(creado__range=(desde, hasta)).prefetch_related("items").order_by("creado")
    for o in qs:
        w.writerow([
            o.numero, timezone.localtime(o.creado).strftime("%Y-%m-%d %H:%M"), o.cliente_nombre, o.cliente_email,
            o.cliente_telefono, f"{o.cliente_tipo_documento} {o.cliente_numero_documento}".strip(), o.envio_departamento,
            o.envio_municipio, o.envio_direccion, " | ".join(f"{i.cantidad}x {i.sku}" for i in o.items.all()),
            o.subtotal, o.descuentos, o.costo_envio, o.total, o.get_estado_pago_display(), o.get_estado_pedido_display(),
            o.metodo_pago, o.wompi_referencia, o.wompi_transaccion_id, o.transportadora, o.numero_guia,
        ])
    return resp


def _export_productos(desde, hasta, form):
    resp, w = _csv(f"productos_{form.cleaned_data['desde']}_{form.cleaned_data['hasta']}.csv")
    vendidos = dict(
        OrderItem.objects.filter(pedido__estado_pago="aprobado", pedido__pagado_en__range=(desde, hasta))
        .values_list("producto_id").annotate(n=Sum("cantidad"))
    )
    w.writerow(["SKU", "Nombre", "Marca", "Categorías", "Precio", "Tipo descuento", "Precio final", "% ahorro", "Stock",
                "Activo", "Destacado", f"Vendidos ({form.cleaned_data['desde']} a {form.cleaned_data['hasta']})"])
    for p in Product.objects.select_related("marca").prefetch_related("categorias").order_by("nombre"):
        w.writerow([
            p.sku, p.nombre, p.marca.nombre if p.marca else "", ", ".join(c.nombre for c in p.categorias.all()),
            p.precio, p.get_tipo_descuento_display(), p.precio_final, p.porcentaje_ahorro, p.stock,
            "Sí" if p.activo else "No", "Sí" if p.destacado else "No", vendidos.get(p.pk, 0),
        ])
    return resp


@staff_required
def auditoria(request):
    qs = AuditLog.objects.select_related("usuario")
    if q := request.GET.get("q", "").strip():
        qs = qs.filter(Q(objeto_repr__icontains=q) | Q(usuario__email__icontains=q) | Q(accion__icontains=q) | Q(modelo__icontains=q))
    if m := request.GET.get("modelo"):
        qs = qs.filter(modelo=m)
    modelos = AuditLog.objects.order_by("modelo").values_list("modelo", flat=True).distinct()
    return render(request, "panel/auditoria.html", {
        "seccion": "auditoria", "pagina": Paginator(qs, 40).get_page(request.GET.get("pagina")), "modelos": modelos,
    })
