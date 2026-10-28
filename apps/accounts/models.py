from django.contrib.auth.models import AbstractUser, BaseUserManager
from django.db import models
from django.utils import timezone


class UserManager(BaseUserManager):
    use_in_migrations = True

    def _create_user(self, email, password, **extra):
        if not email:
            raise ValueError("El email es obligatorio")
        email = self.normalize_email(email).lower()
        user = self.model(email=email, **extra)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_user(self, email, password=None, **extra):
        extra.setdefault("is_staff", False)
        extra.setdefault("is_superuser", False)
        return self._create_user(email, password, **extra)

    def create_superuser(self, email, password=None, **extra):
        extra.setdefault("is_staff", True)
        extra.setdefault("is_superuser", True)
        if extra.get("is_staff") is not True or extra.get("is_superuser") is not True:
            raise ValueError("El superusuario debe tener is_staff e is_superuser")
        return self._create_user(email, password, **extra)

    def get_by_natural_key(self, email):
        return self.get(email__iexact=email)


class User(AbstractUser):
    class TipoDocumento(models.TextChoices):
        CC = "CC", "Cédula de ciudadanía"
        CE = "CE", "Cédula de extranjería"
        NIT = "NIT", "NIT"
        PP = "PP", "Pasaporte"

    username = None
    first_name = models.CharField("nombre", max_length=150)
    last_name = models.CharField("apellido", max_length=150)
    email = models.EmailField("email", unique=True)
    telefono = models.CharField("teléfono", max_length=20, blank=True)
    tipo_documento = models.CharField(
        "tipo de documento", max_length=3, choices=TipoDocumento.choices, default=TipoDocumento.CC
    )
    numero_documento = models.CharField("número de documento", max_length=20, blank=True)
    acepta_tratamiento_datos = models.BooleanField("acepta tratamiento de datos", default=False)
    fecha_aceptacion_datos = models.DateTimeField("fecha de aceptación", null=True, blank=True)

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = ["first_name", "last_name"]

    objects = UserManager()

    class Meta:
        verbose_name = "usuario"
        verbose_name_plural = "usuarios"
        ordering = ["-date_joined"]

    def __str__(self):
        return self.get_full_name() or self.email

    def save(self, *args, **kwargs):
        self.email = (self.email or "").strip().lower()
        if self.acepta_tratamiento_datos and not self.fecha_aceptacion_datos:
            self.fecha_aceptacion_datos = timezone.now()
        super().save(*args, **kwargs)

    @property
    def nombre_corto(self):
        return self.first_name or self.email.split("@")[0]


class Address(models.Model):
    usuario = models.ForeignKey(User, on_delete=models.CASCADE, related_name="direcciones")
    alias = models.CharField("alias", max_length=40, help_text='Ej. "Casa", "Oficina"')
    nombre_recibe = models.CharField("nombre de quien recibe", max_length=120)
    telefono = models.CharField("teléfono", max_length=20)
    departamento = models.ForeignKey("shipping.Departamento", on_delete=models.PROTECT, verbose_name="departamento")
    municipio = models.ForeignKey("shipping.Municipio", on_delete=models.PROTECT, verbose_name="municipio")
    direccion = models.CharField("dirección", max_length=200)
    barrio = models.CharField("barrio", max_length=100, blank=True)
    indicaciones = models.CharField("indicaciones adicionales", max_length=255, blank=True)
    es_predeterminada = models.BooleanField("predeterminada", default=False)
    creado = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "dirección"
        verbose_name_plural = "direcciones"
        ordering = ["-es_predeterminada", "-creado"]

    def __str__(self):
        return f"{self.alias}: {self.direccion}, {self.municipio}"

    def save(self, *args, **kwargs):
        if not self.pk and not Address.objects.filter(usuario=self.usuario).exists():
            self.es_predeterminada = True
        super().save(*args, **kwargs)
        if self.es_predeterminada:
            Address.objects.filter(usuario=self.usuario).exclude(pk=self.pk).update(es_predeterminada=False)

    def as_text(self):
        partes = [self.direccion]
        if self.barrio:
            partes.append(f"Barrio {self.barrio}")
        partes.append(f"{self.municipio.nombre}, {self.departamento.nombre}")
        texto = " · ".join(partes)
        if self.indicaciones:
            texto += f" ({self.indicaciones})"
        return texto
