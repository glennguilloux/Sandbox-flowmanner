"""
HandoffProtocol — structured subtask delegation with context passing.

Enables an agent to delegate a subtask to another agent with full context,
tracking the handoff chain and routing results back up.

Chunk 5 upgrade: adds typed HandoffPacket methods (delegate_with_packet,
accept_with_packet, complete_with_packet) that carry goal, success_criteria,
budget, HITL state, depth policy, and substrate events.  Old free-form
methods are kept as backward-compat wrappers.
"""

import logging
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.agent import AgentMessage, HandoffRecord
from app.models.handoff_packet_models import HandoffPacket
from app.models.substrate_models import SubstrateEventType
from app.services.agent_registry_service import AgentRegistryService
from app.services.swarm.lease_integration import HandoffLeaseIntegration

logger = logging.getLogger(__name__)


class BudgetExceededError(Exception):
    """Raised when a handoff exceeds its budget."""


class HandoffProtocol:
    """Manages structured subtask delegation from one agent to another."""

    def __init__(
        self,
        db: AsyncSession,
        lease_integration: HandoffLeaseIntegration | None = None,
        event_log: Any | None = None,
    ):
        self.db = db
        self.registry = AgentRegistryService()
        self.lease_integration = lease_integration or HandoffLeaseIntegration(db)
        self._event_log = event_log

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

        # Emit HANDOFF_FAILED substrate event (chunk 5)
        await self._emit_handoff_event(
            run_id=handoff.execution_id or handoff_id,
            event_type=SubstrateEventType.HANDOFF_FAILED,
            payload={"handoff_id": handoff_id, "error": error},
        )

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

    # ── Chunk 5: Typed packet methods ───────────────────────────────

    async def delegate_with_packet(
        self,
        packet: HandoffPacket,
        *,
        execution_id: str | None = None,
    ) -> HandoffRecord:
        """Delegate a typed handoff packet to another agent.

        Validates the packet, persists a HandoffRecord with all typed fields,
        claims a lease for the receiving run, and emits HANDOFF_INITIATED.

        Raises:
            BudgetExceededError: if packet.budget.remaining_usd <= 0
            ValueError: if HITL scoping is violated
        """
        # 1. Budget guard
        if packet.budget.remaining_usd <= 0:
            raise BudgetExceededError(
                f"Handoff {packet.handoff_id} has zero or negative budget"
            )

        # 2. HITL cross-tenant scoping — reject items whose workspace_id
        #    differs from the packet's workspace_id, AND reject items that
        #    have no workspace_id when the packet IS scoped (prevents
        #    unscoped items from leaking into a scoped handoff).
        if packet.hitl_state.pending_items and packet.hitl_state.workspace_id:
            for item in packet.hitl_state.pending_items:
                item_ws = item.get("workspace_id")
                if item_ws is None:
                    raise ValueError(
                        f"HITL item {item.get('id')} has no workspace_id "
                        f"but packet is scoped to "
                        f"{packet.hitl_state.workspace_id}"
                    )
                if item_ws != packet.hitl_state.workspace_id:
                    raise ValueError(
                        f"HITL item {item.get('id')} workspace_id mismatch: "
                        f"packet={packet.hitl_state.workspace_id} "
                        f"item={item_ws}"
                    )

        # 3. Persist HandoffRecord with typed fields
        handoff = HandoffRecord(
            id=packet.handoff_id,
            from_agent_id=packet.from_agent_id,
            from_agent_name=packet.from_agent_name,
            to_agent_id=packet.to_agent_id,
            to_agent_name=packet.to_agent_name,
            task_description=packet.goal,  # backward compat
            context={"packet": packet.model_dump(mode="json")},  # backward compat
            constraints={"success_criteria": packet.success_criteria},  # backward compat
            parent_handoff_id=packet.parent_handoff_id,
            execution_id=execution_id,
            status="pending",
            # Typed fields:
            goal=packet.goal,
            success_criteria=packet.success_criteria,
            retrieved_context_ids=packet.retrieved_context_ids,
            tool_candidates=packet.tool_candidates,
            budget_remaining_usd=packet.budget.remaining_usd,
            hitl_state=packet.hitl_state.model_dump(mode="json"),
            depth_policy_state=(
                packet.depth_policy_state.model_dump(mode="json")
                if packet.depth_policy_state
                else None
            ),
        )
        self.db.add(handoff)

        # 4. Claim lease
        await self.lease_integration.claim_for_handoff(
            packet.handoff_id, packet.to_agent_id
        )

        # 5. Emit HANDOFF_INITIATED event
        await self._emit_handoff_event(
            run_id=execution_id or packet.handoff_id,
            event_type=SubstrateEventType.HANDOFF_INITIATED,
            payload=packet.model_dump(mode="json"),
        )

        await self.db.flush()
        logger.info(
            "Handoff delegated (typed): %s → %s goal=%s",
            packet.from_agent_name,
            packet.to_agent_name,
            packet.goal[:80],
        )
        return handoff

    async def accept_with_packet(self, handoff_id: str) -> HandoffPacket:
        """Accept a pending handoff and return the typed packet.

        The receiver does NOT need to call ``get_chain()`` to know its
        goal, budget, context, tools, or HITL state — everything is in
        the returned packet.
        """
        handoff = await self._get(handoff_id)
        if not handoff:
            raise ValueError(f"Handoff {handoff_id} not found")
        if handoff.status != "pending":
            raise ValueError(
                f"Handoff {handoff_id} is in status "
                f"{handoff.status}, not pending"
            )

        handoff.status = "accepted"
        handoff.started_at = datetime.now(UTC)

        # Renew lease
        await self.lease_integration.renew(handoff_id)

        # Emit HANDOFF_ACCEPTED event
        await self._emit_handoff_event(
            run_id=handoff.execution_id or handoff_id,
            event_type=SubstrateEventType.HANDOFF_ACCEPTED,
            payload={
                "handoff_id": handoff_id,
                "to_agent_id": handoff.to_agent_id,
            },
        )

        await self.db.flush()

        return self._packet_from_record(handoff)

    async def complete_with_packet(
        self,
        handoff_id: str,
        result: str,
        result_metadata: dict[str, Any] | None = None,
        spent_usd: Decimal = Decimal("0"),
    ) -> HandoffRecord:
        """Complete a handoff, recording budget spend and releasing the lease.

        If ``spent_usd`` exceeds the packet's budget remaining, raises
        BudgetExceededError and emits HANDOFF_BUDGET_EXHAUSTED.
        """
        handoff = await self._get(handoff_id)
        if not handoff:
            raise ValueError(f"Handoff {handoff_id} not found")

        budget_remaining = (
            Decimal(str(handoff.budget_remaining_usd))
            if handoff.budget_remaining_usd is not None
            else Decimal("0")
        )

        if spent_usd > budget_remaining:
            handoff.status = "failed"
            handoff.completed_at = datetime.now(UTC)
            handoff.result_metadata = {
                **(result_metadata or {}),
                "error": (
                    f"Budget exhausted: spent ${spent_usd} "
                    f"> remaining ${budget_remaining}"
                ),
            }
            await self.lease_integration.release(handoff_id)
            await self._emit_handoff_event(
                run_id=handoff.execution_id or handoff_id,
                event_type=SubstrateEventType.HANDOFF_BUDGET_EXHAUSTED,
                payload={
                    "handoff_id": handoff_id,
                    "spent_usd": str(spent_usd),
                    "budget_remaining_usd": str(budget_remaining),
                },
            )
            await self.db.flush()
            raise BudgetExceededError(
                f"Handoff {handoff_id} overspent: "
                f"${spent_usd} > ${budget_remaining}"
            )

        handoff.result = result
        handoff.result_metadata = result_metadata
        handoff.status = "completed"
        handoff.completed_at = datetime.now(UTC)
        handoff.budget_remaining_usd = float(budget_remaining - spent_usd)

        await self.lease_integration.release(handoff_id)
        await self._emit_handoff_event(
            run_id=handoff.execution_id or handoff_id,
            event_type=SubstrateEventType.HANDOFF_COMPLETED,
            payload={
                "handoff_id": handoff_id,
                "result": result,
                "spent_usd": str(spent_usd),
                "budget_remaining_usd": str(handoff.budget_remaining_usd),
            },
        )
        await self.db.flush()
        logger.info("Handoff %s completed (typed) by %s", handoff_id, handoff.to_agent_name)
        return handoff

    # ── Chunk 5 helpers ─────────────────────────────────────────────

    async def _emit_handoff_event(
        self,
        run_id: str,
        event_type: str,
        payload: dict[str, Any],
    ) -> None:
        """Emit a substrate event via event_log.append (if available)."""
        if self._event_log is None:
            try:
                from app.services.substrate.event_log import get_event_log

                self._event_log = get_event_log()
            except Exception:
                logger.debug("Event log unavailable — skipping event emission")
                return

        try:
            await self._event_log.append(
                self.db,
                run_id,
                [
                    {
                        "type": event_type,
                        "payload": payload,
                        "actor": "handoff_protocol",
                    }
                ],
            )
        except Exception as exc:
            logger.debug("Handoff event emission skipped: %s", exc)

    def _packet_from_record(self, handoff: HandoffRecord) -> HandoffPacket:
        """Reconstruct a typed HandoffPacket from a persisted HandoffRecord.

        Note: ``initial_usd`` is set to ``budget_remaining_usd`` because the
        HandoffRecord does not store the original initial budget.  Callers
        that need the true initial value should read it from the
        HANDOFF_INITIATED event payload.
        """
        from app.models.handoff_packet_models import (
            HandoffBudget,
            HandoffDepthPolicyState,
            HandoffHITLState,
        )

        budget_val = (
            Decimal(str(handoff.budget_remaining_usd))
            if handoff.budget_remaining_usd is not None
            else Decimal("0")
        )

        hitl_data = handoff.hitl_state if handoff.hitl_state else {}
        hitl_state = HandoffHITLState(**hitl_data) if hitl_data else HandoffHITLState()

        depth_data = handoff.depth_policy_state
        depth_state = HandoffDepthPolicyState(**depth_data) if depth_data else None

        return HandoffPacket(
            handoff_id=handoff.id,
            from_agent_id=handoff.from_agent_id,
            from_agent_name=handoff.from_agent_name,
            to_agent_id=handoff.to_agent_id,
            to_agent_name=handoff.to_agent_name,
            goal=handoff.goal or handoff.task_description,
            success_criteria=handoff.success_criteria or [],
            retrieved_context_ids=handoff.retrieved_context_ids or [],
            tool_candidates=handoff.tool_candidates or [],
            budget=HandoffBudget(
                remaining_usd=budget_val,
                initial_usd=budget_val,
            ),
            hitl_state=hitl_state,
            depth_policy_state=depth_state,
            parent_handoff_id=handoff.parent_handoff_id,
        )
