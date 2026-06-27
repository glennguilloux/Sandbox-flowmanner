"""Tests for IntegrationHealthService — health checks, storage, and status queries."""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import httpx
import pytest

from app.models.integration_models import IntegrationHealthRecord
from app.services.integration_health_service import HealthResult, IntegrationHealthService

# ── Fixtures ────────────────────────────────────────────────────────────────


def _make_record(
    slug: str = "slack",
    status: str = "healthy",
    latency_ms: int | None = 12,
    checked_at: datetime | None = None,
) -> IntegrationHealthRecord:
    """Create a mock IntegrationHealthRecord."""
    record = MagicMock(spec=IntegrationHealthRecord)
    record.id = str(uuid4())
    record.integration_slug = slug
    record.status = status
    record.latency_ms = latency_ms
    record.status_code = 200
    record.error_message = None
    record.checked_at = checked_at or datetime.now(UTC)
    return record


def _mock_db_with_records(records: list[IntegrationHealthRecord]) -> AsyncMock:
    """Create a mock AsyncSession that returns the given records."""
    db = AsyncMock()
    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = records
    mock_result.scalar_one_or_none.return_value = records[0] if records else None
    db.execute = AsyncMock(return_value=mock_result)
    return db


def _make_mock_response(status_code: int = 200) -> MagicMock:
    """Create a mock httpx.Response."""
    resp = MagicMock(spec=httpx.Response)
    resp.status_code = status_code
    return resp


def _patch_httpx_get(response: httpx.Response | Exception):
    """Context manager that patches httpx.AsyncClient for GET/POST calls.

    ``AsyncMock.__aenter__`` returns a *new* child mock by default, so we
    must explicitly set ``__aenter__.return_value = mock_client`` to ensure
    the ``async with`` block yields our configured mock.
    """
    mock_client = AsyncMock()
    mock_client.__aenter__.return_value = mock_client
    mock_client.__aexit__.return_value = False
    if isinstance(response, Exception):
        mock_client.get = AsyncMock(side_effect=response)
        mock_client.post = AsyncMock(side_effect=response)
    else:
        mock_client.get = AsyncMock(return_value=response)
        mock_client.post = AsyncMock(return_value=response)
    return patch(
        "app.services.integration_health_service.httpx.AsyncClient",
        return_value=mock_client,
    )


# ── HealthResult ────────────────────────────────────────────────────────────


class TestHealthResult:
    def test_to_dict(self):
        result = HealthResult(status="healthy", latency_ms=15, status_code=200, error_message=None)
        d = result.to_dict()
        assert d["status"] == "healthy"
        assert d["latency_ms"] == 15
        assert d["status_code"] == 200
        assert d["error_message"] is None

    def test_defaults(self):
        result = HealthResult(status="unknown")
        assert result.latency_ms is None
        assert result.status_code is None
        assert result.error_message is None


# ── check() ─────────────────────────────────────────────────────────────────


class TestCheck:
    @pytest.mark.asyncio
    async def test_healthy_response(self):
        db = AsyncMock()
        svc = IntegrationHealthService(db)

        with _patch_httpx_get(_make_mock_response(200)):
            result = await svc.check(
                "slack",
                {
                    "endpoint": "https://slack.com/api/auth.test",
                    "method": "POST",
                    "expected_status": 200,
                    "timeout_seconds": 10,
                },
            )

        assert result.status == "healthy"
        assert result.status_code == 200

    @pytest.mark.asyncio
    async def test_degraded_on_4xx(self):
        db = AsyncMock()
        svc = IntegrationHealthService(db)

        with _patch_httpx_get(_make_mock_response(401)):
            result = await svc.check(
                "github",
                {
                    "endpoint": "https://api.github.com/rate_limit",
                    "method": "GET",
                    "expected_status": 200,
                },
            )

        assert result.status == "degraded"
        assert result.status_code == 401

    @pytest.mark.asyncio
    async def test_down_on_5xx(self):
        db = AsyncMock()
        svc = IntegrationHealthService(db)

        with _patch_httpx_get(_make_mock_response(503)):
            result = await svc.check(
                "slack",
                {
                    "endpoint": "https://slack.com/api/auth.test",
                    "method": "POST",
                    "expected_status": 200,
                },
            )

        assert result.status == "down"

    @pytest.mark.asyncio
    async def test_down_on_timeout(self):
        db = AsyncMock()
        svc = IntegrationHealthService(db)

        with _patch_httpx_get(httpx.TimeoutException("timeout")):
            result = await svc.check(
                "slack",
                {
                    "endpoint": "https://slack.com/api/auth.test",
                    "method": "POST",
                    "timeout_seconds": 5,
                },
            )

        assert result.status == "down"
        assert "Timeout" in result.error_message

    @pytest.mark.asyncio
    async def test_down_on_connect_error(self):
        db = AsyncMock()
        svc = IntegrationHealthService(db)

        with _patch_httpx_get(httpx.ConnectError("refused")):
            result = await svc.check(
                "slack",
                {
                    "endpoint": "https://slack.com/api/auth.test",
                    "method": "POST",
                },
            )

        assert result.status == "down"
        assert "Connection failed" in result.error_message

    @pytest.mark.asyncio
    async def test_unknown_for_relative_endpoint(self):
        db = AsyncMock()
        svc = IntegrationHealthService(db)

        result = await svc.check(
            "apiflow",
            {
                "endpoint": "/api/health",
                "method": "GET",
            },
        )

        assert result.status == "unknown"
        assert "Relative" in result.error_message


