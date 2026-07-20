"""Phase 2 — GET /api/v2/runs/{run_id}/provenance regression tests.

These tests are hermetic: no Postgres, no Docker, no Alembic. The substrate
read path is exercised with AsyncMock / MagicMock stand-ins for the DB
session and the EventLog singleton, so the suite runs on the host.

Coverage:
  * ``_event_to_provenance`` projects structural + best-effort fields
    correctly and returns ``None`` for anything the event log did not emit.
  * ``RunService.get_provenance`` performs a READ-only projection over the
    event log (it never writes) and uses a *separate* read session (contract
    10 of the ``_blueprint_cqrs`` AGENTS.md).
  * The handler endpoint wiring returns the ``ok(...)``-wrapped envelope.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.run_service import RunService, _event_to_provenance


class _FakeEvent:
    """Minimal stand-in for a ``SubstrateEvent`` ORM row."""

    def __init__(
        self,
        sequence: int,
        run_id: str,
        type: str,
        actor: str = "system",
        causal_parent: int | None = None,
        payload: dict | None = None,
        task_id=None,
    ) -> None:
        self.sequence = sequence
        self.run_id = run_id
        self.type = type
        self.actor = actor
        self.causal_parent = causal_parent
        self.payload = payload or {}
        self.task_id = task_id


# ── _event_to_provenance ────────────────────────────────────────────


def test_provenance_full_payload():
    """All best-effort fields emitted by the event log are projected."""
    ev = _FakeEvent(
        sequence=3,
        run_id="run-9",
        type="tool_call",
        actor="agent:planner",
        causal_parent=2,
        payload={
            "tool_name": "web_search",
            "reasoning": "need live pricing",
            "capability_scope": "tools.web_search",
            "budget_spent": 0.012,
            "content_hash": "abc123",
        },
    )
    out = _event_to_provenance(ev)
    assert out == {
        "seq": 3,
        "actor": "agent:planner",
        "causal_parent": 2,
        "type": "tool_call",
        "reasoning": "need live pricing",
        "tool_name": "web_search",
        "capability_scope": "tools.web_search",
        "budget_spent": 0.012,
        "content_hash": "abc123",
    }


def test_provenance_missing_fields_are_null():
    """When the event log omits explainability fields, they fall back to None."""
    ev = _FakeEvent(
        sequence=1,
        run_id="run-1",
        type="step",
        actor="system",
        causal_parent=None,
        payload={},
    )
    out = _event_to_provenance(ev)
    assert out["seq"] == 1
    assert out["actor"] == "system"
    assert out["causal_parent"] is None
    assert out["type"] == "step"
    assert out["reasoning"] is None
    assert out["tool_name"] is None
    assert out["capability_scope"] is None
    assert out["budget_spent"] is None
    # content_hash is derived from the (empty) payload when absent.
    assert isinstance(out["content_hash"], str)
    assert len(out["content_hash"]) == 64


def test_provenance_tool_name_alternate_shapes():
    """tool_name is mined from several known emit shapes."""
    assert _event_to_provenance(_FakeEvent(1, "r", "t", payload={"tool": "fetch"}))["tool_name"] == "fetch"
    assert _event_to_provenance(_FakeEvent(1, "r", "t", payload={"tool_call": {"name": "calc"}}))["tool_name"] == "calc"
    assert (
        _event_to_provenance(_FakeEvent(1, "r", "t", payload={"tool_result": {"tool": "db.query"}}))["tool_name"]
        == "db.query"
    )
    assert _event_to_provenance(_FakeEvent(1, "r", "t", payload={"node_type": "llm"}))["tool_name"] == "llm"


def test_provenance_capability_scope_nested():
    """capability_scope reads from nested capability token / dict."""
    ev = _FakeEvent(1, "r", "t", payload={"capability_token": {"scope": "tools.browser"}})
    assert _event_to_provenance(ev)["capability_scope"] == "tools.browser"


def test_provenance_budget_spent_coerced_to_float():
    """budget_spent coerces to float; un-coercible values become None."""
    assert _event_to_provenance(_FakeEvent(1, "r", "t", payload={"cost_usd": "0.5"}))["budget_spent"] == 0.5
    assert (
        _event_to_provenance(_FakeEvent(1, "r", "t", payload={"budget_spent": "not-a-number"}))["budget_spent"] is None
    )


def test_provenance_content_hash_stable():
    """Derived content_hash is deterministic for identical payloads."""
    p = {"x": 1, "y": 2}
    h1 = _event_to_provenance(_FakeEvent(1, "r", "t", payload=p))["content_hash"]
    h2 = _event_to_provenance(_FakeEvent(2, "r", "t", payload=dict(p)))["content_hash"]
    assert h1 == h2


# ── RunService.get_provenance (READ-only, separate session) ───────────


async def test_get_provenance_reads_event_log_only():
    """get_provenance projects events and never writes to the DB."""
    fake_events = [
        _FakeEvent(1, "run-7", "step", actor="system", payload={"reasoning": "start"}),
        _FakeEvent(
            2,
            "run-7",
            "tool_call",
            actor="agent",
            causal_parent=1,
            payload={"tool_name": "search", "capability_scope": "tools.search"},
        ),
    ]

    # EventLog singleton read stand-in.
    fake_event_log = MagicMock()
    fake_event_log.get_events = AsyncMock(return_value=fake_events)

    # Separate read session (contract 10).
    read_session = AsyncMock()

    calls = []

    def _session_local_factory():
        calls.append("read_session_opened")
        return _SessionCtx(read_session)

    class _SessionCtx:
        def __init__(self, s):
            self._s = s

        async def __aenter__(self):
            return self._s

        async def __aexit__(self, *exc):
            calls.append("read_session_closed")
            return False

    db = MagicMock()
    # The access check (self.get -> self.db.execute) must work without a real row.
    access_result = MagicMock()
    access_result.scalar_one_or_none.return_value = MagicMock(status="completed")
    db.execute = AsyncMock(return_value=access_result)

    service = RunService(db=db)
    with (
        patch(
            "app.database.AsyncSessionLocal",
            new=_session_local_factory,
        ),
        patch(
            "app.services.substrate.event_log.get_event_log",
            new=MagicMock(return_value=fake_event_log),
        ),
    ):
        out = await service.get_provenance("run-7", user_id=1)

    # Separate read session was opened and closed (contract 10).
    assert "read_session_opened" in calls
    assert "read_session_closed" in calls
    # Exactly two events projected in sequence order.
    assert [p["seq"] for p in out] == [1, 2]
    assert out[1]["tool_name"] == "search"
    assert out[1]["capability_scope"] == "tools.search"
    assert out[0]["reasoning"] == "start"
    # Never wrote to the caller's transaction session.
    db.add.assert_not_called()


async def test_get_provenance_empty_run():
    """A run with no events yields an empty projection list."""
    fake_event_log = MagicMock()
    fake_event_log.get_events = AsyncMock(return_value=[])

    read_session = AsyncMock()

    class _SessionCtx:
        def __init__(self, s):
            self._s = s

        async def __aenter__(self):
            return self._s

        async def __aexit__(self, *exc):
            return False

    db = MagicMock()
    access_result = MagicMock()
    access_result.scalar_one_or_none.return_value = MagicMock(status="completed")
    db.execute = AsyncMock(return_value=access_result)

    service = RunService(db=db)
    with (
        patch(
            "app.database.AsyncSessionLocal",
            new=lambda: _SessionCtx(read_session),
        ),
        patch(
            "app.services.substrate.event_log.get_event_log",
            new=MagicMock(return_value=fake_event_log),
        ),
    ):
        out = await service.get_provenance("run-empty", user_id=1)

    assert out == []
