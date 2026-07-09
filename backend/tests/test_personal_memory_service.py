"""TDD tests for PersonalMemoryService (D0-30, T19).

Two test clusters:

(A) Pure-Python tests (no DB, fast):
    * Enum value-set assertions (ClaimType, Scope, SourceType, Sensitivity)
    * Pydantic schema validation (bad/good values, extra="forbid", PATCH
      semantics, from_attributes on response)
    * Default value semantics (confidence/importance/sensitivity)

(B) Integration tests (``@pytest.mark.integration``, live PostgreSQL):
    * create() persists with all fields + defaults
    * get() returns the row; raises NotFound for unknown
    * list_for_user() filters by (user_id, workspace_id)
    * list_for_user() respects scope / claim_type filters
    * list_for_user() excludes soft-deleted by default
    * recall() returns rows ordered by confidence DESC
    * recall() filters by scope list
    * recall() updates last_used_at
    * recall() excludes expired rows
    * forget() soft-deletes (sets deleted_at)
    * forget() is idempotent
    * forget(hard=True) actually removes
    * update_importance() persists new value; rejects out-of-range
    * update() applies PATCH fields; rejects forbidden fields
    * **SECURITY GUARDRAIL**: a row owned by user A in workspace W is
      INVISIBLE when querying as user B in workspace W (workspace
      isolation enforced by every read path).

Run via::

    cd /opt/flowmanner/backend
    DATABASE_URL="postgresql+asyncpg://flowmanner:5f206ab26d543ba5424385cb10200efc@127.0.0.1:5432/flowmanner" \\
      .venv/bin/python -m pytest tests/test_personal_memory_service.py -v

    # integration (live DB)
    DATABASE_URL="postgresql+asyncpg://flowmanner:5f206ab26d543ba5424385cb10200efc@127.0.0.1:5432/flowmanner" \\
      .venv/bin/python -m pytest tests/test_personal_memory_service.py -v -m integration
"""

from __future__ import annotations

import contextlib
import os
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import NullPool

# Ensure DATABASE_URL is set BEFORE importing app modules that need it.
os.environ.setdefault(
    "DATABASE_URL",
    "postgresql+asyncpg://flowmanner:5f206ab26d543ba5424385cb10200efc@127.0.0.1:5432/flowmanner",
)


# ═══════════════════════════════════════════════════════════════════════════
# (A) Pure-Python tests — enum value-sets
# ═══════════════════════════════════════════════════════════════════════════


class TestClaimTypeEnum:
    def test_claim_type_documents_expected_values(self) -> None:
        """ClaimType must include fact, preference, observation, sensitive."""
        from app.schemas.personal_memory import ClaimType

        assert ClaimType.FACT.value == "fact"
        assert ClaimType.PREFERENCE.value == "preference"
        assert ClaimType.OBSERVATION.value == "observation"
        assert ClaimType.SENSITIVE.value == "sensitive"

    def test_claim_type_set_matches_value_set(self) -> None:
        """The set of enum values matches ALL_CLAIM_TYPES in the model."""
        from app.models.personal_memory_models import ALL_CLAIM_TYPES
        from app.schemas.personal_memory import ClaimType

        assert {ct.value for ct in ClaimType} == set(ALL_CLAIM_TYPES)

    def test_claim_type_is_str_enum(self) -> None:
        """ClaimType is a str, Enum (so .value is a plain string)."""
        from app.schemas.personal_memory import ClaimType

        # str enum: ClaimType.FACT == "fact" via str-membership
        assert isinstance(ClaimType.FACT, str)
        assert ClaimType.FACT == "fact"

    def test_claim_type_no_transitions_leak(self) -> None:
        """str, Enum must not leak class-level dicts (e.g. _TRANSITIONS)."""
        from app.schemas.personal_memory import ClaimType

        # If a nonmember() were forgotten, this would contain _TRANSITIONS.
        members = [m for m in dir(ClaimType) if not m.startswith("__")]
        assert "_TRANSITIONS" not in members, (
            "str, Enum must use enum.nonmember() to keep class-level dicts " "out of member iteration"
        )


class TestScopeEnum:
    def test_scope_documents_expected_values(self) -> None:
        from app.schemas.personal_memory import Scope

        assert Scope.PERSONAL.value == "personal"
        assert Scope.WORKSPACE.value == "workspace"
        assert Scope.PROGRAM.value == "program"
        assert Scope.PRIVATE.value == "private"

    def test_scope_set_matches_value_set(self) -> None:
        from app.models.personal_memory_models import ALL_SCOPES
        from app.schemas.personal_memory import Scope

        assert {s.value for s in Scope} == set(ALL_SCOPES)


class TestSourceTypeEnum:
    def test_source_type_documents_expected_values(self) -> None:
        from app.schemas.personal_memory import SourceType

        assert SourceType.MISSION.value == "mission"
        assert SourceType.CONVERSATION.value == "conversation"
        assert SourceType.USER_EXPLICIT.value == "user_explicit"
        assert SourceType.PROGRAM_LEARNING.value == "program_learning"

    def test_source_type_set_matches_value_set(self) -> None:
        from app.models.personal_memory_models import ALL_SOURCE_TYPES
        from app.schemas.personal_memory import SourceType

        assert {st.value for st in SourceType} == set(ALL_SOURCE_TYPES)


class TestSensitivityEnum:
    def test_sensitivity_documents_expected_values(self) -> None:
        from app.schemas.personal_memory import Sensitivity

        assert Sensitivity.NORMAL.value == "normal"
        assert Sensitivity.SENSITIVE.value == "sensitive"
        assert Sensitivity.RESTRICTED.value == "restricted"

    def test_sensitivity_set_matches_value_set(self) -> None:
        from app.models.personal_memory_models import ALL_SENSITIVITIES
        from app.schemas.personal_memory import Sensitivity

        assert {s.value for s in Sensitivity} == set(ALL_SENSITIVITIES)


# ═══════════════════════════════════════════════════════════════════════════
# (A) Pure-Python tests — Pydantic schema validation
# ═══════════════════════════════════════════════════════════════════════════


