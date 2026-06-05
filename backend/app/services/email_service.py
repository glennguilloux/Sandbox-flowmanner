"""
Email Delivery Service

Sends transactional emails via Resend API (or SMTP fallback).
Templates for: welcome, mission completed/failed, 2FA, team invite, password reset.
"""

import logging
from string import Template

import httpx

logger = logging.getLogger(__name__)

# ── Email Templates ────────────────────────────────────────────────────────

TEMPLATES = {
    "welcome": {
        "subject": "Welcome to Flowmanner!",
        "html": """
<h1>Welcome to Flowmanner, ${name}!</h1>
<p>Your account has been created successfully.</p>
<p>Here's what you can do:</p>
<ul>
<li>Create AI-powered missions</li>
<li>Build workflow graphs</li>
<li>Collaborate with your team</li>
</ul>
<p>Get started by creating your first mission!</p>
<p>— The Flowmanner Team</p>
""",
    },
    "mission_completed": {
        "subject": "Mission Completed: ${mission_name}",
        "html": """
<h2>Mission Completed</h2>
<p>Your mission <strong>${mission_name}</strong> has completed successfully.</p>
<p><strong>Duration:</strong> ${duration}</p>
<p><strong>Tasks completed:</strong> ${tasks_completed}</p>
<p><a href="${dashboard_url}/missions/${mission_id}">View Mission</a></p>
<p>— Flowmanner</p>
""",
    },
    "mission_failed": {
        "subject": "Mission Failed: ${mission_name}",
        "html": """
<h2>Mission Failed</h2>
<p>Your mission <strong>${mission_name}</strong> has failed.</p>
<p><strong>Error:</strong> ${error_message}</p>
<p><a href="${dashboard_url}/missions/${mission_id}">View Details</a></p>
<p>— Flowmanner</p>
""",
    },
    "two_fa_code": {
        "subject": "Your Flowmanner Verification Code",
        "html": """
<h2>Verification Code</h2>
<p>Your verification code is:</p>
<h1 style="font-size: 32px; letter-spacing: 8px; text-align: center; padding: 20px; background: #f0f0f0; border-radius: 8px;">${code}</h1>
<p>This code expires in ${expires_minutes} minutes.</p>
<p>If you didn't request this, please ignore this email.</p>
<p>— Flowmanner</p>
""",
    },
    "team_invitation": {
        "subject": "You've been invited to join ${team_name} on Flowmanner",
        "html": """
<h2>Team Invitation</h2>
<p>${inviter_name} has invited you to join <strong>${team_name}</strong> on Flowmanner.</p>
<p><a href="${invite_url}" style="display: inline-block; padding: 12px 24px; background: #6366f1; color: white; text-decoration: none; border-radius: 8px;">Accept Invitation</a></p>
<p>This invitation expires in 7 days.</p>
<p>— Flowmanner</p>
""",
    },
    "password_reset": {
        "subject": "Reset Your Flowmanner Password",
        "html": """
<h2>Password Reset</h2>
<p>You requested a password reset for your Flowmanner account.</p>
<p><a href="${reset_url}" style="display: inline-block; padding: 12px 24px; background: #6366f1; color: white; text-decoration: none; border-radius: 8px;">Reset Password</a></p>
<p>This link expires in ${expires_hours} hours.</p>
<p>If you didn't request this, please ignore this email.</p>
<p>— Flowmanner</p>
""",
    },
    "marketplace_approved": {
        "subject": "Your listing has been approved: ${listing_name}",
        "html": """
<h2>Listing Approved</h2>
<p>Your marketplace listing <strong>${listing_name}</strong> has been approved and is now live!</p>
<p><a href="${marketplace_url}/listings/${listing_id}">View Listing</a></p>
<p>— Flowmanner Marketplace</p>
""",
    },
    "marketplace_rejected": {
        "subject": "Your listing needs changes: ${listing_name}",
        "html": """
<h2>Listing Needs Changes</h2>
<p>Your marketplace listing <strong>${listing_name}</strong> was not approved.</p>
<p><strong>Reason:</strong> ${rejection_reason}</p>
<p>Please update your listing and resubmit.</p>
<p><a href="${marketplace_url}/listings/${listing_id}/edit">Edit Listing</a></p>
<p>— Flowmanner Marketplace</p>
""",
    },
    "data_export_ready": {
        "subject": "Your Flowmanner data export is ready",
        "html": """
<h2>Data Export Ready</h2>
<p>Your data export is ready for download.</p>
<p><a href="${download_url}" style="display: inline-block; padding: 12px 24px; background: #6366f1; color: white; text-decoration: none; border-radius: 8px;">Download Export</a></p>
<p>This link expires in ${expires_hours} hours.</p>
<p>— Flowmanner</p>
""",
    },
    "digest": {
        "subject": "Your Flowmanner Daily Digest — ${date}",
        "html": """
<h2>Daily Digest</h2>
<p>Here's your ${date} summary:</p>
<ul>
<li>Missions completed: ${missions_completed}</li>
<li>Missions failed: ${missions_failed}</li>
<li>Active agents: ${active_agents}</li>
</ul>
<p><a href="${dashboard_url}">View Dashboard</a></p>
<p>— Flowmanner</p>
""",
    },
}


