"""Resilience utility for mission templates (Batch 6 — reusable withResilience).

This is Flowmanner's adaptation of the ``withResilience`` helper pattern we
extracted from the kimi sandbox app. The kimi version modeled resilience with
``label: "failure"`` / ``label: "success"`` edges and a re-implemented retry
loop node. We do NOT port that literally, because of two facts about our own
executor:

1. **Transient retry is already native.** ``NodeExecutor.execute`` loops
   ``for attempt in range(node.max_retries + 1)`` (node_executor.py). Re-building
   a retry loop as graph nodes would double-execute. So this helper leaves the
   retry count alone and only shapes *what happens after retries are exhausted*.

2. **Edge selection is success-biased.** ``GraphStrategy._evaluate_condition``
   fires an outgoing edge only when its ``condition`` resolves truthy, and on a
   failed node it records ``node_outputs[id] = {"error": "..."}`` (a truthy
   string). On success it records ``{"output": ...}`` where ``.error`` is None
   (falsy). Therefore the faithful equivalent of kimi's ``label:"failure"`` edge
   is ``condition="{{id.error}}"`` — truthy only when the task permanently
   failed, falsy on success so the success path runs untouched.

The helper therefore wraps each ``task`` (and ``tool``/``code``) node with an
*escalation subgraph* that is inert on success and only engages on permanent
failure. The default gate is ``"pass_through"`` (no extra nodes, native retry
only) so the helper is a no-op unless the caller opts in to escalation.

Two gates are supported today:
- ``"escalate"``  — append a HITL approval node; on approval the run's
  ``fallback_strategy`` continues, on denial it is recorded. The approval node
  is REVERSIBLE (it only pauses for a human decision) so the two-phase
  STAGE→CONFIRM side-effect gate does not wrap it.
- ``"log_and_continue"`` — append a warn-log node that records the failure and
  lets the workflow continue along the next layer (fail-soft observability).

Positioning: new nodes are stacked below the wrapped task (``+Y`` offset) so
they render without overlapping the success-path nodes.

EXECUTION SEAM (read before trusting "this adds run-time resilience"):
the subgraph is injected into ``default_plan`` — the canvas/editor plan. The
substrate executes ``MissionTask`` rows built from ``default_tasks`` (or the
LLM planner), not from ``default_plan["nodes"]``. So the injected ``approval``/
``log`` nodes only *run* if the plan→task compiler later expands them into
task rows. This module is therefore a correct, validated **plan transformer**;
the compile bridge is a separate integration step (see resilience_service.py).
"""

from __future__ import annotations

import copy
from typing import Any, Literal

# Allowed gate modes. ``pass_through`` leaves the template unchanged (native
# retry only); the other two inject an executor-honored escalation subgraph.
ResilienceGate = Literal["pass_through", "escalate", "log_and_continue"]

_ALLOWED_WRAP_TYPES = {"task", "tool", "code", "tool_execution", "code_execution"}

# Layout constants (canvas units). Escalation nodes stack below the task.
_Y_OFFSET = 160
_X_OFFSET = 220


def _node_type_str(node: dict[str, Any]) -> str:
    """Best-effort extraction of a node's type from either a canvas or
    substrate-shaped dict."""
    if node.get("type") in _ALLOWED_WRAP_TYPES:
        return node["type"]
    data = node.get("data") or {}
    nt = data.get("nodeType")
    if nt in _ALLOWED_WRAP_TYPES:
        return nt
    return ""


def _is_wrappable(node: dict[str, Any]) -> bool:
    return bool(_node_type_str(node))


def _new_id(base: str, suffix: str) -> str:
    # Keep ids stable/deterministic so re-running is idempotent.
    return f"{base}__res_{suffix}"


def _make_log_node(base_id: str, label: str, y: int, x: int) -> dict[str, Any]:
    return {
        "id": _new_id(base_id, "log"),
        "type": "log",
        "position": {"x": x, "y": y},
        "data": {
            "label": f"{label} — failed",
            "nodeType": "log",
            "level": "warn",
            "message": "Task '{{" + base_id + ".error}}' failed after retries",
        },
    }


def _make_approval_node(
    base_id: str, label: str, y: int, x: int, approver_role: str | None, approval_timeout: int, escalation_policy: str
) -> dict[str, Any]:
    data: dict[str, Any] = {
        "label": f"Escalate {label}",
        "nodeType": "approval",
        "approverRole": approver_role or "platform-oncall",
        "approvalTimeout": approval_timeout,
        "escalationPolicy": escalation_policy,
        "effect_class": "reversible",  # approval only pauses for a human decision
    }
    return {
        "id": _new_id(base_id, "approval"),
        "type": "approval",
        "position": {"x": x, "y": y},
        "data": data,
    }


