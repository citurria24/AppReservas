from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from django.conf import settings
from django.utils import timezone
from .models import BranchService, ProfessionalAbsence, Reservation, WorkSchedule


SLOT_STEP_MINUTES = 15


def available_slots(*, salon, branch, service, professional, day):
    if branch.salon_id != salon.id or service.salon_id != salon.id or professional.salon_id != salon.id:
        return []
    if not professional.branches.filter(id=branch.id, active=True).exists():
        return []
    if not professional.services.filter(id=service.id, active=True).exists():
        return []

    offering = BranchService.objects.filter(branch=branch, service=service, active=True).first()
    if not offering:
        return []

    tz = ZoneInfo(settings.TIME_ZONE)
    duration = timedelta(minutes=offering.duration_minutes)
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
            has_reservation = Reservation.objects.filter(
                professional=professional,
                status=Reservation.Status.CONFIRMED,
                starts_at__lt=candidate_end,
                ends_at__gt=candidate,
            ).exists()
            if candidate > timezone.now() and not crosses_break and not has_absence and not has_reservation:
                slots.append(candidate)
            candidate += timedelta(minutes=SLOT_STEP_MINUTES)

    return sorted(set(slots))
