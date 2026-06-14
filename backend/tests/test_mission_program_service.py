"""TDD tests for MissionProgramService (plan §T5).

Covers CRUD + ownership + budget-helper. Every test is integration-marked
because the service uses a real ``AsyncSession`` against PostgreSQL. Run via::

    cd /opt/flowmanner/backend
    DATABASE_URL="postgresql+asyncpg://flowmanner:5f206ab26d543ba5424385cb10200efc@127.0.0.1:5432/flowmanner" \\
      /opt/flowmanner/backend/.venv/bin/python -m pytest tests/test_mission_program_service.py -v -m integration

Cases:
- (a)  create returns program with status="active", learning_brief=None
- (b)  get for non-owner non-member raises ProgramForbidden
- (c)  update on archived program raises ProgramTransitionConflict
- (d)  archive with in-flight run raises ProgramTransitionConflict
- (e)  update_user_notes preserves structured fields (common_failures unchanged)
- (f)  list filters by workspace_id when provided
- (g)  _check_program_budget per_run cap rejects when estimated > cap
- (h)  _check_program_budget monthly cap rejects when projected > cap
- (i)  _check_program_budget both None means no enforcement
- (j)  get raises ProgramNotFound for missing program
- (k)  archive ACTIVE → ARCHIVED succeeds via can_transition_to
- (l)  archive PAUSED → ARCHIVED succeeds (PAUSED can transition to ARCHIVED)
"""

from __future__ import annotations

import os
import uuid
from typing import Any

import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

# Ensure DATABASE_URL is set BEFORE importing app modules.
os.environ.setdefault(
    "DATABASE_URL",
    "postgresql+asyncpg://flowmanner:5f206ab26d543ba5424385cb10200efc@127.0.0.1:5432/flowmanner",
)

# Late imports so env var is honored.
from app.models.mission_models import Mission  # noqa: E402
from app.models.mission_program_models import (  # noqa: E402
    MissionProgram,
    ProgramRun,
)
from app.models.user import User  # noqa: E402
from app.models.workspace_models import Workspace, WorkspaceMember  # noqa: E402
from app.schemas.program import ProgramCreate, ProgramUpdate  # noqa: E402
from app.services.mission_program_service import (  # noqa: E402
    MissionProgramService,
    ProgramBudgetExceeded,
    ProgramError,
    ProgramForbidden,
    ProgramNotFound,
    ProgramTransitionConflict,
)

pytestmark = pytest.mark.integration

# ── Engine + session factory (session-scoped) ────────────────────────────

_TEST_DATABASE_URL = os.environ["DATABASE_URL"]
# Some .env files use the docker hostname `postgres`; for tests on the host
# we need `127.0.0.1`. Only swap if it's still the bare docker hostname.
if "@postgres:" in _TEST_DATABASE_URL:
    _TEST_DATABASE_URL = _TEST_DATABASE_URL.replace("@postgres:", "@127.0.0.1:")
_test_engine = create_async_engine(_TEST_DATABASE_URL, echo=False, poolclass=NullPool)
TestSessionLocal = async_sessionmaker(_test_engine, class_=AsyncSession, expire_on_commit=False)


@pytest_asyncio.fixture(scope="session", autouse=True)
async def _manage_engine():
    """Dispose test engine after the suite finishes."""
    yield
    await _test_engine.dispose()


# ── Per-test DB skip check (cheap, runs once per session) ────────────────


@pytest_asyncio.fixture(scope="session", autouse=True)
async def _skip_if_no_db():
    async with TestSessionLocal() as s:
        try:
            await s.execute(text("SELECT 1"))
        except Exception as e:
            pytest.skip(f"Database not reachable: {e}")


# ── Test-data factory: User + Workspace + optional Member ────────────────


def _new_id() -> int:
    """Unique user ID (unlikely to collide with real users)."""
    return uuid.uuid4().int % 900_000_000 + 100_000


def _new_workspace_id() -> str:
    return f"ws-test-{uuid.uuid4().hex[:24]}"


async def _make_user(session: AsyncSession, *, suffix: str = "owner") -> User:
    user_id = _new_id()
    user = User(
        id=user_id,
        email=f"program-svc-{user_id}-{suffix}@test.flowmanner.example",
        username=f"program_svc_{user_id}_{suffix}",
        full_name=f"Program SVC Test {user_id} {suffix}",
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
        name=f"test-ws-{uuid.uuid4().hex[:8]}",
        slug=f"test-ws-{uuid.uuid4().hex[:12]}",
        owner_id=owner_id,
        plan="free",
        is_active=True,
    )
    session.add(ws)
    await session.flush()
    return ws


