from django.conf import settings
from django.db import models
from django.urls import reverse

from apps.core.images import validate_image_file
from apps.core.storage import get_private_storage


class EstadoPago(models.TextChoices):
    PENDIENTE = "pendiente", "Pendiente"
    APROBADO = "aprobado", "Aprobado"
    RECHAZADO = "rechazado", "Rechazado"
    ANULADO = "anulado", "Anulado"
    ERROR = "error", "Error"


class EstadoPedido(models.TextChoices):
    ESPERANDO_COTIZACION = "esperando_cotizacion", "Esperando cotización de envío"
    PENDIENTE_PAGO = "pendiente_pago", "Pendiente de pago"
    EN_PROCESO = "en_proceso", "En proceso"
    ENVIADO = "enviado", "Enviado"
    ENTREGADO = "entregado", "Entregado"
    CANCELADO = "cancelado", "Cancelado"


class MetodoEntrega(models.TextChoices):
    TRANSPORTADORA = "transportadora", "Transportadora"
    PERSONAL = "personal", "Entrega personal"


class Order(models.Model):
    numero = models.CharField("número", max_length=20, unique=True, null=True, editable=False)
    usuario = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="pedidos")

    # Snapshot del cliente
    cliente_nombre = models.CharField("nombre del cliente", max_length=200)
    cliente_email = models.EmailField("email del cliente")
    cliente_telefono = models.CharField("teléfono del cliente", max_length=20)
    cliente_tipo_documento = models.CharField("tipo de documento", max_length=3, blank=True)
    cliente_numero_documento = models.CharField("número de documento", max_length=20, blank=True)

    # Snapshot de la dirección
    envio_nombre = models.CharField("recibe", max_length=120)
    envio_telefono = models.CharField("teléfono de quien recibe", max_length=20)
    envio_departamento = models.CharField("departamento", max_length=80)
    envio_municipio = models.CharField("municipio", max_length=80)
    envio_municipio_codigo = models.CharField("código DANE municipio", max_length=5, blank=True)
    envio_direccion = models.CharField("dirección", max_length=200)
    envio_barrio = models.CharField("barrio", max_length=100, blank=True)
    envio_indicaciones = models.CharField("indicaciones", max_length=255, blank=True)

    # Totales (COP enteros)
    subtotal = models.PositiveIntegerField("subtotal", default=0)
    descuentos = models.PositiveIntegerField("descuentos (ahorro)", default=0)
    costo_envio = models.PositiveIntegerField("costo de envío", default=0)
    total = models.PositiveIntegerField("total", default=0)
    regla_envio_aplicada = models.CharField("regla de envío aplicada", max_length=255, blank=True)
    envio_dias_estimados = models.CharField("días estimados", max_length=20, blank=True)

    estado_pago = models.CharField("estado del pago", max_length=12, choices=EstadoPago.choices, default=EstadoPago.PENDIENTE)
    estado_pedido = models.CharField("estado del pedido", max_length=25, choices=EstadoPedido.choices, default=EstadoPedido.PENDIENTE_PAGO)

    # Envío
    metodo_entrega = models.CharField("método de entrega", max_length=15, choices=MetodoEntrega.choices, blank=True)
    transportadora = models.CharField("transportadora", max_length=100, blank=True)
    numero_guia = models.CharField("número de guía", max_length=100, blank=True)
    url_rastreo = models.URLField("URL de rastreo", blank=True)
    entregado_por = models.CharField("entregado por", max_length=120, blank=True)

    # Wompi
    wompi_referencia = models.CharField("referencia Wompi", max_length=60, blank=True, db_index=True)
    wompi_transaccion_id = models.CharField("ID transacción Wompi", max_length=80, blank=True)
    metodo_pago = models.CharField("método de pago", max_length=40, blank=True)
    pagado_en = models.DateTimeField("pagado en", null=True, blank=True)

    # Inventario e incidencias
    stock_descontado = models.BooleanField("stock descontado", default=False)
    stock_devuelto = models.BooleanField("stock devuelto", default=False)
    alerta_stock = models.BooleanField("alerta de stock", default=False)
    alerta_detalle = models.TextField("detalle de la alerta", blank=True)

    notas_cliente = models.CharField("notas del cliente", max_length=300, blank=True)
    notas_internas = models.TextField("notas internas (no visibles al cliente)", blank=True)
    creado = models.DateTimeField("creado", auto_now_add=True, db_index=True)
    actualizado = models.DateTimeField("actualizado", auto_now=True)

    class Meta:
        verbose_name = "pedido"
        verbose_name_plural = "pedidos"
        ordering = ["-creado"]
        indexes = [models.Index(fields=["estado_pedido", "-creado"]), models.Index(fields=["estado_pago", "-creado"])]

    def __str__(self):
        return self.numero or f"Pedido #{self.pk}"

    def get_absolute_url(self):
        return reverse("orders:detalle", args=[self.numero])

    @property
    def puede_pagar(self):
        return self.estado_pedido == EstadoPedido.PENDIENTE_PAGO and self.estado_pago != EstadoPago.APROBADO

    @property
    def requiere_accion(self):
        return (
            self.estado_pedido in (EstadoPedido.ESPERANDO_COTIZACION, EstadoPedido.EN_PROCESO) or self.alerta_stock
        )

    @property
    def total_centavos(self):
        return int(self.total) * 100

    @property
    def direccion_texto(self):
        partes = [self.envio_direccion]
        if self.envio_barrio:
            partes.append(f"Barrio {self.envio_barrio}")
        partes.append(f"{self.envio_municipio}, {self.envio_departamento}")
        return " · ".join(partes)

    @property
    def cantidad_productos(self):
        return sum(i.cantidad for i in self.items.all())


