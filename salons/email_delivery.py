from django.template.loader import render_to_string
from django.urls import reverse
from django.utils import timezone

from accounts.email_delivery import send_templated_email


def send_guest_verification_email(*, salon, email, code, expires_minutes=15):
    context = {
        "salon": salon,
        "code": code,
        "expires_minutes": expires_minutes,
    }
    subject = render_to_string("emails/guest_verification_subject.txt", context).strip().replace("\n", " ")
    send_templated_email(
        subject=subject,
        to=email,
        text_template="emails/guest_verification_body.txt",
        html_template="emails/guest_verification_body.html",
        context=context,
    )


def send_reservation_confirmation_email(*, request, reservation):
    context = {
        "reservation": reservation,
        "salon": reservation.salon,
        "local_start": timezone.localtime(reservation.starts_at),
        "cancellation_url": request.build_absolute_uri(
            reverse(
                "client-cancel",
                args=[reservation.salon.slug, reservation.cancellation_token],
            )
        ),
    }
    subject = render_to_string("emails/reservation_confirmation_subject.txt", context).strip().replace("\n", " ")
    send_templated_email(
        subject=subject,
        to=reservation.email,
        text_template="emails/reservation_confirmation_body.txt",
        html_template="emails/reservation_confirmation_body.html",
        context=context,
    )
