from datetime import timedelta

from django.db import transaction
from django.utils import timezone
from django.utils.translation import ngettext

from .booking import available_slots
from .email_delivery import send_reservation_rescheduled_email
from .models import HairSalon, Reservation, ReservationReschedule
from .reservation_service import CustomerIdentity, DailyLimitReached, claim_daily_limit, consume_limit_exception


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
        duration_minutes=reservation.duration_minutes,
    )


def reschedule_reservation(*, reservation, day, slot_value, source, changed_by, request):
    with transaction.atomic():
        # Mismo orden de bloqueo que la creación (peluquería primero) para evitar deadlocks.
        salon = HairSalon.objects.select_for_update().get(pk=reservation.salon_id)
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
        # Moverla dentro del mismo día no suma reservas: el límite solo se aplica
        # al cambiar de día, y una excepción usada en el día de origen no se traslada.
        limit_exception = None
        if day != timezone.localtime(locked.starts_at).date():
            try:
                limit_exception = claim_daily_limit(
                    salon=salon,
                    customer=CustomerIdentity.of_reservation(locked),
                    day=day,
                    exclude_reservation=locked,
                )
            except DailyLimitReached as error:
                raise RescheduleError(ngettext(
                    "El cliente ya tiene %(limit)d reserva activa para esa fecha en esta peluquería, que es el máximo permitido.",
                    "El cliente ya tiene %(limit)d reservas activas para esa fecha en esta peluquería, que es el máximo permitido.",
                    error.limit,
                ) % {"limit": error.limit})

        previous_starts_at = locked.starts_at
        previous_ends_at = locked.ends_at
        locked.starts_at = selected
        locked.ends_at = selected + timedelta(minutes=locked.duration_minutes)
        locked.save()
        consume_limit_exception(limit_exception, locked)
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
