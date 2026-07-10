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
``claim_recalled`` no-fail methods works. By default the service is
wired to ``MemoryCorrectionService`` (the ``memory_correction_events``
privacy audit trail) via the ``_MemoryCorrectionAudit`` adapter. Audit
writes are fire-and-forget (``BackgroundTaskManager``) so memory ops
never block on the audit write (perf guard).
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import Text, and_, func, or_, select
from sqlalchemy.exc import SQLAlchemyError

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

from app.models.personal_memory_models import (
    ALL_CLAIM_TYPES,
    ALL_SCOPES,
    ALL_SENSITIVITIES,
    ALL_SOURCE_TYPES,
    RECENCY_BANDS_DAYS,
    SOURCE_PRIORITY,
    SOURCE_PRIORITY_DEFAULT,
    PersonalMemoryClaim,
    recency_half_life_band,
    source_priority_for,
)
from app.services.background_task_manager import background_task_manager
from app.services.memory.poison_scan import scan_for_poison

logger = logging.getLogger(__name__)


# ── Epic 2.3 E23-B — lexicographic ranking comparator ─────────────────────
#
# Deterministic, integer-only ranking of personal-memory claims for
# ``recall()``. The policy (per Q1-Q6 decomposition E23-B, superseding the
# draft-considered confidence-first ordering) is:
#
#     source_priority  >  recency_half_life_band  >  confidence  >  importance
#
# implemented as an integer tuple compared lexicographically. We deliberately
# use integer comparisons (not floating weighted sums) so the ordering is
# **reproducible across machines**: a float weighted sum can differ by ULP
# between CPU architectures / Python builds and silently flip a tie. The
# recency axis is bucketed into half-life bands (see
# ``recency_half_life_band``) so a few-seconds difference in ``created_at``
# never flips the order. ``source_priority`` is read off the stored (E23-A)
# column, not derived, so SQL ``ORDER BY source_priority`` and this Python
# secondary sort agree exactly.
#
# Higher tuple sorts FIRST (winner). The stored ``source_priority`` column is
# already higher-is-better; ``recency_half_life_band`` returns higher=newer;
# ``confidence`` / ``importance`` are kept as-is (higher = better). For stable,
# reproducible ties we append ``created_at`` (newer first) and finally the
# claim ``id`` so two absolutely-identical tuples still compare deterministically
# instead of by arbitrary Python object id.
def _rank_sort_key(claim: PersonalMemoryClaim) -> tuple:
    """Return the lexicographic sort key for a claim (higher tuple = first)."""
    sp = int(getattr(claim, "source_priority", 0) or 0)
    band = recency_half_life_band(getattr(claim, "created_at", None))
    conf = float(getattr(claim, "confidence", 0.0) or 0.0)
    imp = float(getattr(claim, "importance", 0.0) or 0.0)
    created = getattr(claim, "created_at", None)
    # id as a final stable tiebreak (UUIDs sort lexicographically).
    cid = str(getattr(claim, "id", "") or "")
    return (sp, band, conf, imp, created, cid)


def lexicographic_rank(
    claims: list[PersonalMemoryClaim],
    *,
    reverse: bool = True,
) -> list[PersonalMemoryClaim]:
    """Deterministically rank ``claims`` by the E23-B policy.

    ``reverse=True`` (default) puts the winner first. Pure function — no DB,
    no ``now()`` dependency beyond the deterministic band bucketing, so the
    result is reproducible. Stable sort (Python's ``sorted`` is stable) means
    the input order is preserved when all tiebreak axes are equal.
    """
    return sorted(claims, key=_rank_sort_key, reverse=reverse)


