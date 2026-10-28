"""Validación y procesamiento de imágenes subidas (Pillow → WebP)."""
import io
import uuid

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.files.base import ContentFile
from PIL import Image, ImageOps, UnidentifiedImageError

ALLOWED_FORMATS = {"JPEG", "PNG", "WEBP", "GIF", "MPO"}
Image.MAX_IMAGE_PIXELS = 60_000_000  # protección ante "bombas" de descompresión


def validate_image_file(f):
    """Valida el tipo real (con Pillow, no por extensión) y el peso máximo."""
    if f is None:
        return
    max_bytes = settings.MAX_UPLOAD_MB * 1024 * 1024
    size = getattr(f, "size", None)
    if size is not None and size > max_bytes:
        raise ValidationError(f"La imagen pesa más de {settings.MAX_UPLOAD_MB} MB.")
    try:
        pos = f.tell() if hasattr(f, "tell") else 0
        img = Image.open(f)
        fmt = img.format
        img.verify()
        f.seek(pos)
    except (UnidentifiedImageError, OSError, SyntaxError, Image.DecompressionBombError):
        raise ValidationError("El archivo no es una imagen válida (usa JPG, PNG o WebP).")
    if fmt not in ALLOWED_FORMATS:
        raise ValidationError("Formato de imagen no permitido (usa JPG, PNG o WebP).")


def _open_rgb(f):
    if hasattr(f, "seek"):
        f.seek(0)
    img = Image.open(f)
    img = ImageOps.exif_transpose(img)
    if img.mode in ("RGBA", "LA") or (img.mode == "P" and "transparency" in img.info):
        img = img.convert("RGBA")
    else:
        img = img.convert("RGB")
    return img


def to_webp(img, max_side: int, quality: int = 82):
    """Redimensiona (sin agrandar) y codifica en WebP. Devuelve (ContentFile, ancho, alto)."""
    im = img.copy()
    im.thumbnail((max_side, max_side), Image.Resampling.LANCZOS)
    buf = io.BytesIO()
    im.save(buf, "WEBP", quality=quality, method=4)
    return ContentFile(buf.getvalue()), im.width, im.height


def random_name(suffix: str = "", ext: str = "webp") -> str:
    return f"{uuid.uuid4().hex}{('-' + suffix) if suffix else ''}.{ext}"


def process_upload(f, sizes: dict[str, int]):
    """Convierte una subida a varios tamaños WebP.

    sizes = {"grande": 1600, "media": 800, "thumb": 300}
    Devuelve {nombre: (ContentFile con .name, ancho, alto)}.
    """
    img = _open_rgb(f)
    base = uuid.uuid4().hex
    out = {}
    for key, side in sizes.items():
        content, w, h = to_webp(img, side)
        content.name = f"{base}-{key}.webp"
        out[key] = (content, w, h)
    return out


def replace_with_webp(field_file, max_side: int = 1600):
    """Para ImageFields simples (categorías, banners, logos): convierte el archivo recién subido a WebP."""
    if not field_file or getattr(field_file, "_committed", True):
        return
    img = _open_rgb(field_file.file)
    content, _, _ = to_webp(img, max_side)
    field_file.save(random_name(), content, save=False)
