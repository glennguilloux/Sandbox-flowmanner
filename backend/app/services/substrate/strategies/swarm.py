"""SwarmStrategy — multi-agent decomposition, dispatch, synthesis (H5.1).

Replaces: swarm/orchestrator.py (331 lines → ~150 lines of strategy code).

Two-phase: decompose (LLM) → dispatch (parallel to agents) → synthesize (LLM).
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import TYPE_CHECKING, Any
from uuid import uuid4

from app.services.substrate.strategies.base import ExecutionStrategy
from app.services.substrate.workflow_models import (
    NodeType,
    StrategyResult,
    Workflow,
    WorkflowNode,
    WorkflowType,
)

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from app.services.substrate.executor import UnifiedExecutor

logger = logging.getLogger(__name__)

DECOMPOSE_PROMPT = """You are a task decomposition expert. Given a complex goal, break it into specific, independent subtasks that can be executed in parallel.

Respond with ONLY valid JSON: {"subtasks": [{"id": "task_1", "description": "...", "task_type": "research|code|analysis|review"}]}"""

SYNTHESIZE_PROMPT = """You are a synthesis expert. Combine multiple agent outputs into a coherent, unified result. Merge complementary outputs, resolve conflicts, produce a result greater than the sum of its parts."""


class SwarmStrategy(ExecutionStrategy):
    """Multi-agent swarm strategy — decompose, dispatch, synthesize."""

    def can_handle(self, workflow_type: WorkflowType) -> bool:
        return workflow_type == WorkflowType.SWARM

    async def validate(self, workflow: Workflow) -> list[str]:
        errors: list[str] = []
        fan_out_count = sum(1 for n in workflow.nodes if n.type == NodeType.FAN_OUT)
        fan_in_count = sum(1 for n in workflow.nodes if n.type == NodeType.FAN_IN)

        if fan_out_count < 1:
            errors.append("Swarm workflow requires at least 1 FAN_OUT node")
        if fan_in_count < 1:
            errors.append("Swarm workflow requires at least 1 FAN_IN node")

        return errors

    async def execute(
        self,
        workflow: Workflow,
        context: dict[str, Any],
        executor: UnifiedExecutor,
        db: AsyncSession,
    ) -> StrategyResult:
        run_id = workflow.metadata.get("substrate_run_id", str(uuid4()))
        goal = context.get("goal", workflow.description or workflow.title)

        # Check abort signal
        if executor.is_aborted(run_id):
            return StrategyResult(success=False, status="aborted", error="Aborted")

        # Phase 1: Decompose goal into subtasks
        subtasks = await self._decompose(goal, executor, workflow, run_id)

        # Phase 2: Dispatch subtasks in parallel
        tasks = []
        for i, st in enumerate(subtasks):
            task_node = WorkflowNode(
                id=f"swarm_task_{i}",
                type=NodeType.LLM_CALL,
                title=st.get("description", f"Task {i}"),
                description=st.get("description", ""),
                config={
                    "prompt": st.get("description", ""),
                    "system_prompt": f"You are {st.get('agent_name', 'a specialist agent')}.",
                },
            )
            tasks.append(
                executor.execute_node(
                    db=db,
                    node=task_node,
                    context=context,
                    budget=workflow.budget,
                    run_id=run_id,
                    workflow=workflow,
                )
            )

        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Phase 3: Synthesize results
        outputs = []
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                err_name = type(result).__name__
                outputs.append(f"[Error] Agent {i}: {err_name}: {result}")
            elif result.get("success"):
                text = result.get("output", {}).get("text", "")
                outputs.append(f"### Agent {i}\n{text}")
            else:
                outputs.append(f"[Failed] Agent {i}: {result.get('error')}")

        if not outputs:
            return StrategyResult(success=False, status="failed", error="No agent outputs")

        prompt = f"Original goal: {goal}\n\nAgent outputs:\n\n" + "\n\n---\n\n".join(outputs)
        synthesis = await executor.call_llm(
            budget=workflow.budget,
            model_id="deepseek-chat",
            messages=[
                {"role": "system", "content": SYNTHESIZE_PROMPT},
                {"role": "user", "content": prompt},
            ],
            user_id=workflow.user_id,
            run_id=run_id,
            mission_id=workflow.id,
        )

        synthesis_text = synthesis.get("response", "") if synthesis.get("success") else ""
        total_tokens = sum(r.get("tokens", 0) for r in results if isinstance(r, dict))

        return StrategyResult(
            success=bool(synthesis.get("success")),
            status="completed" if synthesis.get("success") else "failed",
            data={"synthesis": synthesis_text, "agent_outputs": outputs},
            completed_nodes=[f"swarm_task_{i}" for i in range(len(subtasks))],
            total_tokens=total_tokens,
        )

    async def _decompose(
        self,
        goal: str,
        executor: UnifiedExecutor,
        workflow: Workflow,
        run_id: str,
    ) -> list[dict]:
        """Use LLM to decompose a goal into subtasks."""
        prompt = f"Goal: {goal}\n\nDecompose into specific, parallelizable subtasks."
        response = await executor.call_llm(
            budget=workflow.budget,
            model_id="deepseek-chat",
            messages=[
                {"role": "system", "content": DECOMPOSE_PROMPT},
                {"role": "user", "content": prompt},
            ],
            user_id=workflow.user_id,
            run_id=run_id,
            mission_id=workflow.id,
        )

        if not response.get("success"):
            return [{"id": "task_1", "description": goal, "task_type": "general"}]

        try:
            content = response.get("response", "").strip()
            if content.startswith("```"):
                content = content.split("\n", 1)[-1]
            if content.endswith("```"):
                content = content.rsplit("```", 1)[0]
            parsed = json.loads(content.strip())
            return parsed.get("subtasks", [{"id": "task_1", "description": goal}])
        except json.JSONDecodeError:
            return [{"id": "task_1", "description": goal, "task_type": "general"}]
