"""Reglas centrales para crear reservas, independientes de HTTP.

Views y API se encargan de autenticar, validar formularios y presentar
errores; este módulo decide si una reserva puede existir y la persiste.
"""
from dataclasses import dataclass
from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

from django.conf import settings
from django.db import IntegrityError, transaction
from django.utils import timezone

from .booking import available_slots
from .cancellation_policy import active_cancellation_booking_block
from .models import BookingLimitException, BranchService, HairSalon, Reservation, RewardRedemption
from .rewards import available_reward


@dataclass(frozen=True)
class CustomerIdentity:
    """Cliente de una reserva.

    Hoy se identifica por email (case-insensitive). Las consultas por cliente
    pasan por estos métodos para poder sumar otra identidad sin tocar las reglas.
    """

    email: str
    first_name: str = ""
    last_name: str = ""
    contact: str = ""

    @classmethod
    def of_reservation(cls, reservation):
        return cls(
            email=reservation.email,
            first_name=reservation.first_name,
            last_name=reservation.last_name,
            contact=reservation.contact,
        )

    def reservations(self, salon):
        return Reservation.objects.filter(salon=salon, email__iexact=self.email)

    def limit_exceptions(self, salon):
        return BookingLimitException.objects.filter(salon=salon, customer_email__iexact=self.email)


class BookingError(Exception):
    field = None


class SlotUnavailable(BookingError):
    field = "slot"


class DailyLimitReached(BookingError):
    def __init__(self, limit):
        super().__init__(f"Se alcanzó el máximo de {limit} reservas activas por día.")
        self.limit = limit


class CancellationBlockActive(BookingError):
    def __init__(self, block):
        super().__init__("El cliente tiene un bloqueo temporal por cancelaciones.")
        self.block = block


def _local_day_bounds(day):
    start = timezone.make_aware(datetime.combine(day, time.min), ZoneInfo(settings.TIME_ZONE))
    return start, start + timedelta(days=1)


def active_reservations_on(*, salon, customer, day):
    start, end = _local_day_bounds(day)
    return customer.reservations(salon).filter(
        status=Reservation.Status.CONFIRMED,
        starts_at__gte=start,
        starts_at__lt=end,
    )


def claim_daily_limit(*, salon, customer, day, exclude_reservation=None):
    """Aplica max_daily_bookings_per_client para sumar una reserva en `day`.

    Debe ejecutarse dentro de una transacción con la peluquería bloqueada.
    Devuelve None si hay cupo, o la BookingLimitException a consumir si el
    día ya está completo. Sin excepción disponible, lanza DailyLimitReached.
    """
    active = active_reservations_on(salon=salon, customer=customer, day=day)
    if exclude_reservation is not None:
        active = active.exclude(pk=exclude_reservation.pk)
    if active.count() < salon.max_daily_bookings_per_client:
        return None
    exception = customer.limit_exceptions(salon).select_for_update().filter(
        booking_date=day,
        used_at__isnull=True,
    ).order_by("created_at", "pk").first()
    if exception is None:
        raise DailyLimitReached(salon.max_daily_bookings_per_client)
    return exception


def consume_limit_exception(exception, reservation):
    if exception is None:
        return
    exception.reservation = reservation
    exception.used_at = timezone.now()
    exception.save(update_fields=["reservation", "used_at"])


def create_reservation(*, salon, branch, service, professional, starts_at, customer, notes="", notify=None):
    """Crea una reserva confirmada aplicando todas las reglas de reserva.

    `notify(reservation)` se ejecuta al final, dentro de la misma transacción:
    si falla, la reserva y sus efectos (excepción, canje) se revierten.
    """
    day = timezone.localtime(starts_at).date()
    slots = available_slots(salon=salon, branch=branch, service=service, professional=professional, day=day)
    if starts_at not in slots:
        raise SlotUnavailable("Ese horario ya no está disponible. Elegí otro.")
    try:
        with transaction.atomic():
            # Serializa por peluquería el conteo del límite diario y el bloqueo.
            salon = HairSalon.objects.select_for_update().get(pk=salon.pk)
            block = active_cancellation_booking_block(salon=salon, customer_email=customer.email)
            if block:
                raise CancellationBlockActive(block)
            limit_exception = claim_daily_limit(salon=salon, customer=customer, day=day)
            offering = BranchService.objects.get(branch=branch, service=service, active=True)
            reward = available_reward(salon, customer.email)
            reservation = Reservation.objects.create(
                salon=salon,
                branch=branch,
                service=service,
                professional=professional,
                first_name=customer.first_name,
                last_name=customer.last_name,
                email=customer.email,
                contact=customer.contact,
                starts_at=starts_at,
                ends_at=starts_at + timedelta(minutes=offering.duration_minutes),
                duration_minutes=offering.duration_minutes,
                cancellation_notice_hours=salon.cancellation_notice_hours,
                reward_discount_percent=reward["program"].discount_percent if reward else 0,
                notes=notes,
            )
            consume_limit_exception(limit_exception, reservation)
            if reward:
                RewardRedemption.objects.create(
                    salon=salon,
                    customer_email=customer.email,
                    period_start=reward["period_start"],
                    period_end=reward["period_end"],
                    attended_services=reward["attended"],
                    discount_percent=reward["program"].discount_percent,
                    reservation=reservation,
                )
            if notify:
                notify(reservation)
    except IntegrityError as error:
        # ExclusionConstraint de PostgreSQL: otra transacción tomó el horario.
        raise SlotUnavailable("El horario acaba de ocuparse. Elegí otro.") from error
    return reservation
