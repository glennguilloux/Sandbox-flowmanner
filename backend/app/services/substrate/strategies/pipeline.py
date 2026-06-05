"""PipelineStrategy — 7-phase pipeline execution (H5.1).

Replaces: swarm_pipeline/orchestrator.py (~200 lines → ~120 lines of strategy code).
The 7 phase modules (~1,500 lines) are preserved as strategy helpers.

7 phases: DISPATCH → RESEARCH → DRAFT → DEBATE → CONSENSUS → SYNTHESIS → REVIEW
REVIEW can trigger a retry loop (max 3) back to DEBATE.
Missing phase nodes are caught at validation time, not silently skipped.
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

PHASES = [
    "dispatch",
    "research",
    "draft",
    "debate",
    "consensus",
    "synthesis",
    "review",
]


class PipelineStrategy(ExecutionStrategy):
    """7-phase pipeline strategy with review retry loop."""

    def can_handle(self, workflow_type: WorkflowType) -> bool:
        return workflow_type == WorkflowType.PIPELINE

    async def validate(self, workflow: Workflow) -> list[str]:
        errors: list[str] = []

        if not workflow.nodes:
            errors.append("Pipeline workflow must have at least 1 node")

        for node in workflow.nodes:
            if node.type != NodeType.PHASE_GATE:
                errors.append(
                    f"Pipeline node '{node.id}' must be PHASE_GATE, got {node.type.value}"
                )

        # Validate that all required phases have nodes
        phase_configs = {n.config.get("phase") for n in workflow.nodes}
        for phase in PHASES:
            if phase not in phase_configs:
                errors.append(f"Pipeline missing required phase: '{phase}'")

        return errors

    async def execute(
        self,
        workflow: Workflow,
        context: dict[str, Any],
        executor: UnifiedExecutor,
        db: AsyncSession,
    ) -> StrategyResult:
        run_id = workflow.metadata.get("substrate_run_id", str(uuid4()))

        total_tokens = 0
        total_cost = 0.0
        completed = []
        review_feedback = None
        retry_count = 0

        current_phases = list(PHASES)

        while True:
            for phase in current_phases:
                if executor.is_aborted(run_id):
                    return StrategyResult(
                        success=False,
                        status="aborted",
                        error="Aborted",
                        completed_nodes=completed,
                        total_tokens=total_tokens,
                        total_cost_usd=total_cost,
                    )

                phase_node = next(
                    (n for n in workflow.nodes if n.config.get("phase") == phase), None
                )

                if phase_node is None:
                    # Should not happen — validate() catches this
                    return StrategyResult(
                        success=False,
                        status="failed",
                        error=f"Missing phase node for '{phase}'",
                        completed_nodes=completed,
                        total_tokens=total_tokens,
                        total_cost_usd=total_cost,
                    )

                result = await executor.execute_node(
                    db=db,
                    node=phase_node,
                    context={
                        **context,
                        "phase": phase,
                        "review_feedback": review_feedback,
                    },
                    budget=workflow.budget,
                    run_id=run_id,
                    workflow=workflow,
                )

                if result.get("success"):
                    completed.append(phase_node.id)
                    total_tokens += result.get("tokens", 0)
                    total_cost += result.get("cost", 0.0)
                    await executor.ws_manager.broadcast_phase(
                        run_id, phase, "completed"
                    )
                else:
                    logger.error("Phase %s failed: %s", phase, result.get("error"))
                    return StrategyResult(
                        success=False,
                        status="failed",
                        error=f"Phase {phase} failed: {result.get('error')}",
                        completed_nodes=completed,
                        total_tokens=total_tokens,
                        total_cost_usd=total_cost,
                    )

                if phase == "review":
                    output = result.get("output", {})
                    if isinstance(output, dict) and output.get("verdict") == "PASS":
                        return StrategyResult(
                            success=True,
                            status="completed",
                            data=output,
                            completed_nodes=completed,
                            total_tokens=total_tokens,
                            total_cost_usd=total_cost,
                        )
                    else:
                        retry_count += 1
                        if retry_count > 3:
                            return StrategyResult(
                                success=False,
                                status="failed",
                                error="Max review retries exceeded",
                                completed_nodes=completed,
                                total_tokens=total_tokens,
                                total_cost_usd=total_cost,
                            )
                        review_feedback = (
                            output.get("feedback") if isinstance(output, dict) else None
                        )
                        current_phases = ["debate", "consensus", "synthesis", "review"]
                        break
            else:
                break

        return StrategyResult(
            success=True,
            status="completed",
            completed_nodes=completed,
            total_tokens=total_tokens,
            total_cost_usd=total_cost,
        )
