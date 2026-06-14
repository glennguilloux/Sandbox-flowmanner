"""MemoryExtractionPauseService (D30-60, T30 — pause toggle).

Operational service that manages the per-conversation pause toggle. The
extractor (T20's ``PersonalMemoryExtractor``) consults ``is_paused()``
before extracting any new claims; the chat UI calls ``pause_conversation()``
and ``resume_conversation()`` to drive the toggle.

Critical guardrails (from the End-of-Galaxy plan §3):

* **Every read query filters by ``(user_id, workspace_id)`` together.**
  Pauses are workspace-scoped to prevent cross-tenant leakage of pause
  state (a workspace that pauses "stop extracting" should not affect
  any other workspace's conversations).
* **No ``db.commit()``** — per ``services/AGENTS.md`` rule 3. The
  caller (route / CQRS handler) owns the transaction.
* **TTL-only pauses.** There is no "pause forever" path; the
  ``MIN_TTL_SECONDS`` / ``MAX_TTL_SECONDS`` bounds reject out-of-range
  TTLs at the service layer. A future task can add a "permanent pause"
  by extending the model (e.g. an ``is_permanent`` boolean column) —
  it is intentionally not in this slice.
"""
from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import and_, delete, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.memory_extraction_pause_models import MemoryExtractionPause

logger = logging.getLogger(__name__)


# ── Exception hierarchy ────────────────────────────────────────────────


class MemoryExtractionPauseError(Exception):
    """Base for all pause-service errors."""


class MemoryExtractionPauseValidationError(
    MemoryExtractionPauseError, ValueError
):
    """Raised for input validation failures (bad TTL, missing fields).
    Inherits from both the service base and ``ValueError`` so callers
    can use either ``except ValueError`` (Pythonic) or
    ``except MemoryExtractionPauseValidationError`` (specific)."""


# ── TTL bounds ─────────────────────────────────────────────────────────


# Minimum pause length: 60 seconds. Shorter pauses are almost
# certainly typos / test noise.
MIN_TTL_SECONDS = 60

# Maximum pause length: 7 days. Longer pauses are intentionally
# rejected at the service layer — the privacy story is "short TTL
# only, opt-in, never silent permanent" (per the strategic plan).
# A user who wants to pause longer can re-pause when the prior
# pause expires.
MAX_TTL_SECONDS = 7 * 24 * 60 * 60  # 7 days


# ── Service ────────────────────────────────────────────────────────────


