import json
from datetime import timedelta

from django.db.models import Count, F, Q, Sum
from django.db.models.functions import TruncDate
from django.shortcuts import render
from django.utils import timezone

from apps.catalog.models import Product, SearchLog
from apps.orders.models import EstadoPago, EstadoPedido, Order, OrderItem

from ..permisos import staff_required


def _inicio_dia(d):
    return timezone.make_aware(timezone.datetime(d.year, d.month, d.day))


@staff_required
def dashboard(request):
    hoy = timezone.localdate()
    pagados = Order.objects.filter(estado_pago=EstadoPago.APROBADO).exclude(estado_pedido=EstadoPedido.CANCELADO)

    def ventas(desde):
        r = pagados.filter(pagado_en__gte=_inicio_dia(desde)).aggregate(total=Sum("total"), n=Count("id"))
        return {"total": r["total"] or 0, "n": r["n"]}

    inicio_semana = hoy - timedelta(days=hoy.weekday())
    inicio_mes = hoy.replace(day=1)
    por_estado = dict(Order.objects.values_list("estado_pedido").annotate(n=Count("id")))
    estados = [{"clave": e.value, "nombre": e.label, "n": por_estado.get(e.value, 0)} for e in EstadoPedido]

    accion = {
        "por_enviar": Order.objects.filter(estado_pedido=EstadoPedido.EN_PROCESO).order_by("pagado_en")[:8],
        "por_cotizar": Order.objects.filter(estado_pedido=EstadoPedido.ESPERANDO_COTIZACION).order_by("creado")[:8],
        "alertas": Order.objects.filter(alerta_stock=True).exclude(estado_pedido__in=[EstadoPedido.ENTREGADO]).order_by("-creado")[:8],
    }
    stock_bajo = Product.objects.filter(activo=True, stock__lte=F("stock_minimo_alerta")).order_by("stock", "nombre")[:10]
    top = (
        OrderItem.objects.filter(pedido__estado_pago=EstadoPago.APROBADO, pedido__pagado_en__gte=_inicio_dia(hoy - timedelta(days=90)))
        .values("nombre", "sku").annotate(unidades=Sum("cantidad"), ingresos=Sum("subtotal")).order_by("-unidades")[:8]
    )
    sin_resultados = SearchLog.objects.filter(cantidad_resultados=0).order_by("-cantidad_busquedas")[:10]

    desde = hoy - timedelta(days=29)
    serie = dict(
        pagados.filter(pagado_en__gte=_inicio_dia(desde)).annotate(dia=TruncDate("pagado_en", tzinfo=timezone.get_current_timezone()))
        .values_list("dia").annotate(t=Sum("total"))
    )
    dias = [desde + timedelta(days=i) for i in range(30)]
    grafica = {
        "labels": [d.strftime("%d/%m") for d in dias],
        "data": [int(serie.get(d, 0) or 0) for d in dias],
    }
    return render(request, "panel/dashboard.html", {
        "seccion": "dashboard",
        "ventas_hoy": ventas(hoy), "ventas_semana": ventas(inicio_semana), "ventas_mes": ventas(inicio_mes),
        "estados": estados, "accion": accion, "stock_bajo": stock_bajo, "top": top,
        "sin_resultados": sin_resultados, "grafica_json": json.dumps(grafica),
        "pendientes_pago": Order.objects.filter(estado_pedido=EstadoPedido.PENDIENTE_PAGO).count(),
    })
