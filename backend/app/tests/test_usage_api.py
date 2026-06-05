import os
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

os.environ.setdefault("OPENAI_API_KEY", "sk-test")

from app.api.deps import get_current_user, get_db
from app.main_fastapi import app
from app.schemas.usage import UsageByModel, UsageSummaryResponse
from app.services.usage_service import get_usage_service

pytestmark = pytest.mark.integration


@pytest.fixture
def mock_usage_service():
    svc = MagicMock()
    svc.get_summary.return_value = UsageSummaryResponse(
        total_tokens=1500,
        total_cost=0.0045,
        period="month",
        breakdown=[
            UsageByModel(
                model_id="gpt-4o",
                provider="openai",
                prompt_tokens=1000,
                completion_tokens=500,
                cost=0.0045,
            )
        ],
    )
    svc.get_timeseries.return_value = [
        {
            "timestamp": "2026-04-01T00:00:00",
            "tokens": 1500,
            "cost": 0.0045,
            "request_count": 3,
        }
    ]
    return svc


@pytest.fixture
def auth_client(mock_db_session, sample_user, mock_usage_service):
    async def override_get_db():
        yield mock_db_session

    async def override_get_current_user():
        return sample_user

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_current_user] = override_get_current_user
    app.dependency_overrides[get_usage_service] = lambda: mock_usage_service

    with TestClient(app) as client:
        yield client

    app.dependency_overrides.pop(get_db, None)
    app.dependency_overrides.pop(get_current_user, None)
    app.dependency_overrides.pop(get_usage_service, None)


@pytest.fixture
def unauth_client(mock_db_session):
    async def override_get_db():
        yield mock_db_session

    app.dependency_overrides[get_db] = override_get_db

    with TestClient(app, raise_server_exceptions=False) as client:
        yield client

    app.dependency_overrides.pop(get_db, None)


class TestUsageSummary:
    def test_summary_returns_200_with_data(self, auth_client, mock_usage_service):
        response = auth_client.get("/api/v1/usage/summary")

        assert response.status_code == 200
        data = response.json()
        assert data["total_tokens"] == 1500
        assert data["total_cost"] == 0.0045
        assert data["period"] == "month"
        assert len(data["breakdown"]) == 1
        assert data["breakdown"][0]["model_id"] == "gpt-4o"

    def test_summary_calls_service_with_correct_period(
        self, auth_client, mock_usage_service
    ):
        auth_client.get("/api/v1/usage/summary?period=7d")
        mock_usage_service.get_summary.assert_called_once_with(
            user_id="1", period="week"
        )

    def test_summary_30d_maps_to_month(self, auth_client, mock_usage_service):
        auth_client.get("/api/v1/usage/summary?period=30d")
        mock_usage_service.get_summary.assert_called_once_with(
            user_id="1", period="month"
        )

    def test_summary_default_period_is_30d(self, auth_client, mock_usage_service):
        auth_client.get("/api/v1/usage/summary")
        mock_usage_service.get_summary.assert_called_once_with(
            user_id="1", period="month"
        )

    def test_summary_401_without_auth(self, unauth_client):
        response = unauth_client.get("/api/v1/usage/summary")
        assert response.status_code in (401, 403)


class TestUsageTimeseries:
    def test_timeseries_returns_200_with_data(self, auth_client):
        response = auth_client.get("/api/v1/usage/timeseries")

        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        assert len(data) == 1
        point = data[0]
        assert point["timestamp"] == "2026-04-01T00:00:00"
        assert point["tokens"] == 1500
        assert point["cost"] == 0.0045
        assert point["request_count"] == 3

    def test_timeseries_7d_uses_hour_granularity(self, auth_client, mock_usage_service):
        auth_client.get("/api/v1/usage/timeseries?period=7d")
        mock_usage_service.get_timeseries.assert_called_once_with(
            user_id="1", period="week", granularity="hour"
        )

    def test_timeseries_30d_uses_day_granularity(self, auth_client, mock_usage_service):
        auth_client.get("/api/v1/usage/timeseries?period=30d")
        mock_usage_service.get_timeseries.assert_called_once_with(
            user_id="1", period="month", granularity="day"
        )

    def test_timeseries_empty_result(self, auth_client, mock_usage_service):
        mock_usage_service.get_timeseries.return_value = []
        response = auth_client.get("/api/v1/usage/timeseries")
        assert response.status_code == 200
        assert response.json() == []

    def test_timeseries_401_without_auth(self, unauth_client):
        response = unauth_client.get("/api/v1/usage/timeseries")
        assert response.status_code in (401, 403)


class TestUsageBreakdown:
    def test_breakdown_returns_200_with_data(self, auth_client):
        response = auth_client.get("/api/v1/usage/breakdown")

        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        assert len(data) == 1
        item = data[0]
        assert item["model"] == "gpt-4o"
        assert item["provider"] == "openai"
        assert item["tokens"] == 1500
        assert item["cost"] == 0.0045

    def test_breakdown_filters_by_provider(self, auth_client, mock_usage_service):
        response = auth_client.get("/api/v1/usage/breakdown?provider=openai")
        assert response.status_code == 200
        data = response.json()
        assert all(item["provider"] == "openai" for item in data)

    def test_breakdown_provider_filter_case_insensitive(
        self, auth_client, mock_usage_service
    ):
        response = auth_client.get("/api/v1/usage/breakdown?provider=OpenAI")
        assert response.status_code == 200
        assert len(response.json()) == 1

    def test_breakdown_provider_filter_no_match(self, auth_client, mock_usage_service):
        response = auth_client.get("/api/v1/usage/breakdown?provider=anthropic")
        assert response.status_code == 200
        assert response.json() == []

    def test_breakdown_401_without_auth(self, unauth_client):
        response = unauth_client.get("/api/v1/usage/breakdown")
        assert response.status_code in (401, 403)

    def test_breakdown_empty_when_no_usage(self, auth_client, mock_usage_service):
        mock_usage_service.get_summary.return_value = UsageSummaryResponse(
            total_tokens=0, total_cost=0.0, period="month", breakdown=[]
        )
        response = auth_client.get("/api/v1/usage/breakdown")
        assert response.status_code == 200
        assert response.json() == []
