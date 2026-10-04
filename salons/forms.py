from django import forms
from django.utils import timezone
from .models import (
    BookingLimitException,
    Branch,
    BranchService,
    HairSalon,
    Professional,
    ProfessionalAbsence,
    RewardProgram,
    ScheduleBreak,
    Service,
    WorkSchedule,
)


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


class RescheduleForm(forms.Form):
    date = forms.DateField(label="Nueva fecha", widget=forms.DateInput(attrs={"type": "date"}))
    slot = forms.CharField(widget=forms.HiddenInput())

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
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


class BranchManagementForm(forms.ModelForm):
    class Meta:
        model = Branch
        fields = ["name", "address", "phone", "active"]
        labels = {
            "name": "Nombre",
            "address": "Dirección",
            "phone": "Teléfono",
            "active": "Sucursal activa",
        }

    def __init__(self, *args, salon, **kwargs):
        super().__init__(*args, **kwargs)
        self.salon = salon

    def clean_name(self):
        value = self.cleaned_data["name"].strip()
        duplicate = Branch.objects.filter(salon=self.salon, name__iexact=value).exclude(pk=self.instance.pk)
        if duplicate.exists():
            raise forms.ValidationError("Ya existe una sucursal con ese nombre.")
        return value


class ServiceManagementForm(forms.ModelForm):
    class Meta:
        model = Service
        fields = ["name", "active"]
        labels = {"name": "Nombre", "active": "Servicio activo"}

    def __init__(self, *args, salon, **kwargs):
        super().__init__(*args, **kwargs)
        self.salon = salon

    def clean_name(self):
        value = self.cleaned_data["name"].strip()
        duplicate = Service.objects.filter(salon=self.salon, name__iexact=value).exclude(pk=self.instance.pk)
        if duplicate.exists():
            raise forms.ValidationError("Ya existe un servicio con ese nombre.")
        return value


class BranchServiceManagementForm(forms.ModelForm):
    class Meta:
        model = BranchService
        fields = ["branch", "service", "duration_minutes", "active"]
        labels = {
            "branch": "Sucursal",
            "service": "Servicio",
            "duration_minutes": "Duración en minutos",
            "active": "Disponible en esta sucursal",
        }
        widgets = {"duration_minutes": forms.NumberInput(attrs={"min": 5, "step": 5})}

    def __init__(self, *args, salon, **kwargs):
        super().__init__(*args, **kwargs)
        self.salon = salon
        self.fields["branch"].queryset = salon.branches.all()
        self.fields["service"].queryset = salon.services.all()
        self.fields["duration_minutes"].widget.attrs["min"] = 5

    def clean(self):
        cleaned_data = super().clean()
        branch = cleaned_data.get("branch")
        service = cleaned_data.get("service")
        if branch and service:
            duplicate = BranchService.objects.filter(branch=branch, service=service).exclude(pk=self.instance.pk)
            if duplicate.exists():
                raise forms.ValidationError("Ese servicio ya está configurado en la sucursal.")
        return cleaned_data


class ProfessionalManagementForm(forms.ModelForm):
    branches = forms.ModelMultipleChoiceField(
        label="Sucursales",
        queryset=Branch.objects.none(),
        required=False,
        widget=forms.CheckboxSelectMultiple,
    )
    services = forms.ModelMultipleChoiceField(
        label="Servicios",
        queryset=Service.objects.none(),
        required=False,
        widget=forms.CheckboxSelectMultiple,
    )

    class Meta:
        model = Professional
        fields = ["display_name", "branches", "services", "active"]
        labels = {"display_name": "Nombre visible", "active": "Profesional activo"}

    def __init__(self, *args, salon, **kwargs):
        super().__init__(*args, **kwargs)
        self.salon = salon
        self.fields["branches"].queryset = salon.branches.all()
        self.fields["services"].queryset = salon.services.all()
        if self.instance.pk:
            self.fields["branches"].initial = self.instance.branches.all()
            self.fields["services"].initial = self.instance.services.all()

    def clean_display_name(self):
        value = self.cleaned_data["display_name"].strip()
        duplicate = Professional.objects.filter(salon=self.salon, display_name__iexact=value).exclude(
            pk=self.instance.pk
        )
        if duplicate.exists():
            raise forms.ValidationError("Ya existe un profesional con ese nombre.")
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


class WorkScheduleForm(forms.ModelForm):
    class Meta:
        model = WorkSchedule
        fields = ["professional", "branch", "weekday", "starts_at", "ends_at"]
        widgets = {
            "starts_at": forms.TimeInput(attrs={"type": "time"}),
            "ends_at": forms.TimeInput(attrs={"type": "time"}),
        }

    def __init__(self, *args, salon, branches, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["branch"].queryset = branches
        self.fields["professional"].queryset = Professional.objects.filter(
            salon=salon,
            active=True,
            branches__in=branches,
        ).distinct()


class ScheduleBreakForm(forms.ModelForm):
    class Meta:
        model = ScheduleBreak
        fields = ["schedule", "starts_at", "ends_at"]
        widgets = {
            "starts_at": forms.TimeInput(attrs={"type": "time"}),
            "ends_at": forms.TimeInput(attrs={"type": "time"}),
        }

    def __init__(self, *args, salon, branches, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["schedule"].queryset = WorkSchedule.objects.filter(
            professional__salon=salon,
            branch__in=branches,
        ).select_related("professional", "branch")


class ProfessionalAbsenceForm(forms.ModelForm):
    class Meta:
        model = ProfessionalAbsence
        fields = ["professional", "branch", "starts_at", "ends_at", "reason"]
        widgets = {
            "starts_at": forms.DateTimeInput(attrs={"type": "datetime-local"}, format="%Y-%m-%dT%H:%M"),
            "ends_at": forms.DateTimeInput(attrs={"type": "datetime-local"}, format="%Y-%m-%dT%H:%M"),
        }

    def __init__(self, *args, salon, branches, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["branch"].queryset = branches
        self.fields["professional"].queryset = Professional.objects.filter(
            salon=salon,
            active=True,
            branches__in=branches,
        ).distinct()
