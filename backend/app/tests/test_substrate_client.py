# ─────────────────────────────────────────────────────────────────────
# Tests for the Phase-1 chat → substrate wedge (SubstrateClient facade
# + the run-dispatch / SSE re-emit routes).
#
# These are contract/mapping tests: they prove the SPIKE pipe
# ``event_log → SSE → trace-tile`` deterministically WITHOUT a live
# LLM, by feeding a fake EventLog of substrate frames into
# ``run_substrate_turn_sse`` and asserting the frontend-understood
# SSE events that come out (what ``AgentTraceTile`` renders).
#
# Run from the backend worktree:
#     PYTHONPATH=. uv run pytest app/tests/test_substrate_client.py -q
# ─────────────────────────────────────────────────────────────────────
from __future__ import annotations

import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from app.api.deps import get_current_user, get_db
from app.main_fastapi import app
from app.services.chat.substrate_client import (
    _map_substrate_event_to_sse,
    build_solo_workflow,
    run_substrate_turn_sse,
)

# ── helpers ────────────────────────────────────────────────────────


def _substrate_event(type_: str, payload: dict, seq: int = 1) -> SimpleNamespace:
    """Build a substrate-event-shaped object (duck-types EventLog rows)."""
    return SimpleNamespace(type=type_, payload=payload, sequence=seq)


class _FakeEventLog:
    """EventLog stand-in that returns a canned frame list."""

    def __init__(self, events: list) -> None:
        self._events = events

    async def get_events(self, db, run_id, **kwargs):
        return self._events


# ── pure mapping tests ─────────────────────────────────────────────


def test_map_task_started_to_agent_step_start():
    ev = _substrate_event("task.started", {"title": "Goal", "node_id": "goal"}, seq=1)
    sse = _map_substrate_event_to_sse(ev)
    assert sse is not None
    assert sse["type"] == "agent_step_start"
    assert sse["step_id"] == "run:1"
    assert sse["name"] == "Goal"
    assert sse["status"] == "running"


def test_map_task_completed_to_agent_step_end_success():
    ev = _substrate_event("task.completed", {"node_id": "goal"}, seq=2)
    sse = _map_substrate_event_to_sse(ev)
    assert sse["type"] == "agent_step_end"
    assert sse["status"] == "success"


def test_map_task_failed_to_agent_step_end_error():
    ev = _substrate_event("task.failed", {"node_id": "goal"}, seq=2)
    sse = _map_substrate_event_to_sse(ev)
    assert sse["type"] == "agent_step_end"
    assert sse["status"] == "error"


def test_map_tool_call_to_tool_result_running():
    ev = _substrate_event("tool.call", {"tool": "web_search", "call_id": "c1"}, seq=3)
    sse = _map_substrate_event_to_sse(ev)
    assert sse["type"] == "tool_result"
    assert sse["tool"] == "web_search"
    assert sse["call_id"] == "c1"
    assert sse["status"] == "running"


def test_map_tool_response_to_tool_result_done():
    ev = _substrate_event(
        "tool.response",
        {"tool": "web_search", "call_id": "c1", "result": "42"},
        seq=4,
    )
    sse = _map_substrate_event_to_sse(ev)
    assert sse["type"] == "tool_result"
    assert sse["status"] == "done"
    assert sse["result"] == "42"


def test_map_noise_event_is_dropped():
    ev = _substrate_event("circuit_breaker.opened", {}, seq=5)
    assert _map_substrate_event_to_sse(ev) is None


# ── pipe test: event_log → SSE ──────────────────────────


@pytest.mark.asyncio
async def test_run_substrate_turn_sse_pipe():
    """The SPIKE verdict test: substrate frames become trace events."""
    fake_events = [
        _substrate_event("task.started", {"title": "Goal", "node_id": "goal"}, seq=1),
        _substrate_event("tool.call", {"tool": "web_search", "call_id": "c1"}, seq=2),
        _substrate_event(
            "tool.response",
            {"tool": "web_search", "call_id": "c1", "result": "hi"},
            seq=3,
        ),
        _substrate_event("task.completed", {"node_id": "goal"}, seq=4),
    ]
    fake_log = _FakeEventLog(fake_events)

    async def _fake_execute(*args, **kwargs):
        return {"success": True, "status": "completed"}

    with (
        patch(
            "app.services.chat.substrate_client.get_event_log",
            return_value=fake_log,
        ),
        patch(
            "app.services.chat.substrate_client.execute_solo_run",
            _fake_execute,
        ),
    ):
        frames = [json.loads(f) async for f in run_substrate_turn_sse(db=object(), goal="do thing", run_id="run-1")]

    types = [f["type"] for f in frames]
    assert types[0] == "run_started"
    assert "agent_step_start" in types
    assert "tool_result" in types
    assert "agent_step_end" in types
    assert types[-1] == "run_complete"
    # exactly one tool_result running + one done (the same call_id)
    tool_results = [f for f in frames if f["type"] == "tool_result"]
    assert {tr["status"] for tr in tool_results} == {"running", "done"}
    assert frames[-1]["ok"] is True
    assert frames[-1]["events_emitted"] == 4


@pytest.mark.asyncio
async def test_run_substrate_turn_sse_on_execute_error():
    fake_log = _FakeEventLog([])

    async def _boom(*args, **kwargs):
        raise RuntimeError("llm down")

    with (
        patch(
            "app.services.chat.substrate_client.get_event_log",
            return_value=fake_log,
        ),
        patch(
            "app.services.chat.substrate_client.execute_solo_run",
            _boom,
        ),
    ):
        frames = [json.loads(f) async for f in run_substrate_turn_sse(db=object(), goal="x", run_id="run-2")]

    assert frames[0]["type"] == "run_started"
    assert frames[1]["type"] == "error"
    assert "llm down" in frames[1]["error"]
    assert frames[-1]["type"] == "run_complete"
    assert frames[-1]["ok"] is False


# ── route contract tests ───────────────────────────────────


def _client():
    from httpx import ASGITransport, AsyncClient

    transport = ASGITransport(app=app)
    return AsyncClient(transport=transport, base_url="http://test")


@pytest.mark.asyncio
async def test_runs_stream_route_requires_auth():
    async with _client() as c:
        r = await c.post(
            "/api/v2/chat/threads/1/runs/stream",
            json={"goal": "hi"},
        )
    assert r.status_code == 401, r.status_code


@pytest.mark.asyncio
async def test_create_run_route_requires_auth():
    async with _client() as c:
        r = await c.post(
            "/api/v2/chat/threads/1/runs",
            json={"goal": "hi"},
        )
    assert r.status_code == 401, r.status_code


def test_build_solo_workflow_shape():
    wf = build_solo_workflow(goal="do it", run_id="r1", model="deepseek/v4")
    assert wf.type.value == "solo"
    assert len(wf.nodes) == 1
    assert wf.nodes[0].type.value == "llm_call"
    assert wf.nodes[0].config["prompt"] == "do it"
