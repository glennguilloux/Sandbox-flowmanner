"""Tests for the background review service + Celery task.

Eight focused tests covering the v1 contract:

1. ``compute_write_approval`` — solo + multi-member + age thresholds
2. ``parse_reviewer_response`` — accepts both bare list and envelope
3. ``_validate_proposed_write`` — tool whitelist enforcement
4. ``apply_proposed_writes`` — write_approval=false → direct
5. ``apply_proposed_writes`` — write_approval=true → staged
6. ``apply_proposed_writes`` — destructive writes always stage
7. ``review_mission`` skip rules — duration<10s and turns<3
8. ``review_mission`` swallows LLM errors (best-effort semantics)

Run:
    docker compose exec backend pytest app/tests/test_background_review.py -v
"""

from __future__ import annotations

import asyncio
import json
import sys
import uuid
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# Make sure ``app.tasks.background_review_tasks`` is importable when
# tests run outside the backend container.
sys.path.insert(0, "/opt/flowmanner/backend")

from app.services.memory.background_review_prompt import (
    REVIEWER_TOOL_WHITELIST,
)
from app.services.memory.background_review_service import (
    ALL_PENDING_WRITE_ACTIONS,
    ApplyResult,
    BackgroundReviewService,
    PendingWriteAction,
    ProposedWrite,
    compute_write_approval,
    get_background_review_service,
)

# ── 1. compute_write_approval — the workspace policy function ────────────


def _workspace(members: int = 1, created_at: datetime | None = None) -> SimpleNamespace:
    """Build a minimal Workspace-like namespace for ``compute_write_approval``."""
    rel_members = [SimpleNamespace(id=i) for i in range(members)]
    return SimpleNamespace(
        id="ws-1",
        members=rel_members,
        member_count=members,
        created_at=created_at,
    )


def test_compute_write_approval_solo_workspace_is_false():
    """A 1-member workspace never requires approval."""
    ws = _workspace(members=1)
    assert compute_write_approval(ws) is False


def test_compute_write_approval_new_multi_member_is_false():
    """A multi-member workspace newer than 30 days → no approval."""
    ws = _workspace(members=3, created_at=datetime.now(UTC) - timedelta(days=10))
    assert compute_write_approval(ws) is False


def test_compute_write_approval_old_multi_member_is_true():
    """A multi-member workspace older than 30 days → approval required."""
    ws = _workspace(members=3, created_at=datetime.now(UTC) - timedelta(days=45))
    assert compute_write_approval(ws) is True


def test_compute_write_approval_none_is_true():
    """When the workspace is unknown, force approval (fail-closed)."""
    assert compute_write_approval(None) is True


# ── 2. parse_reviewer_response — JSON shape tolerance ────────────────────


def test_parse_reviewer_response_accepts_envelope_with_proposed_writes():
    """The standard ``{"proposed_writes": [...]}`` envelope is parsed."""
    service = BackgroundReviewService()
    raw = json.dumps(
        {
            "reasoning": "user prefers verbose output",
            "proposed_writes": [
                {
                    "action": "memory_add",
                    "content": "User prefers verbose output from agents.",
                    "importance": 0.7,
                    "memory_type": "preference",
                    "scope": "agent",
                }
            ],
        }
    )
    out = service.parse_reviewer_response(raw)
    assert len(out) == 1
    assert out[0].action == PendingWriteAction.ADD
    assert "verbose" in out[0].content


def test_parse_reviewer_response_accepts_bare_list():
    """A bare list at the top level is also accepted."""
    service = BackgroundReviewService()
    raw = json.dumps(
        [
            {
                "action": "memory_add",
                "content": "User has a strong preference for short answers.",
                "importance": 0.6,
            }
        ]
    )
    out = service.parse_reviewer_response(raw)
    assert len(out) == 1
    assert out[0].action == "add"  # mapped to DB action


def test_parse_reviewer_response_returns_empty_on_garbage():
    """Non-JSON or unparseable content yields no proposed writes."""
    service = BackgroundReviewService()
    assert service.parse_reviewer_response("") == []
    assert service.parse_reviewer_response("hello world, no JSON here") == []
    # A JSON value that's not an object/list also yields [].
    assert service.parse_reviewer_response("42") == []


# ── 3. Tool whitelist enforcement ─────────────────────────────────────────


def test_validate_proposed_write_rejects_non_whitelisted_action():
    """An action outside the whitelist is dropped silently."""
    service = BackgroundReviewService()
    item = {
        "action": "execute_code",  # not in REVIEWER_TOOL_WHITELIST
        "content": "rm -rf /",
    }
    assert service._validate_proposed_write(item, "") is None


