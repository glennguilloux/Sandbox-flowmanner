"""Figma webhook handler — receives file lifecycle events from Figma."""

import json
import logging

from fastapi import APIRouter, HTTPException, Request

from app.config import settings

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/figma", tags=["figma"])


@router.post("/webhook")
async def figma_webhook(request: Request):
    """Handle Figma webhook events (file comments, version updates, library publishes)."""
    body = await request.body()

    # Simple shared-secret verification
    secret = settings.FIGMA_WEBHOOK_SECRET
    if secret:
        provided = request.headers.get("x-figma-webhook-secret", request.query_params.get("secret", ""))
        if provided != secret:
            raise HTTPException(status_code=401, detail="Invalid webhook secret")

    try:
        event = json.loads(body)
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Invalid JSON body")

    event_type = event.get("event_type", event.get("type", "unknown"))
    logger.info("Figma webhook received: %s", event_type)

    # Log events for agent triage
    if event_type == "FILE_COMMENT":
        file_name = event.get("file_name", "unknown")
        logger.info("Figma comment on file: %s", file_name)
    elif event_type == "FILE_VERSION_UPDATE":
        file_name = event.get("file_name", "unknown")
        logger.info("Figma version update on file: %s", file_name)
    elif event_type == "LIBRARY_PUBLISH":
        logger.info("Figma library published")

    # Route through the event router -> trigger system -> UnifiedExecutor.
    from app.database import AsyncSessionLocal
    from app.services.event_router import emit_integration_event

    try:
        async with AsyncSessionLocal() as event_db:
            await emit_integration_event(
                db=event_db,
                source="figma",
                event_type=event_type,
                payload={
                    "event_type": event_type,
                    "file_name": event.get("file_name"),
                    "file_key": event.get("file_key"),
                },
            )
            await event_db.commit()
    except Exception:
        logger.warning("Figma event router failed for %s", event_type, exc_info=True)

    return {"status": "ok", "event_type": event_type}
