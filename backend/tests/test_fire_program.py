"""TDD tests for MissionProgramService.fire_program (plan §T8).

Covers the real fire_program() implementation: load program, check ACTIVE,
budget pre-check, create Mission + ProgramRun, dispatch to UnifiedExecutor.

Every test is integration-marked because the service uses a real
``AsyncSession`` against PostgreSQL. The executor is MOCKED — no real
LLM calls. Run via::

    cd /opt/flowmanner/backend
    DATABASE_URL="postgresql+asyncpg://flowmanner:REDACTED_DB_PASSWORD@127.0.0.1:5432/flowmanner" \\
      /opt/flowmanner/backend/.venv/bin/python -m pytest tests/test_fire_program.py -v -m integration

Cases:
- (a)  fire_program on ACTIVE creates Mission + ProgramRun + populates
       constraints["_planning_context"] with the program's learning_brief
- (b)  fire_program dispatches to UnifiedExecutor.execute() (mocked)
- (c)  fire_program on PAUSED raises ProgramTransitionConflict
- (d)  fire_program on ARCHIVED raises ProgramTransitionConflict
- (e)  fire_program respects per_run_budget cap (rejects when over)
- (f)  fire_program sets ProgramRun.status from executor result.success
- (g)  fire_program records cost/tokens/duration on the ProgramRun
- (h)  fire_program on executor exception records run.status="failed"
       with outcome_summary
- (i)  fire_program propagates trigger_payload onto the ProgramRun
- (j)  fire_program is forbidden for non-owner non-member
"""

