# ─────────────────────────────────────────────────────────────────────
# SubstrateClient — single coupling point between the chat surface and the
# unified execution substrate (H5.1).  Part of the `chat` package.
#
# Phase 1 (chat → control-plane front door) introduces the idea that a
# chat turn can spawn a real, observable substrate run (solo strategy only,
# per the owner-approved plan).  Every reference to the Builder's workflow
# schema / UnifiedExecutor lives here so the coupling is ONE file, not
# sprinkled across chat_service / streaming / v2/chat.py.
# ─────────────────────────────────────────────────────────────────────
from __future__ import annotations

import json
import logging
from decimal import Decimal
from typing import TYPE_CHECKING, Any
from uuid import uuid4

from app.services.substrate.event_log import EventLog, get_event_log
from app.services.substrate.executor import UnifiedExecutor
from app.services.substrate.workflow_models import (
    EffectClass,
    NodeType,
    ReasoningProfile,
    Workflow,
    WorkflowNode,
    WorkflowType,
)

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator

    from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


class SubstrateClient:
    """Facade wrapping the chat→substrate coupling.

    Exposes the two stable entry points the chat surface needs:

    * ``build_solo_workflow(...)`` — turn a natural-language goal into a
      single-node S0L0 ``Workflow`` (the only production-safe strategy
      per the plan).
    * ``stream_turn(...)`` — drive a solo run and re-emit its
      ``event_log`` as frontend-understood SSE frames
      (``run_started`` → ``agent_step_start``/``agent_step_end``/
      ``tool_result`` → ``run_complete``).  This is the spike pipe:
      ``event_log → SSE → trace-tile``.

    Keeping the substrate imports behind this class means chat code never
    reaches ``UnifiedExecutor`` / ``blueprint_to_workflow`` directly.
    """

    def build_solo_workflow(self, **kwargs: Any) -> Workflow:
        return build_solo_workflow(**kwargs)

    async def stream_turn(
        self,
        db: AsyncSession,
        *,
        goal: str,
        run_id: str,
        model: str | None = None,
        user_id: str | None = None,
        workspace_id: str | None = None,
    ) -> AsyncGenerator[str, None]:
        async for frame in run_substrate_turn_sse(
            db,
            goal=goal,
            run_id=run_id,
            model=model,
            user_id=user_id,
            workspace_id=workspace_id,
        ):
            yield frame

    async def execute_solo(
        self,
        db: AsyncSession,
        *,
        goal: str,
        run_id: str,
        model: str | None = None,
        user_id: str | None = None,
        workspace_id: str | None = None,
    ) -> dict[str, Any]:
        return await execute_solo_run(
            db,
            goal=goal,
            run_id=run_id,
            model=model,
            user_id=user_id,
            workspace_id=workspace_id,
        )


__all__ = [
    "SubstrateClient",
    "build_solo_workflow",
    "execute_solo_run",
    "new_run_id",
    "run_substrate_turn_sse",
]


def build_solo_workflow(
    *,
    goal: str,
    run_id: str,
    model: str | None = None,
    user_id: str | None = None,
    workspace_id: str | None = None,
    budget: dict[str, Any] | None = None,
) -> Workflow:
    """Build a single-node S0L0 Workflow from a natural-language goal.

    The solo strategy enforces exactly-one-node / no-edges, so this is the
    smallest valid substrate job: one LLM_CALL node carrying the user's goal
    as its prompt.  Tool calls are permitted inside the node (the node
    executor opens the capability-bounded tool loop), which is what makes a
    solo run able to render ≥1 real tool call in-thread.
    """
    node = WorkflowNode(
        id="goal",
        type=NodeType.LLM_CALL,
        title="Goal",
        description=goal,
        config={
            "prompt": goal,
            "system_prompt": (
                "You are Flowmanner's agent. Solve the user's goal by "
                "reasoning and, when useful, calling tools. Be concise."
            ),
            "model": model or "llamacpp/qwen-3.6-27b",
            # Read-only node — must be explicitly reversible so the
            # two-phase STAGE→CONFIRM side-effect gate does not block it.
            "effect_class": EffectClass.REVERSIBLE.value,
        },
        assigned_model=model,
        reasoning_profile=ReasoningProfile.NORMAL,
        effect_class=EffectClass.REVERSIBLE,
    )
    b = budget or {}
    return Workflow(
        id=run_id,
        type=WorkflowType.SOLO,
        title="Chat run",
        description=goal,
        nodes=[node],
        user_id=user_id,
        workspace_id=workspace_id,
        budget=_coerce_budget(b),
    )


def _coerce_budget(b: dict[str, Any]) -> Any:
    from app.models.capability_models import Budget

    return Budget(
        max_cost_usd=Decimal(str(b.get("max_cost_usd", "2.00"))),
        max_wall_time_seconds=b.get("max_wall_time_seconds", 300),
        max_iterations=b.get("max_iterations", 50),
        max_depth=b.get("max_depth", 5),
    )


