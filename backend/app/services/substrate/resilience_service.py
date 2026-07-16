"""Resilience service — applies the withResilience helper to a persisted
MissionTemplate and (optionally) persists the wrapped variant.

Thin glue over :mod:`app.services.substrate.resilience`. The utility is
framework-agnostic; this layer owns DB access and the `MissionTemplate`
row lifecycle so the API router stays tiny.

INTEGRATION GAP (do NOT silently assume the subgraph executes):
`create_from_template` copies `default_plan` verbatim into `mission.plan`,
but the substrate runs `mission_to_workflow(mission, tasks)` from
`MissionTask` ORM rows, which are built from `default_tasks` (or the LLM
planner) — NOT from `default_plan["nodes"]`. So the escalation subgraph we
inject here lives in the **plan/canvas layer**: it is what the editor shows
and what gets persisted as the mission's `default_plan`. For it to actually
run under the substrate, the plan→`MissionTask` compiler must emit a task
row for the injected `approval`/`log` node and wire its edges. That bridge
is the next integration step and is intentionally NOT faked here. Until then,
treat `apply_resilience` as a correct, validated *plan transformer*.
"""

from __future__ import annotations

import copy
import uuid
from typing import TYPE_CHECKING, Any

from sqlalchemy import select

from app.models.mission_advanced_models import MissionTemplate
from app.services.substrate.resilience import (
    ResilienceGate,
    apply_resilience,
)

if TYPE_CHECKING:
    from app.database import AsyncSession
    from app.models.user import User


class ResilienceService:
    """Wraps task nodes in an escalation subgraph, persistable as a variant."""

    def __init__(self, db: AsyncSession):
        self._db = db

    async def get_template(self, template_id: str) -> MissionTemplate | None:
        result = await self._db.execute(select(MissionTemplate).where(MissionTemplate.id == template_id))
        return result.scalar_one_or_none()

    def _wrap(
        self,
        template: MissionTemplate,
        gate: ResilienceGate,
        approver_role: str | None,
        approval_timeout: int,
        escalation_policy: str,
    ) -> dict[str, Any]:
        plan = copy.deepcopy(template.default_plan or {})
        return apply_resilience(
            plan,
            gate=gate,
            approver_role=approver_role,
            approval_timeout=approval_timeout,
            escalation_policy=escalation_policy,
        )

    async def preview(
        self,
        template_id: str,
        gate: ResilienceGate = "escalate",
        approver_role: str | None = None,
        approval_timeout: int = 2,
        escalation_policy: str = "escalate",
    ) -> dict[str, Any]:
        """Return the wrapped plan WITHOUT persisting a new template."""
        template = await self.get_template(template_id)
        if template is None:
            return {"found": False}
        wrapped = self._wrap(template, gate, approver_role, approval_timeout, escalation_policy)
        return {
            "found": True,
            "template_id": str(template.id),
            "template_name": template.name,
            "resilience": wrapped.get("resilience"),
            "plan": wrapped,
        }

    async def apply_and_persist(
        self,
        template_id: str,
        user: User,
        gate: ResilienceGate = "escalate",
        approver_role: str | None = None,
        approval_timeout: int = 2,
        escalation_policy: str = "escalate",
    ) -> dict[str, Any]:
        """Apply the gate and persist a new user-owned template variant.

        The variant is ``is_builtin=False`` so it never collides with the
        shipped catalog, and ``is_public=False`` so it does not leak into the
        public gallery unless the caller later publishes it.
        """
        template = await self.get_template(template_id)
        if template is None:
            return {"found": False}
        wrapped = self._wrap(template, gate, approver_role, approval_timeout, escalation_policy)

        gate_label = "resilient" if gate == "pass_through" else f"resilient-{gate}"
        variant = MissionTemplate(
            id=uuid.uuid4(),
            user_id=user.id,
            name=f"{template.name} ({gate_label})",
            description=template.description or "",
            category=template.category,
            icon=template.icon,
            is_public=False,
            is_builtin=False,
            mission_type=template.mission_type,
            priority=template.priority,
            default_plan=wrapped,
            default_constraints=copy.deepcopy(template.default_constraints),
            tags=copy.deepcopy(template.tags) if template.tags else None,
        )
        self._db.add(variant)
        await self._db.commit()
        await self._db.refresh(variant)

        return {
            "found": True,
            "template_id": str(template.id),
            "variant_id": str(variant.id),
            "variant_name": variant.name,
            "resilience": wrapped.get("resilience"),
        }
