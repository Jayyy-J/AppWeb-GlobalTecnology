from django import forms

from apps.accounts.forms import StyledMixin
from apps.accounts.models import User


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
