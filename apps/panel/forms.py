import json

from django import forms

from apps.catalog.models import Brand, Category, Product
from apps.core.images import validate_image_file
from apps.shipping.models import Departamento, Municipio, ShippingSettings, ShippingZoneRate
from apps.storefront.models import Banner, LegalPage, StoreSettings


class Estilo:
    def _estilo(self):
        for f in self.fields.values():
            w = f.widget
            if isinstance(w, (forms.CheckboxInput, forms.CheckboxSelectMultiple, forms.RadioSelect)):
                continue
            w.attrs.setdefault("class", "input")


class MultipleFileInput(forms.ClearableFileInput):
    allow_multiple_selected = True


class MultipleImageField(forms.FileField):
    widget = MultipleFileInput

    def __init__(self, *args, **kwargs):
        kwargs.setdefault("required", False)
        super().__init__(*args, **kwargs)
        self.widget.attrs.update({"accept": "image/jpeg,image/png,image/webp", "multiple": True})

    def clean(self, data, initial=None):
        archivos = data if isinstance(data, (list, tuple)) else ([data] if data else [])
        limpios = []
        for f in archivos:
            f = super().clean(f, initial)
            if f:
                validate_image_file(f)
                limpios.append(f)
        return limpios


class DateTimeLocal(forms.DateTimeInput):
    input_type = "datetime-local"

    def __init__(self, **kwargs):
        super().__init__(format="%Y-%m-%dT%H:%M", **kwargs)


