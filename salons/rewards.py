from datetime import date, datetime, time
from zoneinfo import ZoneInfo
from django.conf import settings
from django.utils import timezone
from .models import Reservation, RewardProgram, RewardRedemption


def reward_period(program, reference_date=None):
    reference_date = reference_date or timezone.localdate()
    if program.period == RewardProgram.Period.YEARLY:
        period_start = date(reference_date.year, 1, 1)
        period_end = date(reference_date.year + 1, 1, 1)
    else:
        period_start = date(reference_date.year, reference_date.month, 1)
        if reference_date.month == 12:
            period_end = date(reference_date.year + 1, 1, 1)
        else:
            period_end = date(reference_date.year, reference_date.month + 1, 1)
    return period_start, period_end


def available_reward(salon, customer_email, reference_date=None):
    try:
        program = salon.reward_program
    except RewardProgram.DoesNotExist:
        return None
    if not program.active:
        return None
    period_start, period_end = reward_period(program, reference_date)
    if RewardRedemption.objects.filter(
        salon=salon,
        customer_email__iexact=customer_email,
        period_start=period_start,
    ).exists():
        return None
    local_tz = ZoneInfo(settings.TIME_ZONE)
    starts_at = timezone.make_aware(datetime.combine(period_start, time.min), local_tz)
    ends_at = timezone.make_aware(datetime.combine(period_end, time.min), local_tz)
    attended = Reservation.objects.filter(
        salon=salon,
        email__iexact=customer_email,
        status=Reservation.Status.COMPLETED,
        starts_at__gte=starts_at,
        starts_at__lt=ends_at,
    ).count()
    if attended < program.services_required:
        return None
    return {
        "program": program,
        "period_start": period_start,
        "period_end": period_end,
        "attended": attended,
    }
