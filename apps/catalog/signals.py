from django.db import transaction
from django.db.models.signals import m2m_changed, post_delete, post_save
from django.dispatch import receiver

from apps.core.cache import bump

from .models import Brand, Category, Product, ProductImage
from .search import update_search_index


def _reindex(ids):
    ids = list(ids)
    if ids:
        transaction.on_commit(lambda: update_search_index(ids))


@receiver(post_save, sender=Product)
def product_saved(sender, instance, raw=False, **kwargs):
    if raw:
        return
    _reindex([instance.pk])
    bump("home", "menu")


@receiver(m2m_changed, sender=Product.categorias.through)
def product_categories_changed(sender, instance, action, reverse, pk_set, **kwargs):
    if action not in ("post_add", "post_remove", "post_clear"):
        return
    if reverse:  # se cambiaron productos desde la categoría
        _reindex(pk_set or [])
    else:
        _reindex([instance.pk])
    bump("home", "menu")


@receiver(post_save, sender=Category)
@receiver(post_delete, sender=Category)
def category_changed(sender, instance, **kwargs):
    bump("menu", "home")
    if kwargs.get("signal") is post_save and not kwargs.get("raw"):
        _reindex(instance.productos.values_list("pk", flat=True))


@receiver(post_save, sender=Brand)
def brand_changed(sender, instance, raw=False, **kwargs):
    bump("menu", "home")
    if not raw:
        _reindex(instance.productos.values_list("pk", flat=True))


@receiver(post_delete, sender=Product)
@receiver(post_save, sender=ProductImage)
@receiver(post_delete, sender=ProductImage)
def generic_changed(sender, **kwargs):
    bump("home", "menu")
