from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse

from salons.models import (
    Branch,
    HairSalon,
    Membership,
    MembershipBranch,
    Professional,
)


class TeamManagementTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        User = get_user_model()
        cls.owner = User.objects.create_user("team-owner", "owner@team.test", "test-pass-123")
        cls.admin = User.objects.create_user("team-admin", "admin@team.test", "test-pass-123")
        cls.hairdresser = User.objects.create_user("team-hair", "hair@team.test", "test-pass-123")
        cls.other_owner = User.objects.create_user("other-team-owner", "other@team.test", "test-pass-123")
        cls.other_admin = User.objects.create_user("other-team-admin", "other-admin@team.test", "test-pass-123")

        cls.salon = HairSalon.objects.create(name="Equipo", slug="equipo")
        cls.other_salon = HairSalon.objects.create(name="Equipo ajeno", slug="equipo-ajeno")
        cls.branch = Branch.objects.create(salon=cls.salon, name="Centro", address="Principal 1")
        cls.second_branch = Branch.objects.create(salon=cls.salon, name="Pocitos", address="Rambla 2")
        cls.other_branch = Branch.objects.create(salon=cls.other_salon, name="Ajena", address="Lejos 3")
        cls.professional = Professional.objects.create(salon=cls.salon, display_name="Profesional libre")
        cls.other_professional = Professional.objects.create(
            salon=cls.other_salon,
            display_name="Profesional ajeno",
        )

        cls.owner_membership = Membership.objects.create(
            salon=cls.salon,
            user=cls.owner,
            role=Membership.Role.OWNER,
        )
        cls.admin_membership = Membership.objects.create(
            salon=cls.salon,
            user=cls.admin,
            role=Membership.Role.ADMIN,
        )
        cls.hair_membership = Membership.objects.create(
            salon=cls.salon,
            user=cls.hairdresser,
            role=Membership.Role.HAIRDRESSER,
        )
        MembershipBranch.objects.create(membership=cls.admin_membership, branch=cls.branch)
        MembershipBranch.objects.create(membership=cls.hair_membership, branch=cls.branch)
        Membership.objects.create(
            salon=cls.other_salon,
            user=cls.other_owner,
            role=Membership.Role.OWNER,
        )
        cls.other_admin_membership = Membership.objects.create(
            salon=cls.other_salon,
            user=cls.other_admin,
            role=Membership.Role.ADMIN,
        )
        MembershipBranch.objects.create(
            membership=cls.other_admin_membership,
            branch=cls.other_branch,
        )

    def creation_data(self, **overrides):
        data = {
            "username": "nuevo-admin",
            "first_name": "Nueva",
            "last_name": "Persona",
            "email": "nueva@team.test",
            "password1": "Equipo-Seguro-2026!",
            "password2": "Equipo-Seguro-2026!",
            "role": Membership.Role.ADMIN,
            "branches": [self.branch.id, self.second_branch.id],
            "professional": self.professional.id,
        }
        data.update(overrides)
        return data

    def test_owner_creates_user_membership_branches_and_professional_link(self):
        self.client.force_login(self.owner)
        response = self.client.post(
            reverse("team-management", args=[self.salon.slug]),
            self.creation_data(),
        )
        self.assertRedirects(response, reverse("team-management", args=[self.salon.slug]))
        user = get_user_model().objects.get(username="nuevo-admin")
        self.assertTrue(user.check_password("Equipo-Seguro-2026!"))
        self.assertFalse(user.is_staff)
        membership = Membership.objects.get(salon=self.salon, user=user)
        self.assertEqual(membership.role, Membership.Role.ADMIN)
        self.assertEqual(
            set(membership.branches.values_list("id", flat=True)),
            {self.branch.id, self.second_branch.id},
        )
        self.professional.refresh_from_db()
        self.assertEqual(self.professional.user, user)

    def test_admin_and_hairdresser_cannot_manage_team(self):
        url = reverse("team-management", args=[self.salon.slug])
        for user in (self.admin, self.hairdresser):
            self.client.force_login(user)
            response = self.client.get(url)
            self.assertEqual(response.status_code, 403)
            response = self.client.post(url, self.creation_data(username=f"attempt-{user.id}"))
            self.assertEqual(response.status_code, 403)
            response = self.client.post(
                reverse("team-membership-edit", args=[self.salon.slug, self.admin_membership.id]),
                {
                    "role": Membership.Role.HAIRDRESSER,
                    "branches": [self.second_branch.id],
                    "professional": "",
                    "active": "on",
                },
            )
            self.assertEqual(response.status_code, 403)
        self.assertFalse(get_user_model().objects.filter(email="nueva@team.test").exists())

    def test_owner_role_cannot_be_created_or_assigned(self):
        self.client.force_login(self.owner)
        create_response = self.client.post(
            reverse("team-management", args=[self.salon.slug]),
            self.creation_data(role=Membership.Role.OWNER),
        )
        self.assertEqual(create_response.status_code, 200)
        self.assertIn("role", create_response.context["form"].errors)
        self.assertFalse(get_user_model().objects.filter(username="nuevo-admin").exists())

        edit_response = self.client.post(
            reverse("team-membership-edit", args=[self.salon.slug, self.admin_membership.id]),
            {
                "role": Membership.Role.OWNER,
                "branches": [self.branch.id],
                "professional": "",
                "active": "on",
            },
        )
        self.assertEqual(edit_response.status_code, 200)
        self.assertIn("role", edit_response.context["form"].errors)
        self.admin_membership.refresh_from_db()
        self.assertEqual(self.admin_membership.role, Membership.Role.ADMIN)

    def test_owner_membership_cannot_be_edited_or_disabled(self):
        self.client.force_login(self.owner)
        url = reverse("team-membership-edit", args=[self.salon.slug, self.owner_membership.id])
        response = self.client.post(
            url,
            {
                "role": Membership.Role.HAIRDRESSER,
                "branches": [self.branch.id],
                "professional": "",
                "active": "",
            },
        )
        self.assertEqual(response.status_code, 404)
        self.owner_membership.refresh_from_db()
        self.assertTrue(self.owner_membership.active)
        self.assertEqual(self.owner_membership.role, Membership.Role.OWNER)

    def test_cross_tenant_branches_professionals_and_memberships_are_rejected(self):
        self.client.force_login(self.owner)
        response = self.client.post(
            reverse("team-management", args=[self.salon.slug]),
            self.creation_data(
                branches=[self.other_branch.id],
                professional=self.other_professional.id,
            ),
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn("branches", response.context["form"].errors)
        self.assertIn("professional", response.context["form"].errors)
        self.assertFalse(get_user_model().objects.filter(username="nuevo-admin").exists())

        response = self.client.get(
            reverse("team-membership-edit", args=[self.salon.slug, self.other_admin_membership.id])
        )
        self.assertEqual(response.status_code, 404)
        response = self.client.get(reverse("team-management", args=[self.other_salon.slug]))
        self.assertEqual(response.status_code, 404)

    def test_revoked_membership_loses_access_with_existing_session(self):
        admin_client = Client()
        admin_client.force_login(self.admin)
        detail_url = reverse("salon-detail", args=[self.salon.slug])
        self.assertEqual(admin_client.get(detail_url).status_code, 200)

        owner_client = Client()
        owner_client.force_login(self.owner)
        response = owner_client.post(
            reverse("team-membership-edit", args=[self.salon.slug, self.admin_membership.id]),
            {
                "role": Membership.Role.ADMIN,
                "branches": [self.branch.id],
                "professional": "",
                "active": "",
            },
        )
        self.assertRedirects(response, reverse("team-management", args=[self.salon.slug]))
        self.admin_membership.refresh_from_db()
        self.assertFalse(self.admin_membership.active)
        self.assertEqual(admin_client.get(detail_url).status_code, 404)
        self.assertEqual(
            admin_client.get(reverse("availability-settings", args=[self.salon.slug])).status_code,
            404,
        )

    def test_owner_can_change_role_branches_and_professional_link(self):
        self.client.force_login(self.owner)
        response = self.client.post(
            reverse("team-membership-edit", args=[self.salon.slug, self.admin_membership.id]),
            {
                "role": Membership.Role.HAIRDRESSER,
                "branches": [self.second_branch.id],
                "professional": self.professional.id,
                "active": "on",
            },
        )
        self.assertRedirects(response, reverse("team-management", args=[self.salon.slug]))
        self.admin_membership.refresh_from_db()
        self.assertEqual(self.admin_membership.role, Membership.Role.HAIRDRESSER)
        self.assertEqual(list(self.admin_membership.branches.values_list("id", flat=True)), [self.second_branch.id])
        self.professional.refresh_from_db()
        self.assertEqual(self.professional.user, self.admin)
