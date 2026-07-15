"""NodeExecutor — shared execute_node() for all strategies (H5.1).

The single code path for executing a workflow node.  Every strategy
delegates to NodeExecutor for actual node execution.  It handles:

1. Pre-execution budget check
2. Capability token creation for tool nodes
3. Node dispatch to the appropriate handler
4. Fallback strategy execution
5. Event logging (to substrate event log)
6. Retry with budget
7. LLM call recording (via BudgetEnforcer)

All LLM calls go through BudgetEnforcer.call().
All tool calls go through CapabilityEngine.verify().
"""

from __future__ import annotations

import json
import logging
import re
import time
from typing import TYPE_CHECKING, Any

from app.integrations.sandboxd_client import SandboxdClient, get_sandboxd_client
from app.models.capability_models import Action, Budget, BudgetExhausted, ResourceRef
from app.models.substrate_models import SubstrateEvent, SubstrateEventType
from app.services.sandbox_service import SandboxService
from app.services.substrate.context_manager import ContextManager
from app.services.substrate.event_log import _compute_idempotency_key, get_event_log
from app.services.substrate.hitl_pause import HITLPaused
from app.services.substrate.workflow_models import (
    EffectClass,
    NodeType,
    Workflow,
    WorkflowNode,
)

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

# ── Code execution wrapper (written to temp file to avoid quote issues) ──

_WORKSPACE_WRAPPER = """import sys, io, json, math, statistics, datetime, collections
import itertools, functools, operator, re, string, textwrap, hashlib, base64, copy, csv

__builtins__ = {
    'True': True, 'False': False, 'None': None,
    'abs': abs, 'all': all, 'any': any, 'bool': bool,
    'chr': chr, 'dict': dict, 'divmod': divmod,
    'enumerate': enumerate, 'filter': filter, 'float': float, 'format': format,
    'int': int, 'isinstance': isinstance, 'iter': iter,
    'len': len, 'list': list, 'map': map, 'max': max, 'min': min,
    'print': print, 'range': range, 'repr': repr, 'reversed': reversed,
    'round': round, 'set': set, 'slice': slice, 'sorted': sorted,
    'str': str, 'sum': sum, 'tuple': tuple, 'type': type, 'zip': zip,
    'Exception': Exception, 'TypeError': TypeError, 'ValueError': ValueError,
    'KeyError': KeyError, 'IndexError': IndexError,
}

_buf = io.StringIO()
_old = sys.stdout
sys.stdout = _buf
try:
{code}
except Exception as e:
    print(f"ERROR: {{type(e).__name__}}: {{e}}")
finally:
    sys.stdout = _old

_out = _buf.getvalue()
if len(_out) > 1_000_000:
    _out = _out[:1_000_000] + "\\n... (truncated at 1MB)"
print(_out, end='')
"""


# ── Context window constants (Q2-Q3 Chunk 2 Tier 1) ──────────────

# Default number of recent events to inject into agent context.
# Tunable per mission via workflow.metadata["context_window_size"].
_DEFAULT_CONTEXT_WINDOW_SIZE: int = 20

# Event types excluded from the context window — these are infrastructure
# noise that adds tokens without helping the agent reason about its task.
_NOISY_EVENT_TYPES: frozenset[str] = frozenset(
    {
        SubstrateEventType.LEASE_CLAIMED,
        SubstrateEventType.LEASE_RENEWED,
        SubstrateEventType.LEASE_RELEASED,
        SubstrateEventType.CIRCUIT_BREAKER_TRIGGERED,
        SubstrateEventType.CIRCUIT_BREAKER_BROKEN,
        SubstrateEventType.CIRCUIT_BREAKER_RESET,
        SubstrateEventType.CIRCUIT_BREAKER_OPENED,
        SubstrateEventType.PROVIDER_FALLBACK_INVOKED,
        SubstrateEventType.RUN_RESUME_VALIDATED,
        SubstrateEventType.CHECKPOINT,
    }
)