class OrderItem(models.Model):
    pedido = models.ForeignKey(Order, on_delete=models.CASCADE, related_name="items")
    producto = models.ForeignKey("catalog.Product", on_delete=models.SET_NULL, null=True, blank=True, related_name="+")
    nombre = models.CharField("nombre", max_length=200)
    sku = models.CharField("SKU", max_length=60)
    imagen = models.CharField("imagen (URL)", max_length=300, blank=True)
    precio_unitario = models.PositiveIntegerField("precio unitario final")
    precio_antes = models.PositiveIntegerField("precio antes", null=True, blank=True)
    cantidad = models.PositiveIntegerField("cantidad")
    subtotal = models.PositiveIntegerField("subtotal")

    class Meta:
        verbose_name = "producto del pedido"
        verbose_name_plural = "productos del pedido"
        ordering = ["id"]

    def __str__(self):
        return f"{self.cantidad} × {self.nombre}"


def ruta_evidencia(instance, filename):
    import uuid

    return f"evidencias/{instance.pedido_id or 'x'}/{uuid.uuid4().hex}.webp"


class OrderStatusEvent(models.Model):
    pedido = models.ForeignKey(Order, on_delete=models.CASCADE, related_name="eventos")
    estado = models.CharField("estado", max_length=25)
    titulo = models.CharField("título", max_length=120)
    nota = models.TextField("nota visible al cliente", blank=True)
    foto = models.ImageField(
        "foto de evidencia", upload_to=ruta_evidencia, storage=get_private_storage, blank=True,
        validators=[validate_image_file],
    )
    visible_cliente = models.BooleanField("visible para el cliente", default=True)
    usuario = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+")
    creado = models.DateTimeField("fecha", auto_now_add=True)

    class Meta:
        verbose_name = "evento del pedido"
        verbose_name_plural = "línea de tiempo"
        ordering = ["creado", "id"]

    def __str__(self):
        return f"{self.pedido} · {self.titulo}"

    def save(self, *args, **kwargs):
        # Evidencia: se convierte a WebP (máx. 1600 px) y se guarda con nombre aleatorio.
        if self.foto and not getattr(self.foto, "_committed", True):
            from apps.core.images import _open_rgb, to_webp

            content, _, _ = to_webp(_open_rgb(self.foto.file), 1600)
            self.foto.save("evidencia.webp", content, save=False)
        super().save(*args, **kwargs)

    def get_foto_url(self):
        return reverse("orders:evidencia", args=[self.pk]) if self.foto else ""
