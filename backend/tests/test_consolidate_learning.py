"""TDD tests for MissionProgramService.consolidate_learning (plan §T9).

Covers the real consolidate_learning() implementation: load program,
reject archived, query last N terminal runs, fetch episode summaries,
call BudgetEnforcer for LLM synthesis, merge structured fields WITHOUT
overwriting user_notes, persist.

Every test is integration-marked because the service uses a real
``AsyncSession`` against PostgreSQL. The LLM call is MOCKED — no real
LLM hits — and ``EpisodicMemoryService.get_episodes_for_mission`` is
also mocked. Run via::

    cd /opt/flowmanner/backend
    DATABASE_URL="postgresql+asyncpg://flowmanner:REDACTED_DB_PASSWORD@127.0.0.1:5432/flowmanner" \\
      /opt/flowmanner/backend/.venv/bin/python -m pytest tests/test_consolidate_learning.py -v -m integration

Cases:
- (a) zero terminal runs → consolidated_runs=0, no exception
- (b) user_notes are preserved across consolidation (LLM result is
      merged in but user_notes stays intact)
- (c) RUNNING runs are excluded — only terminal runs are counted
- (d) consolidate on ARCHIVED program raises ProgramTransitionConflict
- (e) the LLM call goes through BudgetEnforcer.call (mocked) with a
      prompt that contains "total_runs" and the run summaries
"""

from __future__ import annotations

import json
import os
import uuid
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

# Ensure DATABASE_URL is set BEFORE importing app modules.
os.environ.setdefault(
    "DATABASE_URL",
    "postgresql+asyncpg://flowmanner:REDACTED_DB_PASSWORD@127.0.0.1:5432/flowmanner",
)

# Late imports so env var is honored.
from app.models.mission_models import Mission  # noqa: E402
from app.models.mission_program_models import (  # noqa: E402
    MissionProgram,
    ProgramRun,
)
from app.models.user import User  # noqa: E402
from app.models.workspace_models import Workspace  # noqa: E402
from app.schemas.program import ProgramCreate  # noqa: E402
from app.services.mission_program_service import (  # noqa: E402
    MissionProgramService,
    ProgramTransitionConflict,
)

pytestmark = pytest.mark.integration

# ── Engine + session factory (session-scoped) ────────────────────────────

_TEST_DATABASE_URL = os.environ["DATABASE_URL"]
if "@postgres:" in _TEST_DATABASE_URL:
    _TEST_DATABASE_URL = _TEST_DATABASE_URL.replace("@postgres:", "@127.0.0.1:")
_test_engine = create_async_engine(_TEST_DATABASE_URL, echo=False, poolclass=NullPool)
TestSessionLocal = async_sessionmaker(_test_engine, class_=AsyncSession, expire_on_commit=False)


@pytest_asyncio.fixture(scope="session", autouse=True)
async def _manage_engine():
    yield
    await _test_engine.dispose()


@pytest_asyncio.fixture(scope="session", autouse=True)
async def _skip_if_no_db():
    async with TestSessionLocal() as s:
        try:
            await s.execute(text("SELECT 1"))
        except Exception as e:
            pytest.skip(f"Database not reachable: {e}")


# ── Test-data factories ────────────────────────────────────────────────


def _new_id() -> int:
    return uuid.uuid4().int % 900_000_000 + 100_000


def _new_workspace_id() -> str:
    return f"ws-cons-{uuid.uuid4().hex[:24]}"


async def _make_user(session: AsyncSession, *, suffix: str = "owner") -> User:
    user_id = _new_id()
    user = User(
        id=user_id,
        email=f"cons-svc-{user_id}-{suffix}@test.flowmanner.example",
        username=f"cons_svc_{user_id}_{suffix}",
        full_name=f"Cons SVC Test {user_id} {suffix}",
        hashed_password="test-hash-not-real",
        is_active=True,
        is_admin=False,
        role="free",
    )
    session.add(user)
    await session.flush()
    return user


async def _make_workspace(session: AsyncSession, *, owner_id: int) -> Workspace:
    ws = Workspace(
        id=_new_workspace_id(),
        name=f"cons-ws-{uuid.uuid4().hex[:8]}",
        slug=f"cons-ws-{uuid.uuid4().hex[:12]}",
        owner_id=owner_id,
        plan="free",
        is_active=True,
    )
    session.add(ws)
    await session.flush()
    return ws


