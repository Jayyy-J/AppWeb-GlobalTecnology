from django.db import models
from django.urls import reverse
from django.utils import timezone

from apps.core.images import replace_with_webp, validate_image_file
from apps.core.models import SingletonModel, TimeStampedModel


class StoreSettings(SingletonModel):
    nombre = models.CharField("nombre de la tienda", max_length=80, default="GlobalTecnology")
    eslogan = models.CharField("eslogan", max_length=140, blank=True, default="Tecnología que te conecta con el mundo")
    logo = models.ImageField("logo", upload_to="tienda/", blank=True, validators=[validate_image_file])
    favicon = models.ImageField("favicon", upload_to="tienda/", blank=True, validators=[validate_image_file])
    whatsapp = models.CharField("número de WhatsApp", max_length=20, blank=True, help_text="Con indicativo, ej. 573001234567")
    email_contacto = models.EmailField("email de contacto", blank=True, default="ventas@globaltecnology.co")
    telefono = models.CharField("teléfono", max_length=30, blank=True)
    direccion = models.CharField("dirección física", max_length=200, blank=True)
    facebook = models.URLField("Facebook", blank=True)
    instagram = models.URLField("Instagram", blank=True)
    tiktok = models.URLField("TikTok", blank=True)
    youtube = models.URLField("YouTube", blank=True)
    texto_pie = models.TextField("texto del pie de página", blank=True, default="Tienda de tecnología en Colombia. Pagos seguros con Wompi.")
    barra_anuncios = models.CharField("barra de anuncios", max_length=160, blank=True, default="Envío gratis desde $200.000 a toda Colombia")
    razon_social = models.CharField("razón social", max_length=160, blank=True, default="GlobalTecnology S.A.S.")
    nit = models.CharField("NIT", max_length=20, blank=True, default="900.000.000-0")
    meta_descripcion = models.CharField(
        "meta descripción", max_length=160, blank=True,
        default="Compra tecnología en Colombia: celulares, portátiles, audio, gaming y accesorios con envío a todo el país.",
    )

    class Meta:
        verbose_name = "configuración de la tienda"
        verbose_name_plural = "configuración de la tienda"

    def __str__(self):
        return self.nombre

    def save(self, *args, **kwargs):
        replace_with_webp(self.logo, 600)
        replace_with_webp(self.favicon, 256)
        super().save(*args, **kwargs)

    @property
    def whatsapp_url(self):
        num = "".join(ch for ch in self.whatsapp if ch.isdigit())
        return f"https://wa.me/{num}" if num else ""


class BannerQuerySet(models.QuerySet):
    def vigentes(self):
        now = timezone.now()
        return self.filter(activo=True).filter(
            models.Q(inicia__isnull=True) | models.Q(inicia__lte=now),
            models.Q(termina__isnull=True) | models.Q(termina__gte=now),
        )


class Banner(TimeStampedModel):
    titulo = models.CharField("título", max_length=120)
    subtitulo = models.CharField("subtítulo", max_length=200, blank=True)
    texto_boton = models.CharField("texto del botón", max_length=40, blank=True, default="Ver más")
    enlace = models.CharField("enlace", max_length=300, blank=True, help_text="URL completa o ruta, ej. /categoria/celulares/")
    imagen_escritorio = models.ImageField("imagen escritorio", upload_to="banners/", validators=[validate_image_file])
    imagen_movil = models.ImageField("imagen móvil", upload_to="banners/", blank=True, validators=[validate_image_file])
    orden = models.PositiveIntegerField("orden", default=0)
    activo = models.BooleanField("activo", default=True)
    inicia = models.DateTimeField("inicia", null=True, blank=True)
    termina = models.DateTimeField("termina", null=True, blank=True)

    objects = BannerQuerySet.as_manager()

    class Meta:
        verbose_name = "banner"
        verbose_name_plural = "banners"
        ordering = ["orden", "-creado"]

    def __str__(self):
        return self.titulo

    def save(self, *args, **kwargs):
        replace_with_webp(self.imagen_escritorio, 2000)
        replace_with_webp(self.imagen_movil, 1000)
        super().save(*args, **kwargs)


class LegalPage(TimeStampedModel):
    titulo = models.CharField("título", max_length=120)
    slug = models.SlugField("slug", unique=True)
    contenido = models.TextField("contenido (HTML básico)")
    borrador_revision = models.BooleanField(
        "pendiente de revisión por abogado", default=True,
        help_text="Texto base. Debe revisarlo un abogado antes de publicarse como definitivo.",
    )
    orden = models.PositiveIntegerField(default=0)
    activa = models.BooleanField(default=True)

    class Meta:
        verbose_name = "página legal"
        verbose_name_plural = "páginas legales"
        ordering = ["orden", "titulo"]

    def __str__(self):
        return self.titulo

    def get_absolute_url(self):
        return reverse("storefront:legal", args=[self.slug])

    def save(self, *args, **kwargs):
        from apps.core.html import sanitize_html

        self.contenido = sanitize_html(self.contenido)
        super().save(*args, **kwargs)
