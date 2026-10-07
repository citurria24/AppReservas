from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from django.conf import settings
from django.utils import timezone
from .models import BranchService, ProfessionalAbsence, Reservation, WorkSchedule


def booking_horizon_end(salon):
    """Último día (local) en que la peluquería acepta reservas."""
    return timezone.localdate() + timedelta(days=salon.max_booking_horizon_days)


def available_slots(*, salon, branch, service, professional, day, exclude_reservation_id=None):
    if branch.salon_id != salon.id or service.salon_id != salon.id or professional.salon_id != salon.id:
        return []
    if not professional.branches.filter(id=branch.id, active=True).exists():
        return []
    if not professional.services.filter(id=service.id, active=True).exists():
        return []

    offering = BranchService.objects.filter(branch=branch, service=service, active=True).first()
    if not offering:
        return []
    if day > booking_horizon_end(salon):
        return []

    tz = ZoneInfo(settings.TIME_ZONE)
    duration = timedelta(minutes=offering.duration_minutes)
    step = timedelta(minutes=salon.slot_interval_minutes)
    earliest_start = timezone.now() + timedelta(minutes=salon.min_booking_notice_minutes)
    slots = []
    schedules = WorkSchedule.objects.filter(
        professional=professional,
        branch=branch,
        weekday=day.weekday(),
    ).prefetch_related("breaks")

    for schedule in schedules:
        window_start = timezone.make_aware(datetime.combine(day, schedule.starts_at), tz)
        window_end = timezone.make_aware(datetime.combine(day, schedule.ends_at), tz)
        candidate = window_start
        while candidate + duration <= window_end:
            candidate_end = candidate + duration
            crosses_break = any(
                candidate < timezone.make_aware(datetime.combine(day, pause.ends_at), tz)
                and candidate_end > timezone.make_aware(datetime.combine(day, pause.starts_at), tz)
                for pause in schedule.breaks.all()
            )
            has_absence = ProfessionalAbsence.objects.filter(
                professional=professional,
                branch=branch,
                starts_at__lt=candidate_end,
                ends_at__gt=candidate,
            ).exists()
            reservations = Reservation.objects.filter(
                professional=professional,
                status=Reservation.Status.CONFIRMED,
                starts_at__lt=candidate_end,
                ends_at__gt=candidate,
            )
            if exclude_reservation_id:
                reservations = reservations.exclude(pk=exclude_reservation_id)
            has_reservation = reservations.exists()
            if candidate >= earliest_start and not crosses_break and not has_absence and not has_reservation:
                slots.append(candidate)
            candidate += step

    return sorted(set(slots))
