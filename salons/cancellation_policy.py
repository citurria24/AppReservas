from dataclasses import dataclass
from datetime import datetime, timedelta

from django.utils import timezone

from .models import Reservation


CANCELLATION_WINDOW = timedelta(days=30)
BOOKING_BLOCK_DURATION = timedelta(hours=24)
CANCELLATIONS_TO_BLOCK = 3


@dataclass(frozen=True)
class CancellationBookingBlock:
    unlocks_at: datetime
    triggering_reservation: Reservation

    @property
    def branch(self):
        return self.triggering_reservation.branch


def active_cancellation_booking_block(*, salon, customer_email, now=None):
    """Return the active block caused by a client cancellation, if any.

    Looking back from each possible triggering cancellation preserves the full
    24-hour block even when an older cancellation leaves the rolling 30-day
    window after the limit was reached.
    """
    now = now or timezone.now()
    client_cancellations = Reservation.objects.filter(
        salon=salon,
        email__iexact=customer_email,
        status=Reservation.Status.CANCELLED_CLIENT,
        cancelled_at__isnull=False,
    )
    possible_triggers = client_cancellations.filter(
        cancelled_at__gt=now - BOOKING_BLOCK_DURATION,
        cancelled_at__lte=now,
    ).select_related("branch").order_by("-cancelled_at", "-pk")

    for cancellation in possible_triggers:
        cancellations_in_window = client_cancellations.filter(
            cancelled_at__gte=cancellation.cancelled_at - CANCELLATION_WINDOW,
            cancelled_at__lte=cancellation.cancelled_at,
        ).count()
        if cancellations_in_window >= CANCELLATIONS_TO_BLOCK:
            return CancellationBookingBlock(
                unlocks_at=cancellation.cancelled_at + BOOKING_BLOCK_DURATION,
                triggering_reservation=cancellation,
            )
    return None
