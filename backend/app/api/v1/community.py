"""Community template routes — creates and manages community_templates table.

The community_templates table does NOT exist yet in the DB.
It will be created via psql before first use.
"""

import json
from datetime import UTC

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.database import get_db
from app.models.user import User

router = APIRouter(prefix="/community", tags=["community"])


def _json(val):
    if not val:
        return {}
    try:
        return json.loads(val) if isinstance(val, str) else val
    except Exception:
        return {}


def _dt(dt):
    return dt.isoformat() if dt else None


async def _ensure_table(db: AsyncSession):
    """Create community_templates table if it doesn't exist."""
    await db.execute(text("""
        CREATE TABLE IF NOT EXISTS community_templates (
            id VARCHAR(36) NOT NULL PRIMARY KEY,
            title VARCHAR(255) NOT NULL,
            description TEXT NOT NULL,
            author_id VARCHAR(36) NOT NULL,
            author_name VARCHAR(100) NOT NULL,
            category VARCHAR(50) NOT NULL,
            tags TEXT,
            content TEXT,
            rating FLOAT DEFAULT 0.0,
            rating_count INTEGER DEFAULT 0,
            fork_count INTEGER DEFAULT 0,
            use_count INTEGER DEFAULT 0,
            is_featured BOOLEAN DEFAULT false,
            created_at TIMESTAMP WITH TIME ZONE DEFAULT now(),
            updated_at TIMESTAMP WITH TIME ZONE DEFAULT now()
        )
    """))
    await db.commit()


async def _ensure_comments_table(db: AsyncSession):
    """Create community_comments table if it doesn't exist."""
    await _ensure_table(db)
    await db.execute(text("""
        CREATE TABLE IF NOT EXISTS community_comments (
            id VARCHAR(36) NOT NULL PRIMARY KEY,
            template_id VARCHAR(36) NOT NULL REFERENCES community_templates(id) ON DELETE CASCADE,
            user_id INTEGER NOT NULL REFERENCES users(id),
            author_name VARCHAR(100) NOT NULL DEFAULT '',
            parent_id VARCHAR(36) REFERENCES community_comments(id) ON DELETE CASCADE,
            content TEXT NOT NULL,
            is_deleted BOOLEAN NOT NULL DEFAULT false,
            created_at TIMESTAMP WITH TIME ZONE DEFAULT now(),
            updated_at TIMESTAMP WITH TIME ZONE DEFAULT now()
        )
    """))
    await db.execute(text("""
        CREATE INDEX IF NOT EXISTS ix_community_comments_template_id
        ON community_comments (template_id)
    """))
    await db.execute(text("""
        CREATE INDEX IF NOT EXISTS ix_community_comments_parent_id
        ON community_comments (parent_id)
    """))
    await db.commit()


# ── Templates ─────────────────────────────────────────────────────────