async def _make_member(
    session: AsyncSession, *, workspace_id: str, user_id: int
) -> WorkspaceMember:
    member = WorkspaceMember(
        workspace_id=workspace_id,
        user_id=user_id,
        role="member",
        is_active=True,
    )
    session.add(member)
    await session.flush()
    return member


# ── Per-test fixture: fresh session + owner + workspace + cleanup ────────


@pytest_asyncio.fixture
async def ctx():
    """Yield a clean test context: session, owner User, Workspace.

    Cleanup deletes the owner (CASCADE removes memberships + programs +
    runs via FK + ORM cascade).
    """
    async with TestSessionLocal() as session:
        owner = await _make_user(session, suffix="owner")
        ws = await _make_workspace(session, owner_id=owner.id)
        await session.commit()

        ctx_dict = {"session": session, "owner": owner, "workspace": ws}
        try:
            yield ctx_dict
        finally:
            # Cleanup: delete the workspace (cascades to members + programs +
            # runs) then the owner. Use a fresh session so we're not affected
            # by any in-flight transaction state in `session`.
            try:
                async with TestSessionLocal() as cleanup:
                    # substrate_events is append-only (BEFORE DELETE/UPDATE
                    # trigger), so the FK SET NULL cascade from missions is
                    # blocked. Disable the trigger for the duration of the
                    # cleanup, re-enable after. Order matters: children first.
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
                # Best-effort cleanup; don't mask the real test error.
                # Re-enable the trigger on failure (best effort).
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


# ── (a) create returns active + learning_brief=None ──────────────────────


async def test_create_returns_active_program_with_null_brief(ctx) -> None:
    service = MissionProgramService(ctx["session"])
    payload = ProgramCreate(
        name="Morning Standup",
        description="Runs at 9am every weekday",
        mission_type="research",
        per_run_budget_usd=2.5,
        monthly_budget_usd=50.0,
    )
    program = await service.create(
        user_id=ctx["owner"].id,
        workspace_id=ctx["workspace"].id,
        payload=payload,
    )
    await ctx["session"].commit()

    assert program.id is not None
    assert program.status == "active"
    assert program.learning_brief is None
    assert program.name == "Morning Standup"
    assert program.user_id == ctx["owner"].id
    assert program.workspace_id == ctx["workspace"].id
    assert program.per_run_budget_usd == 2.5
    assert program.monthly_budget_usd == 50.0


# ── (j) get raises ProgramNotFound for missing program ───────────────────


async def test_get_raises_not_found_for_missing_program(ctx) -> None:
    service = MissionProgramService(ctx["session"])
    with pytest.raises(ProgramNotFound):
        await service.get(user_id=ctx["owner"].id, program_id=uuid.uuid4())


# ── (b) get for non-owner non-member raises ProgramForbidden ─────────────


async def test_get_for_non_owner_non_member_raises_forbidden(ctx) -> None:
    # Owner creates a program in their workspace.
    service = MissionProgramService(ctx["session"])
    payload = ProgramCreate(name="Owner-only", description="")
    program = await service.create(
        user_id=ctx["owner"].id,
        workspace_id=ctx["workspace"].id,
        payload=payload,
    )
    await ctx["session"].commit()

    # An outsider — different user, not a member of the workspace.
    async with TestSessionLocal() as s2:
        outsider = await _make_user(s2, suffix="outsider")
        await s2.commit()
        outsider_id = outsider.id

    try:
        # Build a fresh service for the outsider session (no cross-session leakage).
        async with TestSessionLocal() as s2:
            service2 = MissionProgramService(s2)
            with pytest.raises(ProgramForbidden):
                await service2.get(user_id=outsider_id, program_id=program.id)
    finally:
        async with TestSessionLocal() as s3:
            await s3.execute(
                text("DELETE FROM users WHERE id = :uid"), {"uid": outsider_id}
            )
            await s3.commit()


# ── (c) update on archived program raises ProgramTransitionConflict ─────


async def test_update_on_archived_program_raises_conflict(ctx) -> None:
    service = MissionProgramService(ctx["session"])
    payload = ProgramCreate(name="To-archive", description="")
    program = await service.create(
        user_id=ctx["owner"].id,
        workspace_id=ctx["workspace"].id,
        payload=payload,
    )
    await ctx["session"].commit()

    # Archive it first.
    archived = await service.archive(user_id=ctx["owner"].id, program_id=program.id)
    await ctx["session"].commit()
    assert archived.status == "archived"

    # Now try to update its name.
    patch = ProgramUpdate(name="New name")
    with pytest.raises(ProgramTransitionConflict):
        await service.update(user_id=ctx["owner"].id, program_id=program.id, patch=patch)


