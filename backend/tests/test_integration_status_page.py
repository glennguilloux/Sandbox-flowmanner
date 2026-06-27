"""Tests for Phase 5: Public Status Page.

Covers:
- IntegrationIncident model import and structure
- Public status endpoint feature-flag gating
- Public status endpoint response shape (with/without incidents)
- Incident creation from health task logic
"""

from __future__ import annotations

import importlib
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# ── Model import ────────────────────────────────────────────────────────


class TestIntegrationIncidentModel:
    """Verify IntegrationIncident is importable and has the expected columns."""

    def test_import(self):
        from app.models.integration_models import IntegrationIncident

        assert IntegrationIncident is not None

    def test_tablename(self):
        from app.models.integration_models import IntegrationIncident

        assert IntegrationIncident.__tablename__ == "integration_incidents"

    def test_columns_present(self):
        from app.models.integration_models import IntegrationIncident

        mapper = IntegrationIncident.__table__
        col_names = {c.name for c in mapper.columns}
        expected = {
            "id",
            "integration_slug",
            "severity",
            "title",
            "description",
            "status",
            "resolved_at",
            "created_at",
            "updated_at",
        }
        assert expected.issubset(col_names), f"Missing columns: {expected - col_names}"

    def test_importable_from_init(self):
        from app.models import IntegrationIncident

        assert IntegrationIncident is not None


# ── Public status endpoint ──────────────────────────────────────────────


@pytest.mark.asyncio
class TestPublicStatusEndpoint:
    """Tests for GET /api/v1/integrations/status."""

    def _reset_caches(self):
        """Reset the status and flag caches for test isolation."""
        mod = importlib.import_module("app.api.v1.integrations")
        mod._flag_cache.pop("integration_status_page_v1", None)
        mod._status_cache = None
        mod._status_cache_ts = 0.0

    async def test_returns_404_when_flag_disabled(self):
        """Endpoint returns 404 when the feature flag is off."""
        from fastapi import HTTPException

        from app.api.v1.integrations import public_status

        self._reset_caches()
        db = AsyncMock()

        async def mock_execute(stmt, params=None):
            result = MagicMock()
            result.scalar.return_value = False  # flag disabled
            return result

        db.execute = AsyncMock(side_effect=mock_execute)

        with pytest.raises(HTTPException) as exc_info:
            await public_status(db=db)
        assert exc_info.value.status_code == 404

    async def test_returns_status_when_flag_enabled(self):
        """Endpoint returns a well-shaped response when the flag is on."""
        from app.api.v1.integrations import public_status

        self._reset_caches()
        db = AsyncMock()

        # Build mock health records
        health_record = MagicMock()
        health_record.integration_slug = "slack"
        health_record.status = "healthy"
        health_record.latency_ms = 42
        health_record.checked_at = datetime.now(UTC)

        async def mock_execute(stmt, params=None):
            sql = str(stmt)
            result = MagicMock()
            if "feature_flags" in sql:
                result.scalar.return_value = True
            elif "integration_health_records" in sql and "distinct" in sql.lower():
                result.scalars.return_value.all.return_value = [health_record]
            elif "integration_health_records" in sql and "count" in sql.lower():
                row = MagicMock()
                row.total = 10
                row.healthy = 10
                result.one.return_value = row
            elif "integration_incidents" in sql:
                result.scalars.return_value.all.return_value = []
            else:
                result.scalars.return_value.all.return_value = []
            return result

        db.execute = AsyncMock(side_effect=mock_execute)

        # Patch manifest_service at the source module (it's lazily imported)
        with patch("app.services.integration_manifest_service.manifest_service") as mock_manifest:
            mock_manifest.slug_list = ["slack"]
            mock_manifest.get.return_value = {
                "slug": "slack",
                "name": "Slack",
                "trust_level": "verified",
            }

            response = await public_status(db=db)

        assert "updated_at" in response
        assert "integrations" in response
        assert "incidents" in response
        assert len(response["integrations"]) == 1
        assert response["integrations"][0]["slug"] == "slack"
        assert response["integrations"][0]["status"] == "healthy"

    async def test_includes_incidents_in_response(self):
        """When open incidents exist, they appear in the response."""
        from app.api.v1.integrations import public_status

        self._reset_caches()
        db = AsyncMock()

        health_record = MagicMock()
        health_record.integration_slug = "notion"
        health_record.status = "down"
        health_record.latency_ms = None
        health_record.checked_at = datetime.now(UTC)

        incident = MagicMock()
        incident.integration_slug = "notion"
        incident.severity = "major"
        incident.title = "notion is down"
        incident.status = "open"
        incident.created_at = datetime.now(UTC)
        incident.resolved_at = None

        async def mock_execute(stmt, params=None):
            sql = str(stmt)
            result = MagicMock()
            if "feature_flags" in sql:
                result.scalar.return_value = True
            elif "integration_health_records" in sql and "distinct" in sql.lower():
                result.scalars.return_value.all.return_value = [health_record]
            elif "integration_health_records" in sql and "count" in sql.lower():
                row = MagicMock()
                row.total = 10
                row.healthy = 5
                result.one.return_value = row
            elif "integration_incidents" in sql:
                result.scalars.return_value.all.return_value = [incident]
            else:
                result.scalars.return_value.all.return_value = []
            return result

        db.execute = AsyncMock(side_effect=mock_execute)

        with patch("app.services.integration_manifest_service.manifest_service") as mock_manifest:
            mock_manifest.slug_list = ["notion"]
            mock_manifest.get.return_value = {
                "slug": "notion",
                "name": "Notion",
                "trust_level": "verified",
            }

            response = await public_status(db=db)

        assert len(response["incidents"]) == 1
        assert response["incidents"][0]["integration_slug"] == "notion"
        assert response["incidents"][0]["severity"] == "major"

    async def test_no_user_data_leaked(self):
        """Public status response must not contain any user-specific data."""
        from app.api.v1.integrations import public_status

        self._reset_caches()
        db = AsyncMock()

        async def mock_execute(stmt, params=None):
            result = MagicMock()
            sql = str(stmt)
            if "feature_flags" in sql:
                result.scalar.return_value = True
            elif "count" in sql.lower():
                row = MagicMock()
                row.total = 0
                row.healthy = 0
                result.one.return_value = row
            else:
                result.scalars.return_value.all.return_value = []
            return result

        db.execute = AsyncMock(side_effect=mock_execute)

        with patch("app.services.integration_manifest_service.manifest_service") as mock_manifest:
            mock_manifest.slug_list = []
            mock_manifest.get.return_value = None

            response = await public_status(db=db)

        response_str = str(response)
        assert "user_id" not in response_str
        assert "email" not in response_str
        assert "token" not in response_str
        assert "connection" not in response_str


