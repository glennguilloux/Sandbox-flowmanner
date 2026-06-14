"""MemoryCorrectionService — privacy audit trail for personal memory (T29).

Persistence layer for the ``memory_correction_events`` table. This
service IS the audit: the original ``PersonalMemoryService`` has a
duck-typed ``_safe_audit`` hook that no-ops today; the eventual
integration is to swap that no-op for this service (deferred — T29
just provides the foundation; the wiring is a follow-up).

Critical guardrails (from the End-of-Galaxy plan §D30-60 / release gate):

* **No ``db.commit()``** — per ``services/AGENTS.md`` rule 3. The caller
  (route / CQRS handler / existing personal-memory service hook) owns
  the transaction boundary. We only ``flush()`` so the caller's
  commit/rollback decision is the one that finalizes the write.
* **Every read query filters by ``(user_id, workspace_id)`` together.**
  Mirrors the ``PersonalMemoryService`` / ``CritiqueService`` isolation
  guardrail — cross-tenant leakage of audit data is a privacy incident.
* **Validation happens at the service layer** so a bad ``event_type`` /
  ``actor`` surfaces as a ``MemoryCorrectionValidationError`` (which
  also subclasses ``ValueError``) rather than a 500 from a raw
  IntegrityError on flush.
* **Hardcoded ``ALL_*`` tuples** — the model exposes the canonical
  value sets, and the service does NOT redefine them (so CHECK
  constraints and validation stay in lockstep).
"""
from __future__ import annotations

import logging
import uuid
from typing import Any

from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.memory_correction_models import (
    ALL_ACTORS,
    ALL_EVENT_TYPES,
    MemoryCorrectionEvent,
)

logger = logging.getLogger(__name__)


# ── Exception hierarchy ────────────────────────────────────────────────


class MemoryCorrectionServiceError(Exception):
    """Base for all memory-correction-service errors."""


class MemoryCorrectionValidationError(
    MemoryCorrectionServiceError, ValueError
):
    """Raised for input validation failures. Inherits from both
    ``MemoryCorrectionServiceError`` and ``ValueError`` so callers can
    use either ``except ValueError`` (Pythonic) or
    ``except MemoryCorrectionValidationError`` (specific)."""


# ── Service ────────────────────────────────────────────────────────────


