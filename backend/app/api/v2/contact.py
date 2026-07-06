"""V2 Contact form — public endpoint for submitting contact inquiries."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from fastapi import APIRouter, Depends
from pydantic import BaseModel, EmailStr, Field

from app.api.v2.base import ok
from app.database import get_db

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/contact", tags=["v2-contact"])


class ContactSubmissionCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    email: EmailStr
    company: str | None = Field(None, max_length=255)
    subject: str = Field("Sales", max_length=100)
    message: str = Field(..., min_length=1)


@router.post("")
async def submit_contact(
    payload: ContactSubmissionCreate,
    db: AsyncSession = Depends(get_db),
):
    """Submit a contact form inquiry. Public — no auth required."""
    from app.models.contact import ContactSubmission

    submission = ContactSubmission(
        name=payload.name,
        email=payload.email,
        company=payload.company,
        subject=payload.subject,
        message=payload.message,
    )
    db.add(submission)
    await db.commit()

    logger.info("Contact submission received from %s (%s)", payload.email, payload.subject)

    return ok({"status": "received", "id": str(submission.id)})
