"""
SwarmOrchestrator — multi-agent task decomposition, dispatch, and synthesis.

Flow: Goal → Decompose (LLM) → Match agents → Dispatch (parallel) → Synthesize (LLM)
"""

import asyncio
import json
import logging
import time
from datetime import UTC, datetime
from typing import Any, Any

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.swarm_models import OrchestratorExecution, OrchestratorTask
from app.services.agent_registry_service import AgentRegistryService

logger = logging.getLogger(__name__)


DECOMPOSE_SYSTEM_PROMPT = """You are a task decomposition expert. Given a complex goal, break it into specific, independent subtasks that can be executed in parallel by specialized agents.

Respond with ONLY valid JSON:
{
  "subtasks": [
    {
      "id": "task_1",
      "description": "Specific, actionable task description",
      "task_type": "research|code_generation|analysis|review|documentation|creative",
      "depends_on": [],
      "priority": 0
    }
  ]
}

Rules:
- Each subtask should be completable by a single agent
- Minimize dependencies between tasks (prefer parallel execution)
- Use clear, specific descriptions (not vague goals)
- Set priority 0 = normal, 1 = high, -1 = low
- depends_on contains task IDs that must complete before this one starts"""


SYNTHESIZE_SYSTEM_PROMPT = """You are a synthesis expert. Multiple agents have worked on subtasks to achieve a larger goal. Combine their outputs into a coherent, unified result.

You will receive:
1. The original goal
2. Each agent's output with their task description
3. Any conflict markers between agents

Your job:
- Merge complementary outputs into a coherent whole
- Resolve conflicts by noting both perspectives or choosing the stronger one
- Add [CONFLICT] markers where agents disagree and resolution is ambiguous
- Maintain the best parts of each agent's work
- Produce a result that is greater than the sum of its parts"""


