"""
Sentry Webhook Endpoint

Receives webhook events from Sentry when users configure their Sentry projects
to send alerts to Flowmanner.

Webhook URL: POST /api/sentry/webhook

Sentry sends webhook payloads for:
- issue (created, resolved, ignored, assigned)
- event_alert
- metric_alert

The payload structure depends on the Sentry version and configuration.
Sentry webhooks do NOT include HMAC signatures by default — verification
relies on a shared secret passed as a query parameter or header.
"""

import hashlib
import hmac
import json
import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_db

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/sentry", tags=["sentry"])


def _verify_sentry_webhook(body: bytes, signature: str | None) -> bool:
    """
    Verify Sentry webhook signature.

    Sentry signs webhooks with HMAC-SHA256 using the webhook signing secret.
    The signature is in the 'X-Sentry-Signature' header (hex digest).

    If no signing secret is configured, allow through (for initial setup/testing).
    """
    secret = settings.SENTRY_WEBHOOK_SECRET
    if not secret:
        logger.warning("SENTRY_WEBHOOK_SECRET not configured — accepting unsigned webhook")
        return True

    if not signature:
        return False

    expected = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature)


@router.post("/webhook")
async def sentry_webhook(
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """Receive webhook events from Sentry."""
    body = await request.body()

    signature = request.headers.get("X-Sentry-Signature", "")
    if not _verify_sentry_webhook(body, signature if signature else None):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid signature")

    try:
        payload = json.loads(body)
    except json.JSONDecodeError:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid JSON")

    # Sentry webhook payload structure:
    # {
    #   "action": "created" | "resolved" | ...,
    #   "actor": { "id", "type", "name" },
    #   "data": { "issue": { "id", "title", "culprit", "level", ... } },
    #   ... (structure varies by event type)
    # }

    action = payload.get("action", "")
    data = payload.get("data", {})
    issue = data.get("issue", {})

    logger.info("Sentry webhook: action=%s issue_id=%s", action, issue.get("id", "N/A"))

    # Store the event for agent context / trigger agent workflow
    # This is where we'd trigger the "autonomous on-call" workflow:
    # 1. Agent receives the Sentry error
    # 2. Agent fetches the full stack trace via sentry_get_latest_event
    # 3. Agent creates a Linear issue with the analysis
    # 4. Agent notifies the team

    if action in ("created", "regression"):
        await _handle_new_or_regressed_error(db, issue)

    return {"status": "ok", "action": action}


async def _handle_new_or_regressed_error(db: AsyncSession, issue: dict[str, Any]):
    """Process a new or regressed Sentry error → trigger agent workflow."""
    issue_id = issue.get("id")
    title = issue.get("title", "Unknown error")
    culprit = issue.get("culprit", "")
    level = issue.get("level", "error")

    logger.info(
        "Sentry error for agent triage: [%s] %s in %s (issue %s)",
        level,
        title,
        culprit,
        issue_id,
    )

    # TODO: Trigger agent workflow when the agent-trigger infrastructure is ready.
    # For now, just log it. The agent can also poll for issues proactively
    # via the sentry_list_issues tool.
