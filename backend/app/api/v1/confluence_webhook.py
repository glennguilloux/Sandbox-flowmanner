"""Confluence webhook handler — receives page/content lifecycle events from Confluence."""

import json
import logging

from fastapi import APIRouter, HTTPException, Request

from app.config import settings

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/confluence", tags=["confluence"])


@router.post("/webhook")
async def confluence_webhook(request: Request):
    """Handle Confluence webhook events (page created/updated/deleted, comments)."""
    body = await request.body()

    # Simple shared-secret verification
    secret = settings.CONFLUENCE_WEBHOOK_SECRET
    if secret:
        provided = request.headers.get("x-confluence-webhook-secret", request.query_params.get("secret", ""))
        if provided != secret:
            raise HTTPException(status_code=401, detail="Invalid webhook secret")

    try:
        event = json.loads(body)
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Invalid JSON body")

    webhook_event = event.get("webhookEvent", "unknown")
    logger.info("Confluence webhook received: %s", webhook_event)

    # Log page events for agent triage
    if "page" in webhook_event.lower():
        page = event.get("page", {})
        logger.info(
            "Confluence page event: %s — %s (id: %s)",
            webhook_event,
            page.get("title", "no title"),
            page.get("id", "unknown"),
        )
    elif "comment" in webhook_event.lower():
        comment = event.get("comment", {})
        logger.info(
            "Confluence comment event: %s (id: %s)",
            webhook_event,
            comment.get("id", "unknown"),
        )
    elif "attachment" in webhook_event.lower():
        attachment = event.get("attachment", {})
        logger.info(
            "Confluence attachment event: %s — %s",
            webhook_event,
            attachment.get("title", "unknown"),
        )

    # Route through the event router -> trigger system -> UnifiedExecutor.
    from app.database import AsyncSessionLocal
    from app.services.event_router import emit_integration_event

    try:
        async with AsyncSessionLocal() as event_db:
            await emit_integration_event(
                db=event_db,
                source="confluence",
                event_type=webhook_event,
                payload={
                    "webhook_event": webhook_event,
                    "page_title": event.get("page", {}).get("title"),
                    "page_id": event.get("page", {}).get("id"),
                },
            )
            await event_db.commit()
    except Exception:
        logger.warning("Confluence event router failed for %s", webhook_event, exc_info=True)

    return {"status": "ok", "webhook_event": webhook_event}