class NodeExecutor:
    """Shared node execution — used by all 7 strategies."""

    def __init__(self, unified_executor):
        """Create a NodeExecutor.

        Args:
            unified_executor: The UnifiedExecutor that provides budget_enforcer,
                              capability_engine, event_log, etc.
        """
        self.executor = unified_executor
        self._sbx_client: SandboxdClient | None = None
        self._sbx_svc: SandboxService | None = None
        # Comment 11: dedicated long-context substrate for Opus deep dives.
        # The manager is created per run so chunk ids / pinned evidence /
        # rolling summaries are scoped to one execution and replayable via the
        # context.plan substrate event it emits.
        self._context_managers: dict[str, ContextManager] = {}

    @property
    def _sandbox_client(self) -> SandboxdClient:
        if self._sbx_client is None:
            self._sbx_client = get_sandboxd_client()
        return self._sbx_client

    @property
    def _sandbox_service(self) -> SandboxService:
        if self._sbx_svc is None:
            self._sbx_svc = SandboxService(self._sandbox_client)
        return self._sbx_svc

    # ── Context window (Q2-Q3 Chunk 2 Tier 1) ──────────────────────

    # ── Comment 11: long-context management ──────────────────────────
    def _context_manager(self, run_id: str) -> ContextManager:
        """Return the per-run :class:`ContextManager` (creating it on demand)."""
        mgr = self._context_managers.get(run_id)
        if mgr is None:
            mgr = ContextManager()
            self._context_managers[run_id] = mgr
        return mgr

    async def _build_context_window(
        self,
        db: AsyncSession,
        run_id: str,
        current_sequence: int,
        context_window_size: int,
    ) -> list[SubstrateEvent]:
        """Fetch the last N raw events for within-mission context.

        Returns causally-ordered, un-redacted events from the event log,
        excluding infrastructure noise (leases, circuit breakers, etc.).

        Args:
            db: Async database session
            run_id: The substrate run ID
            current_sequence: The sequence of the just-emitted task.started event.
                              Events at this sequence are excluded (it's the
                              event we just wrote, not prior context).
            context_window_size: Number of recent events to fetch (N).

        Returns:
            List of SubstrateEvent objects, ordered by sequence ascending.
        """
        event_log = get_event_log()
        from_seq = max(0, current_sequence - context_window_size)
        raw_events = await event_log.get_events(
            db,
            run_id,
            from_sequence=from_seq,
            to_sequence=current_sequence - 1,
            limit=context_window_size,
        )
        # Filter out noisy infrastructure events
        return [e for e in raw_events if e.type not in _NOISY_EVENT_TYPES]

    @classmethod
    def _sanitize_payload(cls, value: Any) -> Any:
        """Recursively sanitize the string values of an untrusted payload.

        Reuses the shared ``_sanitize_text`` helper (the same one
        ``_sanitize_tool_output`` uses) so control chars are stripped and
        each string is length-capped BEFORE JSON serialization — sanitizing
        the already-serialized JSON would be a no-op because ``json.dumps``
        escapes control chars to ``\\uXXXX`` text.
        """
        if isinstance(value, str):
            return cls._sanitize_text(value)
        if isinstance(value, dict):
            return {k: cls._sanitize_payload(v) for k, v in value.items()}
        if isinstance(value, list):
            return [cls._sanitize_payload(v) for v in value]
        return value

    @classmethod
    def _format_context_events(cls, events: list[SubstrateEvent]) -> str:
        """Format context events as structured text for LLM injection.

        Each event is serialized as a compact line with sequence, type,
        actor, and payload summary.  Payloads are truncated to 300 chars
        to avoid blowing up the context window.

        Trust boundary (B3): event payloads carry verbatim tool/agent
        outputs (RAG, web_search, code, file, browser, sandbox).  This is
        the single chokepoint where prior-event output re-enters the LLM
        prompt (see :771).  Every payload's string values are sanitized
        here via the shared ``_sanitize_text`` helper (control-char strip +
        length cap — the same helper ``_sanitize_tool_output`` uses) so
        untrusted output is never injected raw.
        """
        if not events:
            return ""
        lines: list[str] = []
        for ev in events:
            # Sanitize the untrusted payload BEFORE serialization so control
            # chars in tool/agent output are stripped (json.dumps would only
            # escape, not remove, them).
            sanitized = cls._sanitize_payload(ev.payload or {})
            payload_str = json.dumps(sanitized, default=str)
            if len(payload_str) > 300:
                payload_str = payload_str[:300] + "..."
            lines.append(f"[{ev.sequence}] {ev.type} (actor={ev.actor}) {payload_str}")
        return "\n".join(lines)

    async def execute(
        self,
        db: AsyncSession,
        node: WorkflowNode,
        context: dict[str, Any],
        budget: Budget,
        run_id: str,
        workflow: Workflow | None = None,
    ) -> dict[str, Any]:
        """Execute a single node.

        Q1-B chunk 1: Before executing a HITL node (APPROVAL / HUMAN_REVIEW),
        check if this is a resume — if the inbox item was already resolved,
        return the resolution result without re-creating the interrupt.

        Returns:
            Dict with success, output, tokens, cost, etc.
        """
        event_log = get_event_log()
        result: dict[str, Any] = {"success": False, "error": "Unknown error"}

        # Q1-B chunk 1: HITL resume check — if this is a HITL node and the
        # inbox item was already resolved, return the resolution directly.
        if node.type in (NodeType.APPROVAL, NodeType.HUMAN_REVIEW):
            resume_result = await self._check_hitl_resume(db, node, context, run_id)
            if resume_result is not None:
                return resume_result

        # Pre-execution budget check
        is_exhausted, reason = budget.is_exhausted()
        if is_exhausted:
            raise BudgetExhausted(reason, budget)

        start_time = time.monotonic()

        # Max retries
        max_retries = node.max_retries if node.max_retries is not None else 3

        # ── Side-effect safety: resolve classification BEFORE routing. ──
        # (side-effect-safety-and-planner-trust skill)
        # IRREVERSIBLE nodes are committed in two phases so the external
        # effect can never fire before the orchestrator's fallback/skip/esc
        # decision: STAGE commits side_effect_intent (run-scoped key) BEFORE
        # the call; CONFIRM commits side_effect_confirmed (key EXCLUDES run_id
        # so it deduplicates across retries) AFTER the decision; the effect
        # fires only post-CONFIRM.
        effect_class = node.effect_class
        is_irreversible = effect_class == EffectClass.IRREVERSIBLE

        for attempt in range(max_retries + 1):
            # Check abort signal between retries
            if self.executor.is_aborted(run_id):
                logger.info("Abort signal detected for run %s, node %s", run_id, node.id)
                return {"success": False, "error": "Aborted"}

            node.status = "running"

            # Q2-Q3 Chunk 2 Tier 1: Build context window BEFORE emitting
            # task.started so we can record the window range in the event.
            context_window_size = (
                workflow.metadata.get("context_window_size", _DEFAULT_CONTEXT_WINDOW_SIZE)
                if workflow
                else _DEFAULT_CONTEXT_WINDOW_SIZE
            )
            current_seq = await event_log.get_latest_sequence(db, run_id)
            context_events: list[SubstrateEvent] = []
            if current_seq > 0 and context_window_size > 0:
                context_events = await self._build_context_window(db, run_id, current_seq + 1, context_window_size)

            # Record task.started event (includes context window range for replay)
            context_window_meta = {}
            if context_events:
                context_window_meta = {
                    "context_window_from_seq": context_events[0].sequence,
                    "context_window_to_seq": context_events[-1].sequence,
                    "context_window_event_count": len(context_events),
                }

            await event_log.append(
                db,
                run_id,
                [
                    {
                        "type": SubstrateEventType.TASK_STARTED,
                        "payload": {
                            "task_id": node.id,
                            "task_title": node.title,
                            "task_type": node.type.value,
                            "attempt": attempt + 1,
                            **context_window_meta,
                        },
                        "actor": "node_executor",
                        "mission_id": workflow.id if workflow else None,
                        "task_id": node.id,
                    }
                ],
            )

            try:
                # ── Two-phase STAGE→CONFIRM dispatch (side-effect-safety skill) ──
                # For IRREVERSIBLE nodes we must NOT fire the external effect inside
                # _dispatch. Instead: STAGE commits the fully-rendered intent BEFORE
                # the call, then we only CALL the handler AFTER we've decided to GO;
                # CONFIRM is committed (run-excluded key) and only THEN do we consider
                # the effect "fired". This guarantees the orchestrator's
                # fallback/skip/escalate decision sits between STAGE and the fire.
                if is_irreversible:
                    # Comment 3: crash-window guard. Before any external call,
                    # check whether this logical effect was ALREADY confirmed
                    # (the run-excluded key dedupes across retries/parallel
                    # workers). If so, skip the external call and return a
                    # replayed success — no double-fire after a crash between
                    # dispatch and confirmation.
                    event_log = get_event_log()
                    payload = self._render_effect_payload(node, workflow)
                    confirm_key = _compute_idempotency_key(
                        None, SubstrateEventType.SIDE_EFFECT_CONFIRMED, node.id, payload
                    )
                    already_confirmed = await event_log.find_by_idempotency_key(db, confirm_key)
                    if already_confirmed is not None:
                        logger.info(
                            "Skipping irreversible dispatch for node %s: effect already "
                            "confirmed (key %s) — replaying success.",
                            node.id,
                            confirm_key,
                        )
                        return {
                            "success": True,
                            "output": (already_confirmed.payload or {}).get("effect", {}),
                            "tokens": 0,
                            "cost": 0.0,
                            "replayed": True,
                            "replay_reason": "side_effect_already_confirmed",
                        }

                    # Intent exists but was never confirmed (crash window between
                    # STAGE and CONFIRM, or a stalled retry). Do NOT re-fire the
                    # external effect blindly. Escalate to HITL so a human (or an
                    # external idempotency/outbox acknowledgement) breaks the glass.
                    intent_key = _compute_idempotency_key(
                        run_id, SubstrateEventType.SIDE_EFFECT_INTENT, node.id, payload
                    )
                    existing_intent = await event_log.find_by_idempotency_key(db, intent_key)
                    if existing_intent is not None and already_confirmed is None:
                        logger.error(
                            "Irreversible intent staged but not confirmed for node %s "
                            "(key %s). Escalating to HITL instead of re-firing.",
                            node.id,
                            intent_key,
                        )
                        await event_log.append(
                            db,
                            run_id,
                            [
                                {
                                    "type": SubstrateEventType.TASK_FAILED,
                                    "payload": {
                                        "task_id": node.id,
                                        "error": "irreversible effect intent without confirmation",
                                        "reason": "intent_not_confirmed",
                                        "promoted_to": "hitl_escalate",
                                    },
                                    "actor": "node_executor",
                                    "mission_id": workflow.id if workflow else None,
                                    "task_id": node.id,
                                }
                            ],
                        )
                        node.status = "failed"
                        node.error_message = (
                            "Irreversible effect intent staged without confirmation; "
                            "escalated for outbox/idempotency acknowledgement."
                        )
                        return {
                            "success": False,
                            "escalated": True,
                            "requires_acknowledgement": True,
                            "error": node.error_message,
                        }

                    # Forward a stable idempotency key to external tools that
                    # support it (run-scoped, so each attempt has its own key).
                    committed = await self._stage_irreversible_effect(db, run_id, node, workflow)
                    node.config = {**node.config, "idempotency_key": committed}
                    # Orchestrator health / fallback decision happens in the normal
                    # flow below; if the attempt ultimately fails we promote to
                    # ESCALATE (no retry re-fires) — see failure handling.
                    result = await self._dispatch(
                        db,
                        node,
                        context,
                        budget,
                        run_id,
                        workflow,
                        context_events=context_events,
                    )
                    # CONFIRM only after a successful fire.
                    if result.get("success"):
                        await self._confirm_irreversible_effect(db, run_id, node, workflow, committed_key=committed)
                else:
                    result = await self._dispatch(
                        db,
                        node,
                        context,
                        budget,
                        run_id,
                        workflow,
                        context_events=context_events,
                    )
            except BudgetExhausted:
                raise
            except HITLPaused:
                # Q1-B chunk 1: a node (HITL interrupt node OR a tool node whose
                # standing constraint escalated) raised HITLPaused to actually
                # pause the run. Propagate it so UnifiedExecutor._execute_inner
                # can release the lease and emit RUN_PAUSED. This MUST come
                # before the generic Exception handler — HITLPaused is a control
                # signal, not a node failure. (The generic handler previously
                # swallowed it, which silently broke every HITL pause.)
                raise
            except Exception as e:
                logger.exception("Node %s execution error", node.id)
                result = {"success": False, "error": str(e)}

            elapsed_ms = (time.monotonic() - start_time) * 1000

            if result.get("success"):
                # Record task.completed event
                await event_log.append(
                    db,
                    run_id,
                    [
                        {
                            "type": SubstrateEventType.TASK_COMPLETED,
                            "payload": {
                                "task_id": node.id,
                                "task_title": node.title,
                                "tokens": result.get("tokens", 0),
                                "cost_usd": result.get("cost", 0.0),
                                "latency_ms": elapsed_ms,
                            },
                            "actor": "node_executor",
                            "mission_id": workflow.id if workflow else None,
                            "task_id": node.id,
                        }
                    ],
                )

                node.status = "completed"
                node.output_data = result.get("output")
                node.tokens_used = result.get("tokens", 0)
                node.cost = result.get("cost", 0.0)
                return result

            # Failure handling
            # ── Side-effect safety: committed + IRREVERSIBLE ⇒ ESCALATE ──
            # (side-effect-safety-and-planner-trust skill)
            # If we already committed an irreversible effect intent and the node
            # is IRREVERSIBLE, we must NOT retry: a Retryable error would re-fire
            # the external effect (double-send). Promote ANY error — even a
            # RetryableMissionError — to ESCALATE so a human breaks the glass.
            error = result.get("error")
            if is_irreversible and attempt < max_retries:
                logger.error(
                    "Irreversible effect already committed for node %s; NOT retrying "
                    "(would re-fire). Promoting to ESCALATE.",
                    node.id,
                )
                await event_log.append(
                    db,
                    run_id,
                    [
                        {
                            "type": SubstrateEventType.TASK_FAILED,
                            "payload": {
                                "task_id": node.id,
                                "attempt": attempt + 1,
                                "error": error,
                                "reason": "irreversible_effect_committed",
                                "promoted_to": "escalate",
                            },
                            "actor": "node_executor",
                            "mission_id": workflow.id if workflow else None,
                            "task_id": node.id,
                        }
                    ],
                )
                node.status = "failed"
                node.error_message = f"[ESCALATED] irreversible effect already committed: {error}"
                escalated_result = dict(result)
                escalated_result["escalated"] = True
                escalated_result["error"] = node.error_message
                return escalated_result
                # attempt == max_retries path falls through to TASK_FAILED below.

            if attempt < max_retries:
                node.retry_count = attempt + 1
                logger.warning(
                    "Node %s failed (attempt %d/%d): %s",
                    node.id,
                    attempt + 1,
                    max_retries,
                    result.get("error"),
                )
                # Record task.retrying event
                await event_log.append(
                    db,
                    run_id,
                    [
                        {
                            "type": SubstrateEventType.TASK_RETRYING,
                            "payload": {
                                "task_id": node.id,
                                "attempt": attempt + 1,
                                "error": result.get("error"),
                            },
                            "actor": "node_executor",
                            "mission_id": workflow.id if workflow else None,
                            "task_id": node.id,
                        }
                    ],
                )
                continue

            # All retries exhausted
            logger.error("Node %s failed after %d retries", node.id, max_retries)
            await event_log.append(
                db,
                run_id,
                [
                    {
                        "type": SubstrateEventType.TASK_FAILED,
                        "payload": {
                            "task_id": node.id,
                            "task_title": node.title,
                            "error": result.get("error"),
                            "retries_exhausted": True,
                        },
                        "actor": "node_executor",
                        "mission_id": workflow.id if workflow else None,
                        "task_id": node.id,
                    }
                ],
            )

            node.status = "failed"
            node.error_message = result.get("error")
            return result

        return result  # Should not reach here

    # ── Side-effect safety: two-phase STAGE→CONFIRM dispatch ──────────
    # (side-effect-safety-and-planner-trust skill)
    #
    # STAGE  — commit side_effect_intent BEFORE any external call. The key is
    #          run-scoped (includes run_id) so each retry re-commits its own
    #          intent; the payload is the fully-rendered effect descriptor.
    # CONFIRM— commit side_effect_confirmed AFTER the orchestrator's
    #          fallback/skip/escalate decision AND only on a successful fire.
    #          The key EXCLUDES run_id so the same logical effect dedupes across
    #          retries (prevents a double-send when a retry observes the prior
    #          CONFIRM already present).
    async def _stage_irreversible_effect(
        self,
        db: AsyncSession,
        run_id: str,
        node: WorkflowNode,
        workflow: Workflow | None,
    ) -> str:
        """STAGE: commit the fully-rendered effect intent before any external call.

        Returns the run-scoped idempotency key for this intent (used by CONFIRM to
        link the two phases).
        """
        event_log = get_event_log()
        payload = self._render_effect_payload(node, workflow)
        # Run-scoped key → one intent per (run, node, attempt-content).
        idem_key = _compute_idempotency_key(run_id, SubstrateEventType.SIDE_EFFECT_INTENT, node.id, payload)
        await event_log.append(
            db,
            run_id,
            [
                {
                    "type": SubstrateEventType.SIDE_EFFECT_INTENT,
                    "payload": {
                        "task_id": node.id,
                        "node_type": node.type.value,
                        "effect_class": node.effect_class.value,
                        "idempotency_key": idem_key,
                        "effect": payload,
                    },
                    "actor": "node_executor",
                    "mission_id": workflow.id if workflow else None,
                    "task_id": node.id,
                }
            ],
        )
        logger.info(
            "STAGE committed side_effect_intent for run %s node %s (key %s)",
            run_id,
            node.id,
            idem_key,
        )
        return idem_key

    async def _confirm_irreversible_effect(
        self,
        db: AsyncSession,
        run_id: str,
        node: WorkflowNode,
        workflow: Workflow | None,
        *,
        committed_key: str,
    ) -> None:
        """CONFIRM: commit side_effect_confirmed AFTER a successful fire.

        The key EXCLUDES run_id so a retried/parallel invocation that already
        confirmed this logical effect is deduplicated by the event log and the
        external call is never re-fired.
        """
        event_log = get_event_log()
        payload = self._render_effect_payload(node, workflow)
        # Run-EXCLUDED key → dedupes across retries for the same logical effect.
        idem_key = _compute_idempotency_key(None, SubstrateEventType.SIDE_EFFECT_CONFIRMED, node.id, payload)
        await event_log.append(
            db,
            run_id,
            [
                {
                    "type": SubstrateEventType.SIDE_EFFECT_CONFIRMED,
                    "payload": {
                        "task_id": node.id,
                        "node_type": node.type.value,
                        "effect_class": node.effect_class.value,
                        "staged_key": committed_key,
                        "idempotency_key": idem_key,
                        "effect": payload,
                    },
                    "actor": "node_executor",
                    "mission_id": workflow.id if workflow else None,
                    "task_id": node.id,
                }
            ],
        )
        logger.info(
            "CONFIRM committed side_effect_confirmed for run %s node %s (key %s)",
            run_id,
            node.id,
            idem_key,
        )

    @staticmethod
    def _render_effect_payload(node: WorkflowNode, workflow: Workflow | None) -> dict[str, Any]:
        """Render the fully-rendered, idempotency-deterministic effect descriptor.

        This is what gets committed in STAGE and compared in CONFIRM. It must
        contain everything needed to (re)fire the effect exactly once.
        """
        return {
            "task_id": node.id,
            "node_type": node.type.value,
            "tool_name": node.config.get("tool_name"),
            "prompt": node.config.get("prompt"),
            "url": node.config.get("url"),
            "action": node.config.get("action"),
            "sub_workflow_mode": node.config.get("sub_workflow_mode"),
            "mission_id": workflow.id if workflow else None,
        }

    async def _dispatch(
        self,
        db: AsyncSession,
        node: WorkflowNode,
        context: dict[str, Any],
        budget: Budget,
        run_id: str,
        workflow: Workflow | None = None,
        *,
        context_events: list[SubstrateEvent] | None = None,
    ) -> dict[str, Any]:
        """Dispatch a node to the appropriate handler based on its type."""
        match node.type:
            case NodeType.LLM_CALL:
                return await self._handle_llm(
                    db,
                    node,
                    context,
                    budget,
                    run_id,
                    workflow,
                    context_events=context_events or [],
                )
            case NodeType.TOOL_CALL:
                return await self._handle_tool(db, node, context, budget, run_id, workflow)
            case NodeType.CODE_EXECUTION:
                return await self._handle_code(db, node, context, run_id, workflow)
            case NodeType.RAG_QUERY:
                return await self._handle_rag(node, context, workflow)
            case NodeType.WEB_SEARCH:
                return await self._handle_web_search(node, context)
            case NodeType.FILE_OPERATION:
                return await self._handle_file(node, context)
            case NodeType.HUMAN_REVIEW:
                return await self._handle_hitl_interrupt(
                    db,
                    node,
                    context,
                    run_id,
                    workflow,
                    interrupt_type="clarification",
                )
            case NodeType.APPROVAL:
                return await self._handle_hitl_interrupt(
                    db,
                    node,
                    context,
                    run_id,
                    workflow,
                    interrupt_type="approval",
                )
            case (
                NodeType.BROWSER_NAVIGATE
                | NodeType.BROWSER_SNAPSHOT
                | NodeType.BROWSER_CLICK
                | NodeType.BROWSER_TYPE
                | NodeType.BROWSER_SCROLL
                | NodeType.BROWSER_SCREENSHOT
                | NodeType.BROWSER_CLOSE
            ):
                return await self._handle_browser(node, context)
            case NodeType.SUB_WORKFLOW:
                return await self._handle_sub_workflow(db, node, context, budget, run_id)
            case NodeType.PHASE_GATE | NodeType.FAN_OUT | NodeType.FAN_IN:
                # Delegated to strategy — the node executor just passes through
                return {"success": True, "output": context, "tokens": 0}
            case NodeType.SANDBOX:
                return await self._handle_sandbox_node(db, node, context, budget, run_id, workflow)
            case _:
                return {"success": False, "error": f"Unknown node type: {node.type}"}

    # ── LLM handler ─────────────────────────────────────────────────

    @staticmethod
    def _tool_result_to_dict(result: Any) -> dict[str, Any]:
        if isinstance(result, dict):
            normalized = {
                "success": bool(result.get("success", False)),
                "output": result.get("output"),
                "tokens": int(result.get("tokens", result.get("tokens_used", 0)) or 0),
                "cost": float(result.get("cost", result.get("cost_usd", 0.0)) or 0.0),
                "error": result.get("error"),
            }
            for key, value in result.items():
                if key not in normalized:
                    normalized[key] = value
            return normalized

        return {
            "success": bool(getattr(result, "success", False)),
            "output": getattr(result, "result", getattr(result, "data", None)),
            "tokens": int(getattr(result, "tokens_used", 0) or 0),
            "cost": float(getattr(result, "cost_usd", 0.0) or 0.0),
            "error": getattr(result, "error", None),
        }

    # Trust-boundary (agent-loop-trust-boundary skill): tool output re-enters
    # the prompt on the next node, so it must be sanitized at this boundary.
    _CONTROL_CHARS = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
    _MAX_OUTPUT_CHARS = 16_000

    @classmethod
    def _sanitize_tool_output(cls, normalized: dict[str, Any]) -> dict[str, Any]:
        """Delimit + strip control chars + length-cap the untrusted OUTPUT field."""
        out = normalized.get("output")
        if isinstance(out, dict):
            text = out.get("text") or out.get("stdout") or ""
            if isinstance(text, str):
                out = {**out, "text": cls._sanitize_text(text)}
        elif isinstance(out, str):
            out = cls._sanitize_text(out)
        return {**normalized, "output": out}

    @classmethod
    def _sanitize_text(cls, text: str) -> str:
        text = cls._CONTROL_CHARS.sub(" ", text)
        if len(text) > cls._MAX_OUTPUT_CHARS:
            text = text[: cls._MAX_OUTPUT_CHARS] + " …[truncated]"
        return text

    async def _handle_llm(
        self,
        db: AsyncSession,
        node: WorkflowNode,
        context: dict[str, Any],
        budget: Budget,
        run_id: str,
        workflow: Workflow | None = None,
        *,
        context_events: list[SubstrateEvent] | None = None,
    ) -> dict[str, Any]:
        """Execute an LLM call through the BudgetEnforcer.

        Item #3: LLM output replay.  Before calling the provider, check
        if a recorded llm.response event exists for this node.  If so,
        return it immediately without re-calling the LLM (avoids double
        billing on crash recovery).
        """
        mission_id = workflow.id if workflow else None

        # Phase 6.4: Circuit breaker check before LLM call
        if mission_id:
            allowed, reason = await self.executor.check_circuit_breaker(db=db, mission_id=mission_id, call_type="llm")
            if not allowed:
                return {
                    "success": False,
                    "error": f"Circuit breaker: {reason}",
                    "tokens": 0,
                }

        # Item #3: LLM output replay — check for recorded response
        event_log = get_event_log()

        # Comment 7: consume the depth/reasoning profile (promoted from the
        # DepthPolicy decision) to pick the model + ReasoningOptions. An
        # explicitly assigned model is still honored for normal/deep when it
        # satisfies the profile's tier; otherwise depth selection wins.
        from app.services.substrate.depth_selection import select_model_for_depth
        from app.services.substrate.workflow_models import ReasoningProfile

        _profile = node.reasoning_profile or ReasoningProfile.NORMAL
        _budget_remaining = None
        if hasattr(budget, "remaining"):
            try:
                _budget_remaining = budget.remaining().get("cost_usd")
            except Exception:
                _budget_remaining = None
        _sel = select_model_for_depth(
            _profile,
            budget_remaining_usd=_budget_remaining,
            explicit_model=node.assigned_model,
        )
        model_id = _sel.model_id
        reasoning_options = _sel.reasoning
        if node.assigned_model and node.assigned_model != _sel.model_id:
            logger.info(
                "Depth profile %s overrode node model %s -> %s%s",
                _profile.value,
                node.assigned_model,
                _sel.model_id,
                f" (degraded: {_sel.degradation_note})" if _sel.degraded else "",
            )

        # Emit the existing DEPTH_DECIDED event so replay explains the choice.
        try:
            await event_log.append(
                db,
                run_id,
                [
                    {
                        "type": "depth.decided",
                        "payload": {
                            "node_id": node.id,
                            "profile": _profile.value,
                            "model_id": _sel.model_id,
                            "reflection_iterations": _sel.reflection_iterations,
                            "degraded": _sel.degraded,
                            "degradation_note": _sel.degradation_note,
                        },
                        "actor": "node_executor",
                        "mission_id": mission_id,
                        "task_id": node.id,
                    }
                ],
            )
        except Exception as e:
            logger.debug("Failed to record depth.decided event: %s", e)

        prompt = node.config.get("prompt", node.description or node.title)

        replay_key = _compute_idempotency_key(
            run_id,
            SubstrateEventType.LLM_RESPONSE,
            node.id,
            {"model_id": model_id, "prompt": prompt},
        )
        cached_event = await event_log.find_by_idempotency_key(db, replay_key)
        if cached_event is not None:
            payload = cached_event.payload or {}
            logger.info(
                "LLM output replay for node %s (run %s)",
                node.id,
                run_id,
            )
            return {
                "success": True,
                "output": {"text": payload.get("response", "")},
                "tokens": payload.get("tokens", 0),
                "cost": payload.get("cost_usd", 0.0),
                "model": payload.get("model", model_id),
                "provider": payload.get("provider", "replayed"),
            }

        from app.services.budget_enforcer import get_budget_enforcer

        enforcer = get_budget_enforcer()

        system_prompt = node.config.get("system_prompt")
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})

        # Q2-Q3 Chunk 2 Tier 1: Inject last-N event context window.
        if context_events:
            ctx_text = self._format_context_events(context_events)
            if ctx_text:
                messages.append(
                    {
                        "role": "system",
                        "content": (f"Recent mission events (last {len(context_events)} steps):\n{ctx_text}"),
                    }
                )

        # Comment 11: long-context assembly for deep/long-context nodes.
        # This is the dedicated long-context substrate (NOT personal/episodic
        # memory). When the node profile is deep, or the node explicitly opts
        # into long-context, we consult the run-scoped ContextManager, inject
        # the rendered context BEFORE the user prompt, and persist a
        # context.plan substrate event so replay explains exactly what the
        # model saw (which chunks, pins, rolling summary, token budget).
        wants_context = _profile == ReasoningProfile.DEEP or node.config.get("long_context") is True
        if wants_context:
            _mgr = self._context_manager(run_id)
            if _mgr.has_sources():
                _query = node.config.get("context_query", prompt)
                try:
                    _plan, _rendered = _mgr.build_plan(
                        run_id,
                        node.id,
                        query=_query,
                        token_budget=node.config.get("context_token_budget"),
                    )
                except Exception as e:  # never block execution on context build
                    _plan, _rendered = None, None
                    logger.debug("ContextManager.build_plan failed: %s", e)
                if _rendered:
                    messages.append(
                        {
                            "role": "system",
                            "content": (
                                "Long-context research window (ingested sources, "
                                "pinned evidence, rolling summary):\n" + _rendered
                            ),
                        }
                    )
                if _plan is not None:
                    try:
                        await _mgr.record_context_event(db, run_id, _plan, node_id=node.id, mission_id=mission_id)
                    except Exception as e:  # fire-and-forget persistence
                        logger.debug("Failed to record context.plan event: %s", e)

        messages.append({"role": "user", "content": prompt})

        response = await enforcer.call(
            budget=budget,
            model_id=model_id,
            messages=messages,
            user_id=workflow.user_id if workflow else None,
            run_id=run_id,
            mission_id=mission_id,
            task_id=node.id,
            temperature=node.config.get("temperature", 0.7),
            max_tokens=node.config.get("max_tokens", 2000),
            reasoning=reasoning_options,
        )

        if not response.get("success"):
            return {
                "success": False,
                "error": response.get("error", "LLM call failed"),
                "tokens": 0,
            }

        content = response.get("response", "")
        cost_info = response.get("cost", {})
        budget_info = response.get("budget", {})
        prompt_tokens = cost_info.get("input_tokens", budget_info.get("prompt_tokens", 0))
        completion_tokens = cost_info.get("output_tokens", budget_info.get("completion_tokens", 0))
        tokens = int(prompt_tokens or 0) + int(completion_tokens or 0)

        if not content or content.strip() == "":
            return {
                "success": False,
                "error": "LLM returned empty response",
                "tokens": tokens,
            }

        # Item #3: Record LLM response for future replay
        cost_usd = float(cost_info.get("usd", budget_info.get("spent_usd", 0.0)) or 0.0)
        try:
            await event_log.append(
                db,
                run_id,
                [
                    {
                        "type": SubstrateEventType.LLM_RESPONSE,
                        "payload": {
                            "response": content,
                            "tokens": tokens,
                            "cost_usd": cost_usd,
                            "model": response.get("model", model_id),
                            "provider": response.get("provider", "unknown"),
                            "prompt_tokens": prompt_tokens,
                            "completion_tokens": completion_tokens,
                        },
                        "actor": "node_executor",
                        "mission_id": mission_id,
                        "task_id": node.id,
                        "idempotency_key": replay_key,
                    }
                ],
            )
        except Exception as e:
            logger.debug("Failed to record LLM response for replay: %s", e)

        return {
            "success": True,
            "output": {"text": content},
            "tokens": tokens,
            "cost": cost_usd,
            "model": response.get("model", model_id),
            "provider": response.get("provider", "unknown"),
            "reasoning_profile": _profile.value,
            "reflection_iterations": _sel.reflection_iterations,
            "depth_degraded": _sel.degraded,
            "depth_degradation_note": _sel.degradation_note,
        }

    # ── Tool handler ────────────────────────────────────────────────

    # ── Cost event recording helper (Q1-B Chunk 4) ─────────────────

    async def _emit_cost_event(
        self,
        db: AsyncSession,
        node: WorkflowNode,
        result: dict[str, Any],
        category: str,
        run_id: str,
        workflow: Workflow | None = None,
        tool_name: str | None = None,
        embedding_tokens: int = 0,
    ) -> None:
        """Emit a cost event for a non-LLM node execution.

        Fire-and-forget — records to LLMCallRecord with cost_category
        so the per-step cost attribution engine can aggregate it.
        """
        try:
            from app.models.cost_event import CostCategory, CostEvent
            from app.services.cost_tracker import get_cost_tracker

            cost_usd = float(result.get("cost", 0.0) or 0.0)
            if cost_usd <= 0.0 and category == "tool_execution":
                # Estimate based on latency if no explicit cost
                latency_ms = int(result.get("latency_ms", 0) or 0)
                if latency_ms > 0:
                    cost_usd = latency_ms * 0.000001  # $1 per 1M ms ≈ $0.001/s

            event = CostEvent(
                category=CostCategory(category),
                cost_usd=cost_usd,
                mission_id=workflow.id if workflow else "",
                node_id=node.id,
                run_id=run_id,
                provider=category,
                model_id=node.config.get("tool_name") or node.config.get("tool_id") or category,
                tool_name=tool_name,
                embedding_tokens=embedding_tokens,
                latency_ms=int(result.get("latency_ms", 0) or 0),
                workspace_id=getattr(workflow, "workspace_id", None) or "",
                agent_id=getattr(workflow, "user_id", None) or "",
            )
            tracker = get_cost_tracker()
            await tracker.record_cost_event(db, event)
        except Exception as e:
            logger.debug("Cost event emission skipped for node %s: %s", node.id, e)

    async def _handle_tool(
        self,
        db: AsyncSession,
        node: WorkflowNode,
        context: dict[str, Any],
        budget: Budget,
        run_id: str,
        workflow: Workflow | None = None,
    ) -> dict[str, Any]:
        """Execute a tool call with capability verification."""
        # Phase 6.4: Circuit breaker check before tool call
        mission_id = workflow.id if workflow else None
        if mission_id:
            allowed, reason = await self.executor.check_circuit_breaker(db=db, mission_id=mission_id, call_type="tool")
            if not allowed:
                return {"success": False, "error": f"Circuit breaker: {reason}"}

        from app.services.capability_engine import get_capability_engine

        cap_engine = get_capability_engine()
        tool_name = node.config.get("tool_name") or node.config.get("tool_id")

        if not tool_name:
            # Fall back to LLM if no tool specified
            logger.info("No tool specified for node %s, falling back to LLM", node.id)
            return await self._handle_llm(db, node, context, budget, run_id, workflow)

        # Capability check: verify the caller has permission.
        # Use the workflow's user_id as the principal for token issuance.
        # The kernel should pre-issue tokens before execution reaches this point.
        from uuid import UUID as _UUID

        principal_id = (
            _UUID(workflow.user_id) if workflow and workflow.user_id else _UUID("00000000-0000-0000-0000-000000000000")
        )
        resource = ResourceRef(kind="tool", name=tool_name)
        token = cap_engine.issue(
            resource=resource,
            actions={Action.EXECUTE},
            to=principal_id,
        )

        try:
            cap_engine.verify_and_require(token, Action.EXECUTE)
        except PermissionError as e:
            return {"success": False, "error": f"Capability denied: {e}"}

        # Epic 4.1b: standing-constraint gate. Loads the user's durable
        # ``constraint`` claims and blocks / escalates conflicting tool
        # calls. Fail-open by design — a memory-store error must never
        # brick tool dispatch. NOTE: fail-open means a constraint-store
        # outage widens permissions to allow-all (incl. payment/send); a
        # static deny-list for those is future hardening, not here.
        workspace_id = getattr(workflow, "workspace_id", None) or ""
        if workspace_id:
            from app.services.pre_tool_constraints import (
                ALLOW,
                PreToolConstraints,
            )

            constraints = PreToolConstraints(db)
            resolved_uid = PreToolConstraints.resolve_user_id(getattr(workflow, "user_id", None))
            verdict = await constraints.evaluate(
                tool_name,
                user_id=resolved_uid,
                workspace_id=workspace_id,
            )
            if verdict.decision == "block":
                logger.warning(
                    "Tool %s blocked by standing constraint: %s",
                    tool_name,
                    verdict.reason,
                )
                return {
                    "success": False,
                    "error": f"Blocked by standing constraint: {verdict.reason}",
                    "constraint_blocked": True,
                    "constraint_id": verdict.triggered_claim_id,
                }
            if verdict.decision == "escalate":
                # REAL human-in-the-loop gate (G-9). A standing constraint
                # says this tool needs a human's sign-off before it runs.
                # Pause the run by raising HITLPaused — exactly the same
                # mechanism an APPROVAL/HUMAN_REVIEW node uses — so the run
                # is released (lease) and a human-review inbox item is
                # created. On approval the executor re-enters this node and
                # the approved tool proceeds; on reject the node fails.
                #
                # NOTE: this must NOT simply return a failure dict — that
                # would be a silent hard block, not HITL. The run genuinely
                # pauses here.
                return await self._escalate_constraint_to_hitl(db, node, run_id, workflow, verdict)

        # Route to tool handler
        handlers = {
            "web_search": self._tool_web_search,
            "code_executor": self._tool_code_executor,
            "file_reader": self._tool_file_reader,
            "rag_search": self._tool_rag_search,
        }

        handler = handlers.get(tool_name)
        if not handler:
            return {"success": False, "error": f"Unknown tool: {tool_name}"}

        # For the RAG search tool, inject the workflow's user_id into the
        # execution context so the shared-collection query can be scoped
        # per user (fail-open when no workflow/user_id is available).
        if tool_name == "rag_search":
            context = {**context, "__rag_user_id__": workflow.user_id if workflow else None}

        params = node.config.get("params", {})
        tool_result = await handler(params, context)
        normalized = self._tool_result_to_dict(tool_result)

        # Trust-boundary (agent-loop-trust-boundary skill): the capability and
        # standing-constraint gates above (:920, :937) check the CALLER/tool,
        # NOT the OUTPUT. A web_search/rag/file_reader result is untrusted and
        # re-enters the prompt on the next node — sanitize it here.
        normalized = self._sanitize_tool_output(normalized)

        # Q1-B Chunk 4: emit tool_execution cost event
        if normalized.get("success"):
            await self._emit_cost_event(
                db,
                node,
                normalized,
                "tool_execution",
                run_id,
                workflow,
                tool_name=tool_name,
            )

        return normalized

    # ── Code execution ──────────────────────────────────────────────

    async def _handle_code(
        self,
        db: AsyncSession,
        node: WorkflowNode,
        context: dict[str, Any],
        run_id: str = "",
        workflow: Workflow | None = None,
    ) -> dict[str, Any]:
        """Execute Python code in a sandboxed subprocess."""
        code = node.config.get("code") or context.get("code")
        if not code:
            return {"success": False, "error": "No code provided"}

        result = await self._execute_code_sandboxed(code)

        # Q1-B Chunk 4: emit tool_execution cost event for code execution
        if result.get("success") and run_id:
            await self._emit_cost_event(
                db,
                node,
                result,
                "tool_execution",
                run_id,
                workflow,
                tool_name="code_executor",
            )

        return result

    async def _execute_code_sandboxed(self, code: str) -> dict[str, Any]:
        """Execute code in a restricted subprocess.

        SECURITY: Code runs in an isolated subprocess with:
        - No network access (blocked via environment)
        - Restricted builtins (no __import__, open, exec, eval, compile)
        - 60-second timeout
        - Restricted cwd
        - Output size limit (1MB)

        Uses a temporary .py file instead of inline exec() to avoid
        quote-escaping issues with triple-quoted strings.
        """
        import os as _os
        import shutil
        import subprocess
        import tempfile

        workspace = tempfile.mkdtemp(prefix="mission_")

        # Security: blocked patterns
        DANGEROUS = [
            "__import__",
            "import os",
            "import sys",
            "import subprocess",
            "import socket",
            "import urllib",
            "import http",
            "exec(",
            "eval(",
            "compile(",
            "open(",
            "file(",
            "os.",
            "sys.exit",
            "sys.modules",
            "sys.path",
            "globals()",
            "locals()",
            "vars()",
        ]
        code_lower = code.lower()
        for pat in DANGEROUS:
            if pat.lower() in code_lower:
                return {"success": False, "error": f"Blocked pattern: '{pat}'"}

        tmp_path = _os.path.join(workspace, "_exec.py")
        indented_code = "\n".join("    " + line for line in code.strip().split("\n"))
        with open(tmp_path, "w") as f:
            # Use str.replace() instead of str.format() because the wrapper
            # contains literal curly braces in __builtins__ = { ... } that
            # conflict with format()'s placeholder syntax.
            f.write(_WORKSPACE_WRAPPER.replace("{code}", indented_code))

        try:
            result = subprocess.run(
                ["python3", tmp_path],
                capture_output=True,
                text=True,
                timeout=60,
                cwd=workspace,
            )
            return {
                "success": result.returncode == 0,
                "output": {
                    "stdout": result.stdout[:1_000_000] if result.stdout else "",
                    "stderr": result.stderr[:100_000] if result.stderr else "",
                    "return_code": result.returncode,
                },
                "error": result.stderr if result.returncode != 0 else None,
            }
        except subprocess.TimeoutExpired:
            return {"success": False, "error": "Execution timed out (60s limit)"}
        except Exception as e:
            return {"success": False, "error": str(e)}
        finally:
            shutil.rmtree(workspace, ignore_errors=True)

    # ── RAG ─────────────────────────────────────────────────────────

    async def _handle_rag(
        self,
        node: WorkflowNode,
        context: dict[str, Any],
        workflow: Workflow | None = None,
    ) -> dict[str, Any]:
        """Execute a RAG query."""
        query = node.config.get("query") or context.get("query") or node.description or node.title
        collection = node.config.get("collection", "default")
        user_id = workflow.user_id if workflow else None

        try:
            from app.services.rag_service import RAGService

            rag = RAGService()
            results = rag.query_documents(query, n_results=5, user_id=user_id)
            return {
                "success": True,
                "output": {
                    "query": query,
                    "context": results,
                    "collection": collection,
                },
            }
        except Exception as e:
            return {"success": False, "error": f"RAG query failed: {e}"}

    # ── Web search ──────────────────────────────────────────────────

    async def _handle_web_search(self, node: WorkflowNode, context: dict[str, Any]) -> dict[str, Any]:
        """Execute a web search."""
        query = node.config.get("query") or context.get("query") or node.description

        if not query:
            return {"success": False, "error": "No query provided"}

        try:
            from app.services.web_search.models import SearchRequest, SearchType
            from app.services.web_search.service import get_search_service

            service = get_search_service()
            request = SearchRequest(
                query=query,
                search_type=SearchType.GENERAL,  # type: ignore[attr-defined]
                max_results=5,
            )
            response = await service.search(request)

            results = [{"title": r.title, "url": r.url, "snippet": r.snippet} for r in response.results]
            return {"success": True, "output": {"query": query, "results": results}}
        except Exception as e:
            return {"success": False, "error": f"Web search failed: {e}"}

    # ── File operations ─────────────────────────────────────────────

    async def _handle_file(self, node: WorkflowNode, context: dict[str, Any]) -> dict[str, Any]:
        """Execute a file operation."""
        operation = node.config.get("operation", "read")
        file_id = node.config.get("file_id")

        if not file_id:
            return {"success": False, "error": "No file_id provided"}

        try:
            from app.services.file_storage import FileStorageService

            storage = FileStorageService()
            file_info = storage.get_file_info(file_id)
            if not file_info:
                return {"success": False, "error": f"File {file_id} not found"}

            if operation == "read":
                with open(file_info["path"], "r", encoding="utf-8", errors="ignore") as f:
                    content = f.read()
                return {
                    "success": True,
                    "output": {
                        "content": content[:50000],
                        "filename": file_info.get("filename"),
                    },
                }
            elif operation == "list":
                import os

                return {
                    "success": True,
                    "output": {"files": os.listdir(file_info["path"])},
                }
            else:
                return {"success": False, "error": f"Unknown operation: {operation}"}
        except Exception as e:
            return {"success": False, "error": f"File operation failed: {e}"}

    # ── Browser ─────────────────────────────────────────────────────

    async def _handle_browser(self, node: WorkflowNode, context: dict[str, Any]) -> dict[str, Any]:
        """Execute a browser action through the tool registry."""
        try:
            from app.tools.base import ToolRegistry

            tool_name = node.type.value
            tool = ToolRegistry.get(tool_name)  # type: ignore[arg-type]
            if tool is None:
                return {
                    "success": False,
                    "error": f"Browser tool not registered: {tool_name}",
                }

            tool_input = node.config.get("params", {})
            result = await tool.run(tool_input, {"user_id": "system"})  # type: ignore[attr-defined]

            if result.status.value == "success":
                return {"success": True, "output": result.data}
            return {"success": False, "error": result.error}
        except Exception as e:
            return {"success": False, "error": f"Browser tool failed: {e}"}

    # ── Sandbox node (Phase 3) ───────────────────────────────────────

    async def _handle_sandbox_node(
        self,
        db: AsyncSession,
        node: WorkflowNode,
        context: dict[str, Any],
        budget: Budget,
        run_id: str,
        workflow: Workflow | None = None,
    ) -> dict[str, Any]:
        """Execute a sandbox node: create container → push files → submit task → stream SSE.

        Config keys:
            template: sandboxd template name (default "python")
            task_prompt: coding task prompt for sandboxd's AI agent
            shared_workspace: reuse existing sandbox for this mission
            input_files: dict of path→content to write before task
            snapshot_before: create snapshot before executing (rollback safety)
        """
        config = node.config or {}
        task_prompt = config.get("task_prompt") or context.get("task_prompt")
        if not task_prompt:
            return {"success": False, "error": "No task_prompt provided"}

        template = config.get("template", "python")
        shared_workspace = config.get("shared_workspace", False)
        input_files = config.get("input_files", {})
        snapshot_before = config.get("snapshot_before", False)
        model = config.get("model")

        # Blueprint/substrate runs have a run_id but no missions row
        # (Workflow.id == blueprint_id, not a mission id). Keying the
        # sandbox mapping on mission_id would violate the FK to missions(id),
        # so for blueprint-sourced runs we leave mission_id NULL and let
        # run_id carry the link. Legacy Mission runs keep mission_id.
        blueprint_id = getattr(self.executor, "_active_blueprint_id", None)
        mission_id = None if blueprint_id else (workflow.id if workflow else None)
        user_id = workflow.user_id if workflow else "system"
        event_log = get_event_log()

        sandbox_id = None
        try:
            # 1 — Create or reuse sandbox
            # Blueprint/substrate runs have a run_id but no missions row, so key
            # the sandbox mapping on run_id (mission_id stays NULL → no FK break).
            # Legacy Mission runs keep mission_id.
            if shared_workspace and (mission_id or run_id):
                sandbox_id = await self._sandbox_service.get_sandbox_for_mission(mission_id, db=db, run_id=run_id)
            if not sandbox_id:
                if mission_id or run_id:
                    sandbox_id = await self._sandbox_service.ensure_sandbox_for_mission(
                        mission_id=mission_id,
                        user_id=user_id,
                        db=db,
                        template=template,
                        run_id=run_id,
                    )
                else:
                    # No mission/run context — create ephemeral sandbox
                    resp = await self._sandbox_client.create(
                        project_id=f"node_{node.id}",
                        user_id=user_id,
                        template=template,
                    )
                    sandbox_id = resp["id"]

            await event_log.append(
                db,
                run_id,
                [
                    {
                        "type": SubstrateEventType.SANDBOX_CREATED,
                        "payload": {"sandbox_id": sandbox_id, "node_id": node.id},
                        "actor": "node_executor",
                        "mission_id": mission_id,
                        "task_id": node.id,
                    }
                ],
            )

            # 2 — Optional snapshot checkpoint
            if snapshot_before:
                snap = await self._sandbox_client.create_snapshot(sandbox_id, f"pre_{node.id}")
                await event_log.append(
                    db,
                    run_id,
                    [
                        {
                            "type": SubstrateEventType.SANDBOX_SNAPSHOT_CREATED,
                            "payload": {
                                "snapshot_id": snap.get("id"),
                                "sandbox_id": sandbox_id,
                            },
                            "actor": "node_executor",
                            "mission_id": mission_id,
                            "task_id": node.id,
                        }
                    ],
                )

            # 3 — Write input files
            if input_files:
                for path, content in input_files.items():
                    if isinstance(content, str):
                        content = content.encode("utf-8")
                    await self._sandbox_client.write_file(sandbox_id, path, content)
                await event_log.append(
                    db,
                    run_id,
                    [
                        {
                            "type": SubstrateEventType.SANDBOX_FILES_WRITTEN,
                            "payload": {"files": list(input_files.keys())},
                            "actor": "node_executor",
                            "mission_id": mission_id,
                            "task_id": node.id,
                        }
                    ],
                )

            # 4 — Submit task to sandboxd
            # Render {{ inputs.<key> }} from the run's input values. Use re.sub,
            # not str.format: the sandbox wrapper carries literal {} braces.
            inputs = context.get("inputs") or {}
            if inputs:
                task_prompt = re.sub(
                    r"\{\{\s*inputs\.(\w+)\s*\}\}",
                    lambda m: str(inputs.get(m.group(1), m.group(0))),
                    task_prompt,
                )
            task = await self._sandbox_client.submit_task(
                sandbox_id=sandbox_id,
                prompt=task_prompt,
                agent="opencode",
                model=model,
            )
            task_id = task["id"]

            await event_log.append(
                db,
                run_id,
                [
                    {
                        "type": SubstrateEventType.SANDBOX_TASK_SUBMITTED,
                        "payload": {"task_id": task_id, "sandbox_id": sandbox_id},
                        "actor": "node_executor",
                        "mission_id": mission_id,
                        "task_id": node.id,
                    }
                ],
            )

            # 5 — Stream SSE events, recording progress
            async for sse in self._sandbox_client.task_events(sandbox_id, task_id):
                ev_type = sse.get("type", "")
                ev_data_str = sse.get("data", "{}")

                try:
                    ev_data = json.loads(ev_data_str) if isinstance(ev_data_str, str) else ev_data_str
                except (json.JSONDecodeError, TypeError):
                    ev_data = {"raw": ev_data_str}

                if ev_type == "progress":
                    await event_log.append(
                        db,
                        run_id,
                        [
                            {
                                "type": SubstrateEventType.SANDBOX_TASK_PROGRESS,
                                "payload": {
                                    "task_id": task_id,
                                    "message": ev_data.get("message", ""),
                                    "percent": ev_data.get("percent", 0),
                                },
                                "actor": "node_executor",
                                "mission_id": mission_id,
                                "task_id": node.id,
                            }
                        ],
                    )
                    if hasattr(self.executor, "ws_manager"):
                        self.executor.ws_manager.broadcast_node_state(
                            run_id,
                            node.id,
                            "running",
                            output={
                                "progress": ev_data.get("percent", 0),
                                "message": ev_data.get("message", ""),
                            },
                        )

                elif ev_type == "complete":
                    await event_log.append(
                        db,
                        run_id,
                        [
                            {
                                "type": SubstrateEventType.SANDBOX_TASK_COMPLETED,
                                "payload": {
                                    "task_id": task_id,
                                    "exit_code": ev_data.get("exit_code", 0),
                                    "stdout": str(ev_data.get("stdout", ""))[:50000],
                                },
                                "actor": "node_executor",
                                "mission_id": mission_id,
                                "task_id": node.id,
                            }
                        ],
                    )
                    return {
                        "success": ev_data.get("exit_code", 0) == 0,
                        "output": {
                            "sandbox_id": sandbox_id,
                            "task_id": task_id,
                            "stdout": ev_data.get("stdout", ""),
                            "exit_code": ev_data.get("exit_code", 0),
                        },
                        "tokens": 0,
                        "cost": 0.0,
                    }

                elif ev_type == "error":
                    await event_log.append(
                        db,
                        run_id,
                        [
                            {
                                "type": SubstrateEventType.SANDBOX_TASK_FAILED,
                                "payload": {
                                    "task_id": task_id,
                                    "error": ev_data.get("error", "Unknown sandbox task error"),
                                },
                                "actor": "node_executor",
                                "mission_id": mission_id,
                                "task_id": node.id,
                            }
                        ],
                    )
                    return {
                        "success": False,
                        "error": ev_data.get("error", "Sandbox task failed"),
                        "tokens": 0,
                    }

            # SSE stream ended without complete/error event
            return {
                "success": False,
                "error": "SSE stream ended unexpectedly (no complete/error event)",
                "tokens": 0,
            }

        except Exception as e:
            logger.exception("Sandbox node %s failed", node.id)
            return {"success": False, "error": f"Sandbox node failed: {e}", "tokens": 0}

    # ── Sub-workflow (recursive) ────────────────────────────────────

    # Maximum recursion depth to prevent infinite sub-workflow loops.
    _MAX_SUB_WORKFLOW_DEPTH = 5

    async def _handle_sub_workflow(
        self,
        db: AsyncSession,
        node: WorkflowNode,
        context: dict[str, Any],
        budget: Budget,
        run_id: str,
    ) -> dict[str, Any]:
        """Execute a sub-workflow recursively through the unified executor.

        Loads the child workflow from the database, converts its nodes
        and edges into the canonical Workflow format, and delegates to
        ``self.executor.execute()``.  The parent's budget is shared with
        the child so that spending limits apply across the full DAG.

        Guarded by ``_MAX_SUB_WORKFLOW_DEPTH`` to prevent infinite loops.
        """
        sub_workflow_id = node.config.get("workflow_id")
        if not sub_workflow_id:
            return {"success": False, "error": "No workflow_id for sub_workflow node"}

        # Depth guard — tracked via workflow metadata
        current_depth = context.get("_sub_workflow_depth", 0) + 1
        if current_depth > self._MAX_SUB_WORKFLOW_DEPTH:
            return {
                "success": False,
                "error": f"Max recursion depth ({self._MAX_SUB_WORKFLOW_DEPTH}) exceeded for sub-workflow {sub_workflow_id}",
                "tokens": 0,
            }

        # Check abort signal before starting sub-workflow
        if self.executor.is_aborted(run_id):
            return {"success": False, "error": "Aborted", "tokens": 0}

        try:
            from sqlalchemy import select

            from app.models.graph import GraphWorkflow

            # Load the child workflow from the DB (graph_workflows table)
            result = await db.execute(select(GraphWorkflow).where(GraphWorkflow.id == sub_workflow_id))
            child_graph = result.scalar_one_or_none()
            if child_graph is None:
                return {
                    "success": False,
                    "error": f"Sub-workflow {sub_workflow_id} not found",
                    "tokens": 0,
                }

            # Convert to canonical Workflow via existing adapter
            from app.services.substrate.adapters import graph_to_workflow

            child_workflow = graph_to_workflow(child_graph)

            # Item #3: Reserve worst-case budget for the child workflow.
            # The child's declared max_cost_usd is reserved up front; unused
            # portion is refunded after the child completes.
            child_max_cost = child_workflow.budget.max_cost_usd
            budget.reserve(child_max_cost)

            # Give the child its own isolated budget (not the parent's)
            from decimal import Decimal

            child_budget = Budget(
                max_cost_usd=child_max_cost,
                max_wall_time_seconds=int(budget.max_wall_time_seconds),
                max_iterations=int(budget.max_iterations),
                max_depth=int(budget.max_depth) - 1,
                max_parallel_agents=int(budget.max_parallel_agents),
            )
            child_workflow.budget = child_budget

            # Propagate depth tracking
            child_workflow.metadata["_sub_workflow_depth"] = current_depth

            # Execute recursively via the same unified executor
            from app.services.substrate.workflow_models import StrategyResult

            strategy_result: StrategyResult = await self.executor.execute(db, child_workflow)

            # Item #3: Refund unused reservation back to parent budget
            unused = child_max_cost - child_budget.spent_usd
            if unused > 0:
                budget.refund(unused)

            return {
                "success": strategy_result.success,
                "output": {
                    "sub_workflow_id": sub_workflow_id,
                    "status": strategy_result.status,
                    "data": strategy_result.data,
                    "completed_nodes": strategy_result.completed_nodes,
                    "failed_nodes": strategy_result.failed_nodes,
                },
                "tokens": strategy_result.total_tokens,
                "cost": strategy_result.total_cost_usd,
                "error": strategy_result.error,
            }
        except BudgetExhausted:
            # Child exceeded its budget — reservation already spent, no refund
            raise
        except Exception as e:
            # Refund unused reservation on non-budget failure
            unused = child_max_cost - child_budget.spent_usd
            if unused > 0:
                budget.refund(unused)
            logger.exception("Sub-workflow %s execution failed", sub_workflow_id)
            return {
                "success": False,
                "error": f"Sub-workflow execution failed: {e}",
                "tokens": 0,
            }

    # ── Q1-B: HITL resume check ─────────────────────────────────────

    async def _check_hitl_resume(
        self,
        db: AsyncSession,
        node: WorkflowNode,
        context: dict[str, Any],
        run_id: str,
    ) -> dict[str, Any] | None:
        """Check if this HITL node has already been resolved (resume path).

        On resume after HITL pause, the executor re-enters the HITL node.
        This method checks the inbox item status:
        - approved/clarified → return success with resolution payload
        - rejected/expired → return failure
        - pending → return None (will raise HITLPaused again)
        - no inbox item found → return None (first execution)
        """
        from sqlalchemy import select

        from app.models.hitl_models import InboxItem
        from app.services.substrate.hitl_pause import check_hitl_resolution

        # Find the inbox item for this node in this run
        result = await db.execute(
            select(InboxItem)
            .where(
                InboxItem.run_id == run_id,
                InboxItem.node_id == node.id,
            )
            .order_by(InboxItem.created_at.desc())
            .limit(1)
        )
        item = result.scalar_one_or_none()
        if item is None:
            return None  # First execution — no inbox item yet

        resolution = await check_hitl_resolution(db, item.id)
        if not resolution.resolved:
            return None  # Still pending — will raise HITLPaused again

        if resolution.status in ("approved", "clarified"):
            return {
                "success": True,
                "output": {
                    "hitl_resolution": resolution.status,
                    "resolution_payload": resolution.resolution_payload,
                    "resolution_note": resolution.resolution_note,
                    "inbox_item_id": item.id,
                },
                "tokens": 0,
                "cost": 0.0,
            }

        # rejected, expired, cancelled
        return {
            "success": False,
            "error": f"HITL {resolution.status}: {resolution.resolution_note or 'no details'}",
            "tokens": 0,
            "cost": 0.0,
        }

    # ── HITL interrupt handler (Phase 6.2) ──────────────────────────

    async def _handle_hitl_interrupt(
        self,
        db: AsyncSession,
        node: WorkflowNode,
        context: dict[str, Any],
        run_id: str,
        workflow: Workflow | None = None,
        *,
        interrupt_type: str = "approval",
    ) -> dict[str, Any]:
        """Handle a HITL interrupt node by creating an inbox item and pausing.

        Persists the interrupt to the inbox_items table and emits a
        human_interrupt.raised event. The mission will pause until
        the interrupt is resolved via the HITL Inbox API.
        """
        from app.models.hitl_models import HumanInterruptType, InboxItem
        from app.services.hitl_service import HITLService
        from app.services.substrate.event_log import get_event_log

        event_log = get_event_log()
        hitl_type = HumanInterruptType.APPROVAL if interrupt_type == "approval" else HumanInterruptType.CLARIFICATION

        title = node.config.get("approval_prompt") or node.title or f"{interrupt_type.title()} required"
        description = node.description or node.config.get("description")
        proposed_action = {
            "node_id": node.id,
            "node_title": node.title,
            "node_type": node.type.value,
            "config": {k: v for k, v in node.config.items() if k not in ("approval_prompt",)},
        }

        # Determine the user to notify. workflow.user_id is a UUID *string*
        # (substrate contract) while inbox_items.user_id is an int — coerce
        # only when it's already numeric; otherwise fall back to 0 so a
        # UUID string never raises ValueError here.
        if workflow and workflow.user_id:
            _raw = workflow.user_id
            user_id = int(_raw) if isinstance(_raw, int) else (int(_raw) if str(_raw).isdigit() else 0)
        else:
            user_id = 0
        workspace_id = getattr(workflow, "workspace_id", None) if workflow else None
        mission_id = workflow.id if workflow else None

        # Q1-B chunk 1: Check for existing pending inbox item before creating
        # a new one.  On resume, _check_hitl_resume returns None for pending
        # items, causing re-entry here.  We must NOT create duplicates.
        service = HITLService(db)
        item = None
        try:
            from sqlalchemy import select as select_

            existing_result = await db.execute(
                select_(InboxItem)
                .where(
                    InboxItem.run_id == run_id,
                    InboxItem.node_id == node.id,
                    InboxItem.status == "pending",
                )
                .order_by(InboxItem.created_at.desc())
                .limit(1)
            )
            existing_item = existing_result.scalar_one_or_none()
            if existing_item is not None:
                logger.info(
                    "HITL interrupt already pending: node=%s inbox_item=%s",
                    node.id,
                    existing_item.id,
                )
                item = existing_item
        except Exception as dup_err:
            logger.debug("Duplicate inbox check skipped: %s", dup_err)

        if item is None:
            # GOLD t_002875da: carry a depth-policy decision on the inbox item
            # so the HITL inbox UI can render the reasoning that motivated the
            # interrupt.  At interrupt time we have no per-step risk/uncertainty
            # signal from the executor, so we compute a decision from the
            # strongest available facts: the node requires human approval
            # (tool_requires_approval=True → escalate_to_hitl), and any prior
            # failures/retries on related nodes if reachable.
            from decimal import Decimal

            depth_decision = HITLService.build_depth_decision(
                risk="medium",
                uncertainty=0.5,
                budget_remaining_usd=Decimal("10.0"),
                prior_failures=0,
                tool_requires_approval=True,
                retry_count=0,
                policy_override=False,
            )
            item = await service.create_interrupt(
                mission_id=mission_id or "unknown",
                user_id=user_id,
                interrupt_type=hitl_type,
                title=title,
                description=description,
                proposed_action=proposed_action,
                context={"current_context": context},
                depth_decision=depth_decision,
                task_id=node.id,
                node_id=node.id,
                run_id=run_id,
                workspace_id=workspace_id,
            )

        # Record event
        await event_log.append(
            db,
            run_id,
            [
                {
                    "type": SubstrateEventType.HUMAN_INTERRUPT_RAISED,
                    "payload": {
                        "inbox_item_id": item.id,
                        "interrupt_type": hitl_type.value,
                        "title": title,
                        "node_id": node.id,
                    },
                    "actor": "node_executor",
                    "mission_id": mission_id,
                    "task_id": node.id,
                }
            ],
        )

        logger.info(
            "HITL interrupt raised: node=%s type=%s inbox_item=%s",
            node.id,
            hitl_type.value,
            item.id,
        )

        # Q1-B chunk 1: Raise HITLPaused to actually pause execution.
        # The exception propagates through the strategy to UnifiedExecutor,
        # which releases the lease and emits RUN_PAUSED.
        from app.services.substrate.hitl_pause import HITLPaused

        raise HITLPaused(
            inbox_item_id=item.id,
            run_id=run_id,
            node_id=node.id,
            mission_id=mission_id,
            interrupt_type=hitl_type.value,
            title=title,
            context={"current_context": context},
        )

    # ── Tool helpers ────────────────────────────────────────────────

    async def _tool_web_search(self, params: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
        """Standalone web search tool."""
        query = params.get("query") or context.get("query")
        if not query:
            return {"success": False, "error": "No query provided"}

        try:
            from app.services.web_search.models import SearchRequest, SearchType
            from app.services.web_search.service import get_search_service

            service = get_search_service()
            request = SearchRequest(
                query=query,
                search_type=SearchType.GENERAL,  # type: ignore[attr-defined]
                max_results=5,
            )
            response = await service.search(request)
            results = [{"title": r.title, "url": r.url, "snippet": r.snippet} for r in response.results]
            return {"success": True, "output": {"query": query, "results": results}}
        except Exception as e:
            return {
                "success": True,
                "output": {"query": query, "results": [], "note": str(e)},
            }

    async def _tool_code_executor(self, params: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
        """Standalone code execution tool."""
        code = params.get("code") or context.get("code")
        if not code:
            return {"success": False, "error": "No code provided"}
        return await self._execute_code_sandboxed(code)

    async def _tool_file_reader(self, params: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
        """Standalone file reader tool."""
        file_id = params.get("file_id") or context.get("file_id")
        if not file_id:
            return {"success": False, "error": "No file_id provided"}
        try:
            from app.services.file_storage import FileStorageService

            storage = FileStorageService()
            file_info = storage.get_file_info(file_id)
            if not file_info:
                return {"success": False, "error": f"File {file_id} not found"}
            with open(file_info["path"], "r", encoding="utf-8", errors="ignore") as f:
                content = f.read()
            return {
                "success": True,
                "output": {
                    "filename": file_info.get("filename"),
                    "content": content[:50000],
                    "size": len(content),
                },
            }
        except Exception as e:
            return {"success": False, "error": f"File read failed: {e}"}

    async def _tool_rag_search(self, params: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
        """Standalone RAG search tool."""
        query = params.get("query") or context.get("query")
        # user_id is injected into context by _handle_tool for per-user
        # scoping of shared-collection queries (fail-open if absent).
        user_id = context.get("__rag_user_id__")
        if not query:
            return {"success": False, "error": "No query provided"}
        try:
            from app.services.rag_service import RAGService

            rag = RAGService()
            results = rag.query_documents(query, n_results=5, user_id=user_id)
            return {"success": True, "output": {"query": query, "context": results}}
        except Exception as e:
            return {"success": False, "error": f"RAG search failed: {e}"}