def test_validate_proposed_write_accepts_whitelisted_action():
    """A whitelisted action with valid content is accepted."""
    service = BackgroundReviewService()
    item = {
        "action": "memory_add",
        "content": "The agent should always check the connection pool before launching a swarm.",
        "importance": 0.5,
        "memory_type": "semantic",
        "scope": "agent",
    }
    validated = service._validate_proposed_write(item, "")
    assert validated is not None
    assert validated.action == PendingWriteAction.ADD


def test_whitelist_contains_only_memory_actions():
    """The whitelist is the three memory tools plus the two Q3 skill tools.

    Defence-in-depth: every reviewer action must be enumerated here. Q3-B
    adds ``skill_create`` / ``skill_patch`` so the reviewer can emit reusable
    procedures into the dedicated ``skills`` table.
    """
    assert (
        frozenset(
            {
                "memory_add",
                "memory_replace",
                "memory_remove",
                "skill_create",
                "skill_patch",
            }
        )
        == REVIEWER_TOOL_WHITELIST
    )


# ── 4. apply_proposed_writes — direct vs staged ──────────────────────────


def _make_db_session(rows_to_return: list | None = None) -> AsyncMock:
    """Build a minimal async DB session mock."""
    session = AsyncMock()
    execute_mock = AsyncMock()
    execute_mock.return_value = MagicMock()
    session.execute = execute_mock
    session.commit = AsyncMock()
    session.rollback = AsyncMock()
    session.flush = AsyncMock()
    return session


@pytest.mark.asyncio
async def test_apply_proposed_writes_direct_when_no_approval():
    """write_approval=False on a non-destructive write → direct insert."""
    service = BackgroundReviewService()
    db = _make_db_session()

    proposed = [
        ProposedWrite(
            action=PendingWriteAction.ADD,
            content="The deploy script requires --migrate after touching app/models.",
            importance=0.7,
            memory_type="semantic",
        )
    ]
    result = await service.apply_proposed_writes(
        db,
        workspace_id="ws-1",
        user_id=1,
        agent_id="agent-1",
        source_mission_id=str(uuid.uuid4()),
        proposed=proposed,
        write_approval=False,
    )
    assert len(result.direct_writes) == 1
    assert result.staged_writes == []
    assert result.skipped == []
    db.flush.assert_awaited()


@pytest.mark.asyncio
async def test_apply_proposed_writes_staged_when_approval_required():
    """write_approval=True on an additive write → staged in pending_writes."""
    service = BackgroundReviewService()
    db = _make_db_session()

    proposed = [
        ProposedWrite(
            action=PendingWriteAction.ADD,
            content="The team prefers TDD for new modules.",
            importance=0.7,
            memory_type="semantic",
        )
    ]
    result = await service.apply_proposed_writes(
        db,
        workspace_id="ws-1",
        user_id=1,
        agent_id="agent-1",
        source_mission_id=str(uuid.uuid4()),
        proposed=proposed,
        write_approval=True,
    )
    assert result.direct_writes == []
    assert len(result.staged_writes) == 1
    db.flush.assert_awaited()


@pytest.mark.asyncio
async def test_apply_proposed_writes_destructive_always_staged():
    """REPLACE/REMOVE always stage, even when write_approval=False."""
    service = BackgroundReviewService()
    db = _make_db_session()

    proposed = [
        ProposedWrite(
            action=PendingWriteAction.REMOVE,
            content="",
            old_text="Some stale entry to remove",
        )
    ]
    result = await service.apply_proposed_writes(
        db,
        workspace_id="ws-1",
        user_id=1,
        agent_id="agent-1",
        source_mission_id=str(uuid.uuid4()),
        proposed=proposed,
        write_approval=False,  # even without approval
    )
    assert result.direct_writes == []
    assert len(result.staged_writes) == 1


# ── 5. ProposedWrite.is_destructive ───────────────────────────────────────


def test_proposed_write_is_destructive_for_replace_and_remove():
    """REPLACE and REMOVE are always destructive per the user decision."""
    assert ProposedWrite(action="add", content="x").is_destructive() is False
    assert ProposedWrite(action="replace", content="x").is_destructive() is True
    assert ProposedWrite(action="remove", content="").is_destructive() is True


# ── 6. Skip rules — short missions and tiny turn counts ──────────────────


def test_min_mission_thresholds_match_plan():
    """The Celery task's skip thresholds must match the plan (<10s, <3 turns)."""
    from app.tasks.background_review_tasks import (
        MIN_MISSION_DURATION_SECONDS,
        MIN_MISSION_TURN_COUNT,
    )

    assert MIN_MISSION_DURATION_SECONDS == 10.0
    assert MIN_MISSION_TURN_COUNT == 3


# ── 7. review_mission best-effort semantics ──────────────────────────────


