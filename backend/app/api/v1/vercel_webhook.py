"""Vercel webhook handler — receives deployment events from Vercel."""

import hashlib
import hmac
import json
import logging

from fastapi import APIRouter, HTTPException, Request

from app.config import settings

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/vercel", tags=["vercel"])


def _verify_vercel_signature(body: bytes, signature: str) -> bool:
    """Verify Vercel webhook HMAC-SHA256 signature."""
    secret = settings.VERCEL_WEBHOOK_SECRET
    if not secret:
        return True  # Accept unsigned in dev
    expected = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature)


@router.post("/webhook")
async def vercel_webhook(request: Request):
    """Handle Vercel webhook events (deployment lifecycle)."""
    body = await request.body()

    # Verify signature
    signature = request.headers.get("x-vercel-signature", "")
    if settings.VERCEL_WEBHOOK_SECRET and not _verify_vercel_signature(body, signature):
        raise HTTPException(status_code=401, detail="Invalid webhook signature")

    try:
        event = json.loads(body)
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Invalid JSON body")

    event_type = event.get("type", "unknown")
    logger.info("Vercel webhook received: %s", event_type)

    # Log deployment events for agent triage
    if event_type in ("deployment.error", "deployment.failed"):
        deployment = event.get("payload", {}).get("deployment", {})
        logger.warning(
            "Vercel deployment failed: %s (project: %s)",
            deployment.get("id", "unknown"),
            deployment.get("name", "unknown"),
        )
    elif event_type in ("deployment.succeeded", "deployment.ready"):
        deployment = event.get("payload", {}).get("deployment", {})
        logger.info(
            "Vercel deployment succeeded: %s (url: %s)",
            deployment.get("id", "unknown"),
            deployment.get("url", "unknown"),
        )

    # Route through the event router -> trigger system -> UnifiedExecutor.
    from app.database import AsyncSessionLocal
    from app.services.event_router import emit_integration_event

    deployment = event.get("payload", {}).get("deployment", {})
    try:
        async with AsyncSessionLocal() as event_db:
            await emit_integration_event(
                db=event_db,
                source="vercel",
                event_type=event_type,
                payload={
                    "event_type": event_type,
                    "deployment_id": deployment.get("id"),
                    "project": deployment.get("name"),
                    "url": deployment.get("url"),
                    "meta": event.get("payload", {}).get("meta"),
                },
                delivery_id=event.get("id"),
            )
            await event_db.commit()
    except Exception:
        logger.warning("Vercel event router failed for %s", event_type, exc_info=True)

    return {"status": "ok", "event_type": event_type}
