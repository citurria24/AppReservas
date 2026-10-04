from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.db.models import Prefetch
from django.shortcuts import get_object_or_404, redirect, render

from .access import active_memberships_for, get_accessible_salon_or_404
from .models import Membership, Professional
from .team_forms import CreateTeamMemberForm, EditTeamMembershipForm


def _owner_salon_or_403(user, slug):
    salon = get_accessible_salon_or_404(user, slug)
    membership = active_memberships_for(user).get(salon=salon)
    if membership.role != Membership.Role.OWNER:
        raise PermissionDenied
    return salon


@login_required
def team_management(request, slug):
    salon = _owner_salon_or_403(request.user, slug)
    form = CreateTeamMemberForm(request.POST or None, salon=salon)
    if request.method == "POST" and form.is_valid():
        with transaction.atomic():
            User = get_user_model()
            user = User(
                username=form.cleaned_data["username"],
                first_name=form.cleaned_data["first_name"],
                last_name=form.cleaned_data["last_name"],
                email=form.cleaned_data["email"],
            )
            user.set_password(form.cleaned_data["password1"])
            user.save()
            membership = Membership.objects.create(
                salon=salon,
                user=user,
                role=form.cleaned_data["role"],
            )
            membership.branches.set(form.cleaned_data["branches"])
            professional = form.cleaned_data["professional"]
            if professional:
                professional.user = user
                professional.save(update_fields=["user"])
        return redirect("team-management", slug=salon.slug)

    memberships = salon.memberships.select_related("user").prefetch_related(
        "branches",
        Prefetch(
            "user__professional_profiles",
            queryset=Professional.objects.filter(salon=salon),
            to_attr="team_professionals",
        ),
    ).order_by("role", "user__username")
    rows = [
        {
            "membership": membership,
            "professional": membership.user.team_professionals[0]
            if membership.user.team_professionals
            else None,
            "can_edit": membership.role != Membership.Role.OWNER,
        }
        for membership in memberships
    ]
    return render(
        request,
        "salons/team_management.html",
        {"salon": salon, "form": form, "rows": rows},
    )


@login_required
def team_membership_edit(request, slug, pk):
    salon = _owner_salon_or_403(request.user, slug)
    membership = get_object_or_404(
        Membership.objects.select_related("user"),
        salon=salon,
        pk=pk,
        role__in=[Membership.Role.ADMIN, Membership.Role.HAIRDRESSER],
    )
    form = EditTeamMembershipForm(
        request.POST or None,
        salon=salon,
        membership=membership,
    )
    if request.method == "POST" and form.is_valid():
        with transaction.atomic():
            membership.role = form.cleaned_data["role"]
            membership.active = form.cleaned_data["active"]
            membership.save(update_fields=["role", "active"])
            membership.branches.set(form.cleaned_data["branches"])

            current_professional = salon.professionals.filter(user=membership.user).first()
            selected_professional = form.cleaned_data["professional"]
            if current_professional and current_professional != selected_professional:
                current_professional.user = None
                current_professional.save(update_fields=["user"])
            if selected_professional and selected_professional.user_id != membership.user_id:
                selected_professional.user = membership.user
                selected_professional.save(update_fields=["user"])
        return redirect("team-management", slug=salon.slug)
    return render(
        request,
        "salons/team_membership_edit.html",
        {"salon": salon, "membership": membership, "form": form},
    )