class TestPersonalMemoryClaimCreateSchema:
    """Validate PersonalMemoryClaimCreate (request body)."""

    def test_minimal_create_with_required_fields_only(self) -> None:
        """Required fields: user_id, workspace_id, subject, predicate, object, claim_type, scope, source_type."""
        from app.schemas.personal_memory import PersonalMemoryClaimCreate

        payload = PersonalMemoryClaimCreate(
            user_id=1,
            workspace_id="ws-1",
            subject="user",
            predicate="prefers",
            object={"value": "dark_mode"},
            claim_type="preference",
            scope="personal",
            source_type="user_explicit",
        )
        assert payload.user_id == 1
        assert payload.workspace_id == "ws-1"
        assert payload.subject == "user"
        assert payload.predicate == "prefers"
        assert payload.object == {"value": "dark_mode"}
        assert payload.claim_type == "preference"
        assert payload.scope == "personal"
        assert payload.source_type == "user_explicit"
        # Defaults
        assert payload.confidence == 0.5
        assert payload.importance == 0.5
        assert payload.sensitivity == "normal"
        assert payload.source_id is None
        assert payload.expires_at is None

    def test_full_create_with_all_fields(self) -> None:
        from app.schemas.personal_memory import PersonalMemoryClaimCreate

        expires = datetime(2026, 12, 31, 23, 59, 59, tzinfo=UTC)
        payload = PersonalMemoryClaimCreate(
            user_id=42,
            workspace_id="ws-abc-123",
            subject="user",
            predicate="name",
            object={"value": "Alice"},
            claim_type="fact",
            scope="workspace",
            source_type="conversation",
            confidence=0.9,
            importance=0.7,
            sensitivity="sensitive",
            source_id=uuid.uuid4(),
            expires_at=expires,
        )
        assert payload.confidence == 0.9
        assert payload.importance == 0.7
        assert payload.sensitivity == "sensitive"
        assert payload.source_id is not None
        assert payload.expires_at == expires

    def test_invalid_claim_type_rejected(self) -> None:
        from pydantic import ValidationError

        from app.schemas.personal_memory import PersonalMemoryClaimCreate

        with pytest.raises(ValidationError) as exc_info:
            PersonalMemoryClaimCreate(
                user_id=1,
                workspace_id="ws-1",
                subject="user",
                predicate="prefers",
                object={"value": "x"},
                claim_type="not_a_real_type",  # not in ALL_CLAIM_TYPES
                scope="personal",
                source_type="user_explicit",
            )
        # Make sure claim_type is the offender.
        assert "claim_type" in str(exc_info.value)

    def test_invalid_scope_rejected(self) -> None:
        from pydantic import ValidationError

        from app.schemas.personal_memory import PersonalMemoryClaimCreate

        with pytest.raises(ValidationError) as exc_info:
            PersonalMemoryClaimCreate(
                user_id=1,
                workspace_id="ws-1",
                subject="user",
                predicate="prefers",
                object={"value": "x"},
                claim_type="fact",
                scope="global",  # not in ALL_SCOPES
                source_type="user_explicit",
            )
        assert "scope" in str(exc_info.value)

    def test_invalid_source_type_rejected(self) -> None:
        from pydantic import ValidationError

        from app.schemas.personal_memory import PersonalMemoryClaimCreate

        with pytest.raises(ValidationError) as exc_info:
            PersonalMemoryClaimCreate(
                user_id=1,
                workspace_id="ws-1",
                subject="user",
                predicate="prefers",
                object={"value": "x"},
                claim_type="fact",
                scope="personal",
                source_type="magic_source",  # not in ALL_SOURCE_TYPES
            )
        assert "source_type" in str(exc_info.value)

    def test_invalid_sensitivity_rejected(self) -> None:
        from pydantic import ValidationError

        from app.schemas.personal_memory import PersonalMemoryClaimCreate

        with pytest.raises(ValidationError) as exc_info:
            PersonalMemoryClaimCreate(
                user_id=1,
                workspace_id="ws-1",
                subject="user",
                predicate="prefers",
                object={"value": "x"},
                claim_type="fact",
                scope="personal",
                source_type="user_explicit",
                sensitivity="top_secret",  # not in ALL_SENSITIVITIES
            )
        assert "sensitivity" in str(exc_info.value)

    def test_extra_field_rejected(self) -> None:
        """extra='forbid' means unknown fields raise ValidationError."""
        from pydantic import ValidationError

        from app.schemas.personal_memory import PersonalMemoryClaimCreate

        with pytest.raises(ValidationError):
            PersonalMemoryClaimCreate(
                user_id=1,
                workspace_id="ws-1",
                subject="user",
                predicate="prefers",
                object={"value": "x"},
                claim_type="fact",
                scope="personal",
                source_type="user_explicit",
                made_up_field="nope",  # extra="forbid"
            )

    def test_importance_above_1_rejected(self) -> None:
        from pydantic import ValidationError

        from app.schemas.personal_memory import PersonalMemoryClaimCreate

        with pytest.raises(ValidationError):
            PersonalMemoryClaimCreate(
                user_id=1,
                workspace_id="ws-1",
                subject="user",
                predicate="prefers",
                object={"value": "x"},
                claim_type="fact",
                scope="personal",
                source_type="user_explicit",
                importance=1.5,  # > 1.0
            )

    def test_confidence_below_0_rejected(self) -> None:
        from pydantic import ValidationError

        from app.schemas.personal_memory import PersonalMemoryClaimCreate

        with pytest.raises(ValidationError):
            PersonalMemoryClaimCreate(
                user_id=1,
                workspace_id="ws-1",
                subject="user",
                predicate="prefers",
                object={"value": "x"},
                claim_type="fact",
                scope="personal",
                source_type="user_explicit",
                confidence=-0.1,  # < 0.0
            )


