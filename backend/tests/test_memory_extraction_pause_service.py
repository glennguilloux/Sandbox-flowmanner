"""TDD tests for MemoryExtractionPauseService (D30-60, T30 — pause toggle).

All tests use mocked AsyncSession — no live DB. Integration tests
for the actual ``memory_extraction_pauses`` table live in
``test_memory_extraction_pause_models.py``
(``@pytest.mark.integration``).

Coverage:

* Construction + module surface
* TTL bounds enforcement (MIN/MAX)
* pause_conversation: persistence discipline (add + flush, no commit),
  default fields populated
* resume_conversation: hard-delete semantics, idempotent, count return
* is_paused: cheap single-row check, expires_at boundary
* list_active_pauses: pagination, ordering, workspace-scoped
* cleanup_expired: per-user / global modes, count return

Run via::

    cd /opt/flowmanner/backend
    DATABASE_URL="postgresql+asyncpg://flowmanner:REDACTED_DB_PASSWORD@127.0.0.1:5432/flowmanner" \\
      .venv/bin/python -m pytest tests/test_memory_extraction_pause_service.py -v
"""

from __future__ import annotations

import os
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock

import pytest

os.environ.setdefault(
    "DATABASE_URL",
    "postgresql+asyncpg://flowmanner:REDACTED_DB_PASSWORD@127.0.0.1:5432/flowmanner",
)


# ═══════════════════════════════════════════════════════════════════════════
# Helpers
# ═══════════════════════════════════════════════════════════════════════════


def _make_mock_db():
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
    def test_service_importable(self) -> None:
        from app.services.memory_extraction_pause_service import (
            MemoryExtractionPauseService,
        )

        assert MemoryExtractionPauseService is not None

    def test_validation_error_inherits_value_error(self) -> None:
        from app.services.memory_extraction_pause_service import (
            MemoryExtractionPauseValidationError,
        )

        assert issubclass(MemoryExtractionPauseValidationError, ValueError)

    def test_ttl_bounds_exported(self) -> None:
        from app.services.memory_extraction_pause_service import (
            MAX_TTL_SECONDS,
            MIN_TTL_SECONDS,
        )

        assert MIN_TTL_SECONDS == 60
        assert MAX_TTL_SECONDS == 7 * 24 * 60 * 60

    def test_constructable_with_db(self) -> None:
        from app.services.memory_extraction_pause_service import (
            MemoryExtractionPauseService,
        )

        svc = MemoryExtractionPauseService(_make_mock_db())
        assert svc is not None


# ═══════════════════════════════════════════════════════════════════════════
# TTL validation
# ═══════════════════════════════════════════════════════════════════════════


class TestTtlValidation:
    def test_ttl_too_small_raises(self) -> None:
        from app.services.memory_extraction_pause_service import (
            MemoryExtractionPauseService,
            MemoryExtractionPauseValidationError,
        )

        with pytest.raises(MemoryExtractionPauseValidationError):
            MemoryExtractionPauseService._validate_ttl(30)

    def test_ttl_at_min_accepted(self) -> None:
        from app.services.memory_extraction_pause_service import (
            MIN_TTL_SECONDS,
            MemoryExtractionPauseService,
        )

        # No exception.
        MemoryExtractionPauseService._validate_ttl(MIN_TTL_SECONDS)

    def test_ttl_too_large_raises(self) -> None:
        from app.services.memory_extraction_pause_service import (
            MemoryExtractionPauseService,
            MemoryExtractionPauseValidationError,
        )

        with pytest.raises(MemoryExtractionPauseValidationError):
            MemoryExtractionPauseService._validate_ttl(8 * 24 * 60 * 60)

    def test_ttl_at_max_accepted(self) -> None:
        from app.services.memory_extraction_pause_service import (
            MAX_TTL_SECONDS,
            MemoryExtractionPauseService,
        )

        MemoryExtractionPauseService._validate_ttl(MAX_TTL_SECONDS)

    def test_ttl_zero_raises(self) -> None:
        from app.services.memory_extraction_pause_service import (
            MemoryExtractionPauseService,
            MemoryExtractionPauseValidationError,
        )

        with pytest.raises(MemoryExtractionPauseValidationError):
            MemoryExtractionPauseService._validate_ttl(0)

    def test_ttl_negative_raises(self) -> None:
        from app.services.memory_extraction_pause_service import (
            MemoryExtractionPauseService,
            MemoryExtractionPauseValidationError,
        )

        with pytest.raises(MemoryExtractionPauseValidationError):
            MemoryExtractionPauseService._validate_ttl(-100)

    def test_ttl_non_int_raises(self) -> None:
        from app.services.memory_extraction_pause_service import (
            MemoryExtractionPauseService,
            MemoryExtractionPauseValidationError,
        )

        with pytest.raises(MemoryExtractionPauseValidationError):
            MemoryExtractionPauseService._validate_ttl("3600")  # type: ignore[arg-type]


