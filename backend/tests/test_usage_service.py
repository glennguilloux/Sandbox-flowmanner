import os

os.environ.setdefault("OPENAI_API_KEY", "sk-test")

from datetime import UTC, datetime, timedelta

import pytest

from app.services.usage_service import UsageService, get_usage_service


@pytest.fixture
def svc() -> UsageService:
    service = UsageService()
    return service


def test_record_usage_stores_record(svc: UsageService) -> None:
    record = svc.record_usage(
        user_id="u1",
        model_id="gpt-4o",
        provider="openai",
        prompt_tokens=100,
        completion_tokens=50,
    )

    assert record.user_id == "u1"
    assert record.model_id == "gpt-4o"
    assert record.provider == "openai"
    assert record.prompt_tokens == 100
    assert record.completion_tokens == 50
    assert record.cost > 0

    raw = svc.get_raw_records("u1")
    assert len(raw) == 1
    assert raw[0] == record


def test_record_usage_auto_calculates_cost(svc: UsageService) -> None:
    record = svc.record_usage(
        "u2", "gpt-4o", "openai", prompt_tokens=1000, completion_tokens=500
    )
    expected_cost = round((1000 * 0.000003) + (500 * 0.000006), 8)
    assert record.cost == expected_cost


def test_record_usage_accepts_explicit_cost(svc: UsageService) -> None:
    record = svc.record_usage(
        "u3", "gpt-4o", "openai", prompt_tokens=10, completion_tokens=10, cost=0.99
    )
    assert record.cost == 0.99


def test_get_summary_aggregates_tokens_and_cost(svc: UsageService) -> None:
    svc.record_usage("u4", "gpt-4o", "openai", prompt_tokens=100, completion_tokens=50)
    svc.record_usage("u4", "gpt-4o", "openai", prompt_tokens=200, completion_tokens=100)

    summary = svc.get_summary("u4", period="day")

    assert summary.total_tokens == 450
    assert summary.period == "day"
    assert len(summary.breakdown) == 1
    model_entry = summary.breakdown[0]
    assert model_entry.model_id == "gpt-4o"
    assert model_entry.prompt_tokens == 300
    assert model_entry.completion_tokens == 150


def test_get_summary_separates_by_model(svc: UsageService) -> None:
    svc.record_usage("u5", "gpt-4o", "openai", prompt_tokens=100, completion_tokens=50)
    svc.record_usage(
        "u5", "claude-3", "anthropic", prompt_tokens=200, completion_tokens=100
    )

    summary = svc.get_summary("u5", period="day")

    assert summary.total_tokens == 450
    assert len(summary.breakdown) == 2
    model_ids = {e.model_id for e in summary.breakdown}
    assert model_ids == {"gpt-4o", "claude-3"}


def test_get_summary_filters_by_period(svc: UsageService) -> None:
    old_record = svc.record_usage(
        "u6", "gpt-4o", "openai", prompt_tokens=9999, completion_tokens=9999
    )
    old_record.timestamp = datetime.now(UTC) - timedelta(days=2)

    svc.record_usage("u6", "gpt-4o", "openai", prompt_tokens=10, completion_tokens=5)

    summary = svc.get_summary("u6", period="day")

    assert summary.total_tokens == 15


def test_get_summary_empty_user_returns_zeros(svc: UsageService) -> None:
    summary = svc.get_summary("unknown-user", period="week")
    assert summary.total_tokens == 0
    assert summary.total_cost == 0.0
    assert summary.breakdown == []


def test_get_timeseries_returns_data_points(svc: UsageService) -> None:
    svc.record_usage("u7", "gpt-4o", "openai", prompt_tokens=100, completion_tokens=50)

    points = svc.get_timeseries("u7", period="day", granularity="hour")

    assert len(points) >= 1
    point = points[0]
    assert "timestamp" in point
    assert "tokens" in point
    assert "cost" in point
    assert "request_count" in point
    assert point["tokens"] == 150
    assert point["request_count"] == 1


def test_get_timeseries_buckets_by_hour(svc: UsageService) -> None:
    record1 = svc.record_usage(
        "u8", "gpt-4o", "openai", prompt_tokens=100, completion_tokens=50
    )
    record2 = svc.record_usage(
        "u8", "gpt-4o", "openai", prompt_tokens=200, completion_tokens=100
    )

    points = svc.get_timeseries("u8", period="day", granularity="hour")

    total_tokens = sum(p["tokens"] for p in points)
    assert total_tokens == 450


def test_get_timeseries_empty_returns_empty_list(svc: UsageService) -> None:
    points = svc.get_timeseries("no-user", period="day", granularity="day")
    assert points == []


def test_get_usage_service_returns_singleton() -> None:
    svc1 = get_usage_service()
    svc2 = get_usage_service()
    assert svc1 is svc2


def test_clear_removes_user_records(svc: UsageService) -> None:
    svc.record_usage("u9", "gpt-4o", "openai", prompt_tokens=100, completion_tokens=50)
    assert len(svc.get_raw_records("u9")) == 1
    svc.clear("u9")
    assert svc.get_raw_records("u9") == []


def test_multiple_users_are_isolated(svc: UsageService) -> None:
    svc.record_usage(
        "alice", "gpt-4o", "openai", prompt_tokens=100, completion_tokens=50
    )
    svc.record_usage(
        "bob", "gpt-4o", "openai", prompt_tokens=500, completion_tokens=250
    )

    alice_summary = svc.get_summary("alice", period="day")
    bob_summary = svc.get_summary("bob", period="day")

    assert alice_summary.total_tokens == 150
    assert bob_summary.total_tokens == 750
