import re
from datetime import datetime, timedelta
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.contrib.auth.tokens import default_token_generator
from django.core.mail.backends.base import BaseEmailBackend
from django.test import TestCase, override_settings
from django.urls import reverse


class FailingEmailBackend(BaseEmailBackend):
    def send_messages(self, email_messages):
        raise OSError("SMTP no disponible")


@override_settings(
    EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
    PASSWORD_RESET_TIMEOUT=3600,
)
class StaffPasswordResetTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = get_user_model().objects.create_user(
            username="personal",
            email="personal@example.test",
            password="ClaveAnterior2026!",
            first_name="Persona",
        )

    def request_reset(self, email="personal@example.test"):
        return self.client.post(reverse("password_reset"), {"email": email})

    def reset_path_from_last_email(self):
        from django.core import mail

        match = re.search(r"http://testserver(?P<path>/cuenta/restablecer/[^\s<]+)", mail.outbox[-1].body)
        self.assertIsNotNone(match)
        return match.group("path")

    def test_existing_and_unknown_accounts_have_the_same_http_response(self):
        existing = self.request_reset()
        unknown = self.request_reset("desconocido@example.test")

        self.assertEqual(existing.status_code, 302)
        self.assertEqual(unknown.status_code, 302)
        self.assertEqual(existing.url, reverse("password_reset_done"))
        self.assertEqual(existing.url, unknown.url)

    def test_reset_email_has_text_and_html_and_token_is_single_use(self):
        from django.core import mail

        response = self.request_reset()
        self.assertRedirects(response, reverse("password_reset_done"))
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].alternatives[0].mimetype, "text/html")
        reset_path = self.reset_path_from_last_email()

        first_open = self.client.get(reset_path)
        self.assertEqual(first_open.status_code, 302)
        set_password_path = first_open.url
        response = self.client.post(
            set_password_path,
            {
                "new_password1": "ClaveNuevaMuySegura2026!",
                "new_password2": "ClaveNuevaMuySegura2026!",
            },
        )
        self.assertRedirects(response, reverse("password_reset_complete"))
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password("ClaveNuevaMuySegura2026!"))

        reused = self.client.get(reset_path)
        self.assertEqual(reused.status_code, 200)
        self.assertContains(reused, "El enlace ya no está disponible")

    def test_expired_token_is_rejected(self):
        old_time = datetime.now() - timedelta(hours=2)
        with patch.object(default_token_generator, "_now", return_value=old_time):
            self.request_reset()
        reset_path = self.reset_path_from_last_email()

        response = self.client.get(reset_path)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "El enlace ya no está disponible")

    @override_settings(EMAIL_BACKEND="accounts.tests.test_password_reset.FailingEmailBackend")
    def test_delivery_failure_is_controlled_for_existing_and_unknown_accounts(self):
        existing = self.request_reset()
        unknown = self.request_reset("desconocido@example.test")

        self.assertEqual(existing.status_code, 200)
        self.assertEqual(unknown.status_code, 200)
        error = "No pudimos enviar el correo en este momento"
        self.assertContains(existing, error)
        self.assertContains(unknown, error)
        self.assertNotContains(existing, "Revisá tu correo")
        self.assertNotContains(unknown, "Revisá tu correo")