class TestPersonalMemoryClaimUpdateSchema:
    """Validate PersonalMemoryClaimUpdate (PATCH body)."""

    def test_empty_update_is_valid(self) -> None:
        """PATCH with no fields is a no-op — must still validate."""
        from app.schemas.personal_memory import PersonalMemoryClaimUpdate

        patch = PersonalMemoryClaimUpdate()
        # All fields are None by default.
        assert patch.subject is None
        assert patch.predicate is None
        assert patch.object is None
        assert patch.confidence is None
        assert patch.importance is None
        assert patch.sensitivity is None
        assert patch.expires_at is None

    def test_single_field_update(self) -> None:
        from app.schemas.personal_memory import PersonalMemoryClaimUpdate

        patch = PersonalMemoryClaimUpdate(subject="new subject")
        assert patch.subject == "new subject"
        # Other fields remain None.
        assert patch.predicate is None
        assert patch.importance is None

    def test_multiple_field_update(self) -> None:
        from app.schemas.personal_memory import PersonalMemoryClaimUpdate

        patch = PersonalMemoryClaimUpdate(
            subject="new subject",
            importance=0.9,
            sensitivity="restricted",
        )
        assert patch.subject == "new subject"
        assert patch.importance == 0.9
        assert patch.sensitivity == "restricted"

    def test_invalid_sensitivity_rejected(self) -> None:
        from pydantic import ValidationError

        from app.schemas.personal_memory import PersonalMemoryClaimUpdate

        with pytest.raises(ValidationError):
            PersonalMemoryClaimUpdate(sensitivity="ultra_top_secret")

    def test_invalid_importance_rejected(self) -> None:
        from pydantic import ValidationError

        from app.schemas.personal_memory import PersonalMemoryClaimUpdate

        with pytest.raises(ValidationError):
            PersonalMemoryClaimUpdate(importance=2.0)

    def test_extra_field_rejected(self) -> None:
        """extra='forbid' on the update schema too."""
        from pydantic import ValidationError

        from app.schemas.personal_memory import PersonalMemoryClaimUpdate

        with pytest.raises(ValidationError):
            PersonalMemoryClaimUpdate(
                subject="new",
                user_id=999,  # user_id is NOT editable via PATCH
            )

    def test_user_id_not_in_patch_schema(self) -> None:
        """user_id and workspace_id and id are immutable via PATCH."""
        from app.schemas.personal_memory import PersonalMemoryClaimUpdate

        # Construction with these fields raises because extra="forbid".
        with pytest.raises(Exception):
            PersonalMemoryClaimUpdate(user_id=1)
        with pytest.raises(Exception):
            PersonalMemoryClaimUpdate(workspace_id="ws-x")
        with pytest.raises(Exception):
            PersonalMemoryClaimUpdate(id=uuid.uuid4())


class TestPersonalMemoryClaimResponseSchema:
    """Response schema uses from_attributes=True (ORM-backed)."""

    def test_from_orm_object(self) -> None:
        from app.models.personal_memory_models import PersonalMemoryClaim
        from app.schemas.personal_memory import PersonalMemoryClaimResponse

        claim = PersonalMemoryClaim(
            id=uuid.uuid4(),
            user_id=7,
            workspace_id="ws-zzz",
            subject="user",
            predicate="loves",
            object={"value": "tea"},
            claim_type="preference",
            scope="personal",
            source_type="user_explicit",
            confidence=0.8,
            importance=0.6,
            sensitivity="normal",
        )
        response = PersonalMemoryClaimResponse.model_validate(claim)
        assert response.id == claim.id
        assert response.user_id == 7
        assert response.workspace_id == "ws-zzz"
        assert response.subject == "user"
        assert response.predicate == "loves"
        assert response.object == {"value": "tea"}
        assert response.claim_type == "preference"
        assert response.scope == "personal"
        assert response.source_type == "user_explicit"
        assert response.confidence == 0.8
        assert response.importance == 0.6
        assert response.sensitivity == "normal"
        assert response.deleted_at is None


class TestPersonalMemoryRecallRequestSchema:
    def test_defaults(self) -> None:
        from app.schemas.personal_memory import PersonalMemoryRecallRequest

        req = PersonalMemoryRecallRequest(query="dark mode")
        assert req.query == "dark mode"
        assert req.scopes is None
        assert req.top_k == 10
        assert req.min_confidence == 0.0

    def test_extra_field_rejected(self) -> None:
        from pydantic import ValidationError

        from app.schemas.personal_memory import PersonalMemoryRecallRequest

        with pytest.raises(ValidationError):
            PersonalMemoryRecallRequest(query="x", user_id=1)

    def test_top_k_bounded_above(self) -> None:
        from pydantic import ValidationError

        from app.schemas.personal_memory import PersonalMemoryRecallRequest

        with pytest.raises(ValidationError):
            PersonalMemoryRecallRequest(query="x", top_k=0)


class TestPersonalMemoryListResponseSchema:
    def test_paginated_wrapper(self) -> None:
        from app.schemas.personal_memory import (
            PersonalMemoryClaimResponse,
            PersonalMemoryListResponse,
        )

        items = [
            PersonalMemoryClaimResponse(
                id=uuid.uuid4(),
                user_id=1,
                workspace_id="ws-1",
                subject="u",
                predicate="p",
                object={"v": 1},
                claim_type="fact",
                scope="personal",
                source_type="user_explicit",
                confidence=0.5,
                importance=0.5,
                sensitivity="normal",
            )
        ]
        wrapper = PersonalMemoryListResponse(items=items, total=1, page=1, per_page=50)
        assert wrapper.total == 1
        assert wrapper.page == 1
        assert wrapper.per_page == 50
        assert len(wrapper.items) == 1


class TestPersonalMemoryForgetRequestSchema:
    def test_default_hard_false(self) -> None:
        from app.schemas.personal_memory import PersonalMemoryForgetRequest

        req = PersonalMemoryForgetRequest(claim_id="00000000-0000-0000-0000-000000000000")
        assert req.hard is False

    def test_explicit_hard_true(self) -> None:
        from app.schemas.personal_memory import PersonalMemoryForgetRequest

        req = PersonalMemoryForgetRequest(claim_id="00000000-0000-0000-0000-000000000000", hard=True)
        assert req.hard is True

    def test_claim_id_required(self) -> None:
        from pydantic import ValidationError

        from app.schemas.personal_memory import PersonalMemoryForgetRequest

        with pytest.raises(ValidationError):
            PersonalMemoryForgetRequest()

    def test_extra_field_rejected(self) -> None:
        """An unknown field on the forget request is rejected (extra=forbid)."""
        from pydantic import ValidationError

        from app.schemas.personal_memory import PersonalMemoryForgetRequest

        with pytest.raises(ValidationError):
            PersonalMemoryForgetRequest(
                claim_id="00000000-0000-0000-0000-000000000000",
                hard=False,
                bogus_field="not-allowed",
            )


