from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from .booking import available_slots
from .email_delivery import send_reservation_rescheduled_email
from .models import Reservation, ReservationReschedule


class RescheduleError(Exception):
    def __init__(self, message, *, field=None):
        super().__init__(message)
        self.field = field


def slots_for_reservation(reservation, day):
    return available_slots(
        salon=reservation.salon,
        branch=reservation.branch,
        service=reservation.service,
        professional=reservation.professional,
        day=day,
        exclude_reservation_id=reservation.id,
    )


def _active_reservations_for_target_day(reservation, day):
    local_tz = ZoneInfo(settings.TIME_ZONE)
    day_start = timezone.make_aware(datetime.combine(day, time.min), local_tz)
    day_end = day_start + timedelta(days=1)
    return Reservation.objects.filter(
        salon=reservation.salon,
        email__iexact=reservation.email,
        status=Reservation.Status.CONFIRMED,
        starts_at__gte=day_start,
        starts_at__lt=day_end,
    ).exclude(pk=reservation.pk)


def reschedule_reservation(*, reservation, day, slot_value, source, changed_by, request):
    with transaction.atomic():
        locked = Reservation.objects.select_for_update().select_related(
            "salon", "branch", "service", "professional"
        ).get(pk=reservation.pk)
        if locked.status != Reservation.Status.CONFIRMED:
            raise RescheduleError("La reserva ya no admite reprogramación.")
        if source == ReservationReschedule.Source.CLIENT and not locked.can_client_reschedule:
            raise RescheduleError("La reserva está fuera del plazo para reprogramar.")

        selected = next(
            (slot for slot in slots_for_reservation(locked, day) if slot.isoformat() == slot_value),
            None,
        )
        if not selected:
            raise RescheduleError("Ese horario ya no está disponible. Elegí otro.", field="slot")
        if selected == locked.starts_at:
            raise RescheduleError("Elegí un horario diferente al actual.", field="slot")
        if _active_reservations_for_target_day(locked, day).count() >= 5:
            raise RescheduleError(
                "El cliente ya tiene cinco reservas activas para esa fecha en esta peluquería."
            )

        previous_starts_at = locked.starts_at
        previous_ends_at = locked.ends_at
        locked.starts_at = selected
        locked.ends_at = selected + timedelta(minutes=locked.duration_minutes)
        locked.save()
        ReservationReschedule.objects.create(
            reservation=locked,
            previous_starts_at=previous_starts_at,
            previous_ends_at=previous_ends_at,
            new_starts_at=locked.starts_at,
            new_ends_at=locked.ends_at,
            source=source,
            changed_by=changed_by,
        )
        send_reservation_rescheduled_email(
            request=request,
            reservation=locked,
            previous_starts_at=previous_starts_at,
        )
    return locked