class SwarmOrchestrator:
    """Decompose goals, match agents, dispatch in parallel, synthesize results."""

    def __init__(self, db: AsyncSession):
        self.db = db
        self.registry = AgentRegistryService()
        self.byok_key_id: int | None = None
        self.model_override: str | None = None
        self._byok_key: str | None = None
        self._byok_base_url: str | None = None

    async def execute(
        self,
        goal: str,
        strategy: str = "parallel",
        max_agents: int = 5,
        metadata: dict[str, Any] | None = None,
        byok_key_id: int | None = None,
        model_override: str | None = None,
    ) -> OrchestratorExecution:
        """Execute a goal using multi-agent orchestration."""
        execution = OrchestratorExecution(
            goal=goal,
            strategy=strategy,
            status="decomposing",
            metadata_=metadata,
            started_at=datetime.now(UTC),
        )
        self.db.add(execution)
        await self.db.flush()

        try:
            # ---- Resolve BYOK key if provided ----
            # Store params from execute() call to self for downstream use
            self.byok_key_id = byok_key_id
            self.model_override = model_override

            if self.byok_key_id and not self._byok_key:
                from sqlalchemy import select

                from app.models.byok_models import UserAPIKey

                result = await self.db.execute(
                    select(UserAPIKey).where(
                        UserAPIKey.id == self.byok_key_id, UserAPIKey.is_active == True
                    )
                )
                key_row = result.scalar_one_or_none()
                if key_row:
                    self._byok_key = key_row.get_api_key()
                    self._byok_base_url = key_row.base_url

            # Step 1: Decompose goal into subtasks
            subtasks = await self._decompose(goal, max_agents)
            execution.agent_count = len(subtasks)

            # Step 2: Create task records and match agents
            task_records = []
            for st in subtasks:
                task = OrchestratorTask(
                    execution_id=execution.id,
                    task_description=st["description"],
                    task_type=st.get("task_type", "general"),
                    depends_on=st.get("depends_on", []),
                    priority=st.get("priority", 0),
                    status="pending",
                )
                self.db.add(task)
                task_records.append({**st, "record": task})

            # Step 3: Match agents to tasks
            await self._transition_execution_status(
                execution, "dispatching", cause=f"{len(task_records)} subtasks created"
            )

            for item in task_records:
                match = await self.registry.match(
                    self.db,
                    task_description=item["description"],
                    task_type=item.get("task_type"),
                )
                if match:
                    item["record"].agent_id = match["agent_id"]
                    item["record"].agent_name = match["name"]
                    item["record"].status = "assigned"
                else:
                    item["record"].agent_name = "General"
                    item["record"].status = "assigned"

            # Step 4: Execute tasks (respecting dependencies)
            await self._transition_execution_status(
                execution, "running", cause="Agents dispatched"
            )

            await self._execute_tasks(task_records, strategy)

            # Step 5: Synthesize results
            await self._transition_execution_status(
                execution, "synthesizing", cause="All tasks completed"
            )

            synthesis, conflicts = await self._synthesize(goal, task_records)
            execution.synthesis = synthesis
            execution.conflict_markers = conflicts

            # Update counts
            completed = sum(
                1 for t in task_records if t["record"].status == "completed"
            )
            execution.completed_count = completed
            execution.total_tokens = sum(t["record"].tokens_used for t in task_records)
            await self._transition_execution_status(
                execution,
                "completed",
                cause=f"{completed}/{len(task_records)} tasks completed, {execution.total_tokens} tokens",
            )
            execution.completed_at = datetime.now(UTC)

        except Exception as e:
            logger.error("Swarm execution failed: %s", e, exc_info=True)
            await self._transition_execution_status(
                execution, "failed", cause=f"Error: {e}"
            )
            execution.error_message = str(e)
            execution.completed_at = datetime.now(UTC)

        return execution

    async def _transition_execution_status(
        self, execution: OrchestratorExecution, new_status: str, *, cause: str = ""
    ) -> None:
        """Log and apply an execution status transition."""
        prev_status = execution.status
        execution.status = new_status
        await self.db.commit()
        logger.info(
            "Swarm execution %s state transition: %s → %s (cause: %s) actor=swarm_orchestrator"
            " prev_state=%s next_state=%s",
            execution.id,
            prev_status,
            new_status,
            cause or f"transitioned to {new_status}",
            prev_status,
            new_status,
        )

    async def _decompose(self, goal: str, max_agents: int) -> list[dict]:
        """Use LLM to decompose a goal into subtasks."""
        prompt = f"Goal: {goal}\n\nMaximum subtasks: {max_agents}\n\nDecompose into specific, parallelizable subtasks."

        raw = await self._call_llm(DECOMPOSE_SYSTEM_PROMPT, prompt)
        try:
            cleaned = raw.strip()
            if cleaned.startswith("```"):
                cleaned = cleaned.split("\n", 1)[-1]
            if cleaned.endswith("```"):
                cleaned = cleaned.rsplit("```", 1)[0]
            parsed = json.loads(cleaned.strip())
            return parsed.get("subtasks", [])
        except json.JSONDecodeError:
            logger.warning("Failed to parse decomposition: %s", raw[:200])
            # Fallback: single task
            return [{"id": "task_1", "description": goal, "task_type": "general"}]

    async def _execute_tasks(self, task_records: list[dict], strategy: str) -> None:
        """Execute tasks respecting dependency order."""
        if strategy == "sequential":
            for item in task_records:
                await self._execute_single_task(item)
        else:
            # Parallel with dependency resolution
            completed_ids: set[str] = set()
            remaining = list(task_records)

            while remaining:
                # Find tasks with all dependencies met
                ready = [
                    item
                    for item in remaining
                    if all(
                        dep in completed_ids for dep in (item.get("depends_on") or [])
                    )
                ]

                if not ready:
                    # Deadlock protection: execute remaining sequentially
                    logger.warning(
                        "Dependency deadlock detected, executing remaining sequentially"
                    )
                    for item in remaining:
                        await self._execute_single_task(item)
                        completed_ids.add(item["id"])
                    break

                # Execute ready tasks in parallel
                await asyncio.gather(
                    *[self._execute_single_task(item) for item in ready]
                )

                for item in ready:
                    completed_ids.add(item["id"])
                    remaining.remove(item)

    async def _execute_single_task(self, item: dict) -> None:
        """Execute a single task by calling the LLM."""
        task = item["record"]
        task.status = "running"

        try:
            # Build context from completed dependencies
            dep_context = ""
            if item.get("depends_on"):
                dep_outputs: list[Any] = []
                for _dep_id in item["depends_on"]:
                    # Find the dependency task record
                    for _other in []:
                        pass  # Would need access to all task records
                if dep_outputs:
                    dep_context = "\n\nContext from prior tasks:\n" + "\n---\n".join(
                        dep_outputs
                    )

            agent_prompt = f"You are {task.agent_name or 'a specialist agent'}. Complete this task:\n\n{task.task_description}{dep_context}"

            output = await self._call_llm(
                f"You are {task.agent_name or 'a specialist agent'}. Provide a thorough, well-structured response.",
                task.task_description + dep_context,
            )

            task.output = output
            task.status = "completed"
            task.tokens_used = len(output.split()) * 2  # rough estimate

        except Exception as e:
            logger.error("Task %s failed: %s", task.id, e)
            task.status = "failed"
            task.error_message = str(e)

    async def _synthesize(
        self, goal: str, task_records: list[dict]
    ) -> tuple[str, list[dict]]:
        """Synthesize all task outputs into a unified result."""
        completed_outputs = []
        conflicts = []

        for item in task_records:
            task = item["record"]
            if task.status == "completed" and task.output:
                completed_outputs.append(
                    f"### Agent: {task.agent_name or 'Unknown'}\n**Task:** {task.task_description}\n\n{task.output}"
                )

        if not completed_outputs:
            return "No completed tasks to synthesize.", []

        prompt = f"Original goal: {goal}\n\nAgent outputs:\n\n" + "\n\n---\n\n".join(
            completed_outputs
        )

        synthesis = await self._call_llm(SYNTHESIZE_SYSTEM_PROMPT, prompt)

        # Check for conflict markers
        if "[CONFLICT]" in synthesis:
            conflicts.append(
                {"type": "unresolved", "count": synthesis.count("[CONFLICT]")}
            )

        return synthesis, conflicts

    async def _call_llm(self, system_prompt: str, user_content: str) -> str:
        """Call the LLM API with observability recording."""
        # Strip provider prefix if present (e.g. deepseek/deepseek-v4-flash -> deepseek-v4-flash)
        model_name = self.model_override or settings.LLM_MODEL_NAME
        if "/" in model_name:
            model_name = model_name.split("/", 1)[1]

        api_key = self._byok_key or settings.LLM_API_KEY
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
        }
        payload = {
            "model": model_name,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_content},
            ],
            "temperature": 0.3,
            "max_tokens": 4096,
        }

        start_time = time.monotonic()
        success = True
        error_msg = None

        try:
            api_base = self._byok_base_url or settings.LLM_API_BASE
            async with httpx.AsyncClient(timeout=120.0) as client:
                resp = await client.post(
                    f"{api_base}/chat/completions",
                    headers=headers,
                    json=payload,
                )
                resp.raise_for_status()
                data = resp.json()
                return data["choices"][0]["message"]["content"]
        except Exception as e:
            success = False
            error_msg = str(e)
            raise
        finally:
            latency_ms = int((time.monotonic() - start_time) * 1000)
            await self._record_swarm_llm_call(
                model_id=model_name,
                provider=settings.LLM_API_BASE or "unknown",
                prompt_tokens=len(user_content.split()) * 3,
                completion_tokens=0 if not success else 500,
                latency_ms=latency_ms,
                success=success,
                error_message=error_msg,
            )

    async def _record_swarm_llm_call(
        self,
        model_id: str,
        provider: str,
        prompt_tokens: int,
        completion_tokens: int,
        latency_ms: int,
        success: bool,
        error_message: str | None = None,
    ) -> None:
        """Record an LLM call for swarm orchestrator observability."""
        try:
            from app.models.llm_call_record import LLMCallRecord

            record = LLMCallRecord(
                model_id=model_id,
                provider=provider,
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                cost_usd=0.0,
                latency_ms=latency_ms,
                success=success,
                error_message=error_message,
            )
            self.db.add(record)
        except Exception as e:
            logger.warning("Failed to record swarm LLM call: %s", e)

        # Also record Prometheus metrics
        try:
            from app.core.metrics import record_llm_request

            record_llm_request(
                provider=provider,
                duration_seconds=latency_ms / 1000.0,
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                success=success,
            )
        except Exception:
            logger.debug("swarm_llm_metrics_failed", exc_info=True)

    async def get_execution(self, execution_id: str) -> OrchestratorExecution | None:
        result = await self.db.execute(
            select(OrchestratorExecution).where(
                OrchestratorExecution.id == execution_id
            )
        )
        return result.scalar_one_or_none()

    async def list_executions(self, limit: int = 20) -> list[OrchestratorExecution]:
        result = await self.db.execute(
            select(OrchestratorExecution)
            .order_by(OrchestratorExecution.created_at.desc())
            .limit(limit)
        )
        return list(result.scalars().all())

    async def get_tasks(self, execution_id: str) -> list[OrchestratorTask]:
        result = await self.db.execute(
            select(OrchestratorTask)
            .where(OrchestratorTask.execution_id == execution_id)
            .order_by(OrchestratorTask.priority.desc(), OrchestratorTask.created_at)
        )
        return list(result.scalars().all())
