from datetime import date, datetime, time, timedelta

from django.core import signing
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.db.models import DateTimeField, ExpressionWrapper, F, Q, Value
from django.shortcuts import get_object_or_404
from django.utils import timezone

from .access import active_memberships_for, accessible_reservations_for
from .models import Branch, Membership, Reservation
from .reservation_status import change_reservation_status


TOKEN_SALT = 'salons.bulk-completion'


def managing_memberships(user):
    return active_memberships_for(user).filter(role__in=[Membership.Role.OWNER, Membership.Role.ADMIN])


def bulk_scope(user, day_value, branch_value):
    memberships = managing_memberships(user)
    if not memberships.exists():
        raise PermissionDenied
    day = date.fromisoformat(day_value)
    if day.year >= 9999:
        raise ValueError("Fecha fuera de rango")
    owners = memberships.filter(role=Membership.Role.OWNER).values('salon_id')
    admin_branches = memberships.filter(role=Membership.Role.ADMIN).values('branches__id')
    branches = Branch.objects.filter(Q(salon_id__in=owners) | Q(pk__in=admin_branches)).distinct()
    branch = get_object_or_404(branches, pk=branch_value) if branch_value else None
    return day, branch, branches


def eligible_reservations(user, day, branch, branches):
    start = timezone.make_aware(datetime.combine(day, time.min))
    end = timezone.make_aware(datetime.combine(day + timedelta(days=1), time.min))
    qs = accessible_reservations_for(user).filter(
        branch__in=branches, status=Reservation.Status.CONFIRMED,
        starts_at__gte=start, starts_at__lt=end,
    ).annotate(effective_end=ExpressionWrapper(
        F('starts_at') + F('duration_minutes') * Value(timedelta(minutes=1)),
        output_field=DateTimeField(),
    )).filter(effective_end__lt=timezone.now())
    return qs.filter(branch=branch) if branch else qs


def preview_completion(user, day_value, branch_value):
    day, branch, branches = bulk_scope(user, day_value, branch_value)
    ids = list(eligible_reservations(user, day, branch, branches).values_list('pk', flat=True))
    token = signing.dumps({'user': user.pk, 'day': day.isoformat(), 'branch': branch.pk if branch else '', 'ids': ids}, salt=TOKEN_SALT, compress=True)
    return day, branch, len(ids), token


@transaction.atomic
def complete_preview(user, token):
    data = signing.loads(token, salt=TOKEN_SALT, max_age=900)
    if data['user'] != user.pk:
        raise signing.BadSignature('Usuario incorrecto')
    day, branch, branches = bulk_scope(user, data['day'], data['branch'])
    eligible_ids = eligible_reservations(user, day, branch, branches).filter(pk__in=data['ids']).values('pk')
    # Lock only Reservation, avoiding DISTINCT and nullable joins.
    locked = list(Reservation.objects.select_for_update().filter(pk__in=eligible_ids).order_by('pk'))
    count = 0
    for reservation in locked:
        # A competing operation may have changed the row while we waited.
        if reservation.status != Reservation.Status.CONFIRMED:
            continue
        if reservation.starts_at + timedelta(minutes=reservation.duration_minutes) >= timezone.now():
            continue
        if not eligible_reservations(user, day, branch, branches).filter(pk=reservation.pk).exists():
            continue
        change_reservation_status(user=user, pk=reservation.pk, action='complete')
        count += 1
    return day, branch, count
