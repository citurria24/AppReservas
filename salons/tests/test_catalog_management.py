from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from salons.models import Branch, HairSalon, Membership, MembershipBranch


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
