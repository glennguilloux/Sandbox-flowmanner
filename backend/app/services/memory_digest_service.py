"""MemoryDigestService (D30-60, T31 — daily digest).

Operational + read service for the daily-digest surface. Builds the
"Here's what I learned about you this week" preview, records delivery
attempts, and queries the user's digest history.

Critical guardrails (from the End-of-Galaxy plan §3):

* **Every read query filters by ``(user_id, workspace_id)`` together.**
  Digests are workspace-scoped to prevent cross-tenant leakage of a
  user's memory activity.
* **No ``db.commit()``** — per ``services/AGENTS.md`` rule 3. The
  caller (route / CQRS handler / cron handler) owns the transaction.
* **Pure-logic digest building.** The ``build_preview()`` method
  composes the digest from the user's recent personal-memory claims;
  it does NOT depend on any LLM (the digest content is the claims
  themselves plus a small computed summary, not a synthesized
  narrative). This keeps the digest cheap and deterministic.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.memory_digest_models import (
    ALL_DELIVERY_CHANNELS,
    ALL_DELIVERY_STATUSES,
    MemoryDigestDelivery,
)
from app.models.personal_memory_models import PersonalMemoryClaim

logger = logging.getLogger(__name__)


# ── Exception hierarchy ────────────────────────────────────────────────


class MemoryDigestServiceError(Exception):
    """Base for all digest-service errors."""


class MemoryDigestValidationError(
    MemoryDigestServiceError, ValueError
):
    """Raised for input validation failures. Inherits from both the
    service base and ``ValueError`` so callers can use either
    ``except ValueError`` (Pythonic) or
    ``except MemoryDigestValidationError`` (specific)."""


# ── Constants ──────────────────────────────────────────────────────────


# How many claims a digest preview includes, hard cap. The route
# layer (Pydantic schema) also caps per_page but the service enforces
# this defensively so a misuse from a cron handler can't blow up.
MAX_PREVIEW_CLAIMS = 100

# Default lookback window when /memory/digest/preview is called with
# no explicit `since_days`. 7 days = one weekly digest, matching the
# "Here's what I learned about you this week" UX.
DEFAULT_PREVIEW_LOOKBACK_DAYS = 7

# Per-field caps. Match the DB column widths and the existing
# MemoryExtractionPauseService conventions.
MAX_RECIPIENT_CHARS = 255
MAX_ERROR_MESSAGE_CHARS = 2000


# ── DTOs (pure-Python, no DB) ───────────────────────────────────────────


@dataclass
class DigestClaimSummary:
    """A compact view of one claim in a digest preview.

    Mirrors the ``PersonalMemoryClaimResponse`` shape (sans the
    sensitive / private fields) — enough context for the user to
    decide "yes that's right" / "no forget that" without exposing
    raw claim internals.
    """

    id: UUID
    subject: str
    predicate: str
    claim_type: str
    scope: str
    confidence: float
    created_at: datetime | None = None


@dataclass
class DigestPreview:
    """The full digest preview content — what the /memory/digest/preview
    endpoint returns, what the email / in-app renderer consumes.

    Pure-Python dataclass — no DB session dependency. Constructed by
    ``MemoryDigestService.build_preview()`` and serialised to JSON
    by the route layer via ``dataclasses.asdict()``.
    """

    user_id: int
    workspace_id: str
    since: datetime
    until: datetime
    claims: list[DigestClaimSummary]
    claims_count: int
    by_claim_type: dict[str, int] = field(default_factory=dict)
    by_scope: dict[str, int] = field(default_factory=dict)
    is_empty: bool = False


# ── Service ────────────────────────────────────────────────────────────


class MemoryDigestService:
    """Operational + read service for the daily-digest surface.

    Per ``services/AGENTS.md`` rule 3: this service NEVER calls
    ``db.commit()``. The caller owns the transaction.
    """

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    # ── Validation helpers ──────────────────────────────────────────

    @staticmethod
    def _validate_channel(channel: str) -> None:
        if channel not in ALL_DELIVERY_CHANNELS:
            raise MemoryDigestValidationError(
                f"invalid delivery_channel={channel!r}; "
                f"must be one of {list(ALL_DELIVERY_CHANNELS)}"
            )

    @staticmethod
    def _validate_status(status: str) -> None:
        if status not in ALL_DELIVERY_STATUSES:
            raise MemoryDigestValidationError(
                f"invalid status={status!r}; "
                f"must be one of {list(ALL_DELIVERY_STATUSES)}"
            )

    @staticmethod
    def _validate_recipient(recipient: str | None) -> None:
        if recipient is None:
            return
        if not isinstance(recipient, str):
            raise MemoryDigestValidationError(
                f"recipient must be a string; got {type(recipient).__name__}"
            )
        if len(recipient) > MAX_RECIPIENT_CHARS:
            raise MemoryDigestValidationError(
                f"recipient must be <= {MAX_RECIPIENT_CHARS} chars; "
                f"got {len(recipient)}"
            )

    @staticmethod
    def _validate_error_message(error_message: str | None) -> None:
        if error_message is None:
            return
        if not isinstance(error_message, str):
            raise MemoryDigestValidationError(
                f"error_message must be a string; got "
                f"{type(error_message).__name__}"
            )
        if len(error_message) > MAX_ERROR_MESSAGE_CHARS:
            raise MemoryDigestValidationError(
                f"error_message must be <= {MAX_ERROR_MESSAGE_CHARS} "
                f"chars; got {len(error_message)}"
            )

    @staticmethod
    def _validate_lookback_days(since_days: int) -> None:
        if not isinstance(since_days, int):
            raise MemoryDigestValidationError(
                f"since_days must be an int; got "
                f"{type(since_days).__name__}"
            )
        if since_days < 1:
            raise MemoryDigestValidationError(
                f"since_days must be >= 1; got {since_days!r}"
            )
        if since_days > 365:
            raise MemoryDigestValidationError(
                f"since_days must be <= 365 (1 year); got {since_days!r}"
            )

    # ── Read: build_preview ─────────────────────────────────────────

    async def build_preview(
        self,
        *,
        user_id: int,
        workspace_id: str,
        since_days: int = DEFAULT_PREVIEW_LOOKBACK_DAYS,
        now: datetime | None = None,
    ) -> DigestPreview:
        """Build a digest preview from the user's recent personal-memory
        claims.

        Pure async DB read + pure-Python aggregation; no LLM, no
        mutation, no commit. The route layer (or a cron handler) can
        call this and either render the result directly (preview) or
        pipe it to a delivery channel + record_delivery().

        Claims are pulled from ``personal_memory_claims`` (T18) with
        the standard workspace-isolation guardrail: every row must
        match ``(user_id, workspace_id)``, be non-deleted, non-expired,
        and (defensive) not in the ``private`` scope (the user would
        not want their own private claims surfaced in a digest they
        might share with a co-pilot).

        The hard cap of ``MAX_PREVIEW_CLAIMS`` (100) protects the
        digest from becoming unwieldy; the renderer is expected to
        show the top N and link to the full Memory Inspector.
        """
        self._validate_lookback_days(since_days)
        now = now or datetime.now(UTC)
        since = now - timedelta(days=since_days)

        result = await self.db.execute(
            select(PersonalMemoryClaim)
            .where(
                and_(
                    PersonalMemoryClaim.user_id == user_id,
                    PersonalMemoryClaim.workspace_id == workspace_id,
                    PersonalMemoryClaim.deleted_at.is_(None),
                    PersonalMemoryClaim.scope != "private",
                    # expires_at IS NULL OR expires_at > now()
                    (
                        PersonalMemoryClaim.expires_at.is_(None)
                    )
                    | (PersonalMemoryClaim.expires_at > now),
                    PersonalMemoryClaim.created_at >= since,
                )
            )
            .order_by(PersonalMemoryClaim.created_at.desc())
            .limit(MAX_PREVIEW_CLAIMS)
        )
        claims = list(result.scalars().all())

        summaries = [
            DigestClaimSummary(
                id=c.id,
                subject=c.subject,
                predicate=c.predicate,
                claim_type=c.claim_type,
                scope=c.scope,
                confidence=c.confidence,
                created_at=c.created_at,
            )
            for c in claims
        ]

        # Histograms — simple dict comprehensions.
        by_claim_type: dict[str, int] = {}
        by_scope: dict[str, int] = {}
        for s in summaries:
            by_claim_type[s.claim_type] = by_claim_type.get(s.claim_type, 0) + 1
            by_scope[s.scope] = by_scope.get(s.scope, 0) + 1

        return DigestPreview(
            user_id=user_id,
            workspace_id=workspace_id,
            since=since,
            until=now,
            claims=summaries,
            claims_count=len(summaries),
            by_claim_type=by_claim_type,
            by_scope=by_scope,
            is_empty=len(summaries) == 0,
        )

    # ── Write: record_delivery ──────────────────────────────────────

    async def record_delivery(
        self,
        *,
        user_id: int,
        workspace_id: str,
        delivery_channel: str,
        claims_count: int,
        status: str = "delivered",
        claims_summary: dict | None = None,
        recipient: str | None = None,
        sent_at: datetime | None = None,
        delivered_at: datetime | None = None,
        error_message: str | None = None,
    ) -> MemoryDigestDelivery:
        """Record a digest delivery (or preview) attempt.

        Validates the channel, status, recipient, and error message
        at the service layer. Returns the new (flushed, refreshed)
        row. Caller owns the transaction.

        Default ``status="delivered"`` is appropriate for the common
        in-app case. For the /memory/digest/preview endpoint, pass
        ``status="previewed"`` and ``delivery_channel="preview"``.
        """
        self._validate_channel(delivery_channel)
        self._validate_status(status)
        self._validate_recipient(recipient)
        self._validate_error_message(error_message)
        if claims_count < 0:
            raise MemoryDigestValidationError(
                f"claims_count must be >= 0; got {claims_count!r}"
            )

        now = datetime.now(UTC)
        delivery = MemoryDigestDelivery(
            user_id=user_id,
            workspace_id=workspace_id,
            sent_at=sent_at or now,
            delivery_channel=delivery_channel,
            status=status,
            claims_count=claims_count,
            claims_summary=claims_summary,
            recipient=recipient,
            delivered_at=delivered_at or (now if status == "delivered" else None),
            error_message=error_message,
        )
        self.db.add(delivery)
        await self.db.flush()
        await self.db.refresh(delivery)
        logger.info(
            "memory_digest.recorded id=%s user_id=%s workspace_id=%s "
            "channel=%s status=%s claims_count=%d",
            delivery.id,
            user_id,
            workspace_id,
            delivery_channel,
            status,
            claims_count,
        )
        return delivery

    # ── Read: list_deliveries ────────────────────────────────────────

    async def list_deliveries(
        self,
        *,
        user_id: int,
        workspace_id: str,
        delivery_channel: str | None = None,
        status: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[MemoryDigestDelivery], int]:
        """Paginated listing of past digest deliveries for a user.

        Always filters by ``(user_id, workspace_id)``. Optional
        filters: ``delivery_channel`` and ``status``. Returns
        ``(items, total_count)`` ordered by ``sent_at DESC`` (most
        recent first).
        """
        if delivery_channel is not None:
            self._validate_channel(delivery_channel)
        if status is not None:
            self._validate_status(status)

        where_clause = and_(
            MemoryDigestDelivery.user_id == user_id,
            MemoryDigestDelivery.workspace_id == workspace_id,
        )
        if delivery_channel is not None:
            where_clause = and_(
                where_clause,
                MemoryDigestDelivery.delivery_channel == delivery_channel,
            )
        if status is not None:
            where_clause = and_(
                where_clause,
                MemoryDigestDelivery.status == status,
            )

        total = (
            await self.db.execute(
                select(func.count())
                .select_from(MemoryDigestDelivery)
                .where(where_clause)
            )
        ).scalar_one()

        items = list(
            (
                await self.db.execute(
                    select(MemoryDigestDelivery)
                    .where(where_clause)
                    .order_by(MemoryDigestDelivery.sent_at.desc())
                    .offset(offset)
                    .limit(limit)
                )
            )
            .scalars()
            .all()
        )
        return items, int(total)

    # ── Read: latest_delivery ───────────────────────────────────────

    async def latest_delivery(
        self,
        *,
        user_id: int,
        workspace_id: str,
        delivery_channel: str | None = None,
    ) -> MemoryDigestDelivery | None:
        """Return the most-recent delivery for this user, optionally
        filtered by channel. Returns None if no rows match. The
        single-row LIMIT 1 lookup hits the composite index
        ``(user_id, workspace_id, sent_at)`` (and the channel index
        if filtered).
        """
        if delivery_channel is not None:
            self._validate_channel(delivery_channel)

        where_clause = and_(
            MemoryDigestDelivery.user_id == user_id,
            MemoryDigestDelivery.workspace_id == workspace_id,
        )
        if delivery_channel is not None:
            where_clause = and_(
                where_clause,
                MemoryDigestDelivery.delivery_channel == delivery_channel,
            )

        result = await self.db.execute(
            select(MemoryDigestDelivery)
            .where(where_clause)
            .order_by(MemoryDigestDelivery.sent_at.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()