def test_review_mission_swallows_caller_exceptions():
    """The sync wrapper must never propagate exceptions from the async body.

    We patch the async body to raise; the wrapper must catch and return
    a summary with ``outcome='error'``.

    This test is sync on purpose: production Celery workers invoke
    ``review_mission`` from a worker thread with no running event loop,
    so ``asyncio.run`` works. Running this inside a pytest-asyncio loop
    would raise before we ever reach the patched async body, masking the
    real best-effort behavior we want to verify.
    """
    from app.tasks import background_review_tasks

    with patch.object(
        background_review_tasks,
        "_review_mission_async",
        side_effect=RuntimeError("boom"),
    ):
        # Direct call bypasses Celery dispatch — exercises the wrapper.
        result = background_review_tasks.review_mission("mission-1")
    assert result["outcome"] == "error"
    assert "boom" in result["error"]
    assert "duration_ms" in result


# ── 8. Singleton accessor ─────────────────────────────────────────────────


def test_get_background_review_service_returns_singleton():
    """``get_background_review_service`` returns a stable instance."""
    s1 = get_background_review_service()
    s2 = get_background_review_service()
    assert s1 is s2
    assert isinstance(s1, BackgroundReviewService)


# ── Helpers ───────────────────────────────────────────────────────────────


def test_apply_result_total_writes_counts_both_paths():
    """``ApplyResult.total_writes`` is the union of direct + staged."""
    r = ApplyResult()
    assert r.total_writes == 0
    r.direct_writes.append("a")
    r.staged_writes.append("b")
    r.staged_writes.append("c")
    assert r.total_writes == 3


# ── 9. GOV-1.7 reviewer reliability ──────────────────────────────────────


def _make_service_with_client(client):
    """Return a BackgroundReviewService whose httpx/post path is driven by
    ``client`` (an async-context-manager exposing ``post``)."""
    from app.services.memory import background_review_service as brs

    service = BackgroundReviewService()
    patches = (
        patch(
            "app.services.langgraph.llm_config.get_llm_manager",
            return_value=MagicMock(get_model=lambda m: MagicMock()),
        ),
        patch("app.services.langgraph.llm_config.get_llamacpp_base_url", return_value="http://x"),
        patch("httpx.AsyncClient", return_value=client),
        patch("asyncio.sleep", return_value=None),
    )
    for p in patches:
        p.start()
    return service, patches


def _fake_client_raising(exc, succeed_on_call=None):
    """AsyncClient-like that raises ``exc`` on .post until ``succeed_on_call``
    (1-indexed), then returns a 200 JSON body."""
    import httpx

    class _Resp:
        status_code = 200

        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict:
            return {"choices": [{"message": {"content": '{"proposed_writes": []}'}}]}

    class _Client:
        def __init__(self) -> None:
            self._calls = 0

        async def __aenter__(self) -> _Client:
            return self

        async def __aexit__(self, *exc: object) -> None:
            return None

        async def post(self, *args: object, **kwargs: object) -> _Resp:
            self._calls += 1
            if succeed_on_call is not None and self._calls >= succeed_on_call:
                return _Resp()
            raise exc

    return _Client()


def test_call_reviewer_retries_transient_timeout_then_succeeds():
    """TimeoutException on attempt 1+2 is retried; attempt 3 succeeds."""
    import httpx

    from app.services.memory import background_review_service as brs

    client = _fake_client_raising(httpx.TimeoutException("timeout"), succeed_on_call=3)
    service, patches = _make_service_with_client(client)
    try:
        result = asyncio.run(service.call_reviewer(snapshot="s", transcript="t"))
    finally:
        for p in patches:
            p.stop()
    assert result == '{"proposed_writes": []}'
    # 2 timeouts + 1 success == 3 post() calls.
    assert client._calls == 3


def test_call_reviewer_permanent_error_does_not_retry():
    """A non-transient error fails open immediately, no retry loop."""
    from app.services.memory import background_review_service as brs

    client = _fake_client_raising(ValueError("boom"))
    service, patches = _make_service_with_client(client)
    try:
        result = asyncio.run(service.call_reviewer(snapshot="s", transcript="t"))
    finally:
        for p in patches:
            p.stop()
    assert result == ""
    # Permanent error -> exactly one post() attempt, then immediate return "".
    assert client._calls == 1


def test_call_reviewer_retryable_status_exhausts():
    """A 503 (retryable) exhausts REVIEWER_MAX_RETRIES and returns empty."""
    from app.services.memory import background_review_service as brs

    captured = {"calls": 0}

    class _Resp:
        status_code = 503

        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict:  # pragma: no cover - never reached
            return {}

    class _Client:
        async def __aenter__(self) -> _Client:
            return self

        async def __aexit__(self, *exc: object) -> None:
            return None

        async def post(self, *args: object, **kwargs: object) -> _Resp:
            captured["calls"] += 1
            return _Resp()

    service, patches = _make_service_with_client(_Client())
    try:
        result = asyncio.run(service.call_reviewer(snapshot="s", transcript="t"))
    finally:
        for p in patches:
            p.stop()
    assert result == ""
    assert captured["calls"] == brs.REVIEWER_MAX_RETRIES


