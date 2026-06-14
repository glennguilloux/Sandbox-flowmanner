"""PersonalMemoryService — CRUD + recall + forget for ``PersonalMemoryClaim``
(D0-30, T19 — Personal Memory MVP).

This service is the canonical write/read surface for
``personal_memory_claims`` rows. It implements:

* CRUD: ``create``, ``get``, ``list_for_user``, ``update``,
  ``update_importance``, ``forget``
* Recall: ``recall`` (basic substring match in T19; semantic search
  via embeddings in T20+)

Critical guardrails (from the End-of-Galaxy plan §3):

* **Every read query filters by ``(user_id, workspace_id)`` together.**
  The "user-only" or "workspace-only" path is a security incident —
  the API is designed so it is impossible to construct a read that
  omits the workspace_id filter (every read method takes both as
  positional args and threads them into the WHERE clause).
* **Soft-deleted rows (``deleted_at IS NOT NULL``) are invisible** to
  all read paths by default; ``list_for_user(include_deleted=True)``
  is the only way to surface them.
* **Expired rows (``expires_at < now()``) are invisible** to all read
  paths; there is no opt-in flag for the expiry filter.
* **No ``db.commit()``** — per ``services/AGENTS.md`` rule 3. We only
  ``flush()`` so the caller (route / CQRS handler) can observe IDs
  and own the transaction boundary.

Audit integration is duck-typed: any object exposing
``claim_created`` / ``claim_updated`` / ``claim_forgotten`` /
``claim_recalled`` no-fail methods works. A no-op fallback is used
until T4 wires up ``PersonalMemoryAudit``.
"""

from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.personal_memory_models import (
    ALL_CLAIM_TYPES,
    ALL_SCOPES,
    ALL_SENSITIVITIES,
    ALL_SOURCE_TYPES,
    PersonalMemoryClaim,
)

logger = logging.getLogger(__name__)


# ── Exception hierarchy (per plan §T19) ──────────────────────────────────


class PersonalMemoryError(Exception):
    """Base for all personal-memory service errors."""


class PersonalMemoryClaimNotFound(PersonalMemoryError):
    """Raised when a claim ID does not resolve to a row (or is filtered
    out by the (user_id, workspace_id) predicate — same outcome to the
    caller: 404, not 403, to avoid leaking existence across the
    isolation boundary)."""


class PersonalMemoryValidationError(PersonalMemoryError, ValueError):
    """Raised for input validation failures (bad enum value, out-of-range
    numeric, unknown PATCH field, etc.). Inherits from both the service
    base and ``ValueError`` so callers can use either
    ``except ValueError`` (Pythonic) or
    ``except PersonalMemoryValidationError`` (specific).
    """


class PersonalMemoryForbidden(PersonalMemoryError):
    """Reserved for future use: surfaces a 403 when the (user_id,
    workspace_id) predicate ever needs to differentiate "not visible"
    from "not yours". Currently every read returns NotFound for both
    (a deliberate choice — see the docstring on
    PersonalMemoryClaimNotFound)."""


# ── Editable fields for update() (PATCH semantics) ───────────────────────
#
# Fields NOT in this set are immutable via PATCH: id, user_id,
# workspace_id, claim_type, scope, source_type, created_at, updated_at,
# last_used_at, deleted_at. The taxonomy columns are intentionally
# immutable because changing a claim's kind / scope would invalidate
# provenance — re-create the claim if you need to reclassify.

_EDITABLE_PATCH_FIELDS: frozenset[str] = frozenset(
    {
        "subject",
        "predicate",
        "object",
        "confidence",
        "importance",
        "sensitivity",
        "expires_at",
    }
)


# ── Audit no-op fallback ────────────────────────────────────────────────


