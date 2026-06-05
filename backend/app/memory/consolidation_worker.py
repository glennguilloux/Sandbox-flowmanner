"""Episodic memory consolidation worker (H5).

Ingests completed mission payloads, extracts episode tuples
(context/action/outcome/success), and stores them as persistent
Memory records using the existing SQLAlchemy Memory/MemorySession models.

Provides an adapter boundary for future RabbitMQ subscription
(just the ingest API — no celery/RabbitMQ wiring).

Includes a configurable 90-day retention policy hook.
"""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, Any
from uuid import uuid4

from sqlalchemy import delete, select

from app.models.memory_models import Memory, MemorySession

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

# ── Retention config ───────────────────────────────────────────────

_RETENTION_DAYS = 90  # overridable for tests


def _utcnow() -> datetime:
    return datetime.now(UTC)


class MemoryConsolidationWorker:
    """Ingests mission payloads and persists episodic memories.

    Usage::

        worker = MemoryConsolidationWorker()
        await worker.process_mission(db, mission_id="...", user_id=1, payload={...})
        await worker.apply_retention(db)
    """

    async def process_mission(
        self,
        db: AsyncSession,
        mission_id: str,
        user_id: int,
        payload: dict[str, Any],
    ) -> dict[str, str]:
        """Extract episode tuple and store as a Memory record.

        Returns a dict with ``session_id`` and ``memory_id``.
        """
        success_flag = payload.get("status") in (
            "completed",
            "approved",
            MissionStatus.COMPLETED,
            MissionStatus.APPROVED,
        )

        episode = {
            "context": payload.get("title", "") or "",
            "action": payload.get("plan") or {},
            "outcome": payload.get("results") or {},
            "success": success_flag,
            "error": payload.get("error_message") or None,
        }

        session = MemorySession(
            id=str(uuid4()),
            user_id=user_id,
            title=f"Consolidated Mission: {mission_id[:8]}",
            description=f"Auto-consolidated episodes from mission {mission_id}",
        )
        db.add(session)
        await db.flush()

        memory = Memory(
            id=str(uuid4()),
            session_id=session.id,
            user_id=user_id,
            content=json.dumps(episode, default=str),
            source_mission_id=mission_id,
            meta={
                "type": "episode_tuple",
                "mission_id": mission_id,
                "success": success_flag,
            },
        )
        db.add(memory)
        await db.commit()

        logger.info(
            "Consolidated episode for mission %s (success=%s)",
            mission_id,
            success_flag,
        )
        return {"session_id": session.id, "memory_id": memory.id}

    async def retrieve_by_mission(
        self,
        db: AsyncSession,
        mission_id: str,
    ) -> list[dict[str, Any]]:
        """Retrieve all episode memories for a given mission."""
        result = await db.execute(
            select(Memory).where(Memory.source_mission_id == mission_id)
        )
        memories = result.scalars().all()
        return [
            {
                "id": m.id,
                "session_id": m.session_id,
                "content": json.loads(m.content),
                "meta": m.meta,
                "created_at": m.created_at.isoformat() if m.created_at else None,
            }
            for m in memories
        ]

    async def retrieve_by_agent(
        self,
        db: AsyncSession,
        agent_id: str,
        limit: int = 20,
    ) -> list[dict[str, Any]]:
        """Retrieve episode memories whose metadata references ``agent_id``."""
        result = await db.execute(
            select(Memory)
            .where(Memory.meta["agent_id"].as_string() == agent_id)
            .order_by(Memory.created_at.desc())
            .limit(limit)
        )
        memories = result.scalars().all()
        return [
            {
                "id": m.id,
                "session_id": m.session_id,
                "content": json.loads(m.content),
                "meta": m.meta,
                "created_at": m.created_at.isoformat() if m.created_at else None,
            }
            for m in memories
        ]

    async def apply_retention(
        self,
        db: AsyncSession,
        retention_days: int | None = None,
    ) -> int:
        """Delete MemorySession records older than *retention_days* (default 90).

        Returns the number of sessions deleted.
        """
        days = retention_days if retention_days is not None else _RETENTION_DAYS
        cutoff = _utcnow() - timedelta(days=days)

        result = await db.execute(
            delete(MemorySession).where(MemorySession.created_at < cutoff)
        )
        await db.commit()

        deleted = result.rowcount
        if deleted:
            logger.info(
                "Retention pruned %d old memory sessions (cutoff=%s)",
                deleted,
                cutoff.isoformat(),
            )
        return deleted


# Lazy import to avoid circular deps at module level
from app.models.mission_models import MissionStatus

# ── Singleton ──────────────────────────────────────────────────────

_worker: MemoryConsolidationWorker | None = None


def get_consolidation_worker() -> MemoryConsolidationWorker:
    global _worker
    if _worker is None:
        _worker = MemoryConsolidationWorker()
    return _worker