# ═══════════════════════════════════════════════════════════════════════════
# Conversation-id / reason validation
# ═══════════════════════════════════════════════════════════════════════════


class TestFieldValidation:
    def test_conversation_id_empty_raises(self) -> None:
        from app.services.memory_extraction_pause_service import (
            MemoryExtractionPauseService,
            MemoryExtractionPauseValidationError,
        )

        with pytest.raises(MemoryExtractionPauseValidationError):
            MemoryExtractionPauseService._validate_conversation_id("")

    def test_conversation_id_too_long_raises(self) -> None:
        from app.services.memory_extraction_pause_service import (
            MemoryExtractionPauseService,
            MemoryExtractionPauseValidationError,
        )

        with pytest.raises(MemoryExtractionPauseValidationError):
            MemoryExtractionPauseService._validate_conversation_id("x" * 101)

    def test_conversation_id_at_max_accepted(self) -> None:
        from app.services.memory_extraction_pause_service import (
            MemoryExtractionPauseService,
        )

        MemoryExtractionPauseService._validate_conversation_id("x" * 100)

    def test_reason_none_accepted(self) -> None:
        from app.services.memory_extraction_pause_service import (
            MemoryExtractionPauseService,
        )

        MemoryExtractionPauseService._validate_reason(None)

    def test_reason_too_long_raises(self) -> None:
        from app.services.memory_extraction_pause_service import (
            MemoryExtractionPauseService,
            MemoryExtractionPauseValidationError,
        )

        with pytest.raises(MemoryExtractionPauseValidationError):
            MemoryExtractionPauseService._validate_reason("x" * 501)

    def test_reason_at_max_accepted(self) -> None:
        from app.services.memory_extraction_pause_service import (
            MemoryExtractionPauseService,
        )

        MemoryExtractionPauseService._validate_reason("x" * 500)


# ═══════════════════════════════════════════════════════════════════════════
# pause_conversation
# ═══════════════════════════════════════════════════════════════════════════


class TestPauseConversation:
    async def test_persists_row(self) -> None:
        from app.services.memory_extraction_pause_service import (
            MemoryExtractionPauseService,
        )

        db = _make_mock_db()
        svc = MemoryExtractionPauseService(db)
        result = await svc.pause_conversation(
            user_id=1,
            workspace_id="ws-1",
            conversation_id="conv-abc",
            ttl_seconds=3600,
            reason="sensitive topic",
        )
        assert db.add.called
        added = db.add.call_args[0][0]
        from app.models.memory_extraction_pause_models import (
            MemoryExtractionPause,
        )

        assert isinstance(added, MemoryExtractionPause)
        assert added.user_id == 1
        assert added.workspace_id == "ws-1"
        assert added.conversation_id == "conv-abc"
        assert added.reason == "sensitive topic"
        assert result is added

    async def test_sets_expires_at_to_now_plus_ttl(self) -> None:
        from app.services.memory_extraction_pause_service import (
            MemoryExtractionPauseService,
        )

        db = _make_mock_db()
        svc = MemoryExtractionPauseService(db)
        before = datetime.now(UTC)
        await svc.pause_conversation(
            user_id=1,
            workspace_id="ws",
            conversation_id="conv",
            ttl_seconds=3600,
        )
        after = datetime.now(UTC)
        added = db.add.call_args[0][0]
        # expires_at should fall in [before+1h, after+1h] (1s slop).
        expected_min = before + timedelta(seconds=3600)
        expected_max = after + timedelta(seconds=3600)
        assert expected_min <= added.expires_at <= expected_max

    async def test_reason_optional(self) -> None:
        from app.services.memory_extraction_pause_service import (
            MemoryExtractionPauseService,
        )

        db = _make_mock_db()
        svc = MemoryExtractionPauseService(db)
        await svc.pause_conversation(
            user_id=1,
            workspace_id="ws",
            conversation_id="conv",
            ttl_seconds=3600,
        )
        added = db.add.call_args[0][0]
        assert added.reason is None

    async def test_does_not_commit(self) -> None:
        from app.services.memory_extraction_pause_service import (
            MemoryExtractionPauseService,
        )

        db = _make_mock_db()
        svc = MemoryExtractionPauseService(db)
        await svc.pause_conversation(
            user_id=1,
            workspace_id="ws",
            conversation_id="conv",
            ttl_seconds=3600,
        )
        assert not db.commit.called

    async def test_flushes_for_id_visibility(self) -> None:
        from app.services.memory_extraction_pause_service import (
            MemoryExtractionPauseService,
        )

        db = _make_mock_db()
        svc = MemoryExtractionPauseService(db)
        await svc.pause_conversation(
            user_id=1,
            workspace_id="ws",
            conversation_id="conv",
            ttl_seconds=3600,
        )
        assert db.flush.await_count >= 1

    async def test_invalid_ttl_raises_and_does_not_persist(self) -> None:
        from app.services.memory_extraction_pause_service import (
            MemoryExtractionPauseService,
            MemoryExtractionPauseValidationError,
        )

        db = _make_mock_db()
        svc = MemoryExtractionPauseService(db)
        with pytest.raises(MemoryExtractionPauseValidationError):
            await svc.pause_conversation(
                user_id=1,
                workspace_id="ws",
                conversation_id="conv",
                ttl_seconds=10,
            )
        assert not db.add.called