@router.get("/templates")
async def list_templates(
    page: int = Query(1),
    limit: int = Query(20),
    category: str | None = Query(None),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    await _ensure_table(db)
    conditions = []
    params = {"lim": limit, "off": (page - 1) * limit}
    if category:
        conditions.append("category = :cat")
        params["cat"] = category
    where_clause = " WHERE " + " AND ".join(conditions) if conditions else ""
    count_r = await db.execute(text("SELECT COUNT(*) FROM community_templates" + where_clause), params)
    rows_r = await db.execute(text("SELECT id, title, description, author_id, author_name, category, tags, content, rating, rating_count, fork_count, use_count, is_featured, created_at, updated_at FROM community_templates" + where_clause + " ORDER BY created_at DESC LIMIT :lim OFFSET :off"), params)
    templates = []
    for r in rows_r.fetchall():
        templates.append({"id": str(r[0]), "title": r[1], "description": r[2], "author_id": str(r[3]), "author_name": r[4], "category": r[5], "tags": _json(r[6]) if r[6] else [], "content": _json(r[7]) if r[7] else {}, "rating": float(r[8] or 0), "rating_count": r[9] or 0, "fork_count": r[10] or 0, "use_count": r[11] or 0, "is_featured": r[12] or False, "created_at": _dt(r[13]) or "", "updated_at": _dt(r[14]) or ""})
    return {"templates": templates, "total": count_r.scalar() or 0, "page": page, "limit": limit}


@router.get("/templates/{template_id}")
async def get_template(template_id: str, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    await _ensure_table(db)
    r = await db.execute(text("SELECT id, title, description, author_id, author_name, category, tags, content, rating, rating_count, fork_count, use_count, is_featured, created_at, updated_at FROM community_templates WHERE id=:id"), {"id": template_id})
    row = r.fetchone()
    if not row: raise HTTPException(404, "Template not found")
    return {"template": {"id": str(row[0]), "title": row[1], "description": row[2], "author_id": str(row[3]), "author_name": row[4], "category": row[5], "tags": _json(row[6]) if row[6] else [], "content": _json(row[7]) if row[7] else {}, "rating": float(row[8] or 0), "rating_count": row[9] or 0, "fork_count": row[10] or 0, "use_count": row[11] or 0, "is_featured": row[12] or False, "created_at": _dt(row[13]) or "", "updated_at": _dt(row[14]) or ""}}


@router.post("/templates")
async def create_template(data: dict, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    import uuid
    await _ensure_table(db)
    tid = str(uuid.uuid4())
    tags = json.dumps(data.get("tags", []))
    content = json.dumps(data.get("content", {}))
    await db.execute(text("INSERT INTO community_templates (id, title, description, author_id, author_name, category, tags, content, created_at, updated_at) VALUES (:id, :title, :desc, :aid, :aname, :cat, :tags, :content, NOW(), NOW())"), {"id": tid, "title": data.get("name", data.get("title", "")), "desc": data.get("description", ""), "aid": str(user.id), "aname": user.username if hasattr(user, 'username') else str(user.id), "cat": data.get("category", "general"), "tags": tags, "content": content})
    await db.commit()
    return await get_template(tid, db, user)


@router.put("/templates/{template_id}")
async def update_template(template_id: str, data: dict, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    # Verify ownership before allowing update
    existing = await db.execute(text("SELECT author_id FROM community_templates WHERE id = :id"), {"id": template_id})
    row = existing.fetchone()
    if not row:
        raise HTTPException(404, "Template not found")
    if str(row[0]) != str(user.id):
        raise HTTPException(403, "You can only update your own templates")
    # Whitelist allowed fields to prevent SQL injection
    ALLOWED_FIELDS = {"title", "description", "category", "tags", "content"}
    sets = []
    params = {"id": template_id}
    if "title" in data or "name" in data:
        sets.append("title = :title")
        params["title"] = data.get("title", data.get("name", ""))
    if "description" in data:
        sets.append("description = :desc")
        params["desc"] = data["description"]
    if "category" in data:
        sets.append("category = :cat")
        params["cat"] = data["category"]
    if not sets:
        raise HTTPException(400, "No valid fields to update")
    sets.append("updated_at = NOW()")
    await db.execute(text("UPDATE community_templates SET " + ", ".join(sets) + " WHERE id = :id"), params)
    await db.commit()
    return await get_template(template_id, db, user)


@router.delete("/templates/{template_id}")
async def delete_template(template_id: str, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    # Verify ownership before allowing delete
    existing = await db.execute(text("SELECT author_id FROM community_templates WHERE id = :id"), {"id": template_id})
    row = existing.fetchone()
    if not row:
        raise HTTPException(404, "Template not found")
    if str(row[0]) != str(user.id):
        raise HTTPException(403, "You can only delete your own templates")
    r = await db.execute(text("DELETE FROM community_templates WHERE id = :id"), {"id": template_id})
    await db.commit()
    if r.rowcount == 0:
        raise HTTPException(404, "Template not found")
    return {"ok": True}


@router.post("/templates/{template_id}/rate")
async def rate_template(template_id: str, data: dict, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    rating = data.get("rating", 0)
    await db.execute(text("UPDATE community_templates SET rating = ((rating * rating_count) + :r) / (rating_count + 1), rating_count = rating_count + 1, updated_at=NOW() WHERE id=:id"), {"id": template_id, "r": rating})
    await db.commit()
    return await get_template(template_id, db, user)


@router.post("/templates/{template_id}/fork")
async def fork_template(template_id: str, data: dict, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    await db.execute(text("UPDATE community_templates SET fork_count = fork_count + 1 WHERE id=:id"), {"id": template_id})
    await db.commit()
    return await get_template(template_id, db, user)


@router.get("/templates/{template_id}/comments")
async def get_comments(
    template_id: str,
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    include_deleted: bool = Query(False),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Return paginated comments for a template, with nested replies."""
    await _ensure_comments_table(db)

    # Verify template exists
    tpl = await db.execute(text("SELECT id FROM community_templates WHERE id = :id"), {"id": template_id})
    if not tpl.fetchone():
        raise HTTPException(404, "Template not found")

    deleted_filter = "" if include_deleted else "AND c.is_deleted = false"
    offset = (page - 1) * limit

    # Count total top-level comments (for pagination)
    count_r = await db.execute(
        text(f"SELECT COUNT(*) FROM community_comments c WHERE c.template_id = :tid AND c.parent_id IS NULL {deleted_filter}"),
        {"tid": template_id},
    )
    total = count_r.scalar() or 0

    # Fetch top-level comments (no parent) with pagination
    rows = await db.execute(
        text(f"""
            SELECT c.id, c.template_id, c.user_id, c.author_name, c.parent_id,
                   c.content, c.is_deleted, c.created_at, c.updated_at
            FROM community_comments c
            WHERE c.template_id = :tid AND c.parent_id IS NULL {deleted_filter}
            ORDER BY c.created_at DESC
            LIMIT :lim OFFSET :off
        """),
        {"tid": template_id, "lim": limit, "off": offset},
    )
    top_level = rows.fetchall()

    # Collect top-level IDs to fetch their replies
    top_ids = [str(r[0]) for r in top_level]
    replies_by_parent: dict[str, list[dict]] = {}
    if top_ids:
        placeholders = ", ".join(f":pid{i}" for i in range(len(top_ids)))
        reply_params = {f"pid{i}": tid for i, tid in enumerate(top_ids)}
        reply_r = await db.execute(
            text(f"""
                SELECT c.id, c.template_id, c.user_id, c.author_name, c.parent_id,
                       c.content, c.is_deleted, c.created_at, c.updated_at
                FROM community_comments c
                WHERE c.parent_id IN ({placeholders}) {deleted_filter}
                ORDER BY c.created_at ASC
            """),
            reply_params,
        )
        for r in reply_r.fetchall():
            pid = str(r[4])
            replies_by_parent.setdefault(pid, []).append({
                "id": str(r[0]), "template_id": str(r[1]), "user_id": r[2],
                "author_name": r[3] or "", "parent_id": str(r[4]),
                "content": "[deleted]" if r[6] else r[5],
                "is_deleted": r[6], "created_at": _dt(r[7]) or "", "updated_at": _dt(r[8]) or "",
            })

    comments = []
    for r in top_level:
        cid = str(r[0])
        comments.append({
            "id": cid, "template_id": str(r[1]), "user_id": r[2],
            "author_name": r[3] or "", "parent_id": None,
            "content": "[deleted]" if r[6] else r[5],
            "is_deleted": r[6], "created_at": _dt(r[7]) or "", "updated_at": _dt(r[8]) or "",
            "replies": replies_by_parent.get(cid, []),
        })

    return {"comments": comments, "total": total, "page": page, "limit": limit}


@router.post("/templates/{template_id}/comments")
async def add_comment(
    template_id: str,
    data: dict,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Create a comment (or threaded reply) on a template."""
    import uuid
    await _ensure_comments_table(db)

    # Verify template exists
    tpl = await db.execute(text("SELECT id FROM community_templates WHERE id = :id"), {"id": template_id})
    if not tpl.fetchone():
        raise HTTPException(404, "Template not found")

    content = (data.get("content") or "").strip()
    if not content:
        raise HTTPException(400, "Content is required")
    if len(content) > 5000:
        raise HTTPException(400, "Content must be 5000 characters or fewer")

    parent_id = data.get("parent_id")
    if parent_id:
        # Verify parent comment exists and belongs to the same template
        parent = await db.execute(
            text("SELECT id, template_id FROM community_comments WHERE id = :pid"),
            {"pid": parent_id},
        )
        parent_row = parent.fetchone()
        if not parent_row:
            raise HTTPException(404, "Parent comment not found")
        if str(parent_row[1]) != template_id:
            raise HTTPException(400, "Parent comment belongs to a different template")

    cid = str(uuid.uuid4())
    author_name = user.username if hasattr(user, "username") else str(user.id)
    await db.execute(
        text("""
            INSERT INTO community_comments (id, template_id, user_id, author_name, parent_id, content, created_at, updated_at)
            VALUES (:id, :tid, :uid, :aname, :pid, :content, NOW(), NOW())
        """),
        {"id": cid, "tid": template_id, "uid": user.id, "aname": author_name, "pid": parent_id, "content": content},
    )
    await db.commit()

    # Return updated total (top-level count, consistent with GET) + the new comment
    count_r = await db.execute(
        text("SELECT COUNT(*) FROM community_comments WHERE template_id = :tid AND parent_id IS NULL AND is_deleted = false"),
        {"tid": template_id},
    )
    total = count_r.scalar() or 0

    from datetime import datetime
    now_iso = datetime.now(UTC).isoformat()
    comment = {
        "id": cid, "template_id": template_id, "user_id": user.id,
        "author_name": author_name, "parent_id": parent_id,
        "content": content, "is_deleted": False,
        "created_at": now_iso, "updated_at": now_iso,
        "replies": [],
    }
    return {"comment": comment, "total": total}


# ── Other endpoints ───────────────────────────────────────────────────

@router.get("/featured")
async def get_featured(db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    await _ensure_table(db)
    r = await db.execute(text("SELECT id, title, description, author_id, author_name, category, tags, content, rating, rating_count, fork_count, use_count, is_featured, created_at, updated_at FROM community_templates WHERE is_featured=true ORDER BY rating DESC LIMIT 10"))
    templates = []
    for row in r.fetchall():
        templates.append({"id": str(row[0]), "title": row[1], "description": row[2], "author_id": str(row[3]), "author_name": row[4], "category": row[5], "tags": _json(row[6]) if row[6] else [], "content": _json(row[7]) if row[7] else {}, "rating": float(row[8] or 0), "rating_count": row[9] or 0, "fork_count": row[10] or 0, "use_count": row[11] or 0, "is_featured": row[12] or False, "created_at": _dt(row[13]) or "", "updated_at": _dt(row[14]) or ""})
    return {"templates": templates, "total": len(templates)}


@router.get("/categories")
async def get_categories(db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    # Count templates per category
        r = await db.execute(text("SELECT category, COUNT(*) FROM community_templates GROUP BY category"))
        counts = {row[0]: row[1] for row in r.fetchall()}
        cats = [
            {"id": "research", "name": "Research", "description": "Research and analysis templates", "template_count": counts.get("research", 0), "slug": "research"},
            {"id": "support", "name": "Support", "description": "Customer support templates", "template_count": counts.get("support", 0), "slug": "support"},
            {"id": "sales", "name": "Sales", "description": "Sales and lead qualification templates", "template_count": counts.get("sales", 0), "slug": "sales"},
            {"id": "engineering", "name": "Engineering", "description": "Code review and dev templates", "template_count": counts.get("engineering", 0), "slug": "engineering"},
            {"id": "productivity", "name": "Productivity", "description": "Productivity and automation templates", "template_count": counts.get("productivity", 0), "slug": "productivity"},
        ]
        return {"categories": cats}


@router.get("/trending")
async def get_trending(limit: int = Query(10), db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    await _ensure_table(db)
    r = await db.execute(text("SELECT id, title, description, author_id, author_name, category, tags, content, rating, rating_count, fork_count, use_count, is_featured, created_at, updated_at FROM community_templates ORDER BY use_count DESC LIMIT :lim"), {"lim": limit})
    templates = []
    for row in r.fetchall():
        templates.append({"id": str(row[0]), "title": row[1], "description": row[2], "author_id": str(row[3]), "author_name": row[4], "category": row[5], "tags": _json(row[6]) if row[6] else [], "content": _json(row[7]) if row[7] else {}, "rating": float(row[8] or 0), "rating_count": row[9] or 0, "fork_count": row[10] or 0, "use_count": row[11] or 0, "is_featured": row[12] or False, "created_at": _dt(row[13]) or "", "updated_at": _dt(row[14]) or ""})
    return {"templates": templates, "total": len(templates)}


@router.get("/stats")
async def get_stats(db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    await _ensure_table(db)
    # Aggregate template stats
    r = await db.execute(text("SELECT COUNT(*), COALESCE(SUM(use_count),0), COALESCE(SUM(fork_count),0), COALESCE(AVG(rating),0) FROM community_templates"))
    row = r.fetchone()
    # Real user count: total workspace members
    users_r = await db.execute(text("SELECT COUNT(DISTINCT user_id) FROM workspace_members"))
    total_users = users_r.scalar() or 0
    # Real ratings count: sum of all rating_count values
    ratings_r = await db.execute(text("SELECT COALESCE(SUM(rating_count), 0) FROM community_templates"))
    total_ratings = ratings_r.scalar() or 0
    # Top 5 categories by template count
    cats_r = await db.execute(text("SELECT category, COUNT(*) AS cnt FROM community_templates GROUP BY category ORDER BY cnt DESC LIMIT 5"))
    top_categories = [{"category": row_c[0], "count": row_c[1]} for row_c in cats_r.fetchall()]
    return {"total_templates": row[0] or 0, "total_users": total_users, "total_forks": row[2] or 0, "total_ratings": total_ratings, "avg_rating": float(row[3] or 0), "top_categories": top_categories}
