from datetime import timedelta
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from salons.models import Branch, HairSalon, Membership, MembershipBranch, Professional, Reservation, Service


class CancellationPolicyTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        User = get_user_model()
        cls.owner = User.objects.create_user("policy-owner", "owner@policy.test", "test-pass-123")
        cls.admin = User.objects.create_user("policy-admin", "admin@policy.test", "test-pass-123")
        cls.hairdresser = User.objects.create_user("policy-hair", "hair@policy.test", "test-pass-123")
        cls.salon = HairSalon.objects.create(name="Políticas", slug="politicas", cancellation_notice_hours=24)
        cls.branch = Branch.objects.create(salon=cls.salon, name="Centro", address="Centro 10", phone="2900 0000")
        cls.service = Service.objects.create(salon=cls.salon, name="Corte")
        cls.professional = Professional.objects.create(salon=cls.salon, user=cls.hairdresser, display_name="Alex")
        Membership.objects.create(salon=cls.salon, user=cls.owner, role=Membership.Role.OWNER)
        admin_membership = Membership.objects.create(salon=cls.salon, user=cls.admin, role=Membership.Role.ADMIN)
        MembershipBranch.objects.create(membership=admin_membership, branch=cls.branch)
        hair_membership = Membership.objects.create(salon=cls.salon, user=cls.hairdresser, role=Membership.Role.HAIRDRESSER)
        MembershipBranch.objects.create(membership=hair_membership, branch=cls.branch)

    def create_reservation(self, *, hours_from_now=72, notice=24):
        starts = timezone.now() + timedelta(hours=hours_from_now)
        return Reservation.objects.create(
            salon=self.salon,
            branch=self.branch,
            service=self.service,
            professional=self.professional,
            first_name="Cliente",
            last_name="Cancelación",
            email="cancel@example.test",
            contact="099 111 111",
            starts_at=starts,
            ends_at=starts + timedelta(minutes=30),
            duration_minutes=30,
            cancellation_notice_hours=notice,
        )

    def test_owner_and_admin_can_update_policy(self):
        url = reverse("salon-settings", args=[self.salon.slug])
        self.client.force_login(self.owner)
        response = self.client.post(url, {"cancellation_notice_hours": 48})
        self.assertEqual(response.status_code, 200)
        self.salon.refresh_from_db()
        self.assertEqual(self.salon.cancellation_notice_hours, 48)
        self.client.force_login(self.admin)
        response = self.client.post(url, {"cancellation_notice_hours": 36})
        self.assertEqual(response.status_code, 200)
        self.salon.refresh_from_db()
        self.assertEqual(self.salon.cancellation_notice_hours, 36)

    def test_hairdresser_cannot_update_policy(self):
        self.client.force_login(self.hairdresser)
        response = self.client.post(
            reverse("salon-settings", args=[self.salon.slug]),
            {"cancellation_notice_hours": 1},
        )
        self.assertEqual(response.status_code, 403)

    def test_client_can_cancel_before_deadline(self):
        reservation = self.create_reservation()
        url = reverse("client-cancel", args=[self.salon.slug, reservation.cancellation_token])
        response = self.client.post(url)
        self.assertEqual(response.status_code, 200)
        reservation.refresh_from_db()
        self.assertEqual(reservation.status, Reservation.Status.CANCELLED_CLIENT)
        self.assertContains(response, "Tu reserva fue cancelada")

    def test_client_cannot_cancel_after_deadline_and_sees_phone(self):
        reservation = self.create_reservation(hours_from_now=12, notice=24)
        url = reverse("client-cancel", args=[self.salon.slug, reservation.cancellation_token])
        response = self.client.post(url)
        self.assertEqual(response.status_code, 200)
        reservation.refresh_from_db()
        self.assertEqual(reservation.status, Reservation.Status.CONFIRMED)
        self.assertContains(response, "Ya no es posible cancelar online")
        self.assertContains(response, "2900 0000")

    def test_token_cannot_be_used_with_another_salon_slug(self):
        reservation = self.create_reservation()
        other = HairSalon.objects.create(name="Otra", slug="otra")
        response = self.client.get(reverse("client-cancel", args=[other.slug, reservation.cancellation_token]))
        self.assertEqual(response.status_code, 404)

