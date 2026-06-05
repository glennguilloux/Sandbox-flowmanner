"""LLM execution for mission tasks — extracted from MissionExecutor.

Handles LLM-based task execution including agent system prompt resolution,
message building, cost recording, and error classification.

Usage::

    executor = LlmExecutor(cost_tracker=CostTracker(),
                           get_model_router=lambda: router)
    result = await executor.execute_llm(task, {"prompt": "Hello"}, mission, db)
"""

import logging
import time
from typing import Any

from sqlalchemy import select

from app.database import AsyncSessionLocal
from app.models.agent import AgentTemplate
from app.services.mission_errors import PermanentMissionError, RetryableMissionError

logger = logging.getLogger(__name__)


class LlmExecutor:
    """Executes LLM-based tasks within mission workflows.

    Args:
        cost_tracker: :class:`CostTracker` instance for recording LLM calls.
        get_model_router: Callable that returns a ``ModelRouter`` (or
            ``None``).  Called lazily each time an LLM call is made to avoid
            stale references.

    Example:
        >>> executor = LlmExecutor(
        ...     cost_tracker=CostTracker(),
        ...     get_model_router=lambda: get_app_state().model_router,
        ... )
        >>> result = await executor.execute_llm(
        ...     task, {"prompt": "Explain threads"}, mission=mission, db=db
        ... )
    """

    def __init__(self, cost_tracker=None, get_model_router=None):
        self.cost_tracker = cost_tracker
        self._get_model_router = get_model_router or (lambda: None)

    async def execute_llm(
        self, task, input_data: dict[str, Any], mission=None, db=None
    ) -> dict[str, Any]:
        """Execute an LLM task and record observability data.

        Builds messages (system prompt from assigned agent + user prompt),
        routes through the model router, records cost/latency, and returns a
        normalized result dict.

        Args:
            task: Task-like object with ``.description``, ``.title``,
                ``.assigned_model``, ``.assigned_agent_id``, and ``.id``.
            input_data: Dict which may contain a ``"prompt"`` key.  Falls
                back to ``task.description`` or ``task.title``.
            mission: Optional mission object with ``.id`` and ``.user_id``
                for attribution.
            db: Optional SQLAlchemy session for cost recording.

        Returns:
            Dict:
                - ``success`` (bool)
                - ``output`` (dict with ``text``, optional) — on success
                - ``error`` (str) — on failure
                - ``tokens`` (int) — total tokens consumed
                - ``permanent`` (bool, optional) — ``True`` for
                  non-retryable errors

        Raises:
            RetryableMissionError: Re-raised from the model router for
                transient failures the caller should retry.
        """
        model_router = self._get_model_router()

        if not model_router:
            return {"success": False, "error": "ModelRouter not available"}

        prompt = input_data.get("prompt", task.description or task.title)

        messages = await self._build_llm_messages(task, prompt)

        user_id = str(mission.user_id) if mission and mission.user_id else "system"
        model_id = task.assigned_model or "unknown"
        start_time = time.monotonic()

        try:
            response = await model_router.route_request(
                messages=messages,
                user_id=user_id,
                db_session=db,
                is_admin=False,
                model_preference=task.assigned_model or None,
            )

            latency_ms = int((time.monotonic() - start_time) * 1000)
            cost_info = response.get("cost", {})
            prompt_tokens = cost_info.get("input_tokens", 0)
            completion_tokens = cost_info.get("output_tokens", 0)

            # Record LLM call for observability
            if self.cost_tracker:
                await self.cost_tracker.record_llm_call(
                    db=db,
                    mission_id=str(mission.id) if mission else None,
                    task_id=str(task.id) if task and hasattr(task, "id") else None,
                    model_id=response.get("model", model_id),
                    provider=response.get("provider", "unknown"),
                    prompt_tokens=prompt_tokens,
                    completion_tokens=completion_tokens,
                    cost_usd=self.cost_tracker.estimate_cost(
                        model_id, prompt_tokens + completion_tokens
                    ),
                    latency_ms=latency_ms,
                    success=response.get("success", False),
                    error_message=response.get("error") if not response.get("success") else None,
                )

            if not response.get("success"):
                return {
                    "success": False,
                    "error": response.get("error", "LLM call failed"),
                    "tokens": 0,
                }

            content = response.get("response", "")
            tokens = prompt_tokens + completion_tokens

            if not content or content.strip() == "":
                return {
                    "success": False,
                    "error": "LLM returned empty response",
                    "output": {"text": ""},
                    "tokens": tokens,
                }

            return {"success": True, "output": {"text": content}, "tokens": tokens}
        except RetryableMissionError as e:
            logger.warning(f"Retryable LLM error in task {task.id}: {e}")
            raise
        except PermanentMissionError as e:
            logger.error(f"Permanent LLM error in task {task.id}: {e}")
            return {"success": False, "error": str(e), "permanent": True}
        except Exception as e:
            latency_ms = int((time.monotonic() - start_time) * 1000)
            if self.cost_tracker:
                await self.cost_tracker.record_llm_call(
                    db=db,
                    mission_id=str(mission.id) if mission else None,
                    task_id=str(task.id) if task and hasattr(task, "id") else None,
                    model_id=model_id,
                    provider="unknown",
                    prompt_tokens=0,
                    completion_tokens=0,
                    cost_usd=0.0,
                    latency_ms=latency_ms,
                    success=False,
                    error_message=str(e),
                )
            return {"success": False, "error": f"LLM call failed: {e!s}"}

    async def _build_llm_messages(self, task, prompt: str) -> list[dict[str, Any]]:
        """Build the messages array for an LLM call.

        If the task has an assigned agent, the agent's system prompt is
        resolved and prepended as a ``system`` role message.

        Args:
            task: Task-like object with ``.assigned_agent_id`` and ``.id``.
            prompt: User-facing prompt text.

        Returns:
            List of role/content dicts, e.g.
            ``[{"role": "system", "content": "..."}, {"role": "user", ...}]``.
        """
        messages: list[dict[str, Any]] = []

        system_prompt = await self._resolve_agent_system_prompt(task)
        if system_prompt:
            logger.info(
                f"Agent system prompt injected for task {task.id}: {len(system_prompt)} chars"
            )
            messages.append({"role": "system", "content": system_prompt})

        messages.append({"role": "user", "content": prompt})
        return messages

    async def _resolve_agent_system_prompt(self, task) -> str | None:
        """Resolve the system prompt from an assigned agent template.

        Queries the ``AgentTemplate`` table first by ``template_id``, then
        falls back to a JSONB slug match.  Returns ``None`` if no template
        matches or lookup fails.

        Args:
            task: Task-like object with ``.assigned_agent_id``.

        Returns:
            System prompt string, or ``None``.
        """
        if not task.assigned_agent_id:
            return None

        try:
            async with AsyncSessionLocal() as db:
                result = await db.execute(
                    select(AgentTemplate).where(
                        AgentTemplate.template_id == str(task.assigned_agent_id)
                    )
                )
                template = result.scalars().first()
                if template and template.system_prompt:
                    return template.system_prompt

                result = await db.execute(
                    select(AgentTemplate).where(
                        AgentTemplate.model_config["slug"].astext
                        == str(task.assigned_agent_id)
                    )
                )
                template = result.scalars().first()
                if template and template.system_prompt:
                    return template.system_prompt
        except Exception as e:
            logger.warning(
                f"Failed to resolve agent system prompt for task {task.id}: {e}"
            )

        return None