class EmailService:
    """Sends transactional emails."""

    def __init__(
        self,
        api_key: str | None = None,
        from_email: str = "noreply@flowmanner.com",
        from_name: str = "Flowmanner",
        smtp_host: str | None = None,
        smtp_port: int = 587,
        smtp_username: str | None = None,
        smtp_password: str | None = None,
    ):
        self._api_key = api_key
        self._from_email = from_email
        self._from_name = from_name
        self._smtp_host = smtp_host
        self._smtp_port = smtp_port
        self._smtp_username = smtp_username
        self._smtp_password = smtp_password
        self._http_client: httpx.AsyncClient | None = None

    async def _get_client(self) -> httpx.AsyncClient:
        if self._http_client is None or self._http_client.is_closed:
            self._http_client = httpx.AsyncClient(timeout=30)
        return self._http_client

    async def close(self):
        if self._http_client and not self._http_client.is_closed:
            await self._http_client.aclose()

    async def send_email(
        self,
        to: str,
        template_name: str,
        variables: dict,
        reply_to: str | None = None,
    ) -> bool:
        """Send an email using a named template."""
        template = TEMPLATES.get(template_name)
        if not template:
            logger.error(f"Unknown email template: {template_name}")
            return False

        subject = Template(template["subject"]).safe_substitute(variables)
        html = Template(template["html"]).safe_substitute(variables)

        return await self._send(to=to, subject=subject, html=html, reply_to=reply_to)

    async def send_raw(
        self,
        to: str,
        subject: str,
        html: str,
        reply_to: str | None = None,
    ) -> bool:
        """Send a raw HTML email."""
        return await self._send(to=to, subject=subject, html=html, reply_to=reply_to)

    async def _send(
        self,
        to: str,
        subject: str,
        html: str,
        reply_to: str | None = None,
    ) -> bool:
        """Send email via Resend API or SMTP fallback."""
        if self._api_key:
            return await self._send_via_resend(to, subject, html, reply_to)
        elif self._smtp_host:
            return await self._send_via_smtp(to, subject, html, reply_to)
        else:
            logger.warning(
                "No email provider configured (no RESEND_API_KEY or SMTP_HOST)"
            )
            return False

    async def _send_via_resend(
        self,
        to: str,
        subject: str,
        html: str,
        reply_to: str | None = None,
    ) -> bool:
        """Send via Resend API."""
        client = await self._get_client()
        payload = {
            "from": f"{self._from_name} <{self._from_email}>",
            "to": [to],
            "subject": subject,
            "html": html,
        }
        if reply_to:
            payload["reply_to"] = reply_to

        try:
            resp = await client.post(
                "https://api.resend.com/emails",
                json=payload,
                headers={
                    "Authorization": f"Bearer {self._api_key}",
                    "Content-Type": "application/json",
                },
            )
            if resp.status_code == 200:
                logger.info(f"Email sent to {to}: {subject}")
                return True
            else:
                logger.error(f"Resend API error: {resp.status_code} — {resp.text}")
                return False
        except Exception as e:
            logger.error(f"Failed to send email via Resend: {e}")
            return False

    async def _send_via_smtp(
        self,
        to: str,
        subject: str,
        html: str,
        reply_to: str | None = None,
    ) -> bool:
        """Send via SMTP (synchronous, wrapped in executor)."""
        import asyncio
        import smtplib
        from email.mime.multipart import MIMEMultipart
        from email.mime.text import MIMEText

        def _send():
            msg = MIMEMultipart("alternative")
            msg["Subject"] = subject
            msg["From"] = f"{self._from_name} <{self._from_email}>"
            msg["To"] = to
            if reply_to:
                msg["Reply-To"] = reply_to

            msg.attach(MIMEText(html, "html"))

            with smtplib.SMTP(self._smtp_host, self._smtp_port) as server:
                server.starttls()
                if self._smtp_username and self._smtp_password:
                    server.login(self._smtp_username, self._smtp_password)
                server.send_message(msg)

        try:
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(None, _send)
            logger.info(f"Email sent via SMTP to {to}: {subject}")
            return True
        except Exception as e:
            logger.error(f"Failed to send email via SMTP: {e}")
            return False


# ── Singleton ──────────────────────────────────────────────────────────────

_email_service: EmailService | None = None


def get_email_service() -> EmailService:
    """Get or create the email service singleton."""
    global _email_service
    if _email_service is None:
        from app.config import settings

        _email_service = EmailService(
            api_key=getattr(settings, "RESEND_API_KEY", None),
            from_email=getattr(settings, "EMAIL_FROM", "noreply@flowmanner.com"),
            from_name=getattr(settings, "EMAIL_FROM_NAME", "Flowmanner"),
            smtp_host=getattr(settings, "SMTP_HOST", None),
            smtp_port=getattr(settings, "SMTP_PORT", 587),
            smtp_username=getattr(settings, "SMTP_USERNAME", None),
            smtp_password=getattr(settings, "SMTP_PASSWORD", None),
        )
    return _email_service


async def send_notification_email(
    user_email: str,
    template_name: str,
    variables: dict,
) -> bool:
    """Convenience function to send a notification email."""
    service = get_email_service()
    return await service.send_email(
        to=user_email,
        template_name=template_name,
        variables=variables,
    )
