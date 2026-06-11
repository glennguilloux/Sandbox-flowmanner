"""
Linear Webhook Endpoint

Receives webhook events from Linear:
- Issue created → create a Flowmanner mission
- Issue updated → update mission status
- Issue deleted → cancel mission

Webhook URL: POST /api/linear/webhook
"""

import hashlib
import hmac
import json
import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_db

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/linear", tags=["linear"])


def _verify_linear_signature(body: bytes, signature: str, secret: str) -> bool:
    """Verify Linear webhook HMAC-SHA256 signature."""
    if not secret:
        logger.error("LINEAR_WEBHOOK_SECRET not configured — rejecting webhook")
        return False

    expected = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature)


@router.post("/webhook")
async def linear_webhook(
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """
    Receive webhook events from Linear.

    Handles:
    - Issue created → creates a Flowmanner mission
    - Issue updated → updates linked mission
    - Issue deleted → cancels linked mission
    """
    body = await request.body()

    # Verify signature
    signature = request.headers.get("Linear-Signature", "")
    if not _verify_linear_signature(body, signature, settings.LINEAR_WEBHOOK_SECRET):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid signature")

    try:
        payload = json.loads(body)
    except json.JSONDecodeError:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid JSON")

    action = payload.get("action")
    event_type = payload.get("type")
    data = payload.get("data", {})

    logger.info(f"Linear webhook: {action} {event_type}")

    if event_type != "Issue":
        return {"status": "ignored", "reason": f"Unsupported event type: {event_type}"}

    try:
        if action == "create":
            await _handle_issue_created(db, data)
        elif action == "update":
            await _handle_issue_updated(db, data)
        elif action == "remove":
            await _handle_issue_deleted(db, data)
        else:
            return {"status": "ignored", "reason": f"Unsupported action: {action}"}

        return {"status": "ok", "action": action}
    except Exception as e:
        logger.error(f"Error handling Linear webhook: {e}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


async def _find_system_user(db: AsyncSession) -> int | None:
    """Find a system user to own automatically-created missions."""
    from sqlalchemy import select

    from app.models.user import User

    result = await db.execute(select(User).where(User.email == "system@flowmanner.com").limit(1))
    user = result.scalars().first()
    if user:
        return user.id

    # Fallback: get any user
    result = await db.execute(select(User).limit(1))
    user = result.scalars().first()
    return user.id if user else None


async def _handle_issue_created(db: AsyncSession, data: dict[str, Any]):
    """Create a Flowmanner mission when a Linear issue is created."""
    from sqlalchemy import select

    from app.models.mission_models import Mission
    from app.services.mission_service import create_mission

    issue_id = data.get("id")

    # Idempotency: check if already imported (Linear may retry webhooks)
    existing = await db.execute(select(Mission).where(Mission.plan["linear"]["issue_id"].astext == issue_id).limit(1))
    if existing.scalars().first():
        logger.info(f"Linear issue {issue_id} already imported — skipping")
        return

    title = data.get("title", "Untitled Issue")
    description = data.get("description", "")
    issue_url = data.get("url", "")
    team = data.get("team", {})
    team_name = team.get("name", "Unknown")

    user_id = await _find_system_user(db)
    if user_id is None:
        logger.error("No users in database — cannot create mission from Linear issue")
        return

    mission = await create_mission(
        db,
        title=f"[{team_name}] {title}",
        description=description or f"Imported from Linear issue: {issue_url}",
        mission_type="linear_issue",
        priority=_map_linear_priority(data.get("priority")),
        user_id=user_id,
        status="pending",
    )

    # Store Linear linkage in plan
    mission.plan = {
        "linear": {
            "issue_id": issue_id,
            "issue_url": issue_url,
            "team_id": team.get("id"),
            "team_name": team_name,
        }
    }
    await db.commit()

    logger.info(f"Created mission {mission.id} from Linear issue {issue_id}")


async def _handle_issue_updated(db: AsyncSession, data: dict[str, Any]):
    """Update linked mission when a Linear issue is updated."""
    from sqlalchemy import select

    from app.models.mission_models import Mission

    issue_id = data.get("id")

    # Find mission linked to this Linear issue
    # We search in plan->linear->issue_id (JSONB)
    result = await db.execute(select(Mission).where(Mission.plan["linear"]["issue_id"].astext == issue_id).limit(1))
    mission = result.scalars().first()
    if not mission:
        logger.debug(f"No linked mission for Linear issue {issue_id}")
        return

    # Update mission if issue state changed
    state = data.get("state", {})
    state_name = state.get("name", "").lower() if state else ""

    if state_name in ("done", "completed", "closed", "resolved"):
        if mission.status not in ("completed", "failed", "cancelled"):
            mission.status = "completed"
            await db.commit()
            logger.info(f"Marked mission {mission.id} as completed (Linear issue {issue_id} → {state_name})")
    elif state_name in ("cancelled",) and mission.status not in (
        "completed",
        "failed",
        "cancelled",
    ):
        mission.status = "cancelled"
        await db.commit()
        logger.info(f"Cancelled mission {mission.id} (Linear issue {issue_id} → {state_name})")


async def _handle_issue_deleted(db: AsyncSession, data: dict[str, Any]):
    """Cancel linked mission when Linear issue is deleted."""
    from sqlalchemy import select

    from app.models.mission_models import Mission

    issue_id = data.get("id")

    result = await db.execute(select(Mission).where(Mission.plan["linear"]["issue_id"].astext == issue_id).limit(1))
    mission = result.scalars().first()
    if not mission:
        return

    mission.status = "cancelled"
    await db.commit()
    logger.info(f"Cancelled mission {mission.id} (Linear issue {issue_id} deleted)")


def _map_linear_priority(linear_priority) -> str | None:
    """Map Linear priority (0-4, or 'urgent'/'high'/'normal'/'low') to Flowmanner priority."""
    if linear_priority is None:
        return None
    if isinstance(linear_priority, str):
        mapping = {
            "urgent": "critical",
            "high": "high",
            "medium": "medium",
            "low": "low",
        }
        return mapping.get(linear_priority.lower(), "medium")
    # Numeric: 0=no priority, 1=urgent, 2=high, 3=medium, 4=low
    if linear_priority == 0:
        return None
    mapping = {1: "critical", 2: "high", 3: "medium", 4: "low"}
    return mapping.get(linear_priority, "medium")
