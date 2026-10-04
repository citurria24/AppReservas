from datetime import time, timedelta

from django.db import connection
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from salons.booking import available_slots
from salons.cancellation_policy import active_cancellation_booking_block
from salons.models import (
    Branch,
    BranchService,
    HairSalon,
    Professional,
    ProfessionalBranch,
    ProfessionalService,
    Reservation,
    Service,
    WorkSchedule,
)


class CancellationBookingBlockTests(TestCase):
    customer_email = "bloqueo@example.test"

    @classmethod
    def setUpTestData(cls):
        cls.salon = HairSalon.objects.create(name="Política de bloqueos", slug="bloqueos")
        cls.branch = Branch.objects.create(
            salon=cls.salon,
            name="Centro",
            address="Principal 123",
            phone="2900 1234",
        )
        cls.service = Service.objects.create(salon=cls.salon, name="Corte")
        cls.professional = Professional.objects.create(salon=cls.salon, display_name="Alex")
        ProfessionalBranch.objects.create(professional=cls.professional, branch=cls.branch)
        ProfessionalService.objects.create(professional=cls.professional, service=cls.service)
        BranchService.objects.create(branch=cls.branch, service=cls.service, duration_minutes=30)

        cls.booking_day = timezone.localdate() + timedelta(days=1)
        while cls.booking_day.weekday() != 0:
            cls.booking_day += timedelta(days=1)
        WorkSchedule.objects.create(
            professional=cls.professional,
            branch=cls.branch,
            weekday=0,
            starts_at=time(9),
            ends_at=time(12),
        )

        cls.other_salon = HairSalon.objects.create(name="Otra peluquería", slug="otra-peluqueria")
        cls.other_branch = Branch.objects.create(
            salon=cls.other_salon,
            name="Otra sucursal",
            address="Secundaria 456",
            phone="2400 9999",
        )
        cls.other_service = Service.objects.create(salon=cls.other_salon, name="Otro corte")
        cls.other_professional = Professional.objects.create(
            salon=cls.other_salon,
            display_name="Otra profesional",
        )

    def setUp(self):
        self.assertEqual(connection.vendor, "postgresql")

    def create_cancellation(self, *, cancelled_at, salon=None, status=None):
        salon = salon or self.salon
        if salon == self.salon:
            branch, service, professional = self.branch, self.service, self.professional
        else:
            branch, service, professional = (
                self.other_branch,
                self.other_service,
                self.other_professional,
            )
        starts_at = timezone.now() + timedelta(days=10)
        return Reservation.objects.create(
            salon=salon,
            branch=branch,
            service=service,
            professional=professional,
            first_name="Cliente",
            last_name="Bloqueo",
            email=self.customer_email,
            contact="099 111 222",
            starts_at=starts_at,
            ends_at=starts_at + timedelta(minutes=30),
            duration_minutes=30,
            status=status or Reservation.Status.CANCELLED_CLIENT,
            cancelled_at=cancelled_at,
        )

    def verify_guest_session(self):
        session = self.client.session
        session["verified_guest"] = {
            "salon_id": self.salon.id,
            "first_name": "Cliente",
            "last_name": "Bloqueo",
            "email": self.customer_email,
            "contact": "099 111 222",
            "verified_at": timezone.now().isoformat(),
        }
        session.save()

    def booking_payload(self):
        selected = available_slots(
            salon=self.salon,
            branch=self.branch,
            service=self.service,
            professional=self.professional,
            day=self.booking_day,
        )[0]
        return {
            "branch": self.branch.id,
            "service": self.service.id,
            "professional": self.professional.id,
            "date": self.booking_day.isoformat(),
            "slot": selected.isoformat(),
            "notes": "",
        }

    def test_one_and_two_client_cancellations_do_not_block(self):
        now = timezone.now()
        self.create_cancellation(cancelled_at=now - timedelta(hours=2))
        self.assertIsNone(
            active_cancellation_booking_block(
                salon=self.salon,
                customer_email=self.customer_email,
                now=now,
            )
        )
        self.create_cancellation(cancelled_at=now - timedelta(hours=1))
        self.assertIsNone(
            active_cancellation_booking_block(
                salon=self.salon,
                customer_email=self.customer_email,
                now=now,
            )
        )

    def test_third_client_cancellation_within_thirty_days_blocks_for_24_hours(self):
        now = timezone.now()
        for hours_ago in (72, 48, 1):
            self.create_cancellation(cancelled_at=now - timedelta(hours=hours_ago))

        block = active_cancellation_booking_block(
            salon=self.salon,
            customer_email=self.customer_email,
            now=now,
        )

        self.assertIsNotNone(block)
        self.assertEqual(block.unlocks_at, now + timedelta(hours=23))

    def test_salon_cancellation_does_not_count(self):
        now = timezone.now()
        self.create_cancellation(cancelled_at=now - timedelta(hours=3))
        self.create_cancellation(cancelled_at=now - timedelta(hours=2))
        self.create_cancellation(
            cancelled_at=now - timedelta(hours=1),
            status=Reservation.Status.CANCELLED_SALON,
        )

        self.assertIsNone(
            active_cancellation_booking_block(
                salon=self.salon,
                customer_email=self.customer_email,
                now=now,
            )
        )

    def test_cancellation_older_than_thirty_days_does_not_count(self):
        now = timezone.now()
        for age in (timedelta(days=31), timedelta(hours=2), timedelta(hours=1)):
            self.create_cancellation(cancelled_at=now - age)

        self.assertIsNone(
            active_cancellation_booking_block(
                salon=self.salon,
                customer_email=self.customer_email,
                now=now,
            )
        )

    def test_active_block_prevents_booking(self):
        now = timezone.now()
        for hours_ago in (3, 2, 1):
            self.create_cancellation(cancelled_at=now - timedelta(hours=hours_ago))
        self.verify_guest_session()

        response = self.client.post(
            reverse("booking-create", args=[self.salon.slug]),
            self.booking_payload(),
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "No podés crear una nueva reserva")
        self.assertFalse(
            Reservation.objects.filter(
                salon=self.salon,
                email=self.customer_email,
                status=Reservation.Status.CONFIRMED,
            ).exists()
        )

    def test_expired_block_allows_booking_without_erasing_history(self):
        now = timezone.now()
        for hours_ago in (27, 26, 25):
            self.create_cancellation(cancelled_at=now - timedelta(hours=hours_ago))
        self.verify_guest_session()

        response = self.client.post(
            reverse("booking-create", args=[self.salon.slug]),
            self.booking_payload(),
        )

        self.assertRedirects(response, reverse("booking-success", args=[self.salon.slug]))
        self.assertEqual(
            Reservation.objects.filter(
                salon=self.salon,
                email=self.customer_email,
                status=Reservation.Status.CANCELLED_CLIENT,
            ).count(),
            3,
        )

    def test_cancellations_are_isolated_between_salons(self):
        now = timezone.now()
        for hours_ago in (3, 2, 1):
            self.create_cancellation(cancelled_at=now - timedelta(hours=hours_ago))

        self.assertIsNotNone(
            active_cancellation_booking_block(
                salon=self.salon,
                customer_email=self.customer_email,
                now=now,
            )
        )
        self.assertIsNone(
            active_cancellation_booking_block(
                salon=self.other_salon,
                customer_email=self.customer_email,
                now=now,
            )
        )

    def test_block_page_shows_exact_unlock_time_and_triggering_branch_phone(self):
        now = timezone.now()
        for hours_ago in (3, 2, 1):
            self.create_cancellation(cancelled_at=now - timedelta(hours=hours_ago))
        expected_unlock = timezone.localtime(now + timedelta(hours=23))
        self.verify_guest_session()

        response = self.client.get(reverse("booking-create", args=[self.salon.slug]))

        self.assertContains(response, expected_unlock.strftime("%d/%m/%Y"))
        self.assertContains(response, expected_unlock.strftime("%H:%M"))
        self.assertContains(response, self.branch.phone)
