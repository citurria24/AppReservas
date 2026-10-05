from django.conf import settings
from django.contrib.postgres.constraints import ExclusionConstraint
from django.contrib.postgres.fields import DateTimeRangeField, RangeOperators
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Q
from django.utils import timezone
from psycopg.types.range import Range
import uuid
from datetime import timedelta


class HairSalon(models.Model):
    name = models.CharField("nombre", max_length=160)
    slug = models.SlugField(unique=True)
    active = models.BooleanField("activa", default=True)
    cancellation_notice_hours = models.PositiveSmallIntegerField("anticipación mínima para cancelar", default=24)

    class Meta:
        ordering = ["name"]
        verbose_name = "peluquería"
        verbose_name_plural = "peluquerías"

    def __str__(self):
        return self.name


class Branch(models.Model):
    salon = models.ForeignKey(HairSalon, on_delete=models.CASCADE, related_name="branches", verbose_name="peluquería")
    name = models.CharField("nombre", max_length=120)
    address = models.CharField("dirección", max_length=250)
    phone = models.CharField("teléfono", max_length=40, blank=True)
    active = models.BooleanField("activa", default=True)

    class Meta:
        ordering = ["name"]
        constraints = [models.UniqueConstraint(fields=["salon", "name"], name="unique_branch_name_per_salon")]
        verbose_name = "sucursal"
        verbose_name_plural = "sucursales"

    def __str__(self):
        return f"{self.salon} · {self.name}"


class Membership(models.Model):
    class Role(models.TextChoices):
        OWNER = "owner", "Owner"
        ADMIN = "admin", "Administrador"
        HAIRDRESSER = "hairdresser", "Peluquero"

    salon = models.ForeignKey(HairSalon, on_delete=models.CASCADE, related_name="memberships", verbose_name="peluquería")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="salon_memberships", verbose_name="usuario")
    role = models.CharField("rol", max_length=20, choices=Role.choices)
    branches = models.ManyToManyField(Branch, through="MembershipBranch", related_name="authorized_memberships", blank=True)
    active = models.BooleanField("activa", default=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["salon", "user"], name="unique_membership_per_salon_user"),
            models.UniqueConstraint(fields=["salon"], condition=Q(role="owner"), name="one_owner_per_salon"),
        ]
        verbose_name = "membresía"
        verbose_name_plural = "membresías"

    def __str__(self):
        return f"{self.user} · {self.salon} ({self.get_role_display()})"

    def authorized_branches(self):
        if self.role == self.Role.OWNER:
            return self.salon.branches.filter(active=True)
        return self.branches.filter(active=True)


class MembershipBranch(models.Model):
    membership = models.ForeignKey(Membership, on_delete=models.CASCADE)
    branch = models.ForeignKey(Branch, on_delete=models.CASCADE)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["membership", "branch"], name="unique_membership_branch")]
        verbose_name = "acceso a sucursal"
        verbose_name_plural = "accesos a sucursales"

    def clean(self):
        if self.membership_id and self.branch_id and self.membership.salon_id != self.branch.salon_id:
            raise ValidationError("La membresía y la sucursal deben pertenecer a la misma peluquería.")

    def save(self, *args, **kwargs):
        self.full_clean()
        return super().save(*args, **kwargs)


class Professional(models.Model):
    salon = models.ForeignKey(HairSalon, on_delete=models.CASCADE, related_name="professionals", verbose_name="peluquería")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, related_name="professional_profiles", null=True, blank=True, verbose_name="usuario")
    display_name = models.CharField("nombre visible", max_length=160)
    branches = models.ManyToManyField(Branch, through="ProfessionalBranch", related_name="professionals", blank=True)
    active = models.BooleanField("activo", default=True)

    class Meta:
        ordering = ["display_name"]
        constraints = [
            models.UniqueConstraint(fields=["salon", "display_name"], name="unique_professional_name_per_salon"),
            models.UniqueConstraint(fields=["salon", "user"], condition=Q(user__isnull=False), name="unique_professional_user_per_salon"),
        ]
        verbose_name = "profesional"
        verbose_name_plural = "profesionales"

    def __str__(self):
        return f"{self.display_name} · {self.salon}"


