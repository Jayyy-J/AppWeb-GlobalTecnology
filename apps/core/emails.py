"""Envío de emails con plantillas HTML de marca. Nunca rompe el flujo si el SMTP falla."""
import logging

from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string
from django.utils.html import strip_tags

logger = logging.getLogger("emails")


def send_templated(template: str, subject: str, to, context: dict | None = None, attachments=None) -> bool:
    from apps.storefront.models import StoreSettings

    if isinstance(to, str):
        to = [to]
    to = [t for t in to if t]
    if not to:
        return False
    ctx = {"tienda": StoreSettings.load(), "SITE_URL": settings.SITE_URL, **(context or {})}
    try:
        html = render_to_string(f"emails/{template}.html", ctx)
        text = strip_tags(html)
        msg = EmailMultiAlternatives(subject, text, settings.DEFAULT_FROM_EMAIL, to)
        msg.attach_alternative(html, "text/html")
        for att in attachments or []:
            msg.attach(*att)
        msg.send(fail_silently=False)
        logger.info("email_enviado plantilla=%s destino=%s", template, ",".join(to))
        return True
    except Exception:
        logger.exception("email_fallido plantilla=%s destino=%s", template, ",".join(to))
        return False
