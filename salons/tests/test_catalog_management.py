from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from salons.models import Branch, BranchService, HairSalon, Membership, MembershipBranch, Service


class BranchManagementTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        User = get_user_model()
        cls.owner = User.objects.create_user("catalog-owner", "owner@catalog.test", "test-pass-123")
        cls.other_owner = User.objects.create_user("other-owner", "other@catalog.test", "test-pass-123")
        cls.admin = User.objects.create_user("catalog-admin", "admin@catalog.test", "test-pass-123")
        cls.salon = HairSalon.objects.create(name="Catálogo", slug="catalogo")
        cls.other_salon = HairSalon.objects.create(name="Otro catálogo", slug="otro-catalogo")
        cls.branch = Branch.objects.create(salon=cls.salon, name="Centro", address="Principal 1")
        cls.other_branch = Branch.objects.create(salon=cls.other_salon, name="Ajena", address="Lejos 2")
        Membership.objects.create(salon=cls.salon, user=cls.owner, role=Membership.Role.OWNER)
        Membership.objects.create(salon=cls.other_salon, user=cls.other_owner, role=Membership.Role.OWNER)
        admin_membership = Membership.objects.create(salon=cls.salon, user=cls.admin, role=Membership.Role.ADMIN)
        MembershipBranch.objects.create(membership=admin_membership, branch=cls.branch)

    def test_owner_can_create_and_edit_a_branch(self):
        self.client.force_login(self.owner)
        response = self.client.post(
            reverse("branch-management", args=[self.salon.slug]),
            {"name": "Pocitos", "address": "Rambla 123", "phone": "2711 0000", "active": "on"},
        )
        self.assertRedirects(response, reverse("branch-management", args=[self.salon.slug]))
        branch = Branch.objects.get(salon=self.salon, name="Pocitos")

        response = self.client.post(
            reverse("branch-edit", args=[self.salon.slug, branch.id]),
            {"name": "Pocitos Nuevo", "address": "Rambla 456", "phone": "", "active": ""},
        )
        self.assertRedirects(response, reverse("branch-management", args=[self.salon.slug]))
        branch.refresh_from_db()
        self.assertEqual(branch.name, "Pocitos Nuevo")
        self.assertFalse(branch.active)

    def test_admin_cannot_manage_branches(self):
        self.client.force_login(self.admin)
        response = self.client.get(reverse("branch-management", args=[self.salon.slug]))
        self.assertEqual(response.status_code, 403)

    def test_owner_cannot_edit_branch_from_another_salon(self):
        self.client.force_login(self.owner)
        response = self.client.get(reverse("branch-edit", args=[self.salon.slug, self.other_branch.id]))
        self.assertEqual(response.status_code, 404)

    def test_duplicate_branch_name_is_rejected_case_insensitively(self):
        self.client.force_login(self.owner)
        response = self.client.post(
            reverse("branch-management", args=[self.salon.slug]),
            {"name": "centro", "address": "Otra", "phone": "", "active": "on"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Ya existe una sucursal con ese nombre")
        self.assertEqual(Branch.objects.filter(salon=self.salon).count(), 1)


class ServiceManagementTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        User = get_user_model()
        cls.owner = User.objects.create_user("service-owner", "owner@service.test", "test-pass-123")
        cls.other_owner = User.objects.create_user("other-service-owner", "other@service.test", "test-pass-123")
        cls.admin = User.objects.create_user("service-admin", "admin@service.test", "test-pass-123")
        cls.salon = HairSalon.objects.create(name="Servicios", slug="servicios")
        cls.other_salon = HairSalon.objects.create(name="Servicios ajenos", slug="servicios-ajenos")
        cls.branch = Branch.objects.create(salon=cls.salon, name="Centro", address="Principal 1")
        cls.other_branch = Branch.objects.create(salon=cls.other_salon, name="Ajena", address="Lejos 2")
        cls.service = Service.objects.create(salon=cls.salon, name="Corte")
        cls.other_service = Service.objects.create(salon=cls.other_salon, name="Color ajeno")
        cls.offering = BranchService.objects.create(branch=cls.branch, service=cls.service, duration_minutes=30)
        cls.other_offering = BranchService.objects.create(branch=cls.other_branch, service=cls.other_service, duration_minutes=45)
        Membership.objects.create(salon=cls.salon, user=cls.owner, role=Membership.Role.OWNER)
        Membership.objects.create(salon=cls.other_salon, user=cls.other_owner, role=Membership.Role.OWNER)
        admin_membership = Membership.objects.create(salon=cls.salon, user=cls.admin, role=Membership.Role.ADMIN)
        MembershipBranch.objects.create(membership=admin_membership, branch=cls.branch)

    def test_owner_can_create_service_and_branch_duration(self):
        self.client.force_login(self.owner)
        url = reverse("service-management", args=[self.salon.slug])
        response = self.client.post(url, {"form_type": "service", "name": "Color", "active": "on"})
        self.assertRedirects(response, url)
        service = Service.objects.get(salon=self.salon, name="Color")

        response = self.client.post(
            url,
            {
                "form_type": "offering",
                "branch": self.branch.id,
                "service": service.id,
                "duration_minutes": 75,
                "active": "on",
            },
        )
        self.assertRedirects(response, url)
        self.assertTrue(
            BranchService.objects.filter(branch=self.branch, service=service, duration_minutes=75).exists()
        )

    def test_owner_can_edit_and_deactivate_an_offering(self):
        self.client.force_login(self.owner)
        response = self.client.post(
            reverse("offering-edit", args=[self.salon.slug, self.offering.id]),
            {
                "branch": self.branch.id,
                "service": self.service.id,
                "duration_minutes": 40,
                "active": "",
            },
        )
        self.assertRedirects(response, reverse("service-management", args=[self.salon.slug]))
        self.offering.refresh_from_db()
        self.assertEqual(self.offering.duration_minutes, 40)
        self.assertFalse(self.offering.active)

    def test_admin_cannot_manage_service_catalog(self):
        self.client.force_login(self.admin)
        response = self.client.get(reverse("service-management", args=[self.salon.slug]))
        self.assertEqual(response.status_code, 403)

    def test_cross_tenant_offering_is_rejected_and_edit_returns_404(self):
        self.client.force_login(self.owner)
        url = reverse("service-management", args=[self.salon.slug])
        response = self.client.post(
            url,
            {
                "form_type": "offering",
                "branch": self.other_branch.id,
                "service": self.service.id,
                "duration_minutes": 30,
                "active": "on",
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn("branch", response.context["offering_form"].errors)
        response = self.client.get(reverse("offering-edit", args=[self.salon.slug, self.other_offering.id]))
        self.assertEqual(response.status_code, 404)
