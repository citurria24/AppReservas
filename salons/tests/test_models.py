from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.test import TestCase
from salons.models import Branch, BranchService, HairSalon, Membership, MembershipBranch, Professional, Service


class DomainIntegrityTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        User = get_user_model()
        cls.user1 = User.objects.create_user("one", "one@example.test", "test-pass-123")
        cls.user2 = User.objects.create_user("two", "two@example.test", "test-pass-123")
        cls.salon1 = HairSalon.objects.create(name="Uno", slug="uno")
        cls.salon2 = HairSalon.objects.create(name="Dos", slug="dos")
        cls.branch1 = Branch.objects.create(salon=cls.salon1, name="Centro", address="Uno")
        cls.branch2 = Branch.objects.create(salon=cls.salon2, name="Centro", address="Dos")
        cls.service1 = Service.objects.create(salon=cls.salon1, name="Corte")

    def test_database_allows_only_one_owner_per_salon(self):
        Membership.objects.create(salon=self.salon1, user=self.user1, role=Membership.Role.OWNER)
        with self.assertRaises(IntegrityError), transaction.atomic():
            Membership.objects.create(salon=self.salon1, user=self.user2, role=Membership.Role.OWNER)

    def test_professional_is_independent_from_membership_role(self):
        Membership.objects.create(salon=self.salon1, user=self.user1, role=Membership.Role.ADMIN)
        professional = Professional.objects.create(salon=self.salon1, user=self.user1, display_name="Profesional admin")
        self.assertEqual(professional.user, self.user1)
        self.assertEqual(professional.user.salon_memberships.get(salon=self.salon1).role, Membership.Role.ADMIN)

    def test_service_has_one_duration_per_branch(self):
        BranchService.objects.create(branch=self.branch1, service=self.service1, duration_minutes=30)
        with self.assertRaises(IntegrityError), transaction.atomic():
            BranchService.objects.bulk_create([
                BranchService(branch=self.branch1, service=self.service1, duration_minutes=45)
            ])

    def test_cross_tenant_service_assignment_is_rejected(self):
        offering = BranchService(branch=self.branch2, service=self.service1, duration_minutes=30)
        with self.assertRaises(ValidationError):
            offering.save()

    def test_cross_tenant_branch_permission_is_rejected(self):
        membership = Membership.objects.create(salon=self.salon1, user=self.user1, role=Membership.Role.ADMIN)
        access = MembershipBranch(membership=membership, branch=self.branch2)
        with self.assertRaises(ValidationError):
            access.save()
