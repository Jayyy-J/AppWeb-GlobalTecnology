from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver

from apps.core.cache import bump

from .models import Banner, LegalPage, StoreSettings


@receiver(post_save, sender=Banner)
@receiver(post_delete, sender=Banner)
@receiver(post_save, sender=StoreSettings)
@receiver(post_save, sender=LegalPage)
@receiver(post_delete, sender=LegalPage)
def contenido_cambiado(sender, **kwargs):
    bump("home", "menu")
