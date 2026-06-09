"""
Feature Flags API

GET /api/feature-flags — list all flags (admin)
GET /api/feature-flags/active — list enabled flags (all users)
POST /api/feature-flags — create flag
PUT /api/feature-flags/{key} — update flag
DELETE /api/feature-flags/{key} — delete flag
"""

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.database import get_db
from app.models.user import User

router = APIRouter(prefix="/feature-flags", tags=["feature-flags"])


class FeatureFlagCreate(BaseModel):
    key: str
    name: str
    description: str | None = None
    enabled_globally: bool = False


class FeatureFlagUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    enabled_globally: bool | None = None


class FeatureFlagResponse(BaseModel):
    id: int
    key: str
    name: str
    description: str | None
    enabled_globally: bool
    created_at: datetime | None
    updated_at: datetime | None


@router.get("")
async def list_flags(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List all feature flags (admin only)."""
    result = await db.execute(text("SELECT * FROM feature_flags ORDER BY key"))
    flags = result.fetchall()
    return {
        "flags": [
            {
                "id": f.id,
                "key": f.key,
                "name": f.name,
                "description": f.description,
                "enabled_globally": f.enabled_globally,
                "created_at": str(f.created_at) if f.created_at else None,
                "updated_at": str(f.updated_at) if f.updated_at else None,
            }
            for f in flags
        ]
    }


@router.get("/active")
async def list_active_flags(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List only enabled feature flags (for frontend consumption)."""
    result = await db.execute(
        text("SELECT key, name FROM feature_flags WHERE enabled_globally = true")
    )
    flags = result.fetchall()
    return {f.key: True for f in flags}


@router.post("", status_code=201)
async def create_flag(
    payload: FeatureFlagCreate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Create a new feature flag."""
    # Check if key exists
    existing = await db.execute(
        text("SELECT id FROM feature_flags WHERE key = :key"), {"key": payload.key}
    )
    if existing.scalar():
        raise HTTPException(status_code=409, detail="Flag key already exists")

    result = await db.execute(
        text(
            """
            INSERT INTO feature_flags (key, name, description, enabled_globally, created_at, updated_at)
            VALUES (:key, :name, :description, :enabled, NOW(), NOW())
            RETURNING id, key, name, description, enabled_globally, created_at, updated_at
        """
        ),
        {
            "key": payload.key,
            "name": payload.name,
            "description": payload.description,
            "enabled": payload.enabled_globally,
        },
    )
    flag = result.fetchone()
    await db.commit()

    return {
        "id": flag.id,
        "key": flag.key,
        "name": flag.name,
        "description": flag.description,
        "enabled_globally": flag.enabled_globally,
        "created_at": str(flag.created_at),
        "updated_at": str(flag.updated_at),
    }


@router.put("/{key}")
async def update_flag(
    key: str,
    payload: FeatureFlagUpdate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Update a feature flag."""
    updates = []
    params = {"key": key}

    if payload.name is not None:
        updates.append("name = :name")
        params["name"] = payload.name
    if payload.description is not None:
        updates.append("description = :description")
        params["description"] = payload.description
    if payload.enabled_globally is not None:
        updates.append("enabled_globally = :enabled")
        params["enabled"] = payload.enabled_globally

    if not updates:
        raise HTTPException(status_code=400, detail="No fields to update")

    updates.append("updated_at = NOW()")

    result = await db.execute(
        text(
            f"""
            UPDATE feature_flags
            SET {", ".join(updates)}
            WHERE key = :key
            RETURNING id, key, name, description, enabled_globally, created_at, updated_at
        """
        ),
        params,
    )
    flag = result.fetchone()
    if not flag:
        raise HTTPException(status_code=404, detail="Flag not found")

    await db.commit()

    return {
        "id": flag.id,
        "key": flag.key,
        "name": flag.name,
        "description": flag.description,
        "enabled_globally": flag.enabled_globally,
        "created_at": str(flag.created_at),
        "updated_at": str(flag.updated_at),
    }


@router.delete("/{key}", status_code=204)
async def delete_flag(
    key: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Delete a feature flag."""
    result = await db.execute(
        text("DELETE FROM feature_flags WHERE key = :key RETURNING id"), {"key": key}
    )
    if not result.scalar():
        raise HTTPException(status_code=404, detail="Flag not found")
    await db.commit()