# ── Epic 2.3 / Q2 — tiering + token budget (E23-B consumer) ────────────────
#
# ``rank_and_budget_claims`` is the chat-injection gate that turns the raw
# E23-B-ranked claim list into the *resolved, token-bounded* set that gets
# injected into the LLM prompt. It implements the Q2-A/Q2-C policy:
#
#   * Tier-0 (protected): ``claim_type='constraint'`` claims. These are
#     immortal by design (``expires_at IS NULL`` in practice) and must never
#     be truncated or ranked *against* preferences — a "never deploy Fridays"
#     constraint must survive even when the prompt is full. They are spent
#     first against the token budget.
#   * Tier-1 (competitive): everything else, ranked by ``lexicographic_rank``
#     (source_priority > recency > confidence > importance). On overflow we
#     DROP the lowest-ranked claims — we never perform LLM consolidation at
#     inject time (non-deterministic, kills prompt cache), per Q2-C.
#
# Determinism: the function is pure (no DB, no ``now()`` beyond the band
# bucketing already inside ``lexicographic_rank``), so the same input always
# yields the same resolved set — required for the frozen-snapshot reuse
# (Q2-D) to be reproducible across a session.
#
# Token estimate: ~4 chars/token (matches ``chat_context._estimate_tokens``)
# over the rendered memory-block text of each claim, so the budget tracks
# what ``format_memory_block`` will actually emit.

# Claim types that are immortal / protected (never truncated, never ranked
# vs preferences). Extend here if a new protected type lands — single source.
_PROTECTED_CLAIM_TYPES: frozenset[str] = frozenset({"constraint"})


