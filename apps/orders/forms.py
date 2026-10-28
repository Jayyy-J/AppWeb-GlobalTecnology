from django import forms

from apps.accounts.forms import StyledMixin
from apps.accounts.models import User

from .models import EstadoPedido


class CheckoutForm(StyledMixin, forms.Form):
    direccion = forms.CharField(widget=forms.HiddenInput, required=False)  # id de dirección o "nueva"
    first_name = forms.CharField(label="Nombre", max_length=150)
    last_name = forms.CharField(label="Apellido", max_length=150)
    email = forms.EmailField(label="Email")
    telefono = forms.CharField(label="Teléfono", max_length=20)
    tipo_documento = forms.ChoiceField(label="Tipo de documento", choices=User.TipoDocumento.choices)
    numero_documento = forms.CharField(label="Número de documento", max_length=20)
    notas_cliente = forms.CharField(label="Notas para la entrega", max_length=300, required=False,
                                    widget=forms.TextInput(attrs={"placeholder": "Ej. horario de entrega"}))
    acepta_terminos = forms.BooleanField(
        label="Acepto los términos y condiciones, la política de envíos y la política de privacidad.",
        error_messages={"required": "Debes aceptar los términos y condiciones para continuar."},
    )

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.user = user
        self._style()
        self.fields["telefono"].widget.attrs.update({"autocomplete": "tel", "inputmode": "tel"})
        self.fields["numero_documento"].widget.attrs.update({"inputmode": "numeric"})

    def clean_numero_documento(self):
        v = self.cleaned_data["numero_documento"].strip().replace(".", "").replace(" ", "")
        if not v.replace("-", "").isalnum():
            raise forms.ValidationError("Número de documento no válido.")
        return v

    def clean_telefono(self):
        v = "".join(ch for ch in self.cleaned_data["telefono"] if ch.isdigit() or ch == "+")
        if len(v.replace("+", "")) < 7:
            raise forms.ValidationError("Escribe un teléfono válido.")
        return v


class CotizacionForm(forms.Form):
    costo_envio = forms.IntegerField(label="Valor del envío (COP)", min_value=0, max_value=50_000_000)
    nota = forms.CharField(label="Nota para el cliente (opcional)", required=False, widget=forms.Textarea(attrs={"rows": 3}))


class CambioEstadoForm(forms.Form):
    """Cambio de estado desde el panel con las reglas de evidencia (también validadas en el servicio)."""

    estado = forms.ChoiceField(label="Nuevo estado")
    metodo_entrega = forms.ChoiceField(
        label="Método de entrega", required=False, widget=forms.RadioSelect,
        choices=[("transportadora", "Transportadora"), ("personal", "Entrega personal")],
    )
    transportadora = forms.CharField(label="Transportadora", max_length=100, required=False,
                                     widget=forms.TextInput(attrs={"placeholder": "Servientrega, Interrapidísimo, Coordinadora…", "list": "transportadoras"}))
    numero_guia = forms.CharField(label="Número de guía", max_length=100, required=False)
    url_rastreo = forms.URLField(label="URL de rastreo", required=False, assume_scheme="https")
    entregado_por = forms.CharField(label="Nombre de quien entrega", max_length=120, required=False)
    foto = forms.ImageField(label="Foto de evidencia", required=False)
    nota = forms.CharField(label="Nota visible para el cliente", required=False, widget=forms.Textarea(attrs={"rows": 3}))

    def __init__(self, *args, pedido=None, **kwargs):
        from .services import transiciones_posibles

        super().__init__(*args, **kwargs)
        self.pedido = pedido
        opciones = [(e, EstadoPedido(e).label) for e in transiciones_posibles(pedido)
                    if e != EstadoPedido.PENDIENTE_PAGO]  # el pago se habilita con la cotización
        self.fields["estado"].choices = opciones
        for name, f in self.fields.items():
            if not isinstance(f.widget, (forms.RadioSelect,)):
                f.widget.attrs.setdefault("class", "input")

    def clean_foto(self):
        from apps.core.images import validate_image_file

        f = self.cleaned_data.get("foto")
        if f:
            validate_image_file(f)
        return f

    def clean(self):
        from .services import TransicionInvalida, validar_transicion

        cleaned = super().clean()
        estado = cleaned.get("estado")
        if not estado or self.errors:
            return cleaned
        try:
            validar_transicion(
                self.pedido, estado, foto=cleaned.get("foto"), metodo_entrega=cleaned.get("metodo_entrega") or None,
                transportadora=cleaned.get("transportadora", ""), entregado_por=cleaned.get("entregado_por", ""),
            )
        except TransicionInvalida as e:
            if hasattr(e, "error_dict"):
                for campo, errs in e.error_dict.items():
                    self.add_error(campo if campo in self.fields else None, errs)
            else:
                self.add_error(None, e)
        return cleaned