class _NoOpAudit:
    """Duck-typed audit; no-op until T4 wires up PersonalMemoryAudit.

    Each method is a permissive no-op so the service can call
    ``self.audit.claim_created(...)`` unconditionally.
    """

    def claim_created(self, *args: Any, **kwargs: Any) -> None:
        pass

    def claim_updated(self, *args: Any, **kwargs: Any) -> None:
        pass

    def claim_forgotten(self, *args: Any, **kwargs: Any) -> None:
        pass

    def claim_recalled(self, *args: Any, **kwargs: Any) -> None:
        pass


# ── Service ─────────────────────────────────────────────────────────────


class PersonalMemoryService:
    """CRUD + recall + forget for ``PersonalMemoryClaim``.

    Per ``services/AGENTS.md`` rule 3: this service NEVER calls
    ``db.commit()``. The CQRS command handler (or route) owns the
    transaction. We only ``flush()`` so IDs and column defaults are
    populated before the caller's commit/rollback decision.
    """

    def __init__(
        self, db: AsyncSession, audit: Any | None = None
    ) -> None:
        self.db = db
        self.audit = audit or _NoOpAudit()

    # ── Validation helpers ──────────────────────────────────────────

    @staticmethod
    def _validate_enum_value(
        field: str, value: str, allowed: tuple[str, ...]
    ) -> None:
        if value not in allowed:
            raise PersonalMemoryValidationError(
                f"invalid {field}={value!r}; must be one of {list(allowed)}"
            )

    @staticmethod
    def _validate_importance(value: float) -> None:
        if not (0.0 <= value <= 1.0):
            raise PersonalMemoryValidationError(
                f"importance must be in [0.0, 1.0]; got {value!r}"
            )

    # ── CRUD: create ────────────────────────────────────────────────

    async def create(
        self,
        *,
        user_id: int,
        workspace_id: str,
        subject: str,
        predicate: str,
        object: dict[str, Any],
        claim_type: str,
        scope: str,
        source_type: str,
        source_id: uuid.UUID | None = None,
        confidence: float = 0.5,
        importance: float = 0.5,
        sensitivity: str = "normal",
        expires_at: datetime | None = None,
    ) -> PersonalMemoryClaim:
        """Insert a new claim. Validates the four enum fields and the
        two bounded numerics; raises ``PersonalMemoryValidationError``
        for invalid values.

        The DB-level CHECK constraints will also reject invalid values,
        but pre-validating at the service layer turns a 500 (raw
        IntegrityError) into a 422 with a precise message.
        """
        self._validate_enum_value("claim_type", claim_type, ALL_CLAIM_TYPES)
        self._validate_enum_value("scope", scope, ALL_SCOPES)
        self._validate_enum_value("source_type", source_type, ALL_SOURCE_TYPES)
        self._validate_enum_value("sensitivity", sensitivity, ALL_SENSITIVITIES)
        self._validate_importance(importance)
        if not (0.0 <= confidence <= 1.0):
            raise PersonalMemoryValidationError(
                f"confidence must be in [0.0, 1.0]; got {confidence!r}"
            )

        claim = PersonalMemoryClaim(
            user_id=user_id,
            workspace_id=workspace_id,
            subject=subject,
            predicate=predicate,
            object=object,
            claim_type=claim_type,
            scope=scope,
            source_type=source_type,
            source_id=source_id,
            confidence=confidence,
            importance=importance,
            sensitivity=sensitivity,
            expires_at=expires_at,
        )
        self.db.add(claim)
        await self.db.flush()
        await self.db.refresh(claim)
        logger.info(
            "personal_memory.claim_created id=%s user_id=%s workspace_id=%s",
            claim.id,
            user_id,
            workspace_id,
        )
        self._safe_audit(
            "claim_created",
            claim_id=str(claim.id),
            user_id=user_id,
            workspace_id=workspace_id,
        )
        return claim

    # ── CRUD: get ───────────────────────────────────────────────────

    async def get(
        self,
        *,
        user_id: int,
        workspace_id: str,
        claim_id: uuid.UUID,
    ) -> PersonalMemoryClaim:
        """Fetch a single claim by id, scoped to (user_id, workspace_id).

        Raises ``PersonalMemoryClaimNotFound`` if no row matches. The
        (user_id, workspace_id) filter is intentionally non-optional —
        callers cannot bypass the workspace isolation guardrail.
        """
        result = await self.db.execute(
            select(PersonalMemoryClaim).where(
                and_(
                    PersonalMemoryClaim.id == claim_id,
                    PersonalMemoryClaim.user_id == user_id,
                    PersonalMemoryClaim.workspace_id == workspace_id,
                )
            )
        )
        claim = result.scalar_one_or_none()
        if claim is None:
            raise PersonalMemoryClaimNotFound(
                f"claim {claim_id} not found"
            )
        return claim

    # ── CRUD: list_for_user ─────────────────────────────────────────

    async def list_for_user(
        self,
        *,
        user_id: int,
        workspace_id: str,
        scope: str | None = None,
        claim_type: str | None = None,
        include_deleted: bool = False,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[PersonalMemoryClaim], int]:
        """Paginated listing for the Memory Inspector UI.

        Always filters by ``(user_id, workspace_id)``. By default
        excludes soft-deleted rows. Returns ``(items, total_count)``.
        """
        if scope is not None:
            self._validate_enum_value("scope", scope, ALL_SCOPES)
        if claim_type is not None:
            self._validate_enum_value(
                "claim_type", claim_type, ALL_CLAIM_TYPES
            )

        # Base predicate: (user_id, workspace_id) + not-deleted.
        base_predicates = [
            PersonalMemoryClaim.user_id == user_id,
            PersonalMemoryClaim.workspace_id == workspace_id,
        ]
        if not include_deleted:
            base_predicates.append(PersonalMemoryClaim.deleted_at.is_(None))

        # Optional filters.
        optional_predicates: list[Any] = []
        if scope is not None:
            optional_predicates.append(PersonalMemoryClaim.scope == scope)
        if claim_type is not None:
            optional_predicates.append(
                PersonalMemoryClaim.claim_type == claim_type
            )

        where_clause = and_(*base_predicates, *optional_predicates)

        # Total count.
        count_stmt = (
            select(func.count())
            .select_from(PersonalMemoryClaim)
            .where(where_clause)
        )
        total = (await self.db.execute(count_stmt)).scalar_one()

        # Items (paginated, ordered by created_at DESC).
        items_stmt = (
            select(PersonalMemoryClaim)
            .where(where_clause)
            .order_by(PersonalMemoryClaim.created_at.desc())
            .offset(offset)
            .limit(limit)
        )
        items = list((await self.db.execute(items_stmt)).scalars().all())
        return items, int(total)

    # ── CRUD: recall ────────────────────────────────────────────────

    async def recall(
        self,
        *,
        user_id: int,
        workspace_id: str,
        query: str,
        scopes: list[str] | None = None,
        top_k: int = 10,
        min_confidence: float = 0.0,
    ) -> tuple[list[PersonalMemoryClaim], int]:
        """Recall for a query string.

        T19 basic version: filter by ``(user_id, workspace_id, NOT
        deleted, NOT expired, confidence >= min_confidence, scope IN
        scopes-if-given)`` and a simple case-insensitive substring
        search on the ``(subject, predicate)`` text. Full semantic
        search via embeddings is T20+.

        Sorted by ``confidence DESC, importance DESC, last_used_at
        DESC NULLS LAST``. Updates ``last_used_at = now()`` for the
        returned rows (one of the few writes this method does).
        """
        if scopes is not None:
            for s in scopes:
                self._validate_enum_value("scope", s, ALL_SCOPES)
        if not (0.0 <= min_confidence <= 1.0):
            raise PersonalMemoryValidationError(
                f"min_confidence must be in [0.0, 1.0]; got {min_confidence!r}"
            )

        # Compose predicates.
        now = datetime.now(UTC)
        predicates: list[Any] = [
            PersonalMemoryClaim.user_id == user_id,
            PersonalMemoryClaim.workspace_id == workspace_id,
            PersonalMemoryClaim.deleted_at.is_(None),
            # Expired rows are invisible. expires_at IS NULL OR expires_at > now().
            or_(
                PersonalMemoryClaim.expires_at.is_(None),
                PersonalMemoryClaim.expires_at > now,
            ),
            PersonalMemoryClaim.confidence >= min_confidence,
        ]
        if scopes:
            predicates.append(PersonalMemoryClaim.scope.in_(scopes))

        # Substring match on (subject, predicate). Case-insensitive
        # via SQL lower() (Postgres-friendly).
        q = query.lower()
        predicates.append(
            or_(
                func.lower(PersonalMemoryClaim.subject).contains(q),
                func.lower(PersonalMemoryClaim.predicate).contains(q),
            )
        )

        where_clause = and_(*predicates)

        # Total count (useful for the recall response).
        count_stmt = (
            select(func.count())
            .select_from(PersonalMemoryClaim)
            .where(where_clause)
        )
        total = (await self.db.execute(count_stmt)).scalar_one()

        # Items: ordered by confidence DESC, importance DESC,
        # last_used_at DESC NULLS LAST, then limited.
        items_stmt = (
            select(PersonalMemoryClaim)
            .where(where_clause)
            .order_by(
                PersonalMemoryClaim.confidence.desc(),
                PersonalMemoryClaim.importance.desc(),
                PersonalMemoryClaim.last_used_at.desc().nulls_last(),
            )
            .limit(top_k)
        )
        items = list((await self.db.execute(items_stmt)).scalars().all())

        # Bump last_used_at on the returned rows. The caller will
        # commit (or roll back) at the transaction boundary.
        if items:
            new_ts = datetime.now(UTC)
            for c in items:
                c.last_used_at = new_ts
            await self.db.flush()
            self._safe_audit(
                "claim_recalled",
                user_id=user_id,
                workspace_id=workspace_id,
                count=len(items),
            )

        return items, int(total)

    # ── CRUD: forget ────────────────────────────────────────────────

    async def forget(
        self,
        *,
        user_id: int,
        workspace_id: str,
        claim_id: uuid.UUID,
        hard: bool = False,
    ) -> PersonalMemoryClaim:
        """Soft-delete by default (``hard=False``). Idempotent: forgetting
        an already-forgotten claim is a no-op (returns the row unchanged).

        ``hard=True`` actually removes the row from the table.
        """
        # ``get()`` enforces the (user_id, workspace_id) filter.
        claim = await self.get(
            user_id=user_id, workspace_id=workspace_id, claim_id=claim_id
        )

        if hard:
            # Async session: delete() is a coroutine in async SQLAlchemy 2.x.
            await self.db.delete(claim)
            await self.db.flush()
            logger.info(
                "personal_memory.claim_forgotten_hard id=%s user_id=%s workspace_id=%s",
                claim_id,
                user_id,
                workspace_id,
            )
            # After a hard delete, the ORM object is gone — we still
            # log + audit, but return the detached object.
            self._safe_audit(
                "claim_forgotten",
                claim_id=str(claim_id),
                user_id=user_id,
                workspace_id=workspace_id,
                hard=True,
            )
            return claim

        # Soft-delete: idempotent.
        if claim.deleted_at is not None:
            logger.info(
                "personal_memory.claim_forgotten_noop id=%s user_id=%s workspace_id=%s",
                claim_id,
                user_id,
                workspace_id,
            )
            return claim

        claim.deleted_at = datetime.now(UTC)
        await self.db.flush()
        await self.db.refresh(claim)
        logger.info(
            "personal_memory.claim_forgotten id=%s user_id=%s workspace_id=%s",
            claim_id,
            user_id,
            workspace_id,
        )
        self._safe_audit(
            "claim_forgotten",
            claim_id=str(claim_id),
            user_id=user_id,
            workspace_id=workspace_id,
            hard=False,
        )
        return claim

    # ── CRUD: update_importance ─────────────────────────────────────

    async def update_importance(
        self,
        *,
        user_id: int,
        workspace_id: str,
        claim_id: uuid.UUID,
        new_importance: float,
    ) -> PersonalMemoryClaim:
        """Update the importance score. Validates ``0.0 <= new_importance <= 1.0``."""
        self._validate_importance(new_importance)
        claim = await self.get(
            user_id=user_id, workspace_id=workspace_id, claim_id=claim_id
        )
        claim.importance = new_importance
        await self.db.flush()
        await self.db.refresh(claim)
        logger.info(
            "personal_memory.claim_importance_updated id=%s new=%s user_id=%s",
            claim_id,
            new_importance,
            user_id,
        )
        self._safe_audit(
            "claim_updated",
            claim_id=str(claim_id),
            user_id=user_id,
            workspace_id=workspace_id,
            field="importance",
        )
        return claim

    # ── CRUD: update (PATCH) ────────────────────────────────────────

    async def update(
        self,
        *,
        user_id: int,
        workspace_id: str,
        claim_id: uuid.UUID,
        **fields: Any,
    ) -> PersonalMemoryClaim:
        """PATCH-style update for editable fields.

        Editable: ``subject``, ``predicate``, ``object``, ``confidence``,
        ``importance``, ``sensitivity``, ``expires_at``.

        Immutable: ``id``, ``user_id``, ``workspace_id``, ``claim_type``,
        ``scope``, ``source_type``, ``last_used_at``, ``deleted_at``,
        ``created_at``, ``updated_at``. Passing any of these (or any
        other unknown field) raises ``PersonalMemoryValidationError``.
        """
        forbidden = set(fields) - _EDITABLE_PATCH_FIELDS
        if forbidden:
            raise PersonalMemoryValidationError(
                f"unknown or non-editable field(s) in PATCH: "
                f"{sorted(forbidden)}; allowed: {sorted(_EDITABLE_PATCH_FIELDS)}"
            )

        # Field-level validation for the (few) constrained fields.
        if "sensitivity" in fields and fields["sensitivity"] is not None:
            self._validate_enum_value(
                "sensitivity", fields["sensitivity"], ALL_SENSITIVITIES
            )
        if "importance" in fields and fields["importance"] is not None:
            self._validate_importance(fields["importance"])
        if "confidence" in fields and fields["confidence"] is not None:
            if not (0.0 <= fields["confidence"] <= 1.0):
                raise PersonalMemoryValidationError(
                    f"confidence must be in [0.0, 1.0]; got {fields['confidence']!r}"
                )

        claim = await self.get(
            user_id=user_id, workspace_id=workspace_id, claim_id=claim_id
        )
        for field, value in fields.items():
            setattr(claim, field, value)
        await self.db.flush()
        await self.db.refresh(claim)
        logger.info(
            "personal_memory.claim_updated id=%s fields=%s user_id=%s",
            claim_id,
            sorted(fields),
            user_id,
        )
        self._safe_audit(
            "claim_updated",
            claim_id=str(claim_id),
            user_id=user_id,
            workspace_id=workspace_id,
            fields=sorted(fields),
        )
        return claim

    # ── Audit helper ────────────────────────────────────────────────

    def _safe_audit(self, method_name: str, **kwargs: Any) -> None:
        """Best-effort audit call. Logs (does not raise) on failure so
        the service never crashes the request because of an audit sink
        outage."""
        try:
            method = getattr(self.audit, method_name, None)
            if callable(method):
                method(**kwargs)
        except Exception as exc:  # pragma: no cover - depends on audit impl
            logger.warning(
                "personal_memory.audit_failed method=%s error=%s", method_name, exc
            )