class ProductForm(Estilo, forms.ModelForm):
    especificaciones_json = forms.CharField(widget=forms.HiddenInput, required=False)
    imagenes_nuevas = MultipleImageField(label="Subir fotos")

    class Meta:
        model = Product
        fields = [
            "nombre", "sku", "marca", "categoria_principal", "categorias", "descripcion_corta", "descripcion",
            "precio", "tipo_descuento", "descuento_porcentaje", "precio_antes", "descuento_inicia", "descuento_termina",
            "stock", "stock_minimo_alerta", "activo", "destacado", "nuevo",
        ]
        widgets = {
            "categorias": forms.CheckboxSelectMultiple,
            "descripcion": forms.Textarea(attrs={"rows": 8}),
            "descripcion_corta": forms.Textarea(attrs={"rows": 2}),
            "descuento_inicia": DateTimeLocal(),
            "descuento_termina": DateTimeLocal(),
            "tipo_descuento": forms.RadioSelect,
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        cats = Category.objects.select_related("parent").order_by("parent__orden", "parent__nombre", "orden", "nombre")
        self.fields["categorias"].queryset = cats
        self.fields["categoria_principal"].queryset = cats
        self.fields["marca"].queryset = Brand.objects.order_by("nombre")
        self.fields["categorias"].required = False
        self.fields["descripcion"].help_text = "HTML básico permitido (p, strong, ul, li, h2…). Se sanea al guardar."
        self.fields["precio"].widget.attrs.update({"x-model.number": "precio", "inputmode": "numeric"})
        self.fields["descuento_porcentaje"].widget.attrs.update({"x-model.number": "pct", "min": 1, "max": 90})
        self.fields["precio_antes"].widget.attrs.update({"x-model.number": "antes", "inputmode": "numeric"})
        self.fields["tipo_descuento"].widget.attrs.update({"x-model": "tipo"})
        self.fields["especificaciones_json"].initial = json.dumps(
            [{"k": k, "v": v} for k, v in (self.instance.especificaciones or {}).items()], ensure_ascii=False
        )
        self._estilo()

    def clean_especificaciones_json(self):
        raw = self.cleaned_data.get("especificaciones_json") or "[]"
        try:
            filas = json.loads(raw)
            assert isinstance(filas, list)
        except (ValueError, AssertionError):
            raise forms.ValidationError("Especificaciones inválidas.")
        specs = {}
        for f in filas:
            k, v = str(f.get("k", "")).strip()[:60], str(f.get("v", "")).strip()[:120]
            if k and v:
                if "__" in k:
                    raise forms.ValidationError(f"La clave «{k}» no puede contener «__».")
                specs[k] = v
        return specs

    def clean_sku(self):
        return self.cleaned_data["sku"].strip().upper()

    def clean(self):
        cleaned = super().clean()
        principal = cleaned.get("categoria_principal")
        cats = list(cleaned.get("categorias") or [])
        if principal and principal not in cats:
            cats.append(principal)
        if principal and principal.parent and principal.parent not in cats:
            cats.append(principal.parent)
        cleaned["categorias"] = cats
        return cleaned

    def save(self, commit=True):
        self.instance.especificaciones = self.cleaned_data.get("especificaciones_json") or {}
        return super().save(commit)


class ProductBulkForm(forms.Form):
    ACCIONES = [
        ("activar", "Activar"), ("desactivar", "Desactivar"), ("destacar", "Destacar"), ("no_destacar", "Quitar destacado"),
        ("asignar_categoria", "Asignar categoría"), ("quitar_categoria", "Quitar de categoría"),
        ("aplicar_descuento", "Aplicar descuento %"), ("quitar_descuento", "Quitar descuento"),
    ]
    accion = forms.ChoiceField(choices=ACCIONES)
    ids = forms.ModelMultipleChoiceField(queryset=Product.objects.all(), error_messages={"required": "Selecciona al menos un producto."})
    categoria = forms.ModelChoiceField(queryset=Category.objects.all(), required=False)
    porcentaje = forms.IntegerField(min_value=1, max_value=90, required=False)

    def clean(self):
        c = super().clean()
        if c.get("accion") in ("asignar_categoria", "quitar_categoria") and not c.get("categoria"):
            self.add_error("categoria", "Elige la categoría.")
        if c.get("accion") == "aplicar_descuento" and not c.get("porcentaje"):
            self.add_error("porcentaje", "Indica el porcentaje (1–90).")
        return c


class CategoryForm(Estilo, forms.ModelForm):
    class Meta:
        model = Category
        fields = ["nombre", "slug", "parent", "descripcion", "imagen", "orden", "activa", "mostrar_en_menu"]
        widgets = {"descripcion": forms.Textarea(attrs={"rows": 3})}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        qs = Category.objects.filter(parent__isnull=True)
        if self.instance.pk:
            qs = qs.exclude(pk=self.instance.pk)
        self.fields["parent"].queryset = qs
        self.fields["parent"].empty_label = "— Ninguna (categoría principal) —"
        self.fields["slug"].required = False
        self.fields["slug"].help_text = "Se genera automáticamente si lo dejas vacío."
        self._estilo()


class BrandForm(Estilo, forms.ModelForm):
    class Meta:
        model = Brand
        fields = ["nombre", "slug", "logo", "activa"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["slug"].required = False
        self._estilo()


class ShippingSettingsForm(Estilo, forms.ModelForm):
    class Meta:
        model = ShippingSettings
        fields = ["envio_gratis_activo", "envio_gratis_desde", "tarifas_por_zona_activas", "tarifa_fija_activa",
                  "tarifa_fija_valor", "cotizacion_manual_activa"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._estilo()


class ZoneRateForm(Estilo, forms.ModelForm):
    class Meta:
        model = ShippingZoneRate
        fields = ["departamento", "municipio", "valor", "dias_estimados", "activo"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        dep = self.data.get("departamento") or (self.instance.departamento_id if self.instance.pk else None)
        self.fields["municipio"].queryset = (
            Municipio.objects.filter(departamento_id=dep) if dep and str(dep).isdigit() else Municipio.objects.none()
        )
        self.fields["municipio"].empty_label = "— Todo el departamento —"
        self.fields["departamento"].widget.attrs.update({
            "hx-get": "/ubicaciones/municipios/", "hx-target": "#id_municipio", "hx-trigger": "change", "hx-include": "this",
        })
        self._estilo()

    def clean(self):
        c = super().clean()
        dep, mun = c.get("departamento"), c.get("municipio")
        if dep and mun and mun.departamento_id != dep.id:
            self.add_error("municipio", "El municipio no pertenece al departamento.")
        if dep:
            dup = ShippingZoneRate.objects.filter(departamento=dep, municipio=mun)
            if self.instance.pk:
                dup = dup.exclude(pk=self.instance.pk)
            if dup.exists():
                raise forms.ValidationError("Ya existe una tarifa para ese destino. Edítala en lugar de crear otra.")
        return c


class CSVImportForm(forms.Form):
    archivo = forms.FileField(label="Archivo CSV", help_text="Columnas: departamento;municipio;valor;dias;activo (código DANE o nombre).")

    def clean_archivo(self):
        f = self.cleaned_data["archivo"]
        if f.size > 2 * 1024 * 1024:
            raise forms.ValidationError("El archivo supera 2 MB.")
        return f


class StoreSettingsForm(Estilo, forms.ModelForm):
    class Meta:
        model = StoreSettings
        fields = ["nombre", "eslogan", "logo", "favicon", "barra_anuncios", "whatsapp", "telefono", "email_contacto",
                  "direccion", "facebook", "instagram", "tiktok", "youtube", "texto_pie", "razon_social", "nit",
                  "meta_descripcion"]
        widgets = {"texto_pie": forms.Textarea(attrs={"rows": 2})}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._estilo()


class BannerForm(Estilo, forms.ModelForm):
    class Meta:
        model = Banner
        fields = ["titulo", "subtitulo", "texto_boton", "enlace", "imagen_escritorio", "imagen_movil", "orden", "activo",
                  "inicia", "termina"]
        widgets = {"inicia": DateTimeLocal(), "termina": DateTimeLocal()}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["imagen_escritorio"].help_text = "Recomendado 2000 × 750 px."
        self.fields["imagen_movil"].help_text = "Opcional. Recomendado 1000 × 1250 px."
        self._estilo()

    def clean_enlace(self):
        v = (self.cleaned_data.get("enlace") or "").strip()
        if v and not (v.startswith("/") or v.startswith("https://") or v.startswith("http://")):
            raise forms.ValidationError("Usa una ruta (/ofertas/) o una URL completa (https://…).")
        return v


class LegalPageForm(Estilo, forms.ModelForm):
    class Meta:
        model = LegalPage
        fields = ["titulo", "contenido", "borrador_revision", "activa", "orden"]
        widgets = {"contenido": forms.Textarea(attrs={"rows": 22})}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._estilo()


class FiltroFechasForm(forms.Form):
    desde = forms.DateField(label="Desde", widget=forms.DateInput(attrs={"type": "date", "class": "input"}))
    hasta = forms.DateField(label="Hasta", widget=forms.DateInput(attrs={"type": "date", "class": "input"}))

    def clean(self):
        c = super().clean()
        if c.get("desde") and c.get("hasta") and c["desde"] > c["hasta"]:
            raise forms.ValidationError("La fecha inicial debe ser anterior a la final.")
        return c


def departamentos():
    return Departamento.objects.order_by("nombre")