# ── Per-test fixture ───────────────────────────────────────────────────


@pytest_asyncio.fixture
async def ctx():
    """Yield a clean test context: session, owner User, Workspace."""
    async with TestSessionLocal() as session:
        owner = await _make_user(session)
        ws = await _make_workspace(session, owner_id=owner.id)
        await session.commit()

        ctx_dict = {"session": session, "owner": owner, "workspace": ws}
        try:
            yield ctx_dict
        finally:
            try:
                async with TestSessionLocal() as cleanup:
                    # substrate_events is append-only; disable the trigger for cleanup.
                    await cleanup.execute(
                        text(
                            "ALTER TABLE substrate_events "
                            "DISABLE TRIGGER trg_substrate_events_append_only"
                        )
                    )
                    await cleanup.execute(
                        text("DELETE FROM program_runs WHERE program_id IN "
                             "(SELECT id FROM mission_programs WHERE user_id = :uid)"),
                        {"uid": owner.id},
                    )
                    await cleanup.execute(
                        text("DELETE FROM mission_programs WHERE user_id = :uid"),
                        {"uid": owner.id},
                    )
                    await cleanup.execute(
                        text("DELETE FROM missions WHERE user_id = :uid"),
                        {"uid": owner.id},
                    )
                    await cleanup.execute(
                        text("DELETE FROM workspace_members WHERE user_id = :uid"),
                        {"uid": owner.id},
                    )
                    await cleanup.execute(
                        text("DELETE FROM workspaces WHERE owner_id = :uid"),
                        {"uid": owner.id},
                    )
                    await cleanup.execute(
                        text("DELETE FROM users WHERE id = :uid"),
                        {"uid": owner.id},
                    )
                    await cleanup.execute(
                        text(
                            "ALTER TABLE substrate_events "
                            "ENABLE TRIGGER trg_substrate_events_append_only"
                        )
                    )
                    await cleanup.commit()
            except Exception:
                try:
                    async with TestSessionLocal() as s2:
                        await s2.execute(
                            text(
                                "ALTER TABLE substrate_events "
                                "ENABLE TRIGGER trg_substrate_events_append_only"
                            )
                        )
                        await s2.commit()
                except Exception:
                    pass


# ── Helpers: mocks + run seeding ───────────────────────────────────────


def _make_memory_mock() -> MagicMock:
    """Build a stand-in for EpisodicMemoryService singleton.

    ``get_episodes_for_mission`` is an AsyncMock returning an empty list
    by default (each test can configure it to return more).
    """
    m = MagicMock()
    m.get_episodes_for_mission = AsyncMock(return_value=[])
    return m


def _make_enforcer_mock(*, response_content: str = "{}") -> MagicMock:
    """Build a stand-in for BudgetEnforcer singleton.

    ``call`` is an AsyncMock returning a dict with a ``content`` key.
    """
    e = MagicMock()
    e.call = AsyncMock(
        return_value={"content": response_content, "success": True}
    )
    return e


async def _seed_run(
    session: AsyncSession,
    *,
    program_id: uuid.UUID,
    mission_owner_id: int,
    workspace_id: str,
    status: str,
    cost_usd: float = 0.05,
) -> ProgramRun:
    """Insert a ProgramRun (and a real Mission row to satisfy the FK)."""
    mission_id = uuid.uuid4()
    mission = Mission(
        id=mission_id,
        title="cons-placeholder",
        description="",
        user_id=mission_owner_id,
        workspace_id=workspace_id,
        status=status,
    )
    session.add(mission)
    await session.flush()
    run = ProgramRun(
        program_id=program_id,
        mission_id=mission_id,
        trigger_type="manual",
        status=status,
        cost_usd=cost_usd,
    )
    session.add(run)
    await session.flush()
    return run


# ── (a) zero terminal runs → noop ──────────────────────────────────────


