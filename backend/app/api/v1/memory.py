"""Memory API routes — sessions, memories, search, and extraction."""

import logging
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.database import get_db
from app.models.memory_models import Memory, MemorySession
from app.models.user import User

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/memory", tags=["memory"])


def _not_found() -> HTTPException:
    return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found")


@router.get("")
async def list_memories(
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    offset = (page - 1) * limit

    count_q = select(func.count(Memory.id)).where(Memory.user_id == user.id)
    total = (await db.execute(count_q)).scalar() or 0

    q = (
        select(Memory)
        .where(Memory.user_id == user.id)
        .order_by(Memory.created_at.desc())
        .offset(offset)
        .limit(limit)
    )
    result = await db.execute(q)
    memories = result.scalars().all()

    return {
        "memories": [
            {
                "id": str(m.id),
                "session_id": str(m.session_id),
                "content": m.content,
                "embedding": None,  # don't return large embeddings
                "metadata": m.meta or {},
                "created_at": m.created_at.isoformat() if m.created_at else "",
                "updated_at": m.updated_at.isoformat() if m.updated_at else "",
            }
            for m in memories
        ],
        "total": total,
        "page": page,
        "limit": limit,
    }


@router.get("/sessions")
async def list_sessions(
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    offset = (page - 1) * limit

    count_q = select(func.count(MemorySession.id)).where(MemorySession.user_id == user.id)
    total = (await db.execute(count_q)).scalar() or 0

    q = (
        select(MemorySession)
        .where(MemorySession.user_id == user.id)
        .order_by(MemorySession.created_at.desc())
        .offset(offset)
        .limit(limit)
    )
    result = await db.execute(q)
    sessions = result.scalars().all()

    # Get memory counts per session
    session_ids = [s.id for s in sessions]
    mem_counts = {}
    if session_ids:
        count_result = await db.execute(
            select(Memory.session_id, func.count(Memory.id))
            .where(Memory.session_id.in_(session_ids))
            .group_by(Memory.session_id)
        )
        mem_counts = {row[0]: row[1] for row in count_result.all()}

    return {
        "sessions": [
            {
                "id": str(s.id),
                "user_id": str(s.user_id),
                "title": s.title,
                "description": s.description,
                "memory_count": mem_counts.get(s.id, 0),
                "created_at": s.created_at.isoformat() if s.created_at else "",
                "updated_at": s.updated_at.isoformat() if s.updated_at else "",
            }
            for s in sessions
        ],
        "total": total,
    }


@router.get("/sessions/{session_id}")
async def get_session(
    session_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    result = await db.execute(
        select(MemorySession).where(
            MemorySession.id == session_id,
            MemorySession.user_id == user.id,
        )
    )
    session = result.scalar_one_or_none()
    if not session:
        raise _not_found()

    mem_count_q = select(func.count(Memory.id)).where(Memory.session_id == session_id)
    mem_count = (await db.execute(mem_count_q)).scalar() or 0

    return {
        "session": {
            "id": str(session.id),
            "user_id": str(session.user_id),
            "title": session.title,
            "description": session.description,
            "memory_count": mem_count,
            "created_at": session.created_at.isoformat() if session.created_at else "",
            "updated_at": session.updated_at.isoformat() if session.updated_at else "",
        }
    }


@router.get("/{memory_id}")
async def get_memory(
    memory_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    result = await db.execute(
        select(Memory).where(
            Memory.id == memory_id,
            Memory.user_id == user.id,
        )
    )
    memory = result.scalar_one_or_none()
    if not memory:
        raise _not_found()

    return {
        "memory": {
            "id": str(memory.id),
            "session_id": str(memory.session_id),
            "content": memory.content,
            "embedding": None,
            "metadata": memory.meta or {},
            "created_at": memory.created_at.isoformat() if memory.created_at else "",
            "updated_at": memory.updated_at.isoformat() if memory.updated_at else "",
        }
    }


@router.post("/search")
async def search_memories(
    payload: dict,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Search memories by text query (simple LIKE search)."""
    query_text = payload.get("query", "")
    if not query_text:
        return {"results": [], "total": 0, "query": ""}

    q = (
        select(Memory)
        .where(
            Memory.user_id == user.id,
            Memory.content.ilike(f"%{query_text}%"),
        )
        .order_by(Memory.created_at.desc())
        .limit(50)
    )
    result = await db.execute(q)
    memories = result.scalars().all()

    return {
        "results": [
            {
                "id": str(m.id),
                "session_id": str(m.session_id),
                "content": m.content,
                "metadata": m.meta or {},
                "created_at": m.created_at.isoformat() if m.created_at else "",
            }
            for m in memories
        ],
        "total": len(memories),
        "query": query_text,
    }


@router.post("/extract")
async def extract_memories(
    payload: dict,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Extract memories from a mission or text content."""
    mission_id = payload.get("mission_id")
    text_content = payload.get("content", "")
    session_id = payload.get("session_id")

    if not text_content and not mission_id:
        raise HTTPException(status_code=400, detail="content or mission_id required")

    # If mission_id provided, try to get mission output
    if mission_id and not text_content:
        from app.models.mission_models import Mission
        result = await db.execute(select(Mission).where(Mission.id == mission_id))
        mission = result.scalar_one_or_none()
        if mission and mission.results:
            text_content = str(mission.results)[:10000]

    if not text_content:
        return {"extracted_memories": [], "session_id": None, "count": 0}

    # Create or get session
    if not session_id:
        session = MemorySession(
            user_id=user.id,
            title=f"Extraction {datetime.now(UTC).strftime('%Y-%m-%d %H:%M')}",
        )
        db.add(session)
        await db.flush()
        session_id = str(session.id)

    # Simple extraction: split text into meaningful chunks
    sentences = [s.strip() for s in text_content.replace("\n", ". ").split(". ") if len(s.strip()) > 20]

    extracted = []
    for sentence in sentences[:20]:  # limit to 20 memories per extraction
        memory = Memory(
            session_id=session_id,
            user_id=user.id,
            content=sentence.strip().rstrip(".") + ".",
            meta={"source": "extraction", "mission_id": mission_id} if mission_id else {"source": "extraction"},
            source_mission_id=mission_id,
        )
        db.add(memory)
        extracted.append(memory)

    await db.flush()

    return {
        "extracted_memories": [
            {
                "id": str(m.id),
                "content": m.content,
            }
            for m in extracted
        ],
        "session_id": session_id,
        "count": len(extracted),
    }