# ── check_and_store() ───────────────────────────────────────────────────────


class TestCheckAndStore:
    @pytest.mark.asyncio
    async def test_stores_result_after_check(self):
        db = AsyncMock()
        svc = IntegrationHealthService(db)

        with _patch_httpx_get(_make_mock_response(200)):
            result = await svc.check_and_store(
                "slack",
                {
                    "endpoint": "https://slack.com/api/auth.test",
                    "method": "POST",
                    "expected_status": 200,
                },
            )

        assert result.status == "healthy"
        db.add.assert_called_once()
        db.flush.assert_awaited_once()
        stored = db.add.call_args[0][0]
        assert stored.integration_slug == "slack"
        assert stored.status == "healthy"


# ── get_latest_status() ─────────────────────────────────────────────────────


class TestGetLatestStatus:
    @pytest.mark.asyncio
    async def test_returns_latest_record(self):
        record = _make_record(slug="slack", status="healthy")
        db = _mock_db_with_records([record])
        svc = IntegrationHealthService(db)

        result = await svc.get_latest_status("slack")
        assert result is not None
        assert result.integration_slug == "slack"

    @pytest.mark.asyncio
    async def test_returns_none_when_no_records(self):
        db = AsyncMock()
        db.execute = AsyncMock(return_value=MagicMock(scalar_one_or_none=MagicMock(return_value=None)))
        svc = IntegrationHealthService(db)

        result = await svc.get_latest_status("nonexistent")
        assert result is None


# ── get_history() ────────────────────────────────────────────────────────────


class TestGetHistory:
    @pytest.mark.asyncio
    async def test_returns_list_of_records(self):
        records = [_make_record(slug="slack", status="healthy") for _ in range(3)]
        db = _mock_db_with_records(records)
        svc = IntegrationHealthService(db)

        result = await svc.get_history("slack", limit=3)
        assert len(result) == 3


# ── record_failure() / record_outage() ──────────────────────────────────────


class TestRecordFailureAndOutage:
    @pytest.mark.asyncio
    async def test_record_failure_stores_degraded(self):
        db = AsyncMock()
        svc = IntegrationHealthService(db)

        await svc.record_failure("slack", "Connection refused")

        db.add.assert_called_once()
        record = db.add.call_args[0][0]
        assert record.status == "degraded"
        assert record.integration_slug == "slack"
        assert record.error_message == "Connection refused"
        db.flush.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_record_outage_stores_down(self):
        db = AsyncMock()
        svc = IntegrationHealthService(db)

        await svc.record_outage("github", "Circuit open")

        db.add.assert_called_once()
        record = db.add.call_args[0][0]
        assert record.status == "down"
        assert record.error_message == "Circuit open"


# ── cleanup_old_records() ───────────────────────────────────────────────────


class TestCleanupOldRecords:
    @pytest.mark.asyncio
    async def test_deletes_old_records(self):
        db = AsyncMock()
        mock_result = MagicMock()
        mock_result.rowcount = 42
        db.execute = AsyncMock(return_value=mock_result)
        svc = IntegrationHealthService(db)

        count = await svc.cleanup_old_records(days=90)
        assert count == 42
        db.execute.assert_awaited_once()