async def test_zero_runs_returns_noop(ctx) -> None:
    """No terminal runs → consolidated_runs=0, no LLM call, no error."""
    service = MissionProgramService(ctx["session"])
    payload = ProgramCreate(name="Empty", description="")
    program = await service.create(
        user_id=ctx["owner"].id,
        workspace_id=ctx["workspace"].id,
        payload=payload,
    )
    await ctx["session"].commit()

    memory_mock = _make_memory_mock()
    enforcer_mock = _make_enforcer_mock()

    with patch(
        "app.services.episodic_memory_service.get_episodic_memory_service",
        return_value=memory_mock,
    ), patch(
        "app.services.budget_enforcer.get_budget_enforcer",
        return_value=enforcer_mock,
    ):
        response = await service.consolidate_learning(
            user_id=ctx["owner"].id, program_id=program.id
        )

    assert response.consolidated_runs == 0
    # LLM MUST NOT be called when there are no terminal runs.
    enforcer_mock.call.assert_not_called()
    # Existing brief is returned as-is (defaults for an empty program).
    assert response.brief.total_runs == 0
    assert response.duration_ms >= 0


# ── (b) user_notes are preserved across consolidation ─────────────────


async def test_user_notes_preserved_across_consolidation(ctx) -> None:
    """Set user_notes; mock LLM to return other structured fields; verify
    user_notes survives the merge and the LLM-returned fields are present.
    """
    service = MissionProgramService(ctx["session"])
    payload = ProgramCreate(name="With-notes", description="")
    program = await service.create(
        user_id=ctx["owner"].id,
        workspace_id=ctx["workspace"].id,
        payload=payload,
    )
    await ctx["session"].commit()

    # Seed an initial brief with user_notes + a structured field that the
    # LLM is going to overwrite. The structured field should change;
    # user_notes should NOT.
    program.learning_brief = {
        "total_runs": 1,
        "success_rate": 0.5,
        "common_failures": [],
        "effective_tools": ["old_tool"],
        "ineffective_tools": [],
        "hitl_history": [],
        "plan_adjustments": "",
        "last_consolidated_at": None,
        "user_notes": "ALWAYS avoid Mondays — high load",
    }
    await ctx["session"].commit()

    # Seed 1 terminal run so we exercise the LLM path.
    await _seed_run(
        ctx["session"],
        program_id=program.id,
        mission_owner_id=ctx["owner"].id,
        workspace_id=ctx["workspace"].id,
        status="completed",
        cost_usd=0.10,
    )
    await ctx["session"].commit()

    # LLM returns structured fields + an attempted overwrite of user_notes.
    # The service MUST ignore the LLM's user_notes and keep the existing one.
    llm_payload = {
        "total_runs": 2,
        "success_rate": 0.95,
        "effective_tools": ["new_tool"],
        "plan_adjustments": "Tuesdays are great",
        "user_notes": "LLM attempted to overwrite — must be ignored",
    }
    enforcer_mock = _make_enforcer_mock(
        response_content=json.dumps(llm_payload)
    )
    memory_mock = _make_memory_mock()

    with patch(
        "app.services.episodic_memory_service.get_episodic_memory_service",
        return_value=memory_mock,
    ), patch(
        "app.services.budget_enforcer.get_budget_enforcer",
        return_value=enforcer_mock,
    ):
        response = await service.consolidate_learning(
            user_id=ctx["owner"].id, program_id=program.id
        )

    # LLM-returned structured fields make it into the brief.
    assert response.brief.user_notes == "ALWAYS avoid Mondays — high load"
    assert response.brief.effective_tools == ["new_tool"]
    assert response.brief.success_rate == 0.95
    assert response.brief.plan_adjustments == "Tuesdays are great"
    assert response.brief.last_consolidated_at is not None
    assert response.consolidated_runs == 1
    # Persisted in DB (not just returned) — re-read.
    await ctx["session"].refresh(program)
    assert program.learning_brief["user_notes"] == "ALWAYS avoid Mondays — high load"
    assert program.learning_brief["effective_tools"] == ["new_tool"]


# ── (c) RUNNING runs are excluded from the count ────────────────────────