# ── (d) archive with in-flight run raises ProgramTransitionConflict ─────


async def test_archive_with_in_flight_run_raises_conflict(ctx) -> None:
    service = MissionProgramService(ctx["session"])
    payload = ProgramCreate(name="With-running-run", description="")
    program = await service.create(
        user_id=ctx["owner"].id,
        workspace_id=ctx["workspace"].id,
        payload=payload,
    )
    await ctx["session"].commit()

    # Seed an in-flight run directly (fire_program is implemented in T8).
    in_flight = ProgramRun(
        program_id=program.id,
        mission_id=uuid.uuid4(),  # placeholder; not a real mission FK row.
        trigger_type="manual",
        status="running",
    )
    # We need a real Mission row to satisfy the FK.
    # Create a minimal mission owned by the same user.
    mission = Mission(
        id=in_flight.mission_id,
        title="placeholder",
        description="",
        user_id=ctx["owner"].id,
        workspace_id=ctx["workspace"].id,
        status="running",
    )
    ctx["session"].add(mission)
    ctx["session"].add(in_flight)
    await ctx["session"].commit()

    with pytest.raises(ProgramTransitionConflict):
        await service.archive(user_id=ctx["owner"].id, program_id=program.id)


# ── (e) update_user_notes preserves structured fields ───────────────────


async def test_update_user_notes_preserves_structured_fields(ctx) -> None:
    service = MissionProgramService(ctx["session"])
    payload = ProgramCreate(name="With-brief", description="")
    program = await service.create(
        user_id=ctx["owner"].id,
        workspace_id=ctx["workspace"].id,
        payload=payload,
    )
    await ctx["session"].commit()

    # Seed a structured learning brief directly (consolidation is T9).
    existing_brief: dict[str, Any] = {
        "total_runs": 12,
        "success_rate": 0.75,
        "common_failures": [
            {"pattern": "tool_timeout", "count": 3, "mitigation": "retry"}
        ],
        "effective_tools": ["web_search"],
        "ineffective_tools": ["shell_exec"],
        "plan_adjustments": "skip sundays",
        "last_consolidated_at": "2026-06-01T00:00:00Z",
        "user_notes": "old notes (should be replaced)",
    }
    program.learning_brief = existing_brief
    await ctx["session"].commit()

    updated = await service.update_user_notes(
        user_id=ctx["owner"].id, program_id=program.id, notes="Avoid Mondays — high load"
    )
    await ctx["session"].commit()

    assert updated.learning_brief is not None
    assert updated.learning_brief["user_notes"] == "Avoid Mondays — high load"
    # Structured fields are preserved verbatim.
    assert updated.learning_brief["common_failures"] == [
        {"pattern": "tool_timeout", "count": 3, "mitigation": "retry"}
    ]
    assert updated.learning_brief["effective_tools"] == ["web_search"]
    assert updated.learning_brief["plan_adjustments"] == "skip sundays"
    assert updated.learning_brief["total_runs"] == 12


# ── (f) list filters by workspace_id when provided ───────────────────────


async def test_list_filters_by_workspace_id(ctx) -> None:
    service = MissionProgramService(ctx["session"])

    # Create a program in the owner's workspace.
    payload = ProgramCreate(name="In-owner-ws", description="")
    p_in = await service.create(
        user_id=ctx["owner"].id,
        workspace_id=ctx["workspace"].id,
        payload=payload,
    )
    await ctx["session"].commit()

    # Create a second workspace (owner of it is the SAME user — but it's a
    # different workspace_id) and seed a program there.
    other_ws = await _make_workspace(session=ctx["session"], owner_id=ctx["owner"].id)
    await ctx["session"].commit()
    payload2 = ProgramCreate(name="In-other-ws", description="")
    p_out = await service.create(
        user_id=ctx["owner"].id,
        workspace_id=other_ws.id,
        payload=payload2,
    )
    await ctx["session"].commit()

    # Filter by owner-ws.
    items, total = await service.list(
        user_id=ctx["owner"].id,
        workspace_id=ctx["workspace"].id,
        page=1,
        per_page=50,
    )
    ids = {p.id for p in items}
    assert p_in.id in ids
    assert p_out.id not in ids
    assert total >= 1

    # No filter — see both.
    items_all, _ = await service.list(
        user_id=ctx["owner"].id, workspace_id=None, page=1, per_page=50
    )
    ids_all = {p.id for p in items_all}
    assert p_in.id in ids_all and p_out.id in ids_all


