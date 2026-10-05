from .access import active_memberships_for
from .models import Membership


def owner_navigation(request):
    salons = active_memberships_for(request.user).filter(role=Membership.Role.OWNER).select_related('salon')
    return {'owner_salons': [membership.salon for membership in salons]}
