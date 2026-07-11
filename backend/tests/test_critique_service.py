"""TDD tests for CritiqueService (D30-60, T27 — wire critic to persistence).

All tests use mocked AsyncSession — no live DB. The integration tests
for the actual ``critiques`` table live in ``test_critique_models.py``
(``@pytest.mark.integration``).

Coverage:

* Construction and validation contract (critic_kind enum, score
  clamping, summary truncation)
* Persistence discipline: ``db.add`` + ``db.flush`` called,
  ``db.commit`` NOT called (per services/AGENTS.md rule 3)
* Read-side workspace isolation: ``(user_id, workspace_id)`` filter
  enforced on every read
* Edge cases: empty scores, all-None, NaN, out-of-range, long summary

Run via::

    cd /opt/flowmanner/backend
    DATABASE_URL="postgresql+asyncpg://flowmanner:REDACTED_DB_PASSWORD@127.0.0.1:5432/flowmanner" \\
      .venv/bin/python -m pytest tests/test_critique_service.py -v
"""
from __future__ import annotations

import os
import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest

# Ensure DATABASE_URL is set BEFORE importing app modules that need it.
os.environ.setdefault(
    "DATABASE_URL",
    "postgresql+asyncpg://flowmanner:REDACTED_DB_PASSWORD@127.0.0.1:5432/flowmanner",
)


# ═══════════════════════════════════════════════════════════════════════════
# Helpers
# ═══════════════════════════════════════════════════════════════════════════


def _make_critic_output(**overrides):
    """Build a CriticOutput with sensible defaults for testing."""
    from app.services.critic import CriticOutput

    defaults = dict(
        score_overall=0.7,
        score_alignment=0.8,
        score_safety=0.9,
        score_completeness=0.6,
        summary="Solid plan, missed edge case",
        misses=["did not check race condition"],
        risks=["timeout under load"],
        improvements=[{"description": "add retry", "confidence": 0.7}],
        alternatives=[{"approach": "queue", "tradeoffs": "more deps", "score": 0.6}],
        raw_response={"raw": "..."},
        model_id="deepseek-chat",
        tokens_in=100,
        tokens_out=50,
        duration_ms=200,
    )
    defaults.update(overrides)
    return CriticOutput(**defaults)


def _make_mock_db():
    """Build a mocked AsyncSession. The session's commit() must NOT be
    called by the service (services/AGENTS.md rule 3)."""
    db = MagicMock()
    db.add = MagicMock()
    db.flush = AsyncMock()
    db.commit = MagicMock()
    db.refresh = AsyncMock()
    db.execute = AsyncMock()
    return db


# ═══════════════════════════════════════════════════════════════════════════
# Construction + module surface
# ═══════════════════════════════════════════════════════════════════════════


class TestModuleSurface:
    def test_critique_service_importable(self) -> None:
        from app.services.critique_service import CritiqueService

        assert CritiqueService is not None

    def test_module_exports_critique_not_found(self) -> None:
        from app.services.critique_service import CritiqueNotFound

        assert issubclass(CritiqueNotFound, Exception)

    def test_module_exports_critique_validation_error(self) -> None:
        from app.services.critique_service import CritiqueValidationError

        # Must be both a domain error AND a ValueError (per pattern).
        assert issubclass(CritiqueValidationError, ValueError)

    def test_constructable_with_db(self) -> None:
        from app.services.critique_service import CritiqueService

        db = _make_mock_db()
        svc = CritiqueService(db)
        assert svc is not None


# ═══════════════════════════════════════════════════════════════════════════
# create_from_critic — happy path
# ═══════════════════════════════════════════════════════════════════════════


class TestCreateFromCriticHappyPath:
    async def test_persists_row_with_all_fields(self) -> None:
        from app.services.critique_service import CritiqueService

        db = _make_mock_db()
        svc = CritiqueService(db)
        out = _make_critic_output()
        mission_id = uuid.uuid4()
        result = await svc.create_from_critic(
            user_id=42,
            workspace_id="ws-1",
            mission_id=mission_id,
            critic_output=out,
            critic_kind="critic",
        )
        # The service must call db.add() with a Critique instance.
        assert db.add.called
        added = db.add.call_args[0][0]
        from app.models.critique_models import Critique

        assert isinstance(added, Critique)
        # And the underlying row should have the right identifiers.
        assert added.user_id == 42
        assert added.workspace_id == "ws-1"
        assert added.mission_id == mission_id
        assert added.critic_kind == "critic"
        assert result is added  # service returns the same object

    async def test_optional_program_id_persisted(self) -> None:
        from app.services.critique_service import CritiqueService

        db = _make_mock_db()
        svc = CritiqueService(db)
        program_id = uuid.uuid4()
        await svc.create_from_critic(
            user_id=1,
            workspace_id="ws",
            mission_id=uuid.uuid4(),
            critic_output=_make_critic_output(),
            critic_kind="critic",
            program_id=program_id,
        )
        added = db.add.call_args[0][0]
        assert added.program_id == program_id

    async def test_program_id_none_when_omitted(self) -> None:
        from app.services.critique_service import CritiqueService

        db = _make_mock_db()
        svc = CritiqueService(db)
        await svc.create_from_critic(
            user_id=1,
            workspace_id="ws",
            mission_id=uuid.uuid4(),
            critic_output=_make_critic_output(),
            critic_kind="critic",
        )
        added = db.add.call_args[0][0]
        assert added.program_id is None

    async def test_all_three_critic_kinds_accepted(self) -> None:
        from app.models.critique_models import ALL_CRITIC_KINDS
        from app.services.critique_service import CritiqueService

        for kind in ALL_CRITIC_KINDS:
            db = _make_mock_db()
            svc = CritiqueService(db)
            await svc.create_from_critic(
                user_id=1,
                workspace_id="ws",
                mission_id=uuid.uuid4(),
                critic_output=_make_critic_output(),
                critic_kind=kind,
            )
            added = db.add.call_args[0][0]
            assert added.critic_kind == kind


