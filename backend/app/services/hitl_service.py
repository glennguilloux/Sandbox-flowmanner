"""HITL (Human-in-the-Loop) service — Phase 6.2.

Provides:
- create_interrupt(): Persist a HumanInterrupt to inbox_items
- resolve_interrupt(): Approve/reject/clarify an inbox item
- list_pending(): List pending inbox items for a user/workspace
- expire_stale(): Mark expired items
- SSE push integration via Redis pub/sub

Usage:
    service = HITLService(db)
    item = await service.create_interrupt(
        mission_id="...", user_id=42,
        interrupt_type=HumanInterruptType.APPROVAL,
        title="Approve deployment?",
        proposed_action={"tool": "deploy", "target": "production"},
    )
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any
from uuid import uuid4

from sqlalchemy import and_, func, select

from app.models.hitl_models import (
    HumanInterruptType,
    InboxItem,
    InboxItemStatus,
)

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


class HITLService:
    """Human-in-the-Loop inbox management."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def create_interrupt(
        self,
        *,
        mission_id: str,
        user_id: int,
        interrupt_type: HumanInterruptType,
        title: str,
        description: str | None = None,
        proposed_action: dict | None = None,
        context: dict | None = None,
        task_id: str | None = None,
        node_id: str | None = None,
        run_id: str | None = None,
        workspace_id: str | None = None,
        expires_at: datetime | None = None,
    ) -> InboxItem:
        """Create a new inbox item from a HumanInterrupt."""
        item = InboxItem(
            id=str(uuid4()),
            workspace_id=workspace_id,
            user_id=user_id,
            mission_id=mission_id,
            run_id=run_id,
            task_id=task_id,
            node_id=node_id,
            interrupt_type=interrupt_type.value,
            title=title,
            description=description,
            proposed_action=proposed_action,
            context=context,
            status=InboxItemStatus.PENDING.value,
            expires_at=expires_at,
        )
        self.db.add(item)
        await self.db.flush()

        # Push real-time notification via SSE
        await self._push_inbox_event(user_id, "interrupt_raised", item)

        logger.info(
            "HITL interrupt created: id=%s type=%s mission=%s title=%s",
            item.id,
            interrupt_type.value,
            mission_id,
            title,
        )
        return item

    async def resolve_interrupt(
        self,
        item_id: str,
        *,
        resolved_by: int,
        status: InboxItemStatus,
        resolution_payload: dict | None = None,
        resolution_note: str | None = None,
    ) -> InboxItem:
        """Resolve an inbox item (approve/reject/clarify).

        The caller is responsible for resuming the mission executor
        after resolution.
        """
        result = await self.db.execute(select(InboxItem).where(InboxItem.id == item_id))
        item = result.scalar_one_or_none()
        if item is None:
            raise ValueError(f"Inbox item {item_id} not found")

        if item.status != InboxItemStatus.PENDING.value:
            raise ValueError(
                f"Inbox item {item_id} is already {item.status}, cannot resolve"
            )

        item.status = status.value
        item.resolved_at = datetime.now(UTC)
        item.resolved_by = resolved_by
        item.resolution_payload = resolution_payload
        item.resolution_note = resolution_note
        await self.db.flush()

        # Push real-time notification
        await self._push_inbox_event(item.user_id, "interrupt_resolved", item)

        logger.info(
            "HITL interrupt resolved: id=%s status=%s by=%s",
            item.id,
            status.value,
            resolved_by,
        )
        return item

    async def list_pending(
        self,
        *,
        user_id: int,
        workspace_id: str | None = None,
        interrupt_type: str | None = None,
        mission_id: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> dict[str, Any]:
        """List pending inbox items for a user/workspace."""
        conditions = [
            InboxItem.user_id == user_id,
            InboxItem.status == InboxItemStatus.PENDING.value,
        ]
        if workspace_id:
            conditions.append(InboxItem.workspace_id == workspace_id)
        if interrupt_type:
            conditions.append(InboxItem.interrupt_type == interrupt_type)
        if mission_id:
            conditions.append(InboxItem.mission_id == mission_id)

        where = and_(*conditions)

        # Count
        count_stmt = select(func.count()).select_from(InboxItem).where(where)
        total = (await self.db.execute(count_stmt)).scalar() or 0

        # Fetch
        stmt = (
            select(InboxItem)
            .where(where)
            .order_by(InboxItem.created_at.desc())
            .offset(offset)
            .limit(limit)
        )
        items = (await self.db.execute(stmt)).scalars().all()

        return {
            "items": [self._item_to_dict(i) for i in items],
            "total": total,
        }

    async def get_item(self, item_id: str) -> InboxItem | None:
        """Get an inbox item by ID."""
        result = await self.db.execute(select(InboxItem).where(InboxItem.id == item_id))
        return result.scalar_one_or_none()

    async def expire_stale(self) -> int:
        """Mark expired items as EXPIRED. Returns count expired."""
        now = datetime.now(UTC)
        stmt = select(InboxItem).where(
            InboxItem.status == InboxItemStatus.PENDING.value,
            InboxItem.expires_at.isnot(None),
            InboxItem.expires_at < now,
        )
        items = (await self.db.execute(stmt)).scalars().all()
        for item in items:
            item.status = InboxItemStatus.EXPIRED.value
            item.resolved_at = now
        if items:
            await self.db.flush()
            logger.info("Expired %d stale inbox items", len(items))
        return len(items)

    async def count_pending(self, user_id: int, workspace_id: str | None = None) -> int:
        """Count pending inbox items for a user."""
        conditions = [
            InboxItem.user_id == user_id,
            InboxItem.status == InboxItemStatus.PENDING.value,
        ]
        if workspace_id:
            conditions.append(InboxItem.workspace_id == workspace_id)
        stmt = select(func.count()).select_from(InboxItem).where(and_(*conditions))
        return (await self.db.execute(stmt)).scalar() or 0

    async def _push_inbox_event(
        self, user_id: int, event: str, item: InboxItem
    ) -> None:
        """Push inbox event to user's SSE channel via Redis pub/sub."""
        try:
            from app.services.sse_service import publish_user_notification

            await publish_user_notification(
                user_id,
                {
                    "event": event,
                    "data": self._item_to_dict(item),
                },
            )
        except Exception as e:
            logger.debug("Failed to push inbox SSE event: %s", e)

    @staticmethod
    def _item_to_dict(item: InboxItem) -> dict[str, Any]:
        """Convert an InboxItem to a JSON-serializable dict."""
        return {
            "id": item.id,
            "workspace_id": item.workspace_id,
            "user_id": item.user_id,
            "mission_id": item.mission_id,
            "run_id": item.run_id,
            "task_id": item.task_id,
            "node_id": item.node_id,
            "interrupt_type": item.interrupt_type,
            "title": item.title,
            "description": item.description,
            "proposed_action": item.proposed_action,
            "context": item.context,
            "status": item.status,
            "resolved_at": item.resolved_at.isoformat() if item.resolved_at else None,
            "resolved_by": item.resolved_by,
            "resolution_payload": item.resolution_payload,
            "resolution_note": item.resolution_note,
            "expires_at": item.expires_at.isoformat() if item.expires_at else None,
            "created_at": item.created_at.isoformat() if item.created_at else None,
            "updated_at": item.updated_at.isoformat() if item.updated_at else None,
        }
