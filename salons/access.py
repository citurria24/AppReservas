from django.shortcuts import get_object_or_404
from django.db.models import Q
from .models import Branch, HairSalon, Membership, Reservation


MANAGE_OPERATIONAL_SETTINGS = "manage_operational_settings"

# Permisos de peluquería que cada rol recibe por defecto. El owner los tiene
# siempre todos. Cuando existan permisos configurables por admin, se resolverán
# en membership_has_permission sin cambiar a quienes la consultan.
DEFAULT_ROLE_PERMISSIONS = {
    Membership.Role.ADMIN: frozenset(),
    Membership.Role.HAIRDRESSER: frozenset(),
}


def membership_has_permission(membership, permission):
    if membership is None or not membership.active:
        return False
    if membership.role == Membership.Role.OWNER:
        return True
    return permission in DEFAULT_ROLE_PERMISSIONS.get(membership.role, frozenset())


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


def accessible_reservations_for(user):
    memberships = active_memberships_for(user)
    owner_salon_ids = memberships.filter(role=Membership.Role.OWNER).values("salon_id")
    admin_branch_ids = memberships.filter(role=Membership.Role.ADMIN).values("branches__id")
    hairdresser_branch_ids = memberships.filter(role=Membership.Role.HAIRDRESSER).values("branches__id")
    return Reservation.objects.filter(
        Q(salon_id__in=owner_salon_ids)
        | Q(branch_id__in=admin_branch_ids)
        | Q(branch_id__in=hairdresser_branch_ids, professional__user=user)
    ).select_related("salon", "branch", "service", "professional").distinct()


def can_manage_reservation(user, reservation):
    membership = active_memberships_for(user).filter(salon=reservation.salon).first()
    if not membership:
        return False
    if membership.role == Membership.Role.OWNER:
        return True
    return membership.role == Membership.Role.ADMIN and membership.branches.filter(id=reservation.branch_id).exists()


def can_complete_reservation(user, reservation):
    if can_manage_reservation(user, reservation):
        return True
    has_branch_access = active_memberships_for(user).filter(
        salon=reservation.salon,
        role=Membership.Role.HAIRDRESSER,
        branches=reservation.branch,
    ).exists()
    return has_branch_access and reservation.professional.user_id == user.id
