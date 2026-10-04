from django import forms
from django.contrib.auth import get_user_model, password_validation
from django.core.exceptions import ValidationError
from django.db.models import Q

from .models import Branch, Membership, Professional


TEAM_ROLES = (
    (Membership.Role.ADMIN, "Administrador"),
    (Membership.Role.HAIRDRESSER, "Peluquero"),
)


class CreateTeamMemberForm(forms.Form):
    username = forms.CharField(label="Usuario", max_length=150)
    first_name = forms.CharField(label="Nombre", max_length=150)
    last_name = forms.CharField(label="Apellido", max_length=150)
    email = forms.EmailField(label="Correo electrónico")
    password1 = forms.CharField(label="Contraseña inicial", widget=forms.PasswordInput)
    password2 = forms.CharField(label="Confirmar contraseña", widget=forms.PasswordInput)
    role = forms.ChoiceField(label="Rol", choices=TEAM_ROLES)
    branches = forms.ModelMultipleChoiceField(
        label="Sucursales autorizadas",
        queryset=Branch.objects.none(),
        widget=forms.CheckboxSelectMultiple,
    )
    professional = forms.ModelChoiceField(
        label="Vincular profesional (opcional)",
        queryset=Professional.objects.none(),
        required=False,
        help_text="Ser profesional es independiente del rol operativo.",
    )

    def __init__(self, *args, salon, **kwargs):
        super().__init__(*args, **kwargs)
        self.salon = salon
        self.fields["branches"].queryset = salon.branches.all()
        self.fields["professional"].queryset = salon.professionals.filter(user__isnull=True)

    def clean_username(self):
        value = self.cleaned_data["username"].strip()
        User = get_user_model()
        if User.objects.filter(username__iexact=value).exists():
            raise forms.ValidationError("Ese nombre de usuario no está disponible.")
        return value

    def clean_email(self):
        value = self.cleaned_data["email"].strip().lower()
        User = get_user_model()
        if User.objects.filter(email__iexact=value).exists():
            raise forms.ValidationError("Ese correo no está disponible.")
        return value

    def clean(self):
        cleaned_data = super().clean()
        password1 = cleaned_data.get("password1")
        password2 = cleaned_data.get("password2")
        if password1 and password2 and password1 != password2:
            self.add_error("password2", "Las contraseñas no coinciden.")
            return cleaned_data
        if password1:
            User = get_user_model()
            candidate = User(
                username=cleaned_data.get("username", ""),
                email=cleaned_data.get("email", ""),
                first_name=cleaned_data.get("first_name", ""),
                last_name=cleaned_data.get("last_name", ""),
            )
            try:
                password_validation.validate_password(password1, user=candidate)
            except ValidationError as error:
                self.add_error("password1", error)
        return cleaned_data


class EditTeamMembershipForm(forms.Form):
    role = forms.ChoiceField(label="Rol", choices=TEAM_ROLES)
    branches = forms.ModelMultipleChoiceField(
        label="Sucursales autorizadas",
        queryset=Branch.objects.none(),
        widget=forms.CheckboxSelectMultiple,
    )
    professional = forms.ModelChoiceField(
        label="Profesional vinculado (opcional)",
        queryset=Professional.objects.none(),
        required=False,
    )
    active = forms.BooleanField(label="Membresía activa", required=False)

    def __init__(self, *args, salon, membership, **kwargs):
        self.salon = salon
        self.membership = membership
        current_professional = salon.professionals.filter(user=membership.user).first()
        kwargs.setdefault(
            "initial",
            {
                "role": membership.role,
                "branches": membership.branches.all(),
                "professional": current_professional,
                "active": membership.active,
            },
        )
        super().__init__(*args, **kwargs)
        self.fields["branches"].queryset = salon.branches.all()
        self.fields["professional"].queryset = salon.professionals.filter(
            Q(user__isnull=True) | Q(user=membership.user)
        ).distinct()
