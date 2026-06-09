"""
EscalationChain — failure escalation with retry and agent routing.

When a task fails:
  Level 0: Retry with same agent (N attempts)
  Level 1: Escalate to specialist agent (better match)
  Level 2: Escalate to human (creates review task)
  Level 3: Dead letter (max retries exceeded, logged for manual review)
"""

import logging
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.agent import AgentMessage, EscalationRecord
from app.services.agent_registry_service import AgentRegistryService

logger = logging.getLogger(__name__)

# Escalation policies
POLICY_DEFAULT = "default"
POLICY_AGGRESSIVE = "aggressive"
POLICY_CONSERVATIVE = "conservative"
POLICY_NEVER_ESCALATE = "never_escalate"

POLICY_CONFIGS = {
    POLICY_DEFAULT: {
        "max_retries_same": 2,
        "max_retries_specialist": 2,
        "max_retries_human": 1,
        "total_max_retries": 5,
    },
    POLICY_AGGRESSIVE: {
        "max_retries_same": 1,
        "max_retries_specialist": 1,
        "max_retries_human": 1,
        "total_max_retries": 3,
    },
    POLICY_CONSERVATIVE: {
        "max_retries_same": 3,
        "max_retries_specialist": 3,
        "max_retries_human": 2,
        "total_max_retries": 8,
    },
    POLICY_NEVER_ESCALATE: {
        "max_retries_same": 3,
        "max_retries_specialist": 0,
        "max_retries_human": 0,
        "total_max_retries": 3,
    },
}


