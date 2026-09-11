import logging

from django.conf import settings
from django.core.mail import send_mail
from django.template.loader import render_to_string

logger = logging.getLogger(__name__)


def send_feature_request_notification(feature_request, admin_url):
    """
    Email the site owner about a new suggestion.

    Never raises — a mail outage must not cost the user their submission.
    """
    recipient = settings.FEATURE_REQUEST_NOTIFY_EMAIL
    if not recipient:
        return

    context = {"feature_request": feature_request, "admin_url": admin_url}
    subject = render_to_string("email/feature_request_subject.txt", context).strip()
    body = render_to_string("email/feature_request_body.txt", context)

    try:
        send_mail(
            subject,
            body,
            settings.DEFAULT_FROM_EMAIL,
            [recipient],
        )
    except Exception:
        logger.exception(
            "Failed to send feature request notification for %s",
            feature_request.pk,
        )