# ── (g) _check_program_budget per_run cap rejects when estimated > cap ──


async def test_budget_check_per_run_cap_rejects(ctx) -> None:
    service = MissionProgramService(ctx["session"])
    payload = ProgramCreate(name="Bounded", description="", per_run_budget_usd=1.0)
    program = await service.create(
        user_id=ctx["owner"].id,
        workspace_id=ctx["workspace"].id,
        payload=payload,
    )
    await ctx["session"].commit()

    # Estimated cost ($2.00) > per-run cap ($1.00) → reject.
    with pytest.raises(ProgramBudgetExceeded):
        await service._check_program_budget(program, estimated_cost_usd=2.0)

    # Estimated cost ($0.50) within cap → OK.
    await service._check_program_budget(program, estimated_cost_usd=0.5)


# ── (h) _check_program_budget monthly cap rejects when projected > cap ───


async def test_budget_check_monthly_cap_rejects(ctx) -> None:
    service = MissionProgramService(ctx["session"])
    payload = ProgramCreate(name="MonthlyBounded", description="", monthly_budget_usd=10.0)
    program = await service.create(
        user_id=ctx["owner"].id,
        workspace_id=ctx["workspace"].id,
        payload=payload,
    )
    await ctx["session"].commit()

    # Seed a completed run costing $8.00 this month.
    mission_id = uuid.uuid4()
    mission = Mission(
        id=mission_id,
        title="placeholder",
        description="",
        user_id=ctx["owner"].id,
        workspace_id=ctx["workspace"].id,
        status="completed",
    )
    prior_run = ProgramRun(
        program_id=program.id,
        mission_id=mission_id,
        trigger_type="manual",
        status="completed",
        cost_usd=8.0,
    )
    ctx["session"].add(mission)
    ctx["session"].add(prior_run)
    await ctx["session"].commit()

    # Projected: $8.00 + $5.00 = $13.00 > $10.00 cap → reject.
    with pytest.raises(ProgramBudgetExceeded):
        await service._check_program_budget(program, estimated_cost_usd=5.0)

    # Projected: $8.00 + $1.50 = $9.50 within $10.00 cap → OK.
    await service._check_program_budget(program, estimated_cost_usd=1.5)


# ── (i) _check_program_budget both None means no enforcement ────────────


async def test_budget_check_no_caps_means_no_enforcement(ctx) -> None:
    service = MissionProgramService(ctx["session"])
    payload = ProgramCreate(name="Unbounded", description="")  # both caps None
    program = await service.create(
        user_id=ctx["owner"].id,
        workspace_id=ctx["workspace"].id,
        payload=payload,
    )
    await ctx["session"].commit()

    # No caps → even a huge estimate is fine.
    await service._check_program_budget(program, estimated_cost_usd=1_000_000.0)


# ── (k) archive ACTIVE → ARCHIVED succeeds ──────────────────────────────


async def test_archive_active_to_archived_succeeds(ctx) -> None:
    service = MissionProgramService(ctx["session"])
    payload = ProgramCreate(name="To-archive-2", description="")
    program = await service.create(
        user_id=ctx["owner"].id,
        workspace_id=ctx["workspace"].id,
        payload=payload,
    )
    await ctx["session"].commit()
    assert program.status == "active"

    archived = await service.archive(user_id=ctx["owner"].id, program_id=program.id)
    await ctx["session"].commit()
    assert archived.status == "archived"


# ── (l) archive PAUSED → ARCHIVED succeeds ──────────────────────────────


async def test_archive_paused_to_archived_succeeds(ctx) -> None:
    service = MissionProgramService(ctx["session"])
    payload = ProgramCreate(name="Pause-then-archive", description="")
    program = await service.create(
        user_id=ctx["owner"].id,
        workspace_id=ctx["workspace"].id,
        payload=payload,
    )
    await ctx["session"].commit()

    # ACTIVE → PAUSED via PATCH.
    patch = ProgramUpdate(status="paused")
    paused = await service.update(
        user_id=ctx["owner"].id, program_id=program.id, patch=patch
    )
    await ctx["session"].commit()
    assert paused.status == "paused"

    # PAUSED → ARCHIVED via archive().
    archived = await service.archive(user_id=ctx["owner"].id, program_id=program.id)
    await ctx["session"].commit()
    assert archived.status == "archived"