class Service(models.Model):
    salon = models.ForeignKey(HairSalon, on_delete=models.CASCADE, related_name="services", verbose_name="peluquería")
    name = models.CharField("nombre", max_length=140)
    professionals = models.ManyToManyField(Professional, through="ProfessionalService", related_name="services", blank=True)
    active = models.BooleanField("activo", default=True)

    class Meta:
        ordering = ["name"]
        constraints = [models.UniqueConstraint(fields=["salon", "name"], name="unique_service_name_per_salon")]
        verbose_name = "servicio"
        verbose_name_plural = "servicios"

    def __str__(self):
        return f"{self.name} · {self.salon}"


class ProfessionalBranch(models.Model):
    professional = models.ForeignKey(Professional, on_delete=models.CASCADE)
    branch = models.ForeignKey(Branch, on_delete=models.CASCADE)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["professional", "branch"], name="unique_professional_branch")]
        verbose_name = "asignación de profesional a sucursal"
        verbose_name_plural = "asignaciones de profesionales a sucursales"

    def clean(self):
        if self.professional_id and self.branch_id and self.professional.salon_id != self.branch.salon_id:
            raise ValidationError("El profesional y la sucursal deben pertenecer a la misma peluquería.")

    def save(self, *args, **kwargs):
        self.full_clean()
        return super().save(*args, **kwargs)


class ProfessionalService(models.Model):
    professional = models.ForeignKey(Professional, on_delete=models.CASCADE)
    service = models.ForeignKey(Service, on_delete=models.CASCADE)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["professional", "service"], name="unique_professional_service")]
        verbose_name = "servicio de profesional"
        verbose_name_plural = "servicios de profesionales"

    def clean(self):
        if self.professional_id and self.service_id and self.professional.salon_id != self.service.salon_id:
            raise ValidationError("El profesional y el servicio deben pertenecer a la misma peluquería.")

    def save(self, *args, **kwargs):
        self.full_clean()
        return super().save(*args, **kwargs)


class BranchService(models.Model):
    branch = models.ForeignKey(Branch, on_delete=models.CASCADE, related_name="service_offerings", verbose_name="sucursal")
    service = models.ForeignKey(Service, on_delete=models.CASCADE, related_name="branch_offerings", verbose_name="servicio")
    duration_minutes = models.PositiveSmallIntegerField("duración (minutos)")
    active = models.BooleanField("activo", default=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["branch", "service"], name="unique_service_per_branch"),
            models.CheckConstraint(condition=Q(duration_minutes__gte=5), name="service_duration_at_least_5_minutes"),
        ]
        verbose_name = "servicio por sucursal"
        verbose_name_plural = "servicios por sucursal"

    def clean(self):
        if self.branch_id and self.service_id and self.branch.salon_id != self.service.salon_id:
            raise ValidationError("La sucursal y el servicio deben pertenecer a la misma peluquería.")

    def save(self, *args, **kwargs):
        self.full_clean()
        return super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.service.name} en {self.branch.name}: {self.duration_minutes} min"


class WorkSchedule(models.Model):
    class Weekday(models.IntegerChoices):
        MONDAY = 0, "Lunes"
        TUESDAY = 1, "Martes"
        WEDNESDAY = 2, "Miércoles"
        THURSDAY = 3, "Jueves"
        FRIDAY = 4, "Viernes"
        SATURDAY = 5, "Sábado"
        SUNDAY = 6, "Domingo"

    professional = models.ForeignKey(Professional, on_delete=models.CASCADE, related_name="work_schedules", verbose_name="profesional")
    branch = models.ForeignKey(Branch, on_delete=models.CASCADE, related_name="work_schedules", verbose_name="sucursal")
    weekday = models.PositiveSmallIntegerField("día", choices=Weekday.choices)
    starts_at = models.TimeField("inicio")
    ends_at = models.TimeField("fin")

    class Meta:
        ordering = ["weekday", "starts_at"]
        constraints = [
            models.UniqueConstraint(fields=["professional", "branch", "weekday", "starts_at"], name="unique_work_schedule_start"),
            models.CheckConstraint(condition=Q(ends_at__gt=models.F("starts_at")), name="work_schedule_end_after_start"),
        ]
        verbose_name = "jornada profesional"
        verbose_name_plural = "jornadas profesionales"

    def clean(self):
        if self.professional_id and self.branch_id:
            if self.professional.salon_id != self.branch.salon_id:
                raise ValidationError("El profesional y la sucursal deben pertenecer a la misma peluquería.")
            if not ProfessionalBranch.objects.filter(professional=self.professional, branch=self.branch).exists():
                raise ValidationError("El profesional debe estar asignado a la sucursal.")

    def save(self, *args, **kwargs):
        self.full_clean()
        return super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.professional.display_name} · {self.get_weekday_display()} {self.starts_at:%H:%M}-{self.ends_at:%H:%M}"


