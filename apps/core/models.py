from django.core.cache import cache
from django.db import models


class TimeStampedModel(models.Model):
    creado = models.DateTimeField("creado", auto_now_add=True)
    actualizado = models.DateTimeField("actualizado", auto_now=True)

    class Meta:
        abstract = True


class SingletonModel(models.Model):
    """Modelo de una sola fila (pk=1), cacheado."""

    class Meta:
        abstract = True

    @classmethod
    def _cache_key(cls):
        return f"singleton:{cls._meta.label_lower}"

    def save(self, *args, **kwargs):
        self.pk = 1
        super().save(*args, **kwargs)
        cache.delete(self._cache_key())

    def delete(self, *args, **kwargs):  # no se borra
        return None

    @classmethod
    def load(cls):
        obj = cache.get(cls._cache_key())
        if obj is None:
            obj, _ = cls.objects.get_or_create(pk=1)
            cache.set(cls._cache_key(), obj, 60 * 10)
        return obj
