"""Background review Celery task — reviews a completed mission.

Single task: ``review_mission(mission_id)``. Invoked by
``services/improvement/improvement_loop_v2.on_mission_complete`` via
fire-and-forget ``asyncio.create_task`` (per the task decision:
no signature change on ``on_mission_complete``, the review is a
peer concern to the existing improvement loop, not a replacement).

Skip rules (evaluated INSIDE this task by re-fetching the mission
from the DB — option (B) from the verification report, because
``on_mission_complete`` does not receive duration / turn_count):

- Mission duration < 10 seconds  → skip (no signal).
- Mission turn count < 3         → skip (no signal).
- Mission missing or not in a terminal status → skip.

Best-effort semantics: a runtime failure (LLM down, DB hiccup,
JSON parse error) MUST NOT propagate — the task returns a structured
error dict and increments the Langfuse span's
``status_message="error"`` counter. The mission that triggered the
review already completed; the review is a side effect.

Langfuse spans (4, per the plan):

- ``memory.review.reviewer_call``     — the LLM call
- ``memory.review.validation``        — JSON parse + whitelist check
- ``memory.review.apply_writes``      — direct / staged writes
- ``memory.review.supersede_resolution`` — how supersedes were resolved
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import os
import time
import uuid
from datetime import UTC, datetime
from typing import Any

from .celery_app import celery_app

logger = logging.getLogger(__name__)

# Skip thresholds. Picked per the task decision:
# - <10s missions are too short to have learned anything.
# - <3 turns are likely trivial one-shots.
MIN_MISSION_DURATION_SECONDS = 10.0
MIN_MISSION_TURN_COUNT = 3


def _get_langfuse_service():
    """Lazy-import the Langfuse service. Returns None if unavailable.

    Importing inside the function keeps this module importable in
    test contexts where Langfuse is mocked or disabled.
    """
    try:
        from app.services.langfuse_service import get_langfuse_service

        return get_langfuse_service()
    except Exception as exc:  # pragma: no cover - defensive
        logger.debug("Langfuse unavailable for background review spans: %s", exc)
        return None


async def _record_review_gap(
    mission_id: str,
    workspace: str | None,
    user_id: int | None,
    reason: str,
    detail: str | None = None,
) -> None:
    """Persist a durable audit-log gap record when the reviewer fails (GOV-1.7).

    A reviewer failure must not be a silent memory hole. We write a durable
    ``audit_logs`` row (best-effort) so there is a persistent, queryable record
    that a mission's background review did not complete. The task never raises
    from here — failing to log a gap must not fail the review task.
    """
    try:
        from app.database import AsyncSessionLocal
        from app.models.legacy_models import AuditLog

        log = AuditLog(
            id=str(uuid.uuid4()),
            timestamp=datetime.now(UTC),
            action="memory.review.gap",
            action_details=json.dumps(
                {
                    "mission_id": mission_id,
                    "workspace_id": workspace,
                    "reason": reason,
                    "detail": detail,
                }
            )[:4000],
            user_id=user_id,
            endpoint="/api/memory/background-review",
            method="REVIEW",
        )
        async with AsyncSessionLocal() as db:
            db.add(log)
            await db.commit()
        logger.warning(
            "memory.review.gap recorded for mission=%s reason=%s",
            mission_id,
            reason,
        )
    except Exception as exc:  # pragma: no cover - defensive
        logger.warning(
            "memory.review.gap FAILED to persist for mission=%s: %s",
            mission_id,
            exc,
        )


def _count_turns(mission: Any) -> int:
    """Best-effort turn count from a Mission ORM object.

    Missions don't have a first-class ``turn_count`` column; we count
    the length of ``Mission.results["turns"]`` if it's a list, else
    the number of ``MissionTask`` rows associated with the mission.
    Returns 0 on any failure.
    """
    try:
        results = getattr(mission, "results", None) or {}
        if isinstance(results, dict):
            turns = results.get("turns")
            if isinstance(turns, list):
                return len(turns)
            messages = results.get("messages")
            if isinstance(messages, list):
                return len(messages)
        tasks = getattr(mission, "tasks", None)
        if tasks is not None:
            try:
                return len(tasks)
            except TypeError:
                pass
        return 0
    except Exception:
        return 0


def _mission_duration_seconds(mission: Any) -> float:
    """Mission wall-clock duration from started_at / completed_at.

    Returns 0.0 if either timestamp is missing — the caller treats 0
    as "too short" and skips.
    """
    try:
        started = getattr(mission, "started_at", None)
        completed = getattr(mission, "completed_at", None)
        if started is None or completed is None:
            return 0.0
        if isinstance(started, str):
            started = datetime.fromisoformat(started.replace("Z", "+00:00"))
        if isinstance(completed, str):
            completed = datetime.fromisoformat(completed.replace("Z", "+00:00"))
        return max(0.0, (completed - started).total_seconds())
    except Exception:
        return 0.0


@celery_app.task(
    name="app.tasks.background_review_tasks.review_mission",
    bind=True,
    max_retries=2,
    default_retry_delay=30,
    acks_late=True,
)
def review_mission(self, mission_id: str) -> dict[str, Any]:
    """Background self-improvement review after mission completion.

    Returns a structured summary dict so the dispatch log shows what
    happened even when no human is looking. The dict is also the
    return value the API can expose to a future "what did the reviewer
    decide" endpoint.
    """
    started = time.perf_counter()
    summary: dict[str, Any] = {
        "mission_id": mission_id,
        "outcome": "skipped",
        "reason": "",
        "direct_writes": 0,
        "staged_writes": 0,
        "superseded": 0,
        "duration_ms": 0,
        "reviewer_model": "",
        "error": "",
    }

    langfuse = _get_langfuse_service()
    trace = (
        langfuse.trace(
            name="background_review",
            metadata={"mission_id": mission_id},
            tags=["memory", "background_review"],
        )
        if langfuse
        else None
    )

    try:
        asyncio.run(_review_mission_async(mission_id, summary, trace))
    except Exception as exc:
        # Last-ditch catch — ``_review_mission_async`` is supposed to
        # swallow its own errors. This branch only fires on something
        # truly unexpected (event-loop crash, import error).
        logger.exception("review_mission crashed for mission=%s", mission_id)
        summary["outcome"] = "error"
        summary["error"] = str(exc)
    finally:
        summary["duration_ms"] = int((time.perf_counter() - started) * 1000)
        logger.info("review_mission summary: %s", summary)
        if trace is not None and hasattr(trace, "update"):
            with contextlib.suppress(Exception):
                trace.update(output=summary)

    return summary


async def _review_mission_async(
    mission_id: str,
    summary: dict[str, Any],
    trace: Any,
) -> None:
    """Async body of ``review_mission``.

    All DB + LLM work happens here. Returns updates ``summary`` in
    place — the Celery task reads it after ``asyncio.run`` returns.
    """
    from app.database import AsyncSessionLocal
    from app.services.memory.background_review_service import (
        BackgroundReviewService,
        compute_write_approval,
        get_background_review_service,
    )

    service = get_background_review_service()

    # ── 1. Re-fetch the mission + apply skip rules ───────────────────
    async with AsyncSessionLocal() as db:
        from sqlalchemy import select

        from app.models.mission_models import Mission

        mission = (await db.execute(select(Mission).where(Mission.id == mission_id))).scalar_one_or_none()

        if mission is None:
            summary["outcome"] = "skipped"
            summary["reason"] = "mission_not_found"
            return

        duration = _mission_duration_seconds(mission)
        turns = _count_turns(mission)
        if duration < MIN_MISSION_DURATION_SECONDS:
            summary["outcome"] = "skipped"
            summary["reason"] = "duration_too_short"
            return
        if turns < MIN_MISSION_TURN_COUNT:
            summary["outcome"] = "skipped"
            summary["reason"] = "turns_too_few"
            return

        workspace = getattr(mission, "workspace_id", None)
        user_id = getattr(mission, "user_id", None)
        agent_id = getattr(mission, "agent_id", None)

        # ── 2. Build the reviewer inputs ─────────────────────────────
        snapshot = await service.build_snapshot(db, workspace)
        transcript = await service.build_transcript(db, mission_id)

        # ── 3. Call the reviewer LLM (Langfuse span: reviewer_call) ──
        reviewer_span = None
        if trace is not None and hasattr(trace, "span"):
            reviewer_span = trace.span(
                name="memory.review.reviewer_call",
                metadata={
                    "mission_id": mission_id,
                    "agent_id": agent_id,
                    "workspace_id": workspace,
                    "snapshot_chars": len(snapshot),
                    "transcript_chars": len(transcript),
                },
            )
        try:
            raw_response = await service.call_reviewer(
                snapshot=snapshot,
                transcript=transcript,
            )
        except Exception as exc:
            logger.warning("reviewer LLM call failed for mission=%s: %s", mission_id, exc)
            raw_response = ""
            # GOV-1.7: do not let the failure be a silent memory hole.
            # Persist a durable gap record (best-effort) so the missing
            # review is queryable in the audit log.
            await _record_review_gap(
                mission_id=mission_id,
                workspace=workspace,
                user_id=user_id,
                reason="reviewer_exception",
                detail=str(exc)[:1000],
            )
        if reviewer_span is not None and hasattr(reviewer_span, "update"):
            with contextlib.suppress(Exception):
                reviewer_span.update(
                    output={"response_chars": len(raw_response)},
                    status_message="ok" if raw_response else "empty",
                )

        summary["reviewer_model"] = service.__class__.__name__  # cheap identifier
        # Pull the real model id from the singleton (set in __init__).

        if not raw_response:
            summary["outcome"] = "no_response"
            summary["reason"] = "reviewer_returned_empty"
            # GOV-1.7: a fail-open empty response is a silent memory hole.
            # Persist a durable gap record (best-effort) so the missing
            # review is queryable in the audit log instead of disappearing.
            await _record_review_gap(
                mission_id=mission_id,
                workspace=workspace,
                user_id=user_id,
                reason="reviewer_returned_empty",
            )
            return

        # ── 4. Parse + validate (Langfuse span: validation) ──────────
        validation_span = None
        if trace is not None and hasattr(trace, "span"):
            validation_span = trace.span(
                name="memory.review.validation",
                metadata={"response_chars": len(raw_response)},
            )
        proposed = service.parse_reviewer_response(raw_response)
        if validation_span is not None and hasattr(validation_span, "update"):
            with contextlib.suppress(Exception):
                validation_span.update(
                    output={"proposed_count": len(proposed)},
                )

        if not proposed:
            summary["outcome"] = "no_proposed_writes"
            summary["reason"] = "reviewer_returned_nothing_worth_remembering"
            return

        # ── 5. Compute write_approval per workspace rules ────────────
        from app.models.workspace_models import Workspace

        ws_orm = None
        if workspace:
            ws_orm = (await db.execute(select(Workspace).where(Workspace.id == workspace))).scalar_one_or_none()
        write_approval = compute_write_approval(ws_orm)

        # ── 6. Apply writes (Langfuse span: apply_writes) ────────────
        apply_span = None
        if trace is not None and hasattr(trace, "span"):
            apply_span = trace.span(
                name="memory.review.apply_writes",
                metadata={
                    "write_approval": write_approval,
                    "proposed_count": len(proposed),
                    "user_id": user_id,
                    "workspace_id": workspace,
                },
            )
        try:
            result = await service.apply_proposed_writes(
                db,
                workspace_id=workspace,
                user_id=user_id or 0,
                agent_id=agent_id,
                source_mission_id=mission_id,
                proposed=proposed,
                write_approval=write_approval,
            )
            await db.commit()
        except Exception as exc:
            logger.warning(
                "apply_proposed_writes failed for mission=%s: %s",
                mission_id,
                exc,
            )
            await db.rollback()
            summary["outcome"] = "apply_error"
            summary["error"] = str(exc)
            if apply_span is not None and hasattr(apply_span, "update"):
                with contextlib.suppress(Exception):
                    apply_span.update(status_message="error")
            return

        summary["direct_writes"] = len(result.direct_writes)
        summary["staged_writes"] = len(result.staged_writes)
        summary["superseded"] = len(result.superseded)
        summary["outcome"] = "applied"

        if apply_span is not None and hasattr(apply_span, "update"):
            with contextlib.suppress(Exception):
                apply_span.update(
                    output={
                        "direct_writes": result.direct_writes,
                        "staged_writes": result.staged_writes,
                        "superseded": result.superseded,
                        "skipped": result.skipped,
                    },
                )

        # ── 7. Supersede resolution span ─────────────────────────────
        if result.superseded and trace is not None and hasattr(trace, "span"):
            super_span = trace.span(
                name="memory.review.supersede_resolution",
                metadata={"count": len(result.superseded)},
            )
            with contextlib.suppress(Exception):
                super_span.update(
                    output={
                        "pairs": [{"old_id": old_id, "new_id": new_id} for old_id, new_id in result.superseded],
                    },
                )

        # ── 8. Best-effort: notify the user via SSE + notifications ──
        if result.staged_writes and user_id:
            try:
                await _notify_pending_writes(user_id, mission_id, len(result.staged_writes))
            except Exception as exc:
                logger.debug(
                    "Background review user notification failed for user=%s: %s",
                    user_id,
                    exc,
                )


async def _notify_pending_writes(user_id: int, mission_id: str, count: int) -> None:
    """Push a '💾 Agent wants to remember X' notification to the user.

    Per the user decision (2026-06-17): SSE + in-app only. No email,
    no Telegram, no push. Reuses the existing notification_service +
    sse_service — zero new infra.
    """
    try:
        from app.database import AsyncSessionLocal
        from app.services.notification_service import send_notification

        async with AsyncSessionLocal() as db:
            await send_notification(
                user_id=user_id,
                notification_type="memory_review_pending",
                data={
                    "title": "Agent wants to remember",
                    "message": (
                        f"{count} pending memory write{'s' if count != 1 else ''} from mission {mission_id[:8]}"
                    ),
                    "mission_id": mission_id,
                    "pending_count": count,
                },
                db=db,
            )
    except Exception as exc:
        logger.debug("notification_service unavailable: %s", exc)
