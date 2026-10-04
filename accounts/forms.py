from django import forms
from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.tokens import default_token_generator
from django.contrib.sites.shortcuts import get_current_site
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode

from .email_delivery import send_templated_email


class StaffPasswordResetRequestForm(forms.Form):
    email = forms.EmailField(label="Correo electrónico")

    def send_reset_email(self, request):
        email = self.cleaned_data["email"].strip().lower()
        user = (
            get_user_model()
            ._default_manager.filter(email__iexact=email, is_active=True)
            .order_by("pk")
            .first()
        )
        if user and not user.has_usable_password():
            user = None

        common_context = {
            "site_name": get_current_site(request).name,
            "requested_email": email,
        }
        if user:
            uid = urlsafe_base64_encode(force_bytes(user.pk))
            token = default_token_generator.make_token(user)
            reset_path = reverse("password_reset_confirm", kwargs={"uidb64": uid, "token": token})
            context = {
                **common_context,
                "user": user,
                "reset_url": request.build_absolute_uri(reset_path),
                "timeout_minutes": max(1, settings.PASSWORD_RESET_TIMEOUT // 60),
            }
            subject = render_to_string("emails/password_reset_subject.txt", context).strip().replace("\n", " ")
            text_template = "emails/password_reset_body.txt"
            html_template = "emails/password_reset_body.html"
        else:
            context = common_context
            subject = render_to_string("emails/password_reset_subject.txt", context).strip().replace("\n", " ")
            text_template = "emails/password_reset_unknown_body.txt"
            html_template = "emails/password_reset_unknown_body.html"

        send_templated_email(
            subject=subject,
            to=email,
            text_template=text_template,
            html_template=html_template,
            context=context,
        )
