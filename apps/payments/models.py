from django.db import models


class Payment(models.Model):
    """Intento de pago en Wompi. Cada reintento genera una referencia nueva vinculada al mismo pedido."""

    class Estado(models.TextChoices):
        PENDING = "PENDING", "Pendiente"
        APPROVED = "APPROVED", "Aprobado"
        DECLINED = "DECLINED", "Rechazado"
        VOIDED = "VOIDED", "Anulado"
        ERROR = "ERROR", "Error"

    pedido = models.ForeignKey("orders.Order", on_delete=models.CASCADE, related_name="pagos")
    referencia = models.CharField("referencia", max_length=60, unique=True)
    monto_centavos = models.PositiveBigIntegerField("monto (centavos)")
    moneda = models.CharField(max_length=3, default="COP")
    estado = models.CharField(max_length=10, choices=Estado.choices, default=Estado.PENDING)
    transaccion_id = models.CharField("ID transacción", max_length=80, blank=True, db_index=True)
    metodo = models.CharField("método de pago", max_length=40, blank=True)
    detalle = models.CharField("detalle", max_length=255, blank=True)
    respuesta = models.JSONField("última respuesta de Wompi", default=dict, blank=True)
    creado = models.DateTimeField(auto_now_add=True)
    actualizado = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "pago Wompi"
        verbose_name_plural = "pagos Wompi"
        ordering = ["-creado"]

    def __str__(self):
        return f"{self.referencia} ({self.estado})"


class WompiEvent(models.Model):
    """Registro de cada evento recibido en el webhook (auditoría e idempotencia)."""

    evento = models.CharField(max_length=60)
    transaccion_id = models.CharField(max_length=80, blank=True, db_index=True)
    referencia = models.CharField(max_length=60, blank=True, db_index=True)
    estado = models.CharField(max_length=20, blank=True)
    ambiente = models.CharField(max_length=10, blank=True)
    checksum = models.CharField(max_length=128, blank=True)
    valido = models.BooleanField(default=False)
    resultado = models.CharField(max_length=60, blank=True)
    payload = models.JSONField(default=dict)
    recibido = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "evento Wompi"
        verbose_name_plural = "eventos Wompi"
        ordering = ["-recibido"]

    def __str__(self):
        return f"{self.evento} {self.transaccion_id} {self.estado}"
