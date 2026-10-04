from django import forms
from django.utils import timezone
from .models import BookingLimitException, Branch, HairSalon, Professional, RewardProgram, Service


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


class SalonPolicyForm(forms.ModelForm):
    class Meta:
        model = HairSalon
        fields = ["cancellation_notice_hours"]
        labels = {"cancellation_notice_hours": "Horas mínimas de anticipación para cancelar"}
        help_texts = {"cancellation_notice_hours": "El valor vigente se guardará dentro de cada nueva reserva."}
        widgets = {"cancellation_notice_hours": forms.NumberInput(attrs={"min": 0, "max": 720})}

    def clean_cancellation_notice_hours(self):
        value = self.cleaned_data["cancellation_notice_hours"]
        if value > 720:
            raise forms.ValidationError("La anticipación no puede superar 720 horas (30 días).")
        return value


class BookingLimitExceptionForm(forms.ModelForm):
    class Meta:
        model = BookingLimitException
        fields = ["customer_email", "booking_date", "reason"]
        labels = {
            "customer_email": "Correo verificado del cliente",
            "booking_date": "Fecha de las reservas",
            "reason": "Motivo de la excepción",
        }
        widgets = {
            "booking_date": forms.DateInput(attrs={"type": "date"}),
            "reason": forms.Textarea(attrs={"rows": 3}),
        }

    def clean_booking_date(self):
        value = self.cleaned_data["booking_date"]
        if value < timezone.localdate():
            raise forms.ValidationError("La excepción debe corresponder a una fecha actual o futura.")
        return value


class RewardProgramForm(forms.ModelForm):
    class Meta:
        model = RewardProgram
        fields = ["active", "services_required", "period", "discount_percent"]
        labels = {
            "active": "Activar programa de recompensas",
            "services_required": "Cantidad de servicios atendidos",
            "period": "Período de conteo",
            "discount_percent": "Porcentaje de descuento",
        }
        widgets = {
            "services_required": forms.NumberInput(attrs={"min": 1}),
            "discount_percent": forms.NumberInput(attrs={"min": 1, "max": 100}),
        }