class ScheduleBreak(models.Model):
    schedule = models.ForeignKey(WorkSchedule, on_delete=models.CASCADE, related_name="breaks", verbose_name="jornada")
    starts_at = models.TimeField("inicio")
    ends_at = models.TimeField("fin")

    class Meta:
        ordering = ["starts_at"]
        constraints = [models.CheckConstraint(condition=Q(ends_at__gt=models.F("starts_at")), name="schedule_break_end_after_start")]
        verbose_name = "descanso"
        verbose_name_plural = "descansos"

    def clean(self):
        if self.schedule_id and (self.starts_at < self.schedule.starts_at or self.ends_at > self.schedule.ends_at):
            raise ValidationError("El descanso debe estar dentro de la jornada.")

    def save(self, *args, **kwargs):
        self.full_clean()
        return super().save(*args, **kwargs)


class ProfessionalAbsence(models.Model):
    professional = models.ForeignKey(Professional, on_delete=models.CASCADE, related_name="absences", verbose_name="profesional")
    branch = models.ForeignKey(Branch, on_delete=models.CASCADE, related_name="professional_absences", verbose_name="sucursal")
    starts_at = models.DateTimeField("inicio")
    ends_at = models.DateTimeField("fin")
    reason = models.CharField("motivo", max_length=180, blank=True)

    class Meta:
        ordering = ["starts_at"]
        constraints = [models.CheckConstraint(condition=Q(ends_at__gt=models.F("starts_at")), name="absence_end_after_start")]
        verbose_name = "ausencia profesional"
        verbose_name_plural = "ausencias profesionales"

    def clean(self):
        if self.professional_id and self.branch_id and self.professional.salon_id != self.branch.salon_id:
            raise ValidationError("El profesional y la sucursal deben pertenecer a la misma peluquería.")

    def save(self, *args, **kwargs):
        self.full_clean()
        return super().save(*args, **kwargs)


class GuestVerification(models.Model):
    email = models.EmailField("correo electrónico", db_index=True)
    code_hash = models.CharField(max_length=128)
    expires_at = models.DateTimeField("vence")
    verified_at = models.DateTimeField("verificado", null=True, blank=True)
    attempts = models.PositiveSmallIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "verificación de invitado"
        verbose_name_plural = "verificaciones de invitados"

    @property
    def is_valid(self):
        return self.verified_at is None and self.expires_at > timezone.now() and self.attempts < 5


