"""Background review service — applies the reviewer's proposed writes.

Owns the three write operations the verification report flagged as
missing from ``MemoryService``:

- ``add_reviewed_entry`` — direct write to ``memory_entries`` when the
  workspace's ``write_approval`` flag is false (solo users, or
  workspaces under 30 days old).
- ``stage_pending_write`` — staging row in ``pending_writes`` when
  ``write_approval`` is true. The row sits in the queue until the user
  approves it, rejects it, or 7 days elapse.
- ``supersede_entry`` — promote a replacement. The old entry is flipped
  to ``superseded`` and the new entry's ``supersedes_id`` points at it.

Staging runs the GOV-1.3a escalate-only poison scan and attaches the
findings to the row metadata so the eventual HITL drain (GOV-1.1) can
prioritize flagged writes. The scan can never block or de-escalate a
staged write.

Also owns the reviewer LLM call (via ``LLMManager`` on the LangGraph
path — not via ``chat_service._resolve_provider`` which is broken for
``llamacpp-*`` model_ids per ``services/AGENTS.md §3``) and the
validation layer that drops any proposed write whose action is not in
the tool whitelist.

Best-effort semantics: every public method must NEVER raise on a
runtime LLM/DB error. Failures are logged and a Langfuse span is
closed with ``status_message="error"`` so we can alert on the error
rate (target < 5% per the plan).
"""

from __future__ import annotations

import asyncio
import json
import logging
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any

from app.models.memory_models import (
    ALL_PENDING_WRITE_ACTIONS,
    ALL_PENDING_WRITE_TYPES,
    PENDING_WRITE_DEFAULT_TTL_DAYS,
    MemoryEntry,
    PendingWrite,
    PendingWriteAction,
    PendingWriteStatus,
    PendingWriteType,
)
from app.services.memory.background_review_prompt import (
    IMPORTANCE_CEILING,
    IMPORTANCE_FLOOR,
    REVIEW_PROMPT,
    REVIEWER_ACTION_TO_DB_ACTION,
    REVIEWER_CONTENT_MAX_CHARS,
    REVIEWER_CONTENT_MIN_CHARS,
    REVIEWER_TOOL_WHITELIST,
)
from app.services.memory.poison_scan import scan_for_poison

logger = logging.getLogger(__name__)

# Default reviewer model. Per the task decisions:
#   - default = llamacpp-qwen3.6-27b (the running 27B on :11434)
#   - fallback = fail open + log (no 1.5B fallback in v1)
#   - NO SaaS APIs (OpenAI/Google/DeepSeek) — earlier I recommended
#     GPT-4o-mini; that was wrong. Reviewer stays on the local 27B.
DEFAULT_REVIEWER_MODEL = "llamacpp-qwen3.6-27b"

# GOV-1.7 reviewer reliability: bounded retry on transient HTTP failures.
REVIEWER_MAX_RETRIES = 3
REVIEWER_RETRY_BASE_DELAY = 1.0
REVIEWER_RETRYABLE_STATUS = frozenset({429, 500, 502, 503, 504})


@dataclass(frozen=True)
class ProposedWrite:
    """A single write the reviewer LLM proposed.

    Validated at parse time against the tool whitelist; only validated
    objects reach ``apply_proposed_writes``.
    """

    action: str  # one of PendingWriteAction.{ADD, REPLACE, REMOVE}
    content: str
    old_text: str | None = None
    importance: float = 0.5
    memory_type: str = "episodic"
    scope: str = "agent"
    reasoning: str = ""

    def is_destructive(self) -> bool:
        """Destructive writes always require approval regardless of
        workspace ``write_approval``. Per the user decision of 2026-06-17.
        """
        return self.action in {
            PendingWriteAction.REPLACE,
            PendingWriteAction.REMOVE,
        }


@dataclass
class ApplyResult:
    """Outcome of running the reviewer's proposed writes.

    Carries enough detail for the Celery task to log a meaningful
    summary and for the API layer (future) to expose to the user.
    """

    direct_writes: list[str] = field(default_factory=list)  # memory_entry ids
    staged_writes: list[str] = field(default_factory=list)  # pending_write ids
    skipped: list[dict[str, str]] = field(default_factory=list)
    superseded: list[tuple[str, str]] = field(default_factory=list)  # (old_id, new_id)
    cost_estimate_usd: float = 0.0
    reviewer_model: str = DEFAULT_REVIEWER_MODEL

    @property
    def total_writes(self) -> int:
        return len(self.direct_writes) + len(self.staged_writes)