def _failure_edge(source: str, target: str, base_id: str) -> dict[str, Any]:
    """An edge that fires ONLY when the source task permanently failed.

    Under GraphStrategy, ``{{base_id.error}}`` is truthy on failure (the executor
    records ``{"error": "..."}``) and falsy on success (``.error`` is None), so
    this is the correct success-biased routing condition.

    Edge shape matches ``default_plan`` convention (top-level ``label``/``condition``,
    no ``data`` wrapper) so the injected plan renders in the canvas and round-trips
    through the template load/save path.
    """
    return {
        "id": f"e-{base_id}__res_{target}",
        "source": source,
        "target": target,
        "type": "smoothstep",
        "condition": f"{{{{{base_id}.error}}}}",
        "label": "on failure",
    }


def _success_only_edge(source: str, target: str, label: str | None) -> dict[str, Any]:
    edge: dict[str, Any] = {
        "id": f"e-{source}__ok_{target}",
        "source": source,
        "target": target,
        "type": "smoothstep",
    }
    if label:
        edge["label"] = label
    return edge


def _rewire_success_edges(edges: list[dict[str, Any]], base_id: str, replacement: str) -> list[dict[str, Any]]:
    """Redirect the original success-path edges (those leaving the wrapped task)
    to ``replacement`` instead, so the escalation node rejoins the happy path
    once a human approves (``escalate``) or after logging (``log_and_continue``).
    """
    out = []
    for e in edges:
        if e.get("source") == base_id:
            ne = copy.deepcopy(e)
            ne["source"] = replacement
            ne["id"] = f"e-{replacement}__{ne['target']}"
            out.append(ne)
        else:
            out.append(e)
    return out


def apply_resilience(
    template: dict[str, Any],
    gate: ResilienceGate = "escalate",
    approver_role: str | None = None,
    approval_timeout: int = 2,
    escalation_policy: str = "escalate",
) -> dict[str, Any]:
    """Return a copy of ``template`` with an escalation subgraph wrapped around
    every task-type node, per ``gate``.

    Args:
        template: a ``MissionTemplate.default_plan``-shaped dict
            (``{"nodes": [...], "edges": [...]}``). Nodes are canvas-shaped
            (``id/type/position/data``); edges carry ``source``/``target`` and
            optional ``data.label`` / ``data.condition``.
        gate: ``"pass_through"`` (no-op), ``"escalate"`` (HITL approval on
            permanent failure), or ``"log_and_continue"`` (warn log + continue).
        approver_role: role for the escalation approval node (``escalate`` only).
        approval_timeout: hours before escalation auto-fires (``escalate`` only).
        escalation_policy: ``"escalate"`` or ``"abort"`` on timeout.

    Returns:
        A new dict with the same top-level keys plus ``resilience`` metadata
        describing how many task nodes were wrapped and which gate was applied.
        The original ``template`` is never mutated.
    """
    if gate == "pass_through":
        result = copy.deepcopy(template)
        result["resilience"] = {
            "applied": False,
            "gate": "pass_through",
            "wrapped_nodes": 0,
            "note": "Native node.max_retries handles transient failure; no " "escalation subgraph injected.",
        }
        return result

    nodes = copy.deepcopy(template.get("nodes", []))
    edges = copy.deepcopy(template.get("edges", []))

    wrapped = 0
    for node in nodes:
        if not _is_wrappable(node):
            continue
        base_id = node["id"]
        label = (node.get("data") or {}).get("label") or base_id
        bx = (node.get("position") or {}).get("x", 0)
        by = (node.get("position") or {}).get("y", 0)

        if gate == "escalate":
            appr = _make_approval_node(
                base_id, label, by + _Y_OFFSET, bx, approver_role, approval_timeout, escalation_policy
            )
            # Rewire the task's ORIGINAL success edges to rejoin through the
            # approval node BEFORE adding the failure edge, so the failure edge
            # (which also has source==base_id) is not itself rewritten.
            edges = _rewire_success_edges(edges, base_id, appr["id"])
            nodes.append(appr)
            edges.append(_failure_edge(base_id, appr["id"], base_id))
        elif gate == "log_and_continue":
            log = _make_log_node(base_id, label, by + _Y_OFFSET, bx)
            edges = _rewire_success_edges(edges, base_id, log["id"])
            nodes.append(log)
            edges.append(_failure_edge(base_id, log["id"], base_id))
        wrapped += 1

    result = copy.deepcopy(template)
    result["nodes"] = nodes
    result["edges"] = edges
    result["resilience"] = {
        "applied": True,
        "gate": gate,
        "wrapped_nodes": wrapped,
        "approver_role": approver_role,
        "approval_timeout": approval_timeout,
        "escalation_policy": escalation_policy,
    }
    return result
