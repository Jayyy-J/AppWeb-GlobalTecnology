from django import forms
from django.contrib.auth import password_validation
from django.contrib.auth.forms import AuthenticationForm, PasswordChangeForm, PasswordResetForm, SetPasswordForm

from .models import Address, User


class StyledMixin:
    """Agrega clases CSS y atributos de accesibilidad a los widgets."""

    def _style(self):
        for name, field in self.fields.items():
            w = field.widget
            if isinstance(w, forms.CheckboxInput):
                w.attrs.setdefault("class", "check")
            else:
                w.attrs.setdefault("class", "input")
            if field.required:
                w.attrs.setdefault("required", "required")


class LoginForm(StyledMixin, AuthenticationForm):
    username = forms.EmailField(label="Email", widget=forms.EmailInput(attrs={"autocomplete": "email", "autofocus": True}))
    error_messages = {
        "invalid_login": "Email o contraseña incorrectos.",
        "inactive": "Esta cuenta está desactivada. Escríbenos si crees que es un error.",
    }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["password"].label = "Contraseña"
        self._style()


class RegistroForm(StyledMixin, forms.ModelForm):
    password1 = forms.CharField(label="Contraseña", widget=forms.PasswordInput(attrs={"autocomplete": "new-password"}))
    password2 = forms.CharField(label="Confirmar contraseña", widget=forms.PasswordInput(attrs={"autocomplete": "new-password"}))
    acepta_tratamiento_datos = forms.BooleanField(
        label="Autorizo el tratamiento de mis datos personales según la política de privacidad (Ley 1581 de 2012).",
        required=True,
        error_messages={"required": "Debes autorizar el tratamiento de datos para crear tu cuenta."},
    )

    class Meta:
        model = User
        fields = ["first_name", "last_name", "email", "telefono"]
        widgets = {
            "email": forms.EmailInput(attrs={"autocomplete": "email"}),
            "telefono": forms.TextInput(attrs={"autocomplete": "tel", "inputmode": "tel"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["telefono"].required = True
        self._style()

    def clean_email(self):
        email = self.cleaned_data["email"].strip().lower()
        if User.objects.filter(email__iexact=email).exists():
            raise forms.ValidationError("Ya existe una cuenta con este email. ¿Quieres iniciar sesión?")
        return email

    def clean(self):
        cleaned = super().clean()
        p1, p2 = cleaned.get("password1"), cleaned.get("password2")
        if p1 and p2 and p1 != p2:
            self.add_error("password2", "Las contraseñas no coinciden.")
        if p1:
            tmp = User(email=cleaned.get("email", ""), first_name=cleaned.get("first_name", ""), last_name=cleaned.get("last_name", ""))
            try:
                password_validation.validate_password(p1, tmp)
            except forms.ValidationError as e:
                self.add_error("password1", e)
        return cleaned

    def save(self, commit=True):
        user = super().save(commit=False)
        user.set_password(self.cleaned_data["password1"])
        user.acepta_tratamiento_datos = True
        if commit:
            user.save()
        return user


class PerfilForm(StyledMixin, forms.ModelForm):
    class Meta:
        model = User
        fields = ["first_name", "last_name", "telefono", "tipo_documento", "numero_documento"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._style()


class AddressForm(StyledMixin, forms.ModelForm):
    class Meta:
        model = Address
        fields = [
            "alias", "nombre_recibe", "telefono", "departamento", "municipio",
            "direccion", "barrio", "indicaciones", "es_predeterminada",
        ]
        widgets = {
            "direccion": forms.TextInput(attrs={"placeholder": "Calle 10 # 20-30, apto 401", "autocomplete": "street-address"}),
            "alias": forms.TextInput(attrs={"placeholder": "Casa, Oficina…"}),
        }

    def __init__(self, *args, **kwargs):
        from apps.shipping.models import Municipio

        super().__init__(*args, **kwargs)
        dep_id = self.data.get(self.add_prefix("departamento")) or (self.instance.departamento_id if self.instance.pk else None)
        self.fields["municipio"].queryset = (
            Municipio.objects.filter(departamento_id=dep_id) if dep_id and str(dep_id).isdigit() else Municipio.objects.none()
        )
        self.fields["departamento"].empty_label = "Selecciona un departamento"
        self.fields["municipio"].empty_label = "Selecciona un municipio"
        self.fields["es_predeterminada"].label = "Usar como dirección predeterminada"
        self._style()

    def clean(self):
        cleaned = super().clean()
        dep, mun = cleaned.get("departamento"), cleaned.get("municipio")
        if dep and mun and mun.departamento_id != dep.id:
            self.add_error("municipio", "El municipio no pertenece al departamento.")
        return cleaned


class ClaveCambioForm(StyledMixin, PasswordChangeForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._style()


class RecuperarForm(StyledMixin, PasswordResetForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._style()

    def send_mail(self, subject_template_name, email_template_name, context, from_email, to_email, html_email_template_name=None):
        from apps.core.emails import send_templated

        send_templated("recuperar_clave", "Recupera tu contraseña de GlobalTecnology", to_email, context)


class NuevaClaveForm(StyledMixin, SetPasswordForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._style()
