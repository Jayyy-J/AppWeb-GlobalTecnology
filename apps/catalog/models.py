from decimal import ROUND_HALF_UP, Decimal

from django.contrib.postgres.search import SearchVectorField
from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.db.models import Case, ExpressionWrapper, F, IntegerField, Q, Value, When
from django.db.models.functions import Round
from django.urls import reverse
from django.utils import timezone
from django.utils.text import slugify

from apps.core.images import process_upload, replace_with_webp, validate_image_file
from apps.core.models import TimeStampedModel
from apps.core.text import normalize


def unique_slug(instance, value, field="slug", max_length=200):
    base = slugify(value)[: max_length - 8] or "item"
    slug, n = base, 2
    Model = type(instance)
    while Model.objects.filter(**{field: slug}).exclude(pk=instance.pk).exists():
        slug = f"{base}-{n}"
        n += 1
    return slug


class Category(TimeStampedModel):
    nombre = models.CharField("nombre", max_length=100)
    slug = models.SlugField("slug", max_length=120, unique=True, blank=True)
    descripcion = models.TextField("descripción", blank=True)
    imagen = models.ImageField("imagen", upload_to="categorias/", blank=True, validators=[validate_image_file])
    parent = models.ForeignKey(
        "self", on_delete=models.CASCADE, null=True, blank=True, related_name="hijas", verbose_name="categoría padre",
        limit_choices_to={"parent__isnull": True},
    )
    orden = models.PositiveIntegerField("orden", default=0)
    activa = models.BooleanField("activa", default=True)
    mostrar_en_menu = models.BooleanField("mostrar en el menú", default=True)

    class Meta:
        verbose_name = "categoría"
        verbose_name_plural = "categorías"
        ordering = ["orden", "nombre"]

    def __str__(self):
        return f"{self.parent.nombre} › {self.nombre}" if self.parent_id else self.nombre

    def clean(self):
        if self.parent_id:
            if self.parent_id == self.pk:
                raise ValidationError({"parent": "Una categoría no puede ser su propia padre."})
            if self.parent.parent_id:
                raise ValidationError({"parent": "Solo se permite un nivel de subcategorías."})
            if self.pk and self.hijas.exists():
                raise ValidationError({"parent": "Esta categoría tiene subcategorías; no puede ser subcategoría."})

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = unique_slug(self, self.nombre)
        replace_with_webp(self.imagen, 800)
        super().save(*args, **kwargs)

    def get_absolute_url(self):
        return reverse("catalog:categoria", args=[self.slug])

    def ids_con_hijas(self):
        return [self.pk, *self.hijas.filter(activa=True).values_list("pk", flat=True)]


class Brand(TimeStampedModel):
    nombre = models.CharField("nombre", max_length=100, unique=True)
    slug = models.SlugField("slug", max_length=120, unique=True, blank=True)
    logo = models.ImageField("logo", upload_to="marcas/", blank=True, validators=[validate_image_file])
    activa = models.BooleanField("activa", default=True)

    class Meta:
        verbose_name = "marca"
        verbose_name_plural = "marcas"
        ordering = ["nombre"]

    def __str__(self):
        return self.nombre

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = unique_slug(self, self.nombre)
        replace_with_webp(self.logo, 400)
        super().save(*args, **kwargs)

    def get_absolute_url(self):
        return reverse("catalog:marca", args=[self.slug])


def _descuento_vigente_q(now):
    return (Q(descuento_inicia__isnull=True) | Q(descuento_inicia__lte=now)) & (
        Q(descuento_termina__isnull=True) | Q(descuento_termina__gte=now)
    )


