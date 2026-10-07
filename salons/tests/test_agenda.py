from datetime import datetime, timedelta
from unittest.mock import patch
from zoneinfo import ZoneInfo
from django.conf import settings
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
    ProfessionalBranch,
    Reservation,
    Service,
)


def after_start(reservation):
    """Atendida/Ausente solo se permiten desde el inicio de la reserva."""
    return patch("django.utils.timezone.now", return_value=reservation.starts_at + timedelta(minutes=1))


class AgendaPermissionTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        User = get_user_model()
        cls.owner = User.objects.create_user("agenda-owner", "owner@agenda.test", "test-pass-123")
        cls.admin = User.objects.create_user("agenda-admin", "admin@agenda.test", "test-pass-123")
        cls.hairdresser = User.objects.create_user("agenda-pro", "pro@agenda.test", "test-pass-123")
        cls.other_owner = User.objects.create_user("other-owner", "other@agenda.test", "test-pass-123")
        cls.salon = HairSalon.objects.create(name="Agenda Uno", slug="agenda-uno")
        cls.other_salon = HairSalon.objects.create(name="Agenda Dos", slug="agenda-dos")
        cls.branch = Branch.objects.create(salon=cls.salon, name="Centro", address="Centro 1")
        cls.other_branch_same_salon = Branch.objects.create(salon=cls.salon, name="Este", address="Este 2")
        cls.foreign_branch = Branch.objects.create(salon=cls.other_salon, name="Sur", address="Sur 3")
        Membership.objects.create(salon=cls.salon, user=cls.owner, role=Membership.Role.OWNER)
        admin_membership = Membership.objects.create(salon=cls.salon, user=cls.admin, role=Membership.Role.ADMIN)
        MembershipBranch.objects.create(membership=admin_membership, branch=cls.branch)
        hair_membership = Membership.objects.create(salon=cls.salon, user=cls.hairdresser, role=Membership.Role.HAIRDRESSER)
        MembershipBranch.objects.create(membership=hair_membership, branch=cls.branch)
        Membership.objects.create(salon=cls.other_salon, user=cls.other_owner, role=Membership.Role.OWNER)
        cls.professional = Professional.objects.create(salon=cls.salon, user=cls.hairdresser, display_name="Profesional propio")
        cls.colleague = Professional.objects.create(salon=cls.salon, display_name="Colega")
        cls.foreign_professional = Professional.objects.create(salon=cls.other_salon, display_name="Profesional ajeno")
        ProfessionalBranch.objects.create(professional=cls.professional, branch=cls.branch)
        ProfessionalBranch.objects.create(professional=cls.colleague, branch=cls.branch)
        ProfessionalBranch.objects.create(professional=cls.foreign_professional, branch=cls.foreign_branch)
        cls.service = Service.objects.create(salon=cls.salon, name="Corte")
        cls.foreign_service = Service.objects.create(salon=cls.other_salon, name="Color")
        local_tz = ZoneInfo(settings.TIME_ZONE)
        cls.day = timezone.localdate() + timedelta(days=2)
        starts = timezone.make_aware(datetime.combine(cls.day, datetime.min.time().replace(hour=10)), local_tz)
        cls.own_reservation = cls.create_reservation(cls.salon, cls.branch, cls.service, cls.professional, starts, "Cliente propio")
        cls.colleague_reservation = cls.create_reservation(cls.salon, cls.branch, cls.service, cls.colleague, starts, "Cliente colega")
        cls.foreign_reservation = cls.create_reservation(cls.other_salon, cls.foreign_branch, cls.foreign_service, cls.foreign_professional, starts, "Cliente ajeno")

    @classmethod
    def create_reservation(cls, salon, branch, service, professional, starts, first_name):
        return Reservation.objects.create(
            salon=salon,
            branch=branch,
            service=service,
            professional=professional,
            first_name=first_name,
            last_name="Demo",
            email=f"{first_name.replace(' ', '.').lower()}@example.test",
            contact="099 000 000",
            starts_at=starts,
            ends_at=starts + timedelta(minutes=30),
            duration_minutes=30,
        )

    def agenda_url(self):
        return f"{reverse('agenda')}?date={self.day.isoformat()}"

    def test_owner_sees_own_salon_reservations_only(self):
        self.client.force_login(self.owner)
        response = self.client.get(self.agenda_url())
        self.assertContains(response, "Cliente propio")
        self.assertContains(response, "Cliente colega")
        self.assertNotContains(response, "Cliente ajeno")

    def test_admin_only_sees_assigned_branch(self):
        self.client.force_login(self.admin)
        response = self.client.get(self.agenda_url())
        self.assertContains(response, "Cliente propio")
        self.assertNotContains(response, "Agenda Dos")
        self.assertNotContains(response, "Este 2")

    def test_hairdresser_only_sees_own_reservations(self):
        self.client.force_login(self.hairdresser)
        response = self.client.get(self.agenda_url())
        self.assertContains(response, "Cliente propio")
        self.assertNotContains(response, "Cliente colega")

    def test_admin_can_cancel_local_reservation_but_not_foreign_one(self):
        self.client.force_login(self.admin)
        response = self.client.post(reverse("reservation-status", args=[self.own_reservation.id]), {"action": "cancel"})
        self.assertEqual(response.status_code, 302)
        self.own_reservation.refresh_from_db()
        self.assertEqual(self.own_reservation.status, Reservation.Status.CANCELLED_SALON)
        response = self.client.post(reverse("reservation-status", args=[self.foreign_reservation.id]), {"action": "cancel"})
        self.assertEqual(response.status_code, 404)

    def test_hairdresser_can_complete_but_cannot_cancel_own_reservation(self):
        self.client.force_login(self.hairdresser)
        response = self.client.post(reverse("reservation-status", args=[self.own_reservation.id]), {"action": "cancel"})
        self.assertEqual(response.status_code, 403)
        with after_start(self.own_reservation):
            response = self.client.post(reverse("reservation-status", args=[self.own_reservation.id]), {"action": "complete"})
        self.assertEqual(response.status_code, 302)
        self.own_reservation.refresh_from_db()
        self.assertEqual(self.own_reservation.status, Reservation.Status.COMPLETED)