async def execute_solo_run(
    db: AsyncSession,
    *,
    goal: str,
    run_id: str,
    model: str | None = None,
    user_id: str | None = None,
    workspace_id: str | None = None,
) -> dict[str, Any]:
    """Build + dispatch a solo substrate run, returning the StrategyResult dict.

    Thin facade over ``UnifiedExecutor.execute``.  Callers that want to
    stream the run's event_log as SSE should use ``run_substrate_turn_sse``
    instead, which drives this and re-emits events live.
    """
    workflow = build_solo_workflow(
        goal=goal,
        run_id=run_id,
        model=model,
        user_id=user_id,
        workspace_id=workspace_id,
    )
    executor = UnifiedExecutor()
    result = await executor.execute(db, workflow, run_id=run_id)
    return result.model_dump() if hasattr(result, "model_dump") else dict(result)


# ── SSE re-emission of substrate event_log frames ──────────────────
#
# The frontend's useStreaming parser already understands agent_step_start /
# agent_step_end / tool_result (and AgentTraceTile renders the resulting
# message.steps inline).  The substrate, by contrast, emits its own
# vocabulary (task.started, task.completed, tool.call, tool.response, ...).
# This generator maps substrate frames → the frontend's trace vocabulary so
# a real solo run becomes a legible, in-thread, step-by-step trace with
# no new transport or new client parser.


def _map_substrate_event_to_sse(ev: Any) -> dict[str, Any] | None:
    """Map one substrate event to a frontend-understood SSE payload.

    Returns ``None`` for event types we deliberately do not surface in the
    chat trace (keepalive / lease / circuit-breaker noise).
    """
    etype = ev.type if hasattr(ev, "type") else ev.get("type")
    payload = ev.payload if hasattr(ev, "payload") else ev.get("payload") or {}
    seq = ev.sequence if hasattr(ev, "sequence") else ev.get("sequence")

    if etype in ("task.started", "mission.started", "run.started"):
        node = payload.get("node_id") or payload.get("task_id") or "goal"
        return {
            "type": "agent_step_start",
            "step_id": f"run:{seq}",
            "step_type": "tool",
            "name": payload.get("title") or node,
            "display_name": payload.get("title") or node,
            "agent_name": payload.get("agent_name") or "agent",
            "status": "running",
            "substrate_seq": seq,
        }
    if etype in ("task.completed", "mission.completed", "run.completed"):
        node = payload.get("node_id") or payload.get("task_id") or "goal"
        return {
            "type": "agent_step_end",
            "step_id": f"run:{seq}",
            "status": "success",
            "substrate_seq": seq,
        }
    if etype in ("task.failed", "mission.failed", "run.failed"):
        node = payload.get("node_id") or payload.get("task_id") or "goal"
        return {
            "type": "agent_step_end",
            "step_id": f"run:{seq}",
            "status": "error",
            "substrate_seq": seq,
        }
    if etype == "tool.call":
        return {
            "type": "tool_result",
            "tool": payload.get("tool") or payload.get("name") or "tool",
            "call_id": payload.get("call_id") or f"call:{seq}",
            "status": "running",
            "substrate_seq": seq,
        }
    if etype == "tool.response":
        return {
            "type": "tool_result",
            "tool": payload.get("tool") or payload.get("name") or "tool",
            "call_id": payload.get("call_id") or payload.get("parent_call_id") or f"call:{seq}",
            "status": "done",
            "result": payload.get("result") or payload.get("output"),
            "substrate_seq": seq,
        }
    if etype == "llm.response":
        # Surface the model's synthesized reasoning as an inline step block.
        content = payload.get("content") or payload.get("text")
        if content:
            return {
                "type": "agent_step_end",
                "step_id": f"run:{seq}",
                "status": "success",
                "substrate_seq": seq,
            }
    # Everything else (budget, circuit-breaker, lease, checkpoints): skip.
    return None


async def run_substrate_turn_sse(
    db: AsyncSession,
    *,
    goal: str,
    run_id: str,
    model: str | None = None,
    user_id: str | None = None,
    workspace_id: str | None = None,
) -> AsyncGenerator[str, None]:
    """Drive a solo substrate run and re-emit its event_log as SSE frames.

    This is the SPIKE pipe: ``event_log → SSE → trace-tile``.  It emits
    ``run_started`` once, then replays the accumulated event log as
    frontend-typed events (agent_step_start / agent_step_end / tool_result),
    then a final ``run_complete`` frame.  If the run fails before any
    event is logged, it still emits a clean error frame so the client
    terminates normally.
    """
    event_log: EventLog = get_event_log()
    yield json.dumps({"type": "run_started", "run_id": run_id})

    error_payload: dict[str, Any] | None = None
    try:
        result = await execute_solo_run(
            db,
            goal=goal,
            run_id=run_id,
            model=model,
            user_id=user_id,
            workspace_id=workspace_id,
        )
        if not result.get("success", True):
            error_payload = {
                "type": "error",
                "error": result.get("error") or "Run failed",
            }
    except Exception as exc:
        logger.exception("run_substrate_turn_sse: solo run failed for %s", run_id)
        error_payload = {"type": "error", "error": str(exc)}

    # Replay the event log as typed events (the core of the spike).
    events = await event_log.get_events(db, run_id)
    emitted = 0
    for ev in events:
        sse = _map_substrate_event_to_sse(ev)
        if sse is not None:
            yield json.dumps(sse)
            emitted += 1

    if error_payload is not None:
        yield json.dumps(error_payload)

    yield json.dumps(
        {
            "type": "run_complete",
            "run_id": run_id,
            "events_emitted": emitted,
            "ok": error_payload is None,
        }
    )


def new_run_id() -> str:
    """Allocate a fresh run id for a chat-spawned substrate run."""
    return str(uuid4())