class ProductQuerySet(models.QuerySet):
    def activos(self):
        return self.filter(activo=True)

    def con_precios(self):
        """Anota precio_final_db y descuento_pct_db (para filtrar/ordenar en la BD)."""
        now = timezone.now()
        vigente = _descuento_vigente_q(now)
        return self.annotate(
            precio_final_db=Case(
                When(
                    vigente & Q(tipo_descuento="porcentaje", descuento_porcentaje__gt=0),
                    then=Round(
                        ExpressionWrapper(
                            F("precio") * (Value(100) - F("descuento_porcentaje")) / Value(100.0),
                            output_field=models.FloatField(),
                        )
                    ),
                ),
                default=F("precio"),
                output_field=IntegerField(),
            ),
            descuento_pct_db=Case(
                When(vigente & Q(tipo_descuento="porcentaje"), then=F("descuento_porcentaje")),
                When(
                    vigente & Q(tipo_descuento="precio_antes", precio_antes__gt=F("precio")),
                    then=Round(
                        ExpressionWrapper(
                            (F("precio_antes") - F("precio")) * Value(100.0) / F("precio_antes"),
                            output_field=models.FloatField(),
                        )
                    ),
                ),
                default=Value(0),
                output_field=IntegerField(),
            ),
        )

    def con_descuento(self):
        return self.con_precios().filter(descuento_pct_db__gt=0)

    def para_listado(self):
        return self.select_related("marca", "categoria_principal").prefetch_related(
            models.Prefetch("imagenes", queryset=ProductImage.objects.order_by("-es_principal", "orden", "id"))
        )


