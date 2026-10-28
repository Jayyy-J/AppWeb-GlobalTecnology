from django.conf import settings
from django.core.validators import MinValueValidator
from django.db import models


class Cart(models.Model):
    usuario = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="carrito")
    creado = models.DateTimeField(auto_now_add=True)
    actualizado = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "carrito"
        verbose_name_plural = "carritos"

    def __str__(self):
        return f"Carrito de {self.usuario}"


class CartItem(models.Model):
    carrito = models.ForeignKey(Cart, on_delete=models.CASCADE, related_name="items")
    producto = models.ForeignKey("catalog.Product", on_delete=models.CASCADE, related_name="+")
    cantidad = models.PositiveIntegerField(default=1, validators=[MinValueValidator(1)])
    # Solo referencia: el precio cobrado SIEMPRE se recalcula en el servidor al pagar.
    precio_al_agregar = models.PositiveIntegerField(default=0)
    creado = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "producto en carrito"
        verbose_name_plural = "productos en carrito"
        ordering = ["creado", "id"]
        constraints = [models.UniqueConstraint(fields=["carrito", "producto"], name="item_unico_por_carrito")]

    def __str__(self):
        return f"{self.cantidad} × {self.producto}"
