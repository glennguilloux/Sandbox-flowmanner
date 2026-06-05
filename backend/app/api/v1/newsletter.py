"""Newsletter subscription endpoint — Redis-backed."""

import logging
import re

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.cache.workflow_cache import get_workflow_cache

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/newsletter", tags=["newsletter"])

EMAIL_RE = re.compile(r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$")

NEWSLETTER_KEY = "newsletter:subscribers"


class SubscribeRequest(BaseModel):
    email: str


class SubscribeResponse(BaseModel):
    message: str


@router.post("/subscribe", response_model=SubscribeResponse)
async def subscribe_newsletter(payload: SubscribeRequest):
    email = payload.email.strip().lower()

    if not EMAIL_RE.match(email):
        raise HTTPException(status_code=400, detail="Invalid email address")

    cache = get_workflow_cache()

    if not cache.client:
        raise HTTPException(status_code=503, detail="Service unavailable")

    added = cache.client.sadd(NEWSLETTER_KEY, email)

    if added == 0:
        return SubscribeResponse(message="You are already subscribed.")

    logger.info(f"Newsletter subscription: {email}")
    return SubscribeResponse(message="Subscribed successfully.")