class Product(TimeStampedModel):
    class TipoDescuento(models.TextChoices):
        NINGUNO = "ninguno", "Sin descuento"
        PORCENTAJE = "porcentaje", "Porcentaje"
        PRECIO_ANTES = "precio_antes", "Precio antes (tachado)"

    nombre = models.CharField("nombre", max_length=200)
    slug = models.SlugField("slug", max_length=220, unique=True, blank=True)
    sku = models.CharField("SKU", max_length=60, unique=True)
    marca = models.ForeignKey(Brand, on_delete=models.SET_NULL, null=True, blank=True, related_name="productos")
    categorias = models.ManyToManyField(Category, related_name="productos", blank=True, verbose_name="categorías")
    categoria_principal = models.ForeignKey(
        Category, on_delete=models.SET_NULL, null=True, blank=True, related_name="productos_principales",
        verbose_name="categoría principal",
    )
    descripcion_corta = models.CharField("descripción corta", max_length=300, blank=True)
    descripcion = models.TextField("descripción larga", blank=True, help_text="HTML básico; se sanea al guardar.")
    precio = models.PositiveIntegerField("precio de venta (COP, IVA incluido)", validators=[MinValueValidator(1)])
    tipo_descuento = models.CharField("tipo de descuento", max_length=20, choices=TipoDescuento.choices, default=TipoDescuento.NINGUNO)
    descuento_porcentaje = models.PositiveSmallIntegerField(
        "descuento (%)", null=True, blank=True, validators=[MinValueValidator(1), MaxValueValidator(90)]
    )
    precio_antes = models.PositiveIntegerField("precio antes", null=True, blank=True)
    descuento_inicia = models.DateTimeField("descuento inicia", null=True, blank=True)
    descuento_termina = models.DateTimeField("descuento termina", null=True, blank=True)
    stock = models.PositiveIntegerField("stock", default=0)
    stock_minimo_alerta = models.PositiveIntegerField("alerta de stock mínimo", default=3)
    activo = models.BooleanField("activo", default=True)
    destacado = models.BooleanField("destacado", default=False)
    nuevo = models.BooleanField("nuevo", default=False)
    especificaciones = models.JSONField("especificaciones", default=dict, blank=True)
    search_vector = SearchVectorField(null=True, editable=False)
    search_text = models.TextField(editable=False, blank=True, default="")

    objects = ProductQuerySet.as_manager()

    class Meta:
        verbose_name = "producto"
        verbose_name_plural = "productos"
        ordering = ["-creado"]
        indexes = [
            models.Index(fields=["activo", "-creado"]),
            models.Index(fields=["activo", "destacado"]),
            models.Index(fields=["precio"]),
        ]

    def __str__(self):
        return self.nombre

    def get_absolute_url(self):
        return reverse("catalog:producto", args=[self.slug])

    # ---------- Validación ----------
    def clean(self):
        errors = {}
        if self.tipo_descuento == self.TipoDescuento.PORCENTAJE:
            if not self.descuento_porcentaje or not (1 <= self.descuento_porcentaje <= 90):
                errors["descuento_porcentaje"] = "Indica un porcentaje entre 1 y 90."
        elif self.tipo_descuento == self.TipoDescuento.PRECIO_ANTES:
            if not self.precio_antes or (self.precio and self.precio_antes <= self.precio):
                errors["precio_antes"] = "El precio antes debe ser mayor que el precio de venta."
        if self.descuento_inicia and self.descuento_termina and self.descuento_termina <= self.descuento_inicia:
            errors["descuento_termina"] = "La fecha de fin debe ser posterior a la de inicio."
        if not isinstance(self.especificaciones, dict):
            errors["especificaciones"] = "Las especificaciones deben ser pares clave/valor."
        if errors:
            raise ValidationError(errors)

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = unique_slug(self, self.nombre)
        if self.tipo_descuento != self.TipoDescuento.PORCENTAJE:
            self.descuento_porcentaje = None if self.tipo_descuento == self.TipoDescuento.NINGUNO else self.descuento_porcentaje
        if isinstance(self.especificaciones, dict):
            self.especificaciones = {str(k).strip(): str(v).strip() for k, v in self.especificaciones.items() if str(k).strip()}
        super().save(*args, **kwargs)

    # ---------- Precios (siempre calculados en el servidor) ----------
    def descuento_vigente(self, now=None) -> bool:
        now = now or timezone.now()
        if self.descuento_inicia and now < self.descuento_inicia:
            return False
        if self.descuento_termina and now > self.descuento_termina:
            return False
        return True

    @property
    def tiene_descuento(self) -> bool:
        if not self.descuento_vigente():
            return False
        if self.tipo_descuento == self.TipoDescuento.PORCENTAJE:
            return bool(self.descuento_porcentaje)
        if self.tipo_descuento == self.TipoDescuento.PRECIO_ANTES:
            return bool(self.precio_antes and self.precio_antes > self.precio)
        return False

    @property
    def precio_final(self) -> int:
        if self.tiene_descuento and self.tipo_descuento == self.TipoDescuento.PORCENTAJE:
            valor = Decimal(self.precio) * (Decimal(100) - Decimal(self.descuento_porcentaje)) / Decimal(100)
            return int(valor.quantize(Decimal("1"), rounding=ROUND_HALF_UP))
        return int(self.precio)

    @property
    def precio_tachado(self) -> int | None:
        """Precio de referencia mostrado tachado (None si no hay descuento)."""
        if not self.tiene_descuento:
            return None
        if self.tipo_descuento == self.TipoDescuento.PORCENTAJE:
            return int(self.precio)
        return int(self.precio_antes)

    @property
    def porcentaje_ahorro(self) -> int:
        ref = self.precio_tachado
        if not ref:
            return 0
        if self.tipo_descuento == self.TipoDescuento.PORCENTAJE:
            return int(self.descuento_porcentaje)
        pct = (Decimal(ref) - Decimal(self.precio_final)) * 100 / Decimal(ref)
        return int(pct.quantize(Decimal("1"), rounding=ROUND_HALF_UP))

    @property
    def ahorro(self) -> int:
        ref = self.precio_tachado
        return (ref - self.precio_final) if ref else 0

    @property
    def disponible(self) -> bool:
        return self.activo and self.stock > 0

    @property
    def stock_bajo(self) -> bool:
        return 0 < self.stock <= self.stock_minimo_alerta

    @property
    def imagen_principal(self):
        imgs = list(self.imagenes.all())  # usa prefetch si existe
        if not imgs:
            return None
        for im in imgs:
            if im.es_principal:
                return im
        return sorted(imgs, key=lambda i: (i.orden, i.id))[0]

    # ---------- Búsqueda ----------
    def build_search_text(self):
        partes = [self.nombre, self.sku, self.descripcion_corta]
        if self.marca_id:
            partes.append(self.marca.nombre)
        if self.pk:
            partes += [c.nombre for c in self.categorias.all()]
        partes += [f"{k} {v}" for k, v in (self.especificaciones or {}).items()]
        return normalize(" ".join(p for p in partes if p))


