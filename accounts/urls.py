from django.contrib.auth import views as auth_views
from django.urls import path
from django.views.generic import TemplateView

from .views import StaffPasswordResetView


urlpatterns = [
    path("recuperar/", StaffPasswordResetView.as_view(), name="password_reset"),
    path(
        "recuperar/enviado/",
        TemplateView.as_view(template_name="registration/password_reset_done.html"),
        name="password_reset_done",
    ),
    path(
        "restablecer/<uidb64>/<token>/",
        auth_views.PasswordResetConfirmView.as_view(
            template_name="registration/password_reset_confirm.html",
            success_url="/cuenta/restablecer/completo/",
        ),
        name="password_reset_confirm",
    ),
    path(
        "restablecer/completo/",
        TemplateView.as_view(template_name="registration/password_reset_complete.html"),
        name="password_reset_complete",
    ),
]
