from django.contrib.auth import get_user_model
from django.db import connection
from django.test import TestCase
from django.urls import reverse
from salons.access import accessible_branches_for
from salons.models import Branch, HairSalon, Membership, MembershipBranch


class TenantAccessTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        User = get_user_model()
        cls.user_a = User.objects.create_user("owner-a", "a@example.test", "test-pass-123")
        cls.user_b = User.objects.create_user("owner-b", "b@example.test", "test-pass-123")
        cls.admin_a = User.objects.create_user("admin-a", "admin@example.test", "test-pass-123")
        cls.salon_a = HairSalon.objects.create(name="Salón A", slug="salon-a")
        cls.salon_b = HairSalon.objects.create(name="Salón B", slug="salon-b")
        cls.branch_a1 = Branch.objects.create(salon=cls.salon_a, name="A1", address="A 1")
        cls.branch_a2 = Branch.objects.create(salon=cls.salon_a, name="A2", address="A 2")
        cls.branch_b = Branch.objects.create(salon=cls.salon_b, name="B1", address="B 1")
        cls.owner_a = Membership.objects.create(salon=cls.salon_a, user=cls.user_a, role=Membership.Role.OWNER)
        cls.owner_b = Membership.objects.create(salon=cls.salon_b, user=cls.user_b, role=Membership.Role.OWNER)
        cls.membership_admin = Membership.objects.create(salon=cls.salon_a, user=cls.admin_a, role=Membership.Role.ADMIN)
        MembershipBranch.objects.create(membership=cls.membership_admin, branch=cls.branch_a1)

    def test_tests_really_use_postgresql(self):
        self.assertEqual(connection.vendor, "postgresql")

    def test_owner_only_sees_own_salon_on_dashboard(self):
        self.client.force_login(self.user_a)
        response = self.client.get(reverse("dashboard"))
        self.assertContains(response, "Salón A")
        self.assertNotContains(response, "Salón B")

    def test_cross_tenant_detail_returns_404(self):
        self.client.force_login(self.user_a)
        response = self.client.get(reverse("salon-detail", args=[self.salon_b.slug]))
        self.assertEqual(response.status_code, 404)

    def test_owner_gets_every_branch_in_own_salon_only(self):
        ids = set(accessible_branches_for(self.user_a).values_list("id", flat=True))
        self.assertEqual(ids, {self.branch_a1.id, self.branch_a2.id})

    def test_admin_gets_only_explicit_branch(self):
        ids = set(accessible_branches_for(self.admin_a).values_list("id", flat=True))
        self.assertEqual(ids, {self.branch_a1.id})
        self.client.force_login(self.admin_a)
        response = self.client.get(reverse("salon-detail", args=[self.salon_a.slug]))
        self.assertContains(response, "<h2>A1</h2>", html=True)
        self.assertNotContains(response, "<h2>A2</h2>", html=True)

    def test_detail_button_replaces_main_content_with_htmx_partial(self):
        self.client.force_login(self.user_a)
        dashboard = self.client.get(reverse("dashboard"))
        self.assertContains(dashboard, 'hx-target="main"')
        self.assertContains(dashboard, 'hx-swap="innerHTML show:top"')

        response = self.client.get(
            reverse("salon-detail", args=[self.salon_a.slug]),
            HTTP_HX_REQUEST="true",
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Salón A")
        self.assertNotContains(response, "<!doctype html>")

    def test_anonymous_user_is_redirected_to_login(self):
        response = self.client.get(reverse("dashboard"))
        self.assertRedirects(response, f"{reverse('login')}?next=/")
