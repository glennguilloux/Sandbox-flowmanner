"""Resume validation — sanity-check the event log before resuming a run.

Q1-A chunk 4: Prevents silent data corruption from missing, corrupt,
or out-of-order events by inspecting the last N events and surfacing
anomalies as warnings or a hard ``is_resumable=False`` flag.

Contract:
- READ-ONLY: queries the event log, does not modify it.
- NEVER raises on corrupt state — returns a structured ``ResumeValidation``.
- The caller (UnifiedExecutor) decides whether to emit run.failed or
  run.resumed events based on the returned object.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from app.models.substrate_models import SubstrateEventType
from app.services.substrate.event_log import EventLog, get_event_log

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ResumeValidation:
    """Structured result of a resume-validation check.

    Frozen because it is a diagnostic snapshot, not a mutable state object.
    """

    run_id: str
    last_event_sequence: int
    last_checkpoint_sequence: int | None
    last_completed_node_id: str | None
    in_flight_node_id: str | None  # node.started without matching node.completed
    warnings: list[str] = field(default_factory=list)
    is_resumable: bool = True


async def validate_resume_state(
    db: AsyncSession,
    run_id: str,
    event_log: EventLog | None = None,
) -> ResumeValidation:
    """Validate the event log state before resuming a crashed run.

    Reads the last 100 events and checks for structural anomalies:
    - Orphan checkpoints (checkpoint for a node that never completed)
    - Duplicate completions (two node.completed for the same node)
    - Checkpoint lag (checkpoint lags >50 events behind the latest event)
    - In-flight nodes (node.started without matching node.completed)

    Args:
        db: Async database session
        run_id: UUID string identifying the execution run
        event_log: Optional EventLog instance (defaults to singleton)

    Returns:
        ResumeValidation with diagnostic fields.  ``is_resumable=False``
        means the caller should emit a run.failed event and bail.
    """
    el = event_log or get_event_log()

    # Fetch last 100 events in sequence order, then reverse for reverse scan.
    recent_events = await el.get_events(db, run_id, limit=100)
    if not recent_events:
        return ResumeValidation(run_id=run_id, last_event_sequence=0, last_checkpoint_sequence=None, last_completed_node_id=None, in_flight_node_id=None)

    last_event_sequence = recent_events[-1].sequence

    # ── Single pass (reverse) to find latest checkpoint and completed node ──
    last_checkpoint_sequence: int | None = None
    last_completed_node_id: str | None = None

    for ev in reversed(recent_events):
        if last_checkpoint_sequence is None and ev.type == SubstrateEventType.CHECKPOINT:
            last_checkpoint_sequence = ev.sequence
        if last_completed_node_id is None and ev.type == SubstrateEventType.NODE_COMPLETED:
            last_completed_node_id = (ev.payload or {}).get("task_id")
        if last_checkpoint_sequence is not None and last_completed_node_id is not None:
            break

    # ── Scan for in-flight node, duplicates, orphan checkpoints ──
    started_nodes: set[str] = set()
    completed_nodes: set[str] = set()
    checkpoint_nodes: set[str] = set()
    warnings: list[str] = []
    in_flight_node_id: str | None = None

    for ev in recent_events:
        payload = ev.payload or {}
        if ev.type == SubstrateEventType.NODE_STARTED:
            started_nodes.add(payload.get("task_id", ""))
        elif ev.type == SubstrateEventType.NODE_COMPLETED:
            nid = payload.get("task_id", "")
            if nid in completed_nodes:
                warnings.append("duplicate_completion")
                return ResumeValidation(
                    run_id=run_id,
                    last_event_sequence=last_event_sequence,
                    last_checkpoint_sequence=last_checkpoint_sequence,
                    last_completed_node_id=last_completed_node_id,
                    in_flight_node_id=None,
                    warnings=warnings,
                    is_resumable=False,
                )
            completed_nodes.add(nid)
        elif ev.type == SubstrateEventType.CHECKPOINT:
            ck_nid = payload.get("task_id")
            if ck_nid is not None:
                checkpoint_nodes.add(ck_nid)

    # In-flight = started but not completed
    in_flight_set = started_nodes - completed_nodes
    if in_flight_set:
        in_flight_node_id = in_flight_set.pop()

    # Orphan checkpoint = checkpoint references a node that never completed
    orphan_ckpt_nodes = checkpoint_nodes - completed_nodes
    if orphan_ckpt_nodes:
        warnings.append("orphan_checkpoint")
        return ResumeValidation(
            run_id=run_id,
            last_event_sequence=last_event_sequence,
            last_checkpoint_sequence=last_checkpoint_sequence,
            last_completed_node_id=last_completed_node_id,
            in_flight_node_id=in_flight_node_id,
            warnings=warnings,
            is_resumable=False,
        )

    # Checkpoint lag
    if last_checkpoint_sequence is not None and (last_event_sequence - last_checkpoint_sequence) > 50:
        warnings.append("checkpoint_lag")

    return ResumeValidation(
        run_id=run_id,
        last_event_sequence=last_event_sequence,
        last_checkpoint_sequence=last_checkpoint_sequence,
        last_completed_node_id=last_completed_node_id,
        in_flight_node_id=in_flight_node_id,
        warnings=warnings,
        is_resumable=True,
    )
