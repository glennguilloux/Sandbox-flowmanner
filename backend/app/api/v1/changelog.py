"""
Changelog API

GET /api/changelog — list published entries (all users)
GET /api/changelog/latest — get latest entries since date
POST /api/changelog — create entry (admin)
PUT /api/changelog/{id} — update entry (admin)
DELETE /api/changelog/{id} — delete entry (admin)
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.database import get_db
from app.models.user import User

router = APIRouter(prefix="/changelog", tags=["changelog"])


class ChangelogCreate(BaseModel):
    version: str
    title: str
    content: str
    entry_type: str = "feature"  # feature, fix, improvement, breaking
    published: bool = False


class ChangelogUpdate(BaseModel):
    version: str | None = None
    title: str | None = None
    content: str | None = None
    entry_type: str | None = None
    published: bool | None = None


@router.get("")
async def list_changelog(
    limit: int = Query(50, ge=1, le=100),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List published changelog entries."""
    result = await db.execute(
        text(
            """
            SELECT id, version, title, content, entry_type, published_at, created_at
            FROM changelog_entries
            WHERE published = true
            ORDER BY published_at DESC
            LIMIT :limit
        """
        ),
        {"limit": limit},
    )
    entries = result.fetchall()

    return {
        "entries": [
            {
                "id": e.id,
                "version": e.version,
                "title": e.title,
                "content": e.content,
                "type": e.entry_type,
                "published_at": str(e.published_at) if e.published_at else None,
                "created_at": str(e.created_at) if e.created_at else None,
            }
            for e in entries
        ]
    }


@router.get("/latest")
async def latest_changelog(
    since: str | None = Query(None, description="ISO date string"),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get latest changelog entries, optionally since a date."""
    if since:
        result = await db.execute(
            text(
                """
                SELECT id, version, title, content, entry_type, published_at
                FROM changelog_entries
                WHERE published = true AND published_at > :since
                ORDER BY published_at DESC
                LIMIT 10
            """
            ),
            {"since": since},
        )
    else:
        result = await db.execute(
            text(
                """
                SELECT id, version, title, content, entry_type, published_at
                FROM changelog_entries
                WHERE published = true
                ORDER BY published_at DESC
                LIMIT 5
            """
            )
        )

    entries = result.fetchall()
    return {
        "entries": [
            {
                "id": e.id,
                "version": e.version,
                "title": e.title,
                "content": e.content,
                "type": e.entry_type,
                "published_at": str(e.published_at) if e.published_at else None,
            }
            for e in entries
        ]
    }


@router.post("", status_code=201)
async def create_changelog_entry(
    payload: ChangelogCreate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Create a new changelog entry (admin only)."""
    published_at = "NOW()" if payload.published else "NULL"

    result = await db.execute(
        text(
            f"""
            INSERT INTO changelog_entries (version, title, content, entry_type, published, published_at, created_at)
            VALUES (:version, :title, :content, :entry_type, :published, {published_at}, NOW())
            RETURNING id, version, title, content, entry_type, published, published_at, created_at
        """
        ),
        {
            "version": payload.version,
            "title": payload.title,
            "content": payload.content,
            "entry_type": payload.entry_type,
            "published": payload.published,
        },
    )
    entry = result.fetchone()
    await db.commit()

    return {
        "id": entry.id,
        "version": entry.version,
        "title": entry.title,
        "content": entry.content,
        "type": entry.entry_type,
        "published": entry.published,
        "published_at": str(entry.published_at) if entry.published_at else None,
        "created_at": str(entry.created_at),
    }


@router.put("/{entry_id}")
async def update_changelog_entry(
    entry_id: int,
    payload: ChangelogUpdate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Update a changelog entry."""
    updates = []
    params = {"id": entry_id}

    if payload.version is not None:
        updates.append("version = :version")
        params["version"] = payload.version
    if payload.title is not None:
        updates.append("title = :title")
        params["title"] = payload.title
    if payload.content is not None:
        updates.append("content = :content")
        params["content"] = payload.content
    if payload.entry_type is not None:
        updates.append("entry_type = :entry_type")
        params["entry_type"] = payload.entry_type
    if payload.published is not None:
        updates.append("published = :published")
        params["published"] = payload.published
        if payload.published:
            updates.append("published_at = NOW()")

    if not updates:
        raise HTTPException(status_code=400, detail="No fields to update")

    result = await db.execute(
        text(
            f"""
            UPDATE changelog_entries
            SET {', '.join(updates)}
            WHERE id = :id
            RETURNING id, version, title, content, entry_type, published, published_at, created_at
        """
        ),
        params,
    )
    entry = result.fetchone()
    if not entry:
        raise HTTPException(status_code=404, detail="Entry not found")

    await db.commit()

    return {
        "id": entry.id,
        "version": entry.version,
        "title": entry.title,
        "content": entry.content,
        "type": entry.entry_type,
        "published": entry.published,
        "published_at": str(entry.published_at) if entry.published_at else None,
        "created_at": str(entry.created_at),
    }


@router.delete("/{entry_id}", status_code=204)
async def delete_changelog_entry(
    entry_id: int,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Delete a changelog entry."""
    result = await db.execute(
        text("DELETE FROM changelog_entries WHERE id = :id RETURNING id"),
        {"id": entry_id},
    )
    if not result.scalar():
        raise HTTPException(status_code=404, detail="Entry not found")
    await db.commit()
