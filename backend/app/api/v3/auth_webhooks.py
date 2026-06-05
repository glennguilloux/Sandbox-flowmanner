from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select

from app.api.deps import get_current_user
from app.api.v3.base import ok
from app.database import get_db
from app.models.auth_v3_models import AuthWebhookSubscription

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from app.models.user import User

router = APIRouter(prefix="/auth", tags=["v3-auth-webhooks"])


async def _require_webhooks_enabled(db: AsyncSession) -> None:
    from sqlalchemy import text

    result = await db.execute(
        text(
            "SELECT enabled_globally FROM feature_flags WHERE key = 'AUTH_V3_WEBHOOKS'"
        )
    )
    if not result.scalar():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Endpoint not found"
        )


@router.post("/webhooks", status_code=status.HTTP_201_CREATED)
async def create_webhook(
    workspace_id: str,
    url: str,
    events: list[str],
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await _require_webhooks_enabled(db)

    webhook = AuthWebhookSubscription(
        id=str(uuid.uuid4()),
        workspace_id=workspace_id,
        url=url,
        secret=uuid.uuid4().hex,
        events=",".join(events),
    )
    db.add(webhook)
    await db.flush()

    return ok(
        {"id": webhook.id, "workspace_id": webhook.workspace_id, "url": webhook.url}
    )


@router.get("/webhooks", status_code=status.HTTP_200_OK)
async def list_webhooks(
    workspace_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await _require_webhooks_enabled(db)

    result = await db.execute(
        select(AuthWebhookSubscription).where(
            AuthWebhookSubscription.workspace_id == workspace_id
        )
    )
    webhooks = result.scalars().all()

    return ok(
        [
            {"id": w.id, "url": w.url, "events": w.events, "is_active": w.is_active}
            for w in webhooks
        ]
    )


@router.delete("/webhooks/{webhook_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_webhook(
    webhook_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await _require_webhooks_enabled(db)

    result = await db.execute(
        select(AuthWebhookSubscription).where(AuthWebhookSubscription.id == webhook_id)
    )
    webhook = result.scalar_one_or_none()
    if not webhook:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Webhook not found"
        )

    await db.delete(webhook)
    await db.flush()