# ═══════════════════════════════════════════════════════════════════════════
# (B) Integration tests — live PostgreSQL
# ═══════════════════════════════════════════════════════════════════════════


# ── Engine + session factory ──────────────────────────────────────────────

_TEST_DATABASE_URL = os.environ["DATABASE_URL"]
# Some .env files use the docker hostname `postgres`; tests on the host
# need `127.0.0.1`. Only swap if it's still the bare docker hostname.
if "@postgres:" in _TEST_DATABASE_URL:
    _TEST_DATABASE_URL = _TEST_DATABASE_URL.replace("@postgres:", "@127.0.0.1:")
_test_engine = create_async_engine(_TEST_DATABASE_URL, echo=False, poolclass=NullPool)
TestSessionLocal = async_sessionmaker(_test_engine, class_=AsyncSession, expire_on_commit=False)


@pytest_asyncio.fixture(scope="session", autouse=True)
async def _manage_engine() -> Any:
    """Dispose test engine after the suite finishes."""
    yield
    await _test_engine.dispose()


@pytest_asyncio.fixture(scope="session", autouse=True)
async def _skip_if_no_db() -> Any:
    """Skip the entire module if PostgreSQL is unreachable."""
    async with TestSessionLocal() as s:
        try:
            await s.execute(text("SELECT 1"))
        except Exception as e:  # pragma: no cover - depends on env
            pytest.skip(f"Database not reachable: {e}")


# ── Test-data factory helpers ────────────────────────────────────────────


def _new_user_id() -> int:
    """Unique user ID (unlikely to collide with real users)."""
    return uuid.uuid4().int % 900_000_000 + 100_000


def _new_workspace_id() -> str:
    return f"ws-pmem-{uuid.uuid4().hex[:24]}"


async def _make_user(session: AsyncSession, *, suffix: str = "owner") -> Any:
    """Insert a fresh User row. Caller is responsible for commit."""
    from app.models.user import User

    uid = _new_user_id()
    user = User(
        id=uid,
        email=f"pmem-svc-{uid}-{suffix}@test.flowmanner.example",
        username=f"pmem_svc_{uid}_{suffix}",
        full_name=f"PMem SVC Test {uid} {suffix}",
        hashed_password="test-hash-not-real",
        is_active=True,
        is_admin=False,
        role="free",
    )
    session.add(user)
    await session.flush()
    return user


async def _make_workspace(session: AsyncSession, *, owner_id: int) -> Any:
    """Insert a fresh Workspace row. Caller is responsible for commit."""
    from app.models.workspace_models import Workspace

    ws = Workspace(
        id=_new_workspace_id(),
        name=f"test-ws-pmem-{uuid.uuid4().hex[:8]}",
        slug=f"test-ws-pmem-{uuid.uuid4().hex[:12]}",
        owner_id=owner_id,
        plan="free",
        is_active=True,
    )
    session.add(ws)
    await session.flush()
    return ws


async def _cleanup_user(user_id: int) -> None:
    """Best-effort cleanup: claims → workspace → user."""
    try:
        async with TestSessionLocal() as cleanup:
            await cleanup.execute(
                text("DELETE FROM personal_memory_claims WHERE user_id = :uid"),
                {"uid": user_id},
            )
            await cleanup.execute(
                text("DELETE FROM workspaces WHERE owner_id = :uid"),
                {"uid": user_id},
            )
            await cleanup.execute(
                text("DELETE FROM users WHERE id = :uid"),
                {"uid": user_id},
            )
            await cleanup.commit()
    except Exception:
        # Best-effort; do not mask the real test error.
        pass


# ── Per-test fixture: single-user, single-workspace context ──────────────


@pytest_asyncio.fixture
async def ctx() -> Any:
    """Yield session, owner User, Workspace; cleanup on teardown.

    The fixture commits the seed (owner + workspace) once so the test
    body can query them. Cleanup of persisted rows (claims/workspace/
    user) runs in a SEPARATE session after the original session is
    closed — this avoids any "async generator already running" race
    between the session's ``__aexit__`` and the cleanup coroutine.

    Test bodies should not leave uncommitted state in ``ctx['session']``
    on the happy path. The recall() method intentionally does not
    commit (per the service rule); if a recall test then closes the
    session without committing, the last_used_at update is rolled
    back — that's fine, the test asserts on the return value, not on
    the persisted last_used_at timestamp.
    """
    session = TestSessionLocal()
    try:
        owner = await _make_user(session, suffix="owner")
        ws = await _make_workspace(session, owner_id=owner.id)
        await session.commit()
        ctx_dict = {"session": session, "owner": owner, "workspace": ws}
        yield ctx_dict
    finally:
        # Close the test session cleanly. If close fails (e.g. async
        # generator race), swallow it — we still want cleanup to run.
        with contextlib.suppress(Exception):
            await session.close()
        await _cleanup_user(owner.id)


# ── Per-test fixture: TWO users + TWO workspaces for the guardrail test ──


@pytest_asyncio.fixture
async def two_workspaces() -> Any:
    """Two workspaces in two different users' ownership.

    Layout:
        user_a  — ws_a
        user_b  — ws_b
    """
    async with TestSessionLocal() as session:
        user_a = await _make_user(session, suffix="alice")
        ws_a = await _make_workspace(session, owner_id=user_a.id)
        user_b = await _make_user(session, suffix="bob")
        ws_b = await _make_workspace(session, owner_id=user_b.id)
        await session.commit()
        ctx_dict = {
            "session": session,
            "user_a": user_a,
            "ws_a": ws_a,
            "user_b": user_b,
            "ws_b": ws_b,
        }
        try:
            yield ctx_dict
        finally:
            await _cleanup_user(user_a.id)
            await _cleanup_user(user_b.id)