class Reservation(models.Model):
    class Status(models.TextChoices):
        CONFIRMED = "confirmed", "Confirmada"
        CANCELLED_CLIENT = "cancelled_client", "Cancelada por cliente"
        CANCELLED_SALON = "cancelled_salon", "Cancelada por local"
        COMPLETED = "completed", "Atendida"
        NO_SHOW = "no_show", "Ausente"

    salon = models.ForeignKey(HairSalon, on_delete=models.PROTECT, related_name="reservations", verbose_name="peluquería")
    branch = models.ForeignKey(Branch, on_delete=models.PROTECT, related_name="reservations", verbose_name="sucursal")
    service = models.ForeignKey(Service, on_delete=models.PROTECT, related_name="reservations", verbose_name="servicio")
    professional = models.ForeignKey(Professional, on_delete=models.PROTECT, related_name="reservations", verbose_name="profesional")
    first_name = models.CharField("nombre", max_length=100)
    last_name = models.CharField("apellido", max_length=100)
    email = models.EmailField("correo electrónico")
    contact = models.CharField("contacto", max_length=100)
    starts_at = models.DateTimeField("inicio")
    ends_at = models.DateTimeField("fin")
    occupied_range = DateTimeRangeField("intervalo ocupado")
    duration_minutes = models.PositiveSmallIntegerField("duración guardada")
    cancellation_notice_hours = models.PositiveSmallIntegerField("anticipación para cancelar", default=24)
    cancellation_token = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    reward_discount_percent = models.PositiveSmallIntegerField("descuento de recompensa", default=0)
    status = models.CharField("estado", max_length=24, choices=Status.choices, default=Status.CONFIRMED)
    cancelled_at = models.DateTimeField("cancelada", null=True, blank=True)
    notes = models.TextField("notas", blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["starts_at"]
        indexes = [
            models.Index(
                fields=["salon", "status", "cancelled_at"],
                name="reservation_cancel_policy_idx",
            ),
        ]
        constraints = [
            models.CheckConstraint(condition=Q(ends_at__gt=models.F("starts_at")), name="reservation_end_after_start"),
            ExclusionConstraint(
                name="prevent_professional_reservation_overlap",
                expressions=[("professional", RangeOperators.EQUAL), ("occupied_range", RangeOperators.OVERLAPS)],
                condition=Q(status="confirmed"),
            ),
        ]
        verbose_name = "reserva"
        verbose_name_plural = "reservas"

    def clean(self):
        errors = {}
        if self.branch_id and self.salon_id and self.branch.salon_id != self.salon_id:
            errors["branch"] = "La sucursal no pertenece a la peluquería."
        if self.service_id and self.salon_id and self.service.salon_id != self.salon_id:
            errors["service"] = "El servicio no pertenece a la peluquería."
        if self.professional_id and self.salon_id and self.professional.salon_id != self.salon_id:
            errors["professional"] = "El profesional no pertenece a la peluquería."
        if errors:
            raise ValidationError(errors)

    def save(self, *args, **kwargs):
        self.occupied_range = Range(self.starts_at, self.ends_at, bounds="[)")
        self.full_clean(exclude=["occupied_range"])
        return super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.first_name} {self.last_name} · {self.starts_at:%d/%m/%Y %H:%M}"

    @property
    def client_cancellation_deadline(self):
        return self.starts_at - timedelta(hours=self.cancellation_notice_hours)

    @property
    def can_client_cancel(self):
        return self.status == self.Status.CONFIRMED and timezone.now() <= self.client_cancellation_deadline

    @property
    def can_client_reschedule(self):
        return self.can_client_cancel


class ReservationStatusChange(models.Model):
    reservation = models.ForeignKey(Reservation, on_delete=models.PROTECT, related_name="status_changes")
    previous_status = models.CharField(max_length=24, choices=Reservation.Status.choices)
    new_status = models.CharField(max_length=24, choices=Reservation.Status.choices)
    changed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True,
        related_name="reservation_status_changes",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at", "pk"]


class ReservationReschedule(models.Model):
    class Source(models.TextChoices):
        CLIENT = "client", "Cliente"
        SALON = "salon", "Peluquería"

    reservation = models.ForeignKey(
        Reservation,
        on_delete=models.CASCADE,
        related_name="reschedules",
        verbose_name="reserva",
    )
    previous_starts_at = models.DateTimeField("inicio anterior")
    previous_ends_at = models.DateTimeField("fin anterior")
    new_starts_at = models.DateTimeField("inicio nuevo")
    new_ends_at = models.DateTimeField("fin nuevo")
    source = models.CharField("origen", max_length=12, choices=Source.choices)
    changed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="reservation_reschedules",
        null=True,
        blank=True,
        verbose_name="modificada por",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.CheckConstraint(
                condition=Q(previous_ends_at__gt=models.F("previous_starts_at")),
                name="reschedule_previous_end_after_start",
            ),
            models.CheckConstraint(
                condition=Q(new_ends_at__gt=models.F("new_starts_at")),
                name="reschedule_new_end_after_start",
            ),
        ]
        verbose_name = "reprogramación"
        verbose_name_plural = "reprogramaciones"

    def clean(self):
        if self.source == self.Source.CLIENT and self.changed_by_id:
            raise ValidationError("Una reprogramación del cliente no puede tener un usuario interno.")
        if self.source == self.Source.SALON and not self.changed_by_id:
            raise ValidationError("Una reprogramación de la peluquería debe registrar el usuario responsable.")

    def save(self, *args, **kwargs):
        self.full_clean()
        return super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.reservation} · {self.previous_starts_at:%d/%m/%Y %H:%M} → {self.new_starts_at:%d/%m/%Y %H:%M}"


