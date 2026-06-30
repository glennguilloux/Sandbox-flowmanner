"""GitHub webhook handler — receives push, PR, issue, and workflow events."""

import hashlib
import hmac
import json
import logging

from fastapi import APIRouter, HTTPException, Request

from app.config import settings

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/github", tags=["github"])


def _verify_github_signature(body: bytes, sig_header: str, secret: str) -> bool:
    """Verify GitHub webhook HMAC-SHA256 signature.

    GitHub sends the signature in the X-Hub-Signature-256 header
    as 'sha256=<hex>' format.
    """
    if not sig_header:
        return False

    expected = (
        "sha256="
        + hmac.new(
            secret.encode("utf-8"),
            body,
            hashlib.sha256,
        ).hexdigest()
    )

    return hmac.compare_digest(expected, sig_header)


@router.post("/webhook")
async def github_webhook(request: Request):
    """Handle GitHub webhook events (push, pull_request, issues, workflow_run, etc.)."""
    body = await request.body()

    # Verify HMAC-SHA256 signature
    secret = settings.GITHUB_WEBHOOK_SECRET
    if secret:
        sig_header = request.headers.get("x-hub-signature-256", "")
        if not _verify_github_signature(body, sig_header, secret):
            raise HTTPException(status_code=401, detail="Invalid webhook signature")

    try:
        event = json.loads(body)
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Invalid JSON body")

    # GitHub event type comes from the X-GitHub-Event header
    event_type = request.headers.get("x-github-event", "unknown")
    delivery_id = request.headers.get("x-github-delivery")
    action = event.get("action", "")

    # Ping events are purely diagnostic — no trigger matching needed.
    if event_type == "ping":
        logger.info("GitHub ping received (delivery=%s)", delivery_id)
        return {"status": "ok", "event": "ping"}

    logger.info(
        "GitHub webhook received: event=%s action=%s delivery=%s",
        event_type,
        action,
        delivery_id,
    )

    # Extract common fields
    repo = event.get("repository", {}).get("full_name", "unknown")
    sender = event.get("sender", {}).get("login", "unknown")

    # Log specific event types for agent triage
    if event_type == "push":
        ref = event.get("ref", "unknown")
        commits = event.get("commits", [])
        logger.info("GitHub push to %s: %s (%d commits)", repo, ref, len(commits))
    elif event_type == "pull_request":
        pr = event.get("pull_request", {})
        logger.info(
            "GitHub PR %s: #%s — %s (%s)",
            action,
            pr.get("number", "?"),
            pr.get("title", "?"),
            pr.get("state", "?"),
        )
    elif event_type == "issues":
        issue = event.get("issue", {})
        logger.info(
            "GitHub issue %s: #%s — %s",
            action,
            issue.get("number", "?"),
            issue.get("title", "?"),
        )
    elif event_type == "workflow_run":
        workflow = event.get("workflow_run", {})
        logger.info(
            "GitHub workflow %s: %s — %s",
            action,
            workflow.get("name", "?"),
            workflow.get("conclusion", workflow.get("status", "?")),
        )

    # Route through the event router -> trigger system -> UnifiedExecutor.
    normalized_event = f"{event_type}.{action}" if action else event_type
    from app.database import AsyncSessionLocal
    from app.services.event_router import emit_integration_event

    try:
        async with AsyncSessionLocal() as event_db:
            await emit_integration_event(
                db=event_db,
                source="github",
                event_type=normalized_event,
                payload={
                    "event_type": event_type,
                    "action": action,
                    "repository": repo,
                    "sender": sender,
                    "delivery_id": delivery_id,
                    "number": (event.get("pull_request", {}).get("number") or event.get("issue", {}).get("number")),
                },
                delivery_id=delivery_id,
            )
            await event_db.commit()
    except Exception:
        logger.warning("GitHub event router failed for %s", normalized_event, exc_info=True)

    return {"status": "ok", "event": event_type, "action": action}
