"""HITL pause/resume primitives (Q1-B chunk 1).

When a HITL node (APPROVAL or HUMAN_REVIEW) is reached during execution,
the executor must actually PAUSE — release the worker lease, emit a
RUN_PAUSED event, and wait for human resolution.

This module provides:
- ``HITLPaused`` exception — raised by node_executor when a HITL node is hit
- ``check_hitl_resolution`` — on resume, checks if the inbox item was resolved
- ``resume_node_context`` — builds the context for resuming a HITL node

Flow:
1. NodeExecutor._handle_hitl_interrupt() creates inbox item, raises HITLPaused
2. Strategy propagates HITLPaused (doesn't catch it)
3. UnifiedExecutor._execute_inner catches HITLPaused, releases lease, emits RUN_PAUSED
4. Human resolves inbox item via API → Celery task dispatched
5. Celery task calls UnifiedExecutor.execute(db, workflow, run_id=run_id)
6. UnifiedExecutor detects run exists + is paused → resumes
7. NodeExecutor re-enters HITL node → calls check_hitl_resolution → continues
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import select

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


# ── Exception ───────────────────────────────────────────────────────


@dataclass
class HITLPaused(Exception):
    """Raised when execution must pause for human input.

    Carries all the context needed by the executor to:
    1. Release the worker lease
    2. Emit RUN_PAUSED event
    3. On resume: find the inbox item and check its resolution

    This exception is NOT caught by strategies — it propagates up to
    UnifiedExecutor._execute_inner which handles the pause lifecycle.
    """

    inbox_item_id: str
    run_id: str
    node_id: str
    mission_id: str | None = None
    interrupt_type: str = "approval"
    title: str = ""
    context: dict[str, Any] = field(default_factory=dict)

    def __str__(self) -> str:
        return f"HITLPaused({self.interrupt_type}: {self.title}, item={self.inbox_item_id})"


# ── Resolution check ────────────────────────────────────────────────


@dataclass(frozen=True)
class HITLResolution:
    """Result of checking an inbox item's resolution status."""

    resolved: bool
    status: str  # pending, approved, rejected, clarified, expired, cancelled
    resolution_payload: dict[str, Any] | None = None
    resolution_note: str | None = None


async def check_hitl_resolution(
    db: AsyncSession,
    inbox_item_id: str,
) -> HITLResolution:
    """Check if an inbox item has been resolved.

    Called by the node executor when re-entering a HITL node during resume.
    If the item is still pending, the node should raise HITLPaused again.

    Args:
        db: Async database session.
        inbox_item_id: The inbox item ID from the original HITLPaused exception.

    Returns:
        HITLResolution with the current status.
    """
    from app.models.hitl_models import InboxItem, InboxItemStatus

    result = await db.execute(select(InboxItem).where(InboxItem.id == inbox_item_id))
    item = result.scalar_one_or_none()

    if item is None:
        logger.warning("HITL inbox item %s not found — treating as expired", inbox_item_id)
        return HITLResolution(resolved=True, status="expired")

    if item.status == InboxItemStatus.PENDING.value:
        # Check if expired
        if item.expires_at and item.expires_at < datetime.now(UTC):
            return HITLResolution(resolved=True, status="expired")
        return HITLResolution(resolved=False, status="pending")

    return HITLResolution(
        resolved=True,
        status=item.status,
        resolution_payload=item.resolution_payload,
        resolution_note=item.resolution_note,
    )