class BookingLimitException(models.Model):
    salon = models.ForeignKey(HairSalon, on_delete=models.CASCADE, related_name="booking_limit_exceptions", verbose_name="peluquería")
    customer_email = models.EmailField("correo del cliente")
    booking_date = models.DateField("fecha de las reservas")
    reason = models.CharField("motivo", max_length=300)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="granted_booking_exceptions", verbose_name="autorizada por")
    reservation = models.OneToOneField(Reservation, on_delete=models.SET_NULL, related_name="limit_exception", null=True, blank=True, verbose_name="reserva que utilizó la excepción")
    used_at = models.DateTimeField("utilizada", null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["salon", "customer_email", "booking_date", "used_at"], name="booking_exception_lookup")]
        verbose_name = "excepción al límite de reservas"
        verbose_name_plural = "excepciones al límite de reservas"

    def clean(self):
        if self.salon_id and self.created_by_id:
            is_authorized = Membership.objects.filter(
                salon=self.salon,
                user=self.created_by,
                active=True,
                role__in=[Membership.Role.OWNER, Membership.Role.ADMIN],
            ).exists()
            if not is_authorized:
                raise ValidationError("La excepción debe ser autorizada por un owner o administrador activo.")

    def save(self, *args, **kwargs):
        self.customer_email = self.customer_email.lower()
        self.full_clean()
        return super().save(*args, **kwargs)


class RewardProgram(models.Model):
    class Period(models.TextChoices):
        MONTHLY = "monthly", "Mensual"
        YEARLY = "yearly", "Anual"

    salon = models.OneToOneField(HairSalon, on_delete=models.CASCADE, related_name="reward_program", verbose_name="peluquería")
    active = models.BooleanField("activo", default=False)
    services_required = models.PositiveSmallIntegerField("servicios atendidos requeridos", default=5)
    period = models.CharField("período", max_length=12, choices=Period.choices, default=Period.MONTHLY)
    discount_percent = models.PositiveSmallIntegerField("porcentaje de descuento", default=10)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.CheckConstraint(condition=Q(services_required__gte=1), name="reward_services_at_least_one"),
            models.CheckConstraint(condition=Q(discount_percent__gte=1, discount_percent__lte=100), name="reward_discount_valid_percent"),
        ]
        verbose_name = "programa de recompensas"
        verbose_name_plural = "programas de recompensas"

    def __str__(self):
        return f"{self.salon} · {self.services_required} servicios / {self.get_period_display()}"


class RewardRedemption(models.Model):
    salon = models.ForeignKey(HairSalon, on_delete=models.CASCADE, related_name="reward_redemptions", verbose_name="peluquería")
    customer_email = models.EmailField("correo del cliente")
    period_start = models.DateField("inicio del período")
    period_end = models.DateField("fin del período")
    attended_services = models.PositiveSmallIntegerField("servicios atendidos")
    discount_percent = models.PositiveSmallIntegerField("porcentaje canjeado")
    reservation = models.OneToOneField(Reservation, on_delete=models.PROTECT, related_name="reward_redemption", verbose_name="reserva del canje")
    redeemed_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["salon", "customer_email", "period_start"], name="one_reward_redemption_per_period"),
        ]
        ordering = ["-redeemed_at"]
        verbose_name = "canje de recompensa"
        verbose_name_plural = "canjes de recompensas"

    def save(self, *args, **kwargs):
        self.customer_email = self.customer_email.lower()
        return super().save(*args, **kwargs)
