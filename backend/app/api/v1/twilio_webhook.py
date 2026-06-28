"""Twilio webhook handler — receives message status, call status, and recording events."""

import base64
import hashlib
import hmac
import logging
from urllib.parse import urlencode

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import PlainTextResponse

from app.config import settings

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/twilio", tags=["twilio"])


def _verify_twilio_signature(
    url: str,
    params: dict[str, str],
    sig_header: str,
    auth_token: str,
) -> bool:
    """Verify Twilio webhook signature (HMAC-SHA1).

    Twilio computes HMAC-SHA1 of the full URL + sorted params
    using the Auth Token. Signature in X-Twilio-Signature header.
    """
    if not sig_header:
        return False

    # Build the data string: URL + sorted params
    sorted_params = sorted(params.items())
    data = url + "".join(f"{k}{v}" for k, v in sorted_params)

    expected = base64.b64encode(
        hmac.new(
            auth_token.encode("utf-8"),
            data.encode("utf-8"),
            hashlib.sha1,
        ).digest()
    ).decode()

    return hmac.compare_digest(expected, sig_header)


@router.post("/webhook")
async def twilio_webhook(request: Request):
    """Handle Twilio webhook events (message status, call status, recording)."""
    # Parse form data (Twilio uses application/x-www-form-urlencoded)
    form_data = await request.form()
    params = {k: str(v) for k, v in form_data.items()}

    # Verify HMAC-SHA1 signature
    auth_token = settings.TWILIO_WEBHOOK_SECRET
    if auth_token:
        sig_header = request.headers.get("x-twilio-signature", "")
        # Reconstruct the full URL
        url = str(request.url)
        if not _verify_twilio_signature(url, params, sig_header, auth_token):
            raise HTTPException(status_code=401, detail="Invalid webhook signature")

    # Determine event type from params
    message_sid = params.get("MessageSid")
    call_sid = params.get("CallSid")
    recording_sid = params.get("RecordingSid")

    if message_sid:
        status = params.get("MessageStatus", "unknown")
        logger.info("Twilio webhook: message_sid=%s status=%s", message_sid, status)
    elif call_sid:
        status = params.get("CallStatus", "unknown")
        logger.info("Twilio webhook: call_sid=%s status=%s", call_sid, status)
    elif recording_sid:
        logger.info("Twilio webhook: recording_sid=%s", recording_sid)
    else:
        logger.info("Twilio webhook: unknown event type, params=%s", list(params.keys()))

    # Twilio expects TwiML response (empty is fine)
    return PlainTextResponse("", status_code=200)
