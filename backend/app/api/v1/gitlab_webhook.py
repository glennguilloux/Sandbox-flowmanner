"""GitLab webhook handler — receives merge request, pipeline, and deployment events."""

import json
import logging

from fastapi import APIRouter, HTTPException, Request

from app.config import settings

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/gitlab", tags=["gitlab"])


@router.post("/webhook")
async def gitlab_webhook(request: Request):
    """Handle GitLab webhook events (merge request, pipeline, deployment, notes)."""
    body = await request.body()

    # Verify shared secret (X-Gitlab-Token header — simple string comparison, not HMAC)
    secret = settings.GITLAB_WEBHOOK_SECRET
    if secret:
        token_header = request.headers.get("x-gitlab-token", "")
        if token_header != secret:
            raise HTTPException(status_code=401, detail="Invalid webhook token")

    try:
        event = json.loads(body)
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Invalid JSON body")

    # Determine event type from the object_kind field
    object_kind = event.get("object_kind", "unknown")
    logger.info("GitLab webhook received: object_kind=%s", object_kind)

    if object_kind == "merge_request":
        mr = event.get("object_attributes", {})
        logger.info(
            "GitLab MR event: !%s — %s (state: %s)",
            mr.get("iid", "?"),
            mr.get("title", "?"),
            mr.get("state", "?"),
        )
    elif object_kind == "pipeline":
        pipeline = event.get("object_attributes", {})
        logger.info(
            "GitLab pipeline event: #%s — status: %s, ref: %s",
            pipeline.get("id", "?"),
            pipeline.get("status", "?"),
            pipeline.get("ref", "?"),
        )
    elif object_kind == "deployment":
        deployment = event.get("object_attributes", {})
        logger.info(
            "GitLab deployment event: %s — status: %s, environment: %s",
            deployment.get("id", "?"),
            deployment.get("status", "?"),
            deployment.get("environment", "?"),
        )
    elif object_kind == "note":
        note = event.get("object_attributes", {})
        logger.info(
            "GitLab note event: %s — on %s",
            note.get("id", "?"),
            note.get("noteable_type", "?"),
        )

    # Route through the event router -> trigger system -> UnifiedExecutor.
    from app.database import AsyncSessionLocal
    from app.services.event_router import emit_integration_event

    try:
        async with AsyncSessionLocal() as event_db:
            await emit_integration_event(
                db=event_db,
                source="gitlab",
                event_type=object_kind,
                payload={
                    "object_kind": object_kind,
                    "project": event.get("project", {}).get("path_with_namespace"),
                    "user": event.get("user", {}).get("username"),
                },
            )
            await event_db.commit()
    except Exception:
        logger.warning("GitLab event router failed for %s", object_kind, exc_info=True)

    return {"status": "ok", "object_kind": object_kind}
