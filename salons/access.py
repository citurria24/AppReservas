from django.shortcuts import get_object_or_404
from django.db.models import Q
from .models import Branch, HairSalon, Membership


def active_memberships_for(user):
    if not user.is_authenticated:
        return Membership.objects.none()
    return Membership.objects.filter(user=user, active=True, salon__active=True).select_related("salon")


def accessible_salons_for(user):
    return HairSalon.objects.filter(memberships__in=active_memberships_for(user)).distinct()


def accessible_branches_for(user):
    memberships = active_memberships_for(user)
    owner_salon_ids = memberships.filter(role=Membership.Role.OWNER).values("salon_id")
    explicit_branch_ids = Membership.objects.filter(
        id__in=memberships.exclude(role=Membership.Role.OWNER).values("id")
    ).values("branches__id")
    return Branch.objects.filter(Q(salon_id__in=owner_salon_ids) | Q(id__in=explicit_branch_ids), active=True).distinct()


def get_accessible_salon_or_404(user, slug):
    return get_object_or_404(accessible_salons_for(user), slug=slug)