# ── (i) create() ─────────────────────────────────────────────────────────


@pytest.mark.integration
async def test_create_persists_all_fields(ctx) -> None:
    """create() persists a row with all explicit fields + correct defaults."""
    from app.services.personal_memory_service import PersonalMemoryService

    service = PersonalMemoryService(ctx["session"])
    claim = await service.create(
        user_id=ctx["owner"].id,
        workspace_id=ctx["workspace"].id,
        subject="user",
        predicate="prefers",
        object={"value": "dark_mode"},
        claim_type="preference",
        scope="personal",
        source_type="user_explicit",
        confidence=0.9,
        importance=0.7,
        sensitivity="sensitive",
    )
    await ctx["session"].commit()

    assert claim.id is not None
    assert claim.user_id == ctx["owner"].id
    assert claim.workspace_id == ctx["workspace"].id
    assert claim.subject == "user"
    assert claim.predicate == "prefers"
    assert claim.object == {"value": "dark_mode"}
    assert claim.claim_type == "preference"
    assert claim.scope == "personal"
    assert claim.source_type == "user_explicit"
    assert claim.confidence == 0.9
    assert claim.importance == 0.7
    assert claim.sensitivity == "sensitive"
    assert claim.deleted_at is None
    assert claim.expires_at is None


@pytest.mark.integration
async def test_create_applies_defaults(ctx) -> None:
    """When only required fields are given, defaults kick in."""
    from app.services.personal_memory_service import PersonalMemoryService

    service = PersonalMemoryService(ctx["session"])
    claim = await service.create(
        user_id=ctx["owner"].id,
        workspace_id=ctx["workspace"].id,
        subject="user",
        predicate="name",
        object={"value": "Alice"},
        claim_type="fact",
        scope="personal",
        source_type="conversation",
    )
    await ctx["session"].commit()

    assert claim.confidence == 0.5
    assert claim.importance == 0.5
    assert claim.sensitivity == "normal"
    assert claim.source_id is None
    assert claim.last_used_at is None
    assert claim.expires_at is None
    assert claim.deleted_at is None


@pytest.mark.integration
async def test_create_rejects_invalid_claim_type(ctx) -> None:
    """Invalid claim_type must raise ValueError (not silently persist)."""
    from app.services.personal_memory_service import PersonalMemoryService

    service = PersonalMemoryService(ctx["session"])
    with pytest.raises(ValueError):
        await service.create(
            user_id=ctx["owner"].id,
            workspace_id=ctx["workspace"].id,
            subject="user",
            predicate="prefers",
            object={"value": "x"},
            claim_type="not_a_type",  # invalid
            scope="personal",
            source_type="user_explicit",
        )


# ── (ii) get() ───────────────────────────────────────────────────────────


@pytest.mark.integration
async def test_get_returns_persisted_row(ctx) -> None:
    from app.services.personal_memory_service import PersonalMemoryService

    service = PersonalMemoryService(ctx["session"])
    created = await service.create(
        user_id=ctx["owner"].id,
        workspace_id=ctx["workspace"].id,
        subject="user",
        predicate="prefers",
        object={"value": "tea"},
        claim_type="preference",
        scope="personal",
        source_type="user_explicit",
    )
    await ctx["session"].commit()

    fetched = await service.get(
        user_id=ctx["owner"].id,
        workspace_id=ctx["workspace"].id,
        claim_id=created.id,
    )
    assert fetched.id == created.id
    assert fetched.subject == "user"
    assert fetched.predicate == "prefers"
    assert fetched.object == {"value": "tea"}


@pytest.mark.integration
async def test_get_raises_not_found_for_unknown_id(ctx) -> None:
    from app.services.personal_memory_service import (
        PersonalMemoryClaimNotFound,
        PersonalMemoryService,
    )

    service = PersonalMemoryService(ctx["session"])
    with pytest.raises(PersonalMemoryClaimNotFound):
        await service.get(
            user_id=ctx["owner"].id,
            workspace_id=ctx["workspace"].id,
            claim_id=uuid.uuid4(),  # never inserted
        )


# ── (iii) list_for_user() ────────────────────────────────────────────────


@pytest.mark.integration
async def test_list_for_user_filters_by_user_and_workspace(ctx) -> None:
    """list_for_user() returns only rows matching (user_id, workspace_id)."""
    from app.services.personal_memory_service import PersonalMemoryService

    service = PersonalMemoryService(ctx["session"])
    await service.create(
        user_id=ctx["owner"].id,
        workspace_id=ctx["workspace"].id,
        subject="user",
        predicate="a",
        object={"v": 1},
        claim_type="fact",
        scope="personal",
        source_type="user_explicit",
    )
    await service.create(
        user_id=ctx["owner"].id,
        workspace_id=ctx["workspace"].id,
        subject="user",
        predicate="b",
        object={"v": 2},
        claim_type="fact",
        scope="personal",
        source_type="user_explicit",
    )
    await ctx["session"].commit()

    items, total = await service.list_for_user(
        user_id=ctx["owner"].id,
        workspace_id=ctx["workspace"].id,
    )
    assert total == 2
    assert len(items) == 2


@pytest.mark.integration
async def test_list_for_user_respects_scope_filter(ctx) -> None:
    from app.services.personal_memory_service import PersonalMemoryService

    service = PersonalMemoryService(ctx["session"])
    for scope, p in [("personal", "a"), ("workspace", "b"), ("program", "c")]:
        await service.create(
            user_id=ctx["owner"].id,
            workspace_id=ctx["workspace"].id,
            subject="user",
            predicate=p,
            object={"v": p},
            claim_type="fact",
            scope=scope,
            source_type="user_explicit",
        )
    await ctx["session"].commit()

    items, total = await service.list_for_user(
        user_id=ctx["owner"].id,
        workspace_id=ctx["workspace"].id,
        scope="personal",
    )
    assert total == 1
    assert items[0].scope == "personal"
    assert items[0].predicate == "a"


