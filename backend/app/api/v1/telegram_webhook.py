"""
Telegram Webhook Handler

Receives update events from Telegram Bot API.
Verification: X-Telegram-Bot-Api-Secret-Token header.
"""

import json
import logging

from fastapi import APIRouter, Header, HTTPException, Request

from app.config import settings

logger = logging.getLogger(__name__)
router = APIRouter(tags=["telegram-webhook"])


@router.post("/telegram/webhook")
async def telegram_webhook(
    request: Request,
    x_telegram_bot_api_secret_token: str = Header(None),
):
    """Handle incoming Telegram bot update events."""
    # Verify secret token
    if (
        settings.TELEGRAM_WEBHOOK_SECRET
        and x_telegram_bot_api_secret_token
        and x_telegram_bot_api_secret_token != settings.TELEGRAM_WEBHOOK_SECRET
    ):
        raise HTTPException(status_code=401, detail="Invalid webhook secret token")

    body = await request.body()
    try:
        payload = json.loads(body)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON payload")

    update_id = payload.get("update_id")
    event_type = "unknown"
    if "message" in payload:
        event_type = "message"
    elif "edited_message" in payload:
        event_type = "edited_message"
    elif "channel_post" in payload:
        event_type = "channel_post"
    elif "my_chat_member" in payload:
        event_type = "my_chat_member"

    logger.info("Telegram webhook: update_id=%s type=%s", update_id, event_type)

    return {"status": "ok", "update_id": update_id, "type": event_type}
