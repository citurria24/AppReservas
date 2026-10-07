from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.http import Http404
from django.shortcuts import get_object_or_404
from django.utils import timezone

from .access import accessible_reservations_for, can_complete_reservation, can_manage_reservation
from .models import Reservation, ReservationStatusChange


S = Reservation.Status
TRANSITIONS = {
    S.CONFIRMED: {"complete": S.COMPLETED, "no_show": S.NO_SHOW, "cancel": S.CANCELLED_SALON},
}
# Atendida y Ausente solo tienen sentido desde el inicio del turno.
REQUIRES_STARTED = {"complete", "no_show"}


def has_started(reservation):
    return timezone.now() >= reservation.starts_at


def reservation_actions(user, reservation):
    confirmed = reservation.status == S.CONFIRMED
    can_operate = can_complete_reservation(user, reservation) and has_started(reservation)
    can_manage = can_manage_reservation(user, reservation)
    return {
        "can_complete": confirmed and can_operate,
        "can_no_show": confirmed and can_operate,
        "can_cancel": confirmed and can_manage,
        "can_reschedule": confirmed and can_manage,
    }


@transaction.atomic
def change_reservation_status(*, user, pk, action):
    # Lock the base table only: the access query contains DISTINCT and joins.
    accessible = get_object_or_404(accessible_reservations_for(user), pk=pk)
    reservation = Reservation.objects.select_for_update().get(pk=accessible.pk)
    if action not in ("complete", "no_show", "cancel"):
        raise Http404
    permitted = can_manage_reservation if action == "cancel" else can_complete_reservation
    if not permitted(user, reservation):
        raise PermissionDenied
    target = TRANSITIONS.get(reservation.status, {}).get(action)
    if target is None:
        raise PermissionDenied("La reserva ya no admite ese cambio.")
    if action in REQUIRES_STARTED and not has_started(reservation):
        raise PermissionDenied("La reserva todavía no comenzó.")
    previous = reservation.status
    reservation.status = target
    fields = ["status"]
    if action == "cancel":
        reservation.cancelled_at = timezone.now()
        fields.append("cancelled_at")
    reservation.save(update_fields=fields)
    ReservationStatusChange.objects.create(
        reservation=reservation, previous_status=previous, new_status=target, changed_by=user,
    )
    return reservation
