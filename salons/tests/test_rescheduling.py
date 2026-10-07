from datetime import datetime, time, timedelta
from unittest.mock import patch
from zoneinfo import ZoneInfo

from django.conf import settings
from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from accounts.email_delivery import EmailDeliveryError
from salons.models import (
    Branch,
    BranchService,
    HairSalon,
    Membership,
    MembershipBranch,
    Professional,
    ProfessionalBranch,
    ProfessionalService,
    Reservation,
    ReservationReschedule,
    Service,
    WorkSchedule,
)
from salons.rescheduling import slots_for_reservation


def next_weekday(weekday):
    # Client rescheduling requires 24 hours of notice. Starting two calendar
    # days ahead keeps these tests valid regardless of the current time.
    candidate = timezone.localdate() + timedelta(days=2)
    while candidate.weekday() != weekday:
        candidate += timedelta(days=1)
    return candidate


@override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
class ReservationReschedulingTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        User = get_user_model()
        cls.owner = User.objects.create_user("move-owner", "owner@move.test", "test-pass-123")
        cls.admin = User.objects.create_user("move-admin", "admin@move.test", "test-pass-123")
        cls.hairdresser = User.objects.create_user("move-hair", "hair@move.test", "test-pass-123")
        cls.other_owner = User.objects.create_user("move-other", "other@move.test", "test-pass-123")

        cls.salon = HairSalon.objects.create(name="Reprogramación", slug="reprogramacion")
        cls.other_salon = HairSalon.objects.create(name="Otra agenda", slug="otra-agenda")
        cls.branch = Branch.objects.create(
            salon=cls.salon,
            name="Centro",
            address="Principal 1",
            phone="2900 0000",
        )
        cls.forbidden_branch = Branch.objects.create(salon=cls.salon, name="Este", address="Este 2")
        cls.other_branch = Branch.objects.create(salon=cls.other_salon, name="Ajena", address="Lejos 3")
        cls.service = Service.objects.create(salon=cls.salon, name="Corte")
        cls.other_service = Service.objects.create(salon=cls.other_salon, name="Servicio ajeno")
        cls.professional = Professional.objects.create(
            salon=cls.salon,
            user=cls.hairdresser,
            display_name="Alex",
        )
        cls.limit_professional = Professional.objects.create(salon=cls.salon, display_name="Colega")
        cls.other_professional = Professional.objects.create(salon=cls.other_salon, display_name="Persona ajena")
        ProfessionalBranch.objects.create(professional=cls.professional, branch=cls.branch)
        ProfessionalService.objects.create(professional=cls.professional, service=cls.service)
        BranchService.objects.create(branch=cls.branch, service=cls.service, duration_minutes=30)

        Membership.objects.create(salon=cls.salon, user=cls.owner, role=Membership.Role.OWNER)
        admin_membership = Membership.objects.create(salon=cls.salon, user=cls.admin, role=Membership.Role.ADMIN)
        MembershipBranch.objects.create(membership=admin_membership, branch=cls.branch)
        hair_membership = Membership.objects.create(
            salon=cls.salon,
            user=cls.hairdresser,
            role=Membership.Role.HAIRDRESSER,
        )
        MembershipBranch.objects.create(membership=hair_membership, branch=cls.branch)
        Membership.objects.create(salon=cls.other_salon, user=cls.other_owner, role=Membership.Role.OWNER)

        cls.day = next_weekday(0)
        WorkSchedule.objects.create(
            professional=cls.professional,
            branch=cls.branch,
            weekday=0,
            starts_at=time(9),
            ends_at=time(18),
        )
        local_tz = ZoneInfo(settings.TIME_ZONE)
        starts = timezone.make_aware(datetime.combine(cls.day, time(10)), local_tz)
        cls.reservation = Reservation.objects.create(
            salon=cls.salon,
            branch=cls.branch,
            service=cls.service,
            professional=cls.professional,
            first_name="Cliente",
            last_name="Demo",
            email="cliente@move.test",
            contact="099 111 111",
            starts_at=starts,
            ends_at=starts + timedelta(minutes=30),
            duration_minutes=30,
            cancellation_notice_hours=24,
        )
        cls.foreign_reservation = Reservation.objects.create(
            salon=cls.other_salon,
            branch=cls.other_branch,
            service=cls.other_service,
            professional=cls.other_professional,
            first_name="Cliente",
            last_name="Ajeno",
            email="cliente@move.test",
            contact="099 222 222",
            starts_at=starts,
            ends_at=starts + timedelta(minutes=30),
            duration_minutes=30,
        )

    def new_slot(self):
        return next(
            slot
            for slot in slots_for_reservation(self.reservation, self.day)
            if slot != self.reservation.starts_at
        )

    def payload(self, slot=None):
        selected = slot or self.new_slot()
        return {"date": self.day.isoformat(), "slot": selected.isoformat()}

    def test_current_slot_is_released_for_calculation_but_cannot_be_saved_again(self):
        slots = slots_for_reservation(self.reservation, self.day)
        self.assertIn(self.reservation.starts_at, slots)
        self.client.force_login(self.owner)
        response = self.client.post(
            reverse("reservation-reschedule", args=[self.reservation.id]),
            self.payload(self.reservation.starts_at),
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Elegí un horario diferente")
        self.assertEqual(ReservationReschedule.objects.count(), 0)

    def test_owner_reschedules_and_creates_audited_history(self):
        from django.core import mail

        old_start = self.reservation.starts_at
        selected = self.new_slot()
        self.client.force_login(self.owner)
        response = self.client.post(
            reverse("reservation-reschedule", args=[self.reservation.id]),
            self.payload(selected),
        )
        self.assertRedirects(response, f"{reverse('agenda')}?date={self.day.isoformat()}")
        self.reservation.refresh_from_db()
        self.assertEqual(self.reservation.starts_at, selected)
        self.assertEqual(self.reservation.duration_minutes, 30)
        self.assertEqual(self.reservation.cancellation_notice_hours, 24)
        history = ReservationReschedule.objects.get()
        self.assertEqual(history.previous_starts_at, old_start)
        self.assertEqual(history.new_starts_at, selected)
        self.assertEqual(history.source, ReservationReschedule.Source.SALON)
        self.assertEqual(history.changed_by, self.owner)
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].alternatives[0].mimetype, "text/html")

    def test_client_reschedules_with_token_and_without_local_account(self):
        selected = self.new_slot()
        response = self.client.post(
            reverse(
                "client-reschedule",
                args=[self.salon.slug, self.reservation.cancellation_token],
            ),
            self.payload(selected),
        )
        expected = reverse(
            "client-cancel",
            args=[self.salon.slug, self.reservation.cancellation_token],
        )
        self.assertRedirects(response, f"{expected}?reprogramada=1")
        self.reservation.refresh_from_db()
        self.assertEqual(self.reservation.starts_at, selected)
        history = ReservationReschedule.objects.get()
        self.assertEqual(history.source, ReservationReschedule.Source.CLIENT)
        self.assertIsNone(history.changed_by)

    def test_admin_can_reschedule_an_assigned_branch(self):
        selected = self.new_slot()
        self.client.force_login(self.admin)
        response = self.client.post(
            reverse("reservation-reschedule", args=[self.reservation.id]),
            self.payload(selected),
        )
        self.assertEqual(response.status_code, 302)
        history = ReservationReschedule.objects.get()
        self.assertEqual(history.changed_by, self.admin)

    def test_hairdresser_cannot_reschedule_and_other_tenant_is_hidden(self):
        self.client.force_login(self.hairdresser)
        response = self.client.post(
            reverse("reservation-reschedule", args=[self.reservation.id]),
            self.payload(),
        )
        self.assertEqual(response.status_code, 403)

        self.client.force_login(self.owner)
        response = self.client.get(reverse("reservation-reschedule", args=[self.foreign_reservation.id]))
        self.assertEqual(response.status_code, 404)
        response = self.client.get(
            reverse(
                "client-reschedule",
                args=[self.other_salon.slug, self.reservation.cancellation_token],
            )
        )
        self.assertEqual(response.status_code, 404)

    def test_client_cannot_reschedule_after_cancellation_deadline(self):
        self.reservation.starts_at = timezone.now() + timedelta(hours=2)
        self.reservation.ends_at = self.reservation.starts_at + timedelta(minutes=30)
        self.reservation.save()
        response = self.client.get(
            reverse(
                "client-reschedule",
                args=[self.salon.slug, self.reservation.cancellation_token],
            )
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "ya no se puede reprogramar")

    def test_occupied_slot_is_rejected_without_history(self):
        occupied = self.new_slot()
        Reservation.objects.create(
            salon=self.salon,
            branch=self.branch,
            service=self.service,
            professional=self.professional,
            first_name="Otra",
            last_name="Persona",
            email="otra@move.test",
            contact="099",
            starts_at=occupied,
            ends_at=occupied + timedelta(minutes=30),
            duration_minutes=30,
        )
        self.client.force_login(self.owner)
        response = self.client.post(
            reverse("reservation-reschedule", args=[self.reservation.id]),
            self.payload(occupied),
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Ese horario ya no está disponible")
        self.assertEqual(ReservationReschedule.objects.count(), 0)

    def test_email_failure_rolls_back_reservation_and_history(self):
        old_start = self.reservation.starts_at
        self.client.force_login(self.owner)
        with patch(
            "salons.rescheduling.send_reservation_rescheduled_email",
            side_effect=EmailDeliveryError("SMTP no disponible"),
        ):
            response = self.client.post(
                reverse("reservation-reschedule", args=[self.reservation.id]),
                self.payload(),
            )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "conserva su horario anterior")
        self.reservation.refresh_from_db()
        self.assertEqual(self.reservation.starts_at, old_start)
        self.assertEqual(ReservationReschedule.objects.count(), 0)

    def test_daily_limit_is_enforced_when_moving(self):
        local_tz = ZoneInfo(settings.TIME_ZONE)
        first_start = timezone.make_aware(datetime.combine(self.day, time(6)), local_tz)
        for index in range(5):
            starts = first_start + timedelta(minutes=index * 30)
            Reservation.objects.create(
                salon=self.salon,
                branch=self.branch,
                service=self.service,
                professional=self.limit_professional,
                first_name="Cliente",
                last_name="Demo",
                email=self.reservation.email,
                contact="099",
                starts_at=starts,
                ends_at=starts + timedelta(minutes=30),
                duration_minutes=30,
            )
        self.client.force_login(self.owner)
        response = self.client.post(
            reverse("reservation-reschedule", args=[self.reservation.id]),
            self.payload(),
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "5 reservas activas")
        self.assertEqual(ReservationReschedule.objects.count(), 0)
