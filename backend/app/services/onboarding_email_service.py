"""Onboarding email service — sends welcome and lifecycle emails via EmailService."""

import logging

logger = logging.getLogger(__name__)


async def send_onboarding_email(db, user, email_type: str) -> None:
    """Send an onboarding email to a user via the email delivery service.

    Uses the existing EmailService (Resend API with SMTP fallback).
    If no email provider is configured, logs a warning and continues gracefully.
    """
    try:
        from app.services.email_service import get_email_service

        service = get_email_service()

        template_map = {
            "welcome": "welcome",
        }
        template_name = template_map.get(email_type)
        if not template_name:
            logger.warning(f"Unknown onboarding email type: {email_type}")
            return

        name = (
            getattr(user, "full_name", None)
            or getattr(user, "username", None)
            or getattr(user, "email", "").split("@")[0]
            or "there"
        )

        result = await service.send_email(
            to=user.email,
            template_name=template_name,
            variables={"name": name},
        )

        if result:
            logger.info(f"Sent {email_type} email to {user.email}")
        else:
            logger.warning(
                f"Could not send {email_type} email to {user.email} — "
                "no email provider configured (set RESEND_API_KEY or SMTP_* env vars)"
            )
    except Exception as e:
        logger.warning(
            f"Failed to send onboarding email to {getattr(user, 'email', 'unknown')}: {e}"
        )
