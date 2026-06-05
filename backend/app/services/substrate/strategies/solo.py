"""SoloStrategy — single-node workflow execution (H5.1).

Replaces: mission_executor.py (1,387 lines → ~50 lines of strategy code).

A Workflow with one node and no edges.  The node's config contains
the task definition.  Executes directly — no dependency resolution.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any
from uuid import uuid4

from app.services.substrate.strategies.base import ExecutionStrategy
from app.services.substrate.workflow_models import (
    StrategyResult,
    Workflow,
    WorkflowType,
)

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from app.services.substrate.executor import UnifiedExecutor

logger = logging.getLogger(__name__)


class SoloStrategy(ExecutionStrategy):
    """Single-node workflow strategy."""

    def can_handle(self, workflow_type: WorkflowType) -> bool:
        return workflow_type == WorkflowType.SOLO

    async def validate(self, workflow: Workflow) -> list[str]:
        errors: list[str] = []

        if len(workflow.nodes) != 1:
            errors.append("Solo workflow must have exactly 1 node")
        if workflow.edges:
            errors.append("Solo workflow must have no edges")

        return errors

    async def execute(
        self,
        workflow: Workflow,
        context: dict[str, Any],
        executor: UnifiedExecutor,
        db: AsyncSession,
    ) -> StrategyResult:
        node = workflow.nodes[0]
        run_id = workflow.metadata.get("substrate_run_id", str(uuid4()))

        # Check abort signal before execution
        if executor.is_aborted(run_id):
            return StrategyResult(success=False, status="aborted", error="Aborted")

        result = await executor.execute_node(
            db=db,
            node=node,
            context=context,
            budget=workflow.budget,
            run_id=run_id,
            workflow=workflow,
        )

        return StrategyResult(
            success=result.get("success", False),
            status="completed" if result.get("success") else "failed",
            data=result.get("output"),
            error=result.get("error"),
            completed_nodes=[node.id] if result.get("success") else [],
            failed_nodes=[node.id] if not result.get("success") else [],
            total_tokens=result.get("tokens", 0),
            total_cost_usd=result.get("cost", 0.0),
        )
