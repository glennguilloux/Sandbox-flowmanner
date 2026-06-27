"""Tests for integration health API endpoints — /health and /{slug}/health."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException

from app.api.v1.integrations import (
    get_all_health_statuses,
    get_integration_health,
)

# ── Feature flag gating ─────────────────────────────────────────────────────


class TestHealthFlagGating:
    @pytest.mark.asyncio
    async def test_flag_disabled_raises_404(self):
        """When the health flag is off, the endpoint returns 404."""
        db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar.return_value = None  # flag not found → disabled
        db.execute = AsyncMock(return_value=mock_result)

        # Reset the flag cache
        import app.api.v1.integrations as mod

        mod._flag_cache.pop("integration_health_v1", None)
        mod._health_cache = None

        with pytest.raises(HTTPException) as exc_info:
            await get_all_health_statuses(db=db)
        assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    async def test_flag_enabled_allows_access(self):
        """When the health flag is on, the endpoint returns data."""
        db = AsyncMock()

        # Mock the flag query → enabled
        flag_result = MagicMock()
        flag_result.scalar.return_value = True

        # Mock the health records query (empty)
        health_result = MagicMock()
        health_result.scalars.return_value.all.return_value = []

        # Mock the uptime query
        uptime_result = MagicMock()
        uptime_row = MagicMock()
        uptime_row.total = 0
        uptime_result.one.return_value = uptime_row

        call_count = 0

        async def mock_execute(stmt, params=None):
            nonlocal call_count
            call_count += 1
            sql = str(stmt)
            if "feature_flags" in sql:
                return flag_result
            if "count" in sql.lower() and "healthy" in sql.lower():
                return uptime_result
            return health_result

        db.execute = mock_execute

        # Reset caches
        import app.api.v1.integrations as mod

        mod._flag_cache.pop("integration_health_v1", None)
        mod._health_cache = None

        result = await get_all_health_statuses(db=db)
        assert "integrations" in result
        # Should have entries for each loaded manifest
        assert len(result["integrations"]) > 0

    @pytest.mark.asyncio
    async def test_single_integration_flag_disabled_raises_404(self):
        """When the health flag is off, /{slug}/health returns 404."""
        db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar.return_value = None
        db.execute = AsyncMock(return_value=mock_result)

        import app.api.v1.integrations as mod

        mod._flag_cache.pop("integration_health_v1", None)

        with pytest.raises(HTTPException) as exc_info:
            await get_integration_health(slug="slack", db=db)
        assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    async def test_unknown_integration_returns_404(self):
        """Unknown slug returns 404 even when flag is enabled."""
        db = AsyncMock()
        flag_result = MagicMock()
        flag_result.scalar.return_value = True

        async def mock_execute(stmt, params=None):
            return flag_result

        db.execute = mock_execute

        import app.api.v1.integrations as mod

        mod._flag_cache.pop("integration_health_v1", None)

        with pytest.raises(HTTPException) as exc_info:
            await get_integration_health(slug="nonexistent-integration", db=db)
        assert exc_info.value.status_code == 404


# ── Response shape ──────────────────────────────────────────────────────────


class TestHealthResponseShape:
    @pytest.mark.asyncio
    async def test_single_integration_response_shape(self):
        """Response includes all expected fields."""
        db = AsyncMock()

        # Flag → enabled
        flag_result = MagicMock()
        flag_result.scalar.return_value = True

        # Latest status record
        from datetime import UTC, datetime
        from uuid import uuid4

        from app.models.integration_models import IntegrationHealthRecord

        record = MagicMock(spec=IntegrationHealthRecord)
        record.integration_slug = "slack"
        record.status = "healthy"
        record.latency_ms = 15
        record.status_code = 200
        record.error_message = None
        record.checked_at = datetime.now(UTC)

        latest_result = MagicMock()
        latest_result.scalar_one_or_none.return_value = record

        # History
        history_result = MagicMock()
        history_result.scalars.return_value.all.return_value = [record]

        # Uptime
        uptime_result = MagicMock()
        uptime_row = MagicMock()
        uptime_row.total = 10
        uptime_row.healthy = 9
        uptime_result.one.return_value = uptime_row

        async def mock_execute(stmt, params=None):
            sql = str(stmt)
            if "feature_flags" in sql:
                return flag_result
            if "count" in sql.lower() and "healthy" in sql.lower():
                return uptime_result
            if "ORDER BY" in sql and "LIMIT" in sql:
                return latest_result
            return history_result

        db.execute = mock_execute

        import app.api.v1.integrations as mod

        mod._flag_cache.pop("integration_health_v1", None)

        result = await get_integration_health(slug="slack", db=db)

        assert result["slug"] == "slack"
        assert result["name"] == "Slack"
        assert result["status"] == "healthy"
        assert result["latency_ms"] == 15
        assert result["trust_level"] == "verified"
        assert result["uptime_30d"] == 90.0
        assert result["last_checked"] is not None
        assert isinstance(result["history"], list)

    @pytest.mark.asyncio
    async def test_no_records_returns_unknown(self):
        """When no health records exist, status is 'unknown'."""
        from datetime import UTC, datetime

        db = AsyncMock()

        flag_result = MagicMock()
        flag_result.scalar.return_value = True

        # get_latest_status returns None
        none_result = MagicMock()
        none_result.scalar_one_or_none.return_value = None

        # get_history returns empty list
        empty_result = MagicMock()
        empty_result.scalars.return_value.all.return_value = []

        # compute_uptime_pct returns 0 total
        uptime_result = MagicMock()
        uptime_row = MagicMock()
        uptime_row.total = 0
        uptime_row.healthy = 0
        uptime_result.one.return_value = uptime_row

        call_count = 0

        async def mock_execute(stmt, params=None):
            nonlocal call_count
            call_count += 1
            sql = str(stmt).lower()
            if "feature_flags" in sql:
                return flag_result
            # The aggregate count query for uptime
            if "count" in sql and "healthy" in sql:
                return uptime_result
            # get_latest_status and get_history both return empty
            return none_result if call_count <= 3 else empty_result

        db.execute = mock_execute

        import app.api.v1.integrations as mod

        mod._flag_cache.pop("integration_health_v1", None)

        result = await get_integration_health(slug="slack", db=db)

        assert result["status"] == "unknown"
        assert result["latency_ms"] is None
        assert result["uptime_30d"] is None
        assert result["history"] == []