@pytest.mark.integration
async def test_list_for_user_respects_claim_type_filter(ctx) -> None:
    from app.services.personal_memory_service import PersonalMemoryService

    service = PersonalMemoryService(ctx["session"])
    await service.create(
        user_id=ctx["owner"].id,
        workspace_id=ctx["workspace"].id,
        subject="user",
        predicate="p1",
        object={"v": 1},
        claim_type="fact",
        scope="personal",
        source_type="user_explicit",
    )
    await service.create(
        user_id=ctx["owner"].id,
        workspace_id=ctx["workspace"].id,
        subject="user",
        predicate="p2",
        object={"v": 2},
        claim_type="preference",
        scope="personal",
        source_type="user_explicit",
    )
    await ctx["session"].commit()

    items, total = await service.list_for_user(
        user_id=ctx["owner"].id,
        workspace_id=ctx["workspace"].id,
        claim_type="preference",
    )
    assert total == 1
    assert items[0].claim_type == "preference"


@pytest.mark.integration
async def test_list_for_user_excludes_soft_deleted_by_default(ctx) -> None:
    """Soft-deleted rows are invisible unless include_deleted=True."""
    from app.services.personal_memory_service import PersonalMemoryService

    service = PersonalMemoryService(ctx["session"])
    keep = await service.create(
        user_id=ctx["owner"].id,
        workspace_id=ctx["workspace"].id,
        subject="user",
        predicate="kept",
        object={"v": 1},
        claim_type="fact",
        scope="personal",
        source_type="user_explicit",
    )
    forgotten = await service.create(
        user_id=ctx["owner"].id,
        workspace_id=ctx["workspace"].id,
        subject="user",
        predicate="forgotten",
        object={"v": 2},
        claim_type="fact",
        scope="personal",
        source_type="user_explicit",
    )
    await ctx["session"].commit()
    await service.forget(
        user_id=ctx["owner"].id,
        workspace_id=ctx["workspace"].id,
        claim_id=forgotten.id,
    )
    await ctx["session"].commit()

    # Default: only the kept one.
    items, total = await service.list_for_user(
        user_id=ctx["owner"].id,
        workspace_id=ctx["workspace"].id,
    )
    assert total == 1
    assert items[0].id == keep.id

    # include_deleted=True: both visible.
    items, total = await service.list_for_user(
        user_id=ctx["owner"].id,
        workspace_id=ctx["workspace"].id,
        include_deleted=True,
    )
    assert total == 2
    ids = {it.id for it in items}
    assert ids == {keep.id, forgotten.id}


# ── (iv) recall() ────────────────────────────────────────────────────────


@pytest.mark.integration
async def test_recall_orders_by_confidence_desc(ctx) -> None:
    """recall() orders results by confidence DESC, importance DESC, last_used_at DESC."""
    from app.services.personal_memory_service import PersonalMemoryService

    service = PersonalMemoryService(ctx["session"])
    await service.create(
        user_id=ctx["owner"].id,
        workspace_id=ctx["workspace"].id,
        subject="user",
        predicate="color",
        object={"v": "red"},
        claim_type="preference",
        scope="personal",
        source_type="user_explicit",
        confidence=0.3,
    )
    await service.create(
        user_id=ctx["owner"].id,
        workspace_id=ctx["workspace"].id,
        subject="user",
        predicate="color",
        object={"v": "blue"},
        claim_type="preference",
        scope="personal",
        source_type="user_explicit",
        confidence=0.9,
    )
    await service.create(
        user_id=ctx["owner"].id,
        workspace_id=ctx["workspace"].id,
        subject="user",
        predicate="color",
        object={"v": "green"},
        claim_type="preference",
        scope="personal",
        source_type="user_explicit",
        confidence=0.6,
    )
    await ctx["session"].commit()

    items, total = await service.recall(
        user_id=ctx["owner"].id,
        workspace_id=ctx["workspace"].id,
        query="color",
    )
    assert total == 3
    assert [it.object["v"] for it in items] == ["blue", "green", "red"]


@pytest.mark.integration
async def test_recall_filters_by_scope_list(ctx) -> None:
    """recall() with scopes=['personal'] excludes workspace-scope claims."""
    from app.services.personal_memory_service import PersonalMemoryService

    service = PersonalMemoryService(ctx["session"])
    await service.create(
        user_id=ctx["owner"].id,
        workspace_id=ctx["workspace"].id,
        subject="user",
        predicate="color",
        object={"v": "red"},
        claim_type="preference",
        scope="personal",
        source_type="user_explicit",
    )
    await service.create(
        user_id=ctx["owner"].id,
        workspace_id=ctx["workspace"].id,
        subject="user",
        predicate="color",
        object={"v": "blue"},
        claim_type="preference",
        scope="workspace",
        source_type="user_explicit",
    )
    await ctx["session"].commit()

    items, total = await service.recall(
        user_id=ctx["owner"].id,
        workspace_id=ctx["workspace"].id,
        query="color",
        scopes=["personal"],
    )
    assert total == 1
    assert items[0].scope == "personal"


@pytest.mark.integration
async def test_recall_updates_last_used_at(ctx) -> None:
    """recall() bumps last_used_at on returned rows."""
    from app.services.personal_memory_service import PersonalMemoryService

    service = PersonalMemoryService(ctx["session"])
    claim = await service.create(
        user_id=ctx["owner"].id,
        workspace_id=ctx["workspace"].id,
        subject="user",
        predicate="color",
        object={"v": "red"},
        claim_type="preference",
        scope="personal",
        source_type="user_explicit",
    )
    await ctx["session"].commit()
    assert claim.last_used_at is None

    items, _ = await service.recall(
        user_id=ctx["owner"].id,
        workspace_id=ctx["workspace"].id,
        query="color",
    )
    await ctx["session"].commit()
    assert items[0].last_used_at is not None
    # And a re-fetch sees the bumped value.
    refreshed = await service.get(
        user_id=ctx["owner"].id,
        workspace_id=ctx["workspace"].id,
        claim_id=claim.id,
    )
    assert refreshed.last_used_at is not None