from __future__ import annotations

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
    ProgramStatus,
)
from app.models.user import User  # noqa: E402
from app.models.workspace_models import Workspace  # noqa: E402
from app.schemas.program import ProgramCreate  # noqa: E402
from app.services.mission_program_service import (  # noqa: E402
    MissionProgramService,
    ProgramBudgetExceeded,
    ProgramForbidden,
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
    return f"ws-fire-{uuid.uuid4().hex[:24]}"


async def _make_user(session: AsyncSession, *, suffix: str = "owner") -> User:
    user_id = _new_id()
    user = User(
        id=user_id,
        email=f"fire-svc-{user_id}-{suffix}@test.flowmanner.example",
        username=f"fire_svc_{user_id}_{suffix}",
        full_name=f"Fire SVC Test {user_id} {suffix}",
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
        name=f"fire-ws-{uuid.uuid4().hex[:8]}",
        slug=f"fire-ws-{uuid.uuid4().hex[:12]}",
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


def _make_strategy_result(
    *, success: bool = True, status: str = "completed", **kwargs: Any
):
    """Build a StrategyResult-like object for mocking the executor."""
    from app.services.substrate.workflow_models import StrategyResult

    defaults = {
        "success": success,
        "status": status,
        "data": None,
        "error": None,
        "completed_nodes": [],
        "failed_nodes": [],
        "total_tokens": 100,
        "total_cost_usd": 0.05,
        "execution_time_ms": 1500.0,
        "event_count": 0,
    }
    defaults.update(kwargs)
    return StrategyResult(**defaults)


EXECUTOR_PATH = "app.services.substrate.executor.get_unified_executor"
ADAPTER_PATH = "app.services.substrate.adapters.mission_to_workflow"


# ── (a) fire_program creates Mission + ProgramRun + planning_context ───


async def test_fire_program_creates_mission_and_run(ctx) -> None:
    service = MissionProgramService(ctx["session"])

    # Seed a learning brief on the program before firing.
    payload = ProgramCreate(
        name="Briefed",
        description="",
        mission_type="research",
    )
    program = await service.create(
        user_id=ctx["owner"].id,
        workspace_id=ctx["workspace"].id,
        payload=payload,
    )
    await ctx["session"].commit()
    program.learning_brief = {
        "total_runs": 5,
        "success_rate": 0.6,
        "user_notes": "preserve me",
    }
    await ctx["session"].commit()

    # Mock the executor.
    mock_result = _make_strategy_result(
        success=True, status="completed", total_cost_usd=0.07, total_tokens=150
    )
    with patch(EXECUTOR_PATH) as mock_get_exec:
        mock_exec = MagicMock()
        mock_exec.execute = AsyncMock(return_value=mock_result)
        mock_get_exec.return_value = mock_exec

        with patch(ADAPTER_PATH) as mock_m2w:
            mock_m2w.return_value = MagicMock(id="fake-workflow")

            run = await service.fire_program(
                user_id=ctx["owner"].id,
                program_id=program.id,
                trigger_type="manual",
            )
    await ctx["session"].commit()

    # Mission was created
    assert run.mission_id is not None
    mission = await ctx["session"].get(Mission, run.mission_id)
    assert mission is not None
    assert mission.title == "[Program] Briefed"
    assert mission.user_id == ctx["owner"].id
    assert mission.workspace_id == ctx["workspace"].id
    assert mission.status == "pending"

    # The planning context was injected
    assert mission.constraints is not None
    assert "_planning_context" in mission.constraints
    pc = mission.constraints["_planning_context"]
    assert pc["learning_brief"] == program.learning_brief
    assert pc["learning_brief"]["user_notes"] == "preserve me"

    # The ProgramRun is created and completed
    assert run.program_id == program.id
    assert run.trigger_type == "manual"
    assert run.status == "completed"
    assert run.cost_usd == 0.07
    assert run.tokens_used == 150

    # Executor was called
    assert mock_exec.execute.await_count == 1
    assert mock_m2w.call_count == 1


# ── (b) fire_program dispatches to UnifiedExecutor (via mock) ──────────


async def test_fire_program_dispatches_via_executor(ctx) -> None:
    service = MissionProgramService(ctx["session"])
    payload = ProgramCreate(name="Dispatch", description="")
    program = await service.create(
        user_id=ctx["owner"].id,
        workspace_id=ctx["workspace"].id,
        payload=payload,
    )
    await ctx["session"].commit()

    mock_result = _make_strategy_result()
    with patch(EXECUTOR_PATH) as mock_get_exec, patch(ADAPTER_PATH) as mock_m2w:
        mock_exec = MagicMock()
        mock_exec.execute = AsyncMock(return_value=mock_result)
        mock_get_exec.return_value = mock_exec
        mock_m2w.return_value = MagicMock(id="wf-1")

        await service.fire_program(
            user_id=ctx["owner"].id,
            program_id=program.id,
            trigger_type="cron",
        )
    await ctx["session"].commit()

    # Both adapters were called exactly once
    assert mock_m2w.call_count == 1
    assert mock_exec.execute.await_count == 1
    # mission_to_workflow received a Mission
    m2w_call = mock_m2w.call_args
    assert m2w_call is not None
    # executor received the same session and a workflow
    exec_call = mock_exec.execute.call_args
    assert exec_call is not None


# ── (c) fire_program on PAUSED raises ProgramTransitionConflict ────────


async def test_fire_program_paused_raises_conflict(ctx) -> None:
    service = MissionProgramService(ctx["session"])
    payload = ProgramCreate(name="Paused", description="")
    program = await service.create(
        user_id=ctx["owner"].id,
        workspace_id=ctx["workspace"].id,
        payload=payload,
    )
    await ctx["session"].commit()
    # Pause it.
    from app.schemas.program import ProgramUpdate
    paused = await service.update(
        user_id=ctx["owner"].id,
        program_id=program.id,
        patch=ProgramUpdate(status="paused"),
    )
    await ctx["session"].commit()
    assert paused.status == "paused"

    with pytest.raises(ProgramTransitionConflict):
        await service.fire_program(
            user_id=ctx["owner"].id,
            program_id=program.id,
            trigger_type="manual",
        )


# ── (d) fire_program on ARCHIVED raises ProgramTransitionConflict ───────


async def test_fire_program_archived_raises_conflict(ctx) -> None:
    service = MissionProgramService(ctx["session"])
    payload = ProgramCreate(name="Archived", description="")
    program = await service.create(
        user_id=ctx["owner"].id,
        workspace_id=ctx["workspace"].id,
        payload=payload,
    )
    await ctx["session"].commit()
    await service.archive(user_id=ctx["owner"].id, program_id=program.id)
    await ctx["session"].commit()

    with pytest.raises(ProgramTransitionConflict):
        await service.fire_program(
            user_id=ctx["owner"].id,
            program_id=program.id,
            trigger_type="manual",
        )


# ── (e) fire_program respects per_run_budget cap ───────────────────────


async def test_fire_program_rejects_when_over_budget(ctx) -> None:
    service = MissionProgramService(ctx["session"])
    # Set per_run cap well below the $0.05 default estimate.
    payload = ProgramCreate(name="Tiny budget", description="", per_run_budget_usd=0.01)
    program = await service.create(
        user_id=ctx["owner"].id,
        workspace_id=ctx["workspace"].id,
        payload=payload,
    )
    await ctx["session"].commit()

    with pytest.raises(ProgramBudgetExceeded):
        await service.fire_program(
            user_id=ctx["owner"].id,
            program_id=program.id,
            trigger_type="manual",
        )

    # No Mission or ProgramRun should have been created.
    run_count = (
        await ctx["session"].execute(
            text("SELECT count(*) FROM program_runs WHERE program_id = :pid"),
            {"pid": program.id},
        )
    ).scalar_one()
    assert run_count == 0


# ── (f) fire_program sets ProgramRun.status from executor result ────────


async def test_fire_program_failed_executor_records_failed_run(ctx) -> None:
    service = MissionProgramService(ctx["session"])
    payload = ProgramCreate(name="Failing", description="")
    program = await service.create(
        user_id=ctx["owner"].id,
        workspace_id=ctx["workspace"].id,
        payload=payload,
    )
    await ctx["session"].commit()

    # Executor returns a failed StrategyResult.
    mock_result = _make_strategy_result(
        success=False, status="failed", error="boom", total_cost_usd=0.03, total_tokens=50
    )
    with patch(EXECUTOR_PATH) as mock_get_exec, patch(ADAPTER_PATH) as mock_m2w:
        mock_exec = MagicMock()
        mock_exec.execute = AsyncMock(return_value=mock_result)
        mock_get_exec.return_value = mock_exec
        mock_m2w.return_value = MagicMock(id="wf-2")

        run = await service.fire_program(
            user_id=ctx["owner"].id,
            program_id=program.id,
            trigger_type="manual",
        )
    await ctx["session"].commit()

    assert run.status == "failed"
    assert run.cost_usd == 0.03
    assert run.tokens_used == 50


# ── (g) fire_program records cost/tokens/duration on the ProgramRun ─────


async def test_fire_program_records_outcome_metrics(ctx) -> None:
    service = MissionProgramService(ctx["session"])
    payload = ProgramCreate(name="Measured", description="")
    program = await service.create(
        user_id=ctx["owner"].id,
        workspace_id=ctx["workspace"].id,
        payload=payload,
    )
    await ctx["session"].commit()

    mock_result = _make_strategy_result(
        total_cost_usd=0.123, total_tokens=999, execution_time_ms=4321.0
    )
    with patch(EXECUTOR_PATH) as mock_get_exec, patch(ADAPTER_PATH) as mock_m2w:
        mock_exec = MagicMock()
        mock_exec.execute = AsyncMock(return_value=mock_result)
        mock_get_exec.return_value = mock_exec
        mock_m2w.return_value = MagicMock(id="wf-3")

        run = await service.fire_program(
            user_id=ctx["owner"].id,
            program_id=program.id,
            trigger_type="cron",
        )
    await ctx["session"].commit()

    assert run.cost_usd == 0.123
    assert run.tokens_used == 999
    # duration_seconds computed from execution_time_ms / 1000 (or 0.0 fallback)
    assert run.duration_seconds is not None
    assert run.duration_seconds > 0.0


# ── (h) fire_program records run.status="failed" on executor exception ─


async def test_fire_program_records_failed_on_executor_exception(ctx) -> None:
    service = MissionProgramService(ctx["session"])
    payload = ProgramCreate(name="Exception", description="")
    program = await service.create(
        user_id=ctx["owner"].id,
        workspace_id=ctx["workspace"].id,
        payload=payload,
    )
    await ctx["session"].commit()

    with patch(EXECUTOR_PATH) as mock_get_exec, patch(ADAPTER_PATH) as mock_m2w:
        mock_exec = MagicMock()
        mock_exec.execute = AsyncMock(side_effect=RuntimeError("kaboom"))
        mock_get_exec.return_value = mock_exec
        mock_m2w.return_value = MagicMock(id="wf-4")

        run = await service.fire_program(
            user_id=ctx["owner"].id,
            program_id=program.id,
            trigger_type="manual",
        )
    await ctx["session"].commit()

    assert run.status == "failed"
    assert run.outcome_summary is not None
    assert "kaboom" in run.outcome_summary or "RuntimeError" in run.outcome_summary


# ── (i) fire_program propagates trigger_payload onto the ProgramRun ─────


async def test_fire_program_propagates_trigger_payload(ctx) -> None:
    service = MissionProgramService(ctx["session"])
    payload = ProgramCreate(name="With payload", description="")
    program = await service.create(
        user_id=ctx["owner"].id,
        workspace_id=ctx["workspace"].id,
        payload=payload,
    )
    await ctx["session"].commit()

    trigger_payload = {"source": "cron", "scheduled_at": "2026-06-14T00:00:00Z"}
    mock_result = _make_strategy_result()
    with patch(EXECUTOR_PATH) as mock_get_exec, patch(ADAPTER_PATH) as mock_m2w:
        mock_exec = MagicMock()
        mock_exec.execute = AsyncMock(return_value=mock_result)
        mock_get_exec.return_value = mock_exec
        mock_m2w.return_value = MagicMock(id="wf-5")

        run = await service.fire_program(
            user_id=ctx["owner"].id,
            program_id=program.id,
            trigger_type="cron",
            trigger_payload=trigger_payload,
        )
    await ctx["session"].commit()

    assert run.trigger_type == "cron"
    assert run.trigger_payload == trigger_payload


# ── (j) fire_program is forbidden for non-owner non-member ──────────────


async def test_fire_program_forbidden_for_outsider(ctx) -> None:
    service = MissionProgramService(ctx["session"])
    payload = ProgramCreate(name="Owner-only fire", description="")
    program = await service.create(
        user_id=ctx["owner"].id,
        workspace_id=ctx["workspace"].id,
        payload=payload,
    )
    await ctx["session"].commit()

    async with TestSessionLocal() as s2:
        outsider = await _make_user(s2, suffix="outsider")
        await s2.commit()
        outsider_id = outsider.id

    try:
        async with TestSessionLocal() as s2:
            service2 = MissionProgramService(s2)
            with pytest.raises(ProgramForbidden):
                await service2.fire_program(
                    user_id=outsider_id,
                    program_id=program.id,
                    trigger_type="manual",
                )
    finally:
        async with TestSessionLocal() as s3:
            await s3.execute(
                text("DELETE FROM users WHERE id = :uid"), {"uid": outsider_id}
            )
            await s3.commit()
