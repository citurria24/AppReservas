from django import forms
from django.utils import timezone
from .models import Branch, Professional, Service


class GuestStartForm(forms.Form):
    first_name = forms.CharField(label="Nombre", max_length=100)
    last_name = forms.CharField(label="Apellido", max_length=100)
    email = forms.EmailField(label="Correo electrónico")
    contact = forms.CharField(label="Teléfono o contacto", max_length=100)


class GuestVerifyForm(forms.Form):
    code = forms.CharField(label="Código de verificación", min_length=6, max_length=6)


class BookingForm(forms.Form):
    branch = forms.ModelChoiceField(label="Sucursal", queryset=Branch.objects.none())
    service = forms.ModelChoiceField(label="Servicio", queryset=Service.objects.none())
    professional = forms.ModelChoiceField(label="Profesional", queryset=Professional.objects.none())
    date = forms.DateField(label="Fecha", widget=forms.DateInput(attrs={"type": "date"}))
    slot = forms.CharField(widget=forms.HiddenInput())
    notes = forms.CharField(label="Notas opcionales", required=False, widget=forms.Textarea(attrs={"rows": 3}))

    def __init__(self, *args, salon, **kwargs):
        super().__init__(*args, **kwargs)
        self.salon = salon
        self.fields["branch"].queryset = salon.branches.filter(active=True)
        self.fields["service"].queryset = salon.services.filter(active=True, branch_offerings__active=True).distinct()
        self.fields["professional"].queryset = salon.professionals.filter(active=True).distinct()
        self.fields["date"].widget.attrs["min"] = timezone.localdate().isoformat()

    def clean_date(self):
        value = self.cleaned_data["date"]
        if value < timezone.localdate():
            raise forms.ValidationError("Elegí una fecha actual o futura.")
        return value

