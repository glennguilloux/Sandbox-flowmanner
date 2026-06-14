"""TDD tests for T22: cross-pollination — wire personal memory into
``MissionProgramService.consolidate_learning``.

Covers the new ``user_personal_claims`` sub-key on the merged
``learning_brief`` JSONB. The brief carries the user's top-N
non-restricted, non-private personal memory claims (default empty
list) so downstream rendering can use them as a tie-breaker / context
layer. Consolidation MUST NEVER overwrite ``user_notes`` (the
canonical isolation contract), and a personal-memory failure MUST
NOT break the consolidation flow.

The test file is split into two sections:

* **Schema (pure-Python)** — no DB; verifies the
  ``LearningBriefBase.user_personal_claims`` field defaults to ``[]``
  and round-trips arbitrary claim dicts.

* **Service (integration)** — real ``AsyncSession`` against PostgreSQL,
  but the personal-memory service is mocked via the late-binding
  ``get_personal_memory_service`` callable (per the T21 pattern).
  ``EpisodicMemoryService.get_episodes_for_mission`` is also mocked.
  Run via::

      cd /opt/flowmanner/backend
      DATABASE_URL="postgresql+asyncpg://flowmanner:5f206ab26d543ba5424385cb10200efc@127.0.0.1:5432/flowmanner" \\
        /opt/flowmanner/backend/.venv/bin/python -m pytest tests/test_consolidate_personal_memory.py -v --timeout=15

Cases:
- (schema) ``LearningBriefBase.user_personal_claims`` defaults to ``[]``
- (schema) ``LearningBriefBase.user_personal_claims`` round-trips
  arbitrary claim dicts (preserves the ``id`` key as a string UUID).
- (1)    no ``get_personal_memory_service`` callable → ``user_personal_claims`` is ``[]``.
- (2)    recall returns claims → serialized with the documented shape.
- (3)    restricted sensitivity + private scope claims are filtered out.
- (4)    existing ``user_notes`` is NOT overwritten (canonical isolation test).
- (5)    recall raises exception → brief still merged, ``user_personal_claims`` is ``[]``.
- (6)    ``last_consolidated_at`` is set even when personal memory is empty.
- (7)    existing structured fields (total_runs, success_rate, etc.) preserved.
- (8)    top-20 cap: 25 input → 20 in brief.
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
    "postgresql+asyncpg://flowmanner:5f206ab26d543ba5424385cb10200efc@127.0.0.1:5432/flowmanner",
)

# Late imports so env var is honored.
from app.models.mission_models import Mission  # noqa: E402
from app.models.mission_program_models import (  # noqa: E402
    MissionProgram,
    ProgramRun,
)
from app.models.user import User  # noqa: E402
from app.models.workspace_models import Workspace  # noqa: E402
from app.schemas.program import LearningBriefBase, ProgramCreate  # noqa: E402
from app.services.mission_program_service import (  # noqa: E402
    MissionProgramService,
)


# ════════════════════════════════════════════════════════════════════════
# Section 1 — Schema (pure-Python, no DB)
# ════════════════════════════════════════════════════════════════════════


class TestSchemaUserPersonalClaims:
    """The ``LearningBriefBase`` schema MUST add a new
    ``user_personal_claims`` field that defaults to ``[]`` and
    round-trips the serialized claim shape.
    """

    def test_a_field_defaults_to_empty_list(self) -> None:
        """An empty brief has ``user_personal_claims == []`` by default."""
        brief = LearningBriefBase()
        assert brief.user_personal_claims == []
        # Ensure the field is listed in the model.
        assert "user_personal_claims" in LearningBriefBase.model_fields

    def test_b_round_trips_arbitrary_claim_dicts(self) -> None:
        """The field accepts and re-emits a list of claim dicts with the
        documented shape: ``id``, ``subject``, ``predicate``, ``object``,
        ``claim_type``, ``scope``, ``confidence``, ``importance``,
        ``source_type``.
        """
        claim_dict = {
            "id": str(uuid.uuid4()),
            "subject": "user",
            "predicate": "prefers",
            "object": {"value": "Python"},
            "claim_type": "preference",
            "scope": "personal",
            "confidence": 0.85,
            "importance": 0.7,
            "source_type": "user_explicit",
        }
        brief = LearningBriefBase(
            total_runs=2,
            success_rate=0.5,
            user_personal_claims=[claim_dict],
        )
        assert brief.user_personal_claims == [claim_dict]
        # Round-trip via model_dump() — the dict must survive intact.
        dumped = brief.model_dump()
        assert dumped["user_personal_claims"] == [claim_dict]
        # And via reconstruct from the dump (simulates a JSONB round trip).
        round_tripped = LearningBriefBase(**dumped)
        assert round_tripped.user_personal_claims == [claim_dict]

    def test_c_empty_list_round_trip(self) -> None:
        """An empty list survives the round trip — the field is
        additive, not destructive.
        """
        brief = LearningBriefBase(user_personal_claims=[])
        dumped = brief.model_dump()
        assert dumped["user_personal_claims"] == []
        assert LearningBriefBase(**dumped).user_personal_claims == []


# ════════════════════════════════════════════════════════════════════════
# Section 2 — Service (integration, real DB)
# ════════════════════════════════════════════════════════════════════════

pytestmark_service = pytest.mark.integration

# ── Engine + session factory (session-scoped) ────────────────────────────

_TEST_DATABASE_URL = os.environ["DATABASE_URL"]
if "@postgres:" in _TEST_DATABASE_URL:
    _TEST_DATABASE_URL = _TEST_DATABASE_URL.replace("@postgres:", "@127.0.0.1:")
_test_engine = create_async_engine(_TEST_DATABASE_URL, echo=False, poolclass=NullPool)
TestSessionLocal = async_sessionmaker(_test_engine, class_=AsyncSession, expire_on_commit=False)


@pytest_asyncio.fixture(scope="session", autouse=True)
async def _manage_engine() -> None:
    yield
    await _test_engine.dispose()


@pytest_asyncio.fixture(scope="session", autouse=True)
async def _skip_if_no_db() -> None:
    async with TestSessionLocal() as s:
        try:
            await s.execute(text("SELECT 1"))
        except Exception as e:
            pytest.skip(f"Database not reachable: {e}")


# ── Test-data factories ────────────────────────────────────────────────


def _new_id() -> int:
    return uuid.uuid4().int % 900_000_000 + 100_000


def _new_workspace_id() -> str:
    return f"ws-cpm-{uuid.uuid4().hex[:24]}"


async def _make_user(session: AsyncSession, *, suffix: str = "owner") -> User:
    user_id = _new_id()
    user = User(
        id=user_id,
        email=f"cpm-svc-{user_id}-{suffix}@test.flowmanner.example",
        username=f"cpm_svc_{user_id}_{suffix}",
        full_name=f"CPM SVC Test {user_id} {suffix}",
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
        name=f"cpm-ws-{uuid.uuid4().hex[:8]}",
        slug=f"cpm-ws-{uuid.uuid4().hex[:12]}",
        owner_id=owner_id,
        plan="free",
        is_active=True,
    )
    session.add(ws)
    await session.flush()
    return ws


# ── Per-test fixture (DB-isolated) ──────────────────────────────────────


@pytest_asyncio.fixture
async def ctx() -> Any:
    """Yield a clean test context: session, owner User, Workspace.

    Cleanup deletes per-test rows for the owner across
    ``personal_memory_claims``, ``program_runs``, ``mission_programs``,
    ``missions``, ``workspace_members``, ``workspaces``, ``users``.

    The original session is opened manually (NOT via ``async with``)
    and closed in the finally — same pattern as test_personal_memory_
    service.py to avoid the "asynchronous generator is already
    running" race that the ``async with`` ``__aexit__`` triggers when
    pytest-asyncio tears down between async generators. Cleanup runs
    in a SEPARATE session (see ``_cleanup``).
    """
    session = TestSessionLocal()
    try:
        owner = await _make_user(session)
        ws = await _make_workspace(session, owner_id=owner.id)
        await session.commit()
        ctx_dict = {"session": session, "owner": owner, "workspace": ws}
        yield ctx_dict
    finally:
        # Close the test session cleanly. If close fails (e.g. async
        # generator race), swallow it — we still want cleanup to run.
        try:
            await session.close()
        except Exception:
            pass
        # Best-effort cleanup of persisted rows.
        try:
            async with TestSessionLocal() as cleanup:
                await cleanup.execute(
                    text(
                        "ALTER TABLE substrate_events "
                        "DISABLE TRIGGER trg_substrate_events_append_only"
                    )
                )
                await cleanup.execute(
                    text(
                        "DELETE FROM personal_memory_claims "
                        "WHERE user_id = :uid"
                    ),
                    {"uid": owner.id},
                )
                await cleanup.execute(
                    text(
                        "DELETE FROM program_runs WHERE program_id IN "
                        "(SELECT id FROM mission_programs WHERE user_id = :uid)"
                    ),
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


# ── Helpers: mocks + run seeding ────────────────────────────────────────


def _make_memory_mock() -> MagicMock:
    """Stand-in for EpisodicMemoryService singleton."""
    m = MagicMock()
    m.get_episodes_for_mission = AsyncMock(return_value=[])
    return m


def _make_enforcer_mock(
    *, response_content: str = "{}"
) -> MagicMock:
    """Stand-in for BudgetEnforcer singleton."""
    e = MagicMock()
    e.call = AsyncMock(
        return_value={"content": response_content, "success": True}
    )
    return e


def _make_personal_memory_service_mock(
    *,
    recall_return: tuple[list[Any], int] = ([], 0),
    recall_side_effect: Any = None,
) -> MagicMock:
    """Build a stand-in for PersonalMemoryService.

    ``recall`` is an AsyncMock returning ``(claims, total)``. If
    ``recall_side_effect`` is given, the mock raises that exception
    instead.
    """
    svc = MagicMock()
    if recall_side_effect is not None:
        svc.recall = AsyncMock(side_effect=recall_side_effect)
    else:
        svc.recall = AsyncMock(return_value=recall_return)
    return svc


def _make_claim(
    *,
    subject: str = "user",
    predicate: str = "prefers",
    obj: Any = {"value": "Python"},
    claim_type: str = "preference",
    scope: str = "personal",
    sensitivity: str = "normal",
    confidence: float = 0.85,
    importance: float = 0.7,
    source_type: str = "user_explicit",
    claim_id: uuid.UUID | None = None,
) -> MagicMock:
    """Build a minimal mock claim with the SQLAlchemy column names."""
    c = MagicMock()
    c.id = claim_id or uuid.uuid4()
    c.subject = subject
    c.predicate = predicate
    c.object = obj
    c.claim_type = claim_type
    c.scope = scope
    c.sensitivity = sensitivity
    c.confidence = confidence
    c.importance = importance
    c.source_type = source_type
    return c


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
        title="cpm-placeholder",
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


# ── (1) No personal memory service → user_personal_claims == [] ────────


async def test_no_personal_memory_service_yields_empty_claims(ctx) -> None:
    """When ``get_personal_memory_service`` is ``None`` (or its callable
    returns ``None``), the merged brief carries ``user_personal_claims=[]``.
    The brief is still merged normally.
    """
    service = MissionProgramService(
        ctx["session"],
        get_personal_memory_service=None,
    )
    payload = ProgramCreate(name="No-pm", description="")
    program = await service.create(
        user_id=ctx["owner"].id,
        workspace_id=ctx["workspace"].id,
        payload=payload,
    )
    await ctx["session"].commit()

    # Seed 1 terminal run so the LLM path runs.
    await _seed_run(
        ctx["session"],
        program_id=program.id,
        mission_owner_id=ctx["owner"].id,
        workspace_id=ctx["workspace"].id,
        status="completed",
    )
    await ctx["session"].commit()

    enforcer_mock = _make_enforcer_mock(
        response_content=json.dumps(
            {
                "total_runs": 1,
                "success_rate": 1.0,
                "effective_tools": ["t1"],
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

    # user_personal_claims is the empty list.
    assert response.brief.user_personal_claims == []
    # Existing structured fields are present.
    assert response.brief.total_runs == 1
    assert response.brief.effective_tools == ["t1"]
    # Persisted in DB.
    await ctx["session"].refresh(program)
    assert program.learning_brief["user_personal_claims"] == []


# ── (2) Recall returns claims → serialized with documented shape ───────


async def test_recall_claims_serialized_with_documented_shape(ctx) -> None:
    """Recall returning 2 normal claims produces 2 serialized dicts in
    the brief, each carrying the documented keys: ``id``, ``subject``,
    ``predicate``, ``object``, ``claim_type``, ``scope``,
    ``confidence``, ``importance``, ``source_type``.
    """
    service = MissionProgramService(
        ctx["session"],
        get_personal_memory_service=lambda: _make_personal_memory_service_mock(
            recall_return=(
                [
                    _make_claim(
                        subject="user",
                        predicate="prefers",
                        obj={"value": "Python"},
                        claim_type="preference",
                        scope="personal",
                        confidence=0.9,
                        importance=0.8,
                    ),
                    _make_claim(
                        subject="user",
                        predicate="dislikes",
                        obj={"value": "Java"},
                        claim_type="preference",
                        scope="workspace",
                        confidence=0.7,
                        importance=0.6,
                        source_type="mission",
                    ),
                ],
                2,
            )
        ),
    )
    payload = ProgramCreate(name="With-claims", description="")
    program = await service.create(
        user_id=ctx["owner"].id,
        workspace_id=ctx["workspace"].id,
        payload=payload,
    )
    await ctx["session"].commit()
    await _seed_run(
        ctx["session"],
        program_id=program.id,
        mission_owner_id=ctx["owner"].id,
        workspace_id=ctx["workspace"].id,
        status="completed",
    )
    await ctx["session"].commit()

    enforcer_mock = _make_enforcer_mock(
        response_content=json.dumps(
            {
                "total_runs": 1,
                "success_rate": 1.0,
                "effective_tools": ["t1"],
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

    claims = response.brief.user_personal_claims
    assert len(claims) == 2
    # Documented shape: every claim carries the 9 fields.
    expected_keys = {
        "id",
        "subject",
        "predicate",
        "object",
        "claim_type",
        "scope",
        "confidence",
        "importance",
        "source_type",
    }
    for claim in claims:
        assert set(claim.keys()) == expected_keys, claim
    # Spot-check values from the first claim.
    assert claims[0]["subject"] == "user"
    assert claims[0]["predicate"] == "prefers"
    assert claims[0]["object"] == {"value": "Python"}
    assert claims[0]["claim_type"] == "preference"
    assert claims[0]["scope"] == "personal"
    assert claims[0]["confidence"] == 0.9
    assert claims[0]["importance"] == 0.8
    # id is the string form of the UUID.
    uuid.UUID(claims[0]["id"])  # raises if not a valid UUID
    # Persisted in DB.
    await ctx["session"].refresh(program)
    persisted = program.learning_brief["user_personal_claims"]
    assert len(persisted) == 2
    assert persisted[0]["subject"] == "user"


# ── (3) Restricted sensitivity + private scope claims are filtered out ─


async def test_restricted_and_private_claims_filtered(ctx) -> None:
    """Recall returns 3 claims: one normal/personal (kept), one
    restricted (excluded), one private (excluded). The brief contains
    only the kept one.
    """
    normal = _make_claim(
        subject="user", predicate="prefers", scope="personal",
        sensitivity="normal",
    )
    restricted = _make_claim(
        subject="user", predicate="secret", scope="personal",
        sensitivity="restricted", claim_id=uuid.uuid4(),
    )
    private = _make_claim(
        subject="user", predicate="private", scope="private",
        sensitivity="normal", claim_id=uuid.uuid4(),
    )

    service = MissionProgramService(
        ctx["session"],
        get_personal_memory_service=lambda: _make_personal_memory_service_mock(
            recall_return=([normal, restricted, private], 3)
        ),
    )
    payload = ProgramCreate(name="Filter-test", description="")
    program = await service.create(
        user_id=ctx["owner"].id,
        workspace_id=ctx["workspace"].id,
        payload=payload,
    )
    await ctx["session"].commit()
    await _seed_run(
        ctx["session"],
        program_id=program.id,
        mission_owner_id=ctx["owner"].id,
        workspace_id=ctx["workspace"].id,
        status="completed",
    )
    await ctx["session"].commit()

    enforcer_mock = _make_enforcer_mock(
        response_content=json.dumps({"total_runs": 1, "success_rate": 1.0})
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

    claims = response.brief.user_personal_claims
    assert len(claims) == 1
    # The kept one is the normal/personal claim.
    assert claims[0]["scope"] == "personal"
    assert claims[0]["predicate"] == "prefers"
    # The restricted and private predicates are NOT in the brief.
    assert all(c["predicate"] != "secret" for c in claims)
    assert all(c["predicate"] != "private" for c in claims)


# ── (4) Existing user_notes is NOT overwritten (canonical isolation) ───


async def test_user_notes_not_overwritten(ctx) -> None:
    """Set user_notes on the program, run consolidation with a mock
    LLM that does NOT return user_notes, verify user_notes survives
    intact AND user_personal_claims is populated.
    """
    service = MissionProgramService(
        ctx["session"],
        get_personal_memory_service=lambda: _make_personal_memory_service_mock(
            recall_return=(
                [_make_claim(subject="user", predicate="prefers")],
                1,
            )
        ),
    )
    payload = ProgramCreate(name="Notes-isolation", description="")
    program = await service.create(
        user_id=ctx["owner"].id,
        workspace_id=ctx["workspace"].id,
        payload=payload,
    )
    await ctx["session"].commit()

    # Pre-seed the brief with user_notes. The LLM will not return this
    # key — the merge step must keep it.
    program.learning_brief = {
        "total_runs": 0,
        "user_notes": "ALWAYS avoid Mondays — high load",
    }
    await ctx["session"].commit()

    await _seed_run(
        ctx["session"],
        program_id=program.id,
        mission_owner_id=ctx["owner"].id,
        workspace_id=ctx["workspace"].id,
        status="completed",
    )
    await ctx["session"].commit()

    enforcer_mock = _make_enforcer_mock(
        response_content=json.dumps(
            {"total_runs": 1, "success_rate": 1.0, "effective_tools": ["t1"]}
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

    # Canonical isolation: user_notes survives the consolidation.
    assert response.brief.user_notes == "ALWAYS avoid Mondays — high load"
    # user_personal_claims is populated.
    assert len(response.brief.user_personal_claims) == 1
    # Persisted in DB.
    await ctx["session"].refresh(program)
    assert (
        program.learning_brief["user_notes"]
        == "ALWAYS avoid Mondays — high load"
    )
    assert len(program.learning_brief["user_personal_claims"]) == 1


# ── (5) Recall raises → brief still merged, user_personal_claims == [] ─


async def test_recall_raises_swallowed_yields_empty_claims(ctx) -> None:
    """If the personal-memory service raises during recall, the brief
    is still merged (no exception bubbles out) and
    ``user_personal_claims`` is the empty list.
    """
    service = MissionProgramService(
        ctx["session"],
        get_personal_memory_service=lambda: _make_personal_memory_service_mock(
            recall_side_effect=RuntimeError("personal-memory db down")
        ),
    )
    payload = ProgramCreate(name="Recall-fails", description="")
    program = await service.create(
        user_id=ctx["owner"].id,
        workspace_id=ctx["workspace"].id,
        payload=payload,
    )
    await ctx["session"].commit()
    await _seed_run(
        ctx["session"],
        program_id=program.id,
        mission_owner_id=ctx["owner"].id,
        workspace_id=ctx["workspace"].id,
        status="completed",
    )
    await ctx["session"].commit()

    enforcer_mock = _make_enforcer_mock(
        response_content=json.dumps(
            {"total_runs": 1, "success_rate": 0.5, "effective_tools": ["t1"]}
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
        # MUST NOT raise.
        response = await service.consolidate_learning(
            user_id=ctx["owner"].id, program_id=program.id
        )

    # Brief is still merged and structured fields are present.
    assert response.brief.user_personal_claims == []
    assert response.brief.total_runs == 1
    assert response.brief.effective_tools == ["t1"]
    # Persisted in DB.
    await ctx["session"].refresh(program)
    assert program.learning_brief["user_personal_claims"] == []


# ── (6) last_consolidated_at set even when personal memory is empty ────


async def test_last_consolidated_at_set_with_empty_personal_memory(ctx) -> None:
    """When the personal-memory service returns an empty list, the brief
    is still merged and ``last_consolidated_at`` is set to a non-null
    ISO timestamp.
    """
    service = MissionProgramService(
        ctx["session"],
        get_personal_memory_service=lambda: _make_personal_memory_service_mock(
            recall_return=([], 0)
        ),
    )
    payload = ProgramCreate(name="Empty-pm", description="")
    program = await service.create(
        user_id=ctx["owner"].id,
        workspace_id=ctx["workspace"].id,
        payload=payload,
    )
    await ctx["session"].commit()
    await _seed_run(
        ctx["session"],
        program_id=program.id,
        mission_owner_id=ctx["owner"].id,
        workspace_id=ctx["workspace"].id,
        status="completed",
    )
    await ctx["session"].commit()

    enforcer_mock = _make_enforcer_mock(
        response_content=json.dumps({"total_runs": 1, "success_rate": 1.0})
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

    assert response.brief.last_consolidated_at is not None
    # And user_personal_claims is the empty list.
    assert response.brief.user_personal_claims == []


# ── (7) Existing structured fields (total_runs, success_rate, …) preserved


async def test_structured_fields_preserved(ctx) -> None:
    """LLM-returned structured fields (total_runs, success_rate,
    common_failures, effective_tools, ineffective_tools, hitl_history,
    plan_adjustments) survive the merge alongside the new
    ``user_personal_claims`` key.
    """
    service = MissionProgramService(
        ctx["session"],
        get_personal_memory_service=lambda: _make_personal_memory_service_mock(
            recall_return=([_make_claim()], 1)
        ),
    )
    payload = ProgramCreate(name="Structured-preserved", description="")
    program = await service.create(
        user_id=ctx["owner"].id,
        workspace_id=ctx["workspace"].id,
        payload=payload,
    )
    await ctx["session"].commit()
    await _seed_run(
        ctx["session"],
        program_id=program.id,
        mission_owner_id=ctx["owner"].id,
        workspace_id=ctx["workspace"].id,
        status="completed",
    )
    await ctx["session"].commit()

    llm_payload = {
        "total_runs": 7,
        "success_rate": 0.8571,
        "avg_cost_usd": 0.05,
        "avg_tokens": 1234,
        "common_failures": [{"pattern": "rate-limit", "count": 2, "mitigation": "backoff"}],
        "effective_tools": ["search", "summarize"],
        "ineffective_tools": ["raw-curl"],
        "hitl_history": [{"outcome": "approved", "count": 1}],
        "plan_adjustments": "favor summarization first",
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

    # Structured fields survive the merge.
    assert response.brief.total_runs == 7
    assert response.brief.success_rate == 0.8571
    assert response.brief.avg_cost_usd == 0.05
    assert response.brief.avg_tokens == 1234
    assert response.brief.common_failures == [
        {"pattern": "rate-limit", "count": 2, "mitigation": "backoff"}
    ]
    assert response.brief.effective_tools == ["search", "summarize"]
    assert response.brief.ineffective_tools == ["raw-curl"]
    assert response.brief.hitl_history == [{"outcome": "approved", "count": 1}]
    assert response.brief.plan_adjustments == "favor summarization first"
    # And the new field is populated alongside.
    assert len(response.brief.user_personal_claims) == 1


# ── (8) Top-20 cap: 25 input → 20 in brief ──────────────────────────────


async def test_top_20_cap(ctx) -> None:
    """When recall returns 25 claims, the brief carries the first 20
    (the cap). The order is preserved (importance/confidence/
    last_used_at sort is the service's responsibility; the brief just
    stores what recall returned, up to the cap).
    """
    claims_25 = [
        _make_claim(
            subject="user",
            predicate=f"claim_{i:02d}",
            confidence=0.5 + (i * 0.01),
            importance=0.5 + (i * 0.01),
            claim_id=uuid.uuid4(),
        )
        for i in range(25)
    ]
    service = MissionProgramService(
        ctx["session"],
        get_personal_memory_service=lambda: _make_personal_memory_service_mock(
            recall_return=(claims_25, 25)
        ),
    )
    payload = ProgramCreate(name="Top20-cap", description="")
    program = await service.create(
        user_id=ctx["owner"].id,
        workspace_id=ctx["workspace"].id,
        payload=payload,
    )
    await ctx["session"].commit()
    await _seed_run(
        ctx["session"],
        program_id=program.id,
        mission_owner_id=ctx["owner"].id,
        workspace_id=ctx["workspace"].id,
        status="completed",
    )
    await ctx["session"].commit()

    enforcer_mock = _make_enforcer_mock(
        response_content=json.dumps({"total_runs": 1, "success_rate": 1.0})
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

    claims = response.brief.user_personal_claims
    assert len(claims) == 20
    # Persisted in DB.
    await ctx["session"].refresh(program)
    assert len(program.learning_brief["user_personal_claims"]) == 20
