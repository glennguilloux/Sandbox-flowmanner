"""MetaStrategy — recursive plan-execute-observe loop (H5.1).

Replaces: nexus/meta_loop_orchestrator.py (225 lines → ~100 lines of strategy code).

A workflow containing SUB_WORKFLOW nodes.  Recursive execution with
failure analysis and depth clamping via CapabilityLattice.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any
from uuid import uuid4

from app.services.substrate.strategies.base import ExecutionStrategy
from app.services.substrate.workflow_models import (
    NodeType,
    StrategyResult,
    Workflow,
    WorkflowType,
)

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from app.services.substrate.executor import UnifiedExecutor

logger = logging.getLogger(__name__)


class MetaStrategy(ExecutionStrategy):
    """Recursive meta-execution with failure analysis and depth clamping."""

    def can_handle(self, workflow_type: WorkflowType) -> bool:
        return workflow_type == WorkflowType.META

    async def validate(self, workflow: Workflow) -> list[str]:
        errors: list[str] = []
        sub_count = sum(1 for n in workflow.nodes if n.type == NodeType.SUB_WORKFLOW)

        if sub_count < 1:
            errors.append("Meta workflow requires at least 1 SUB_WORKFLOW node")

        return errors

    async def execute(
        self,
        workflow: Workflow,
        context: dict[str, Any],
        executor: UnifiedExecutor,
        db: AsyncSession,
    ) -> StrategyResult:
        run_id = workflow.metadata.get("substrate_run_id", str(uuid4()))
        max_depth = workflow.budget.max_depth
        goal = context.get("goal", workflow.description or workflow.title)

        return await self._run_cycle(
            goal=goal,
            workflow=workflow,
            executor=executor,
            db=db,
            run_id=run_id,
            max_depth=max_depth,
            current_depth=0,
            context=context,
        )

    async def _run_cycle(
        self,
        goal: str,
        workflow: Workflow,
        executor: UnifiedExecutor,
        db: AsyncSession,
        run_id: str,
        max_depth: int,
        current_depth: int,
        context: dict[str, Any],
    ) -> StrategyResult:
        if current_depth >= max_depth:
            return StrategyResult(
                success=False,
                status="failed",
                error=f"Max recursion depth ({max_depth}) reached",
            )

        completed = []
        total_tokens = 0
        total_cost = 0.0

        for node in workflow.nodes:
            if executor.is_aborted(run_id):
                return StrategyResult(success=False, status="aborted", error="Aborted")

            result = await executor.execute_node(
                db=db,
                node=node,
                context={**context, "goal": goal, "depth": current_depth},
                budget=workflow.budget,
                run_id=run_id,
                workflow=workflow,
            )

            if result.get("success"):
                completed.append(node.id)
                total_tokens += result.get("tokens", 0)
                total_cost += result.get("cost", 0.0)
            else:
                error = result.get("error", "Unknown")
                logger.warning("Meta node %s failed at depth %d: %s", node.id, current_depth, error)

                if current_depth + 1 < max_depth:
                    return await self._run_cycle(
                        goal=f"Retry: {goal}",
                        workflow=workflow,
                        executor=executor,
                        db=db,
                        run_id=run_id,
                        max_depth=max_depth,
                        current_depth=current_depth + 1,
                        context={**context, "previous_error": error},
                    )

                return StrategyResult(
                    success=False,
                    status="failed",
                    error=error,
                    completed_nodes=completed,
                    total_tokens=total_tokens,
                    total_cost_usd=total_cost,
                )

        return StrategyResult(
            success=True,
            status="completed",
            completed_nodes=completed,
            total_tokens=total_tokens,
            total_cost_usd=total_cost,
        )