async def test_running_runs_excluded(ctx) -> None:
    """2 COMPLETED + 1 RUNNING → consolidated_runs == 2, not 3."""
    service = MissionProgramService(ctx["session"])
    payload = ProgramCreate(name="Mixed-status", description="")
    program = await service.create(
        user_id=ctx["owner"].id,
        workspace_id=ctx["workspace"].id,
        payload=payload,
    )
    await ctx["session"].commit()

    # 2 terminal + 1 in-flight.
    await _seed_run(
        ctx["session"],
        program_id=program.id,
        mission_owner_id=ctx["owner"].id,
        workspace_id=ctx["workspace"].id,
        status="completed",
    )
    await _seed_run(
        ctx["session"],
        program_id=program.id,
        mission_owner_id=ctx["owner"].id,
        workspace_id=ctx["workspace"].id,
        status="failed",
    )
    await _seed_run(
        ctx["session"],
        program_id=program.id,
        mission_owner_id=ctx["owner"].id,
        workspace_id=ctx["workspace"].id,
        status="running",
    )
    await ctx["session"].commit()

    enforcer_mock = _make_enforcer_mock(
        response_content=json.dumps({"total_runs": 99})
    )
    memory_mock = _make_memory_mock()

    with patch(
        "app.services.episodic_memory_service.get_episodic_memory_service",
        return_value=memory_mock,
    ), patch(
        "app.services.budget_enforcer.get_budget_enforcer",
        return_value=enforcer_mock,
    ):
        response = await service.consolidate_learning(
            user_id=ctx["owner"].id, program_id=program.id
        )

    # Only the 2 terminal runs are counted.
    assert response.consolidated_runs == 2


# ── (d) ARCHIVED programs raise ProgramTransitionConflict ──────────────


async def test_archived_program_raises_conflict(ctx) -> None:
    """Set status='archived' and call consolidate → ProgramTransitionConflict."""
    service = MissionProgramService(ctx["session"])
    payload = ProgramCreate(name="To-archive-for-cons", description="")
    program = await service.create(
        user_id=ctx["owner"].id,
        workspace_id=ctx["workspace"].id,
        payload=payload,
    )
    await ctx["session"].commit()

    # Archive directly (bypassing the in-flight guard since we have no runs).
    program.status = "archived"
    await ctx["session"].commit()

    with pytest.raises(ProgramTransitionConflict):
        await service.consolidate_learning(
            user_id=ctx["owner"].id, program_id=program.id
        )


# ── (e) LLM call goes through BudgetEnforcer with the right prompt ─────


async def test_llm_call_uses_budget_enforcer(ctx) -> None:
    """Verify the LLM call is dispatched via BudgetEnforcer.call() and the
    prompt contains the 'total_runs' field name and the run summaries.
    """
    service = MissionProgramService(ctx["session"])
    payload = ProgramCreate(name="LLM-call-check", description="")
    program = await service.create(
        user_id=ctx["owner"].id,
        workspace_id=ctx["workspace"].id,
        payload=payload,
    )
    await ctx["session"].commit()

    # Seed 2 completed runs so the LLM call actually happens.
    await _seed_run(
        ctx["session"],
        program_id=program.id,
        mission_owner_id=ctx["owner"].id,
        workspace_id=ctx["workspace"].id,
        status="completed",
    )
    await _seed_run(
        ctx["session"],
        program_id=program.id,
        mission_owner_id=ctx["owner"].id,
        workspace_id=ctx["workspace"].id,
        status="failed",
    )
    await ctx["session"].commit()

    enforcer_mock = _make_enforcer_mock(
        response_content=json.dumps(
            {
                "total_runs": 2,
                "success_rate": 0.5,
                "common_failures": [],
                "effective_tools": ["a"],
                "ineffective_tools": ["b"],
                "hitl_history": [],
                "plan_adjustments": "ok",
            }
        )
    )
    memory_mock = _make_memory_mock()

    with patch(
        "app.services.episodic_memory_service.get_episodic_memory_service",
        return_value=memory_mock,
    ), patch(
        "app.services.budget_enforcer.get_budget_enforcer",
        return_value=enforcer_mock,
    ):
        response = await service.consolidate_learning(
            user_id=ctx["owner"].id, program_id=program.id
        )

    # BudgetEnforcer.call was invoked exactly once.
    assert enforcer_mock.call.await_count == 1
    # The call used the expected model.
    kwargs = enforcer_mock.call.await_kwargs
    assert kwargs["model_id"] == "claude-sonnet-4"
    # The prompt mentions "total_runs" (schema field the LLM should return).
    messages = kwargs["messages"]
    prompt_text = messages[0]["content"]
    assert "total_runs" in prompt_text
    # The prompt also includes serialized run summaries (look for the
    # run_id UUIDs we just seeded — they appear in the JSON dump).
    assert "run_id" in prompt_text
    # Response reflects the LLM's output.
    assert response.brief.effective_tools == ["a"]
    assert response.brief.ineffective_tools == ["b"]