def test_call_reviewer_non_retryable_status_fail_open_once():
    """A 400 (non-retryable) fails open immediately, single attempt."""
    import httpx

    from app.services.memory import background_review_service as brs

    captured = {"calls": 0}

    class _Resp:
        status_code = 400

        def raise_for_status(self) -> None:
            raise httpx.HTTPStatusError("bad", request=None, response=None)  # type: ignore[arg-type]

        def json(self) -> dict:
            return {}

    class _Client:
        async def __aenter__(self) -> _Client:
            return self

        async def __aexit__(self, *exc: object) -> None:
            return None

        async def post(self, *args: object, **kwargs: object) -> _Resp:
            captured["calls"] += 1
            return _Resp()

    service, patches = _make_service_with_client(_Client())
    try:
        result = asyncio.run(service.call_reviewer(snapshot="s", transcript="t"))
    finally:
        for p in patches:
            p.stop()
    assert result == ""
    assert captured["calls"] == 1


def test_review_gap_recorded_on_reviewer_exception():
    """GOV-1.7: a reviewer exception triggers a durable gap record (best-effort)."""
    import app.tasks.background_review_tasks as tmod

    recorded = {}

    async def _fake_gap(mission_id, workspace, user_id, reason, detail=None):
        recorded.setdefault("reasons", []).append(reason)
        recorded["mission_id"] = mission_id

    service = MagicMock()
    service.call_reviewer = AsyncMock(side_effect=RuntimeError("reviewer down"))

    mission = SimpleNamespace(
        id="m-1",
        workspace_id="ws-1",
        user_id=7,
        agent_id="a-1",
        started_at=datetime.now(UTC) - timedelta(minutes=2),
        completed_at=datetime.now(UTC),
        results={"turns": [1, 2, 3, 4, 5]},
    )

    with (
        patch(
            "app.services.memory.background_review_service.get_background_review_service",
            return_value=service,
        ),
        patch.object(tmod, "_record_review_gap", _fake_gap),
    ):
        service.build_snapshot = AsyncMock(return_value="snap")
        service.build_transcript = AsyncMock(return_value="tr")

        fake_db = MagicMock()
        fake_db.execute = AsyncMock(return_value=SimpleNamespace(scalar_one_or_none=lambda: mission))
        fake_session = MagicMock()
        fake_session.__aenter__ = AsyncMock(return_value=fake_db)
        fake_session.__aexit__ = AsyncMock(return_value=None)
        with patch("app.database.AsyncSessionLocal", return_value=fake_session):
            asyncio.run(tmod._review_mission_async("m-1", {}, None))

    assert recorded.get("mission_id") == "m-1"
    assert "reviewer_exception" in recorded.get("reasons", [])


def test_review_gap_recorded_on_empty_response():
    """GOV-1.7: a fail-open empty reviewer response also records a gap."""
    import app.tasks.background_review_tasks as tmod

    recorded = {}

    async def _fake_gap(mission_id, workspace, user_id, reason, detail=None):
        recorded.setdefault("reasons", []).append(reason)

    service = MagicMock()
    service.call_reviewer = AsyncMock(return_value="")

    mission = SimpleNamespace(
        id="m-2",
        workspace_id="ws-2",
        user_id=9,
        agent_id="a-2",
        started_at=datetime.now(UTC) - timedelta(minutes=2),
        completed_at=datetime.now(UTC),
        results={"turns": [1, 2, 3, 4, 5]},
    )

    with (
        patch(
            "app.services.memory.background_review_service.get_background_review_service",
            return_value=service,
        ),
        patch.object(tmod, "_record_review_gap", _fake_gap),
    ):
        service.build_snapshot = AsyncMock(return_value="snap")
        service.build_transcript = AsyncMock(return_value="tr")

        fake_db = MagicMock()
        fake_db.execute = AsyncMock(return_value=SimpleNamespace(scalar_one_or_none=lambda: mission))
        fake_session = MagicMock()
        fake_session.__aenter__ = AsyncMock(return_value=fake_db)
        fake_session.__aexit__ = AsyncMock(return_value=None)
        with patch("app.database.AsyncSessionLocal", return_value=fake_session):
            asyncio.run(tmod._review_mission_async("m-2", {}, None))

    assert "reviewer_returned_empty" in recorded.get("reasons", [])
