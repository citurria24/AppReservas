from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string


class EmailDeliveryError(Exception):
    """Error controlado al entregar un correo transaccional."""


def send_templated_email(*, subject, to, text_template, html_template, context):
    text_body = render_to_string(text_template, context)
    html_body = render_to_string(html_template, context)
    message = EmailMultiAlternatives(subject=subject, body=text_body, to=[to])
    message.attach_alternative(html_body, "text/html")
    try:
        delivered = message.send(fail_silently=False)
    except Exception as exc:
        raise EmailDeliveryError("El servidor de correo no pudo entregar el mensaje.") from exc
    if delivered != 1:
        raise EmailDeliveryError("El servidor de correo no confirmó la entrega del mensaje.")
