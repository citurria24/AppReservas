from django.urls import reverse_lazy
from django.views.generic.edit import FormView

from .email_delivery import EmailDeliveryError
from .forms import StaffPasswordResetRequestForm


class StaffPasswordResetView(FormView):
    template_name = "registration/password_reset_form.html"
    form_class = StaffPasswordResetRequestForm
    success_url = reverse_lazy("password_reset_done")

    def form_valid(self, form):
        try:
            form.send_reset_email(self.request)
        except EmailDeliveryError:
            form.add_error(
                None,
                "No pudimos enviar el correo en este momento. Revisá los datos e intentá nuevamente.",
            )
            return self.form_invalid(form)
        return super().form_valid(form)