class MemoryCorrectionService:
    """Persistence + read layer for the privacy audit trail (D30-60 T29).

    Per ``services/AGENTS.md`` rule 3: this service NEVER calls
    ``db.commit()``. The caller (route, CQRS handler, or — in the
    eventual integration — a hook inside ``PersonalMemoryService``)
    owns the transaction. We only ``flush()`` so IDs and column
    defaults are populated before the caller's commit/rollback
    decision.
    """

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    # ── Validation helpers ────────────────────────────────────────

    @staticmethod
    def _validate_event_type(event_type: str) -> None:
        if event_type not in ALL_EVENT_TYPES:
            raise MemoryCorrectionValidationError(
                f"invalid event_type={event_type!r}; "
                f"must be one of {list(ALL_EVENT_TYPES)}"
            )

    @staticmethod
    def _validate_actor(actor: str) -> None:
        if actor not in ALL_ACTORS:
            raise MemoryCorrectionValidationError(
                f"invalid actor={actor!r}; "
                f"must be one of {list(ALL_ACTORS)}"
            )

    # ── Write: record_event ───────────────────────────────────────

    async def record_event(
        self,
        *,
        user_id: int,
        workspace_id: str,
        event_type: str,
        claim_id: uuid.UUID | None = None,
        actor: str = "user",
        source: str | None = None,
        details: dict[str, Any] | None = None,
    ) -> MemoryCorrectionEvent:
        """Append a new audit row.

        Validates ``event_type`` and ``actor`` against the hardcoded
        ``ALL_EVENT_TYPES`` / ``ALL_ACTORS`` tuples. The DB CHECK
        constraints will also reject invalid values, but pre-validating
        at the service layer turns a 500 (raw IntegrityError) into a
        ``MemoryCorrectionValidationError`` (also a ``ValueError``)
        with a precise message.

        Returns the persisted (flushed, refreshed)
        ``MemoryCorrectionEvent`` row. Caller owns the transaction
        (no commit here).
        """
        self._validate_event_type(event_type)
        self._validate_actor(actor)

        event = MemoryCorrectionEvent(
            user_id=user_id,
            workspace_id=workspace_id,
            claim_id=claim_id,
            event_type=event_type,
            actor=actor,
            source=source,
            details=details,
        )
        self.db.add(event)
        await self.db.flush()
        await self.db.refresh(event)
        logger.info(
            "memory_correction.event_recorded id=%s user_id=%s "
            "workspace_id=%s event_type=%s actor=%s claim_id=%s",
            event.id,
            user_id,
            workspace_id,
            event_type,
            actor,
            claim_id,
        )
        return event

    # ── Read: list_for_user ───────────────────────────────────────

    async def list_for_user(
        self,
        *,
        user_id: int,
        workspace_id: str,
        event_type: str | None = None,
        claim_id: uuid.UUID | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[MemoryCorrectionEvent], int]:
        """Paginated user audit listing for the v2 ``/memory-corrections``
        inspection surface.

        Always filters by ``(user_id, workspace_id)`` (the workspace
        isolation guardrail — see the module docstring). All other
        filters are optional; passing ``None`` means "do not constrain
        on this column".

        Validates ``event_type`` against ``ALL_EVENT_TYPES`` up front
        so a bad client value surfaces as a
        ``MemoryCorrectionValidationError`` (→ 422) rather than a 500
        from a raw IntegrityError.

        Returns ``(items, total_count)``. Items are ordered by
        ``created_at DESC`` (most recent first — the inspection UI's
        preferred sort).

        Per ``services/AGENTS.md`` rule 3: this method does NOT call
        ``db.commit()``. The caller (route) owns the transaction.
        """
        # ── Validation ────────────────────────────────────────────
        if event_type is not None:
            self._validate_event_type(event_type)

        # ── Predicate composition ─────────────────────────────────
        # Mandatory isolation predicate.
        base_predicates = [
            MemoryCorrectionEvent.user_id == user_id,
            MemoryCorrectionEvent.workspace_id == workspace_id,
        ]
        # Optional filters, added incrementally.
        optional_predicates: list[Any] = []
        if event_type is not None:
            optional_predicates.append(
                MemoryCorrectionEvent.event_type == event_type
            )
        if claim_id is not None:
            optional_predicates.append(
                MemoryCorrectionEvent.claim_id == claim_id
            )

        where_clause = and_(*base_predicates, *optional_predicates)

        # ── Total count ───────────────────────────────────────────
        count_stmt = (
            select(func.count())
            .select_from(MemoryCorrectionEvent)
            .where(where_clause)
        )
        total = (await self.db.execute(count_stmt)).scalar_one()

        # ── Items (paginated, ordered by created_at DESC) ────────
        items_stmt = (
            select(MemoryCorrectionEvent)
            .where(where_clause)
            .order_by(MemoryCorrectionEvent.created_at.desc())
            .offset(offset)
            .limit(limit)
        )
        items = list(
            (await self.db.execute(items_stmt)).scalars().all()
        )
        return items, int(total)

    # ── Read: list_for_claim ──────────────────────────────────────

    async def list_for_claim(
        self,
        *,
        user_id: int,
        workspace_id: str,
        claim_id: uuid.UUID,
    ) -> list[MemoryCorrectionEvent]:
        """Return the full audit history for a single claim.

        Scoped to ``(user_id, workspace_id)`` so a claim not visible
        to this user (cross-tenant, soft-deleted, etc.) returns ``[]``
        rather than leaking the existence of audit rows for claims
        the caller cannot see.

        Ordered by ``created_at DESC`` (most recent first).
        """
        result = await self.db.execute(
            select(MemoryCorrectionEvent)
            .where(
                and_(
                    MemoryCorrectionEvent.user_id == user_id,
                    MemoryCorrectionEvent.workspace_id == workspace_id,
                    MemoryCorrectionEvent.claim_id == claim_id,
                )
            )
            .order_by(MemoryCorrectionEvent.created_at.desc())
        )
        return list(result.scalars().all())

    # ── Read: get_provenance ──────────────────────────────────────

    async def get_provenance(
        self,
        *,
        user_id: int,
        workspace_id: str,
        claim_id: uuid.UUID,
    ) -> dict[str, Any]:
        """Return a per-claim provenance summary.

        Scoped to ``(user_id, workspace_id)`` — a claim not visible to
        this user returns ``{event_count: 0, ...}`` rather than leaking
        the existence of audit rows for claims the caller cannot see.

        Returned shape::

            {
                "claim_id": <uuid>,
                "event_count": <int>,
                "first_event_at": <datetime> | None,
                "last_event_at": <datetime> | None,
                "last_event_type": <str> | None,
                "last_actor": <str> | None,
                "events_by_type": {"view": N, "edit": N, ...},
            }

        ``events_by_type`` is keyed by ``ALL_EVENT_TYPES`` and includes
        zero-count buckets so callers can render a stable UI without
        having to handle missing keys.
        """
        # Fetch all events for this (user, workspace, claim). The audit
        # table is append-only so this is bounded by a single claim's
        # lifetime; the list_for_claim() method is the same query
        # the UI uses to render the raw rows.
        events = await self.list_for_claim(
            user_id=user_id,
            workspace_id=workspace_id,
            claim_id=claim_id,
        )

        # Stable bucket map — every known event type shows up, with
        # zero when no rows match.
        events_by_type: dict[str, int] = {et: 0 for et in ALL_EVENT_TYPES}
        for ev in events:
            events_by_type[ev.event_type] = (
                events_by_type.get(ev.event_type, 0) + 1
            )

        if not events:
            return {
                "claim_id": str(claim_id),
                "event_count": 0,
                "first_event_at": None,
                "last_event_at": None,
                "last_event_type": None,
                "last_actor": None,
                "events_by_type": events_by_type,
            }

        # Events are ordered by created_at DESC from list_for_claim,
        # so events[0] is the most recent and events[-1] is the
        # earliest.
        last = events[0]
        first = events[-1]
        return {
            "claim_id": str(claim_id),
            "event_count": len(events),
            "first_event_at": first.created_at,
            "last_event_at": last.created_at,
            "last_event_type": last.event_type,
            "last_actor": last.actor,
            "events_by_type": events_by_type,
        }
