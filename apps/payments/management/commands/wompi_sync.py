from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone

from apps.payments import services, wompi
from apps.payments.models import Payment


class Command(BaseCommand):
    help = ("Consulta en Wompi los pagos pendientes de más de 15 minutos (respaldo si un webhook se pierde). "
            "Programarlo cada 15-30 minutos (cron de Railway).")

    def add_arguments(self, parser):
        parser.add_argument("--minutos", type=int, default=15)
        parser.add_argument("--dias", type=int, default=7, help="Antigüedad máxima a revisar")

    def handle(self, *args, minutos, dias, **opts):
        ahora = timezone.now()
        pagos = Payment.objects.filter(
            estado=Payment.Estado.PENDING, pedido__estado_pago="pendiente",
            creado__lte=ahora - timedelta(minutes=minutos), creado__gte=ahora - timedelta(days=dias),
        ).select_related("pedido")
        revisados = actualizados = errores = 0
        for pago in pagos:
            revisados += 1
            try:
                if pago.transaccion_id:
                    txs = [wompi.get_transaction(pago.transaccion_id)]
                else:
                    txs = wompi.find_transactions(pago.referencia)
            except wompi.WompiError as e:
                errores += 1
                self.stderr.write(f"  {pago.referencia}: error consultando Wompi ({e})")
                continue
            if not txs:
                continue
            # Prioriza una transacción aprobada; si no, la más reciente.
            txs.sort(key=lambda t: (t.get("status") == "APPROVED", t.get("created_at") or ""), reverse=True)
            resultado = services.aplicar_transaccion(txs[0], fuente="sync")
            if resultado in ("ok", "duplicado", "pago_en_cancelado"):
                actualizados += 1
            self.stdout.write(f"  {pago.referencia}: {txs[0].get('status')} → {resultado}")
        self.stdout.write(self.style.SUCCESS(
            f"wompi_sync: {revisados} revisados, {actualizados} actualizados, {errores} errores."
        ))