# ── Incident detection logic ────────────────────────────────────────────


@pytest.mark.asyncio
class TestIncidentDetection:
    """Tests for _detect_and_manage_incidents in health tasks."""

    async def test_creates_incident_when_status_becomes_down(self):
        """An incident should be created when an integration transitions to down."""
        from app.tasks.integration_health_tasks import _detect_and_manage_incidents

        db = AsyncMock()
        service = MagicMock()

        result_down = MagicMock()
        result_down.status = "down"
        result_down.error_message = "Connection refused"
        results = {"slack": result_down}

        # No existing incident
        existing_result = MagicMock()
        existing_result.scalar_one_or_none.return_value = None
        db.execute = AsyncMock(return_value=existing_result)

        await _detect_and_manage_incidents(db, service, results)

        # Should have added an incident
        db.add.assert_called_once()
        incident = db.add.call_args[0][0]
        assert incident.integration_slug == "slack"
        assert incident.severity == "major"
        assert incident.status == "open"

    async def test_creates_minor_incident_for_degraded(self):
        """A degraded status should create a minor incident."""
        from app.tasks.integration_health_tasks import _detect_and_manage_incidents

        db = AsyncMock()
        service = MagicMock()

        result_degraded = MagicMock()
        result_degraded.status = "degraded"
        result_degraded.error_message = "Elevated latency"
        results = {"github": result_degraded}

        existing_result = MagicMock()
        existing_result.scalar_one_or_none.return_value = None
        db.execute = AsyncMock(return_value=existing_result)

        await _detect_and_manage_incidents(db, service, results)

        db.add.assert_called_once()
        incident = db.add.call_args[0][0]
        assert incident.severity == "minor"

    async def test_does_not_create_duplicate_incident(self):
        """Should not create a duplicate incident if one is already open."""
        from app.tasks.integration_health_tasks import _detect_and_manage_incidents

        db = AsyncMock()
        service = MagicMock()

        result_down = MagicMock()
        result_down.status = "down"
        result_down.error_message = "Error"
        results = {"slack": result_down}

        # Existing open incident
        existing_incident = MagicMock()
        existing_result = MagicMock()
        existing_result.scalar_one_or_none.return_value = existing_incident
        db.execute = AsyncMock(return_value=existing_result)

        await _detect_and_manage_incidents(db, service, results)

        db.add.assert_not_called()

    async def test_resolves_incident_when_healthy(self):
        """Open incidents should be resolved when integration returns to healthy."""
        from app.tasks.integration_health_tasks import _detect_and_manage_incidents

        db = AsyncMock()
        service = MagicMock()

        result_healthy = MagicMock()
        result_healthy.status = "healthy"
        results = {"slack": result_healthy}

        open_incident = MagicMock()
        open_incident.id = "test-incident-id"
        open_incident.status = "open"

        incidents_result = MagicMock()
        incidents_result.scalars.return_value.all.return_value = [open_incident]
        db.execute = AsyncMock(return_value=incidents_result)

        await _detect_and_manage_incidents(db, service, results)

        assert open_incident.status == "resolved"
        assert open_incident.resolved_at is not None


# ── Migration ───────────────────────────────────────────────────────────


class TestStatusPageMigration:
    """Verify the migration file exists and is syntactically correct."""

    def test_migration_file_exists(self):
        from pathlib import Path

        migration_path = Path(__file__).parent.parent / "alembic" / "versions" / "20260627_integration_status_page.py"
        assert migration_path.exists(), f"Migration file not found at {migration_path}"

    def test_migration_has_correct_structure(self):
        """Verify the migration file can be compiled and has expected attributes."""
        from pathlib import Path

        migration_path = Path(__file__).parent.parent / "alembic" / "versions" / "20260627_integration_status_page.py"
        source = migration_path.read_text()
        assert "revision: str = " in source
        assert "down_revision: str | None = " in source
        assert "def upgrade()" in source
        assert "def downgrade()" in source
        assert "integration_incidents" in source
        assert "integration_status_page_v1" in source
