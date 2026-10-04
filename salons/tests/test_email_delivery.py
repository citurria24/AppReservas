import re
from datetime import time, timedelta
from unittest.mock import patch

from django.core.mail.backends.base import BaseEmailBackend
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from accounts.email_delivery import EmailDeliveryError
from salons.booking import available_slots
from salons.models import (
    Branch,
    BranchService,
    GuestVerification,
    HairSalon,
    Professional,
    ProfessionalBranch,
    ProfessionalService,
    Reservation,
    Service,
    WorkSchedule,
)


class FailingEmailBackend(BaseEmailBackend):
    def send_messages(self, email_messages):
        raise OSError("SMTP no disponible")


@override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend", DEBUG=False)
class GuestVerificationEmailTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.salon = HairSalon.objects.create(name="Correo", slug="correo")

    def request_code(self):
        return self.client.post(
            reverse("guest-start", args=[self.salon.slug]),
            {
                "first_name": "Cliente",
                "last_name": "Correo",
                "email": "cliente@example.test",
                "contact": "099 123 456",
            },
        )

    def code_from_email(self):
        from django.core import mail

        match = re.search(r"\b\d{6}\b", mail.outbox[-1].body)
        self.assertIsNotNone(match)
        return match.group(0)

    def test_code_is_sent_as_text_and_html_but_not_rendered_with_debug_disabled(self):
        from django.core import mail

        response = self.request_code()
        code = self.code_from_email()

        self.assertRedirects(response, reverse("guest-verify", args=[self.salon.slug]))
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].alternatives[0].mimetype, "text/html")
        verification_page = self.client.get(reverse("guest-verify", args=[self.salon.slug]))
        self.assertNotContains(verification_page, code)
        self.assertNotIn("debug_verification_code", self.client.session)

    def test_expired_code_is_rejected(self):
        self.request_code()
        code = self.code_from_email()
        GuestVerification.objects.update(expires_at=timezone.now() - timedelta(seconds=1))

        response = self.client.post(reverse("guest-verify", args=[self.salon.slug]), {"code": code})

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "El código es incorrecto, venció")
        self.assertIsNone(GuestVerification.objects.get().verified_at)

    def test_code_cannot_be_used_twice(self):
        self.request_code()
        code = self.code_from_email()
        pending = self.client.session["pending_guest"]
        first = self.client.post(reverse("guest-verify", args=[self.salon.slug]), {"code": code})
        self.assertRedirects(first, reverse("booking-create", args=[self.salon.slug]))

        session = self.client.session
        session["pending_guest"] = pending
        session.save()
        second = self.client.post(reverse("guest-verify", args=[self.salon.slug]), {"code": code})

        self.assertEqual(second.status_code, 200)
        self.assertContains(second, "El código es incorrecto, venció")

    @override_settings(EMAIL_BACKEND="salons.tests.test_email_delivery.FailingEmailBackend")
    def test_delivery_failure_keeps_the_form_and_does_not_persist_a_code(self):
        response = self.request_code()

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "No pudimos enviar el código")
        self.assertEqual(GuestVerification.objects.count(), 0)
        self.assertNotIn("pending_guest", self.client.session)


@override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
class ReservationConfirmationFailureTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.salon = HairSalon.objects.create(name="Confirmación", slug="confirmacion")
        cls.branch = Branch.objects.create(salon=cls.salon, name="Centro", address="Calle 1")
        cls.service = Service.objects.create(salon=cls.salon, name="Corte")
        cls.professional = Professional.objects.create(salon=cls.salon, display_name="Alex")
        ProfessionalBranch.objects.create(professional=cls.professional, branch=cls.branch)
        ProfessionalService.objects.create(professional=cls.professional, service=cls.service)
        BranchService.objects.create(branch=cls.branch, service=cls.service, duration_minutes=30)
        candidate = timezone.localdate() + timedelta(days=1)
        while candidate.weekday() != 0:
            candidate += timedelta(days=1)
        cls.day = candidate
        WorkSchedule.objects.create(
            professional=cls.professional,
            branch=cls.branch,
            weekday=0,
            starts_at=time(9),
            ends_at=time(12),
        )

    def setUp(self):
        session = self.client.session
        session["verified_guest"] = {
            "salon_id": self.salon.id,
            "first_name": "Cliente",
            "last_name": "Demo",
            "email": "cliente@example.test",
            "contact": "099 123 456",
            "verified_at": timezone.now().isoformat(),
        }
        session.save()

    def test_confirmation_failure_rolls_back_the_reservation(self):
        selected = available_slots(
            salon=self.salon,
            branch=self.branch,
            service=self.service,
            professional=self.professional,
            day=self.day,
        )[0]
        with patch(
            "salons.views.send_reservation_confirmation_email",
            side_effect=EmailDeliveryError("falló"),
        ):
            response = self.client.post(
                reverse("booking-create", args=[self.salon.slug]),
                {
                    "branch": self.branch.id,
                    "service": self.service.id,
                    "professional": self.professional.id,
                    "date": self.day.isoformat(),
                    "slot": selected.isoformat(),
                    "notes": "",
                },
            )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "La reserva no fue creada")
        self.assertEqual(Reservation.objects.count(), 0)
