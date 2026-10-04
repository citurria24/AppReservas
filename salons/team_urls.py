from django.urls import path

from . import team_views


urlpatterns = [
    path("", team_views.team_management, name="team-management"),
    path("<int:pk>/editar/", team_views.team_membership_edit, name="team-membership-edit"),
]
