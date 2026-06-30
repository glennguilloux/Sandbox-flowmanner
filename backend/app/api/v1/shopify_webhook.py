"""
Shopify Webhook Handler

Receives webhook events from Shopify.
Signature verification: HMAC-SHA256 in X-Shopify-Hmac-SHA256 header (base64 digest).
"""

import base64
import hashlib
import hmac
import logging

from fastapi import APIRouter, Header, HTTPException, Request

from app.config import settings

logger = logging.getLogger(__name__)
router = APIRouter(tags=["shopify-webhook"])


@router.post("/shopify/webhook")
async def shopify_webhook(
    request: Request,
    x_shopify_hmac_sha256: str = Header(None),
    x_shopify_topic: str = Header(None),
    x_shopify_shop_domain: str = Header(None),
):
    """Handle incoming Shopify webhook events."""
    body = await request.body()

    # Verify HMAC signature
    if settings.SHOPIFY_WEBHOOK_SECRET and x_shopify_hmac_sha256:
        computed = base64.b64encode(
            hmac.new(
                settings.SHOPIFY_WEBHOOK_SECRET.encode(),
                body,
                hashlib.sha256,
            ).digest()
        ).decode()
        if not hmac.compare_digest(computed, x_shopify_hmac_sha256):
            raise HTTPException(status_code=401, detail="Invalid webhook signature")

    event_type = x_shopify_topic or "unknown"
    shop = x_shopify_shop_domain or "unknown"

    logger.info("Shopify webhook: topic=%s shop=%s", event_type, shop)

    # Route through the event router -> trigger system -> UnifiedExecutor.
    from app.database import AsyncSessionLocal
    from app.services.event_router import emit_integration_event

    try:
        async with AsyncSessionLocal() as event_db:
            await emit_integration_event(
                db=event_db,
                source="shopify",
                event_type=event_type,
                payload={
                    "topic": event_type,
                    "shop": shop,
                },
            )
            await event_db.commit()
    except Exception:
        logger.warning("Shopify event router failed for %s", event_type, exc_info=True)

    return {"status": "ok", "topic": event_type, "shop": shop}
