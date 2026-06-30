"""Airtable webhook handler — receives base change notifications from Airtable."""

import hashlib
import hmac
import json
import logging

from fastapi import APIRouter, HTTPException, Request

from app.config import settings

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/airtable", tags=["airtable"])


def _verify_airtable_signature(payload: bytes, sig_header: str, secret: str) -> bool:
    """Verify Airtable webhook signature (HMAC-SHA256).

    Airtable sends the signature in the X-Airtable-Content-MAC header.
    Compute HMAC-SHA256 of raw body using webhook secret, compare with header.
    """
    if not sig_header:
        return False

    expected = hmac.new(
        secret.encode("utf-8"),
        payload,
        hashlib.sha256,
    ).hexdigest()

    # Airtable may prefix with "hmac-sha256="
    sig_value = sig_header.split("=", 1)[-1] if "=" in sig_header else sig_header

    return hmac.compare_digest(expected, sig_value)


@router.post("/webhook")
async def airtable_webhook(request: Request):
    """Handle Airtable webhook events (record changes)."""
    body = await request.body()

    # Verify HMAC-SHA256 signature
    secret = settings.AIRTABLE_WEBHOOK_SECRET
    if secret:
        sig_header = request.headers.get("x-airtable-content-mac", "")
        if not _verify_airtable_signature(body, sig_header, secret):
            raise HTTPException(status_code=401, detail="Invalid webhook signature")

    try:
        event = json.loads(body)
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Invalid JSON body")

    # Airtable webhooks send a payload with changed tables
    webhook_id = event.get("webhook", {}).get("id", "unknown")
    logger.info("Airtable webhook received: %s", webhook_id)

    # Log changes for agent triage
    changed_tables = event.get("changedTablesById", {})
    for table_id, changes in changed_tables.items():
        created = len(changes.get("createdRecords", []))
        updated = len(changes.get("changedRecordsById", {}))
        deleted = len(changes.get("destroyedRecords", []))
        logger.info(
            "Airtable table %s changes: %d created, %d updated, %d deleted",
            table_id,
            created,
            updated,
            deleted,
        )

    # Route through the event router -> trigger system -> UnifiedExecutor.
    from app.database import AsyncSessionLocal
    from app.services.event_router import emit_integration_event

    try:
        async with AsyncSessionLocal() as event_db:
            await emit_integration_event(
                db=event_db,
                source="airtable",
                event_type="base.change",
                payload={
                    "webhook_id": webhook_id,
                    "changed_tables": list(changed_tables.keys()),
                },
            )
            await event_db.commit()
    except Exception:
        logger.warning("Airtable event router failed for %s", webhook_id, exc_info=True)

    return {"status": "ok", "webhook_id": webhook_id}