class EscalationChain:
    """Manages failure escalation across agent levels with retry policy."""

    def __init__(self, db: AsyncSession):
        self.db = db
        self.registry = AgentRegistryService()

    async def escalate(
        self,
        task_id: str,
        task_description: str,
        error_message: str,
        current_agent_id: str | None = None,
        current_agent_name: str | None = None,
        policy: str = POLICY_DEFAULT,
        execution_id: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> EscalationRecord:
        """Start or continue an escalation chain for a failed task."""
        policy_config = POLICY_CONFIGS.get(policy, POLICY_CONFIGS[POLICY_DEFAULT])

        # Check if this task already has an active escalation
        existing = await self._get_active(task_id)
        if existing:
            # Continue the chain
            return await self._continue_escalation(
                existing, error_message, policy_config, metadata
            )

        # New escalation
        return await self._start_escalation(
            task_id=task_id,
            task_description=task_description,
            error_message=error_message,
            current_agent_id=current_agent_id,
            current_agent_name=current_agent_name,
            policy_config=policy_config,
            policy_name=policy,
            execution_id=execution_id,
            metadata=metadata,
        )

    async def _start_escalation(
        self,
        task_id: str,
        task_description: str,
        error_message: str,
        current_agent_id: str | None,
        current_agent_name: str | None,
        policy_config: dict,
        policy_name: str,
        execution_id: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> EscalationRecord:
        """Start a new escalation chain."""
        # Determine next level
        if policy_config["max_retries_same"] > 0:
            next_level = 0
            next_agent_id = current_agent_id
            next_agent_name = current_agent_name
            action = "retry"
        elif policy_config["max_retries_specialist"] > 0:
            next_level = 1
            matched = await self._find_specialist(task_description)
            next_agent_id = matched["agent_id"] if matched else None
            next_agent_name = matched["name"] if matched else None
            action = "escalate"
        elif policy_config["max_retries_human"] > 0:
            next_level = 2
            next_agent_id = "human"
            next_agent_name = "Human Reviewer"
            action = "escalate_human"
        else:
            next_level = 3
            next_agent_id = None
            next_agent_name = None
            action = "dead_letter"

        record = EscalationRecord(
            task_id=task_id,
            task_description=task_description,
            level=next_level,
            attempted_agent_id=current_agent_id,
            attempted_agent_name=current_agent_name,
            error_message=error_message,
            escalated_to_agent_id=next_agent_id,
            escalated_to_agent_name=next_agent_name,
            max_retries_per_level=policy_config.get("max_retries_same", 2),
            retries_at_level=0,
            escalation_policy=policy_name,
            status=(
                "retrying"
                if action == "retry"
                else (
                    "escalated"
                    if action == "escalate"
                    else ("dead_letter" if action == "dead_letter" else "active")
                )
            ),
            metadata_=metadata,
        )

        if action == "dead_letter":
            record.resolved = True

        self.db.add(record)

        # Create inter-agent message
        msg = AgentMessage(
            sender_id=current_agent_id or "system",
            sender_name=current_agent_name or "System",
            recipient_id=next_agent_id or "dead-letter",
            recipient_name=next_agent_name or "Dead Letter Queue",
            type="error",
            sub_type=action,
            payload={
                "task_id": task_id,
                "task_description": task_description,
                "error": error_message,
                "level": next_level,
            },
            priority=2,  # critical
            execution_id=execution_id,
            metadata_=metadata,
        )
        self.db.add(msg)
        await self.db.flush()

        logger.info('Escalation started for task %s: level=%s, action=%s', task_id, next_level, action)
        return record

    async def _continue_escalation(
        self,
        existing: EscalationRecord,
        error_message: str,
        policy_config: dict,
        metadata: dict[str, Any] | None = None,
    ) -> EscalationRecord:
        """Continue an existing escalation chain."""
        total_retries = existing.retries_at_level + 1

        if total_retries >= policy_config["total_max_retries"]:
            # Dead letter
            existing.level = 3
            existing.status = "dead_letter"
            existing.resolved = True
            existing.error_message = f"Max retries ({policy_config['total_max_retries']}) exceeded. Last error: {error_message}"
            existing.escalated_to_agent_id = None
            existing.escalated_to_agent_name = None

            msg = AgentMessage(
                sender_id="system",
                sender_name="Escalation System",
                recipient_id="dead-letter",
                recipient_name="Dead Letter Queue",
                type="error",
                sub_type="dead_letter",
                payload={
                    "task_id": existing.task_id,
                    "total_retries": total_retries,
                    "last_error": error_message,
                },
                priority=2,
                metadata_=metadata,
            )
            self.db.add(msg)
            await self.db.flush()
            logger.warning('Task %s moved to dead letter queue', existing.task_id)
            return existing

        # Check if we stay at current level or escalate
        retries_remaining = (
            existing.max_retries_per_level - existing.retries_at_level - 1
        )
        if retries_remaining > 0:
            # Retry at current level
            existing.retries_at_level += 1
            existing.error_message = error_message
            existing.status = "retrying"
        else:
            # Escalate to next level
            existing.level += 1
            existing.retries_at_level = 0
            existing.error_message = error_message

            if existing.level == 1:
                # Escalate to specialist
                matched = await self._find_specialist(existing.task_description)
                existing.escalated_to_agent_id = (
                    matched["agent_id"] if matched else None
                )
                existing.escalated_to_agent_name = matched["name"] if matched else None
                existing.max_retries_per_level = policy_config["max_retries_specialist"]
                existing.status = "escalated"
            elif existing.level == 2:
                # Escalate to human
                existing.escalated_to_agent_id = "human"
                existing.escalated_to_agent_name = "Human Reviewer"
                existing.max_retries_per_level = policy_config["max_retries_human"]
                existing.status = "escalated"
            else:
                # Dead letter
                existing.level = 3
                existing.escalated_to_agent_id = None
                existing.escalated_to_agent_name = None
                existing.resolved = True
                existing.status = "dead_letter"

            # Notify next level agent
            msg = AgentMessage(
                sender_id="system",
                sender_name="Escalation System",
                recipient_id=existing.escalated_to_agent_id or "dead-letter",
                recipient_name=existing.escalated_to_agent_name or "Dead Letter Queue",
                type="error",
                sub_type=f"escalated_level_{existing.level}",
                payload={
                    "task_id": existing.task_id,
                    "task_description": existing.task_description,
                    "error": error_message,
                    "level": existing.level,
                    "previous_agent": existing.attempted_agent_name,
                },
                priority=2,
                metadata_=metadata,
            )
            self.db.add(msg)

        await self.db.flush()
        logger.info('Escalation continued for task %s: level=%s', existing.task_id, existing.level)
        return existing

    async def resolve(
        self,
        escalation_id: str,
        resolution_output: str,
        resolution_agent_id: str | None = None,
    ) -> EscalationRecord | None:
        """Mark an escalation as resolved."""
        record = await self._get(escalation_id)
        if not record:
            return None

        record.resolved = True
        record.resolution_output = resolution_output
        record.resolution_agent_id = resolution_agent_id
        record.status = "resolved"

        msg = AgentMessage(
            sender_id=resolution_agent_id or "system",
            sender_name="Resolution Agent",
            recipient_id="system",
            type="response",
            sub_type="escalation_resolved",
            payload={
                "escalation_id": escalation_id,
                "resolution": resolution_output,
            },
            priority=0,
        )
        self.db.add(msg)
        await self.db.flush()
        return record

    async def _find_specialist(self, task_description: str) -> dict[str, Any] | None:
        """Find a specialist agent for the task."""
        match = await self.registry.match(
            self.db,
            task_description=task_description,
        )
        return match

    async def get_escalation(self, escalation_id: str) -> EscalationRecord | None:
        return await self._get(escalation_id)

    async def list_escalations(
        self,
        resolved: bool | None = None,
        limit: int = 20,
    ) -> list[EscalationRecord]:
        """List escalation records."""
        stmt = select(EscalationRecord).limit(limit)
        if resolved is not None:
            stmt = stmt.where(EscalationRecord.resolved == resolved)
        stmt = stmt.order_by(EscalationRecord.created_at.desc())
        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    async def list_dead_letters(self, limit: int = 20) -> list[EscalationRecord]:
        """List all dead letter escalations."""
        result = await self.db.execute(
            select(EscalationRecord)
            .where(EscalationRecord.status == "dead_letter")
            .order_by(EscalationRecord.created_at.desc())
            .limit(limit)
        )
        return list(result.scalars().all())

    async def _get(self, escalation_id: str) -> EscalationRecord | None:
        result = await self.db.execute(
            select(EscalationRecord).where(EscalationRecord.id == escalation_id)
        )
        return result.scalar_one_or_none()

    async def _get_active(self, task_id: str) -> EscalationRecord | None:
        result = await self.db.execute(
            select(EscalationRecord)
            .where(
                EscalationRecord.task_id == task_id,
                EscalationRecord.resolved == False,
            )
            .order_by(EscalationRecord.created_at.desc())
        )
        return result.scalars().first()