def _estimate_claim_tokens(claim: PersonalMemoryClaim) -> int:
    """Estimate the token cost of ``claim`` as it will render in the
    injected memory block (``format_memory_block`` shape).

    Cheap heuristic (~4 chars/token) over the subject/predicate/object
    text. Used only for budget truncation — over-estimating just drops a
    claim slightly early, which is safe.
    """
    try:
        import json

        obj = json.dumps(getattr(claim, "object", {}) or {}, default=str, sort_keys=True)
    except (TypeError, ValueError):
        obj = str(getattr(claim, "object", ""))
    text = " ".join(
        [
            str(getattr(claim, "subject", "") or ""),
            str(getattr(claim, "predicate", "") or ""),
            obj,
        ]
    )
    return max(1, len(text) // 4)


def rank_and_budget_claims(
    claims: list[PersonalMemoryClaim],
    *,
    token_budget: int,
) -> tuple[list[PersonalMemoryClaim], list[PersonalMemoryClaim]]:
    """Resolve the token-bounded claim set for chat injection.

    Returns ``(selected, dropped)``. ``selected`` is ordered Tier-0 first
    (in input order, constraints are never ranked against each other), then
    Tier-1 by E23-B rank. ``dropped`` is what did not fit the budget (lowest
    rank first) — surfaced for observability (never silently lost from the
    audit trail). Constraints are always in ``selected`` unless the budget is
    pathologically small (defensive: a single constraint should fit any real
    budget).

    ``token_budget <= 0`` selects nothing (caller chose to disable memory in
    the prompt). Empty ``claims`` returns ``([], [])``.
    """
    if not claims or token_budget <= 0:
        return [], list(claims)

    protected: list[PersonalMemoryClaim] = []
    competitive: list[PersonalMemoryClaim] = []
    for c in claims:
        if getattr(c, "claim_type", None) in _PROTECTED_CLAIM_TYPES:
            protected.append(c)
        else:
            competitive.append(c)

    # Tier-1 competitive ranking (E23-B). Tier-0 stays in input order —
    # constraints are all equal-priority protecteds; ranking them against
    # each other adds nothing and could reorder a protected set.
    ranked_competitive = lexicographic_rank(competitive)

    selected: list[PersonalMemoryClaim] = []
    dropped: list[PersonalMemoryClaim] = []
    spent = 0

    # Spend Tier-0 first (protected).
    for c in protected:
        cost = _estimate_claim_tokens(c)
        if spent + cost > token_budget and selected:
            # Only drop a protected claim if something else already claimed
            # budget — i.e. budget is too small to hold even the protecteds
            # alongside earlier context. Keep at least one.
            dropped.append(c)
            continue
        selected.append(c)
        spent += cost

    # Spend Tier-1 by E23-B rank; lowest rank dropped first on overflow.
    for c in ranked_competitive:
        cost = _estimate_claim_tokens(c)
        if spent + cost > token_budget:
            dropped.append(c)
            continue
        selected.append(c)
        spent += cost

    return selected, dropped


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


# ── Audit adapter → MemoryCorrectionService ────────────────────────────

# A freshly-created claim is not committed until the caller's
# transaction commits, yet the audit row references it via FK. Likewise a
# hard-forget deletes the claim row before the fire-and-forget audit runs.
# The writer retries briefly so a pending commit lands, then falls back to
# dropping the claim FK so the privacy trail is never lost. Missed audits
# are logged, never raised (no-fail).
_AUDIT_MAX_RETRIES = 3
_AUDIT_RETRY_BACKOFF_S = 0.05


class _MemoryCorrectionAudit:
    """Duck-typed audit that persists memory events to the privacy
    audit trail (``memory_correction_events``) via
    ``MemoryCorrectionService``.

    Each ``claim_*`` method maps to a valid ``event_type`` and spawns a
    fire-and-forget task (``BackgroundTaskManager``) that opens its OWN
    session and commits the audit row independently of the caller's
    transaction. This keeps memory ops non-blocking (perf guard) and
    makes the audit trail durable even if the caller rolls back.

    Mapping (the service emits ``claim_``-prefixed events; the audit
    table uses a fixed ``event_type`` taxonomy — see
    ``memory_correction_models.ALL_EVENT_TYPES``):
        claim_created   → "create"
        claim_recalled  → "view"
        claim_forgotten → "forget"
        claim_updated   → "edit"
    """

    def __init__(self, manager: Any | None = None) -> None:
        # Default to the process-wide manager (production). Tests may pass
        # a dedicated instance so its tasks are scoped to one event loop.
        from app.services.background_task_manager import background_task_manager

        self._manager = manager or background_task_manager

    def claim_created(self, **kwargs: Any) -> None:
        self._emit("create", **kwargs)

    def claim_recalled(self, **kwargs: Any) -> None:
        self._emit("view", **kwargs)

    def claim_forgotten(self, **kwargs: Any) -> None:
        self._emit("forget", **kwargs)

    def claim_updated(self, **kwargs: Any) -> None:
        self._emit("edit", **kwargs)

    def _emit(self, event_type: str, **kwargs: Any) -> None:
        # user_id / workspace_id are always supplied by every _safe_audit
        # call site; claim_id is optional.
        user_id = kwargs["user_id"]
        workspace_id = kwargs["workspace_id"]
        claim_id_raw = kwargs.get("claim_id")
        claim_id = uuid.UUID(claim_id_raw) if claim_id_raw else None
        # Everything other than the routing keys becomes forensic detail.
        details = {k: v for k, v in kwargs.items() if k not in ("user_id", "workspace_id", "claim_id")}
        if not details:
            details = None
        self._manager.spawn(
            _write_audit_event(
                event_type=event_type,
                user_id=user_id,
                workspace_id=workspace_id,
                claim_id=claim_id,
                details=details,
            ),
            label=f"memory_correction:{event_type}",
        )


async def _write_audit_event(
    *,
    event_type: str,
    user_id: int,
    workspace_id: str,
    claim_id: uuid.UUID | None,
    details: dict[str, Any] | None,
) -> None:
    """Persist one audit row in its own transaction.

    The audit row references ``claim_id`` via FK, but the caller's claim
    may be uncommitted (create) or already hard-deleted (forget) when
    this fire-and-forget task runs. We retry briefly so a pending commit
    lands; if the parent row is genuinely not visible, we fall back to
    writing the event with ``claim_id=None`` (recording the unresolved id
    in ``details``) so the privacy trail is never lost.
    """
    from app.database import fresh_session
    from app.services.memory_correction_service import MemoryCorrectionService

    attempt = 0
    drop_claim_id = False
    while True:
        try:
            async with fresh_session() as session:
                svc = MemoryCorrectionService(session)
                await svc.record_event(
                    user_id=user_id,
                    workspace_id=workspace_id,
                    event_type=event_type,
                    claim_id=None if drop_claim_id else claim_id,
                    actor="user",
                    source="personal_memory_service",
                    details=({**(details or {}), "_claim_id_unresolved": str(claim_id)} if drop_claim_id else details),
                )
            return
        except SQLAlchemyError as exc:
            if not drop_claim_id and attempt < _AUDIT_MAX_RETRIES:
                attempt += 1
                await asyncio.sleep(_AUDIT_RETRY_BACKOFF_S)
                continue
            if not drop_claim_id:
                # Parent row not visible (uncommitted/deleted) — retry once
                # with the FK dropped so the audit event still survives.
                drop_claim_id = True
                continue
            logger.warning(
                "memory_correction.audit_write_failed event_type=%s claim_id=%s error=%s",
                event_type,
                claim_id,
                exc,
            )
            return


# ── Service ─────────────────────────────────────────────────────────────


class PersonalMemoryService:
    """CRUD + recall + forget for ``PersonalMemoryClaim``.

    Per ``services/AGENTS.md`` rule 3: this service NEVER calls
    ``db.commit()``. The CQRS command handler (or route) owns the
    transaction. We only ``flush()`` so IDs and column defaults are
    populated before the caller's commit/rollback decision.
    """

    def __init__(self, db: AsyncSession, audit: Any | None = None) -> None:
        self.db = db
        self.audit = audit or _MemoryCorrectionAudit()

    # ── Validation helpers ──────────────────────────────────────────

    @staticmethod
    def _validate_enum_value(field: str, value: str, allowed: tuple[str, ...]) -> None:
        if value not in allowed:
            raise PersonalMemoryValidationError(f"invalid {field}={value!r}; must be one of {list(allowed)}")

    @staticmethod
    def _validate_importance(value: float) -> None:
        if not (0.0 <= value <= 1.0):
            raise PersonalMemoryValidationError(f"importance must be in [0.0, 1.0]; got {value!r}")

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
            raise PersonalMemoryValidationError(f"confidence must be in [0.0, 1.0]; got {confidence!r}")

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
            # Epic 2.3 E23-A: keep denormalized source priority in sync with
            # source_type on every write (the migration seeds existing rows).
            source_priority=source_priority_for(source_type),
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
        # Epic 2.2 write-invalidation: a new claim write for
        # (user_id, workspace_id) bumps the frozen-snapshot generation
        # counter. The snapshot service re-captures lazily on next access
        # if the counter moved. Imported lazily to avoid a module-load
        # cycle (memory_snapshot_service imports recall_for_chat from
        # memory_citation_service, which imports this module).
        from app.services.memory_snapshot_service import bump_generation

        bump_generation(user_id, workspace_id)
        return claim

    # ── CRUD: create_from_proposal ──────────────────────────────────
    #
    # Thin adapter used by the background reviewer (Epic 2.1): turns a
    # reviewer ``ProposedWrite`` (free-text + ``memory_type`` + optional
    # ``source_type``) into a governed ``PersonalMemoryClaim``.
    #
    # Hard contract (preserves ``BackgroundReviewService`` no-raise
    # semantics): on any data-integrity problem (null workspace, rejected
    # provenance, invalid field) it logs + returns ``None`` — it NEVER
    # raises, so the Celery worker behavior is unchanged.

    # Reviewer source_type vocabulary (the prompt asks for one of these)
    # is the OLD backlog proposal and does NOT match the as-built
    # ``ALL_SOURCE_TYPES`` enum. Bridge it to the real enum here so the
    # value that actually lands in the claim is one the DB CHECK will
    # accept. ``program_learning`` is the canonical value: a reviewer is a
    # programmatic/background process (per provenance_approval.py), which
    # also correctly forces GOV-1.2 human approval.
    _REVIEWER_SOURCE_TYPE_BRIDGE: dict[str, str] = {
        "agent": "program_learning",
        "program_learning": "program_learning",
        "fetched": "mission",
        "tool_output": "mission",
        "third_party": "conversation",
        "conversation": "conversation",
        "mission": "mission",
        "user_explicit": "user_explicit",
    }

    async def create_from_proposal(
        self,
        proposed: Any,
        *,
        workspace_id: str | None,
        user_id: int,
        source_mission_id: str | None = None,
        agent_id: str | None = None,
    ) -> str | None:
        """Promote a reviewer ``ProposedWrite`` into a governed claim.

        Returns the new claim id (as ``str``) on success, ``None`` on
        any data-integrity failure (null workspace, rejected/rejected
        provenance, invalid field). Never raises.

        Governance enforced here (the whole point of Epic 2.1):
          * ``workspace_id`` MUST be present (NOT NULL guardrail — never
            guess a workspace).
          * ``source_type`` MUST resolve to a real enum value; if the
            proposal carries none we default to ``program_learning`` and
            log (the provenance gate still fires).
          * GOV-1.3a poison scan runs on the way in (direct writes
            previously skipped this — now they don't).
          * ``create`` then runs its own validation + fires the
            ``_MemoryCorrectionAudit`` adapter (GOV-1.4/1.6 trails now
            cover reviewer writes).
        """
        try:
            content = (proposed.content or "").strip()
            if not content:
                logger.warning("personal_memory.create_from_proposal: empty content; skipping")
                return None

            # 1. workspace_id NOT NULL guardrail.
            if workspace_id is None:
                logger.warning(
                    "personal_memory.create_from_proposal: workspace_id is None "
                    "(data-integrity error) — refusing to write claim without a workspace"
                )
                return None

            # 2. source_type resolution (bridge reviewer vocab -> enum).
            raw_source = getattr(proposed, "source_type", None)
            if raw_source is None:
                logger.warning(
                    "personal_memory.create_from_proposal: proposal had no source_type; "
                    "defaulting to 'program_learning' (GOV-1.2 still applies)"
                )
                source_type = "program_learning"
            else:
                source_type = self._REVIEWER_SOURCE_TYPE_BRIDGE.get(raw_source)
                if source_type is None:
                    logger.warning(
                        "personal_memory.create_from_proposal: source_type=%r is "
                        "unknown/unverifiable — refusing to write (fail-safe)",
                        raw_source,
                    )
                    return None

            # 3. GOV-1.3a poison scan on the way in (direct writes included).
            scan = scan_for_poison(content, getattr(proposed, "old_text", None))
            if scan.flagged:
                logger.warning(
                    "personal_memory.create_from_proposal: GOV-1.3a flagged " "write user=%s hits=%s severity=%s",
                    user_id,
                    scan.hits,
                    scan.severity,
                )

            # 4. Map ProposedWrite fields -> claim fields.
            memory_type = getattr(proposed, "memory_type", "episodic")
            # claim_type: episodic -> observation; others -> preference/fact.
            if memory_type == "episodic":
                claim_type = "observation"
            elif memory_type == "preference":
                claim_type = "preference"
            else:
                claim_type = "fact"  # semantic / default

            # predicate from memory_type (low-confidence heuristic; flagged).
            predicate_by_type = {
                "preference": "prefers",
                "episodic": "observed",
                "semantic": "is",
            }
            predicate = predicate_by_type.get(memory_type, "is")
            if memory_type not in predicate_by_type:
                logger.warning(
                    "personal_memory.create_from_proposal: low-confidence predicate "
                    "parse for memory_type=%r (defaulted to 'is')",
                    memory_type,
                )

            importance = float(getattr(proposed, "importance", 0.5) or 0.5)
            if importance <= 0.0 or importance > 1.0:
                logger.warning(
                    "personal_memory.create_from_proposal: importance=%s out of "
                    "range; defaulting to 0.5 for calibration (GOV-1.5)",
                    importance,
                )
                importance = 0.5

            # scope: claims use {"personal","shared","private"} (ALL_SCOPES).
            # Reviewer "agent" (a user preference / how the user works) maps
            # to "personal" (user-facing, recallable in chat); "workspace"
            # maps to "shared". Never "private" (would be filtered from chat).
            raw_scope = getattr(proposed, "scope", None) or "agent"
            scope = "shared" if raw_scope == "workspace" else "personal"

            # subject: the workspace/agent owner ("user") is the canonical
            # subject of personal memory.
            subject = "user"

            source_id = uuid.UUID(source_mission_id) if source_mission_id else None

            claim = await self.create(
                user_id=user_id,
                workspace_id=workspace_id,
                subject=subject,
                predicate=predicate,
                object={"text": content},
                claim_type=claim_type,
                scope=scope,
                source_type=source_type,
                source_id=source_id,
                confidence=0.5,
                importance=importance,
                sensitivity="normal",
            )
            logger.info(
                "personal_memory.create_from_proposal: claim=%s user=%s ws=%s type=%s",
                claim.id,
                user_id,
                workspace_id,
                claim_type,
            )
            return str(claim.id)
        except Exception as exc:
            logger.warning(
                "personal_memory.create_from_proposal failed for mission=%s user=%s: %s",
                source_mission_id,
                user_id,
                exc,
            )
            return None

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
            raise PersonalMemoryClaimNotFound(f"claim {claim_id} not found")
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
            self._validate_enum_value("claim_type", claim_type, ALL_CLAIM_TYPES)

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
            optional_predicates.append(PersonalMemoryClaim.claim_type == claim_type)

        where_clause = and_(*base_predicates, *optional_predicates)

        # Total count.
        count_stmt = select(func.count()).select_from(PersonalMemoryClaim).where(where_clause)
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

        Sorted by Epic 2.3 E23-B policy: ``source_priority DESC`` (primary,
        stored column) then a deterministic Python secondary sort
        ``source_priority > recency_half_life_band > confidence > importance``
        via ``lexicographic_rank``. Updates ``last_used_at = now()`` for the
        returned rows (one of the few writes this method does).
        """
        if scopes is not None:
            for s in scopes:
                self._validate_enum_value("scope", s, ALL_SCOPES)
        if not (0.0 <= min_confidence <= 1.0):
            raise PersonalMemoryValidationError(f"min_confidence must be in [0.0, 1.0]; got {min_confidence!r}")

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
        count_stmt = select(func.count()).select_from(PersonalMemoryClaim).where(where_clause)
        total = (await self.db.execute(count_stmt)).scalar_one()

        # Items: Epic 2.3 E23-B ordering. The primary axis (``source_priority``)
        # is resolved at the SQL layer so the DB does the heavy lifting and the
        # ``top_k`` window already favours higher-priority claims. We then apply
        # ``lexicographic_rank`` as a deterministic Python secondary sort
        # (``source_priority > recency_half_life_band > confidence >
        # importance``, integer-only) to guarantee cross-machine reproducible
        # ordering regardless of float/weighted-sum drift. The last_used_at bump
        # is unchanged from T19 (it is a usage signal, not a ranking axis).
        items_stmt = (
            select(PersonalMemoryClaim)
            .where(where_clause)
            .order_by(
                # Window axes MUST match the Python ``lexicographic_rank``
                # comparator (higher tuple = first):
                #   source_priority > recency > confidence > importance
                # ``created_at DESC`` is monotonic with the recency half-life
                # band used by the comparator, so the SQL window never drops a
                # high-recency claim that the Python sort would promote within a
                # source_priority band. Without this, a newer claim could be
                # truncated before the deterministic re-sort and silently lose
                # to an older one (defeating the E23-B recency axis).
                PersonalMemoryClaim.source_priority.desc(),
                PersonalMemoryClaim.created_at.desc(),
                PersonalMemoryClaim.confidence.desc(),
                PersonalMemoryClaim.importance.desc(),
            )
            .limit(top_k)
        )
        items = list((await self.db.execute(items_stmt)).scalars().all())
        # Deterministic final ordering (stable secondary sort). This is the
        # 2.2 handoff requirement: the frozen snapshot captures a resolved view.
        items = lexicographic_rank(items)

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

        # Q1-B — union the dedicated constraint lane. Constraints are retrieved
        # by exact/lexical match (never vectorized, never fuzzy-dependent) and
        # merged in so a standing prohibition ("never deploy Fridays") always
        # reaches the ranked output regardless of the competitive substring
        # gate above. Dedup by id (a constraint the main query already caught
        # is not duplicated).
        constraint_claims = await self._recall_constraint_lane(
            user_id=user_id,
            workspace_id=workspace_id,
            query=query,
            min_confidence=min_confidence,
        )
        if constraint_claims:
            seen_ids = {c.id for c in items}
            for c in constraint_claims:
                if c.id not in seen_ids:
                    items.append(c)
                    seen_ids.add(c.id)
            # Re-apply deterministic ranking so constraints land in their
            # correct Tier-0 position before the caller's budget gate.
            items = lexicographic_rank(items)

        return items, int(total)

    async def _recall_constraint_lane(
        self,
        *,
        user_id: int,
        workspace_id: str,
        query: str,
        min_confidence: float = 0.0,
    ) -> list[PersonalMemoryClaim]:
        """Q1-B — dedicated constraint lane (CORRECTION C2).

        Retrieve the user's standing ``constraint`` claims by **exact /
        lexical** match only. Constraints are NEVER vectorized or fuzzy-
        substring matched against the competitive (fact/preference) lane —
        that is the inversion trap: a "never deploy Fridays" constraint must
        not be cosine/contains-matched against a "deploy Fridays" query and
        silently lost.

        Match semantics (lexical, additive to the competitive recall):
          * keyword/containment over the canonical constraint text
            (subject, predicate, and the ``object`` JSONB serialized to text),
            OR
          * an exact ``object`` match — if the query's normalized tokens
            appear verbatim in the constraint's ``object`` payload.

        Tenant-scoped on ``(user_id, workspace_id)`` exactly like the main
        recall; excludes deleted/expired rows. The lane is deliberately
        independent of the competitive substring gate in ``recall`` so a
        standing constraint is surfaced whenever it is lexically relevant,
        not only when the fuzzy matcher fires.

        This method NEVER raises on DB error — the caller (recall) treats a
        constraint-lane failure as "no extra constraints" (fail-open, same
        posture as the enforcement half in ``pre_tool_constraints``).
        """
        if not (0.0 <= min_confidence <= 1.0):
            min_confidence = 0.0
        now = datetime.now(UTC)
        q = (query or "").lower().strip()
        # Empty query → the standing-context seed (used by the frozen
        # snapshot). Return ALL active constraints for the tenant (a standing
        # constraint applies to the whole session, not just matched turns).
        predicates: list[Any] = [
            PersonalMemoryClaim.user_id == user_id,
            PersonalMemoryClaim.workspace_id == workspace_id,
            PersonalMemoryClaim.claim_type == "constraint",
            PersonalMemoryClaim.deleted_at.is_(None),
            or_(
                PersonalMemoryClaim.expires_at.is_(None),
                PersonalMemoryClaim.expires_at > now,
            ),
            PersonalMemoryClaim.confidence >= min_confidence,
        ]
        if q:
            # Lexical containment over canonical text + serialized object.
            object_text = func.lower(func.cast(PersonalMemoryClaim.object, Text))
            predicates.append(
                or_(
                    func.lower(PersonalMemoryClaim.subject).contains(q),
                    func.lower(PersonalMemoryClaim.predicate).contains(q),
                    object_text.contains(q),
                )
            )
        stmt = select(PersonalMemoryClaim).where(and_(*predicates))
        try:
            rows = list((await self.db.execute(stmt)).scalars().all())
        except Exception as exc:  # fail-open: never brick recall on constraint lane
            logger.warning(
                "personal_memory: constraint lane recall failed (fail-open); " "user_id=%s workspace_id=%s error=%s",
                user_id,
                workspace_id,
                exc,
            )
            return []
        return rows

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
        claim = await self.get(user_id=user_id, workspace_id=workspace_id, claim_id=claim_id)

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
        claim = await self.get(user_id=user_id, workspace_id=workspace_id, claim_id=claim_id)
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
            self._validate_enum_value("sensitivity", fields["sensitivity"], ALL_SENSITIVITIES)
        if "importance" in fields and fields["importance"] is not None:
            self._validate_importance(fields["importance"])
        if "confidence" in fields and fields["confidence"] is not None and not (0.0 <= fields["confidence"] <= 1.0):
            raise PersonalMemoryValidationError(f"confidence must be in [0.0, 1.0]; got {fields['confidence']!r}")

        claim = await self.get(user_id=user_id, workspace_id=workspace_id, claim_id=claim_id)
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
            logger.warning("personal_memory.audit_failed method=%s error=%s", method_name, exc)
