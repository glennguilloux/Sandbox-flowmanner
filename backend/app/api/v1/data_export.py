"""
Data Export & GDPR API

POST /api/users/me/export — generates data export
DELETE /api/users/me — GDPR hard delete
"""

import io
import json
import logging
import zipfile
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.database import get_db
from app.models.user import User

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/data-export", tags=["data-export"])


@router.post("/me/export")
async def export_user_data(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Export all user data as a ZIP file (GDPR compliance)."""
    export_data = {}

    # 1. User profile
    export_data["profile"] = {
        "id": user.id,
        "email": user.email,
        "name": getattr(user, "name", None),
        "created_at": str(user.created_at) if hasattr(user, "created_at") else None,
    }

    # 2. Missions
    try:
        missions = await db.execute(
            text(
                "SELECT id, title, description, status, created_at, updated_at FROM missions WHERE owner_id = :uid"
            ),
            {"uid": user.id},
        )
        export_data["missions"] = [
            {
                "id": row.id,
                "title": row.title,
                "description": row.description,
                "status": row.status,
                "created_at": str(row.created_at) if row.created_at else None,
                "updated_at": str(row.updated_at) if row.updated_at else None,
            }
            for row in missions.fetchall()
        ]
    except Exception as e:
        logger.warning(f"Export missions failed: {e}")
        export_data["missions"] = []

    # 3. Chat history
    try:
        chats = await db.execute(
            text("SELECT id, title, created_at FROM chat_threads WHERE user_id = :uid"),
            {"uid": user.id},
        )
        export_data["chat_threads"] = [
            {
                "id": row.id,
                "title": row.title,
                "created_at": str(row.created_at) if row.created_at else None,
            }
            for row in chats.fetchall()
        ]

        messages = await db.execute(
            text(
                """
                SELECT cm.id, cm.thread_id, cm.role, cm.content, cm.created_at
                FROM chat_messages cm
                JOIN chat_threads ct ON ct.id = cm.thread_id
                WHERE ct.user_id = :uid
                ORDER BY cm.created_at
            """
            ),
            {"uid": user.id},
        )
        export_data["chat_messages"] = [
            {
                "id": row.id,
                "thread_id": row.thread_id,
                "role": row.role,
                "content": row.content[:5000] if row.content else None,
                "created_at": str(row.created_at) if row.created_at else None,
            }
            for row in messages.fetchall()
        ]
    except Exception as e:
        logger.warning(f"Export chats failed: {e}")
        export_data["chat_threads"] = []
        export_data["chat_messages"] = []

    # 4. Agents created
    try:
        agents = await db.execute(
            text(
                "SELECT id, name, description, category, created_at FROM agents WHERE created_by = :uid"
            ),
            {"uid": user.id},
        )
        export_data["agents"] = [
            {
                "id": row.id,
                "name": row.name,
                "description": row.description,
                "category": row.category,
                "created_at": str(row.created_at) if row.created_at else None,
            }
            for row in agents.fetchall()
        ]
    except Exception as e:
        logger.warning(f"Export agents failed: {e}")
        export_data["agents"] = []

    # 5. Settings
    try:
        settings_result = await db.execute(
            text("SELECT * FROM user_settings WHERE user_id = :uid"), {"uid": user.id}
        )
        settings_row = settings_result.fetchone()
        if settings_row:
            export_data["settings"] = dict(settings_row._mapping)
        else:
            export_data["settings"] = {}
    except Exception as e:
        logger.warning(f"Export settings failed: {e}")
        export_data["settings"] = {}

    # 6. API keys (metadata only, not secrets)
    try:
        api_keys = await db.execute(
            text(
                "SELECT id, name, provider, created_at, last_used_at FROM user_api_keys WHERE user_id = :uid"
            ),
            {"uid": user.id},
        )
        export_data["api_keys"] = [
            {
                "id": row.id,
                "name": row.name,
                "provider": row.provider,
                "created_at": str(row.created_at) if row.created_at else None,
                "last_used_at": str(row.last_used_at) if row.last_used_at else None,
            }
            for row in api_keys.fetchall()
        ]
    except Exception as e:
        logger.warning(f"Export api_keys failed: {e}")
        export_data["api_keys"] = []

    # Create ZIP in memory
    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        for filename, data in export_data.items():
            zf.writestr(f"{filename}.json", json.dumps(data, indent=2, default=str))

    zip_buffer.seek(0)

    from fastapi.responses import StreamingResponse

    timestamp = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
    return StreamingResponse(
        zip_buffer,
        media_type="application/zip",
        headers={
            "Content-Disposition": f'attachment; filename="flowmanner_export_{timestamp}.zip"'
        },
    )


@router.delete("/me")
async def delete_user_data(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """GDPR-compliant hard delete of all user data."""
    user_id = user.id

    # Delete in order (respect foreign keys)
    tables = [
        (
            "chat_messages",
            "thread_id IN (SELECT id FROM chat_threads WHERE user_id = :uid)",
        ),
        ("chat_threads", "user_id = :uid"),
        ("chat_files", "user_id = :uid"),
        ("chat_folders", "user_id = :uid"),
        (
            "mission_logs",
            "mission_id IN (SELECT id FROM missions WHERE owner_id = :uid)",
        ),
        (
            "mission_runs",
            "mission_id IN (SELECT id FROM missions WHERE owner_id = :uid)",
        ),
        (
            "mission_tasks",
            "mission_id IN (SELECT id FROM missions WHERE owner_id = :uid)",
        ),
        ("missions", "owner_id = :uid"),
        ("notifications", "user_id = :uid"),
        ("notification_settings", "user_id = :uid"),
        ("push_subscriptions", "user_id = :uid"),
        ("audit_logs", "user_id = :uid"),
        ("analytics_events", "user_id = :uid"),
        ("memories", "user_id = :uid"),
        ("memory_sessions", "user_id = :uid"),
        ("user_api_keys", "user_id = :uid"),
        ("user_settings", "user_id = :uid"),
        ("user_model_preferences", "user_id = :uid"),
        ("workspace_members", "user_id = :uid"),
        ("team_members", "user_id = :uid"),
    ]

    deleted_counts = {}
    for table, where_clause in tables:
        try:
            result = await db.execute(
                text(f"DELETE FROM {table} WHERE {where_clause}"), {"uid": user_id}
            )
            deleted_counts[table] = result.rowcount
        except Exception as e:
            logger.warning(f"Delete from {table} failed: {e}")
            deleted_counts[table] = f"error: {e}"

    # Anonymize user record (don't delete — may have foreign key references)
    try:
        await db.execute(
            text(
                """
                UPDATE users SET
                    email = :anon_email,
                    hashed_password = 'deleted',
                    name = 'Deleted User',
                    is_active = false
                WHERE id = :uid
            """
            ),
            {"uid": user_id, "anon_email": f"deleted_{user_id}@flowmanner.deleted"},
        )
    except Exception as e:
        logger.error(f"Anonymize user failed: {e}")
        raise HTTPException(status_code=500, detail="Failed to delete user data")

    await db.commit()

    # Log the deletion
    logger.info(f"GDPR deletion completed for user {user_id}: {deleted_counts}")

    return {
        "status": "deleted",
        "user_id": user_id,
        "tables_affected": deleted_counts,
    }