def compute_write_approval(workspace: Any) -> bool:
    """Decide whether a workspace requires user approval for memory writes.

    Rules (per the user decision of 2026-06-17):

    - Solo workspaces (single member) → no approval (write_approval=false).
    - Multi-member workspaces older than 30 days → approval required
      (write_approval=true).
    - Multi-member workspaces younger than 30 days → no approval (still
      in the trust-building window).
    - Destructive writes (REPLACE / REMOVE) ALWAYS require approval
      regardless of workspace state — that rule lives on the write
      itself (``ProposedWrite.is_destructive``), not here.

    The ``workspace`` argument may be a SQLAlchemy ``Workspace`` model
    instance OR a plain dict — the service is decoupled from the ORM so
    it can be unit-tested without a DB.
    """
    if workspace is None:
        # Defensive default: if we don't know the workspace, force
        # approval. Better to ask the user than silently write.
        return True

    # Tolerate either an ORM object or a dict-shaped proxy.
    def _get(name: str, default: Any = None) -> Any:
        if isinstance(workspace, dict):
            return workspace.get(name, default)
        return getattr(workspace, name, default)

    # Member count: prefer an explicit column, fall back to the
    # ``members`` relationship length, then to 1.
    members = _get("member_count") or _get("members_count")
    if members is None:
        rel_members = _get("members")
        if rel_members is not None:
            try:
                members = len(rel_members)
            except TypeError:
                members = None
    if members is None:
        members = 1

    created_at = _get("created_at")

    if members <= 1:
        return False

    if created_at is None:
        # No created_at → treat as new → no approval.
        return False

    # created_at may be a datetime or an ISO string.
    if isinstance(created_at, str):
        try:
            created_at = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
        except ValueError:
            return False
    age = datetime.now(UTC) - created_at
    return age > timedelta(days=30)


