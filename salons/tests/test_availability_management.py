from datetime import timedelta
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from salons.models import (
    Branch,
    HairSalon,
    Membership,
    MembershipBranch,
    Professional,
    ProfessionalAbsence,
    ProfessionalBranch,
    ScheduleBreak,
    WorkSchedule,
)


class AvailabilityManagementTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        User = get_user_model()
        cls.owner = User.objects.create_user("hours-owner", "owner@hours.test", "test-pass-123")
        cls.admin = User.objects.create_user("hours-admin", "admin@hours.test", "test-pass-123")
        cls.hairdresser = User.objects.create_user("hours-hair", "hair@hours.test", "test-pass-123")
        cls.salon = HairSalon.objects.create(name="Horarios", slug="horarios")
        cls.branch = Branch.objects.create(salon=cls.salon, name="Permitida", address="Uno")
        cls.forbidden_branch = Branch.objects.create(salon=cls.salon, name="No autorizada", address="Dos")
        Membership.objects.create(salon=cls.salon, user=cls.owner, role=Membership.Role.OWNER)
        admin_membership = Membership.objects.create(salon=cls.salon, user=cls.admin, role=Membership.Role.ADMIN)
        MembershipBranch.objects.create(membership=admin_membership, branch=cls.branch)
        hair_membership = Membership.objects.create(salon=cls.salon, user=cls.hairdresser, role=Membership.Role.HAIRDRESSER)
        MembershipBranch.objects.create(membership=hair_membership, branch=cls.branch)
        cls.professional = Professional.objects.create(salon=cls.salon, display_name="Profesional permitido")
        cls.forbidden_professional = Professional.objects.create(salon=cls.salon, display_name="Profesional no autorizado")
        ProfessionalBranch.objects.create(professional=cls.professional, branch=cls.branch)
        ProfessionalBranch.objects.create(professional=cls.forbidden_professional, branch=cls.forbidden_branch)

    def test_admin_can_create_schedule_only_in_assigned_branch(self):
        self.client.force_login(self.admin)
        url = reverse("availability-settings", args=[self.salon.slug])
        response = self.client.post(
            url,
            {
                "form_type": "schedule",
                "professional": self.professional.id,
                "branch": self.branch.id,
                "weekday": 0,
                "starts_at": "09:00",
                "ends_at": "18:00",
            },
        )
        self.assertEqual(response.status_code, 302)
        self.assertTrue(WorkSchedule.objects.filter(professional=self.professional, branch=self.branch).exists())

        response = self.client.post(
            url,
            {
                "form_type": "schedule",
                "professional": self.forbidden_professional.id,
                "branch": self.forbidden_branch.id,
                "weekday": 1,
                "starts_at": "09:00",
                "ends_at": "18:00",
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertFalse(WorkSchedule.objects.filter(branch=self.forbidden_branch).exists())

    def test_hairdresser_cannot_manage_availability(self):
        self.client.force_login(self.hairdresser)
        response = self.client.get(reverse("availability-settings", args=[self.salon.slug]))
        self.assertEqual(response.status_code, 403)

    def test_break_must_remain_inside_schedule(self):
        schedule = WorkSchedule.objects.create(
            professional=self.professional,
            branch=self.branch,
            weekday=0,
            starts_at="09:00",
            ends_at="18:00",
        )
        self.client.force_login(self.owner)
        response = self.client.post(
            reverse("availability-settings", args=[self.salon.slug]),
            {"form_type": "break", "schedule": schedule.id, "starts_at": "08:00", "ends_at": "10:00"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(ScheduleBreak.objects.count(), 0)
        self.assertContains(response, "El descanso debe estar dentro de la jornada")

    def test_owner_can_register_absence(self):
        self.client.force_login(self.owner)
        starts = timezone.localtime(timezone.now() + timedelta(days=2)).replace(minute=0, second=0, microsecond=0)
        response = self.client.post(
            reverse("availability-settings", args=[self.salon.slug]),
            {
                "form_type": "absence",
                "professional": self.professional.id,
                "branch": self.branch.id,
                "starts_at": starts.strftime("%Y-%m-%dT%H:%M"),
                "ends_at": (starts + timedelta(hours=2)).strftime("%Y-%m-%dT%H:%M"),
                "reason": "Capacitación",
            },
        )
        self.assertEqual(response.status_code, 302)
        self.assertTrue(ProfessionalAbsence.objects.filter(reason="Capacitación").exists())

    def test_admin_cannot_delete_schedule_from_unassigned_branch(self):
        schedule = WorkSchedule.objects.create(
            professional=self.forbidden_professional,
            branch=self.forbidden_branch,
            weekday=0,
            starts_at="09:00",
            ends_at="18:00",
        )
        self.client.force_login(self.admin)
        response = self.client.post(
            reverse("availability-delete", args=[self.salon.slug, "schedule", schedule.id])
        )
        self.assertEqual(response.status_code, 404)
        self.assertTrue(WorkSchedule.objects.filter(id=schedule.id).exists())

