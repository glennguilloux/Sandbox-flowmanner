"""Jira webhook handler — receives issue lifecycle events from Jira."""

import json
import logging

from fastapi import APIRouter, HTTPException, Request

from app.config import settings

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/jira", tags=["jira"])


@router.post("/webhook")
async def jira_webhook(request: Request):
    """Handle Jira webhook events (issue created/updated/deleted)."""
    body = await request.body()

    # Simple shared-secret verification
    secret = settings.JIRA_WEBHOOK_SECRET
    if secret:
        provided = request.headers.get("x-jira-webhook-secret", request.query_params.get("secret", ""))
        if provided != secret:
            raise HTTPException(status_code=401, detail="Invalid webhook secret")

    try:
        event = json.loads(body)
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Invalid JSON body")

    webhook_event = event.get("webhookEvent", "unknown")
    logger.info("Jira webhook received: %s", webhook_event)

    # Log issue events for agent triage
    issue = event.get("issue", {})
    if webhook_event == "jira:issue_created":
        fields = issue.get("fields", {})
        logger.info(
            "Jira issue created: %s — %s",
            issue.get("key", "unknown"),
            fields.get("summary", "no summary"),
        )
    elif webhook_event == "jira:issue_updated":
        logger.info("Jira issue updated: %s", issue.get("key", "unknown"))
    elif webhook_event == "jira:issue_deleted":
        logger.info("Jira issue deleted: %s", issue.get("key", "unknown"))

    return {"status": "ok", "webhook_event": webhook_event}