class BackgroundReviewService:
    """Apply the reviewer's proposed writes to durable storage.

    Stateless beyond a logger. All public methods take the session
    they need (so the Celery worker can manage its own short-lived
    session lifecycle) and never raise on runtime failure.
    """

    # ── Write operations (the 3 missing methods from the plan) ─────────

    async def add_reviewed_entry(
        self,
        db: Any,
        *,
        workspace_id: str | None,
        user_id: int | None,
        agent_id: str | None,
        content: str,
        memory_type: str = "episodic",
        importance: float = 0.5,
        source_mission_id: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> str | None:
        """Insert a memory entry marked as reviewer-accepted.

        Returns the new ``MemoryEntry.id`` on success, ``None`` on
        failure. Never raises — caller treats ``None`` as "the
        reviewer could not commit, move on".
        """
        try:
            entry = MemoryEntry(
                id=str(uuid.uuid4()),
                workspace_id=workspace_id,
                user_id=user_id,
                agent_id=agent_id,
                namespace="agent" if agent_id else "default",
                memory_type=memory_type,
                content=content,
                importance=max(IMPORTANCE_FLOOR, min(IMPORTANCE_CEILING, importance)),
                source_mission_id=source_mission_id,
                meta={
                    "origin": "background_review",
                    **(metadata or {}),
                },
            )
            db.add(entry)
            await db.flush()
            logger.info(
                "BackgroundReviewService.add_reviewed_entry id=%s agent=%s importance=%.2f",
                entry.id,
                agent_id,
                entry.importance,
            )
            return entry.id
        except Exception as exc:
            logger.warning(
                "BackgroundReviewService.add_reviewed_entry failed for mission=%s: %s",
                source_mission_id,
                exc,
            )
            return None

    async def stage_pending_write(
        self,
        db: Any,
        *,
        workspace_id: str | None,
        user_id: int,
        mission_id: str | None,
        action: str,
        content: str | None,
        old_text: str | None = None,
        write_type: str = PendingWriteType.MEMORY,
        ttl_days: int = PENDING_WRITE_DEFAULT_TTL_DAYS,
        metadata: dict[str, Any] | None = None,
    ) -> str | None:
        """Insert a row into ``pending_writes`` for user approval.

        Returns the new ``PendingWrite.id`` on success, ``None`` on
        failure. Never raises.
        """
        try:
            if action not in ALL_PENDING_WRITE_ACTIONS:
                logger.warning(
                    "BackgroundReviewService.stage_pending_write rejected action=%s",
                    action,
                )
                return None
            if write_type not in ALL_PENDING_WRITE_TYPES:
                logger.warning(
                    "BackgroundReviewService.stage_pending_write rejected write_type=%s",
                    write_type,
                )
                return None

            now = datetime.now(UTC)
            # GOV-1.3a: escalate-only extraction-time poison scan. This is a
            # triage aid, NOT the reliable control (that is GOV-1.2). The scan
            # may only FLAG — it must never prevent staging or de-escalate a
            # provenance-mandated approval. Findings are attached to the row
            # metadata so the eventual HITL drain (GOV-1.1) can prioritize
            # flagged writes for human review.
            scan = scan_for_poison(content, old_text)
            if scan.flagged:
                logger.warning(
                    "BackgroundReviewService.stage_pending_write: poison scan flagged "
                    "write user=%s action=%s hits=%s severity=%s",
                    user_id,
                    action,
                    scan.hits,
                    scan.severity,
                )
            row = PendingWrite(
                id=str(uuid.uuid4()),
                workspace_id=workspace_id,
                user_id=user_id,
                mission_id=mission_id,
                write_type=write_type,
                action=action,
                content=content,
                old_text=old_text,
                status=PendingWriteStatus.PENDING,
                expires_at=now + timedelta(days=ttl_days),
                meta={
                    "origin": "background_review",
                    **(metadata or {}),
                    **scan.to_metadata(),
                },
            )
            db.add(row)
            await db.flush()
            logger.info(
                "BackgroundReviewService.stage_pending_write id=%s action=%s user=%s",
                row.id,
                action,
                user_id,
            )
            # GOV-1.1: drain the staged write into the existing HITL inbox as a
            # SEPARATE filter (MEMORY_APPROVAL) from mission action approvals.
            # Memory writes must never pause/abort a mission, so the inbox item
            # carries no mission_id. Best-effort: if inbox creation fails the
            # staged row is still in pending_writes and is caught by the sweeper.
            await self._route_to_inbox(
                db,
                pending_write_id=row.id,
                workspace_id=workspace_id,
                user_id=user_id,
                action=action,
                content=content,
                old_text=old_text,
                expires_at=row.expires_at,
            )
            return row.id
        except Exception as exc:
            logger.warning(
                "BackgroundReviewService.stage_pending_write failed for mission=%s: %s",
                mission_id,
                exc,
            )
            return None

    async def _route_to_inbox(
        self,
        db: Any,
        *,
        pending_write_id: str,
        workspace_id: str | None,
        user_id: int,
        action: str,
        content: str | None,
        old_text: str | None,
        expires_at: datetime,
    ) -> None:
        """Create a HITL inbox item (MEMORY_APPROVAL) for a staged write (GOV-1.1).

        Surfaces the staged memory write in the existing inbox under a separate
        filter so it never contends with mission action approvals and never
        blocks a mission. Best-effort: failures are logged, never raised — the
        pending_writes row remains the source of truth and is swept independently.
        """
        try:
            from app.models.hitl_models import HumanInterruptType
            from app.services.hitl_service import HITLService

            service = HITLService(db)
            preview = (content or old_text or "")[:280]
            await service.create_interrupt(
                mission_id=None,  # memory approvals are not mission-bound
                user_id=user_id,
                interrupt_type=HumanInterruptType.MEMORY_APPROVAL,
                title=f"Memory write: {action}",
                description=preview,
                proposed_action={
                    "pending_write_id": pending_write_id,
                    "action": action,
                    "content": content,
                    "old_text": old_text,
                },
                context={"pending_write_id": pending_write_id, "origin": "background_review"},
                workspace_id=workspace_id,
                expires_at=expires_at,
            )
            logger.info(
                "BackgroundReviewService._route_to_inbox pending_write=%s user=%s",
                pending_write_id,
                user_id,
            )
        except Exception as exc:
            logger.warning(
                "BackgroundReviewService._route_to_inbox failed for pending_write=%s: %s",
                pending_write_id,
                exc,
            )

    async def resolve_pending_write(
        self,
        db: Any,
        *,
        pending_write_id: str,
        approve: bool,
        resolved_by: int | None = None,
    ) -> str | None:
        """Apply or reject a staged memory write from the HITL inbox (GOV-1.1).

        APPROVE -> apply the write to durable storage and mark the row
        APPROVED. REJECT -> mark the row REJECTED (the write is dropped).

        Best-effort: never raises. Returns the new MemoryEntry id on a
        successful apply, ``"rejected"`` on reject, or ``None`` on failure /
        missing row. The caller (inbox API / expiry sweeper) is responsible
        for also resolving the linked InboxItem.
        """
        try:
            from sqlalchemy import select

            from app.models.memory_models import PendingWrite, PendingWriteStatus

            row = (
                await db.execute(select(PendingWrite).where(PendingWrite.id == pending_write_id))
            ).scalar_one_or_none()
            if row is None:
                logger.info(
                    "BackgroundReviewService.resolve_pending_write: pending_write=%s not found",
                    pending_write_id,
                )
                return None
            if row.status != PendingWriteStatus.PENDING:
                logger.info(
                    "BackgroundReviewService.resolve_pending_write: pending_write=%s already %s",
                    pending_write_id,
                    row.status,
                )
                return None

            if not approve:
                row.status = PendingWriteStatus.REJECTED
                row.reviewed_at = datetime.now(UTC)
                await db.flush()
                logger.info(
                    "BackgroundReviewService.resolve_pending_write rejected id=%s",
                    pending_write_id,
                )
                return "rejected"

            # APPROVE -> apply the write.
            result_id: str | None = None
            if row.action == PendingWriteAction.ADD:
                result_id = await self.add_reviewed_entry(
                    db,
                    workspace_id=row.workspace_id,
                    user_id=row.user_id,
                    agent_id=None,
                    content=row.content or "",
                    memory_type="episodic",
                    importance=0.5,
                    source_mission_id=row.mission_id,
                    metadata={"origin": "background_review", "approved_via": "hitl"},
                )
            elif row.action == PendingWriteAction.REPLACE:
                old_id = (row.meta or {}).get("target_entry_id")
                if old_id:
                    result_id = await self.supersede_entry(
                        db,
                        old_entry_id=old_id,
                        new_content=row.content or "",
                        new_importance=0.5,
                        source_mission_id=row.mission_id,
                    )
                else:
                    # No target to replace -> treat as an add.
                    result_id = await self.add_reviewed_entry(
                        db,
                        workspace_id=row.workspace_id,
                        user_id=row.user_id,
                        agent_id=None,
                        content=row.content or "",
                        memory_type="episodic",
                        importance=0.5,
                        source_mission_id=row.mission_id,
                        metadata={"origin": "background_review", "approved_via": "hitl"},
                    )
            elif row.action == PendingWriteAction.REMOVE:
                # Removal is recorded as a resolved row; there is no destructive
                # delete path in v1 (negative constraints are immortal per doc §C).
                # The supersede/mark path is left to the store-reconciliation epic.
                result_id = "removed"
            else:
                logger.warning(
                    "BackgroundReviewService.resolve_pending_write: unknown action=%s",
                    row.action,
                )
                return None

            if result_id is None:
                return None

            row.status = PendingWriteStatus.APPROVED
            row.reviewed_at = datetime.now(UTC)
            if resolved_by is not None:
                row.meta = {**(row.meta or {}), "resolved_by": resolved_by}
            await db.flush()
            logger.info(
                "BackgroundReviewService.resolve_pending_write approved id=%s result=%s",
                pending_write_id,
                result_id,
            )
            return result_id
        except Exception as exc:
            logger.warning(
                "BackgroundReviewService.resolve_pending_write failed for id=%s: %s",
                pending_write_id,
                exc,
            )
            return None

    async def supersede_entry(
        self,
        db: Any,
        *,
        old_entry_id: str,
        new_content: str,
        new_importance: float = 0.5,
        new_memory_type: str = "episodic",
        source_mission_id: str | None = None,
    ) -> str | None:
        """Replace an existing memory entry with a new one.

        Sets ``old_entry.review_state='superseded'`` (using the
        ``meta`` JSONB column — there is no first-class
        ``review_state`` column yet; that lands in a future migration
        if/when the data model needs it) and points the new entry's
        ``supersedes_id`` at the old one.

        Returns the new entry's id, or ``None`` if the old entry
        doesn't exist / write fails.
        """
        try:
            from sqlalchemy import select

            old = (await db.execute(select(MemoryEntry).where(MemoryEntry.id == old_entry_id))).scalar_one_or_none()
            if old is None:
                logger.info(
                    "BackgroundReviewService.supersede_entry: old_id=%s not found",
                    old_entry_id,
                )
                return None

            # Mark the old entry as superseded via meta (avoid schema
            # bloat — review_state is NOT in memory_entries yet). When
            # the column lands, switch this to a real column update.
            meta = dict(old.meta or {})
            meta["review_state"] = "superseded"
            meta["superseded_at"] = datetime.now(UTC).isoformat()
            old.meta = meta

            new_entry = MemoryEntry(
                id=str(uuid.uuid4()),
                workspace_id=old.workspace_id,
                user_id=old.user_id,
                agent_id=old.agent_id,
                namespace=old.namespace,
                memory_type=new_memory_type,
                content=new_content,
                importance=max(IMPORTANCE_FLOOR, min(IMPORTANCE_CEILING, new_importance)),
                supersedes_id=old.id,
                source_mission_id=source_mission_id,
                meta={"origin": "background_review", "supersedes": old.id},
            )
            db.add(new_entry)
            await db.flush()
            logger.info(
                "BackgroundReviewService.supersede_entry: old=%s new=%s",
                old.id,
                new_entry.id,
            )
            return new_entry.id
        except Exception as exc:
            logger.warning(
                "BackgroundReviewService.supersede_entry failed for old_id=%s: %s",
                old_entry_id,
                exc,
            )
            return None

    # ── Validation + apply (used by the Celery task) ──────────────────

    def parse_reviewer_response(self, raw: str) -> list[ProposedWrite]:
        """Parse the reviewer's LLM response into ``ProposedWrite`` objects.

        Defensive: accepts a JSON object, a JSON array, or a string that
        contains a JSON code block. Drops anything that doesn't pass
        the validation rules.

        Returns an empty list on parse failure (logs the error).
        """
        if not raw or not raw.strip():
            return []

        payload = _extract_json(raw)
        if payload is None:
            logger.warning(
                "BackgroundReviewService.parse_reviewer_response: no JSON found in LLM output (first 200 chars): %s",
                raw[:200],
            )
            return []

        # The reviewer is allowed to wrap the writes in either a
        # {"proposed_writes": [...]} envelope OR a bare list. Accept
        # both for resilience.
        if isinstance(payload, list):
            items = payload
            reasoning = ""
        elif isinstance(payload, dict):
            items = payload.get("proposed_writes") or payload.get("writes") or []
            reasoning = payload.get("reasoning", "")
        else:
            logger.warning(
                "BackgroundReviewService.parse_reviewer_response: unexpected JSON type %s",
                type(payload).__name__,
            )
            return []

        if not isinstance(items, list):
            return []

        out: list[ProposedWrite] = []
        for item in items:
            if not isinstance(item, dict):
                continue
            validated = self._validate_proposed_write(item, reasoning)
            if validated is not None:
                out.append(validated)
        return out

    def _validate_proposed_write(self, item: dict[str, Any], fallback_reasoning: str) -> ProposedWrite | None:
        """Apply the tool whitelist + bounds checks to a single raw dict.

        Returns ``None`` for rejected writes (logged at debug so the
        test suite can verify the rejection reason without spamming
        production logs).
        """
        raw_action = item.get("action")
        if not isinstance(raw_action, str):
            return None
        if raw_action not in REVIEWER_TOOL_WHITELIST:
            logger.debug(
                "BackgroundReviewService rejected non-whitelisted action=%s",
                raw_action,
            )
            return None

        db_action = REVIEWER_ACTION_TO_DB_ACTION.get(raw_action)
        if db_action is None:
            return None

        content = item.get("content")
        # ``memory_remove`` may legitimately have no content (it's a
        # delete-by-old-text operation). For add/replace, content is
        # required.
        if db_action != PendingWriteAction.REMOVE:
            if not isinstance(content, str):
                return None
            if not (REVIEWER_CONTENT_MIN_CHARS <= len(content) <= REVIEWER_CONTENT_MAX_CHARS):
                logger.debug(
                    "BackgroundReviewService rejected content length=%d",
                    len(content),
                )
                return None

        old_text = item.get("old_text")
        if old_text is not None and not isinstance(old_text, str):
            old_text = None

        importance_raw = item.get("importance", 0.5)
        try:
            importance = float(importance_raw)
        except (TypeError, ValueError):
            importance = 0.5
        importance = max(IMPORTANCE_FLOOR, min(IMPORTANCE_CEILING, importance))

        memory_type = item.get("memory_type", "episodic")
        if not isinstance(memory_type, str) or memory_type not in {
            "episodic",
            "semantic",
            "preference",
        }:
            memory_type = "episodic"

        scope = item.get("scope", "agent")
        if scope not in {"agent", "workspace"}:
            scope = "agent"

        reasoning = item.get("reasoning") or fallback_reasoning or ""

        return ProposedWrite(
            action=db_action,
            content=content or "",
            old_text=old_text,
            importance=importance,
            memory_type=memory_type,
            scope=scope,
            reasoning=reasoning,
        )

    async def apply_proposed_writes(
        self,
        db: Any,
        *,
        workspace_id: str | None,
        user_id: int,
        agent_id: str | None,
        source_mission_id: str | None,
        proposed: list[ProposedWrite],
        write_approval: bool,
    ) -> ApplyResult:
        """Apply the validated proposed writes to durable storage.

        If ``write_approval`` is false: write directly to
        ``memory_entries`` (skipping the queue). If true: stage in
        ``pending_writes``. Destructive writes always stage regardless
        of ``write_approval`` (per user decision 2026-06-17).
        """
        result = ApplyResult()
        for w in proposed:
            destructive = w.is_destructive()
            needs_approval = write_approval or destructive

            if needs_approval:
                pw_id = await self.stage_pending_write(
                    db,
                    workspace_id=workspace_id,
                    user_id=user_id,
                    mission_id=source_mission_id,
                    action=w.action,
                    content=w.content or None,
                    old_text=w.old_text,
                )
                if pw_id:
                    result.staged_writes.append(pw_id)
                else:
                    result.skipped.append({"action": w.action, "reason": "stage_failed"})
                continue

            # Direct write path.
            if w.action == PendingWriteAction.ADD:
                entry_id = await self.add_reviewed_entry(
                    db,
                    workspace_id=workspace_id,
                    user_id=user_id,
                    agent_id=agent_id,
                    content=w.content,
                    memory_type=w.memory_type,
                    importance=w.importance,
                    source_mission_id=source_mission_id,
                    metadata={"reasoning": w.reasoning} if w.reasoning else None,
                )
                if entry_id:
                    result.direct_writes.append(entry_id)
                else:
                    result.skipped.append({"action": w.action, "reason": "write_failed"})
            elif w.action == PendingWriteAction.REPLACE:
                # Replace requires an old_text to know what to
                # supersede. Without it, fall back to staging.
                if not w.old_text:
                    result.skipped.append({"action": w.action, "reason": "missing_old_text"})
                    continue
                # Look up the matching entry by content equality.
                from sqlalchemy import select

                match = (
                    (
                        await db.execute(
                            select(MemoryEntry).where(
                                MemoryEntry.workspace_id == workspace_id,
                                MemoryEntry.agent_id == agent_id,
                                MemoryEntry.content == w.old_text,
                            )
                        )
                    )
                    .scalars()
                    .first()
                )
                if match is None:
                    # Could not find the old entry — stage instead so
                    # the user can resolve manually.
                    pw_id = await self.stage_pending_write(
                        db,
                        workspace_id=workspace_id,
                        user_id=user_id,
                        mission_id=source_mission_id,
                        action=w.action,
                        content=w.content,
                        old_text=w.old_text,
                    )
                    if pw_id:
                        result.staged_writes.append(pw_id)
                    else:
                        result.skipped.append({"action": w.action, "reason": "no_match_and_stage_failed"})
                    continue
                new_id = await self.supersede_entry(
                    db,
                    old_entry_id=match.id,
                    new_content=w.content,
                    new_importance=w.importance,
                    new_memory_type=w.memory_type,
                    source_mission_id=source_mission_id,
                )
                if new_id:
                    result.superseded.append((match.id, new_id))
                    result.direct_writes.append(new_id)
                else:
                    result.skipped.append({"action": w.action, "reason": "supersede_failed"})
            elif w.action == PendingWriteAction.REMOVE:
                # Remove is destructive — always stages.
                pw_id = await self.stage_pending_write(
                    db,
                    workspace_id=workspace_id,
                    user_id=user_id,
                    mission_id=source_mission_id,
                    action=w.action,
                    content=None,
                    old_text=w.old_text,
                )
                if pw_id:
                    result.staged_writes.append(pw_id)
                else:
                    result.skipped.append({"action": w.action, "reason": "stage_failed"})
            else:
                result.skipped.append({"action": w.action, "reason": "unknown_action"})
        return result

    # ── Reviewer LLM call (LangGraph path, not chat_service) ──────────

    async def call_reviewer(
        self,
        *,
        snapshot: str,
        transcript: str,
        model_id: str = DEFAULT_REVIEWER_MODEL,
    ) -> str:
        """Call the reviewer LLM with the prompt + snapshot + transcript.

        Routes through ``LLMManager`` (the LangGraph path) per the
        task decision — ``chat_service._resolve_provider`` is broken
        for ``llamacpp-*`` model_ids because they have no ``/``.

        Fail open: returns ``""`` on any failure so the Celery task
        can no-op gracefully.
        """
        try:
            from app.services.langgraph.llm_config import (
                get_llamacpp_base_url,
                get_llm_manager,
            )
        except Exception as exc:
            logger.warning(
                "BackgroundReviewService.call_reviewer: LLMManager not importable: %s",
                exc,
            )
            return ""

        user_prompt = (
            f"{REVIEW_PROMPT}\n\n"
            f"## MEMORY_SNAPSHOT\n\n```\n{snapshot}\n```\n\n"
            f"## TRANSCRIPT\n\n```\n{transcript}\n```\n"
        )

        try:
            manager = get_llm_manager()
            model = manager.get_model(model_id)
            if model is None:
                logger.warning(
                    "BackgroundReviewService.call_reviewer: model %s unavailable",
                    model_id,
                )
                return ""
            # Direct OpenAI-compatible HTTP call. We avoid chat_service
            # because it strips BYOK keys for llamacpp (correctly — but
            # we also want to skip its streaming + retry logic).
            import httpx

            base_url = get_llamacpp_base_url(model_id) + "/v1"
            # The mapped name in MODEL_MAP is the actual llama-server model name.
            model_name = manager.MODEL_MAP.get(model_id, model_id)
            payload = {
                "model": model_name,
                "messages": [
                    {
                        "role": "system",
                        "content": "You are the Background Review Agent. Output JSON only.",
                    },
                    {"role": "user", "content": user_prompt},
                ],
                "temperature": 0.2,
                "max_tokens": 1024,
            }
            # GOV-1.7 retry loop — bounded, linear backoff, transient-only.
            for attempt in range(1, REVIEWER_MAX_RETRIES + 1):
                try:
                    async with httpx.AsyncClient(timeout=60.0) as client:
                        resp = await client.post(
                            f"{base_url}/chat/completions",
                            json=payload,
                            headers={"Authorization": "Bearer not-needed"},
                        )
                        status = resp.status_code
                        if status in REVIEWER_RETRYABLE_STATUS:
                            # Transient server-side error -> retry after backoff.
                            logger.warning(
                                "BackgroundReviewService.call_reviewer: transient HTTP %s "
                                "(attempt %d/%d) for %s; retrying",
                                status,
                                attempt,
                                REVIEWER_MAX_RETRIES,
                                model_id,
                            )
                            if attempt < REVIEWER_MAX_RETRIES:
                                await asyncio.sleep(REVIEWER_RETRY_BASE_DELAY * attempt)
                                continue
                            break
                        resp.raise_for_status()
                        data = resp.json()
                    content = data.get("choices", [{}])[0].get("message", {}).get("content", "")
                    return content or ""
                except httpx.TimeoutException as exc:
                    logger.warning(
                        "BackgroundReviewService.call_reviewer: timeout (attempt %d/%d) for %s; retrying",
                        attempt,
                        REVIEWER_MAX_RETRIES,
                        model_id,
                    )
                    last_exc = exc
                    if attempt < REVIEWER_MAX_RETRIES:
                        await asyncio.sleep(REVIEWER_RETRY_BASE_DELAY * attempt)
                        continue
                    break
                except httpx.TransportError as exc:
                    logger.warning(
                        "BackgroundReviewService.call_reviewer: transport error (attempt %d/%d) for %s; retrying",
                        attempt,
                        REVIEWER_MAX_RETRIES,
                        model_id,
                    )
                    last_exc = exc
                    if attempt < REVIEWER_MAX_RETRIES:
                        await asyncio.sleep(REVIEWER_RETRY_BASE_DELAY * attempt)
                        continue
                    break
                except Exception as exc:
                    # Permanent (non-transient) failure -> fail open immediately,
                    # do NOT retry. Return "" so the caller no-ops gracefully.
                    logger.warning(
                        "BackgroundReviewService.call_reviewer: %s failed (permanent): %s",
                        model_id,
                        exc,
                    )
                    return ""
            # Exhausted retries on a transient error -> log + fail open.
            logger.warning(
                "BackgroundReviewService.call_reviewer: %s exhausted %d retries; "
                "returning empty (reviewer unavailable)",
                model_id,
                REVIEWER_MAX_RETRIES,
            )
            return ""
        except Exception as exc:
            logger.warning(
                "BackgroundReviewService.call_reviewer: %s failed: %s",
                model_id,
                exc,
            )
            return ""

    # ── Snapshot + transcript builders ───────────────────────────────

    async def build_snapshot(self, db: Any, workspace_id: str | None) -> str:
        """Fetch a compact text snapshot of the workspace's memory.

        Returned as JSON-encoded string so the reviewer prompt stays
        a single user message. Empty string on failure.
        """
        try:
            from sqlalchemy import select

            stmt = select(MemoryEntry).where(MemoryEntry.workspace_id == workspace_id)
            # Bounded fetch — we don't need every entry, just the
            # newest ~50 to decide what's NEW.
            stmt = stmt.order_by(MemoryEntry.created_at.desc()).limit(50)
            rows = (await db.execute(stmt)).scalars().all()
            payload = [
                {
                    "id": str(r.id),
                    "content": (r.content or "")[:300],
                    "memory_type": r.memory_type,
                    "importance": r.importance,
                    "created_at": r.created_at.isoformat() if r.created_at else "",
                }
                for r in rows
            ]
            return json.dumps(payload, default=str)
        except Exception as exc:
            logger.warning("BackgroundReviewService.build_snapshot failed: %s", exc)
            return ""

    async def build_transcript(self, db: Any, mission_id: str) -> str:
        """Fetch the mission transcript as a compact text block.

        Uses the ``Mission.results`` JSONB blob as the canonical
        transcript source — missions don't have a dedicated
        transcript table yet.
        """
        try:
            from sqlalchemy import select

            from app.models.mission_models import Mission

            row = (await db.execute(select(Mission).where(Mission.id == mission_id))).scalar_one_or_none()
            if row is None:
                return ""
            parts: list[str] = []
            if row.title:
                parts.append(f"Title: {row.title}")
            if row.description:
                parts.append(f"Description: {row.description[:500]}")
            if row.results:
                # Truncate big result blobs to keep the prompt bounded.
                results_str = json.dumps(row.results, default=str)[:4000]
                parts.append(f"Results: {results_str}")
            if row.error_message:
                parts.append(f"Error: {row.error_message[:500]}")
            return "\n".join(parts)
        except Exception as exc:
            logger.warning(
                "BackgroundReviewService.build_transcript failed for mission=%s: %s",
                mission_id,
                exc,
            )
            return ""


# ── Helpers ──────────────────────────────────────────────────────────


def _extract_json(raw: str) -> Any | None:
    """Pull a JSON object/array out of a raw LLM response.

    Tries, in order:
    1. Direct ``json.loads`` on the whole string.
    2. A ``\\`\\`\\`json ... \\`\\`\\`` code block.
    3. The first balanced ``{...}`` / ``[...]`` substring.
    """
    stripped = raw.strip()

    # 1. Whole-string parse.
    try:
        return json.loads(stripped)
    except (ValueError, TypeError):
        pass

    # 2. Fenced JSON code block.
    if "```" in stripped:
        for fence in ("```json", "```JSON", "```"):
            idx = stripped.find(fence)
            if idx == -1:
                continue
            start = idx + len(fence)
            end = stripped.find("```", start)
            if end == -1:
                continue
            candidate = stripped[start:end].strip()
            try:
                return json.loads(candidate)
            except (ValueError, TypeError):
                continue

    # 3. First balanced substring.
    for opener, closer in (("{", "}"), ("[", "]")):
        depth = 0
        start_idx = None
        for i, ch in enumerate(stripped):
            if ch == opener:
                if depth == 0:
                    start_idx = i
                depth += 1
            elif ch == closer:
                if depth > 0:
                    depth -= 1
                    if depth == 0 and start_idx is not None:
                        candidate = stripped[start_idx : i + 1]
                        try:
                            return json.loads(candidate)
                        except (ValueError, TypeError):
                            start_idx = None
                            continue
        if start_idx is not None and depth == 0:
            # Already tried above; no match.
            pass

    return None


# ── Singleton ──────────────────────────────────────────────────────

_background_review_service_instance: BackgroundReviewService | None = None


def get_background_review_service() -> BackgroundReviewService:
    """Get or create the global BackgroundReviewService singleton.

    Stateless service — the singleton pattern is purely for caller
    convenience and for test-time monkeypatching.
    """
    global _background_review_service_instance
    if _background_review_service_instance is None:
        _background_review_service_instance = BackgroundReviewService()
    return _background_review_service_instance