class MemoryExtractionPauseService:
    """Operational service for the per-conversation pause toggle.

    Per ``services/AGENTS.md`` rule 3: this service NEVER calls
    ``db.commit()``. The caller (route / CQRS handler) owns the
    transaction.
    """

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    # ── Validation helpers ──────────────────────────────────────────

    @staticmethod
    def _validate_ttl(ttl_seconds: int) -> None:
        if not isinstance(ttl_seconds, int):
            raise MemoryExtractionPauseValidationError(
                f"ttl_seconds must be an int; got {type(ttl_seconds).__name__}"
            )
        if ttl_seconds < MIN_TTL_SECONDS:
            raise MemoryExtractionPauseValidationError(
                f"ttl_seconds must be >= {MIN_TTL_SECONDS}; got {ttl_seconds!r}"
            )
        if ttl_seconds > MAX_TTL_SECONDS:
            raise MemoryExtractionPauseValidationError(
                f"ttl_seconds must be <= {MAX_TTL_SECONDS} (7 days); "
                f"got {ttl_seconds!r}"
            )

    @staticmethod
    def _validate_conversation_id(conversation_id: str) -> None:
        if not conversation_id or not isinstance(conversation_id, str):
            raise MemoryExtractionPauseValidationError(
                "conversation_id must be a non-empty string"
            )
        if len(conversation_id) > 100:
            raise MemoryExtractionPauseValidationError(
                f"conversation_id must be <= 100 chars; "
                f"got {len(conversation_id)}"
            )

    @staticmethod
    def _validate_reason(reason: str | None) -> None:
        if reason is None:
            return
        if not isinstance(reason, str):
            raise MemoryExtractionPauseValidationError(
                f"reason must be a string; got {type(reason).__name__}"
            )
        if len(reason) > 500:
            raise MemoryExtractionPauseValidationError(
                f"reason must be <= 500 chars; got {len(reason)}"
            )

    # ── Write: pause_conversation ───────────────────────────────────

    async def pause_conversation(
        self,
        *,
        user_id: int,
        workspace_id: str,
        conversation_id: str,
        ttl_seconds: int,
        reason: str | None = None,
    ) -> MemoryExtractionPause:
        """Create a new pause row with the given TTL.

        Each call writes a new row — repeated calls stack (a user who
        pauses twice gets two rows, the latest one wins on
        ``is_paused`` because the lookup is "any non-expired row
        exists for this conversation"). This avoids a race where a
        resume() lands between a pause() and its write.

        Validates the TTL and reason at the service layer. Returns the
        new (flushed, refreshed) row.
        """
        self._validate_ttl(ttl_seconds)
        self._validate_conversation_id(conversation_id)
        self._validate_reason(reason)

        now = datetime.now(UTC)
        expires_at = now + timedelta(seconds=ttl_seconds)

        pause = MemoryExtractionPause(
            user_id=user_id,
            workspace_id=workspace_id,
            conversation_id=conversation_id,
            expires_at=expires_at,
            reason=reason,
        )
        self.db.add(pause)
        await self.db.flush()
        await self.db.refresh(pause)
        logger.info(
            "memory_extraction.paused id=%s user_id=%s workspace_id=%s "
            "conversation_id=%s ttl_seconds=%d expires_at=%s",
            pause.id,
            user_id,
            workspace_id,
            conversation_id,
            ttl_seconds,
            expires_at.isoformat(),
        )
        return pause

    # ── Write: resume_conversation ───────────────────────────────────

    async def resume_conversation(
        self,
        *,
        user_id: int,
        workspace_id: str,
        conversation_id: str,
    ) -> int:
        """Hard-delete ALL non-expired pause rows for this conversation.

        Returns the count of rows removed. Idempotent: a resume() on
        a never-paused conversation returns 0 and is a no-op.

        "Hard delete" (not soft-delete) is intentional: pauses are
        operational state, not audit data. The audit trail of pause /
        resume actions belongs in ``memory_correction_events`` (T29)
        and is logged separately by the caller.
        """
        now = datetime.now(UTC)
        result = await self.db.execute(
            delete(MemoryExtractionPause).where(
                and_(
                    MemoryExtractionPause.user_id == user_id,
                    MemoryExtractionPause.workspace_id == workspace_id,
                    MemoryExtractionPause.conversation_id == conversation_id,
                    MemoryExtractionPause.expires_at > now,
                )
            )
        )
        removed = result.rowcount or 0
        logger.info(
            "memory_extraction.resumed user_id=%s workspace_id=%s "
            "conversation_id=%s removed=%d",
            user_id,
            workspace_id,
            conversation_id,
            removed,
        )
        return int(removed)

    # ── Read: is_paused ──────────────────────────────────────────────

    async def is_paused(
        self,
        *,
        user_id: int,
        workspace_id: str,
        conversation_id: str,
    ) -> bool:
        """Return True iff any non-expired pause row exists for this
        conversation. Cheap single-row check (LIMIT 1) on the composite
        index ``(user_id, workspace_id, conversation_id, expires_at)``.
        """
        now = datetime.now(UTC)
        result = await self.db.execute(
            select(MemoryExtractionPause.id)
            .where(
                and_(
                    MemoryExtractionPause.user_id == user_id,
                    MemoryExtractionPause.workspace_id == workspace_id,
                    MemoryExtractionPause.conversation_id == conversation_id,
                    MemoryExtractionPause.expires_at > now,
                )
            )
            .limit(1)
        )
        return result.scalar_one_or_none() is not None

    # ── Read: list_active_pauses ─────────────────────────────────────

    async def list_active_pauses(
        self,
        *,
        user_id: int,
        workspace_id: str,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[MemoryExtractionPause], int]:
        """Paginated listing of all non-expired pauses for the user.

        Returns ``(items, total_count)`` ordered by ``expires_at DESC``
        (longest-running pauses first). Always filters by
        ``(user_id, workspace_id)``.
        """
        now = datetime.now(UTC)
        where_clause = and_(
            MemoryExtractionPause.user_id == user_id,
            MemoryExtractionPause.workspace_id == workspace_id,
            MemoryExtractionPause.expires_at > now,
        )

        total = (
            await self.db.execute(
                select(func.count())
                .select_from(MemoryExtractionPause)
                .where(where_clause)
            )
        ).scalar_one()

        items = list(
            (
                await self.db.execute(
                    select(MemoryExtractionPause)
                    .where(where_clause)
                    .order_by(MemoryExtractionPause.expires_at.desc())
                    .offset(offset)
                    .limit(limit)
                )
            )
            .scalars()
            .all()
        )
        return items, int(total)

    # ── Maintenance: cleanup_expired ─────────────────────────────────

    async def cleanup_expired(
        self,
        *,
        user_id: int | None = None,
        workspace_id: str | None = None,
    ) -> int:
        """Delete all expired pause rows. Returns the count removed.

        When called from a per-user context (the route layer, after
        a pause/resume), ``user_id`` and ``workspace_id`` scope the
        sweep. When called from a cron / maintenance context, both
        can be None to sweep the entire table.
        """
        now = datetime.now(UTC)
        stmt = delete(MemoryExtractionPause).where(
            MemoryExtractionPause.expires_at <= now
        )
        if user_id is not None:
            stmt = stmt.where(MemoryExtractionPause.user_id == user_id)
        if workspace_id is not None:
            stmt = stmt.where(
                MemoryExtractionPause.workspace_id == workspace_id
            )
        result = await self.db.execute(stmt)
        removed = result.rowcount or 0
        logger.info(
            "memory_extraction.cleanup_expired removed=%d user_id=%s "
            "workspace_id=%s",
            removed,
            user_id,
            workspace_id,
        )
        return int(removed)
