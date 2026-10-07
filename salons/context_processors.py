from .access import MANAGE_OPERATIONAL_SETTINGS, active_memberships_for, membership_has_permission
from .models import Membership


def owner_navigation(request):
    memberships = list(active_memberships_for(request.user))
    return {
        'owner_salons': [membership.salon for membership in memberships if membership.role == Membership.Role.OWNER],
        'settings_salons': [
            membership.salon
            for membership in memberships
            if membership_has_permission(membership, MANAGE_OPERATIONAL_SETTINGS)
        ],
    }