# ═══════════════════════════════════════════════════════════════════════════
# create_from_critic — discipline
# ═══════════════════════════════════════════════════════════════════════════


class TestCreateFromCriticDiscipline:
    async def test_does_not_commit(self) -> None:
        from app.services.critique_service import CritiqueService

        db = _make_mock_db()
        svc = CritiqueService(db)
        await svc.create_from_critic(
            user_id=1,
            workspace_id="ws",
            mission_id=uuid.uuid4(),
            critic_output=_make_critic_output(),
            critic_kind="critic",
        )
        assert not db.commit.called, (
            "service must NOT call db.commit() — caller owns the "
            "transaction (services/AGENTS.md rule 3)"
        )

    async def test_flushes_for_id_visibility(self) -> None:
        from app.services.critique_service import CritiqueService

        db = _make_mock_db()
        svc = CritiqueService(db)
        await svc.create_from_critic(
            user_id=1,
            workspace_id="ws",
            mission_id=uuid.uuid4(),
            critic_output=_make_critic_output(),
            critic_kind="critic",
        )
        assert db.flush.await_count >= 1, (
            "service must call db.flush() so caller can observe the new id"
        )

    async def test_refreshes_row(self) -> None:
        from app.services.critique_service import CritiqueService

        db = _make_mock_db()
        svc = CritiqueService(db)
        await svc.create_from_critic(
            user_id=1,
            workspace_id="ws",
            mission_id=uuid.uuid4(),
            critic_output=_make_critic_output(),
            critic_kind="critic",
        )
        assert db.refresh.await_count >= 1


# ═══════════════════════════════════════════════════════════════════════════
# create_from_critic — validation contract
# ═══════════════════════════════════════════════════════════════════════════


class TestCreateFromCriticValidation:
    async def test_invalid_critic_kind_raises_value_error(self) -> None:
        from app.services.critique_service import (
            CritiqueService,
            CritiqueValidationError,
        )

        db = _make_mock_db()
        svc = CritiqueService(db)
        with pytest.raises(CritiqueValidationError):
            await svc.create_from_critic(
                user_id=1,
                workspace_id="ws",
                mission_id=uuid.uuid4(),
                critic_output=_make_critic_output(),
                critic_kind="bogus_kind",
            )
        # And nothing should have been added.
        assert not db.add.called

    async def test_score_overall_clamped_above_one(self) -> None:
        from app.services.critique_service import CritiqueService

        db = _make_mock_db()
        svc = CritiqueService(db)
        out = _make_critic_output(score_overall=1.5)
        await svc.create_from_critic(
            user_id=1,
            workspace_id="ws",
            mission_id=uuid.uuid4(),
            critic_output=out,
            critic_kind="critic",
        )
        added = db.add.call_args[0][0]
        assert added.score_overall == 1.0

    async def test_score_overall_clamped_below_zero(self) -> None:
        from app.services.critique_service import CritiqueService

        db = _make_mock_db()
        svc = CritiqueService(db)
        out = _make_critic_output(score_overall=-0.2)
        await svc.create_from_critic(
            user_id=1,
            workspace_id="ws",
            mission_id=uuid.uuid4(),
            critic_output=out,
            critic_kind="critic",
        )
        added = db.add.call_args[0][0]
        assert added.score_overall == 0.0

    async def test_score_none_passes_through(self) -> None:
        from app.services.critique_service import CritiqueService

        db = _make_mock_db()
        svc = CritiqueService(db)
        out = _make_critic_output(
            score_overall=None,
            score_alignment=None,
            score_safety=None,
            score_completeness=None,
        )
        await svc.create_from_critic(
            user_id=1,
            workspace_id="ws",
            mission_id=uuid.uuid4(),
            critic_output=out,
            critic_kind="critic",
        )
        added = db.add.call_args[0][0]
        assert added.score_overall is None
        assert added.score_alignment is None

    async def test_long_summary_truncated(self) -> None:
        from app.services.critique_service import (
            MAX_SUMMARY_CHARS,
            CritiqueService,
        )

        db = _make_mock_db()
        svc = CritiqueService(db)
        long_summary = "x" * (MAX_SUMMARY_CHARS + 500)
        out = _make_critic_output(summary=long_summary)
        await svc.create_from_critic(
            user_id=1,
            workspace_id="ws",
            mission_id=uuid.uuid4(),
            critic_output=out,
            critic_kind="critic",
        )
        added = db.add.call_args[0][0]
        assert len(added.summary) == MAX_SUMMARY_CHARS

    async def test_short_summary_passes_through(self) -> None:
        from app.services.critique_service import CritiqueService

        db = _make_mock_db()
        svc = CritiqueService(db)
        out = _make_critic_output(summary="short and sweet")
        await svc.create_from_critic(
            user_id=1,
            workspace_id="ws",
            mission_id=uuid.uuid4(),
            critic_output=out,
            critic_kind="critic",
        )
        added = db.add.call_args[0][0]
        assert added.summary == "short and sweet"

    async def test_empty_lists_default_to_empty(self) -> None:
        from app.services.critique_service import CritiqueService

        db = _make_mock_db()
        svc = CritiqueService(db)
        out = _make_critic_output(
            misses=[], risks=[], improvements=[], alternatives=[]
        )
        await svc.create_from_critic(
            user_id=1,
            workspace_id="ws",
            mission_id=uuid.uuid4(),
            critic_output=out,
            critic_kind="critic",
        )
        added = db.add.call_args[0][0]
        assert added.misses == []
        assert added.risks == []


