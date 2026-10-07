from dataclasses import dataclass
from datetime import datetime, timedelta

from django.utils import timezone

from .models import Reservation


@dataclass(frozen=True)
class CancellationBookingBlock:
    unlocks_at: datetime
    triggering_reservation: Reservation

    @property
    def branch(self):
        return self.triggering_reservation.branch


def active_cancellation_booking_block(*, salon, customer_email, now=None):
    """Return the active block caused by a client cancellation, if any.

    Threshold, rolling window and block duration come from the salon. Looking
    back from each possible triggering cancellation preserves the full block
    even when an older cancellation leaves the rolling window after the limit
    was reached.
    """
    now = now or timezone.now()
    block_duration = timedelta(hours=salon.cancellation_block_hours)
    window = timedelta(days=salon.cancellation_block_window_days)
    client_cancellations = Reservation.objects.filter(
        salon=salon,
        email__iexact=customer_email,
        status=Reservation.Status.CANCELLED_CLIENT,
        cancelled_at__isnull=False,
    )
    possible_triggers = client_cancellations.filter(
        cancelled_at__gt=now - block_duration,
        cancelled_at__lte=now,
    ).select_related("branch").order_by("-cancelled_at", "-pk")

    for cancellation in possible_triggers:
        cancellations_in_window = client_cancellations.filter(
            cancelled_at__gte=cancellation.cancelled_at - window,
            cancelled_at__lte=cancellation.cancelled_at,
        ).count()
        if cancellations_in_window >= salon.cancellation_block_threshold:
            return CancellationBookingBlock(
                unlocks_at=cancellation.cancelled_at + block_duration,
                triggering_reservation=cancellation,
            )
    return None
