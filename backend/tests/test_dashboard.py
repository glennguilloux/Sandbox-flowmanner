"""Integration tests for dashboard API endpoints.

Tests all 3 endpoints: GET /analytics, GET /firefighting-metrics, GET /stats.
Validates response shapes, parameter passing, validation, and error handling.
Uses synchronous TestClient with mocked services and auth override.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# ── Mock factories (dicts — Pydantic serializes these cleanly) ──────────────


def _make_mock_analytics_response():
    """Mock analytics response matching DashboardAnalyticsResponse shape."""
    return dict(
        seven_day_success_rate=0.85,
        avg_runtime_seconds=12.5,
        current_queue_depth=3,
        top_failed_missions=[
            dict(mission_name="Data Extraction Pipeline", failure_count=7),
            dict(mission_name="Report Generator", failure_count=4),
        ],
    )


def _make_mock_firefighting_response():
    """Mock firefighting metrics matching FirefightingMetricsResponse shape."""
    return dict(
        failedMissionCount=12,
        avgRetryCount=2.3,
        topErrorCodes=[
            dict(code="TIMEOUT", count=5),
            dict(code="LLM_502", count=3),
        ],
        manualInterventionMissions=[
            dict(
                missionId="mission-001",
                errorCode="TIMEOUT",
                lastUpdateTimestamp="2026-05-27T10:00:00Z",
            ),
        ],
    )


# ═══════════════════════════════════════════════════════════════════════════════
# GET /api/dashboard/analytics
# ═══════════════════════════════════════════════════════════════════════════════


class TestAnalytics:
    """GET /api/dashboard/analytics — dashboard analytics data."""

    def test_get_analytics_success(self, test_client):
        """Returns correct analytics response shape."""
        mock_resp = _make_mock_analytics_response()

        with patch(
            "app.api.v1.dashboard.get_dashboard_analytics",
            new=AsyncMock(return_value=mock_resp),
        ):
            resp = test_client.get("/api/dashboard/analytics")

        assert resp.status_code == 200
        data = resp.json()
        assert data["sevenDaySuccessRate"] == 0.85
        assert data["avgRuntimeSeconds"] == 12.5
        assert data["currentQueueDepth"] == 3
        assert len(data["topFailedMissions"]) == 2
        assert data["topFailedMissions"][0]["missionName"] == "Data Extraction Pipeline"
        assert data["topFailedMissions"][0]["failureCount"] == 7

    def test_get_analytics_service_failure(self, test_client):
        """Service exception returns 500."""
        with patch(
            "app.api.v1.dashboard.get_dashboard_analytics",
            new=AsyncMock(side_effect=RuntimeError("Database timeout")),
        ):
            resp = test_client.get("/api/dashboard/analytics")

        assert resp.status_code == 500
        assert "Database timeout" in resp.json()["detail"]

    def test_get_analytics_empty_top_failed(self, test_client):
        """Empty top_failed_missions list is handled."""
        mock_resp = _make_mock_analytics_response()
        mock_resp["top_failed_missions"] = []

        with patch(
            "app.api.v1.dashboard.get_dashboard_analytics",
            new=AsyncMock(return_value=mock_resp),
        ):
            resp = test_client.get("/api/dashboard/analytics")

        assert resp.status_code == 200
        data = resp.json()
        assert data["topFailedMissions"] == []


# ═══════════════════════════════════════════════════════════════════════════════
# GET /api/dashboard/firefighting-metrics
# ═══════════════════════════════════════════════════════════════════════════════


class TestFirefightingMetrics:
    """GET /api/dashboard/firefighting-metrics — firefighting metrics data."""

    def test_get_firefighting_metrics_success(self, test_client):
        """Returns correct firefighting metrics response shape."""
        mock_resp = _make_mock_firefighting_response()

        with patch(
            "app.api.v1.dashboard.get_firefighting_metrics",
            new=AsyncMock(return_value=mock_resp),
        ):
            resp = test_client.get("/api/dashboard/firefighting-metrics")

        assert resp.status_code == 200
        data = resp.json()
        assert data["failedMissionCount"] == 12
        assert data["avgRetryCount"] == 2.3
        assert len(data["topErrorCodes"]) == 2
        assert data["topErrorCodes"][0]["code"] == "TIMEOUT"
        assert data["topErrorCodes"][0]["count"] == 5
        assert len(data["manualInterventionMissions"]) == 1
        assert data["manualInterventionMissions"][0]["missionId"] == "mission-001"
        assert data["manualInterventionMissions"][0]["errorCode"] == "TIMEOUT"

    def test_get_firefighting_metrics_with_hours(self, test_client):
        """Hours query param is passed to service."""
        mock_resp = _make_mock_firefighting_response()

        with patch(
            "app.api.v1.dashboard.get_firefighting_metrics",
            new=AsyncMock(return_value=mock_resp),
        ) as mock_fn:
            resp = test_client.get(
                "/api/dashboard/firefighting-metrics", params={"hours": 48}
            )

        assert resp.status_code == 200
        mock_fn.assert_called_once()
        call_args = mock_fn.call_args
        assert call_args.args[1] == 48  # hours is second positional arg (db first)

    def test_get_firefighting_metrics_default_hours(self, test_client):
        """Default hours=24 is used when not specified."""
        mock_resp = _make_mock_firefighting_response()

        with patch(
            "app.api.v1.dashboard.get_firefighting_metrics",
            new=AsyncMock(return_value=mock_resp),
        ) as mock_fn:
            resp = test_client.get("/api/dashboard/firefighting-metrics")

        assert resp.status_code == 200
        call_args = mock_fn.call_args
        assert call_args.args[1] == 24

    @pytest.mark.parametrize("hours", [0, 169])
    def test_validation_hours_out_of_range(self, test_client, hours):
        """Hours outside 1-168 returns 422."""
        resp = test_client.get(
            "/api/dashboard/firefighting-metrics", params={"hours": hours}
        )
        assert (
            resp.status_code == 422
        ), f"hours={hours} should return 422, got {resp.status_code}"

    @pytest.mark.parametrize("hours", [1, 168])
    def test_validation_hours_boundaries(self, test_client, hours):
        """Hours at boundaries 1 and 168 are accepted."""
        mock_resp = _make_mock_firefighting_response()

        with patch(
            "app.api.v1.dashboard.get_firefighting_metrics",
            new=AsyncMock(return_value=mock_resp),
        ):
            resp = test_client.get(
                "/api/dashboard/firefighting-metrics", params={"hours": hours}
            )

        assert (
            resp.status_code == 200
        ), f"hours={hours} should be accepted, got {resp.status_code}"

    def test_get_firefighting_metrics_service_failure(self, test_client):
        """Service exception returns 500."""
        with patch(
            "app.api.v1.dashboard.get_firefighting_metrics",
            new=AsyncMock(side_effect=RuntimeError("Metric collection failed")),
        ):
            resp = test_client.get("/api/dashboard/firefighting-metrics")

        assert resp.status_code == 500
        assert "Metric collection failed" in resp.json()["detail"]

    def test_get_firefighting_metrics_empty_lists(self, test_client):
        """Empty error codes and interventions."""
        mock_resp = _make_mock_firefighting_response()
        mock_resp["topErrorCodes"] = []
        mock_resp["manualInterventionMissions"] = []

        with patch(
            "app.api.v1.dashboard.get_firefighting_metrics",
            new=AsyncMock(return_value=mock_resp),
        ):
            resp = test_client.get("/api/dashboard/firefighting-metrics")

        assert resp.status_code == 200
        data = resp.json()
        assert data["topErrorCodes"] == []
        assert data["manualInterventionMissions"] == []


# ═══════════════════════════════════════════════════════════════════════════════
# GET /api/dashboard/stats
# ═══════════════════════════════════════════════════════════════════════════════


class TestStats:
    """GET /api/dashboard/stats — user dashboard stats with DB queries."""

    def test_get_stats_success(self, test_client, mock_db):
        """Stats returns correct shape with DB query results."""
        # Mock the three DB queries: total missions, completed missions, avg tokens
        mock_total = MagicMock()
        mock_total.scalar.return_value = 42

        mock_completed = MagicMock()
        mock_completed.scalar.return_value = 15

        mock_avg = MagicMock()
        mock_avg.scalar.return_value = 2500.0

        mock_db.execute = AsyncMock(side_effect=[mock_total, mock_completed, mock_avg])

        resp = test_client.get("/api/dashboard/stats")

        assert resp.status_code == 200
        data = resp.json()
        assert data["total_requests"] == 42
        assert data["missions_completed"] == 15
        assert data["avg_response_time_ms"] == 2500000.0  # 2500 * 1000
        assert data["uptime_percentage"] == 99.9

    def test_get_stats_db_errors_return_defaults(self, test_client, mock_db):
        """DB query errors are caught silently, returning zeros/defaults."""
        mock_db.execute = AsyncMock(side_effect=RuntimeError("DB unavailable"))

        resp = test_client.get("/api/dashboard/stats")

        assert resp.status_code == 200
        data = resp.json()
        # All defaults when queries fail
        assert data["total_requests"] == 0
        assert data["missions_completed"] == 0
        assert data["avg_response_time_ms"] == 0.0
        assert data["uptime_percentage"] == 99.9

    def test_get_stats_null_avg(self, test_client, mock_db):
        """Null average tokens is handled (keeps avg_response_time_ms at 0)."""
        mock_total = MagicMock()
        mock_total.scalar.return_value = 10

        mock_completed = MagicMock()
        mock_completed.scalar.return_value = 5

        mock_avg = MagicMock()
        mock_avg.scalar.return_value = None  # no tokens used yet

        mock_db.execute = AsyncMock(side_effect=[mock_total, mock_completed, mock_avg])

        resp = test_client.get("/api/dashboard/stats")

        assert resp.status_code == 200
        data = resp.json()
        assert data["total_requests"] == 10
        assert data["missions_completed"] == 5
        assert data["avg_response_time_ms"] == 0.0  # stays 0 when avg is None

    def test_get_stats_partial_errors(self, test_client, mock_db):
        """Some queries succeeding, some failing — partial data returned."""
        mock_total = MagicMock()
        mock_total.scalar.return_value = 30

        # Second query fails, third succeeds
        mock_avg = MagicMock()
        mock_avg.scalar.return_value = 1000.0

        mock_db.execute = AsyncMock(
            side_effect=[mock_total, RuntimeError("Table locked"), mock_avg]
        )

        resp = test_client.get("/api/dashboard/stats")

        assert resp.status_code == 200
        data = resp.json()
        assert data["total_requests"] == 30  # succeeded
        assert data["missions_completed"] == 0  # failed → default
        assert data["avg_response_time_ms"] == 1000000.0  # 1000 * 1000


# ═══════════════════════════════════════════════════════════════════════════════
# Route registration
# ═══════════════════════════════════════════════════════════════════════════════


class TestRouteRegistration:
    """Verify all 3 dashboard endpoints are registered."""

    @pytest.mark.parametrize(
        "path, expected_status",
        [
            ("/api/dashboard/analytics", 200),
            ("/api/dashboard/firefighting-metrics", 200),
            ("/api/dashboard/stats", 200),
        ],
    )
    def test_endpoints_registered(self, test_client, mock_db, path, expected_status):
        """Endpoint returns expected status (not 404)."""
        with (
            patch(
                "app.api.v1.dashboard.get_dashboard_analytics",
                new=AsyncMock(return_value=_make_mock_analytics_response()),
            ),
            patch(
                "app.api.v1.dashboard.get_firefighting_metrics",
                new=AsyncMock(return_value=_make_mock_firefighting_response()),
            ),
        ):
            mock_total = MagicMock()
            mock_total.scalar.return_value = 0
            mock_db.execute = AsyncMock(return_value=mock_total)

            resp = test_client.get(path)
            assert (
                resp.status_code == expected_status
            ), f"Expected {expected_status} for GET {path}, got {resp.status_code}"