@pytest.mark.integration
async def test_recall_excludes_expired_rows(ctx) -> None:
    """recall() filters out rows with expires_at < now()."""
    from app.services.personal_memory_service import PersonalMemoryService

    service = PersonalMemoryService(ctx["session"])
    # Already expired.
    past = datetime.now(UTC) - timedelta(days=1)
    await service.create(
        user_id=ctx["owner"].id,
        workspace_id=ctx["workspace"].id,
        subject="user",
        predicate="color",
        object={"v": "red"},
        claim_type="preference",
        scope="personal",
        source_type="user_explicit",
        expires_at=past,
    )
    # Future expiry.
    future = datetime.now(UTC) + timedelta(days=7)
    await service.create(
        user_id=ctx["owner"].id,
        workspace_id=ctx["workspace"].id,
        subject="user",
        predicate="color",
        object={"v": "blue"},
        claim_type="preference",
        scope="personal",
        source_type="user_explicit",
        expires_at=future,
    )
    await ctx["session"].commit()

    items, total = await service.recall(
        user_id=ctx["owner"].id,
        workspace_id=ctx["workspace"].id,
        query="color",
    )
    assert total == 1
    assert items[0].object["v"] == "blue"


# ── (v) forget() ─────────────────────────────────────────────────────────


@pytest.mark.integration
async def test_forget_soft_deletes(ctx) -> None:
    """forget() sets deleted_at; row is still in the table but excluded by default."""
    from app.services.personal_memory_service import PersonalMemoryService

    service = PersonalMemoryService(ctx["session"])
    claim = await service.create(
        user_id=ctx["owner"].id,
        workspace_id=ctx["workspace"].id,
        subject="user",
        predicate="p",
        object={"v": 1},
        claim_type="fact",
        scope="personal",
        source_type="user_explicit",
    )
    await ctx["session"].commit()
    claim_id = claim.id

    forgotten = await service.forget(
        user_id=ctx["owner"].id,
        workspace_id=ctx["workspace"].id,
        claim_id=claim_id,
    )
    await ctx["session"].commit()
    assert forgotten.deleted_at is not None

    # Default listing no longer sees it.
    items, total = await service.list_for_user(
        user_id=ctx["owner"].id,
        workspace_id=ctx["workspace"].id,
    )
    assert total == 0
    assert items == []


@pytest.mark.integration
async def test_forget_is_idempotent(ctx) -> None:
    """forgetting an already-forgotten claim is a no-op (no exception)."""
    from app.services.personal_memory_service import PersonalMemoryService

    service = PersonalMemoryService(ctx["session"])
    claim = await service.create(
        user_id=ctx["owner"].id,
        workspace_id=ctx["workspace"].id,
        subject="user",
        predicate="p",
        object={"v": 1},
        claim_type="fact",
        scope="personal",
        source_type="user_explicit",
    )
    await ctx["session"].commit()
    first = await service.forget(
        user_id=ctx["owner"].id,
        workspace_id=ctx["workspace"].id,
        claim_id=claim.id,
    )
    await ctx["session"].commit()
    first_deleted_at = first.deleted_at

    second = await service.forget(
        user_id=ctx["owner"].id,
        workspace_id=ctx["workspace"].id,
        claim_id=claim.id,
    )
    await ctx["session"].commit()
    # deleted_at preserved (not bumped to a new timestamp).
    assert second.deleted_at == first_deleted_at


@pytest.mark.integration
async def test_forget_hard_removes_row(ctx) -> None:
    """forget(hard=True) actually deletes the row from the table."""
    from app.services.personal_memory_service import (
        PersonalMemoryClaimNotFound,
        PersonalMemoryService,
    )

    service = PersonalMemoryService(ctx["session"])
    claim = await service.create(
        user_id=ctx["owner"].id,
        workspace_id=ctx["workspace"].id,
        subject="user",
        predicate="p",
        object={"v": 1},
        claim_type="fact",
        scope="personal",
        source_type="user_explicit",
    )
    await ctx["session"].commit()
    claim_id = claim.id

    await service.forget(
        user_id=ctx["owner"].id,
        workspace_id=ctx["workspace"].id,
        claim_id=claim_id,
        hard=True,
    )
    await ctx["session"].commit()

    with pytest.raises(PersonalMemoryClaimNotFound):
        await service.get(
            user_id=ctx["owner"].id,
            workspace_id=ctx["workspace"].id,
            claim_id=claim_id,
        )


# ── (vi) update_importance() ─────────────────────────────────────────────


@pytest.mark.integration
async def test_update_importance_persists_new_value(ctx) -> None:
    from app.services.personal_memory_service import PersonalMemoryService

    service = PersonalMemoryService(ctx["session"])
    claim = await service.create(
        user_id=ctx["owner"].id,
        workspace_id=ctx["workspace"].id,
        subject="user",
        predicate="p",
        object={"v": 1},
        claim_type="fact",
        scope="personal",
        source_type="user_explicit",
        importance=0.5,
    )
    await ctx["session"].commit()

    updated = await service.update_importance(
        user_id=ctx["owner"].id,
        workspace_id=ctx["workspace"].id,
        claim_id=claim.id,
        new_importance=0.95,
    )
    await ctx["session"].commit()
    assert updated.importance == 0.95


@pytest.mark.integration
async def test_update_importance_rejects_out_of_range(ctx) -> None:
    from app.services.personal_memory_service import (
        PersonalMemoryService,
        PersonalMemoryValidationError,
    )

    service = PersonalMemoryService(ctx["session"])
    claim = await service.create(
        user_id=ctx["owner"].id,
        workspace_id=ctx["workspace"].id,
        subject="user",
        predicate="p",
        object={"v": 1},
        claim_type="fact",
        scope="personal",
        source_type="user_explicit",
    )
    await ctx["session"].commit()

    with pytest.raises(PersonalMemoryValidationError):
        await service.update_importance(
            user_id=ctx["owner"].id,
            workspace_id=ctx["workspace"].id,
            claim_id=claim.id,
            new_importance=1.5,
        )
    with pytest.raises(PersonalMemoryValidationError):
        await service.update_importance(
            user_id=ctx["owner"].id,
            workspace_id=ctx["workspace"].id,
            claim_id=claim.id,
            new_importance=-0.1,
        )


