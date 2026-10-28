"""Carrito persistente en BD. Los precios siempre se recalculan desde el producto."""
from dataclasses import dataclass, field

from django.db import transaction
from django.db.models import Prefetch, Sum

from apps.catalog.models import Product, ProductImage

from .models import Cart, CartItem


def cart_count(user) -> int:
    if not user.is_authenticated:
        return 0
    return CartItem.objects.filter(carrito__usuario=user).aggregate(n=Sum("cantidad"))["n"] or 0


def get_cart(user) -> Cart:
    cart, _ = Cart.objects.get_or_create(usuario=user)
    return cart


class CartError(Exception):
    pass


@transaction.atomic
def add_item(user, producto: Product, cantidad: int = 1):
    """Agrega o suma cantidad. Devuelve (item, mensaje). Limita la cantidad al stock disponible."""
    cantidad = max(1, int(cantidad or 1))
    if not producto.activo:
        raise CartError("Este producto no está disponible.")
    if producto.stock <= 0:
        raise CartError(f"{producto.nombre} está agotado.")
    cart = get_cart(user)
    item, creado = CartItem.objects.select_for_update().get_or_create(
        carrito=cart, producto=producto, defaults={"cantidad": 0, "precio_al_agregar": producto.precio_final}
    )
    nueva = item.cantidad + cantidad
    mensaje = f"Agregaste {producto.nombre} al carrito."
    if nueva > producto.stock:
        nueva = producto.stock
        mensaje = f"Solo hay {producto.stock} unidades de {producto.nombre}; ajustamos la cantidad."
    item.cantidad = nueva
    item.precio_al_agregar = producto.precio_final
    item.save()
    cart.save(update_fields=["actualizado"])
    return item, mensaje


def update_item(user, item_id: int, cantidad: int):
    item = CartItem.objects.select_related("producto").get(pk=item_id, carrito__usuario=user)
    cantidad = int(cantidad)
    if cantidad <= 0:
        item.delete()
        return None, "Producto eliminado del carrito."
    mensaje = ""
    if cantidad > item.producto.stock:
        cantidad = max(item.producto.stock, 1)
        mensaje = f"Solo hay {item.producto.stock} unidades disponibles."
    item.cantidad = cantidad
    item.save(update_fields=["cantidad"])
    return item, mensaje


def remove_item(user, item_id: int):
    CartItem.objects.filter(pk=item_id, carrito__usuario=user).delete()


def clear_cart(user):
    CartItem.objects.filter(carrito__usuario=user).delete()


@dataclass
class Linea:
    item: CartItem
    producto: Product
    cantidad: int
    precio_unitario: int
    precio_referencia: int | None
    problema: str = ""

    @property
    def subtotal(self):
        return self.precio_unitario * self.cantidad

    @property
    def ahorro(self):
        return (self.precio_referencia - self.precio_unitario) * self.cantidad if self.precio_referencia else 0

    @property
    def cambio_precio(self):
        return self.item.precio_al_agregar and self.item.precio_al_agregar != self.precio_unitario


@dataclass
class Resumen:
    lineas: list = field(default_factory=list)
    envio: object = None  # ShippingQuote

    @property
    def subtotal(self):
        return sum(l.subtotal for l in self.lineas if not l.problema)

    @property
    def ahorro(self):
        return sum(l.ahorro for l in self.lineas if not l.problema)

    @property
    def cantidad(self):
        return sum(l.cantidad for l in self.lineas)

    @property
    def problemas(self):
        return [l for l in self.lineas if l.problema]

    @property
    def costo_envio(self):
        return self.envio.valor if self.envio and self.envio.valor is not None else 0

    @property
    def total(self):
        return self.subtotal + self.costo_envio

    @property
    def vacio(self):
        return not self.lineas


def resumen(user, municipio=None) -> Resumen:
    """Recalcula el carrito con precios y stock actuales (y opcionalmente el envío al municipio)."""
    items = CartItem.objects.filter(carrito__usuario=user).select_related("producto", "producto__marca").prefetch_related(
        Prefetch("producto__imagenes", queryset=ProductImage.objects.order_by("-es_principal", "orden", "id"))
    ).order_by("creado", "id")
    res = Resumen()
    for it in items:
        p = it.producto
        problema = ""
        if not p.activo:
            problema = "Ya no está disponible."
        elif p.stock <= 0:
            problema = "Agotado."
        elif it.cantidad > p.stock:
            problema = f"Solo quedan {p.stock} unidades."
        res.lineas.append(Linea(it, p, it.cantidad, p.precio_final, p.precio_tachado, problema))
    if municipio is not None and res.lineas:
        from apps.shipping.services import cotizar_envio

        res.envio = cotizar_envio(res.subtotal, municipio)
    return res