class ProductImage(models.Model):
    SIZES = {"grande": 1600, "media": 800, "thumb": 300}

    producto = models.ForeignKey(Product, on_delete=models.CASCADE, related_name="imagenes")
    imagen = models.ImageField("imagen (grande)", upload_to="productos/%Y/%m/", validators=[validate_image_file])
    imagen_media = models.ImageField(upload_to="productos/%Y/%m/", blank=True, editable=False)
    imagen_thumb = models.ImageField(upload_to="productos/%Y/%m/", blank=True, editable=False)
    ancho = models.PositiveIntegerField(default=0, editable=False)
    alto = models.PositiveIntegerField(default=0, editable=False)
    texto_alternativo = models.CharField("texto alternativo", max_length=200, blank=True)
    orden = models.PositiveIntegerField("orden", default=0)
    es_principal = models.BooleanField("principal", default=False)
    creado = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "imagen de producto"
        verbose_name_plural = "imágenes de producto"
        ordering = ["-es_principal", "orden", "id"]

    def __str__(self):
        return self.texto_alternativo or f"Imagen de {self.producto}"

    def save(self, *args, **kwargs):
        # Al subir una imagen nueva: convertir a WebP y generar los 3 tamaños.
        if self.imagen and not getattr(self.imagen, "_committed", True):
            out = process_upload(self.imagen.file, self.SIZES)
            g, gw, gh = out["grande"]
            self.imagen.save(g.name, g, save=False)
            self.ancho, self.alto = gw, gh
            m = out["media"][0]
            self.imagen_media.save(m.name, m, save=False)
            t = out["thumb"][0]
            self.imagen_thumb.save(t.name, t, save=False)
        if not self.texto_alternativo and self.producto_id:
            self.texto_alternativo = self.producto.nombre
        super().save(*args, **kwargs)
        if self.es_principal:
            ProductImage.objects.filter(producto_id=self.producto_id).exclude(pk=self.pk).update(es_principal=False)

    def delete(self, *args, **kwargs):
        files = [self.imagen, self.imagen_media, self.imagen_thumb]
        super().delete(*args, **kwargs)
        for f in files:
            if f:
                f.storage.delete(f.name)

    @property
    def url_thumb(self):
        return (self.imagen_thumb or self.imagen).url

    @property
    def url_media(self):
        return (self.imagen_media or self.imagen).url

    @property
    def srcset(self):
        partes = []
        if self.imagen_thumb:
            partes.append(f"{self.imagen_thumb.url} 300w")
        if self.imagen_media:
            partes.append(f"{self.imagen_media.url} 800w")
        if self.imagen:
            partes.append(f"{self.imagen.url} {self.ancho or 1600}w")
        return ", ".join(partes)

    @property
    def alt(self):
        return self.texto_alternativo or self.producto.nombre


class SearchLog(models.Model):
    termino = models.CharField("término normalizado", max_length=120, unique=True)
    cantidad_busquedas = models.PositiveIntegerField("búsquedas", default=0)
    cantidad_resultados = models.PositiveIntegerField("resultados (última vez)", default=0)
    ultima_fecha = models.DateTimeField("última búsqueda", default=timezone.now)

    class Meta:
        verbose_name = "registro de búsqueda"
        verbose_name_plural = "registro de búsquedas"
        ordering = ["-cantidad_busquedas"]

    def __str__(self):
        return self.termino