# ── (vii) update() — PATCH semantics ─────────────────────────────────────


@pytest.mark.integration
async def test_update_applies_patch_fields(ctx) -> None:
    """update() applies only the fields passed in **fields."""
    from app.services.personal_memory_service import PersonalMemoryService

    service = PersonalMemoryService(ctx["session"])
    claim = await service.create(
        user_id=ctx["owner"].id,
        workspace_id=ctx["workspace"].id,
        subject="user",
        predicate="p",
        object={"v": 1},
        claim_type="fact",
        scope="personal",
        source_type="user_explicit",
        confidence=0.5,
        importance=0.5,
    )
    await ctx["session"].commit()

    updated = await service.update(
        user_id=ctx["owner"].id,
        workspace_id=ctx["workspace"].id,
        claim_id=claim.id,
        subject="new subject",
        importance=0.9,
    )
    await ctx["session"].commit()
    assert updated.subject == "new subject"
    assert updated.importance == 0.9
    # Untouched fields keep their original value.
    assert updated.predicate == "p"
    assert updated.confidence == 0.5
    assert updated.object == {"v": 1}


@pytest.mark.integration
async def test_update_rejects_invalid_sensitivity(ctx) -> None:
    """update() rejects a value not in the ALL_SENSITIVITIES tuple."""
    from app.services.personal_memory_service import (
        PersonalMemoryService,
        PersonalMemoryValidationError,
    )

    service = PersonalMemoryService(ctx["session"])
    claim = await service.create(
        user_id=ctx["owner"].id,
        workspace_id=ctx["workspace"].id,
        subject="user",
        predicate="p",
        object={"v": 1},
        claim_type="fact",
        scope="personal",
        source_type="user_explicit",
    )
    await ctx["session"].commit()

    with pytest.raises(PersonalMemoryValidationError):
        await service.update(
            user_id=ctx["owner"].id,
            workspace_id=ctx["workspace"].id,
            claim_id=claim.id,
            sensitivity="ultra_top_secret",
        )


# ── (viii) SECURITY GUARDRAIL — workspace isolation ──────────────────────


@pytest.mark.integration
async def test_guardrail_user_b_cannot_see_user_a_row_in_same_workspace(
    two_workspaces,
) -> None:
    """A row owned by user A in workspace W is INVISIBLE when querying
    as user B in workspace W.

    We seed user A in workspace W with one claim. Then user B, also a
    member-equivalent of W (we just give user B the same workspace_id
    to query with), must NOT see user A's claim.
    """
    from app.services.personal_memory_service import PersonalMemoryService

    # user A inserts a claim in their workspace.
    service_a = PersonalMemoryService(two_workspaces["session"])
    claim_a = await service_a.create(
        user_id=two_workspaces["user_a"].id,
        workspace_id=two_workspaces["ws_a"].id,
        subject="user",
        predicate="secret",
        object={"value": "alice_only"},
        claim_type="fact",
        scope="workspace",
        source_type="user_explicit",
    )
    await two_workspaces["session"].commit()
    assert claim_a.id is not None

    # user B (in a DIFFERENT workspace) queries the SAME workspace_id as A.
    # Guardrail: list_for_user / get / recall must filter by (user_id,
    # workspace_id) together. user B is NOT user A, so user B sees NOTHING.
    service_b = PersonalMemoryService(two_workspaces["session"])

    # 1. list_for_user with workspace=W and user=B → empty.
    items, total = await service_b.list_for_user(
        user_id=two_workspaces["user_b"].id,
        workspace_id=two_workspaces["ws_a"].id,
    )
    assert total == 0
    assert items == []

    # 2. get with workspace=W and user=B → NotFound.
    from app.services.personal_memory_service import PersonalMemoryClaimNotFound

    with pytest.raises(PersonalMemoryClaimNotFound):
        await service_b.get(
            user_id=two_workspaces["user_b"].id,
            workspace_id=two_workspaces["ws_a"].id,
            claim_id=claim_a.id,
        )

    # 3. recall with workspace=W and user=B → empty.
    items, total = await service_b.recall(
        user_id=two_workspaces["user_b"].id,
        workspace_id=two_workspaces["ws_a"].id,
        query="secret",
    )
    assert total == 0
    assert items == []


@pytest.mark.integration
async def test_guardrail_user_a_cannot_see_own_row_in_other_workspace(
    two_workspaces,
) -> None:
    """A row owned by user A in workspace W is INVISIBLE when querying
    as user A in workspace W' (a different workspace).

    The (user_id, workspace_id) composite must be enforced — querying
    with the right user but the wrong workspace is equally a violation.
    """
    from app.services.personal_memory_service import (
        PersonalMemoryClaimNotFound,
        PersonalMemoryService,
    )

    # user A inserts a claim in workspace W_a.
    service_a = PersonalMemoryService(two_workspaces["session"])
    claim_a = await service_a.create(
        user_id=two_workspaces["user_a"].id,
        workspace_id=two_workspaces["ws_a"].id,
        subject="user",
        predicate="secret",
        object={"value": "ws_a_only"},
        claim_type="fact",
        scope="workspace",
        source_type="user_explicit",
    )
    await two_workspaces["session"].commit()
    assert claim_a.id is not None

    # user A now queries with workspace=W_b (the OTHER workspace).
    # Guardrail: even though the user_id matches, the workspace_id
    # mismatch makes the row invisible.
    items, total = await service_a.list_for_user(
        user_id=two_workspaces["user_a"].id,
        workspace_id=two_workspaces["ws_b"].id,
    )
    assert total == 0
    assert items == []

    with pytest.raises(PersonalMemoryClaimNotFound):
        await service_a.get(
            user_id=two_workspaces["user_a"].id,
            workspace_id=two_workspaces["ws_b"].id,
            claim_id=claim_a.id,
        )

    items, total = await service_a.recall(
        user_id=two_workspaces["user_a"].id,
        workspace_id=two_workspaces["ws_b"].id,
        query="secret",
    )
    assert total == 0
    assert items == []
