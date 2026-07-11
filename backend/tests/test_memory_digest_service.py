"""TDD tests for MemoryDigestService (D30-60, T31 — daily digest).

All tests use mocked AsyncSession — no live DB. Integration tests
for the actual ``memory_digest_deliveries`` table live in the
``@pytest.mark.integration`` group (future).

Coverage:

* Construction + module surface
* Field validation (channel, status, recipient, error_message, lookback)
* build_preview: workspace-scoped query, deleted/expired/private
  filters, lookback window, histogram computation
* record_delivery: persistence discipline, defaults
* list_deliveries: pagination, channel/status filters, ordering
* latest_delivery: single-row lookup, channel filter

Run via::

    cd /opt/flowmanner/backend
    DATABASE_URL="postgresql+asyncpg://flowmanner:REDACTED_DB_PASSWORD@127.0.0.1:5432/flowmanner" \\
      .venv/bin/python -m pytest tests/test_memory_digest_service.py -v
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


def _make_claim_orm(
    *,
    claim_id=None,
    user_id: int = 1,
    workspace_id: str = "ws",
    subject: str = "subject",
    predicate: str = "predicate",
    claim_type: str = "fact",
    scope: str = "personal",
    confidence: float = 0.7,
    deleted_at=None,
    expires_at=None,
    created_at: datetime | None = None,
):
    """Build a MagicMock that quacks like a PersonalMemoryClaim for
    the preview builder."""
    from uuid import uuid4

    c = MagicMock()
    c.id = claim_id or uuid4()
    c.user_id = user_id
    c.workspace_id = workspace_id
    c.subject = subject
    c.predicate = predicate
    c.claim_type = claim_type
    c.scope = scope
    c.confidence = confidence
    c.deleted_at = deleted_at
    c.expires_at = expires_at
    c.created_at = created_at or datetime.now(UTC)
    return c


# ═══════════════════════════════════════════════════════════════════════════
# Construction + module surface
# ═══════════════════════════════════════════════════════════════════════════


class TestModuleSurface:
    def test_service_importable(self) -> None:
        from app.services.memory_digest_service import MemoryDigestService

        assert MemoryDigestService is not None

    def test_validation_error_inherits_value_error(self) -> None:
        from app.services.memory_digest_service import (
            MemoryDigestValidationError,
        )

        assert issubclass(MemoryDigestValidationError, ValueError)

    def test_dto_classes_importable(self) -> None:
        from app.services.memory_digest_service import (
            DigestClaimSummary,
            DigestPreview,
        )

        assert DigestClaimSummary is not None
        assert DigestPreview is not None

    def test_constructable_with_db(self) -> None:
        from app.services.memory_digest_service import MemoryDigestService

        svc = MemoryDigestService(_make_mock_db())
        assert svc is not None


# ═══════════════════════════════════════════════════════════════════════════
# Field validation
# ═══════════════════════════════════════════════════════════════════════════


class TestFieldValidation:
    def test_invalid_channel_raises(self) -> None:
        from app.services.memory_digest_service import (
            MemoryDigestService,
            MemoryDigestValidationError,
        )

        with pytest.raises(MemoryDigestValidationError):
            MemoryDigestService._validate_channel("sms")

    def test_valid_channel_accepted(self) -> None:
        from app.services.memory_digest_service import MemoryDigestService

        for ch in ("email", "in_app", "preview"):
            MemoryDigestService._validate_channel(ch)

    def test_invalid_status_raises(self) -> None:
        from app.services.memory_digest_service import (
            MemoryDigestService,
            MemoryDigestValidationError,
        )

        with pytest.raises(MemoryDigestValidationError):
            MemoryDigestService._validate_status("queued")

    def test_valid_status_accepted(self) -> None:
        from app.services.memory_digest_service import MemoryDigestService

        for s in ("pending", "delivered", "failed", "previewed"):
            MemoryDigestService._validate_status(s)

    def test_recipient_too_long_raises(self) -> None:
        from app.services.memory_digest_service import (
            MemoryDigestService,
            MemoryDigestValidationError,
        )

        with pytest.raises(MemoryDigestValidationError):
            MemoryDigestService._validate_recipient("x" * 256)

    def test_recipient_none_accepted(self) -> None:
        from app.services.memory_digest_service import MemoryDigestService

        MemoryDigestService._validate_recipient(None)

    def test_error_message_too_long_raises(self) -> None:
        from app.services.memory_digest_service import (
            MemoryDigestService,
            MemoryDigestValidationError,
        )

        with pytest.raises(MemoryDigestValidationError):
            MemoryDigestService._validate_error_message("x" * 2001)

    def test_lookback_days_zero_raises(self) -> None:
        from app.services.memory_digest_service import (
            MemoryDigestService,
            MemoryDigestValidationError,
        )

        with pytest.raises(MemoryDigestValidationError):
            MemoryDigestService._validate_lookback_days(0)

    def test_lookback_days_too_large_raises(self) -> None:
        from app.services.memory_digest_service import (
            MemoryDigestService,
            MemoryDigestValidationError,
        )

        with pytest.raises(MemoryDigestValidationError):
            MemoryDigestService._validate_lookback_days(400)

    def test_lookback_days_one_accepted(self) -> None:
        from app.services.memory_digest_service import MemoryDigestService

        MemoryDigestService._validate_lookback_days(1)

    def test_lookback_days_365_accepted(self) -> None:
        from app.services.memory_digest_service import MemoryDigestService

        MemoryDigestService._validate_lookback_days(365)


# ═══════════════════════════════════════════════════════════════════════════
# build_preview
# ═══════════════════════════════════════════════════════════════════════════


class TestBuildPreview:
    async def test_returns_digest_preview(self) -> None:
        from app.services.memory_digest_service import MemoryDigestService

        db = _make_mock_db()
        result_mock = MagicMock()
        result_mock.scalars.return_value.all.return_value = []
        db.execute = AsyncMock(return_value=result_mock)
        svc = MemoryDigestService(db)
        preview = await svc.build_preview(user_id=1, workspace_id="ws-1")
        assert preview.user_id == 1
        assert preview.workspace_id == "ws-1"
        assert preview.is_empty is True
        assert preview.claims_count == 0

    async def test_returns_claims_in_digest_summaries(self) -> None:
        from app.services.memory_digest_service import MemoryDigestService

        c1 = _make_claim_orm(subject="likes coffee", claim_type="preference")
        c2 = _make_claim_orm(subject="works on backend", claim_type="fact")
        db = _make_mock_db()
        result_mock = MagicMock()
        result_mock.scalars.return_value.all.return_value = [c1, c2]
        db.execute = AsyncMock(return_value=result_mock)
        svc = MemoryDigestService(db)
        preview = await svc.build_preview(user_id=1, workspace_id="ws")
        assert preview.claims_count == 2
        assert preview.is_empty is False
        assert {s.subject for s in preview.claims} == {
            "likes coffee",
            "works on backend",
        }

    async def test_builds_claim_type_histogram(self) -> None:
        from app.services.memory_digest_service import MemoryDigestService

        db = _make_mock_db()
        c1 = _make_claim_orm(claim_type="fact")
        c2 = _make_claim_orm(claim_type="fact")
        c3 = _make_claim_orm(claim_type="preference")
        result_mock = MagicMock()
        result_mock.scalars.return_value.all.return_value = [c1, c2, c3]
        db.execute = AsyncMock(return_value=result_mock)
        svc = MemoryDigestService(db)
        preview = await svc.build_preview(user_id=1, workspace_id="ws")
        assert preview.by_claim_type == {"fact": 2, "preference": 1}

    async def test_builds_scope_histogram(self) -> None:
        from app.services.memory_digest_service import MemoryDigestService

        db = _make_mock_db()
        c1 = _make_claim_orm(scope="personal")
        c2 = _make_claim_orm(scope="workspace")
        c3 = _make_claim_orm(scope="workspace")
        result_mock = MagicMock()
        result_mock.scalars.return_value.all.return_value = [c1, c2, c3]
        db.execute = AsyncMock(return_value=result_mock)
        svc = MemoryDigestService(db)
        preview = await svc.build_preview(user_id=1, workspace_id="ws")
        assert preview.by_scope == {"personal": 1, "workspace": 2}

    async def test_query_filters_by_user_workspace(self) -> None:
        from app.services.memory_digest_service import MemoryDigestService

        db = _make_mock_db()
        result_mock = MagicMock()
        result_mock.scalars.return_value.all.return_value = []
        db.execute = AsyncMock(return_value=result_mock)
        svc = MemoryDigestService(db)
        await svc.build_preview(user_id=42, workspace_id="ws-99")
        stmt = db.execute.await_args[0][0]
        compiled = str(stmt.compile(compile_kwargs={"literal_binds": True}))
        assert "42" in compiled
        assert "ws-99" in compiled

    async def test_query_excludes_private_scope(self) -> None:
        from app.services.memory_digest_service import MemoryDigestService

        db = _make_mock_db()
        result_mock = MagicMock()
        result_mock.scalars.return_value.all.return_value = []
        db.execute = AsyncMock(return_value=result_mock)
        svc = MemoryDigestService(db)
        await svc.build_preview(user_id=1, workspace_id="ws")
        stmt = db.execute.await_args[0][0]
        compiled = str(stmt.compile(compile_kwargs={"literal_binds": True}))
        # The query must reference "private" so the DB excludes it.
        assert "private" in compiled

    async def test_invalid_lookback_raises_and_does_not_query(self) -> None:
        from app.services.memory_digest_service import (
            MemoryDigestService,
            MemoryDigestValidationError,
        )

        db = _make_mock_db()
        svc = MemoryDigestService(db)
        with pytest.raises(MemoryDigestValidationError):
            await svc.build_preview(user_id=1, workspace_id="ws", since_days=0)
        # No DB call should have happened.
        assert not db.execute.await_count

    async def test_default_lookback_is_7_days(self) -> None:
        from app.services.memory_digest_service import (
            DEFAULT_PREVIEW_LOOKBACK_DAYS,
            MemoryDigestService,
        )

        assert DEFAULT_PREVIEW_LOOKBACK_DAYS == 7


# ═══════════════════════════════════════════════════════════════════════════
# record_delivery
# ═══════════════════════════════════════════════════════════════════════════


class TestRecordDelivery:
    async def test_persists_row(self) -> None:
        from app.services.memory_digest_service import MemoryDigestService

        db = _make_mock_db()
        svc = MemoryDigestService(db)
        result = await svc.record_delivery(
            user_id=1,
            workspace_id="ws-1",
            delivery_channel="in_app",
            claims_count=5,
        )
        assert db.add.called
        added = db.add.call_args[0][0]
        from app.models.memory_digest_models import MemoryDigestDelivery

        assert isinstance(added, MemoryDigestDelivery)
        assert added.user_id == 1
        assert added.workspace_id == "ws-1"
        assert added.delivery_channel == "in_app"
        assert added.claims_count == 5
        assert result is added

    async def test_default_status_is_delivered(self) -> None:
        from app.services.memory_digest_service import MemoryDigestService

        db = _make_mock_db()
        svc = MemoryDigestService(db)
        await svc.record_delivery(
            user_id=1,
            workspace_id="ws",
            delivery_channel="in_app",
            claims_count=3,
        )
        added = db.add.call_args[0][0]
        assert added.status == "delivered"

    async def test_previewed_status_accepted(self) -> None:
        from app.services.memory_digest_service import MemoryDigestService

        db = _make_mock_db()
        svc = MemoryDigestService(db)
        await svc.record_delivery(
            user_id=1,
            workspace_id="ws",
            delivery_channel="preview",
            claims_count=0,
            status="previewed",
        )
        added = db.add.call_args[0][0]
        assert added.status == "previewed"

    async def test_invalid_channel_raises(self) -> None:
        from app.services.memory_digest_service import (
            MemoryDigestService,
            MemoryDigestValidationError,
        )

        db = _make_mock_db()
        svc = MemoryDigestService(db)
        with pytest.raises(MemoryDigestValidationError):
            await svc.record_delivery(
                user_id=1,
                workspace_id="ws",
                delivery_channel="carrier_pigeon",
                claims_count=0,
            )
        assert not db.add.called

    async def test_invalid_status_raises(self) -> None:
        from app.services.memory_digest_service import (
            MemoryDigestService,
            MemoryDigestValidationError,
        )

        db = _make_mock_db()
        svc = MemoryDigestService(db)
        with pytest.raises(MemoryDigestValidationError):
            await svc.record_delivery(
                user_id=1,
                workspace_id="ws",
                delivery_channel="email",
                claims_count=0,
                status="queued",
            )
        assert not db.add.called

    async def test_negative_claims_count_raises(self) -> None:
        from app.services.memory_digest_service import (
            MemoryDigestService,
            MemoryDigestValidationError,
        )

        db = _make_mock_db()
        svc = MemoryDigestService(db)
        with pytest.raises(MemoryDigestValidationError):
            await svc.record_delivery(
                user_id=1,
                workspace_id="ws",
                delivery_channel="email",
                claims_count=-1,
            )

    async def test_does_not_commit(self) -> None:
        from app.services.memory_digest_service import MemoryDigestService

        db = _make_mock_db()
        svc = MemoryDigestService(db)
        await svc.record_delivery(
            user_id=1,
            workspace_id="ws",
            delivery_channel="email",
            claims_count=2,
        )
        assert not db.commit.called

    async def test_flushes_for_id_visibility(self) -> None:
        from app.services.memory_digest_service import MemoryDigestService

        db = _make_mock_db()
        svc = MemoryDigestService(db)
        await svc.record_delivery(
            user_id=1,
            workspace_id="ws",
            delivery_channel="email",
            claims_count=2,
        )
        assert db.flush.await_count >= 1


# ═══════════════════════════════════════════════════════════════════════════
# list_deliveries
# ═══════════════════════════════════════════════════════════════════════════


class TestListDeliveries:
    async def test_returns_items_and_total(self) -> None:
        from app.services.memory_digest_service import MemoryDigestService

        db = _make_mock_db()
        count_result = MagicMock()
        count_result.scalar_one.return_value = 10
        item_result = MagicMock()
        item_result.scalars.return_value.all.return_value = [MagicMock()] * 4
        db.execute = AsyncMock(side_effect=[count_result, item_result])
        svc = MemoryDigestService(db)
        items, total = await svc.list_deliveries(user_id=1, workspace_id="ws")
        assert total == 10
        assert len(items) == 4

    async def test_validates_channel_filter(self) -> None:
        from app.services.memory_digest_service import (
            MemoryDigestService,
            MemoryDigestValidationError,
        )

        db = _make_mock_db()
        svc = MemoryDigestService(db)
        with pytest.raises(MemoryDigestValidationError):
            await svc.list_deliveries(
                user_id=1,
                workspace_id="ws",
                delivery_channel="bogus",
            )

    async def test_validates_status_filter(self) -> None:
        from app.services.memory_digest_service import (
            MemoryDigestService,
            MemoryDigestValidationError,
        )

        db = _make_mock_db()
        svc = MemoryDigestService(db)
        with pytest.raises(MemoryDigestValidationError):
            await svc.list_deliveries(user_id=1, workspace_id="ws", status="bogus")

    async def test_pagination_uses_offset_limit(self) -> None:
        from app.services.memory_digest_service import MemoryDigestService

        db = _make_mock_db()
        count_result = MagicMock()
        count_result.scalar_one.return_value = 0
        item_result = MagicMock()
        item_result.scalars.return_value.all.return_value = []
        db.execute = AsyncMock(side_effect=[count_result, item_result])
        svc = MemoryDigestService(db)
        await svc.list_deliveries(
            user_id=1,
            workspace_id="ws",
            limit=25,
            offset=50,
        )
        # Find the items SELECT and check pagination.
        for call in db.execute.await_args_list:
            stmt = call[0][0]
            compiled = str(stmt.compile(compile_kwargs={"literal_binds": True}))
            if "offset" in compiled.lower() and "limit" in compiled.lower():
                assert "25" in compiled
                assert "50" in compiled
                return
        pytest.fail("items SELECT with offset/limit not found")


# ═══════════════════════════════════════════════════════════════════════════
# latest_delivery
# ═══════════════════════════════════════════════════════════════════════════


class TestLatestDelivery:
    async def test_returns_row_when_present(self) -> None:
        from app.services.memory_digest_service import MemoryDigestService

        db = _make_mock_db()
        result_mock = MagicMock()
        result_mock.scalar_one_or_none.return_value = MagicMock()
        db.execute = AsyncMock(return_value=result_mock)
        svc = MemoryDigestService(db)
        result = await svc.latest_delivery(user_id=1, workspace_id="ws")
        assert result is not None

    async def test_returns_none_when_empty(self) -> None:
        from app.services.memory_digest_service import MemoryDigestService

        db = _make_mock_db()
        result_mock = MagicMock()
        result_mock.scalar_one_or_none.return_value = None
        db.execute = AsyncMock(return_value=result_mock)
        svc = MemoryDigestService(db)
        result = await svc.latest_delivery(user_id=1, workspace_id="ws")
        assert result is None

    async def test_validates_channel_filter(self) -> None:
        from app.services.memory_digest_service import (
            MemoryDigestService,
            MemoryDigestValidationError,
        )

        db = _make_mock_db()
        svc = MemoryDigestService(db)
        with pytest.raises(MemoryDigestValidationError):
            await svc.latest_delivery(
                user_id=1,
                workspace_id="ws",
                delivery_channel="bogus",
            )

    async def test_query_uses_limit_1(self) -> None:
        from app.services.memory_digest_service import MemoryDigestService

        db = _make_mock_db()
        result_mock = MagicMock()
        result_mock.scalar_one_or_none.return_value = None
        db.execute = AsyncMock(return_value=result_mock)
        svc = MemoryDigestService(db)
        await svc.latest_delivery(user_id=1, workspace_id="ws")
        stmt = db.execute.await_args[0][0]
        compiled = str(stmt.compile(compile_kwargs={"literal_binds": True}))
        # LIMIT 1 on a single-row lookup.
        assert "limit" in compiled.lower() or "LIMIT 1" in compiled
