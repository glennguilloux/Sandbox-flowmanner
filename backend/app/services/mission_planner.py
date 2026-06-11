"""Mission planning — extracted from MissionExecutor.

Generates execution plans via LLM, creates MissionTask records, and manages
the planning lifecycle (pending → planning → planned).

Usage::

    planner = MissionPlanner(
        cost_tracker=CostTracker(),
        get_model_router=lambda: router,
        log_callback=log_fn,
        transition_callback=transition_fn,
    )
    result = await planner.plan_mission(mission_id)
"""

import json
import logging
import re
import time
from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

import httpx

from app.config import settings
from app.database import AsyncSessionLocal
from app.models.mission_models import (
    Mission,
    MissionStatus,
    MissionTask,
    MissionTaskStatus,
)
from app.services.mission_errors import PermanentMissionError, RetryableMissionError

logger = logging.getLogger(__name__)


class MissionPlanner:
    """Generates and manages mission execution plans.

    Uses an LLM (via ModelRouter, with httpx fallback) to break a mission
    into ordered tasks, creates ``MissionTask`` records, and manages the
    planning lifecycle.

    Args:
        cost_tracker: :class:`CostTracker` for recording LLM calls during
            plan generation.
        get_model_router: Callable returning a ``ModelRouter`` instance
            (or ``None``).  Called lazily to support late binding.
        log_callback: Async callable with signature
            ``(db, mission_id, task_id, level, message, extra_data)``.
        transition_callback: Async callable with signature
            ``(db, mission, new_status, *, cause, error_message, level)``.

    Example:
        >>> planner = MissionPlanner(
        ...     cost_tracker=CostTracker(),
        ...     get_model_router=lambda: get_app_state().model_router,
        ...     log_callback=my_log_fn,
        ...     transition_callback=my_transition_fn,
        ... )
        >>> result = await planner.plan_mission(uuid4())
        >>> assert result["success"] is True
    """

    def __init__(
        self,
        cost_tracker=None,
        get_model_router=None,
        log_callback=None,
        transition_callback=None,
    ):
        self.cost_tracker = cost_tracker
        self._get_model_router = get_model_router or (lambda: None)
        self._log = log_callback or _nop_log
        self._transition_status = transition_callback or _nop_transition

    # ── Public API ─────────────────────────────────────────────────────────

    async def plan_mission(self, mission_id: UUID) -> dict[str, Any]:
        """Plan a mission by generating tasks via LLM.

        Opens a DB session, fetches the mission, generates a task plan,
        and creates ``MissionTask`` records.  If the LLM returns no tasks,
        a single default task is created as fallback.

        Args:
            mission_id: UUID of the mission to plan.

        Returns:
            Dict:
                - ``success`` (bool)
                - ``status`` (str) — ``MissionStatus.PLANNED`` on success
                - ``task_count`` (int) — number of tasks generated
                - ``error`` (str) — on failure
                - ``permanent`` (bool, optional) — ``True`` for
                  non-retryable errors

        Raises:
            RetryableMissionError: Transient planning failure the caller
                should retry.
        """
        async with AsyncSessionLocal() as db:
            try:
                from sqlalchemy import select

                result = await db.execute(select(Mission).where(Mission.id == str(mission_id)))
                mission = result.scalars().first()
                if not mission:
                    logger.error("Mission %s not found", mission_id)
                    return {"success": False, "error": "Mission not found"}

                # Update status to planning
                mission.status = MissionStatus.PLANNING
                await db.commit()
                await self._log(
                    db,
                    mission.id,
                    None,
                    "info",
                    "Starting mission planning",
                    extra_data={
                        "actor": "mission_executor",
                        "prev_state": MissionStatus.PENDING,
                        "next_state": MissionStatus.PLANNING,
                        "cause": "Mission planning initiated",
                    },
                )

                # Check if tasks already exist
                existing = await db.execute(select(MissionTask).where(MissionTask.mission_id == str(mission_id)))
                if existing.scalars().first():
                    await self._log(
                        db,
                        mission.id,
                        None,
                        "info",
                        "Tasks already exist, updating plan only",
                    )
                    await self._transition_status(
                        db,
                        mission,
                        MissionStatus.PLANNED,
                        cause="Tasks exist — plan update only",
                    )
                    return {"success": True, "status": MissionStatus.PLANNED}

                # Build prompt for LLM
                prompt = self._build_plan_prompt(mission)

                # Inject learning context from past similar missions
                try:
                    from app.services.learning_service import get_learning_service

                    learning_svc = get_learning_service()
                    if learning_svc:
                        learning_ctx = await learning_svc.inject_into_planner_context(
                            task_description=f"{mission.title} {mission.description or ''}",
                            mission_type=mission.mission_type,
                        )
                        if learning_ctx and learning_ctx.get("has_historical_data"):
                            prompt += (
                                f"\n\nHistorical context from similar past missions:\n"
                                f"- {learning_ctx.get('context_summary', '')}\n"
                            )
                            if learning_ctx.get("recommended_model"):
                                prompt += f"- Recommended model: {learning_ctx['recommended_model']}\n"
                            if learning_ctx.get("success_patterns"):
                                prompt += "- Success patterns:\n"
                                for sp in learning_ctx["success_patterns"][:3]:
                                    prompt += f"  * {sp}\n"
                            prompt += "Use this historical context to improve your planning.\n"
                            await self._log(
                                db,
                                mission.id,
                                None,
                                "info",
                                "Injected learning context into planner",
                            )
                except Exception as learn_err:
                    logger.debug("Learning context injection skipped: %s", learn_err)

                # Call LLM to generate plan
                plan_tasks = await self._generate_plan(
                    prompt,
                    db=db,
                    user_id=mission.user_id,
                    mission_id=str(mission_id),
                )

                if not plan_tasks:
                    # Fallback: create a single default task
                    plan_tasks = [
                        {
                            "title": f"Execute: {mission.title}",
                            "description": mission.description or "Execute the mission",
                            "task_type": "llm",
                            "dependencies": [],
                        }
                    ]
                    await self._log(
                        db,
                        mission.id,
                        None,
                        "warning",
                        "LLM planning failed, using default task",
                    )

                # Create MissionTask records
                for idx, task_def in enumerate(plan_tasks):
                    task = MissionTask(
                        id=str(uuid4()),
                        mission_id=str(mission_id),
                        title=task_def.get("title", f"Task {idx + 1}"),
                        description=task_def.get("description", ""),
                        task_type=task_def.get("task_type", "llm"),
                        order_index=idx,
                        dependencies=task_def.get("dependencies", []),
                        assigned_model=None,
                        status=MissionTaskStatus.PENDING,
                        retry_count=0,
                        max_retries=settings.MISSION_DEFAULT_MAX_RETRIES,
                    )
                    db.add(task)

                # Update mission with plan and status
                mission.plan = {
                    "tasks": plan_tasks,
                    "generated_at": datetime.now(UTC).isoformat(),
                }
                await self._transition_status(
                    db,
                    mission,
                    MissionStatus.PLANNED,
                    cause=f"{len(plan_tasks)} tasks generated",
                )
                return {
                    "success": True,
                    "status": MissionStatus.PLANNED,
                    "task_count": len(plan_tasks),
                }

            except PermanentMissionError as e:
                logger.error("Planning permanently failed for mission %s: %s", mission_id, e)
                await self._transition_status(
                    db,
                    mission,
                    MissionStatus.FAILED,
                    cause=f"Planning permanently failed: {e}",
                    error_message=f"Planning failed: {e!s}",
                    level="error",
                )
                return {"success": False, "error": str(e), "permanent": True}
            except RetryableMissionError as e:
                logger.warning("Retryable planning failure for mission %s: %s", mission_id, e)
                raise
            except Exception as e:
                logger.error("Planning failed for mission %s: %s", mission_id, e)
                await self._transition_status(
                    db,
                    mission,
                    MissionStatus.FAILED,
                    cause=f"Planning error: {e}",
                    error_message=f"Planning failed: {e!s}",
                    level="error",
                )
                return {"success": False, "error": str(e)}

    # ── Prompt Building ────────────────────────────────────────────────────

    def _build_plan_prompt(self, mission) -> str:
        """Build the LLM prompt for mission planning.

        Constructs a structured prompt from the mission's title, description,
        mission type, and constraints, instructing the LLM to return a JSON
        array of task definitions.

        Args:
            mission: Mission model with ``.title``, ``.description``,
                ``.mission_type``, and ``.constraints``.

        Returns:
            Prompt string.
        """
        constraints_str = json.dumps(mission.constraints or {})
        title = mission.title or "Untitled Mission"
        desc = mission.description or "No description provided"
        mtype = mission.mission_type or "general"
        nl = chr(10)
        parts = [
            "You are a mission planner. Break down this mission into specific, actionable tasks.",
            "",
            f"Mission: {title}",
            f"Description: {desc}",
            f"Mission Type: {mtype}",
            f"Constraints: {constraints_str}",
            "",
            "Return a JSON array of tasks. Each task should have:",
            "- title: short task name",
            "- description: what this task does",
            '- task_type: one of "llm", "tool", "rag", "code", "review"',
            "- dependencies: array of 0-based indices of tasks that must complete before this one",
            "",
            "Return ONLY the JSON array, no other text.",
        ]
        return nl.join(parts)

    # ── LLM Plan Generation ───────────────────────────────────────────────

    async def _generate_plan(
        self,
        prompt: str,
        db=None,
        user_id: int | None = None,
        mission_id: str | None = None,
    ) -> list[dict[str, Any]]:
        """Use LLM to generate a mission plan as a list of task dicts.

        Tries the model router first, then falls back to a raw httpx call
        to the LLM server.  Extracts a JSON array from the response using
        regex and records cost/latency regardless of outcome.

        Args:
            prompt: Planning prompt text.
            db: Optional SQLAlchemy session for cost recording.
            user_id: Optional user ID for model router attribution.
            mission_id: Optional mission UUID string for cost recording.

        Returns:
            List of task definition dicts, or empty list if generation fails.

        Raises:
            RetryableMissionError: Transient LLM failure.
        """
        start_time = time.monotonic()
        model_id = "unknown"
        provider = "unknown"
        success = False
        error_msg = None
        prompt_tokens = 0
        completion_tokens = 0
        content = ""
        try:
            model_router = self._get_model_router()
            if model_router:
                response = await model_router.route_request(
                    messages=[{"role": "user", "content": prompt}],
                    user_id=str(user_id) if user_id else "system",
                    db_session=db,
                    is_admin=True,
                    temperature=settings.MISSION_PLAN_TEMPERATURE,
                    max_tokens=settings.MISSION_PLAN_MAX_TOKENS,
                )

                model_id = response.get("model", "deepseek-chat")
                provider = response.get("provider", "unknown")
                cost_info = response.get("cost", {})
                prompt_tokens = cost_info.get("input_tokens", 0)
                completion_tokens = cost_info.get("output_tokens", 0)

                if not response.get("success"):
                    error_msg = response.get("error", "Model routing failed")
                    logger.error("Plan generation failed: %s", error_msg)
                    raise RuntimeError(f"Plan generation failed: {error_msg}")

                content = response.get("content", "") if isinstance(response, dict) else str(response)
            else:
                llm_url = getattr(settings, "LLM_BASE_URL", "http://localhost:11434")
                llm_key = getattr(settings, "LLM_API_KEY", "")
                llm_model = getattr(settings, "LLM_DEFAULT_MODEL", "qwen3:14b")
                model_id = llm_model
                provider = "llamacpp"

                headers = {"Content-Type": "application/json"}
                if llm_key:
                    headers["Authorization"] = f"Bearer {llm_key}"

                async with httpx.AsyncClient(timeout=settings.MISSION_LLM_REQUEST_TIMEOUT) as client:
                    resp = await client.post(
                        f"{llm_url}/v1/chat/completions",
                        headers=headers,
                        json={
                            "model": llm_model,
                            "messages": [{"role": "user", "content": prompt}],
                            "temperature": settings.MISSION_PLAN_TEMPERATURE,
                            "max_tokens": settings.MISSION_PLAN_MAX_TOKENS,
                        },
                    )
                    data = resp.json()
                    content = data.get("choices", [{}])[0].get("message", {}).get("content", "")
                    prompt_tokens = data.get("usage", {}).get("prompt_tokens", 0)
                    completion_tokens = data.get("usage", {}).get("completion_tokens", 0)

            # Extract JSON array from response
            content = content.strip()
            json_match = re.search(r"\[.*\]", content, re.DOTALL)
            if json_match:
                tasks = json.loads(json_match.group())
                if isinstance(tasks, list) and len(tasks) > 0:
                    success = True
                    return tasks

            error_msg = "Could not parse plan from LLM response"
            logger.warning("%s: %s", error_msg, content[:200])
            return []
        except RetryableMissionError as e:
            error_msg = str(e)
            logger.warning("Retryable LLM plan generation failure: %s", e)
            raise
        except PermanentMissionError as e:
            error_msg = str(e)
            logger.error("Permanent LLM plan generation failure: %s", e)
            return []
        except Exception as e:
            error_msg = str(e)
            logger.error("LLM plan generation failed: %s", e)
            return []
        finally:
            # Always record the LLM call for plan generation observability
            latency_ms = int((time.monotonic() - start_time) * 1000)
            if self.cost_tracker:
                await self.cost_tracker.record_llm_call(
                    db=db,
                    mission_id=mission_id,
                    task_id=None,
                    model_id=model_id,
                    provider=provider,
                    prompt_tokens=prompt_tokens,
                    completion_tokens=completion_tokens,
                    cost_usd=self.cost_tracker.estimate_cost(model_id, prompt_tokens + completion_tokens),
                    latency_ms=latency_ms,
                    success=success,
                    error_message=error_msg,
                )


async def _nop_log(db, mission_id, task_id, level, message, extra_data=None):
    """No-op log callback used when none is provided to MissionPlanner."""
    pass


async def _nop_transition(db, mission, new_status, *, cause="", error_message=None, level="info"):
    """No-op transition callback used when none is provided to MissionPlanner."""
    pass
