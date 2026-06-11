"""
HandoffProtocol — structured subtask delegation with context passing.

Enables an agent to delegate a subtask to another agent with full context,
tracking the handoff chain and routing results back up.
"""

import logging
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.agent import AgentMessage, HandoffRecord
from app.services.agent_registry_service import AgentRegistryService

logger = logging.getLogger(__name__)


class HandoffProtocol:
    """Manages structured subtask delegation from one agent to another."""

    def __init__(self, db: AsyncSession):
        self.db = db
        self.registry = AgentRegistryService()

    async def delegate(
        self,
        from_agent_id: str,
        from_agent_name: str,
        task_description: str,
        task_type: str = "general",
        to_agent_id: str | None = None,
        context: dict[str, Any] | None = None,
        constraints: dict[str, Any] | None = None,
        priority: int = 0,
        parent_handoff_id: str | None = None,
        execution_id: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> HandoffRecord:
        """Delegate a task to another agent (auto-matched if no target specified)."""
        # Auto-match if no recipient specified
        if to_agent_id is None:
            match = await self.registry.match(
                self.db,
                task_description=task_description,
                task_type=task_type,
            )
            if match:
                to_agent_id = match["agent_id"]
                to_agent_name = match["name"]
            else:
                raise ValueError(f"No agent found for task: {task_description[:100]}")
        else:
            # Look up name
            cap = await self.registry.get_capability(self.db, to_agent_id)
            to_agent_name = cap.name if cap else to_agent_id

        # Create handoff record
        handoff = HandoffRecord(
            from_agent_id=from_agent_id,
            from_agent_name=from_agent_name,
            to_agent_id=to_agent_id,
            to_agent_name=to_agent_name,
            task_description=task_description,
            task_type=task_type,
            context=context,
            constraints=constraints,
            priority=priority,
            parent_handoff_id=parent_handoff_id,
            execution_id=execution_id,
            status="pending",
            metadata_=metadata,
        )
        self.db.add(handoff)

        # Create inter-agent message
        message = AgentMessage(
            sender_id=from_agent_id,
            sender_name=from_agent_name,
            recipient_id=to_agent_id,
            recipient_name=to_agent_name,
            type="handoff",
            sub_type="delegate",
            payload={
                "task_description": task_description,
                "task_type": task_type,
                "context": context,
                "constraints": constraints,
                "handoff_id": handoff.id,
            },
            priority=priority,
            correlation_id=handoff.id,
            execution_id=execution_id,
            metadata_=metadata,
        )
        self.db.add(message)

        await self.db.flush()
        logger.info(
            "Handoff created: %s → %s: %s",
            from_agent_name,
            to_agent_name,
            task_description[:80],
        )
        return handoff

    async def accept(self, handoff_id: str) -> HandoffRecord | None:
        """Accept a pending handoff."""
        handoff = await self._get(handoff_id)
        if not handoff:
            return None

        handoff.status = "accepted"
        handoff.started_at = datetime.now(UTC)

        # Notify sender
        msg = AgentMessage(
            sender_id=handoff.to_agent_id,
            sender_name=handoff.to_agent_name,
            recipient_id=handoff.from_agent_id,
            recipient_name=handoff.from_agent_name,
            type="handoff",
            sub_type="accepted",
            payload={"handoff_id": handoff_id},
            priority=handoff.priority,
            correlation_id=handoff_id,
            execution_id=handoff.execution_id,
        )
        self.db.add(msg)
        await self.db.flush()
        return handoff

    async def complete(
        self,
        handoff_id: str,
        result: str,
        result_metadata: dict[str, Any] | None = None,
    ) -> HandoffRecord | None:
        """Complete a handoff with results."""
        handoff = await self._get(handoff_id)
        if not handoff:
            return None

        handoff.result = result
        handoff.result_metadata = result_metadata
        handoff.status = "completed"
        handoff.completed_at = datetime.now(UTC)

        # Send result back to delegator
        msg = AgentMessage(
            sender_id=handoff.to_agent_id,
            sender_name=handoff.to_agent_name,
            recipient_id=handoff.from_agent_id,
            recipient_name=handoff.from_agent_name,
            type="handoff",
            sub_type="complete",
            payload={
                "handoff_id": handoff_id,
                "result": result,
                "result_metadata": result_metadata,
            },
            priority=handoff.priority,
            correlation_id=handoff_id,
            execution_id=handoff.execution_id,
        )
        self.db.add(msg)
        await self.db.flush()
        logger.info("Handoff %s completed by %s", handoff_id, handoff.to_agent_name)
        return handoff

    async def reject(
        self,
        handoff_id: str,
        reason: str = "Agent declined the handoff",
    ) -> HandoffRecord | None:
        """Reject a handoff."""
        handoff = await self._get(handoff_id)
        if not handoff:
            return None

        handoff.status = "rejected"
        handoff.completed_at = datetime.now(UTC)

        msg = AgentMessage(
            sender_id=handoff.to_agent_id,
            sender_name=handoff.to_agent_name,
            recipient_id=handoff.from_agent_id,
            recipient_name=handoff.from_agent_name,
            type="handoff",
            sub_type="rejected",
            payload={"handoff_id": handoff_id, "reason": reason},
            priority=handoff.priority,
            correlation_id=handoff_id,
            execution_id=handoff.execution_id,
        )
        self.db.add(msg)
        await self.db.flush()
        return handoff

    async def fail(
        self,
        handoff_id: str,
        error: str,
    ) -> HandoffRecord | None:
        """Mark handoff as failed."""
        handoff = await self._get(handoff_id)
        if not handoff:
            return None

        handoff.status = "failed"
        handoff.completed_at = datetime.now(UTC)

        msg = AgentMessage(
            sender_id=handoff.to_agent_id,
            sender_name=handoff.to_agent_name,
            recipient_id=handoff.from_agent_id,
            recipient_name=handoff.from_agent_name,
            type="handoff",
            sub_type="failed",
            payload={"handoff_id": handoff_id, "error": error},
            priority=1,
            correlation_id=handoff_id,
            execution_id=handoff.execution_id,
        )
        self.db.add(msg)
        await self.db.flush()
        return handoff

    async def get_chain(self, handoff_id: str) -> list[HandoffRecord]:
        """Get the full handoff chain (parent → child → ...)."""
        chain: list[HandoffRecord] = []
        current = await self._get(handoff_id)
        visited: set[str] = set()

        while current and current.id not in visited:
            chain.append(current)
            visited.add(current.id)
            if current.parent_handoff_id:
                current = await self._get(current.parent_handoff_id)
            else:
                break

        # Reverse so root is first
        chain.reverse()
        return chain

    async def get_messages(self, handoff_id: str) -> list[AgentMessage]:
        """Get all messages for a handoff."""
        result = await self.db.execute(
            select(AgentMessage).where(AgentMessage.correlation_id == handoff_id).order_by(AgentMessage.created_at)
        )
        return list(result.scalars().all())

    async def list_handoffs(
        self,
        agent_id: str | None = None,
        status: str | None = None,
        execution_id: str | None = None,
        limit: int = 20,
    ) -> list[HandoffRecord]:
        """List handoffs, optionally filtered."""
        stmt = select(HandoffRecord).limit(limit)

        if agent_id:
            from sqlalchemy import or_

            stmt = stmt.where(
                or_(
                    HandoffRecord.from_agent_id == agent_id,
                    HandoffRecord.to_agent_id == agent_id,
                )
            )
        if status:
            stmt = stmt.where(HandoffRecord.status == status)
        if execution_id:
            stmt = stmt.where(HandoffRecord.execution_id == execution_id)

        stmt = stmt.order_by(HandoffRecord.created_at.desc())
        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    async def _get(self, handoff_id: str) -> HandoffRecord | None:
        result = await self.db.execute(select(HandoffRecord).where(HandoffRecord.id == handoff_id))
        return result.scalar_one_or_none()