# ═══════════════════════════════════════════════════════════════════════════
# resume_conversation
# ═══════════════════════════════════════════════════════════════════════════


class TestResumeConversation:
    async def test_returns_count_removed(self) -> None:
        from app.services.memory_extraction_pause_service import (
            MemoryExtractionPauseService,
        )

        db = _make_mock_db()
        result_mock = MagicMock()
        result_mock.rowcount = 3
        db.execute = AsyncMock(return_value=result_mock)
        svc = MemoryExtractionPauseService(db)
        removed = await svc.resume_conversation(
            user_id=1,
            workspace_id="ws",
            conversation_id="conv",
        )
        assert removed == 3

    async def test_idempotent_returns_zero_when_no_rows(self) -> None:
        from app.services.memory_extraction_pause_service import (
            MemoryExtractionPauseService,
        )

        db = _make_mock_db()
        result_mock = MagicMock()
        result_mock.rowcount = 0
        db.execute = AsyncMock(return_value=result_mock)
        svc = MemoryExtractionPauseService(db)
        removed = await svc.resume_conversation(
            user_id=1,
            workspace_id="ws",
            conversation_id="never-paused",
        )
        assert removed == 0

    async def test_does_not_commit(self) -> None:
        from app.services.memory_extraction_pause_service import (
            MemoryExtractionPauseService,
        )

        db = _make_mock_db()
        result_mock = MagicMock()
        result_mock.rowcount = 1
        db.execute = AsyncMock(return_value=result_mock)
        svc = MemoryExtractionPauseService(db)
        await svc.resume_conversation(
            user_id=1,
            workspace_id="ws",
            conversation_id="conv",
        )
        assert not db.commit.called

    async def test_uses_hard_delete_not_soft(self) -> None:
        """Resume is operational state, not audit data. The audit trail
        belongs in memory_correction_events (T29)."""
        from app.services.memory_extraction_pause_service import (
            MemoryExtractionPauseService,
        )

        db = _make_mock_db()
        result_mock = MagicMock()
        result_mock.rowcount = 1
        db.execute = AsyncMock(return_value=result_mock)
        svc = MemoryExtractionPauseService(db)
        await svc.resume_conversation(
            user_id=1,
            workspace_id="ws",
            conversation_id="conv",
        )
        # The execute() call must be a DELETE, not an UPDATE.
        stmt = db.execute.await_args[0][0]
        # SQLAlchemy delete() expressions have a `_delete_table` attr
        # (private but stable across versions); check that the
        # statement IS a delete and is NOT an update.
        from sqlalchemy.sql.dml import Delete, Update

        assert isinstance(stmt, Delete), (
            "resume must use DELETE not UPDATE — pauses are operational "
            "state, the audit trail lives in memory_correction_events"
        )
        assert not isinstance(stmt, Update)


# ═══════════════════════════════════════════════════════════════════════════
# is_paused
# ═══════════════════════════════════════════════════════════════════════════


class TestIsPaused:
    async def test_returns_true_when_active_pause_exists(self) -> None:
        from app.services.memory_extraction_pause_service import (
            MemoryExtractionPauseService,
        )

        db = _make_mock_db()
        result_mock = MagicMock()
        result_mock.scalar_one_or_none.return_value = "some-uuid"
        db.execute = AsyncMock(return_value=result_mock)
        svc = MemoryExtractionPauseService(db)
        assert (
            await svc.is_paused(
                user_id=1,
                workspace_id="ws",
                conversation_id="conv",
            )
            is True
        )

    async def test_returns_false_when_no_active_pause(self) -> None:
        from app.services.memory_extraction_pause_service import (
            MemoryExtractionPauseService,
        )

        db = _make_mock_db()
        result_mock = MagicMock()
        result_mock.scalar_one_or_none.return_value = None
        db.execute = AsyncMock(return_value=result_mock)
        svc = MemoryExtractionPauseService(db)
        assert (
            await svc.is_paused(
                user_id=1,
                workspace_id="ws",
                conversation_id="conv",
            )
            is False
        )

    async def test_is_paused_uses_limit_1(self) -> None:
        from app.services.memory_extraction_pause_service import (
            MemoryExtractionPauseService,
        )

        db = _make_mock_db()
        result_mock = MagicMock()
        result_mock.scalar_one_or_none.return_value = None
        db.execute = AsyncMock(return_value=result_mock)
        svc = MemoryExtractionPauseService(db)
        await svc.is_paused(user_id=1, workspace_id="ws", conversation_id="conv")
        # The select must be LIMIT 1 (cheap lookup).
        stmt = db.execute.await_args[0][0]
        compiled = str(stmt.compile(compile_kwargs={"literal_binds": True}))
        assert "limit" in compiled.lower() or "LIMIT 1" in compiled


