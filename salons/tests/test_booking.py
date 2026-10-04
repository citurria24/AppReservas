from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo
from django.conf import settings
from django.contrib.auth.hashers import check_password
from django.contrib.auth import get_user_model
from django.db import IntegrityError, transaction
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from unittest.mock import patch
from psycopg.types.range import Range
from salons.booking import available_slots
from salons.models import (
    Branch,
    BranchService,
    BookingLimitException,
    GuestVerification,
    HairSalon,
    Membership,
    Professional,
    ProfessionalBranch,
    ProfessionalService,
    Reservation,
    RewardProgram,
    RewardRedemption,
    ScheduleBreak,
    Service,
    WorkSchedule,
)


def next_weekday(weekday):
    candidate = timezone.localdate() + timedelta(days=1)
    while candidate.weekday() != weekday:
        candidate += timedelta(days=1)
    return candidate


class PublicBookingTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.salon = HairSalon.objects.create(name="Público", slug="publico")
        cls.other_salon = HairSalon.objects.create(name="Ajeno", slug="ajeno")
        cls.branch = Branch.objects.create(salon=cls.salon, name="Centro", address="Principal 1")
        cls.other_branch = Branch.objects.create(salon=cls.other_salon, name="Otra", address="Otra 2")
        cls.service = Service.objects.create(salon=cls.salon, name="Corte")
        cls.professional = Professional.objects.create(salon=cls.salon, display_name="Alex")
        ProfessionalBranch.objects.create(professional=cls.professional, branch=cls.branch)
        ProfessionalService.objects.create(professional=cls.professional, service=cls.service)
        BranchService.objects.create(branch=cls.branch, service=cls.service, duration_minutes=30)
        cls.day = next_weekday(0)
        cls.schedule = WorkSchedule.objects.create(
            professional=cls.professional,
            branch=cls.branch,
            weekday=0,
            starts_at=time(9),
            ends_at=time(18),
        )
        ScheduleBreak.objects.create(schedule=cls.schedule, starts_at=time(13), ends_at=time(14))
        cls.owner = get_user_model().objects.create_user("booking-owner", "booking.owner@example.test", "test-pass-123")
        Membership.objects.create(salon=cls.salon, user=cls.owner, role=Membership.Role.OWNER)

    def verify_guest(self):
        with patch("salons.views.secrets.randbelow", return_value=123456):
            response = self.client.post(
                reverse("guest-start", args=[self.salon.slug]),
                {"first_name": "Cliente", "last_name": "Demo", "email": "cliente@example.test", "contact": "099 123 456"},
            )
        self.assertRedirects(response, reverse("guest-verify", args=[self.salon.slug]))
        code = "123456"
        verification = GuestVerification.objects.get(email="cliente@example.test")
        self.assertTrue(check_password(code, verification.code_hash))
        response = self.client.post(reverse("guest-verify", args=[self.salon.slug]), {"code": code})
        self.assertRedirects(response, reverse("booking-create", args=[self.salon.slug]))

    def test_public_link_is_available_without_login(self):
        response = self.client.get(reverse("public-salon", args=[self.salon.slug]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Reservar un turno")
        self.assertContains(response, "Corte")

    def test_my_reservations_requires_a_verified_guest(self):
        response = self.client.get(reverse("my-reservations", args=[self.salon.slug]))
        self.assertRedirects(response, reverse("guest-start", args=[self.salon.slug]))

    def test_my_reservations_only_lists_verified_email_in_current_salon(self):
        starts = timezone.now() + timedelta(days=3)
        own_reservation = Reservation.objects.create(
            salon=self.salon,
            branch=self.branch,
            service=self.service,
            professional=self.professional,
            first_name="Cliente",
            last_name="Demo",
            email="CLIENTE@example.test",
            contact="099 123 456",
            starts_at=starts,
            ends_at=starts + timedelta(minutes=30),
            duration_minutes=30,
        )
        other_customer_service = Service.objects.create(salon=self.salon, name="Servicio de otra persona")
        Reservation.objects.create(
            salon=self.salon,
            branch=self.branch,
            service=other_customer_service,
            professional=self.professional,
            first_name="Otra",
            last_name="Persona",
            email="otra@example.test",
            contact="099 000 000",
            starts_at=starts + timedelta(hours=1),
            ends_at=starts + timedelta(hours=1, minutes=30),
            duration_minutes=30,
        )
        other_salon_service = Service.objects.create(salon=self.other_salon, name="Servicio de otra peluquería")
        other_salon_professional = Professional.objects.create(salon=self.other_salon, display_name="Profesional ajeno")
        Reservation.objects.create(
            salon=self.other_salon,
            branch=self.other_branch,
            service=other_salon_service,
            professional=other_salon_professional,
            first_name="Cliente",
            last_name="Demo",
            email="cliente@example.test",
            contact="099 123 456",
            starts_at=starts,
            ends_at=starts + timedelta(minutes=30),
            duration_minutes=30,
        )

        self.verify_guest()
        public_response = self.client.get(reverse("public-salon", args=[self.salon.slug]))
        response = self.client.get(reverse("my-reservations", args=[self.salon.slug]))

        self.assertContains(public_response, reverse("my-reservations", args=[self.salon.slug]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.service.name)
        self.assertContains(response, str(own_reservation.cancellation_token))
        self.assertNotContains(response, other_customer_service.name)
        self.assertNotContains(response, other_salon_service.name)

    def test_verified_session_cannot_be_reused_for_another_salon(self):
        self.verify_guest()
        response = self.client.get(reverse("my-reservations", args=[self.other_salon.slug]))
        self.assertRedirects(response, reverse("guest-start", args=[self.other_salon.slug]))

    def test_verified_guest_can_log_out_and_change_email(self):
        self.verify_guest()
        response = self.client.get(reverse("public-salon", args=[self.salon.slug]))
        self.assertContains(response, "Salir / cambiar correo")

        response = self.client.post(reverse("guest-logout", args=[self.salon.slug]))

        self.assertRedirects(response, reverse("public-salon", args=[self.salon.slug]))
        self.assertNotIn("verified_guest", self.client.session)
        response = self.client.get(reverse("booking-create", args=[self.salon.slug]))
        self.assertRedirects(response, reverse("guest-start", args=[self.salon.slug]))

    def test_guest_logout_is_post_only_and_does_not_clear_another_salon_session(self):
        self.verify_guest()
        response = self.client.get(reverse("guest-logout", args=[self.salon.slug]))
        self.assertEqual(response.status_code, 404)

        response = self.client.post(reverse("guest-logout", args=[self.other_salon.slug]))

        self.assertRedirects(response, reverse("public-salon", args=[self.other_salon.slug]))
        self.assertIn("verified_guest", self.client.session)

    def test_guest_email_verification_and_booking_flow(self):
        self.verify_guest()
        slots = available_slots(
            salon=self.salon,
            branch=self.branch,
            service=self.service,
            professional=self.professional,
            day=self.day,
        )
        selected = slots[0]
        response = self.client.post(
            reverse("booking-create", args=[self.salon.slug]),
            {
                "branch": self.branch.id,
                "service": self.service.id,
                "professional": self.professional.id,
                "date": self.day.isoformat(),
                "slot": selected.isoformat(),
                "notes": "Primera visita",
            },
        )
        self.assertRedirects(response, reverse("booking-success", args=[self.salon.slug]))
        reservation = Reservation.objects.get()
        self.assertEqual(reservation.email, "cliente@example.test")
        self.assertEqual(reservation.duration_minutes, 30)
        self.assertEqual(reservation.cancellation_notice_hours, self.salon.cancellation_notice_hours)

    def test_availability_does_not_cross_break_or_closing_time(self):
        slots = available_slots(
            salon=self.salon,
            branch=self.branch,
            service=self.service,
            professional=self.professional,
            day=self.day,
        )
        local_times = {timezone.localtime(slot).time() for slot in slots}
        self.assertIn(time(12, 30), local_times)
        self.assertNotIn(time(12, 45), local_times)
        self.assertNotIn(time(13, 0), local_times)
        self.assertIn(time(17, 30), local_times)
        self.assertNotIn(time(17, 45), local_times)

    def test_booking_form_rejects_objects_from_another_salon(self):
        self.verify_guest()
        response = self.client.post(
            reverse("booking-create", args=[self.salon.slug]),
            {
                "branch": self.other_branch.id,
                "service": self.service.id,
                "professional": self.professional.id,
                "date": self.day.isoformat(),
                "slot": "invalid",
                "notes": "",
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn("branch", response.context["form"].errors)
        self.assertEqual(Reservation.objects.count(), 0)

    def test_postgresql_constraint_rejects_professional_overlap(self):
        tz = ZoneInfo(settings.TIME_ZONE)
        starts = timezone.make_aware(datetime.combine(self.day, time(10)), tz)
        ends = starts + timedelta(minutes=30)
        base = {
            "salon": self.salon,
            "branch": self.branch,
            "service": self.service,
            "professional": self.professional,
            "first_name": "A",
            "last_name": "B",
            "contact": "099",
            "starts_at": starts,
            "ends_at": ends,
            "occupied_range": Range(starts, ends, bounds="[)"),
            "duration_minutes": 30,
        }
        Reservation.objects.bulk_create([Reservation(email="a@example.test", **base)])
        with self.assertRaises(IntegrityError), transaction.atomic():
            Reservation.objects.bulk_create([Reservation(email="b@example.test", **base)])

    def create_five_active_reservations(self):
        slots = available_slots(
            salon=self.salon,
            branch=self.branch,
            service=self.service,
            professional=self.professional,
            day=self.day,
        )
        selected = slots[::2][:6]
        for slot in selected[:5]:
            Reservation.objects.create(
                salon=self.salon,
                branch=self.branch,
                service=self.service,
                professional=self.professional,
                first_name="Cliente",
                last_name="Demo",
                email="cliente@example.test",
                contact="099 123 456",
                starts_at=slot,
                ends_at=slot + timedelta(minutes=30),
                duration_minutes=30,
            )
        return selected[5]

    def post_booking(self, selected):
        return self.client.post(
            reverse("booking-create", args=[self.salon.slug]),
            {
                "branch": self.branch.id,
                "service": self.service.id,
                "professional": self.professional.id,
                "date": self.day.isoformat(),
                "slot": selected.isoformat(),
                "notes": "Reserva adicional",
            },
        )

    def test_sixth_active_reservation_is_blocked_across_the_salon(self):
        selected = self.create_five_active_reservations()
        self.verify_guest()
        response = self.post_booking(selected)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Ya tenés cinco reservas activas")
        self.assertEqual(Reservation.objects.filter(email="cliente@example.test").count(), 5)

    def test_single_use_admin_exception_allows_sixth_reservation(self):
        selected = self.create_five_active_reservations()
        exception = BookingLimitException.objects.create(
            salon=self.salon,
            customer_email="cliente@example.test",
            booking_date=self.day,
            reason="Grupo familiar autorizado",
            created_by=self.owner,
        )
        self.verify_guest()
        response = self.post_booking(selected)
        self.assertRedirects(response, reverse("booking-success", args=[self.salon.slug]))
        exception.refresh_from_db()
        self.assertIsNotNone(exception.used_at)
        self.assertIsNotNone(exception.reservation_id)
        self.assertEqual(Reservation.objects.filter(email="cliente@example.test").count(), 6)

    def test_reward_is_applied_once_to_next_eligible_booking(self):
        RewardProgram.objects.create(
            salon=self.salon,
            active=True,
            services_required=2,
            period=RewardProgram.Period.MONTHLY,
            discount_percent=15,
        )
        local_tz = ZoneInfo(settings.TIME_ZONE)
        attended_day = timezone.localdate()
        for hour in (6, 7):
            starts = timezone.make_aware(datetime.combine(attended_day, time(hour)), local_tz)
            Reservation.objects.create(
                salon=self.salon,
                branch=self.branch,
                service=self.service,
                professional=self.professional,
                first_name="Cliente",
                last_name="Demo",
                email="cliente@example.test",
                contact="099 123 456",
                starts_at=starts,
                ends_at=starts + timedelta(minutes=30),
                duration_minutes=30,
                status=Reservation.Status.COMPLETED,
            )
        self.verify_guest()
        slots = available_slots(
            salon=self.salon,
            branch=self.branch,
            service=self.service,
            professional=self.professional,
            day=self.day,
        )
        response = self.post_booking(slots[0])
        self.assertRedirects(response, reverse("booking-success", args=[self.salon.slug]))
        rewarded = Reservation.objects.filter(status=Reservation.Status.CONFIRMED).latest("id")
        self.assertEqual(rewarded.reward_discount_percent, 15)
        redemption = RewardRedemption.objects.get()
        self.assertEqual(redemption.reservation, rewarded)

        remaining_slots = available_slots(
            salon=self.salon,
            branch=self.branch,
            service=self.service,
            professional=self.professional,
            day=self.day,
        )
        response = self.post_booking(remaining_slots[0])
        self.assertRedirects(response, reverse("booking-success", args=[self.salon.slug]))
        second = Reservation.objects.filter(status=Reservation.Status.CONFIRMED).latest("id")
        self.assertEqual(second.reward_discount_percent, 0)
        self.assertEqual(RewardRedemption.objects.count(), 1)
