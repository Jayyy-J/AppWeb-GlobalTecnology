from django.core.validators import MinValueValidator
from django.db import models

from apps.core.models import SingletonModel


class Departamento(models.Model):
    codigo = models.CharField("código DANE", max_length=2, unique=True)
    nombre = models.CharField("nombre", max_length=80)

    class Meta:
        verbose_name = "departamento"
        verbose_name_plural = "departamentos"
        ordering = ["nombre"]

    def __str__(self):
        return self.nombre


class Municipio(models.Model):
    codigo = models.CharField("código DANE", max_length=5, unique=True)
    nombre = models.CharField("nombre", max_length=80)
    departamento = models.ForeignKey(Departamento, on_delete=models.CASCADE, related_name="municipios")

    class Meta:
        verbose_name = "municipio"
        verbose_name_plural = "municipios"
        ordering = ["nombre"]

    def __str__(self):
        return f"{self.nombre} ({self.departamento.nombre})"


class ShippingSettings(SingletonModel):
    tarifa_fija_activa = models.BooleanField("tarifa fija activa", default=True)
    tarifa_fija_valor = models.PositiveIntegerField("valor tarifa fija", default=15000)
    envio_gratis_activo = models.BooleanField("envío gratis activo", default=True)
    envio_gratis_desde = models.PositiveIntegerField("envío gratis desde (subtotal)", default=200000)
    tarifas_por_zona_activas = models.BooleanField("tarifas por zona activas", default=True)
    cotizacion_manual_activa = models.BooleanField("cotización manual activa", default=True)

    class Meta:
        verbose_name = "configuración de envíos"
        verbose_name_plural = "configuración de envíos"

    def __str__(self):
        return "Configuración de envíos"


class ShippingZoneRate(models.Model):
    departamento = models.ForeignKey(Departamento, on_delete=models.CASCADE, related_name="tarifas")
    municipio = models.ForeignKey(
        Municipio, on_delete=models.CASCADE, null=True, blank=True, related_name="tarifas",
        help_text="Opcional. Si se define, tiene prioridad sobre la tarifa del departamento.",
    )
    valor = models.PositiveIntegerField("valor", validators=[MinValueValidator(0)])
    dias_estimados = models.CharField("días estimados de entrega", max_length=20, blank=True, help_text="Ej. 2-4")
    activo = models.BooleanField("activo", default=True)

    class Meta:
        verbose_name = "tarifa por zona"
        verbose_name_plural = "tarifas por zona"
        ordering = ["departamento__nombre", "municipio__nombre"]
        constraints = [
            models.UniqueConstraint(fields=["departamento", "municipio"], name="tarifa_unica_por_municipio"),
            models.UniqueConstraint(
                fields=["departamento"], condition=models.Q(municipio__isnull=True), name="tarifa_unica_por_departamento"
            ),
        ]

    def __str__(self):
        destino = self.municipio.nombre if self.municipio_id else self.departamento.nombre
        return f"{destino}: {self.valor}"

    def clean(self):
        from django.core.exceptions import ValidationError

        if self.municipio_id and self.municipio.departamento_id != self.departamento_id:
            raise ValidationError({"municipio": "El municipio no pertenece al departamento seleccionado."})
