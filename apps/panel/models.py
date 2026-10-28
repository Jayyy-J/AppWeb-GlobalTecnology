from django.conf import settings
from django.db import models


class AuditLog(models.Model):
    """Quién cambió qué y cuándo (productos, precios, pedidos, configuración)."""

    usuario = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name="+")
    accion = models.CharField("acción", max_length=40)
    modelo = models.CharField("modelo", max_length=60)
    objeto_id = models.CharField("id del objeto", max_length=40, blank=True)
    objeto_repr = models.CharField("objeto", max_length=200, blank=True)
    cambios = models.JSONField("cambios", default=dict, blank=True)
    ip = models.GenericIPAddressField(null=True, blank=True)
    fecha = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        verbose_name = "registro de auditoría"
        verbose_name_plural = "auditoría"
        ordering = ["-fecha"]

    def __str__(self):
        return f"{self.fecha:%Y-%m-%d %H:%M} {self.usuario} {self.accion} {self.modelo} {self.objeto_repr}"

    def cambios_lista(self):
        """[(campo, texto legible)] para mostrar en la tabla de auditoría."""
        out = []
        for k, v in (self.cambios or {}).items():
            if isinstance(v, list) and len(v) == 2 and k not in ("productos", "orden"):
                antes, despues = v
                texto = f"{antes if antes not in (None, '') else '—'} → {despues if despues not in (None, '') else '—'}"
            elif isinstance(v, list):
                texto = ", ".join(str(x) for x in v)
            else:
                texto = "—" if v in (None, "") else str(v)
            out.append((k, texto[:160]))
        return out
