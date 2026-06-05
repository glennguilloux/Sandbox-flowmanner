"""Audit log API endpoints for user-facing audit trail."""

import logging

from fastapi import APIRouter, Depends, Query
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_db
from app.models.user import User

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/audit/logs", tags=["audit"])


@router.get("/")
async def get_user_audit_log(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    action: str | None = None,
):
    """Get audit log entries for the current user."""
    # Build query
    base_query = "SELECT * FROM audit_logs WHERE user_id = :user_id"
    count_query = "SELECT COUNT(*) FROM audit_logs WHERE user_id = :user_id"
    params: dict = {"user_id": user.id}

    if action:
        base_query += " AND action = :action"
        count_query += " AND action = :action"
        params["action"] = action

    base_query += " ORDER BY timestamp DESC LIMIT :limit OFFSET :offset"
    params["limit"] = limit
    params["offset"] = offset

    # Get total count
    count_result = await db.execute(text(count_query), params)
    total = count_result.scalar() or 0

    # Get entries
    result = await db.execute(text(base_query), params)
    rows = result.fetchall()

    entries = []
    for row in rows:
        entries.append(
            {
                "id": row[0] if len(row) > 0 else None,
                "action": row[1] if len(row) > 1 else None,
                "details": row[2] if len(row) > 2 else None,
                "ip_address": row[3] if len(row) > 3 else None,
                "user_id": row[4] if len(row) > 4 else None,
                "user_email": row[5] if len(row) > 5 else None,
                "endpoint": row[6] if len(row) > 6 else None,
                "method": row[7] if len(row) > 7 else None,
                "user_agent": row[8] if len(row) > 8 else None,
                "success": row[9] if len(row) > 9 else None,
                "timestamp": row[10].isoformat() if len(row) > 10 and row[10] else None,
            }
        )

    return {
        "entries": entries,
        "total": total,
        "limit": limit,
        "offset": offset,
    }
