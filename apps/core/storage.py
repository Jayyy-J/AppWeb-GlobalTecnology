from django.conf import settings
from django.core.files.storage import FileSystemStorage
from django.utils.functional import LazyObject


class PrivateStorage(LazyObject):
    """Almacenamiento de evidencias: sin URL pública; se sirven con una vista protegida."""

    def _setup(self):
        self._wrapped = FileSystemStorage(
            location=str(settings.MEDIA_ROOT / settings.PRIVATE_MEDIA_DIR), base_url=None
        )


private_storage = PrivateStorage()


def get_private_storage():
    return private_storage
