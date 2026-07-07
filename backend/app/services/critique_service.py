"""CritiqueService — persistence layer for the D30-60 critic stack (T27).

Wraps ``CriticOutput`` (from T25) and persists a single ``Critique`` row
per critic run. This service is the canonical write/read surface for
the ``critiques`` table established in T24.

Critical guardrails (from the End-of-Galaxy plan §D30-60):

* **No ``db.commit()``** — per ``services/AGENTS.md`` rule 3. The caller
  (route / executor hook / CQRS handler) owns the transaction boundary.
  We only ``flush()`` so the caller's commit/rollback decision is the
  one that finalizes the write.
* **Every read query filters by ``(user_id, workspace_id)`` together.**
  Mirrors the ``PersonalMemoryService`` isolation guardrail — the critic
  surface is workspace-scoped to prevent cross-tenant leakage of
  critique verdicts.
* **Validation happens at the service layer** so a bad ``critic_kind``
  or out-of-range score surfaces as a 422 (or runtime ValueError) at
  the call site, not a 500 from a raw IntegrityError on flush.
* **Score clamping at write time.** Even if the upstream ``CriticOutput``
  (T25) clamps its own scores defensively, we re-clamp here as a
  belt-and-suspenders measure.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from sqlalchemy import and_, func, select

from app.models.critique_models import ALL_CRITIC_KINDS, Critique
from app.services.improvement_generator import (
    ImprovementBatch,
    ImprovementGenerator,
    MissionContext,
)

if TYPE_CHECKING:
    import uuid

    from sqlalchemy.ext.asyncio import AsyncSession

    from app.services.critic import CriticOutput

logger = logging.getLogger(__name__)


# ── Exception hierarchy ────────────────────────────────────────────────


class CritiqueServiceError(Exception):
    """Base for all critique-service errors."""


class CritiqueNotFound(CritiqueServiceError):
    """Raised when a critique ID does not resolve to a row (or is filtered
    out by the (user_id, workspace_id) predicate — same outcome to the
    caller: NotFound, to avoid leaking existence across the isolation
    boundary)."""


class CritiqueValidationError(CritiqueServiceError, ValueError):
    """Raised for input validation failures. Inherits from both
    ``CritiqueServiceError`` and ``ValueError`` so callers can use
    either ``except ValueError`` (Pythonic) or
    ``except CritiqueValidationError`` (specific)."""


# ── Limits ─────────────────────────────────────────────────────────────


# Defensive cap on the free-text summary column. Matches the project's
# pattern of capping short text fields at the service layer (see
# ``consolidate_learning``'s 500-char plan_adjustments cap scaled up).
MAX_SUMMARY_CHARS = 2000

# Score bounds (per Critique model's CHECK constraint).
SCORE_MIN = 0.0
SCORE_MAX = 1.0


# ── Helpers ────────────────────────────────────────────────────────────


def _clamp_score(value: float | None) -> float | None:
    """Clamp a 0.0-1.0 score into range, or return None for None/NaN.

    A non-None out-of-range value is clamped to the nearest bound rather
    than rejected, so the critic stack stays resilient to upstream drift.
    """
    if value is None:
        return None
    try:
        v = float(value)
    except (TypeError, ValueError):
        return None
    # NaN guard.
    if v != v:  # NaN != NaN
        return None
    if v < SCORE_MIN:
        return SCORE_MIN
    if v > SCORE_MAX:
        return SCORE_MAX
    return v


def _truncate_summary(value: str | None) -> str | None:
    """Cap a free-text summary to ``MAX_SUMMARY_CHARS`` characters.

    A non-None value longer than the cap is truncated; ``None`` passes
    through unchanged. Empty strings are preserved as empty strings.
    """
    if value is None:
        return None
    if len(value) <= MAX_SUMMARY_CHARS:
        return value
    return value[:MAX_SUMMARY_CHARS]


# ── Service ────────────────────────────────────────────────────────────


class CritiqueService:
    """Persistence layer for the ``critiques`` table (D30-60 T27).

    Per ``services/AGENTS.md`` rule 3: this service NEVER calls
    ``db.commit()``. The caller (executor hook, route, CQRS handler)
    owns the transaction. We only ``flush()`` so IDs and column defaults
    are populated before the caller's commit/rollback decision.
    """

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    # ── Validation helpers ──────────────────────────────────────────

    @staticmethod
    def _validate_critic_kind(critic_kind: str) -> None:
        if critic_kind not in ALL_CRITIC_KINDS:
            raise CritiqueValidationError(
                f"invalid critic_kind={critic_kind!r}; must be one of {list(ALL_CRITIC_KINDS)}"
            )

    # ── Write: create_from_critic ───────────────────────────────────

    async def create_from_critic(
        self,
        *,
        user_id: int,
        workspace_id: str,
        mission_id: uuid.UUID,
        critic_output: CriticOutput,
        critic_kind: str,
        program_id: uuid.UUID | None = None,
    ) -> Critique:
        """Persist a ``Critique`` row from a ``CriticOutput``.

        Validates ``critic_kind``, clamps the four score columns, and
        truncates the free-text summary. The DB CHECK constraints will
        also reject invalid values, but pre-validating at the service
        layer turns a 500 (raw IntegrityError) into a 422 (or a
        domain-specific exception) with a precise message.

        Returns the persisted (flushed, refreshed) ``Critique`` row.
        Caller owns the transaction (no commit here).
        """
        self._validate_critic_kind(critic_kind)

        kwargs = critic_output.to_critique_kwargs()
        # Clamp all four score columns defensively.
        kwargs["score_overall"] = _clamp_score(kwargs.get("score_overall"))
        kwargs["score_alignment"] = _clamp_score(kwargs.get("score_alignment"))
        kwargs["score_safety"] = _clamp_score(kwargs.get("score_safety"))
        kwargs["score_completeness"] = _clamp_score(kwargs.get("score_completeness"))
        # Truncate the free-text summary.
        kwargs["summary"] = _truncate_summary(kwargs.get("summary"))

        critique = Critique(
            user_id=user_id,
            workspace_id=workspace_id,
            mission_id=mission_id,
            program_id=program_id,
            critic_kind=critic_kind,
            **kwargs,
        )
        self.db.add(critique)
        await self.db.flush()
        await self.db.refresh(critique)
        logger.info(
            "critique.persisted id=%s user_id=%s workspace_id=%s mission_id=%s critic_kind=%s score_overall=%s",
            critique.id,
            user_id,
            workspace_id,
            mission_id,
            critic_kind,
            critique.score_overall,
        )

        # ── 2a.3: derive + persist the ImprovementBatch ─────────────
        # Run the pure-logic ImprovementGenerator over the same
        # CriticOutput we just persisted, and stash the result on the
        # Critique row as JSONB. This is the single source of truth for
        # "what should improve next"; T27 may later fan it out into a
        # MissionProgram.learning_brief. Per services/AGENTS.md rule 3,
        # we only flush() — the caller owns the commit.
        #
        # Defensive: if generation raises for ANY reason, log
        # (parameterised) and skip — never break the critique write.
        try:
            batch = ImprovementGenerator().generate(
                critic_output,
                MissionContext(
                    mission_id=str(mission_id),
                    goal=getattr(critic_output, "summary", "") or "",
                    plan={},
                    outcome={},
                    user_id=user_id,
                    workspace_id=workspace_id,
                ),
            )
            if isinstance(batch, ImprovementBatch):
                critique.improvement_batch = CritiqueService._batch_to_json(batch)
                await self.db.flush()
        except Exception:
            logger.exception(
                "critique.improvement_batch.skipped id=%s mission_id=%s",
                critique.id,
                mission_id,
            )
        return critique

    # ── ImprovementBatch → JSONB serialiser ─────────────────────────

    @staticmethod
    def _batch_to_json(batch: ImprovementBatch) -> dict:
        """Serialise an :class:`ImprovementBatch` to a JSON-safe dict.

        The ``PlanAdjustment`` / ``ToolSuggestion`` dataclasses are
        flattened into a stable key layout so the stored JSONB is easy
        to read from SQL / T27 fan-out.
        """
        return {
            "plan_adjustments": [
                {
                    "description": a.description,
                    "category": a.category,
                    "confidence": a.confidence,
                    "source": a.source,
                }
                for a in batch.plan_adjustments
            ],
            "tool_suggestions": [
                {
                    "tool_name": t.tool_name,
                    "reason": t.reason,
                    "confidence": t.confidence,
                }
                for t in batch.tool_suggestions
            ],
            "common_failure_patterns": list(batch.common_failure_patterns),
            "summary": batch.summary,
            "overall_recommendation": batch.overall_recommendation,
        }

    # ── Read: list ──────────────────────────────────────────────────

    async def list(
        self,
        *,
        user_id: int,
        workspace_id: str,
        mission_id: uuid.UUID | None = None,
        program_id: uuid.UUID | None = None,
        critic_kind: str | None = None,
        min_score_overall: float | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[Critique], int]:
        """Paginated listing for the v2 /critiques inspection surface.

        Always filters by ``(user_id, workspace_id)`` (the workspace
        isolation guardrail — see the module docstring). All other
        filters are optional; passing ``None`` means "do not constrain
        on this column".

        Validates ``critic_kind`` against ``ALL_CRITIC_KINDS`` and
        ``min_score_overall`` against ``[0.0, 1.0]`` up front so a bad
        client value surfaces as a ``CritiqueValidationError`` (→ 422)
        rather than a 500 from a raw IntegrityError.

        Returns ``(items, total_count)``. Items are ordered by
        ``created_at DESC`` (most recent first — the inspection UI's
        preferred sort).

        Per ``services/AGENTS.md`` rule 3: this method does NOT call
        ``db.commit()``. The caller (route) owns the transaction.
        """
        # ── Validation ────────────────────────────────────────────
        if critic_kind is not None:
            self._validate_critic_kind(critic_kind)
        if min_score_overall is not None and not (SCORE_MIN <= min_score_overall <= SCORE_MAX):
            raise CritiqueValidationError(
                f"min_score_overall must be in [{SCORE_MIN}, {SCORE_MAX}]; got {min_score_overall!r}"
            )

        # ── Predicate composition ─────────────────────────────────
        # Mandatory isolation predicate.
        base_predicates = [
            Critique.user_id == user_id,
            Critique.workspace_id == workspace_id,
        ]
        # Optional filters, added incrementally — no premature commit
        # (the route commits when the request is done).
        optional_predicates: list[Any] = []
        if mission_id is not None:
            optional_predicates.append(Critique.mission_id == mission_id)
        if program_id is not None:
            optional_predicates.append(Critique.program_id == program_id)
        if critic_kind is not None:
            optional_predicates.append(Critique.critic_kind == critic_kind)
        if min_score_overall is not None:
            optional_predicates.append(Critique.score_overall >= min_score_overall)

        where_clause = and_(*base_predicates, *optional_predicates)

        # ── Total count ───────────────────────────────────────────
        count_stmt = select(func.count()).select_from(Critique).where(where_clause)
        total = (await self.db.execute(count_stmt)).scalar_one()

        # ── Items (paginated, ordered by created_at DESC) ────────
        items_stmt = (
            select(Critique).where(where_clause).order_by(Critique.created_at.desc()).offset(offset).limit(limit)
        )
        items = list((await self.db.execute(items_stmt)).scalars().all())
        return items, int(total)

    # ── Read: get ───────────────────────────────────────────────────

    async def get(
        self,
        *,
        user_id: int,
        workspace_id: str,
        critique_id: uuid.UUID,
    ) -> Critique:
        """Fetch a single critique by id, scoped to (user_id, workspace_id).

        Raises ``CritiqueNotFound`` if no row matches. The
        ``(user_id, workspace_id)`` filter is intentionally non-optional
        — callers cannot bypass the workspace isolation guardrail.
        """
        result = await self.db.execute(
            select(Critique).where(
                and_(
                    Critique.id == critique_id,
                    Critique.user_id == user_id,
                    Critique.workspace_id == workspace_id,
                )
            )
        )
        critique = result.scalar_one_or_none()
        if critique is None:
            raise CritiqueNotFound(f"critique {critique_id} not found")
        return critique