# ═══════════════════════════════════════════════════════════════════════════
# get — workspace isolation
# ═══════════════════════════════════════════════════════════════════════════


class TestGetIsolation:
    async def test_get_returns_row_when_scoped(self) -> None:
        from app.services.critique_service import CritiqueService

        db = _make_mock_db()
        fake_row = MagicMock()
        result_mock = MagicMock()
        result_mock.scalar_one_or_none.return_value = fake_row
        db.execute = AsyncMock(return_value=result_mock)
        svc = CritiqueService(db)
        result = await svc.get(
            user_id=1,
            workspace_id="ws",
            critique_id=uuid.uuid4(),
        )
        assert result is fake_row

    async def test_get_raises_not_found_when_no_row(self) -> None:
        from app.services.critique_service import (
            CritiqueNotFound,
            CritiqueService,
        )

        db = _make_mock_db()
        result_mock = MagicMock()
        result_mock.scalar_one_or_none.return_value = None
        db.execute = AsyncMock(return_value=result_mock)
        svc = CritiqueService(db)
        with pytest.raises(CritiqueNotFound):
            await svc.get(
                user_id=1,
                workspace_id="ws",
                critique_id=uuid.uuid4(),
            )

    async def test_get_scopes_query_with_user_and_workspace(self) -> None:
        from app.services.critique_service import CritiqueService

        db = _make_mock_db()
        result_mock = MagicMock()
        result_mock.scalar_one_or_none.return_value = MagicMock()
        db.execute = AsyncMock(return_value=result_mock)
        svc = CritiqueService(db)
        critique_id = uuid.uuid4()
        await svc.get(
            user_id=42,
            workspace_id="ws-99",
            critique_id=critique_id,
        )
        # Inspect the WHERE clause (the second positional arg of execute).
        stmt = db.execute.await_args[0][0]
        compiled = str(stmt.compile(compile_kwargs={"literal_binds": True}))
        assert "user_id" in compiled
        assert "workspace_id" in compiled
        assert "42" in compiled
        assert "ws-99" in compiled


# ═══════════════════════════════════════════════════════════════════════════
# Clamp helper
# ═══════════════════════════════════════════════════════════════════════════


class TestClampHelper:
    def test_clamp_none(self) -> None:
        from app.services.critique_service import _clamp_score

        assert _clamp_score(None) is None

    def test_clamp_in_range(self) -> None:
        from app.services.critique_service import _clamp_score

        assert _clamp_score(0.5) == 0.5

    def test_clamp_above_max(self) -> None:
        from app.services.critique_service import _clamp_score

        assert _clamp_score(2.5) == 1.0

    def test_clamp_below_min(self) -> None:
        from app.services.critique_service import _clamp_score

        assert _clamp_score(-0.3) == 0.0

    def test_clamp_nan_returns_none(self) -> None:
        from app.services.critique_service import _clamp_score

        assert _clamp_score(float("nan")) is None

    def test_clamp_non_numeric_returns_none(self) -> None:
        from app.services.critique_service import _clamp_score

        assert _clamp_score("not a number") is None  # type: ignore[arg-type]