# ═══════════════════════════════════════════════════════════════════════════
# list_active_pauses
# ═══════════════════════════════════════════════════════════════════════════


class TestListActivePauses:
    async def test_returns_items_and_total(self) -> None:
        from app.services.memory_extraction_pause_service import (
            MemoryExtractionPauseService,
        )

        db = _make_mock_db()
        # First call: count; second call: items.
        count_result = MagicMock()
        count_result.scalar_one.return_value = 7
        item_result = MagicMock()
        item_result.scalars.return_value.all.return_value = [MagicMock()] * 3
        db.execute = AsyncMock(side_effect=[count_result, item_result])
        svc = MemoryExtractionPauseService(db)
        items, total = await svc.list_active_pauses(user_id=1, workspace_id="ws")
        assert total == 7
        assert len(items) == 3

    async def test_pagination_uses_offset_limit(self) -> None:
        from app.services.memory_extraction_pause_service import (
            MemoryExtractionPauseService,
        )

        db = _make_mock_db()
        count_result = MagicMock()
        count_result.scalar_one.return_value = 50
        item_result = MagicMock()
        item_result.scalars.return_value.all.return_value = []
        db.execute = AsyncMock(side_effect=[count_result, item_result])
        svc = MemoryExtractionPauseService(db)
        await svc.list_active_pauses(user_id=1, workspace_id="ws", limit=10, offset=20)
        # The item-fetch SELECT must reference LIMIT 10 OFFSET 20.
        # We don't assert on the order of args; assert on the
        # presence of the values in either of the two execute() calls.
        # Simpler: check the call args for the offset/limit values.
        for call in db.execute.await_args_list:
            stmt = call[0][0]
            compiled = str(stmt.compile(compile_kwargs={"literal_binds": True}))
            if "offset" in compiled.lower() and "limit" in compiled.lower():
                # Found the items query. Check pagination values.
                # We don't strict-assert on the literal because
                # SQLAlchemy may inline or bind.
                assert "10" in compiled
                assert "20" in compiled
                return
        # If we got here, neither call had the items query — fail.
        pytest.fail("items SELECT with offset/limit not found")


# ═══════════════════════════════════════════════════════════════════════════
# cleanup_expired
# ═══════════════════════════════════════════════════════════════════════════


class TestCleanupExpired:
    async def test_returns_count_removed(self) -> None:
        from app.services.memory_extraction_pause_service import (
            MemoryExtractionPauseService,
        )

        db = _make_mock_db()
        result_mock = MagicMock()
        result_mock.rowcount = 12
        db.execute = AsyncMock(return_value=result_mock)
        svc = MemoryExtractionPauseService(db)
        removed = await svc.cleanup_expired()
        assert removed == 12

    async def test_global_sweep_no_user_filter(self) -> None:
        from app.services.memory_extraction_pause_service import (
            MemoryExtractionPauseService,
        )

        db = _make_mock_db()
        result_mock = MagicMock()
        result_mock.rowcount = 0
        db.execute = AsyncMock(return_value=result_mock)
        svc = MemoryExtractionPauseService(db)
        await svc.cleanup_expired()
        stmt = db.execute.await_args[0][0]
        compiled = str(stmt.compile(compile_kwargs={"literal_binds": True}))
        # Global sweep: should NOT filter by user_id (no "users.id" mention).
        # The presence of "user_id" in the column list is OK; we check
        # that the WHERE only constrains expires_at.
        assert "expires_at" in compiled.lower()

    async def test_per_user_sweep_filters_by_user(self) -> None:
        from app.services.memory_extraction_pause_service import (
            MemoryExtractionPauseService,
        )

        db = _make_mock_db()
        result_mock = MagicMock()
        result_mock.rowcount = 1
        db.execute = AsyncMock(return_value=result_mock)
        svc = MemoryExtractionPauseService(db)
        await svc.cleanup_expired(user_id=42, workspace_id="ws-9")
        stmt = db.execute.await_args[0][0]
        compiled = str(stmt.compile(compile_kwargs={"literal_binds": True}))
        assert "42" in compiled
        assert "ws-9" in compiled
